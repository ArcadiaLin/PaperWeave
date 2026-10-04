"""环境自检：连上 neo4j-e09，报告版本与 edition，确认不是 v1 库，并检查材料与种子目录。

只读，不写任何数据。neo4j-e08 与 neo4j-e09 端口相同，靠 v1 Label 检查防止连错库。

    uv run python -m e09.env_check
"""

import sys

from neo4j import GraphDatabase

from .config import NEO4J_AUTH, NEO4J_DB, NEO4J_URI, PAPERS, SEEDS

V1_LABELS = {"MethodConcept", "ClaimConcept", "Resource", "ResourceRecord"}   # 出现即说明连到了 v1 库


def check_graph(out=sys.stdout) -> list[str]:
    """out：自检信息写到哪里；单表单入口传 stderr，让 stdout 只留 plan。"""
    with GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH) as driver:
        driver.verify_connectivity()
        comp, _, _ = driver.execute_query(
            "CALL dbms.components() YIELD name, versions, edition RETURN name, versions[0] AS version, edition",
            database_=NEO4J_DB)
        for r in comp:
            print(f"{r['name']} {r['version']} ({r['edition']}) @ {NEO4J_URI}", file=out)
        labels, _, _ = driver.execute_query("CALL db.labels() YIELD label RETURN collect(label) AS labels", database_=NEO4J_DB)
        found = set(labels[0]["labels"])
        nodes, _, _ = driver.execute_query("MATCH (n) RETURN count(n) AS n", database_=NEO4J_DB)
        print(f"节点数 {nodes[0]['n']}；Label {sorted(found) or '（空库）'}", file=out)
    if found & V1_LABELS:
        return [f"发现 v1 Label {sorted(found & V1_LABELS)}，可能连到了 neo4j-e08"]
    return []


def check_files() -> list[str]:
    papers = sorted(p.name for p in PAPERS.iterdir() if (p / "paper.md").is_file()) if PAPERS.is_dir() else []
    seeds = sorted(p.name for p in SEEDS.glob("*.yml"))
    print(f"论文材料 {len(papers)} 篇：{papers}")
    print(f"种子 {seeds}")
    return [] if papers and seeds else [f"材料或种子缺失：{PAPERS}、{SEEDS}"]


def main() -> int:
    errors = check_files() + check_graph()
    for e in errors:
        print(f"错误：{e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
