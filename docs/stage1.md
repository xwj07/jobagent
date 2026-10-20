# 阶段一：JD 数据管道 — 设计说明与作业

这一阶段的代码量不大，但把后面所有模块都会复用的三个模式立起来了：**结构化输出、幂等、按条隔离失败**。读代码时请按下面这个顺序走。

## 数据流

```
JSONL 输入
  └─ RawPosting（schemas.py，输入校验）
       └─ extract.ingest_one（每条一个事务）
            ├─ content_hash 去重（extract.py）
            ├─ Provider.extract → JobExtraction（llm.py + schemas.py，输出校验）
            ├─ canonical() 技能名归并（normalize.py）
            └─ 写入 job_postings / skills / job_skills（models.py）
  └─ stats.py 聚合
       └─ CLI 表格 / JSON 输出（cli.py）
```

## 五个关键决策

**1. 为什么 provider 是 Protocol，而不是直接调 SDK？**
因为测试和 CI 不应该依赖网络和密钥。`MockProvider` 用确定性规则实现同一个接口，所有上层代码对"真模型还是假模型"无感知。你以后加 rerank、模拟面试时，同一套写法会反复出现：**接口在核心，实现在边缘**。

**2. 为什么抽取结果必须先过 Pydantic？**
LLM 的输出是字符串，不是数据。`JobExtraction.model_validate_json` 是你和模型之间的防火墙：类型错、越界（比如月薪 5000K）、字段缺失都在这里被拦下。注意 schema 的两个细节——`salary_min_k/max_k` 做了 0~1000 的边界，`model_validator` 静默交换颠倒的 min/max，而不是让整条记录失败。

**3. 为什么校验失败要"带着错误重试"？**
看 `OpenAIChatProvider.extract` 里的 `feedback` 逻辑：第二次请求会把 Pydantic 的具体报错拼进 system prompt。这让模型知道错在哪，比盲目重试成功率高得多。这是最便宜的一次可靠性投资。

**4. 为什么幂等键是 sha256(company|title|归一化文本)？**
采集端不可避免会重复导入（同一职位重新发布、导出两次）。哈希前先 `re.sub(r"\s+", " ", ...)` 归一化空白，避免格式噪声造成假重复。唯一约束在数据库层，并发导入也不会产生重复行。

**5. 为什么每条 JD 独立事务？**
`ingest_many` 对每条规定自、提交、关闭。一条坏数据只进入 `failed` 列表，不回滚整批。这是"导入 80 条 JD"这种真实场景的基本要求，也是面试里常被追问的批处理设计点。

## 你怎么看代码

建议顺序：

1. `schemas.py`（10 分钟）——先看契约，再看实现。
2. `extract.py` 的 `ingest_one`（15 分钟）——数据从文本变成三张表的过程。
3. `llm.py` 的 `OpenAIChatProvider.extract`（15 分钟）——重试与反馈。
4. `tests/test_ingest.py`（15 分钟）——测试就是可执行的规格说明。
5. `stats.py` + `cli.py`（10 分钟）——聚合和展示。

每读完一个文件，试着用自己的话回答文档里的"五个关键决策"。

## 作业（关掉我的实现，自己写）

目标：证明你理解了抽取层，而不是记住了代码。

**作业 A：重写一个精简抽取器**

在 `src/jobagent/llm.py` 之外新建 `src/jobagent/my_extract.py`，实现：

- `extract_years(text) -> int | None`：支持"3-5年"、"3年以上"、"经验不限"；  
  注意"3年以上"应返回 3，"经验不限"返回 0。
- `extract_salary(text) -> tuple[int | None, int | None]`：支持 `"25-40K·14薪"`、  
  `"30-50万/年"`（换算成月薪 K）、`"面议"`（返回 `None, None`）。
- `extract_skills(text) -> list[SkillMention]`：至少覆盖 10 个技能词；  
  同一技能大小写/别名只出现一次；"优先/加分项"所在的**同一个分句**里出现的技能标 `required=False`。

然后用测试卡关：新建 `tests/test_my_extract.py`，至少写 12 个用例，包括边界情况（"15K以上"、"10年以上"、一句话里同时出现必需和加分技能）。卡关标准：

```bash
pytest tests/test_my_extract.py -q     # 全绿
ruff check src/jobagent/my_extract.py  # 干净
```

**作业 B：把聚合并发化（进阶）**

`stats.skill_frequency` 现在是全量加载到内存再计数。把计数改成 SQL 聚合（`select(Skill.name, func.count(...)).join(JobSkill)...group_by(...)`），并写一个测试证明两种实现结果一致。这题就是以后"生产环境里 N+1 查询"问题的预演。

**作业 C：写一个 JD 采集器的边界说明（不写代码）**

用 200 字说明：为什么本项目不做自动爬取和自动投递，以及如果你要做一个"用户手动触发、低频、只读"的浏览器插件，哪些数据可以落、哪些不可以。**面试时这道题比代码题更能体现工程判断力。**

交作业时把你写的代码贴回来，我按 code review 的方式给你逐条批注。

## 阶段一验收标准

- `pytest` 全绿、`ruff check .` 干净；
- 用 mock provider 导入样例数据，`stats` 输出合理；
- 重复导入 `inserted=0`；
- 能脱稿讲清楚上面五个决策。
