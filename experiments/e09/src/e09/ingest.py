"""论文入库入口：按 INGEST_ORDER 读正式表单，逐批 compile → dry_run → apply，写入 neo4j-e09。

    uv run python -m e09.ingest              # 即 make ingest；已入库的批次判为不变，不重复写入
    uv run python -m e09.ingest --dry-run    # 只打印 plan；遇到第一个要写入的批次即停，后面的批次依赖它

表单的顶层键 x-ingest 记录这一批的提交者与 dry_run 来回轮数（编译时忽略 x- 键），写进批次记录，
作为主张 A 的构建成本（commit_contract.md §6）。
"""

import sys

import yaml

from .config import FORMS
from .env_check import check_graph
from .form import compile_form, summary
from .operators.commit import apply_paper, dry_run, paper_summary
from .utils.graph import driver, ensure_schema

# 后一批引用前一批建立的对象，顺序即依赖（commit_contract.md §1 跨批依赖）
INGEST_ORDER = ["2023-DLinear.yml", "2023-PatchTST.yml"]


def main(argv) -> int:
    dry = "--dry-run" in argv
    files = {p.name for p in FORMS.glob("*.yml")}
    if files != set(INGEST_ORDER):
        print(f"错误：表单 {sorted(files)} 与 INGEST_ORDER {INGEST_ORDER} 不一致", file=sys.stderr)
        return 1
    if errors := check_graph():   # 与 neo4j-e08 端口相同，写之前确认不是 v1 库
        print(f"错误：{errors}", file=sys.stderr)
        return 1
    ensure_schema()
    try:
        for f in INGEST_ORDER:
            path = FORMS / f
            meta = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("x-ingest") or {}
            delta, issues = compile_form(path)
            if any(i["level"] == "error" for i in issues) or not delta:
                print(summary(delta, issues))
                return 1
            p = dry_run(delta, issues)
            print(paper_summary(p))
            if p.blocked:
                return 1
            if p.empty:
                continue
            if dry:
                print("（--dry-run：不写入；后面的批次依赖这一批，到此为止）")
                return 0
            r = apply_paper(p, committed_by=meta.get("committed_by", "agent"), rounds=meta.get("rounds"))
            print(f"→ 已写入，批次 {r['batch']}，补算向量 {r['embedded']} 个")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
