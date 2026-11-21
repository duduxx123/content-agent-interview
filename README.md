# ContentAgent 直播辅助 Agent

## 环境

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

```powershell
cd D:\content-agent-interview
uv sync
uv run --env-file .env uvicorn content_agent.main:app --host 127.0.0.1 --port 8080
```

开发时可在命令后加 `--reload`；实时监听期间不要使用，热重载会断开 B 站连接。

服务启动后访问 `http://127.0.0.1:8080/` 打开 Web 演示页面，访问 `http://127.0.0.1:8080/docs` 查看交互式 API 文档。接口字段、SSE 事件和错误码见 `docs/api.md`，生产启动、反向代理和 Cookie 失效处理见 `docs/deployment.md`。题目样例位于 `examples/scene.json`。

## Web 演示页面

页面有两个数据源：

- **场景回放**：载入预置场景，手动调整直播进度、弹幕、互动事件和商品信息。
- **实时监听**：通过 B 站 WebSocket 接收弹幕、礼物、醒目留言和上舰事件，左侧事件流实时滚动；默认手动分析，勾选“自动刷新提词队列”后每 10 秒把本窗口弹幕送入 Agent，自动刷新阶段、调度说明和提词队列。未配置 `.env` 时可选择“离线模拟源”做本地演示，页面会明确标注。

回放模式下展开“当前商品”，可以从商品目录的 5 个 SKU 中切换；选中后会带出规格、价格、成分和特点，Agent 再按 `sku_id` 补全缺失的卖点、用法和注意事项。

实时监听的数据来源：

- 在线人数每 20 秒从 B 站房间信息接口刷新，显示在实时面板的“在线”计数里。
- 购物车点击率、成交转化率不是 B 站公开接口能提供的数据。实时页面不展示、不发送这两项，也不使用示例值；决策融合中对应的信号保持关闭。
- 实时事件流走 `GET /live/events`（SSE），启动/停止分别使用 `POST /live/start`、`POST /live/stop`，`POST /live/analyze` 可立即分析当前窗口。
- `POST /live/metrics` 保留为未来业务数据接入点，但当前页面没有入口，也不会用默认值补位。
- 礼物按金瓜子面值折算：1000 金瓜子 = 1 元，银瓜子礼物计 0 元；舰长、提督、总督分别统计件数和价值；醒目留言按面额单列。页面同时展示礼物件数和礼物价值，价值是面值，不是平台结算金额。
- 实时模式下可以在左侧“阶段控制”手动指定阶段，或在“当前商品”切换 SKU；运行中修改会通过 `POST /live/config` 应用到当前会话。切换阶段后右侧阶段卡立即更新，提词队列是否刷新仍由“自动刷新提词队列”开关决定。
- 实时面板的“自动刷新提词队列”默认关闭。关闭时窗口定时分析暂停，队列保持不动，弹幕仍会累积；点“立即分析本窗口”才更新。勾选后恢复每 10 秒自动刷新。
- 配置 DeepSeek 后，每个实时窗口先做 AI 语义互动分析（主题、相似问题、刷屏、负面反馈、购买意向），再生成提词；模型会收到当前阶段、阶段目标、下一阶段准备和候选草稿，话术按阶段调整。未配置 Key 或调用失败时回退关键词规则和通用规则话术。提词队列上方会标注“AI 语义 / 关键词”和“AI 生成 / 规则版”；AI 生成的话术卡片也会带“AI 生成”标签。
- “AI 决策摘要”是模型单独生成的一段排序解释，和规则引擎生成的“调度说明”分开展示；规则版不会生成 AI 摘要。
- 页面顶部“合规词库”进入只读子页面，支持按风险等级、类别和关键词浏览风险词条与替代方向。
- “调度说明”不是操作日志，而是解释本轮提词为什么这样排序：阶段冲突、同问/刷屏加权、合规降级、手动阶段指令等。没有触发时会显示空状态。

建议的 2 分钟演示顺序：

1. 场景回放：展示阶段时间轴和三档提词，拖动进度越过 70% 查看阶段切换。
2. 切到“促单冲突场景”：同问和负面反馈触发答疑插播。
3. 切到“实时监听”：开始 B 站监听，展示实时弹幕、礼物、进房昵称和在线人数；10 秒窗口自动生成提词。点击和转化率没有公开数据源，页面不展示。
4. 展开“分析明细”，查看同问、刷屏和事件。

录制 2 分钟视频的完整口播顺序和故障回退见 `docs/demo.md`。

实时事件视图会显示发送者昵称、弹幕/礼物内容和进房/关注等动作。昵称只用于页面展示，不会进入模型；模型收到的仍然只是弹幕文本、商品事实和候选草稿。实时模式只展示能获取到的在线人数，不展示购物车点击率和转化率。

## 连接 B 站直播弹幕（网页端）

项目直接包含 `src/blivedm` 中的 `blivedm` 源码，使用网页端 `BLiveClient`，通过房间号和浏览器 Cookie 建立连接，不需要 B 站开放平台 `access_key`。Cookie 只从进程环境变量读取，不要提交或分享 Cookie。

先复制 `.env.example` 为 `.env`，填写房间号、完整 Cookie（整串用双引号包起来，分号之间不要换行）和 DeepSeek API Key：

