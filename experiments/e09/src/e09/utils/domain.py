"""领域配置：每个领域的条件槽与切分约定（docs/designs/v2/extraction_principles.md §4）。

条件槽进入结果行的行键，也是可比性条件。取值都是字符串或 null，语法按槽声明：
- int：整数，如 "96"
- best-of：多个候选中逐任务取最优，如 "best-of{24,48,96}"
- convention：沿用有名字的切分约定，如 "convention:ltsf-autoformer"
- null：原文未写明

切分约定只登记名称与出处，内容留空：规则只比较名字；具体怎么切属于出处论文自身的抽取。
"""

import re

GRAMMAR = {
    "int": re.compile(r"\d+"),
    "best-of": re.compile(r"best-of\{\d+(,\d+)*\}"),
    "convention": re.compile(r"convention:([a-z0-9-]+)"),
}

DOMAINS = {
    "ltsf": {
        # forms：允许的取值语法；row_label：原表把它印在行标签上，行级取值须与原文核对
        "slots": {
            "horizon": {"forms": {"int"}, "row_label": True},                   # 预测长度：原表必写，不允许留空
            "lookback": {"forms": {"int", "best-of", "null"}, "row_label": False},   # 回看窗口
            "split": {"forms": {"convention", "null"}, "row_label": False},     # 首个 I3 实例只用切分约定；显式 Split 绑定以后再加
        },
        "conventions": {
            "ltsf-autoformer": {"source": "Wu et al., 2021. Autoformer: Decomposition transformers with "
                                          "auto-correlation for long-term series forecasting. Experimental setup.",
                                "content": None},
        },
    },
}


def slot_form(domain: str, slot: str, value) -> str | None:
    """返回取值所属的语法名；不合声明时返回 None。"""
    allowed = DOMAINS[domain]["slots"][slot]["forms"]
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
