# E09 入口。
#
#   make setup       委派给仓库根：建共享 .venv 并装 git 过滤器
#   make neo4j-up    启动 infra/neo4j-e09（bolt 7687，浏览器 7474；先停 neo4j-e08）
#   make neo4j-down  停止 neo4j-e09（数据保留在 infra/neo4j-e09/data/）
#   make check       环境自检：材料与种子目录、连库、版本与 edition、确认不是 v1 库
#   make seed        种子入库（e09.seed）：重跑无副作用；有冲突或写后复核失败时返回非零
#   make embed       建向量索引并补算向量（Resolve 的语义阶段用）；需要 embedding 服务，只补算文本变过的对象
#   make compile     编译论文表单（不连库）：默认编译 fixtures/forms/ 下的夹具，FORMS=... 指定；有错误时返回非零
#   make ingest      论文入库（e09.ingest）：按顺序编译、dry_run、apply 正式表单；已入库的判为不变；有阻塞项时返回非零
#   make lab         在本目录启动 JupyterLab
#
# 当前用户若不在 docker 组：make neo4j-up DOCKER="sudo docker"

UV ?= uv
DOCKER ?= docker
RUN = $(UV) run
COMPOSE = $(DOCKER) compose -f ../../infra/neo4j-e09/docker-compose.yml

.PHONY: setup neo4j-up neo4j-down check seed embed compile ingest lab clean

setup:
	$(MAKE) -C ../.. setup

neo4j-up:
	$(COMPOSE) up -d

neo4j-down:
	$(COMPOSE) down

check:
	$(RUN) python -m e09.env_check

seed:
	$(RUN) python -m e09.seed

embed:
	$(RUN) python -m e09.utils.embedding

FORMS ?= $(wildcard fixtures/forms/*.yml)
compile:
	$(RUN) python -m e09.form $(FORMS)

ingest:
	$(RUN) python -m e09.ingest

lab:
	mkdir -p notebooks && $(RUN) jupyter lab --notebook-dir=notebooks

clean:
	rm -rf notebooks/_scratch
