# jobagent

把原始招聘 JD 变成结构化数据，再聚合成"市场到底在要什么技术"的技能情报。

已提供 **JD 数据管道、PDF 简历解析、岗位采集与匹配报告、人工标注与评估页面**。
智联公开岗位采集已实测；BOSS 当前触发安全验证，页面会显示阻断原因。
完整路线图见 `docs/roadmap.md`。

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

## PDF 简历解析（Windows / Conda）

```powershell
conda activate jobagent
python -m pip install -e ".[dev]"
```

在项目根目录的 `.env` 中填写模型配置（尚未创建时可以复制 `.env.example`）：

```dotenv
JOBAGENT_LLM_BASE_URL=https://ai.gitee.com/v1
JOBAGENT_LLM_API_KEY=你的密钥
JOBAGENT_LLM_MODEL=DeepSeek-V4-Pro-0813
```

这里使用 Gitee AI 的 `/v1/chat/completions` 接口，API key 由 SDK 放入
`Authorization: Bearer ...` 请求头。简历解析一次返回完整 JSON，不开启流式输出。

启动接口：

```powershell
python -m uvicorn jobagent.api:app --reload
```

浏览器打开 <http://127.0.0.1:8000/>，选择 PDF 简历，点击 **开始解析**。
教育、工作、项目和技能以卡片显示；失败时页面显示对应原因。
简历解析会在每次请求时读取项目根目录的最新 `.env` 配置，填写密钥后可直接重新解析。
也可以在终端上传：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/resumes/parse" -F "file=@C:/Users/xuwei/Documents/resume.pdf"
```

返回 `ResumeExtraction` JSON：

| 字段 | 内容 |
|---|---|
| `name` | 姓名 |
| `target_role` | 简历明确写出的求职意向 |
| `education` | 学校、专业、学历、起止时间 |
| `work_experience` | 公司、职位、起止时间、工作内容 |
| `projects` | 项目名称、个人角色、技术、职责、成果 |
| `skills` | 技能名称 `name` 和支持它的原文片段 `evidence` |

没有提供的标量信息返回 `null`，列表返回 `[]`。简历接口直接调用真实模型，
不受 JD 导入的 `JOBAGENT_PROVIDER=mock` 设置影响。
当前支持可提取文字的 PDF；扫描图片 PDF 不执行 OCR。
本接口解析后直接返回结果，尚不保存简历或提供匹配评分。

阅读顺序：`schemas.py` 中的 `ResumeExtraction` → `resume.py` 中的
`extract_pdf_text` 和 `OpenAIResumeProvider.extract` → `api.py` 中的 `parse_resume`。
模型只接收简历文本，没有浏览器、文件系统或其他工具权限。
离线测试使用固定模型响应验证链路，不代表真实模型的抗提示注入效果已通过评估。

## 岗位采集、匹配报告与评估

启动同一个后端后，在首页下方用下拉菜单选择职位、城市和招聘平台。获取岗位后，
点击“生成匹配报告”，查看固定 rubric 分数、逐项证据、技能差距与补足建议。
匹配记录会保存到本地数据库，用于人工评估。

也可以在“获取或上传招聘信息”中选择“自行提供”，上传文字版 PDF、UTF-8 TXT，
或直接粘贴 JD。添加后点击该岗位的“生成匹配报告”，使用同一份已解析简历进行分析。
职位名称可选；未提供的公司、城市和薪资不会编造。

进入 <http://127.0.0.1:8000/evaluation>，独立填写人工技能 gap 和维度评分。
页面统计实际标注进度；只对已标注配对计算 Precision、Recall、F1 与 Spearman，
不足 50 组时标为试算。当前未预置人工标签。

完整评分公式、采集验证状态和标注步骤见 [docs/matching.md](docs/matching.md)。

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

## 会追问的模拟面试

简历解析完成后，可点击结果区的「编辑 / 补充」，修改基本信息，并添加、删除或编辑教育、
工作、项目和技能条目。点击「保存简历修改」后，新匹配报告和新面试使用修改后的内容。
编辑过程中可取消；修改在当前页面保留，刷新后需要重新解析简历。

完成简历解析后，在岗位卡片点击「开始模拟面试」。系统根据简历与 JD 生成三个主题，
根据回答追问、切换难度；每个主题最多追问一次。结束后展示四个维度的评分、回答依据、
改进建议与考察要点。会话自动保存，刷新可继续，也可以提前结束并查看已提交内容的评分。

当前采用手写 Agent loop，模型评估回答，Python 控制路由、追问次数与评分汇总。
支持「语音作答（推荐）」与「手写输入」自由选择。录音停止后可以试听再提交，
语音直接发给 Gitee `Qwen3.8-Omni-Flash` 理解并评分，复用当前模型密钥；
用 `JOBAGENT_AUDIO_MODEL` 配置语音模型。使用麦克风时通过 HTTPS 或 localhost 打开页面。
实现与接口说明见 [docs/interview.md](docs/interview.md)。

## 合规说明

采集模块只读取公开搜索页和职位描述，不执行登录、验证码处理或自动投递。
使用前确认相应平台的访问与使用条件；被平台阻断时页面显示真实状态。
