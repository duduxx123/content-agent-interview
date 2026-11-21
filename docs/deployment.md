# 部署说明

本文档说明如何在单机环境运行 ContentAgent。当前版本是面试演示用的单实例应用：`LiveSession` 保存在进程内存中，不支持多 worker 或多实例共享同一个监听会话。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Windows、Linux 或 macOS 均可
- 实时监听 B 站时需要可访问 B 站网页端接口和 WebSocket 的网络环境
- 可选：DeepSeek API Key（不配置时使用规则版）

## 依赖清单

运行时依赖由 `pyproject.toml` 声明、`uv.lock` 锁定；执行 `uv sync` 即可安装，不需要手工维护版本。

| 依赖 | 用途 |
|---|---|
| `fastapi` | HTTP API、请求校验和 OpenAPI 文档 |
| `uvicorn[standard]` | ASGI 服务进程 |
| `aiohttp` | B 站 HTTP 请求与 WebSocket 连接 |
| `Brotli` | B 站 WebSocket 消息解压 |
| `pure-protobuf` | 解析新版 `SEND_GIFT_V2` 等 protobuf 消息 |
| `yarl` | B 站请求 URL 拼接 |
| `pydantic` | 输入输出模型和数据校验（随 FastAPI 安装） |

`src/blivedm/` 是随仓库提供的 B 站直播客户端源码，不通过包管理器安装，许可证见 `THIRD_PARTY_LICENSES/`。Python 3.12+ 与 uv 是运行前提，不含在上表内。

## 安装

```powershell
cd D:\content-agent-interview
uv sync
```

`uv sync` 会根据 `pyproject.toml` 和 `uv.lock` 创建 `.venv` 并安装依赖。

## 配置

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

填写 `.env`：

```dotenv
BILIBILI_ROOM_ID=你的直播间号
BILIBILI_COOKIE="从浏览器复制的完整Cookie字符串"
DEEPSEEK_API_KEY=你的DeepSeek_API_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_TIMEOUT_SECONDS=20
```

说明：

- `BILIBILI_COOKIE` 是网页端 Cookie，不是开放平台 `access_key`。整串用双引号包起来，分号之间不要换行。
- Cookie 只从进程环境变量读取，不写入日志、不返回给页面，也不进入模型请求。
- 不需要实时监听时，可以只启动 Web 演示和 `POST /analyze`，不必配置 B 站变量。
- 不需要模型润色时，把 `config/agent.json` 的 `deepseek_enabled` 保持为 `false`，或删除 `DEEPSEEK_API_KEY`。

配置文件位置：

| 文件 | 用途 |
|---|---|
| `config/agent.json` | 是否启用 DeepSeek 润色 |
| `config/products.json` | SKU 商品事实和卖点关键词 |
| `config/compliance_rules.json` | 合规风险词、类别和替代方向 |
| `config/decision_rules.json` | 阶段边界、评分权重、阈值和冲突策略 |

修改配置后重启进程即可生效；实时监听期间不要使用热重载。

## 启动

开发/演示：

```powershell
uv run --env-file .env uvicorn content_agent.main:app --host 127.0.0.1 --port 8080
```

对外提供服务：

```powershell
uv run --env-file .env uvicorn content_agent.main:app --host 0.0.0.0 --port 8080 --workers 1
```

- 不要加 `--reload`：热重载会重建进程，B 站 WebSocket 和实时会话会断开。
- 只使用一个 worker。每个 worker 都有独立的 `live_session`；多 worker 会让 SSE 订阅和分析窗口分散到不同进程。
- 当前版本不支持在同一个进程内同时监听多个直播间。

启动后检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

预期返回：

```json
{"status": "ok"}
```

页面入口：

- `http://127.0.0.1:8080/`：演示页面
- `http://127.0.0.1:8080/docs`：交互式 API 文档
- `http://127.0.0.1:8080/openapi.json`：OpenAPI 定义

## 反向代理与 SSE

如果通过 Nginx、Caddy 等反向代理暴露服务，必须关闭对 SSE 的缓冲，否则页面会批量延迟收到事件。

