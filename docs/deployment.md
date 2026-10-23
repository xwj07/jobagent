# Windows 电脑后端 + Cloudflare Pages 网页

网页由 Cloudflare Pages 提供，Pages 的服务端代理把接口请求转给 Cloudflare Tunnel，再由 Tunnel 转到 Windows 服务器上的 FastAPI。浏览器只访问 Pages 同一个域名，无需修改前端 API 地址或添加跨域配置。

## 1. Windows 服务器

安装 Git、Miniconda 和官方 cloudflared。在服务器终端执行：

```powershell
git clone https://github.com/xuwei/jobagent.git
cd jobagent
conda create -n jobagent python=3.11 -y
conda activate jobagent
python -m pip install -e .
Copy-Item .env.example .env
notepad .env
```

在 `.env` 中填写 Gitee API key 和实际可用的模型名称。不要上传 `.env`、数据库或真实简历。新电脑使用自己的数据库，不需要复制开发期间的简历记录。

启动后端，并保持终端运行：

```powershell
powershell -ExecutionPolicy Bypass -File deploy/start-backend.ps1
```

在该电脑访问 `http://127.0.0.1:8000/`，先测试 PDF 解析、岗位匹配和面试。

## 2. Tunnel

在 Cloudflare 控制台创建命名 Tunnel，选择 Windows，按控制台生成的命令在服务器安装连接器服务。Tunnel 的凭证只放在服务器，不提交 GitHub。

添加一个 Published application，域名使用 `api.weijianxu.indevs.in`，服务为 `http://127.0.0.1:8000`。确认 Tunnel 显示 Healthy，并通过该 HTTPS 地址测试后端。

此步骤要求该域名的 DNS 可以在 Cloudflare 中配置。仅拥有一个子域名字符串并不等于已获得相应 DNS 管理权。以 Cloudflare 域名状态和实际解析结果为准。

## 3. Pages

Cloudflare Workers & Pages → 创建 Pages 项目 → 连接 GitHub 仓库。设置：

| 配置 | 值 |
| --- | --- |
| 生产分支 | `main` |
| 框架 | None |
| 构建命令 | `python scripts/build_cloudflare.py` |
| 输出目录 | `dist/cloudflare` |
| 环境变量 `BACKEND_URL` | `https://api.weijianxu.indevs.in` |

生产和预览环境分别配置变量。构建目录只包含网页资源和 Pages 服务端代理，Gitee key 留在 Windows 后端的 `.env` 中。配置变更后重新部署。

## 4. 演示前验收

- 用另一台设备打开 Pages HTTPS 地址。
- 上传虚构简历，编辑字段；上传岗位，生成匹配报告。
- 启动面试，提交文字回答和语音回答，检查追问与最终反馈。
- 检查岗位采集的真实来源状态；平台可能限制公开访问，不能保证数量。
- Windows 禁止自动睡眠，确保后端进程和 Tunnel 均在线。

当前版本尚未实现用户隔离，人工评估接口能读取保存的案例与简历，不能直接作为面向陌生用户的公共服务。当前部署文件也尚未配置访问控制。演示请使用虚构数据；开放真实简历使用之前，需要完成访问权限配置。如果通过 Cloudflare Access 保护 Tunnel，Pages 的代理还需要配置服务身份，不能只给 Tunnel 加登录页，否则接口会收到登录页而不是业务结果。

当前请求会同步等待 LLM；部署后须实测匹配和音频处理时长。Cloudflare 代理有请求超时限制，不能仅以本地请求成功判断线上验收通过。

参考：[Tunnel 设置](https://developers.cloudflare.com/tunnel/get-started/)、[Pages 高级模式](https://developers.cloudflare.com/pages/functions/advanced-mode/)。
