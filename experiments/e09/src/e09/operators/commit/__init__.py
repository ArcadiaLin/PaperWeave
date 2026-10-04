"""Commit：增量检查 → plan（dry_run，只查不写）→ apply（单事务）→ 复核（docs/designs/v2/commit_contract.md）。

- seed：种子增量（Entity、Concept 与它们的 NameKey、关系），make seed 使用；
- paper：论文表单 paper-form-v4 编译出的增量（form.py），含 Experiment、Claim、Contribution、Material 与 IngestBatch；
  plan_view 给出结构化的 plan，单表单入口见 e09.commit；
- supplement：增补表单 supplement-form-v1 编译出的增量，含 Observation、Agent 认为的贡献与正反关系。
"""

from .paper import PaperPlan, apply_paper, dry_run, paper_summary, plan_view
from .seed import Plan, apply_plan, check_seed, plan_seed, summary
from .supplement import SupplementPlan, apply_supplement, dry_run_supplement, supplement_summary, supplement_view

__all__ = ["Plan", "apply_plan", "check_seed", "plan_seed", "summary",
           "PaperPlan", "dry_run", "apply_paper", "paper_summary", "plan_view",
           "SupplementPlan", "dry_run_supplement", "apply_supplement", "supplement_summary", "supplement_view"]
