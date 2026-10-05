"""在 Neo4j 上执行变更集并写入版本记录。

一次 :meth:`VersionedGraph.commit` 是一个事务：

1. 锁住分支节点（所有写同一分支的提交因此串行）；
2. 取出变更集涉及的节点与边，用 :func:`~graph_vc.state.check_preconditions` 核对改前状态；
3. 按固定顺序执行修改：删边、建节点、改节点、建边与改边、删节点；
4. 写提交节点 ``(:Commit)``，连 ``PARENT`` 到父提交、``TOUCHED`` 到本次触及且仍存在的节点，推进分支头。

任一步失败，整个事务回滚。图外文件在事务开始前核对：必须已存在且哈希一致。

版本记录占用 ``Commit``、``Branch``、``IdCounter`` 三个 Label 与 ``PARENT``、``TOUCHED`` 两种关系，
变更集不能触及它们；:meth:`VersionedGraph.snapshot` 也不包含它们。需要 Neo4j 5.26 及以上（动态 Label）。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neo4j import Driver, ManagedTransaction

from .changeset import RESERVED_LABELS, RESERVED_TYPES, Changeset, EdgeChange, EdgeKey, Properties
from .errors import ChangesetError, Conflict, ConflictError, FileIntegrityError, GraphVCError
from .state import GraphState, NodeState, check_preconditions

COMMIT_PREFIX = "commit"
PREFIX = re.compile(r"^[a-z][a-z0-9_]*$")

_RESERVED_LABELS = sorted(RESERVED_LABELS)
_RESERVED_TYPES = sorted(RESERVED_TYPES)

_SETUP = [
    "CREATE CONSTRAINT graph_vc_commit_id IF NOT EXISTS FOR (c:Commit) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT graph_vc_branch_name IF NOT EXISTS FOR (b:Branch) REQUIRE b.name IS UNIQUE",
    "CREATE CONSTRAINT graph_vc_counter_prefix IF NOT EXISTS FOR (c:IdCounter) REQUIRE c.prefix IS UNIQUE",
]


@dataclass(frozen=True, slots=True)
class CommitRecord:
    """一个提交。``touched`` 是本次触及且仍存在的节点，``removed`` 是本次删除的节点。"""

    id: str
    branch: str
    seq: int
    parent: str | None
    author: str
    at: str
    message: str
    source: str
    changeset: Changeset
    base: str | None = None
    input: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    touched: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


class VersionedGraph:
    """带版本记录的图写入入口。

    ``file_root`` 是变更集中 :class:`~graph_vc.changeset.FileRef` 相对路径的根目录；
    ``node_labels`` / ``rel_types`` 给出时，变更集只能使用其中的 Label 与关系类型。
    """

    def __init__(
        self,
        driver: Driver,
        *,
        database: str | None = None,
        file_root: Path | None = None,
        node_labels: frozenset[str] | None = None,
        rel_types: frozenset[str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._driver = driver
        self._database = database
        self._file_root = file_root
        self._node_labels = node_labels
        self._rel_types = rel_types
        self._clock = clock or (lambda: datetime.now(UTC))

    # ── 初始化与 id ───────────────────────────────────────────────────

    def setup(self, branch: str = "main") -> None:
        """建立版本记录所需的约束与分支节点；可重复调用。"""
        for statement in _SETUP:
            self._driver.execute_query(statement, database_=self._database)
        self._driver.execute_query("MERGE (:Branch {name: $name})", name=branch, database_=self._database)

    def allocate_ids(self, prefix: str, count: int = 1, *, width: int = 4) -> list[str]:
        """分配 ``count`` 个新 id（``<prefix>_<序号>``）。

        计数器存在库中，首次使用时从库里该前缀已用的最大序号起算。分配即消耗：
        之后写入失败只留下空号，被删节点的 id 也不会再分配。
        """
        if not PREFIX.match(prefix) or prefix == COMMIT_PREFIX:
            raise ValueError(f"invalid id prefix {prefix!r}")
        if count < 1:
            raise ValueError("count must be positive")
        with self._session() as session:
            last = session.execute_write(_allocate, prefix, count)
        return [f"{prefix}_{n:0{width}d}" for n in range(last - count + 1, last + 1)]

    # ── 写入 ──────────────────────────────────────────────────────────

    def commit(
        self,
        changeset: Changeset,
        *,
        author: str,
        message: str = "",
        source: str = "",
        branch: str = "main",
        base: str | None = None,
        input: str | None = None,
        meta: Mapping[str, Any] | None = None,
    ) -> CommitRecord:
        """在一个事务中执行变更集并写入提交记录。

        ``source`` 是写入来源（如 ``commit-tool``、某个 Agent 算子），``base`` 是写入者读视图时所在的提交，
        ``input`` 是交上来的原文，``meta`` 是其余需要随提交保存的信息（须可序列化为 JSON）。

        Raises:
            ChangesetError: 变更集为空或不合法。
            FileIntegrityError: 引用的文件缺失或哈希不一致。
            ConflictError: 改前状态与库中当前状态不一致。
        """
        if not changeset:
            raise ChangesetError(["changeset is empty"])
        changeset.validate(node_labels=self._node_labels, rel_types=self._rel_types)
        self._check_files(changeset)
        draft = _Draft(
            branch=branch,
            author=author,
            at=self._clock().isoformat(),
            message=message,
            source=source,
            base=base,
            input=input,
            meta=dict(meta or {}),
            changeset=changeset,
        )
        with self._session() as session:
            return session.execute_write(_commit, draft)

    def revert(self, commit_id: str, *, author: str, message: str = "", branch: str = "main") -> CommitRecord:
        """以一个新提交撤销 ``commit_id``：执行它的逆向变更集，不改写历史。"""
        target = self.get_commit(commit_id)
        return self.commit(
            target.changeset.invert(),
            author=author,
            message=message or f"Revert {commit_id}",
            source=f"revert:{commit_id}",
            branch=branch,
        )

    # ── 读取 ──────────────────────────────────────────────────────────

    def head(self, branch: str = "main") -> str | None:
        records = self._read("MATCH (b:Branch {name: $name}) RETURN b.head AS head", name=branch)
        if not records:
            raise GraphVCError(f"unknown branch {branch!r}; call setup() first")
        return records[0]["head"]

    def get_commit(self, commit_id: str) -> CommitRecord:
        records = self._read("MATCH (c:Commit {id: $id}) RETURN properties(c) AS c", id=commit_id)
        if not records:
            raise GraphVCError(f"unknown commit {commit_id!r}")
        return _record_from_props(records[0]["c"])

    def history(self, branch: str = "main") -> list[CommitRecord]:
        """分支上的全部提交，从最早到最新。"""
        records = self._read(
            """MATCH (b:Branch {name: $name})
               MATCH (h:Commit {id: b.head})-[:PARENT*0..]->(c:Commit)
               RETURN properties(c) AS c ORDER BY c.seq""",
            name=branch,
        )
        return [_record_from_props(r["c"]) for r in records]

    def snapshot(self) -> GraphState:
        """当前受版本管理的状态：带 ``id`` 的非版本记录节点，以及它们之间的非版本记录关系。"""
        nodes = self._read(
            """MATCH (n) WHERE n.id IS NOT NULL AND none(l IN labels(n) WHERE l IN $labels)
               RETURN n.id AS id, labels(n) AS labels, properties(n) AS props""",
            labels=_RESERVED_LABELS,
        )
        edges = self._read(
            """MATCH (a)-[r]->(b)
               WHERE a.id IS NOT NULL AND b.id IS NOT NULL AND NOT type(r) IN $types
                 AND none(l IN labels(a) + labels(b) WHERE l IN $labels)
               RETURN a.id AS src, type(r) AS type, b.id AS dst, properties(r) AS props""",
            labels=_RESERVED_LABELS,
            types=_RESERVED_TYPES,
        )
        return _state_from_rows(nodes, edges)

    # ── 内部 ──────────────────────────────────────────────────────────

    def _session(self):
        return self._driver.session(database=self._database)

    def _read(self, query: str, **params: Any) -> list[Any]:
        return self._driver.execute_query(query, params, database_=self._database).records

    def _check_files(self, changeset: Changeset) -> None:
        if not changeset.files:
            return
        if self._file_root is None:
            raise FileIntegrityError(["changeset references files but no file_root is configured"])
        problems = []
        for ref in changeset.files:
            path = self._file_root / ref.path
            if not path.is_file():
                problems.append(f"{ref.path}: missing")
            elif sha256_file(path) != ref.sha256:
                problems.append(f"{ref.path}: sha256 mismatch")
        if problems:
            raise FileIntegrityError(problems)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ── 事务函数 ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Draft:
    branch: str
    author: str
    at: str
    message: str
    source: str
    base: str | None
    input: str | None
    meta: dict[str, Any]
    changeset: Changeset


def _allocate(tx: ManagedTransaction, prefix: str, count: int) -> int:
    record = tx.run(
        "MATCH (c:IdCounter {prefix: $prefix}) SET c.last = c.last + $count RETURN c.last AS last",
        prefix=prefix,
        count=count,
    ).single()
    if record is not None:
        return record["last"]
    record = tx.run(
        """OPTIONAL MATCH (n) WHERE n.id STARTS WITH $stem
           WITH max(toInteger(substring(n.id, size($stem)))) AS used
           MERGE (c:IdCounter {prefix: $prefix})
           ON CREATE SET c.last = coalesce(used, 0)
           SET c.last = c.last + $count
           RETURN c.last AS last""",
        prefix=prefix,
        stem=f"{prefix}_",
        count=count,
    ).single()
    return record["last"]


def _commit(tx: ManagedTransaction, draft: _Draft) -> CommitRecord:
    cs = draft.changeset
    lock = tx.run(
        "MATCH (b:Branch {name: $name}) SET b.seq = coalesce(b.seq, 0) + 1 RETURN b.head AS head, b.seq AS seq",
        name=draft.branch,
    ).single()
    if lock is None:
        raise GraphVCError(f"unknown branch {draft.branch!r}; call setup() first")

    conflicts = check_preconditions(cs, _fetch_state(tx, cs))
    if conflicts:
        raise ConflictError(conflicts)

    _write_changes(tx, cs)

    commit_id = f"{COMMIT_PREFIX}_{_allocate(tx, COMMIT_PREFIX, 1):06d}"
    removed = tuple(n.id for n in cs.nodes if n.op == "delete")
    touched = _touched(cs)
    record = CommitRecord(
        id=commit_id,
        branch=draft.branch,
        seq=lock["seq"],
        parent=lock["head"],
        author=draft.author,
        at=draft.at,
        message=draft.message,
        source=draft.source,
        changeset=cs,
        base=draft.base,
        input=draft.input,
        meta=draft.meta,
        touched=tuple(touched),
        removed=removed,
    )
    tx.run("CREATE (c:Commit) SET c = $props", props=_record_to_props(record))
    if record.parent is not None:
        tx.run(
            "MATCH (c:Commit {id: $id}), (p:Commit {id: $parent}) CREATE (c)-[:PARENT]->(p)",
            id=commit_id,
            parent=record.parent,
        )
    _expect(
        tx,
        """UNWIND $rows AS row MATCH (c:Commit {id: $id}), (n {id: row.id})
           CREATE (c)-[:TOUCHED {op: row.op}]->(n) RETURN count(*) AS c""",
        len(touched),
        "touched index",
        id=commit_id,
        rows=[{"id": k, "op": v} for k, v in touched.items()],
    )
    tx.run("MATCH (b:Branch {name: $name}) SET b.head = $id", name=draft.branch, id=commit_id)
    return record


def _fetch_state(tx: ManagedTransaction, cs: Changeset) -> GraphState:
    """取出核对前提所需的局部状态：涉及的节点、涉及的边，以及被删节点的全部关系。"""
    ids = sorted({n.id for n in cs.nodes} | {end for e in cs.edges for end in (e.key.src, e.key.dst)})
    deleted = sorted(n.id for n in cs.nodes if n.op == "delete")
    nodes = tx.run(
        """UNWIND $ids AS id MATCH (n {id: id})
           RETURN n.id AS id, labels(n) AS labels, properties(n) AS props""",
        ids=ids,
    ).data()
    for row in nodes:
        reserved = RESERVED_LABELS & set(row["labels"])
        if reserved:
            raise ChangesetError([f"node {row['id']!r} is a version record ({', '.join(sorted(reserved))})"])
    listed = tx.run(
        """UNWIND $keys AS k MATCH (a {id: k.src})-[r:$(k.type)]->(b {id: k.dst})
           RETURN elementId(r) AS rid, a.id AS src, type(r) AS type, b.id AS dst, properties(r) AS props""",
        keys=[{"src": e.key.src, "type": e.key.type, "dst": e.key.dst} for e in cs.edges],
    ).data()
    incident = tx.run(
        """UNWIND $ids AS id MATCH (n {id: id})-[r]-()
           WHERE NOT type(r) IN $types
           RETURN elementId(r) AS rid, startNode(r).id AS src, type(r) AS type, endNode(r).id AS dst,
                  properties(r) AS props""",
        ids=deleted,
        types=_RESERVED_TYPES,
    ).data()
    unmanaged = [r for r in incident if r["src"] is None or r["dst"] is None]
    if unmanaged:
        raise ConflictError(
            [
                Conflict(
                    f"{r['src']}-[{r['type']}]->{r['dst']}", "relationship to a node without id cannot be versioned"
                )
                for r in unmanaged
            ]
        )
    # 同一条关系可能同时出现在两次查询中（被删节点上、且列在变更集里的边），按 elementId 去重。
    edges = list({r["rid"]: r for r in listed + incident}.values())
    return _state_from_rows(nodes, edges)


def _write_changes(tx: ManagedTransaction, cs: Changeset) -> None:
    edge_deletes = [_edge_row(e) for e in cs.edges if e.op == "delete"]
    _expect(
        tx,
        """UNWIND $rows AS row MATCH (a {id: row.src})-[r:$(row.type)]->(b {id: row.dst})
           DELETE r RETURN count(*) AS c""",
        len(edge_deletes),
        "relationship deletes",
        rows=edge_deletes,
    )

    creates = [
        {"id": n.id, "labels": sorted(n.labels_after or ()), "props": n.after} for n in cs.nodes if n.op == "create"
    ]
    _expect(
        tx,
        """UNWIND $rows AS row CREATE (n:$(row.labels)) SET n = row.props, n.id = row.id
           RETURN count(*) AS c""",
        len(creates),
        "node creates",
        rows=creates,
    )

    updates = [n for n in cs.nodes if n.op == "update"]
    removals = [{"id": n.id, "labels": sorted((n.labels_before or set()) - (n.labels_after or set()))} for n in updates]
    additions = [
        {"id": n.id, "labels": sorted((n.labels_after or set()) - (n.labels_before or set()))} for n in updates
    ]
    removals = [r for r in removals if r["labels"]]
    additions = [r for r in additions if r["labels"]]
    _expect(
        tx,
        "UNWIND $rows AS row MATCH (n {id: row.id}) REMOVE n:$(row.labels) RETURN count(*) AS c",
        len(removals),
        "label removals",
        rows=removals,
    )
    _expect(
        tx,
        "UNWIND $rows AS row MATCH (n {id: row.id}) SET n:$(row.labels) RETURN count(*) AS c",
        len(additions),
        "label additions",
        rows=additions,
    )
    prop_updates = [{"id": n.id, "props": n.after} for n in updates if n.after]
    _expect(
        tx,
        "UNWIND $rows AS row MATCH (n {id: row.id}) SET n += row.props RETURN count(*) AS c",
        len(prop_updates),
        "property updates",
        rows=prop_updates,
    )

    edge_creates = [_edge_row(e, e.after) for e in cs.edges if e.op == "create"]
    _expect(
        tx,
        """UNWIND $rows AS row MATCH (a {id: row.src}), (b {id: row.dst})
           CREATE (a)-[r:$(row.type)]->(b) SET r = row.props RETURN count(*) AS c""",
        len(edge_creates),
        "relationship creates",
        rows=edge_creates,
    )
    edge_updates = [_edge_row(e, e.after) for e in cs.edges if e.op == "update"]
    _expect(
        tx,
        """UNWIND $rows AS row MATCH (a {id: row.src})-[r:$(row.type)]->(b {id: row.dst})
           SET r += row.props RETURN count(*) AS c""",
        len(edge_updates),
        "relationship updates",
        rows=edge_updates,
    )

    deletes = [n.id for n in cs.nodes if n.op == "delete"]
    tx.run("UNWIND $ids AS id MATCH (n {id: id})<-[t:TOUCHED]-(:Commit) DELETE t", ids=deletes)
    _expect(
        tx,
        "UNWIND $ids AS id MATCH (n {id: id}) DELETE n RETURN count(*) AS c",
        len(deletes),
        "node deletes",
        ids=deletes,
    )


def _edge_row(change: EdgeChange, props: Properties | None = None) -> dict[str, Any]:
    return {"src": change.key.src, "type": change.key.type, "dst": change.key.dst, "props": props}


def _expect(tx: ManagedTransaction, query: str, expected: int, what: str, **params: Any) -> None:
    """执行一条批量语句并核对影响行数；不符说明前提核对之后状态又变了，或语句本身有缺陷。"""
    if expected == 0:
        return
    actual = tx.run(query, params).single()["c"]
    if actual != expected:
        raise GraphVCError(f"{what}: expected {expected} rows, got {actual}; transaction rolled back")


def _touched(cs: Changeset) -> dict[str, str]:
    """本次触及且仍存在的节点：新建、修改，以及增删改过关系的端点（op 为 ``edge``）。"""
    touched: dict[str, str] = {}
    deleted = {n.id for n in cs.nodes if n.op == "delete"}
    for n in cs.nodes:
        if n.op != "delete":
            touched[n.id] = n.op
    for e in cs.edges:
        for end in (e.key.src, e.key.dst):
            if end not in deleted:
                touched.setdefault(end, "edge")
    return dict(sorted(touched.items()))


# ── 记录与行的转换 ────────────────────────────────────────────────────


def _record_to_props(record: CommitRecord) -> dict[str, Any]:
    props: dict[str, Any] = {
        "id": record.id,
        "branch": record.branch,
        "seq": record.seq,
        "parent": record.parent,
        "author": record.author,
        "at": record.at,
        "message": record.message,
        "source": record.source,
        "base": record.base,
        "input": record.input,
        "meta": _dumps(record.meta),
        "changeset": _dumps(record.changeset.to_dict()),
        "touched": list(record.touched),
        "removed": list(record.removed),
    }
    return {k: v for k, v in props.items() if v is not None}


def _record_from_props(props: Mapping[str, Any]) -> CommitRecord:
    return CommitRecord(
        id=props["id"],
        branch=props["branch"],
        seq=props["seq"],
        parent=props.get("parent"),
        author=props["author"],
        at=props["at"],
        message=props.get("message", ""),
        source=props.get("source", ""),
        changeset=Changeset.from_dict(json.loads(props["changeset"])),
        base=props.get("base"),
        input=props.get("input"),
        meta=json.loads(props.get("meta", "{}")),
        touched=tuple(props.get("touched", ())),
        removed=tuple(props.get("removed", ())),
    )


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _state_from_rows(nodes: list[Mapping[str, Any]], edges: list[Mapping[str, Any]]) -> GraphState:
    state = GraphState()
    for row in nodes:
        if row["id"] in state.nodes:
            raise GraphVCError(f"duplicate node id {row['id']!r} in the database")
        props = {k: v for k, v in row["props"].items() if k != "id"}
        state.nodes[row["id"]] = NodeState(frozenset(row["labels"]), props)
    for row in edges:
        key = EdgeKey(row["src"], row["type"], row["dst"])
        if key in state.edges:
            raise GraphVCError(f"parallel relationships {key} cannot be versioned")
        state.edges[key] = dict(row["props"])
    return state


__all__ = ["CommitRecord", "VersionedGraph", "sha256_file"]
