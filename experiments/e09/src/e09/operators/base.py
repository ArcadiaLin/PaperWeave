"""算子的定义：每个算子是一个 :class:`Operator`，字段对应 pi 的 ``ToolDefinition``，可以直接导出为 Agent 的工具。

    operator.execute(ctx, request) -> 结构化结果；不通过时抛出 ContractError（中间件算子）或 OperatorError（Agent 算子）
    operator.call(ctx, request)    -> Result：把这两种错误转成错误结果，给命令行与工具入口用

请求是一个映射，``op`` 为算子名，其余键是该算子的参数，形状由 ``parameters``（JSON Schema）声明。``parameters`` 只
描述顶层形状，供注册工具与 LLM 理解；细的校验由各算子的代码给出 ``{rule, where, msg}`` 或 ``{at, msg}``，不在
两处各写一遍。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..artifact.write import REQUEST_KEYS, REQUIRED, OperatorError, Validate, write_artifact
from ..store.store import ContractError, Store
from ..yamlfmt import dump

Family = Literal["db", "agent"]
FAILED = frozenset({"blocked", "conflict"})  # Commit 没有写入的状态


@dataclass(frozen=True, slots=True)
class Context:
    """一次调用的环境。``at`` 是写入的形成时间；``sync`` 在写入后补算向量，为 ``None`` 时不补算；``text`` 是请求
    原文，写入时记入提交，不给时用请求的 YAML。查询向量由 ``store.embed`` 给出。"""

    store: Store
    at: str
    sync: Callable[[], int] | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class Result:
    """对应 pi 的 ``AgentToolResult``：``details`` 是结构化结果，``text`` 是给 LLM 读的 YAML。"""

    details: dict[str, Any]
    is_error: bool = False

    @property
    def text(self) -> str:
        return dump(self.details)


Execute = Callable[[Context, Mapping[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Operator:
    """一个算子。``family`` 为 ``db``（由中间件执行）或 ``agent``（Agent 给内容，中间件校验后写成 Artifact）；
    ``prompt_snippet`` 与 ``prompt_guidelines`` 对应 pi 的同名字段，后者就是该算子的使用指南；``validate`` 只有
    Agent 算子有。"""

    name: str
    label: str
    description: str
    family: Family
    parameters: dict[str, Any]
    execute: Execute
    writes: bool = False
    prompt_snippet: str | None = None
    prompt_guidelines: tuple[str, ...] = ()
    validate: Validate | None = None

    def call(self, ctx: Context, request: Mapping[str, Any]) -> Result:
        try:
            details = self.execute(ctx, request)
        except ContractError as exc:
            return Result({"error": "contract", "problems": exc.problems}, is_error=True)
        except OperatorError as exc:
            return Result({"errors": exc.errors}, is_error=True)
        return Result(details, is_error=details.get("status") in FAILED)


def schema(properties: Mapping[str, Any], required: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    """对象的 JSON Schema。"""
    out: dict[str, Any] = {"type": "object", "properties": dict(properties), "additionalProperties": False}
    if required:
        out["required"] = list(required)
    return out


def params_of(op: str, parameters: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    """去掉 ``op`` 后的参数，按 ``parameters`` 的顶层形状核对：未知参数与缺少的必填参数是契约错误。

    Raises:
        ContractError: 请求不符合算子契约。
    """
    if not isinstance(request, Mapping):
        raise ContractError([{"at": "request", "msg": "a mapping with op and the operator's parameters"}])
    params = {k: v for k, v in request.items() if k != "op"}
    accepted = set(parameters["properties"]) - {"op"}
    if unknown := sorted(set(params) - accepted):
        raise ContractError([{"at": k, "msg": f"{op} accepts {sorted(accepted)}"} for k in unknown])
    if missing := [k for k in parameters.get("required", []) if k != "op" and k not in params]:
        raise ContractError([{"at": k, "msg": "required"} for k in missing])
    return params


def db_operator(
    *,
    name: str,
    label: str,
    description: str,
    parameters: dict[str, Any],
    run: Callable[..., dict[str, Any]],
    prompt_snippet: str | None = None,
    prompt_guidelines: tuple[str, ...] = (),
) -> Operator:
    """只读的中间件算子：核对参数后调用 ``run(store, **params)``。"""

    def execute(ctx: Context, request: Mapping[str, Any]) -> dict[str, Any]:
        return run(ctx.store, **params_of(name, parameters, request))

    return Operator(name, label, description, "db", parameters, execute, False, prompt_snippet, prompt_guidelines)


def agent_operator(
    *,
    name: str,
    label: str,
    description: str,
    params: dict[str, Any],
    payload: dict[str, Any],
    validate: Validate,
    prompt_snippet: str | None = None,
    prompt_guidelines: tuple[str, ...] = (),
) -> Operator:
    """Agent 算子：``validate`` 检查该算子的 ``params`` 与 ``payload``，其余（共同校验、文档、提交）都经
    :func:`e09.artifact.write.write_artifact`。``params`` 与 ``payload`` 是这两个键的 JSON Schema。"""
    parameters = schema(
        {
            "op": {"const": name},
            "title": {"type": "string", "description": "Optional; generated from op and params when omitted."},
            "abs": {"type": "string", "description": "A few sentences on what this artifact is; used for search."},
            "inputs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Object, source, artifact or record references actually used.",
            },
            "params": params,
            "payload": payload,
            "session": {"type": "string"},
            "formed_by": {"type": "string"},
        },
        [k for k in REQUEST_KEYS if k in REQUIRED],
    )

    def execute(ctx: Context, request: Mapping[str, Any]) -> dict[str, Any]:
        return write_artifact(ctx.store, request, {name: validate}, at=ctx.at, text=ctx.text, sync=ctx.sync)

    return Operator(
        name, label, description, "agent", parameters, execute, True, prompt_snippet, prompt_guidelines, validate
    )


__all__ = [
    "Context",
    "Execute",
    "Family",
    "Operator",
    "Result",
    "agent_operator",
    "db_operator",
    "params_of",
    "schema",
]
