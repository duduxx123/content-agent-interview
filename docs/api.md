# API 文档

服务默认监听 `http://127.0.0.1:8080`。除 SSE 外，请求和响应均为 `application/json; charset=utf-8`。启动后可访问 `/docs` 查看交互式 OpenAPI 页面，`/openapi.json` 获取机器可读的接口定义。

## 接口一览

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/analyze` | 对一轮直播输入生成提词建议 |
| GET | `/demo/bootstrap` | 获取演示阶段计划、预置场景和商品目录 |
| GET | `/compliance` | 合规词库浏览页 |
| GET | `/compliance/rules` | 合规词库 JSON |
| GET | `/live/status` | 查询实时监听状态 |
| POST | `/live/start` | 启动 B 站或离线模拟监听 |
| POST | `/live/stop` | 停止监听 |
| POST | `/live/config` | 运行中更新商品、进度或阶段 |
| POST | `/live/analyze` | 立即分析当前窗口 |
| POST | `/live/metrics` | 接入外部业务指标（可选） |
| GET | `/live/events` | SSE 实时事件流 |

错误响应统一为：

```json
{"detail": "错误说明"}
```

常见状态码：

| 状态码 | 场景 |
|---|---|
| 422 | 请求体字段缺失或类型不合法 |
| 409 | `/live/analyze` 时实时监听未启动 |
| 503 | 启动监听失败，例如 Cookie 或房间号未配置 |

## 通用模型

### AgentInput

`POST /analyze` 的请求体。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `live_state` | object | 是 | 直播阶段、已播时长、计划时长、当前 SKU |
| `directive` | object/null | 否 | 运营下发的结构化阶段指令，`target_stage` 优先于时间推算 |
| `recent_comments` | string[] | 否 | 本轮弹幕/醒目留言文本；互动模块会重新统计同问、刷屏、情绪和意图 |
| `comment_analysis` | object | 否 | 上游已算好的互动摘要；`recent_comments` 非空时以模块重新计算为准 |
| `event_counts` | object | 否 | 本轮事件计数，例如 `{"danmaku": 30, "gift": 4}` |
| `product` | object | 是 | 商品事实，见下表 |
| `backend_metrics` | object | 否 | 后台指标；没有真实来源时省略或保持 0，对应信号会关闭 |

`live_state` 字段：`current_stage`、`elapsed_seconds`、`planned_seconds`、`current_sku`。

`product` 字段：`sku_id`、`name`、`specification`、`price`、`ingredients`、`benefits`、`selling_points`、`usage_instructions`、`applicable_audience`、`cautions`、`evidence_notes`。`selling_points` 每项包含 `topic`、`label`、`description`、`match_keywords`、`evidence`、`verified`。

`sku_id` 命中 `config/products.json` 时，缺失的 `selling_points`、`usage_instructions`、`applicable_audience`、`cautions` 和 `evidence_notes` 会由商品目录补全；请求中已提供的字段不会被覆盖。当前目录有 5 个演示 SKU：`12345`、`20001`、`20002`、`20003`、`20004`。

### AgentOutput

| 字段 | 类型 | 说明 |
|---|---|---|
| `suggestions` | object[] | 已排序的提词建议 |
| `analysis_summary` | string[] | 阶段、互动、冲突和合规说明 |
| `stage_state` | object/null | 当前阶段、下一阶段、准备项、进度和来源 |
| `decision_notes` | string[] | 调度说明：冲突、同问/刷屏、合规降级和阶段指令对排序的影响 |
| `generation_mode` | string | 话术生成方式：`rules` 或 `deepseek` |
| `interaction_mode` | string | 互动分析方式：`rules`（关键词）或 `deepseek`（AI 语义） |
| `ai_decision_summary` | string | AI 生成的本轮决策摘要；规则版为空字符串 |

`generation_mode=deepseek` 表示展示的话术由模型根据规则草稿生成/润色，页面会在话术卡片上标“AI 生成”；`rules` 为规则版。`interaction_mode=deepseek` 表示互动分析由 AI 语义完成，页面标“AI 语义”。`decision_notes` 由规则引擎生成，页面标“规则引擎”；`ai_decision_summary` 是模型单独写的一段排序解释，页面在“AI 决策摘要”区块标“AI 生成”。两者不会混在一起。

`suggestions` 每项包含：

```json
{
  "priority": "高",
  "score": 0.868,
  "suggested_script": "当前商品资料列出的控油特点是控油。具体适用范围和使用注意事项请以商品详情为准。",
  "recommended_action": "先核对商品标签或备案资料，再说明控油特点",
  "trigger_reason": "观众提到：油皮",
  "compliance_status": "通过词库预筛查（仍需按语境复核）",
  "topic": "肤质",
  "intent": "答疑",
  "compliance_replacements": []
}
```

`priority` 为 `高` / `中` / `低`，`intent` 为 `讲解` / `答疑` / `转化`。命中合规风险时，`suggested_script` 会被替换为暂缓播报提示，`score` 会被压到 0.1，`priority` 变为 `低`。

## POST /analyze

对一轮直播输入执行阶段引擎、互动理解、卖点匹配、合规过滤和决策融合。

### 请求示例

```json
{
  "live_state": {
    "current_stage": "产品讲解期",
    "elapsed_seconds": 900,
    "planned_seconds": 3600,
    "current_sku": "12345"
  },
  "recent_comments": [
    "油皮能用吗",
    "有没有小样",
    "价格太贵了"
  ],
  "product": {
    "sku_id": "12345",
    "name": "控油保湿精华液",
    "specification": "30ml",
    "price": 350,
    "ingredients": ["水杨酸", "烟酰胺", "透明质酸"],
    "benefits": ["控油", "保湿"]
  }
}
```

### 调用示例

```powershell
# PowerShell：直接提交 examples/scene.json
$body = Get-Content examples/scene.json -Raw -Encoding utf8
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8080/analyze `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

```bash
# curl / Git Bash
curl -X POST http://127.0.0.1:8080/analyze \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary @examples/scene.json
```

```powershell
# 不启动 HTTP 服务，直接用命令行跑同一条 Agent 链路
uv run --env-file .env content-agent --input examples/scene.json
```

### 响应示例

```json
{
  "suggestions": [
    {
      "priority": "高",
      "score": 0.868,
      "suggested_script": "当前商品资料列出的控油特点是控油。具体适用范围和使用注意事项请以商品详情为准。",
      "recommended_action": "先核对商品标签或备案资料，再说明控油特点",
      "trigger_reason": "观众提到：油皮",
      "compliance_status": "通过词库预筛查（仍需按语境复核）",
      "topic": "肤质",
      "intent": "答疑",
      "compliance_replacements": []
    }
  ],
  "analysis_summary": [
    "直播阶段：促单期（推动下单并处理最后疑虑）",
    "下一阶段：收尾期；准备：整理本场高频问题给下一场、回收并复盘本场互动数据"
  ],
  "stage_state": {
    "current_stage": "促单期",
    "declared_stage": "产品讲解期",
    "stage_focus": "转化",
    "stage_goal": "推动下单并处理最后疑虑",
    "next_stage": "收尾期",
    "next_stage_preparation": ["整理本场高频问题给下一场", "回收并复盘本场互动数据"],
    "stage_progress": 0.5,
    "stage_remaining_seconds": 360,
    "total_remaining_seconds": 720,
    "source": "clock",
    "notes": []
  },
  "decision_notes": [
    "促单期与答疑需求冲突：同问最高 3 次、存在负面反馈，已为答疑建议预留更高优先级，并暂缓转化类建议。"
  ],
  "generation_mode": "rules",
  "interaction_mode": "rules",
  "ai_decision_summary": ""
}
```

说明：

- 阶段按 `elapsed_seconds / planned_seconds` 推算；带 `directive.target_stage` 时以指令为准。
- 未启用模型时，互动模块从 `recent_comments` 计算同问、刷屏、负面反馈和购买意向。
- `config/agent.json` 的 `deepseek_enabled` 为 `true` 且配置了 `DEEPSEEK_API_KEY` 时，先对 `recent_comments` 和当前阶段做 AI 语义互动分析，再润色规则草稿。模型会收到弹幕文本、商品事实、主题计数、候选草稿，以及当前阶段、阶段目标、下一阶段准备和阶段来源；润色提示词要求话术按预热/讲解/答疑/促单/收尾阶段调整语气和动作，但不增加商品资料外的事实。模型不接收 Cookie 或用户昵称。语义分析或润色失败会自动回退，`interaction_mode` / `generation_mode` 会标明实际使用的方式。

## GET /demo/bootstrap

返回 Web 演示页面使用的阶段计划、预置场景和商品目录。

```json
{
  "stages": [
    {
      "name": "预热期",
      "start_ratio": 0.0,
      "end_ratio": 0.1,
      "focus": "互动",
      "goal": "暖场并引导关注"
    }
  ],
  "scenes": [
    {"id": "scene", "name": "标准讲解场景", "description": "产品讲解期 · ...", "scene": {}}
  ],
  "products": [
    {
      "sku_id": "20001",
      "name": "氨基酸净澈洁面乳",
      "specification": "120g",
      "price": 89,
      "ingredients": ["氨基酸表活", "甘油", "烟酰胺"],
      "benefits": ["温和清洁", "保湿"]
    }
  ]
}
```

`scene` 是完整的 `AgentInput`，可以直接提交给 `POST /analyze`。

## GET /compliance

返回只读的合规词库浏览页 `static/compliance.html`。页面从 `GET /compliance/rules` 读取数据，支持按风险等级、类别和关键词筛选。

### GET /compliance/rules

返回 `config/compliance_rules.json` 的原始结构：

```json
{
  "version": 1,
  "notice": "本词库用于营销话术风险预筛查……",
  "groups": [
    {
      "category": "绝对化或排名表述",
      "risk_level": "high_review",
      "replacement": "删除无法核验的排名或绝对化表述……",
      "terms": ["国家级", "世界级", "顶级"]
    }
  ]
}
```

`risk_level` 为 `high_review` 或 `review`。该页面只用于浏览，不做实时拦截；实时拦截仍由 Agent 的合规模块执行。

## 实时监听

实时监听把平台消息转换成统一的 `LiveEvent`，通过 SSE 推送给页面，并按窗口自动调用同一条分析链路。当前进程只维护一个 `LiveSession`。

### GET /live/status

```json
{
  "state": "listening",
  "source": "bilibili",
  "room_id": null,
  "window_seconds": 10,
  "started_at": 1760000000,
  "elapsed_seconds": 900,
  "planned_seconds": 3600,
  "current_stage": "产品讲解期",
  "target_stage": null,
  "auto_analyze": false,
  "stage_state": {
    "current_stage": "产品讲解期",
    "stage_goal": "讲清主推商品的核心卖点",
    "next_stage": "答疑期",
    "stage_progress": 0.25,
    "source": "clock"
  },
  "event_count": 42,
  "counts": {"danmaku": 30, "gift": 4, "room_interaction": 8},
  "subscribers": 1,
  "last_analysis_at": 1760000010,
  "error": null,
  "totals": {
    "gift_items": 4,
    "gift_value_rmb": 0.4,
    "super_chat_count": 0,
    "super_chat_value_rmb": 0.0,
    "guard_3_count": 0,
    "guard_3_value_rmb": 0.0,
    "guard_2_count": 0,
    "guard_2_value_rmb": 0.0,
    "guard_1_count": 0,
    "guard_1_value_rmb": 0.0,
    "total_value_rmb": 0.4
  },
  "metrics": {
    "online_count": 1250,
    "cart_click_rate_change": "",
    "conversion_rate": ""
  },
  "sources": {
    "online_count": "bilibili",
    "cart_click_rate_change": "unavailable",
    "conversion_rate": "unavailable"
  }
}
```

`state`：`idle` / `starting` / `listening` / `stopped` / `error`。

`elapsed_seconds` 和 `planned_seconds` 是当前会话的进度；`target_stage` 非空表示手动指定了阶段，`null` 表示按时间推算。`auto_analyze` 默认 `false`；为 `false` 时停止定时窗口分析，弹幕继续累积，手动调用 `POST /live/analyze` 仍可分析。`stage_state` 是当前阶段预览，手动切换阶段时页面用它立即更新右侧阶段卡，不需要等待下一轮分析。

`sources` 的取值：

| 值 | 含义 |
|---|---|
| `bilibili` | 来自 B 站房间信息接口 |
| `pending` | 尚未取到 |
| `unavailable` | 没有可用的公开数据源 |
| `start` | 启动时由请求体提供 |
| `external` | 由 `POST /live/metrics` 推送 |

`room_id` 为直播间号；示例中置空。页面和接口不会返回 Cookie。

### POST /live/start

请求体可省略。字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `source` | string | `bilibili`（默认）或 `simulated` |
| `elapsed_seconds` | int/null | 覆盖模板中的已播时长 |
| `planned_seconds` | int/null | 覆盖模板中的计划时长 |
| `current_stage` | string/null | 覆盖模板中的声明阶段 |
| `target_stage` | string/null | 启动时强制进入某个阶段，优先于时间推算 |
| `auto_analyze` | bool | 是否每个窗口自动分析并刷新提词，默认 `false` |
| `product` | object/null | 覆盖模板商品 |
| `backend_metrics` | object/null | 外部指标；不提供时点击/转化保持不可用 |
| `window_seconds` | int/null | 分析窗口，3–120 秒，默认 10 |

`source=bilibili` 需要进程环境变量 `BILIBILI_ROOM_ID` 和 `BILIBILI_COOKIE`。启动失败返回 503，错误信息只说明缺少哪个配置或连接失败类型，不返回 Cookie。

```json
{
  "source": "simulated",
  "window_seconds": 10
}
```

响应与 `GET /live/status` 相同。如果已经在监听，重复调用会直接返回当前状态。

### POST /live/stop

停止监听并关闭 provider，返回最终状态。没有运行中的会话时返回 `idle`。

### POST /live/config

运行中更新当前会话，不需要停止再启动。用于 Web 页面切换商品、拖动进度或手动指定阶段。

```json
{
  "product": {
    "sku_id": "20003",
    "name": "清透防晒乳",
    "specification": "50ml",
    "price": 159
  },
  "elapsed_seconds": 3000,
  "planned_seconds": 3600,
  "target_stage": "促单期",
  "auto_analyze": false
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `product` | object/null | 新商品；不传则保持当前商品 |
| `elapsed_seconds` | int/null | 新的已播时长；不传则保持当前进度 |
| `planned_seconds` | int/null | 新的计划时长 |
| `current_stage` | string/null | 更新声明阶段 |
| `target_stage` | string/null | 手动指定阶段；空字符串表示恢复按时间推算 |
| `auto_analyze` | bool/null | `false` 暂停定时刷新提词；`true` 恢复自动窗口分析 |

响应与 `GET /live/status` 相同。`target_stage` 会写入分析输入的 `directive`，阶段引擎会优先使用它；更新后下一窗口生效，调用 `POST /live/analyze` 可以立即刷新。`auto_analyze=false` 时窗口定时器不再自动分析，避免提词队列在主播阅读时被替换；弹幕仍会继续累积，手动分析可用。监听未启动返回 409。

### POST /live/analyze

立即分析当前窗口，不等待定时器。

```json
{
  "analysis": {
    "suggestions": [],
    "analysis_summary": [],
    "stage_state": null,
    "decision_notes": [],
    "generation_mode": "rules",
    "interaction_mode": "rules"
  },
  "message": "",
  "at": 1760000010,
  "window_seconds": 10
}
```

窗口内没有弹幕或醒目留言时，`analysis` 为 `null`，`message` 为 `本窗口暂无弹幕`。监听未启动返回 409。

### POST /live/metrics

可选的业务指标接入点，用于未来接入真实的购物车点击率、转化率或其他后台数据。页面当前不调用这个接口。

```json
{
  "online_count": 2222,
  "cart_click_rate_change": "上升12%",
  "conversion_rate": "3.1%",
  "source": "external"
}
```

只更新请求中出现的字段，返回：

```json
{
  "metrics": {
    "online_count": 2222,
    "cart_click_rate_change": "上升12%",
    "conversion_rate": "3.1%"
  },
  "sources": {
    "online_count": "external",
    "cart_click_rate_change": "external",
    "conversion_rate": "external"
  }
}
```

### GET /live/events

`text/event-stream`。连接建立后先发送一条 `snapshot`，之后推送命名事件；15 秒没有消息时发送 `: ping` 注释保持连接。

```text
event: snapshot
data: {"type":"snapshot","status":{...},"events":[],"analysis":null,"window":{"comments":[],"counts":{}},"window_seconds":10}

event: event
data: {"type":"event","event":{"id":1,"kind":"danmaku","text":"油皮能用吗","user":"观众A","timestamp":1760000000,"received_at":1760000000,"metrics":{}},"counts":{"danmaku":1},"totals":{...}}

event: analysis
data: {"type":"analysis","output":{...},"window_seconds":10,"comments":["油皮能用吗"],"counts":{"danmaku":1},"latency_ms":35,"at":1760000010}
```

事件类型：

| `event` | 触发时机 | 主要字段 |
|---|---|---|
| `snapshot` | 建立连接时 | `status`、`events`、`analysis`、`window`、`window_seconds` |
| `status` | 状态变化 | 与 `/live/status` 相同，另带 `type` |
| `event` | 收到一条直播事件 | `event`、`counts`、`totals` |
| `metrics` | 在线人数或外部指标变化 | `metrics`、`sources` |
| `window` | 窗口结束但没有可分析文本 | `comments`、`counts`、`window_seconds`、`at` |
| `analysis` | 窗口分析完成 | `output`、`window_seconds`、`comments`、`counts`、`latency_ms`、`at` |
| `live-error` | provider 中断或单窗口分析失败 | `message`、`fatal`（`true` 表示监听已停止） |

`event.event.kind`：

| kind | 含义 | `metrics` |
|---|---|---|
| `danmaku` | 弹幕 | 空 |
| `gift` | 礼物 | `price`、`num`、`total_coin`、`coin_type`、`value_rmb` |
| `guard` | 上舰 | `guard_level`（1 总督 / 2 提督 / 3 舰长）、`price`、`num`、`coin_type`、`value_rmb` |
| `super_chat` | 醒目留言 | `price_rmb`、`value_rmb` |
| `room_interaction` | 进房、关注、分享、点赞等 | `interaction_type` |

价值按面值折算：`1000 金瓜子 = 1 元`，银瓜子礼物计 0 元；舰长、提督、总督分别累计件数和价值。该数值不是平台结算或分成后的收入。

断线重连会重新收到 `snapshot`，不会补发断线期间遗漏的事件。昵称只在 `event.user` 和页面展示，不进入互动分析文本或模型输入。

## 配置与模型调用

| 环境变量 | 用途 |
|---|---|
| `BILIBILI_ROOM_ID` | B 站直播间号 |
| `BILIBILI_COOKIE` | B 站网页端 Cookie，仅从进程环境读取 |
| `DEEPSEEK_API_KEY` | 可选，启用模型润色 |
| `DEEPSEEK_BASE_URL` | 默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 默认 `deepseek-flash` |
| `DEEPSEEK_TIMEOUT_SECONDS` | 默认 20 |

`config/agent.json` 的 `deepseek_enabled` 控制是否启用模型。关闭时 `interaction_mode` 和 `generation_mode` 都保持 `rules`；开启但调用失败时，对应字段会保持 `rules` 并继续返回关键词/规则版结果。
