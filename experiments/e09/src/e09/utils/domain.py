"""领域配置：每个领域进入结构的实验级条件与切分约定（docs/designs/v2/extraction_principles.md §4）。

报告级入库只在结构里保留规则可直接判定的实验级条件；预测长度、回看窗口等在表内会变的条件写进 Experiment.setting。
条件取值是字符串或 null，语法按声明：
- convention：沿用有名字的切分约定，如 "convention:ltsf-autoformer"
- null：原文未写明

切分约定只登记名称与出处，内容留空：规则只比较名字；具体怎么切属于出处论文自身的抽取。
"""

import re

GRAMMAR = {
    "convention": re.compile(r"convention:([a-z0-9-]+)"),
}

DOMAINS = {
    "ltsf": {
        "conditions": {
            "split": {"convention", "null"},   # 首个 I3 实例只用切分约定；显式 Split 绑定以后再加
        },
        "conventions": {
            "ltsf-autoformer": {"source": "Wu et al., 2021. Autoformer: Decomposition transformers with "
                                          "auto-correlation for long-term series forecasting. Experimental setup.",
                                "content": None},
        },
    },
}


def condition_form(domain: str, name: str, value) -> str | None:
    """返回取值所属的语法名；不合声明时返回 None。"""
    allowed = DOMAINS[domain]["conditions"][name]
    if value is None:
        return "null" if "null" in allowed else None
    if not isinstance(value, str):
        return None
    for form in allowed - {"null"}:
        if m := GRAMMAR[form].fullmatch(value):
            if form == "convention" and m.group(1) not in DOMAINS[domain]["conventions"]:
                return None
            return form
    return None