```dotenv
BILIBILI_ROOM_ID=你的直播间号
BILIBILI_COOKIE="从浏览器复制的完整Cookie字符串"
DEEPSEEK_API_KEY=你的DeepSeek_API_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_TIMEOUT_SECONDS=20
```

将 `config/agent.json` 的 `deepseek_enabled` 设为 `true` 后，Agent 会先用 DeepSeek 对实时窗口做语义互动分析，再润色规则模块生成的候选话术；仓库初始值为 `false`，当前工作区是否开启以 `config/agent.json` 为准。API Key 未配置或调用失败时会自动回退。模型只收到弹幕文本、商品事实、主题计数和候选草稿，不会收到 Cookie 或用户昵称。

商品目录和卖点关键词维护在 `config/products.json`，当前包含 5 个演示 SKU（`12345`、`20001`、`20002`、`20003`、`20004`）。请求里的 `product.sku_id` 命中目录时，缺失的卖点、用法、适用人群和注意事项会自动补全。广告风险词库在 `config/compliance_rules.json`，按绝对化、效果保证、医疗化宣称、资质评价和价格促销五类维护 150+ 条词条，命中后会暂缓原话术并给出修改方向。合规模块会先做全半角、空格和分隔符归一化，再匹配等价表达，并用否定/免责、转述/询问语境和固定搭配例外减少误报；这仍是规则化语义预筛，是否违规需要结合商品类别、依据和广告语境人工复核。

直播阶段边界、评分权重、优先级阈值和冲突策略维护在 `config/decision_rules.json`。阶段引擎按 `elapsed_seconds / planned_seconds` 推算当前阶段并给出下一阶段准备项；输入中的 `directive` 可以下发结构化指令（例如提前进入促单期），决策融合会在促单期遇到同问或负面反馈时保留答疑插播。

启动直播监听：

```powershell
uv run --env-file .env python -m content_agent.live_cli
```

启动 HTTP API：

```powershell
uv run --env-file .env uvicorn content_agent.main:app --host 127.0.0.1 --port 8080
```

监听器每 30 秒汇总一次弹幕、醒目留言和互动事件，输出当前阶段、下一阶段准备项、互动摘要及排序后的提词建议。商品资料以 `examples/scene.json` 为模板，直播阶段按时间推算；购物车点击率和成交转化率没有公开数据源，不参与实时分析，Web 实时页面只展示 B 站在线人数。停止时按 `Ctrl+C`。

本地 CLI 和 Web 演示默认使用 `examples/` 下的预置场景，无需连接直播间。

## 目录结构

```text
src/blivedm/              复制的 B 站直播客户端源码
src/content_agent/
  main.py                 FastAPI 接口与 Web 演示入口
  static/                 无构建步骤的演示页面（HTML/CSS/JS）
  cli.py                  示例输入命令行入口
  live_cli.py             B 站实时事件监听入口
  schemas.py              统一输入输出与事件模型
  pipeline.py             决策中枢
  live_session.py         实时事件聚合、SSE 广播和窗口自动分析
  modules/                阶段引擎、互动分析、卖点匹配、合规检查、融合排序
  providers/               B 站、模拟实时源和直播平台适配器
config/                    商品目录、合规预筛规则、决策规则和模型开关
examples/                  演示输入
docs/                      架构、API、部署、合规、演示脚本和平台接入笔记
THIRD_PARTY_LICENSES/      第三方许可证
```

## 文档

- `docs/architecture.md`：模块边界、决策链路和实时事件流
- `docs/api.md`：接口字段、请求/响应示例、SSE 事件和错误码
- `docs/deployment.md`：环境变量、单 worker 部署、反向代理和故障排查
- `docs/compliance.md`：合规词库分类、语义过滤边界和依据
- `docs/demo.md`：2 分钟演示脚本和故障回退
- `docs/platform-selection.md`：B 站接入方式和消息兼容说明

## 运行示例

```powershell
uv run --env-file .env content-agent --input examples/scene.json

# 促单期 + 同问/负面反馈的冲突演示
uv run --env-file .env content-agent --input examples/scene_conflict.json
```

`examples/scene.json` 保留题目输入中的 `backend_metrics` 字段用于展示输入结构；Web 演示会清空其中的点击/转化示例值，实时模式只取 B 站在线人数。

## 测试

```powershell
uv run python -m unittest discover -s tests -v
```

## 已知限制

1. 场景回放和实时模式都不使用购物车点击/转化的示例值；在线人数只在 Web 实时模式从 B 站房间信息获取。
2. 配置 DeepSeek 时互动理解走 AI 语义分析；未配置 Key 或调用失败时回退关键词规则，相近问法的合并能力会下降。
3. 合规过滤是规则化语义预筛（归一化、语境例外和等价表达）。
4. 实时监听依赖 B 站网页端 Cookie 和 WebSocket；Cookie 失效或房间未开播时需要重新配置后重启监听。
5. 新版房间的 `SEND_GIFT_V2` 只包含礼物名称、数量、价格，不含送礼人昵称；礼物会正常显示，旧版 `SEND_GIFT` 才会显示送礼人。

