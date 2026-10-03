"""graph_model_v2.md 的机器可读部分：kind、命名空间、关系端点与 id 前缀。

与 docs/designs/v2/graph_model_v2.md 不一致时以文档为准，改这里。
覆盖种子与首个 I3 实例用到的部分：Content 只有 Experiment（报告级），另有 Material、IngestBatch。
"""

KINDS = {"Entity": ["Paper", "Dataset", "Split", "Code", "Model", "Benchmark"],         # §2.1
         "Concept": ["Method", "Task", "Metric", "Protocol", "Issue", "Proposition"],   # §3.1
         "Content": ["Experiment"]}                                                     # §4.1；首版只录实验
FAMILY = {k: f for f, ks in KINDS.items() for k in ks}                                 # kind -> 主 Label
SEED_KINDS = {"Entity": {"Dataset", "Model", "Benchmark"}, "Concept": {"Task", "Method", "Metric"}}   # 种子只预置这些
REQUIRED = {"Entity": "description", "Concept": "definition"}
NAMESPACES = {"arxiv": True, "doi": True, "s2": True, "url": False}   # 命名空间 -> 是否唯一（§2.4）
REL_RULES = {   # 已实现写入的关系 -> (起点主 Label, 终点主 Label, 终点 kind 限制)；§6
    "BROADER": ("Concept", "Concept", None), "OVERLAPS_WITH": ("Concept", "Concept", None),
    "PART_OF": ("Entity", "Entity", None), "FOR_TASK": ("Entity", "Concept", "Task"),
    "CITES": ("Entity", "Entity", "Paper")}   # 论文批次：本文 → 被引论文，选择性写入（extraction_principles.md §7）
PAPER_RELS = {"CITES"}   # 论文批次能写的关系；其余关系仍只由种子写入
SYMMETRIC = {"OVERLAPS_WITH"}   # 语义对称，不分方向
FORM_ONLY = {"aliases"}         # 表单字段：注册为 NameKey，不写进对象

# id 形如 <前缀>_<4 位序号>
PREFIX = {"Paper": "paper", "Dataset": "dataset", "Split": "split", "Code": "code", "Model": "model",
          "Benchmark": "bench", "Method": "method", "Task": "task", "Metric": "metric", "Protocol": "protocol",
          "Issue": "issue", "Proposition": "prop", "Experiment": "exp"}

# NameKey 不存成对象上的 aliases 列表，正是为了让唯一约束作用在单个字符串上（第 5 节）
CONSTRAINTS = [
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (n:Concept) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT namekey_key IF NOT EXISTS FOR (k:NameKey) REQUIRE k.key IS UNIQUE",
    # 论文增量的自然键（commit_contract.md §5）与系统记录
    "CREATE CONSTRAINT content_id IF NOT EXISTS FOR (n:Content) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT experiment_key IF NOT EXISTS FOR (n:Experiment) REQUIRE n.exp_key IS UNIQUE",
    "CREATE CONSTRAINT material_hash IF NOT EXISTS FOR (m:Material) REQUIRE m.content_hash IS UNIQUE",
    "CREATE CONSTRAINT batch_id IF NOT EXISTS FOR (b:IngestBatch) REQUIRE b.id IS UNIQUE",
]
# 已退役的约束：ensure_schema 删除。result_row_key 属于行级入库（f95631b），首版改为报告级后不用
RETIRED_CONSTRAINTS = ["result_row_key"]

# 全文索引：名称 -> (Label, 字段, 分词方式)。检索字段按类别声明（intents_decompose.md §6.2）
# - namekey_raw：名称词面通道。名称与 alias 都在 NameKey 上，对象上没有 aliases 列表；默认分词，不做词形还原
# - entity_texts / concept_texts：Entity 的 description、Concept 的 definition 与 scope_note；english 分词
FULLTEXT = {
    "namekey_raw": ("NameKey", ["raw"], "standard-no-stop-words"),
    "entity_texts": ("Entity", ["description"], "english"),
    "concept_texts": ("Concept", ["definition", "scope_note"], "english"),
}
TEXT_FIELDS = {"Entity": ["description"], "Concept": ["definition", "scope_note"]}   # 文本通道与向量共用的字段
