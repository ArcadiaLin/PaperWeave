"""graph_model_v2.md 的机器可读部分：kind、命名空间、关系端点与 id 前缀。

与 docs/designs/v2/graph_model_v2.md 不一致时以文档为准，改这里。
覆盖种子与首个 I3 实例用到的部分：Content 只有 Experiment，另有 ResultUnit、Material、IngestBatch。
"""

KINDS = {"Entity": ["Paper", "Dataset", "Split", "Code", "Model", "Benchmark"],         # §2.1
         "Concept": ["Method", "Task", "Metric", "Protocol", "Issue", "Proposition"],   # §3.1
         "Content": ["Experiment"]}                                                     # §4.1；首版只录实验
FAMILY = {k: f for f, ks in KINDS.items() for k in ks}                                 # kind -> 主 Label
SEED_KINDS = {"Entity": {"Dataset", "Model", "Benchmark"}, "Concept": {"Task", "Method", "Metric"}}   # 种子只预置这些
REQUIRED = {"Entity": "description", "Concept": "definition"}
NAMESPACES = {"arxiv": True, "doi": True, "s2": True, "url": False}   # 命名空间 -> 是否唯一（§2.4）
REL_RULES = {   # 种子用到的关系 -> (起点主 Label, 终点主 Label, 终点 kind 限制)；§6
    "BROADER": ("Concept", "Concept", None), "OVERLAPS_WITH": ("Concept", "Concept", None),
    "PART_OF": ("Entity", "Entity", None), "FOR_TASK": ("Entity", "Concept", "Task")}
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
    "CREATE CONSTRAINT result_row_key IF NOT EXISTS FOR (r:ResultUnit) REQUIRE r.row_key IS UNIQUE",
    "CREATE CONSTRAINT material_hash IF NOT EXISTS FOR (m:Material) REQUIRE m.content_hash IS UNIQUE",
    "CREATE CONSTRAINT batch_id IF NOT EXISTS FOR (b:IngestBatch) REQUIRE b.id IS UNIQUE",
]

# 全文索引：名称 -> (Label, 字段, 分词方式)。检索字段按类别声明（intents_decompose.md §6.2）
# - namekey_raw：名称词面通道。名称与 alias 都在 NameKey 上，对象上没有 aliases 列表；默认分词，不做词形还原
# - entity_texts / concept_texts：Entity 的 description、Concept 的 definition 与 scope_note；english 分词
FULLTEXT = {
    "namekey_raw": ("NameKey", ["raw"], "standard-no-stop-words"),
    "entity_texts": ("Entity", ["description"], "english"),
    "concept_texts": ("Concept", ["definition", "scope_note"], "english"),
}
TEXT_FIELDS = {"Entity": ["description"], "Concept": ["definition", "scope_note"]}   # 文本通道与向量共用的字段
