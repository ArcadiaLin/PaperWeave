# E09 入口。
#
#   make setup       委派给仓库根：建共享 .venv 并装 git 过滤器
#   make neo4j-up    启动 infra/neo4j-e09（bolt 7687，浏览器 7474；先停 neo4j-e08）
#   make neo4j-down  停止 neo4j-e09（数据保留在 infra/neo4j-e09/data/）
#   make check       环境自检：材料与种子目录、连库、版本与 edition、确认不是 v1 库
#   make embed       建向量索引并补算向量（Resolve 的语义阶段用）；需要 embedding 服务，只补算文本变过的对象
#   make test        读取算子在现有库上的检验（tests/；库没起时跳过）
#   make lab         在本目录启动 JupyterLab
#
# 写入路径正在改用 packages/graph-vc 与 packages/graph-doc 重写，入库目标（seed / ingest）随新路径恢复。
# 旧写入路径（表单编译与 Commit）见 tag e09-legacy-write：现有 neo4j-e09 库与 I3 实验由它建出。
#
# 当前用户若不在 docker 组：make neo4j-up DOCKER="sudo docker"

UV ?= uv
DOCKER ?= docker
RUN = $(UV) run
COMPOSE = $(DOCKER) compose -f ../../infra/neo4j-e09/docker-compose.yml

.PHONY: setup neo4j-up neo4j-down check embed test lab clean

setup:
	$(MAKE) -C ../.. setup

neo4j-up:
	$(COMPOSE) up -d

neo4j-down:
	$(COMPOSE) down

check:
	$(RUN) python -m e09.env_check

embed:
	$(RUN) python -m e09.utils.embedding

test:
	$(RUN) pytest tests -q

lab:
	mkdir -p notebooks && $(RUN) jupyter lab --notebook-dir=notebooks

clean:
	rm -rf notebooks/_scratch
