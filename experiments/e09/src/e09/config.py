"""E09 的共同配置：仓库路径与 neo4j-e09 连接参数。脚本与 notebook 都从这里取，避免各写一份。"""

import os
from pathlib import Path

REPO = next(p for p in [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents] if (p / "AGENTS.md").is_file())
DATA = REPO / "data/raw/e09-paper-knowledge"   # 论文材料（复制自 e08，只读）与 v2 种子
SEEDS = DATA / "seeds"
FORMS = DATA / "forms"     # 论文入库表单（paper-form-v4），版本管理
PAPERS = DATA / "papers"

# 默认值对应 infra/neo4j-e09/docker-compose.yml；与 neo4j-e08 端口相同，同一时间只起一个
NEO4J_URI = os.environ.get("E09_NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (os.environ.get("E09_NEO4J_USER", "neo4j"), os.environ.get("E09_NEO4J_PASSWORD", "password"))
NEO4J_DB = os.environ.get("E09_NEO4J_DATABASE", "neo4j")