Nginx 示例：

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_buffering off;
    proxy_cache off;
    gzip off;
    proxy_read_timeout 3600s;
}
```

应用已经在 `/live/events` 响应中设置：

- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `X-Accel-Buffering: no`

前端使用浏览器原生 `EventSource`，断线后会自动重连并重新收到 `snapshot`。

## 进程管理

### Linux systemd

```ini
[Unit]
Description=ContentAgent live assistant
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/content-agent-interview
EnvironmentFile=/opt/content-agent-interview/.env
ExecStart=/opt/content-agent-interview/.venv/bin/uvicorn content_agent.main:app --host 127.0.0.1 --port 8080 --workers 1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now contentagent
sudo systemctl status contentagent
```

### Windows

演示环境可直接在 PowerShell 前台运行。需要长期运行时，建议使用任务计划程序或 NSSM 托管上述 `uvicorn` 命令，并确保工作目录是项目根目录、`.env` 通过 `--env-file` 或进程环境注入。

## 运行期检查

```powershell
# 健康检查
Invoke-RestMethod http://127.0.0.1:8080/health

# 实时状态
Invoke-RestMethod http://127.0.0.1:8080/live/status

# 启动离线模拟源
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/live/start `
  -ContentType "application/json" `
  -Body '{"source":"simulated","window_seconds":10}'

# 停止
Invoke-RestMethod -Method Post http://127.0.0.1:8080/live/stop
```

B 站监听启动失败时，`/live/start` 返回 503，`/live/status.error` 会说明缺少房间号、Cookie 或连接失败类型。日志不包含 Cookie、请求头或模型 API Key。

## Cookie 失效与重启

B 站 Cookie 过期后，实时事件会中断，状态变为 `error`。处理步骤：

1. 在浏览器重新登录 B 站，复制新的完整 Cookie。
2. 更新 `.env` 的 `BILIBILI_COOKIE`。
3. 重启进程，重新调用 `POST /live/start`。

不要把 Cookie 写入代码、提交到仓库或贴到聊天记录中。`.env` 已在 `.gitignore` 中忽略。

## 数据与隐私

- 不持久化弹幕、昵称、礼物或会话数据；事件只保存在进程内存的有界缓冲区中。
- 昵称只用于页面事件流展示，不写入互动分析文本，也不进入模型输入。
- 模型请求只包含商品事实、主题计数和候选草稿。
- 如果接入外部业务指标，请通过 `POST /live/metrics` 推送，并在自己的网关层完成鉴权和访问控制。当前演示版本没有用户系统。

## 资源与限制

- 实时事件缓冲区最多保留 300 条；SSE 订阅队列满时会丢弃旧消息。
- 默认每 10 秒分析一个窗口，窗口可在 3–120 秒之间配置。
- 在线人数每 20 秒从 B 站房间信息接口刷新一次；购物车点击率和转化率没有公开数据源，保持 `unavailable`，页面不展示。
- 最后一个 SSE 订阅者断开 60 秒后，实时会话会自动停止，释放 B 站连接。
- 当前没有数据库、任务队列和鉴权，适合单机演示；生产化需要补充持久化、权限、限流和多房间调度。

## 故障排查

| 现象 | 排查 |
|---|---|
| 页面空白 | 确认进程已启动，访问 `/health`；确认 `uvicorn` 工作目录是项目根目录 |
| `/live/start` 返回 503 | 检查 `.env` 是否通过 `--env-file` 传入，房间号是否为数字，Cookie 是否完整 |
| 页面收不到实时事件 | 检查反向代理是否关闭缓冲；直接访问 `/live/events` 观察 SSE |
| 长时间没有弹幕 | 直播间可能暂时无人发言；可切换到“离线模拟源”验证页面 |
| DeepSeek 超时 | 不影响规则版结果；检查 Key、网络和 `DEEPSEEK_TIMEOUT_SECONDS`，或关闭 `deepseek_enabled` |
| 重启后统计归零 | 当前会话统计只保存在内存，重启即清空，属于预期行为 |
