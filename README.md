# jobagent

把原始招聘 JD 变成结构化数据，再聚合成"市场到底在要什么技术"的技能情报。

当前是**阶段一：JD 数据管道**。完整路线图（简历匹配 → RAG 面试教练 → 评估体系 → 部署）见 `docs/roadmap.md`。

## 为什么做这个项目

选技术栈不靠感觉，靠数据：先抽 50~100 条目标岗位 JD，统计技能词频，再按市场要求设计后续模块。项目本身就是选型的证据。

## 快速开始

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# 不需要 API key，用确定性 mock 抽取器跑通全流程
jobagent init-db
jobagent ingest data/samples/jds.jsonl --provider mock
jobagent stats --top 15
```

## 接入真实模型

任何 OpenAI 兼容接口都行（DeepSeek / 通义 / Kimi / OpenAI）：

```bash
cp .env.example .env
# 编辑 .env：JOBAGENT_PROVIDER=openai，填 JOBAGENT_LLM_BASE_URL / API_KEY / MODEL
jobagent ingest data/samples/jds.jsonl
```

## 切换到 Postgres

```bash
docker compose up -d db
export JOBAGENT_DATABASE_URL=postgresql+psycopg://jobagent:jobagent@localhost:5432/jobagent
pip install "psycopg[binary]"   # 驱动单独装，保持默认依赖轻量
jobagent init-db
```

## 输入格式

每行一个 JSON 对象（JSONL）：

```json
{"raw_text": "【岗位名】\n城市 · 年限 · 学历\n薪资\n岗位职责...", "company": "可选", "title": "可选", "source": "manual", "url": "可选"}
```

采集端（浏览器插件或手动复制）只负责把页面文本落到 JSONL；抽取、去重、规范化都由本工具完成。

## 设计要点

- **幂等写入**：`content_hash = sha256(company|title|归一化文本)`，重复导入自动跳过。
- **结构化输出强约束**：抽取结果必须通过 Pydantic 校验；校验失败会把错误信息回喂给模型重试。
- **单条事务边界**：一条 JD 抽取失败不会回滚整批导入，失败项单独报告。
- **技能规范化**：别名表把 `K8s`/`Kubernetes`、`大模型`/`LLM` 合并为同一技能。
- **mock provider 不是玩具**：测试和 CI 完全离线，不需要任何密钥。

## 开发

```bash
pytest          # 单元测试 + 端到端导入测试
ruff check .    # lint
jobagent stats --json   # 机器可读输出，便于后续做看板
```

## 合规说明

本工具只处理你**手动获取或经授权**的文本。批量抓取、自动投递请联系平台规则；仓库不包含任何针对招聘平台的爬虫或自动申请代码。
