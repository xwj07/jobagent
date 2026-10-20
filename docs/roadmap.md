# 路线图

按"每阶段都可独立演示"的原则拆分。阶段一是已交付的基线，之后每个阶段都复用它的数据层和 provider 模式。

## 阶段一：JD 数据管道（已交付）

采集 JSONL → 结构化抽取 → 幂等入库 → 技能词频/薪资统计。技术点：Pydantic 结构化输出、失败反馈重试、单条事务隔离、别名归一化、mock provider 离线测试。

## 阶段二：简历解析与匹配（预计 2 周）

- 简历 PDF 解析，切成"项目/技能/经历"结构化块（PDF 解析复用 `pdf` 技能里的工具链）。
- JD 与简历的混合检索：BM25（Postgres 全文或 rank_bm25）+ 向量召回（pgvector + Embedding），RRF 融合，cross-encoder rerank。
- 输出带 rubric 的匹配报告：命中项、缺失项、弥补建议。
- **评估集**：50 组人工标注的简历-岗位配对，统计 gap 识别的 precision/recall、模型打分与人工打分的 Spearman 相关性。

## 阶段三：手写 agent loop + 模拟面试（预计 2 周）

- 先不用框架，手写 `plan → tool call → observe → reflect` 循环，工具包括：查 JD、查简历、检索面经知识库。
- 面试策略：根据 JD+简历生成问题计划，按回答追问、切换难度，最后按维度打分反馈。
- 再把循环迁移到 LangGraph，对比两种实现的可恢复性、可观测性和代码量，写成文档——这是面试里最好的架构叙事。
- 安全：JD/简历视为不可信输入，做指令隔离，防提示注入。

## 阶段四：评估与可观测性（持续）

- 黄金测试集 + LLM-as-judge，每次 prompt/模型改动跑回归。
- Langfuse 追踪每次抽取与匹配的耗时、token 成本、失败率。
- GitHub Actions：`pytest + ruff + 评估回归`，分数下降阻止合并。

## 阶段五：服务化与前端（预计 1 周）

- FastAPI 暴露 `POST /postings`、`POST /match`、`GET /stats`、`WS /interview`。
- Next.js 看板：技能词频图、匹配报告、流式面试对话。
- Docker Compose 一键起，写部署文档和演示 GIF。

## 贯穿始终

- 每个阶段结束写一节设计文档（为什么这样做、放弃了什么），直接作为简历项目的技术文档。
- 评估数据、失败案例、成本数字，都是面试里可量化的谈资。
