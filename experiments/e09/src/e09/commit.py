"""单表单入库入口：Agent 逐份迭代时调用（docs/designs/v2/commit_contract.md §1）。

    uv run python -m e09.commit <表单.yml>            # compile + dry_run：打印结构化 plan（YAML），只读
    uv run python -m e09.commit <表单.yml> --apply    # plan 为 ready 时写入；有阻塞项时打印 plan，返回非零
    uv run python -m e09.commit <表单.yml> --text     # 打印给人看的摘要，代替 YAML

返回码：0 = ready / unchanged / 已写入；1 = 有阻塞项；2 = 用法或环境错误。
表单的顶层键 x-ingest 记录提交者与 dry_run 来回轮数，apply 时写进批次记录（§6）。
"""

import sys
from pathlib import Path

import yaml

from .env_check import check_graph
from .form import FORM_VERSION, compile_form
from .operators.commit import apply_paper, dry_run, paper_summary, plan_view
from .utils.graph import driver, ensure_schema


def main(argv) -> int:
    paths = [a for a in argv if not a.startswith("--")]
    if len(paths) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(paths[0])
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if raw.get("form") != FORM_VERSION:
        print(f"错误：当前只接受 {FORM_VERSION}，表单写的是 {raw.get('form')!r}", file=sys.stderr)
        return 2
    if errors := check_graph(out=sys.stderr):   # 与 neo4j-e08 端口相同，先确认连的是 v2 库
        print(f"错误：{errors}", file=sys.stderr)
        return 2
    try:
        delta, issues = compile_form(path)
        p = dry_run(delta, issues)
        if "--apply" in argv and not p.blocked and not p.empty:
            ensure_schema()
            meta = raw.get("x-ingest") or {}
            r = apply_paper(p, committed_by=meta.get("committed_by", "agent"), rounds=meta.get("rounds"))
            out = {"status": "applied", "batch": r["batch"], "embedded": r["embedded"], "ids": r["ids"]}
            print(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))
            return 0
        print(paper_summary(p) if "--text" in argv else yaml.safe_dump(plan_view(p), allow_unicode=True, sort_keys=False, width=120))
        return 1 if p.blocked else 0
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
