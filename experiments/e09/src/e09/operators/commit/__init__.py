"""Commit：增量检查 → plan（dry_run，只查不写）→ apply（单事务）→ 复核（docs/designs/v2/commit_contract.md）。

- seed：种子增量（Entity、Concept 与它们的 NameKey、关系），make seed 使用；
- paper：论文表单编译出的增量（form.py），含 Experiment、ResultUnit、Material 与 IngestBatch。
"""

from .paper import PaperPlan, apply_paper, dry_run, paper_summary
from .seed import Plan, apply_plan, check_seed, plan_seed, summary

__all__ = ["Plan", "apply_plan", "check_seed", "plan_seed", "summary",
           "PaperPlan", "dry_run", "apply_paper", "paper_summary"]
