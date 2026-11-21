const ui = {
  status: document.getElementById("agent-status"),
  statusText: document.getElementById("status-text"),
  modeReplay: document.getElementById("mode-replay"),
  modeLive: document.getElementById("mode-live"),
  replayFields: document.getElementById("replay-fields"),
  livePanel: document.getElementById("live-panel"),
  liveDot: document.getElementById("live-dot"),
  liveState: document.getElementById("live-state"),
  liveDetail: document.getElementById("live-detail"),
  liveSource: document.getElementById("live-source"),
  liveStage: document.getElementById("live-stage"),
  liveAuto: document.getElementById("live-auto"),
  liveStart: document.getElementById("live-start"),
  liveStop: document.getElementById("live-stop"),
  liveDanmaku: document.getElementById("live-danmaku"),
  liveGift: document.getElementById("live-gift"),
  liveSuper: document.getElementById("live-super"),
  liveOnline: document.getElementById("live-online"),
  liveGiftValue: document.getElementById("live-gift-value"),
  liveSuperValue: document.getElementById("live-super-value"),
  liveGuard3: document.getElementById("live-guard-3"),
  liveGuard2: document.getElementById("live-guard-2"),
  liveGuard1: document.getElementById("live-guard-1"),
  liveTotalValue: document.getElementById("live-total-value"),
  liveFeed: document.getElementById("live-feed"),
  liveWindowHint: document.getElementById("live-window-hint"),
  presets: document.getElementById("presets"),
  presetDesc: document.getElementById("preset-desc"),
  modeNote: document.getElementById("mode-note"),
  elapsed: document.getElementById("elapsed"),
  elapsedLabel: document.getElementById("elapsed-label"),
  plannedLabel: document.getElementById("planned-label"),
  directive: document.getElementById("directive"),
  comments: document.getElementById("comments"),
  commentCount: document.getElementById("comment-count"),
  superChat: document.getElementById("super-chat"),
  gift: document.getElementById("gift"),
  productPreset: document.getElementById("product-preset"),
  productName: document.getElementById("product-name"),
  productSpec: document.getElementById("product-spec"),
  productPrice: document.getElementById("product-price"),
  productIngredients: document.getElementById("product-ingredients"),
  productBenefits: document.getElementById("product-benefits"),
  productSummary: document.getElementById("product-summary"),
  resetBtn: document.getElementById("reset-btn"),
  runBtn: document.getElementById("run-btn"),
  runLabel: document.getElementById("run-label"),
  errorBanner: document.getElementById("error-banner"),
  stageSource: document.getElementById("stage-source"),
  stageName: document.getElementById("stage-name"),
  stageGoal: document.getElementById("stage-goal"),
  stageRemaining: document.getElementById("stage-remaining"),
  stageTotal: document.getElementById("stage-total"),
  stageNote: document.getElementById("stage-note"),
  timeline: document.getElementById("timeline"),
  nextStage: document.getElementById("next-stage"),
  prepList: document.getElementById("prep-list"),
  notes: document.getElementById("notes"),
  notesCount: document.getElementById("notes-count"),
  aiSummary: document.getElementById("ai-summary"),
  aiSummaryText: document.getElementById("ai-summary-text"),
  queue: document.getElementById("queue"),
  queueMeta: document.getElementById("queue-meta"),
  queueAuto: document.getElementById("queue-auto"),
  queueAutoWrap: document.getElementById("queue-auto-wrap"),
  output: document.querySelector(".output"),
  summaryDetails: document.getElementById("summary-details"),
  summaryList: document.getElementById("summary-list"),
  summaryCount: document.getElementById("summary-count"),
};

const state = {
  scenes: [],
  stages: [],
  products: [],
  sceneId: null,
  scene: null,
  mode: "replay",
  runId: 0,
  controller: null,
  liveStream: null,
  liveListening: false,
  liveStartedAt: 0,
  lastLiveEventId: 0,
  lastAnalysisAt: 0,
  liveWindowSeconds: 10,
};

const LIVE_KIND_LABELS = {
  danmaku: "弹幕",
  gift: "礼物",
  guard: "上舰",
  super_chat: "醒目留言",
  room_interaction: "互动",
};

const LIVE_STATE_LABELS = {
  idle: "未开始",
  starting: "连接中",
  listening: "监听中",
  stopped: "已停止",
  error: "连接失败",
};


const SOURCE_LABELS = {
  clock: "时间推算",
  directive: "结构化指令",
  declared: "输入声明",
};

function formatClock(totalSeconds) {
  const value = Math.max(0, Math.round(Number(totalSeconds) || 0));
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function clamp(value, low, high) {
  return Math.min(Math.max(value, low), high);
}

function toInt(value) {
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

function splitList(value) {
  return value
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function emptyAnalysis() {
  return {
    hot_words: {},
    negative_feedback: [],
    purchase_intent: [],
    questions: [],
    repeated_questions: {},
    repeated_comments: {},
  };
}

function setStatus(mode, text) {
  ui.status.dataset.state = mode;
  ui.statusText.textContent = text;
}

function showError(message) {
  ui.errorBanner.replaceChildren();
  const text = document.createElement("span");
  text.textContent = message;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "text-btn";
  close.textContent = "关闭";
  close.addEventListener("click", hideError);
  ui.errorBanner.append(text, close);
  ui.errorBanner.hidden = false;
}

function hideError() {
  ui.errorBanner.hidden = true;
  ui.errorBanner.replaceChildren();
}

function renderPresets() {
  ui.presets.replaceChildren();
  for (const preset of state.scenes) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preset-tab";
    button.textContent = preset.name;
    button.title = preset.description || "";
    button.setAttribute("aria-pressed", String(preset.id === state.sceneId));
    button.addEventListener("click", () => selectScene(preset.id, true));
    ui.presets.append(button);
  }
}

function renderLiveStageOptions() {
  const current = ui.liveStage.value;
  ui.liveStage.replaceChildren();
  const auto = document.createElement("option");
  auto.value = "";
  auto.textContent = "按时间推进";
  ui.liveStage.append(auto);
  for (const stage of state.stages) {
    if (!stage.name) {
      continue;
    }
    const option = document.createElement("option");
    option.value = stage.name;
    option.textContent = stage.name;
    ui.liveStage.append(option);
  }
  ui.liveStage.value = Array.from(ui.liveStage.options).some(
    (option) => option.value === current
  )
    ? current
    : "";
}

function renderProductOptions() {
  ui.productPreset.replaceChildren();
  const custom = document.createElement("option");
  custom.value = "";
  custom.textContent = "自定义 / 当前场景";
  ui.productPreset.append(custom);

  for (const product of state.products) {
    const option = document.createElement("option");
    option.value = product.sku_id;
    const price =
      product.price === null || product.price === undefined
        ? "价格待定"
        : `¥${product.price}`;
    option.textContent = `${product.name} · ${product.specification || "规格待定"} · ${price}`;
    ui.productPreset.append(option);
  }
}

function selectScene(id, run) {
  const preset = state.scenes.find((item) => item.id === id);
  if (!preset) {
    return;
  }
  state.sceneId = id;
  state.scene = structuredClone(preset.scene);
  ui.presetDesc.textContent = preset.description || "";
  renderPresets();
  populateForm();
  hideError();
  if (run && state.mode === "replay") {
    runAnalysis();
  }
}

function populateForm() {
  const scene = state.scene || {};
  const live = scene.live_state || {};
  const planned = Math.max(1, Number(live.planned_seconds) || 3600);
  const elapsed = clamp(Number(live.elapsed_seconds) || 0, 0, planned);

  ui.elapsed.max = String(planned);
  ui.elapsed.value = String(elapsed);
  ui.plannedLabel.textContent = formatClock(planned);
  updateElapsedLabel();
  ui.directive.value = "none";

  const comments = Array.isArray(scene.recent_comments) ? scene.recent_comments : [];
  ui.comments.value = comments.join("\n");
  updateCommentCount();

  const events = scene.event_counts || {};
  ui.superChat.value = String(Math.max(0, Number(events.super_chat) || 0));
  ui.gift.value = String(Math.max(0, Number(events.gift) || 0));

  const product = scene.product || {};
  ui.productName.value = product.name || "";
  ui.productSpec.value = product.specification || "";
  ui.productPrice.value =
    product.price === null || product.price === undefined ? "" : String(product.price);
  ui.productIngredients.value = Array.isArray(product.ingredients)
    ? product.ingredients.join("，")
    : "";
  ui.productBenefits.value = Array.isArray(product.benefits)
    ? product.benefits.join("，")
    : "";
  const sku = product.sku_id || "";
  ui.productPreset.value = state.products.some((item) => item.sku_id === sku)
    ? sku
    : "";
  updateProductSummary();
}

function updateElapsedLabel() {
  const planned = Number(ui.elapsed.max) || 3600;
  const elapsed = Number(ui.elapsed.value) || 0;
  ui.elapsedLabel.textContent = `${formatClock(elapsed)} / ${formatClock(planned)}`;
}

function updateCommentCount() {
  const count = ui.comments.value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean).length;
  ui.commentCount.textContent = `${count} 条`;
}

function updateProductSummary() {
  const name = ui.productName.value.trim() || "未命名商品";
  const spec = ui.productSpec.value.trim() || "规格待定";
  const rawPrice = ui.productPrice.value.trim();
  const price = Number(rawPrice);
  const priceText =
    rawPrice !== "" && Number.isFinite(price)
      ? `¥${price.toLocaleString("zh-CN")}`
      : "价格待定";
  ui.productSummary.textContent = `${name} · ${spec} · ${priceText}`;
  ui.productSummary.title = ui.productSummary.textContent;
}

function buildProduct() {
  const base =
    state.scene && state.scene.product ? structuredClone(state.scene.product) : {};
  base.name = ui.productName.value.trim() || base.name || "未命名商品";
  base.specification = ui.productSpec.value.trim();
  const rawPrice = ui.productPrice.value.trim();
  const parsedPrice = rawPrice === "" ? null : Number(rawPrice);
  base.price = Number.isFinite(parsedPrice) ? parsedPrice : null;
  base.ingredients = splitList(ui.productIngredients.value);
  base.benefits = splitList(ui.productBenefits.value);
  return base;
}

function buildPayload() {
  const base = structuredClone(state.scene);
  const comments = ui.comments.value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

  base.live_state = {
    ...(base.live_state || {}),
    elapsed_seconds: Number(ui.elapsed.value) || 0,
  };

  if (ui.directive.value === "none") {
    delete base.directive;
  } else {
    base.directive = {
      target_stage: ui.directive.value,
      reason: "演示：运营下发结构化指令",
    };
  }

  base.recent_comments = comments;
  base.comment_analysis = emptyAnalysis();
  base.event_counts = {
    danmaku: comments.length,
    super_chat: toInt(ui.superChat.value),
    gift: toInt(ui.gift.value),
  };
  // The demo does not have a real cart/conversion source, so leave those signals off.
  base.backend_metrics = {
    online_count: 0,
    cart_click_rate_change: "",
    conversion_rate: "",
  };
  base.product = buildProduct();

  return base;
}

async function runAnalysis() {
  if (!state.scene) {
    return;
  }

  const runId = ++state.runId;
  state.controller?.abort();
  const controller = new AbortController();
  state.controller = controller;

  setStatus("running", "分析中");
  ui.runBtn.disabled = true;
  hideError();
  ui.queueMeta.textContent = "正在生成…";
  const startedAt = performance.now();

  try {
    const response = await fetch("/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(buildPayload()),
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `请求失败（HTTP ${response.status}）`;
      const body = await response.json().catch(() => null);
      if (body && body.detail) {
        detail = Array.isArray(body.detail)
          ? body.detail.map((item) => item.msg || JSON.stringify(item)).join("；")
          : String(body.detail);
      }
      throw new Error(detail);
    }

    const data = await response.json();
    if (runId !== state.runId) {
      return;
    }
    renderOutput(data, Math.round(performance.now() - startedAt));
    setStatus("ready", "已更新");
  } catch (error) {
    if (error.name === "AbortError" || runId !== state.runId) {
      return;
    }
    setStatus("error", "分析失败");
    showError(error.message || "无法连接分析服务");
    ui.queueMeta.textContent = "未更新";
  } finally {
    if (runId === state.runId) {
      ui.runBtn.disabled = false;
    }
  }
}

function renderOutput(data, latency) {
  const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
  const summary = Array.isArray(data.analysis_summary) ? data.analysis_summary : [];
  const notes = Array.isArray(data.decision_notes) ? data.decision_notes : [];

  renderStage(data.stage_state || null);
  renderAiSummary(data.ai_decision_summary || "");
  renderNotes(notes);
  renderSuggestions(
    suggestions,
    data.generation_mode === "deepseek",
    (data.stage_state || {}).current_stage || ""
  );
  renderSummary(summary, notes, data.stage_state || null);

  const mode = data.generation_mode === "deepseek" ? "DeepSeek 润色" : "规则版";
  const interaction =
    data.interaction_mode === "deepseek" ? "AI 语义" : "关键词";
  ui.queueMeta.textContent = `${mode} · ${interaction} · ${suggestions.length} 条建议 · ${latency} ms`;
  if (ui.output) {
    ui.output.scrollTop = 0;
  }
}

function renderStage(stage) {
  ui.prepList.replaceChildren();

  if (!stage) {
    ui.stageSource.textContent = "待分析";
    delete ui.stageSource.dataset.source;
    ui.stageName.textContent = "待命";
    ui.stageGoal.textContent = "载入场景后生成提词建议";
    ui.stageRemaining.textContent = "--:--";
    ui.stageTotal.textContent = "本阶段剩余";
    ui.stageNote.hidden = true;
    ui.stageNote.textContent = "";
    ui.nextStage.textContent = "—";
    renderTimeline(null);
    return;
  }

  ui.stageSource.textContent = SOURCE_LABELS[stage.source] || stage.source || "未知来源";
  if (stage.source) {
    ui.stageSource.dataset.source = stage.source;
  } else {
    delete ui.stageSource.dataset.source;
  }
  ui.stageName.textContent = stage.current_stage || "未知阶段";
  ui.stageGoal.textContent = stage.stage_goal || "—";
  ui.stageRemaining.textContent = formatClock(stage.stage_remaining_seconds);
  ui.stageTotal.textContent = `本阶段剩余 · 总剩余 ${formatClock(
    stage.total_remaining_seconds
  )}`;
  ui.nextStage.textContent = stage.next_stage || "本场最后阶段";

  const stageNotes = Array.isArray(stage.notes) ? stage.notes : [];
  ui.stageNote.hidden = stageNotes.length === 0;
  ui.stageNote.textContent = stageNotes.join("；");

  const preparation = Array.isArray(stage.next_stage_preparation)
    ? stage.next_stage_preparation
    : [];
  for (const item of preparation) {
    const li = document.createElement("li");
    li.textContent = item;
    ui.prepList.append(li);
  }

  renderTimeline(stage);
}

function renderTimeline(stage) {
  ui.timeline.replaceChildren();

  if (!state.stages.length) {
    const segment = document.createElement("div");
    segment.className = "timeline-seg is-current";
    segment.style.flex = "1";
    const label = document.createElement("span");
    label.className = "seg-label";
    label.textContent = "未加载阶段计划";
    segment.append(label);
    ui.timeline.append(segment);
    return;
  }

  const currentIndex = stage
    ? state.stages.findIndex((item) => item.name === stage.current_stage)
    : -1;

  state.stages.forEach((item, index) => {
    const span = Math.max(0.01, Number(item.end_ratio) - Number(item.start_ratio));
    const segment = document.createElement("div");
    segment.className = "timeline-seg";
    segment.style.flex = `${span} 1 0`;

    const isCurrent = index === currentIndex;
    const isPast = currentIndex >= 0 && index < currentIndex;
    if (isCurrent) {
      segment.classList.add("is-current");
    }
    if (isPast) {
      segment.classList.add("is-past");
    }

    const fill = document.createElement("span");
    fill.className = "seg-fill";
    if (isCurrent) {
      const progress = clamp(Number(stage.stage_progress) || 0, 0, 1);
      fill.style.width = `${Math.round(progress * 100)}%`;
    } else if (isPast) {
      fill.style.width = "100%";
    }

    const label = document.createElement("span");
    label.className = "seg-label";
    label.textContent = item.name || "";

    segment.append(fill, label);
    ui.timeline.append(segment);
  });
}

function renderAiSummary(text) {
  const summary = String(text || "").trim();
  ui.aiSummaryText.textContent = summary;
  ui.aiSummary.hidden = !summary;
}

function renderNotes(notes) {
  ui.notes.replaceChildren();
  ui.notesCount.textContent = `${notes.length} 条`;

  if (!notes.length) {
    const empty = document.createElement("p");
    empty.className = "notes-empty";
    empty.textContent = "本轮没有冲突、合规降级或阶段调整需要说明。";
    ui.notes.append(empty);
    return;
  }

  for (const note of notes) {
    const row = document.createElement("p");
    row.className = "note-row";
    if (note.includes("合规")) {
      row.classList.add("is-compliance");
    } else if (
      note.includes("冲突") ||
      note.includes("暂缓") ||
      note.includes("保留答疑")
    ) {
      row.classList.add("is-conflict");
    } else if (
      note.includes("刷屏") ||
      note.includes("同问") ||
      note.includes("加权")
    ) {
      row.classList.add("is-signal");
    }
    row.textContent = note;
    ui.notes.append(row);
  }
}

function makePriority(value) {
  const badge = document.createElement("span");
  badge.className = "priority";
  badge.dataset.priority = value || "低";
  badge.textContent = value || "低";
  return badge;
}

function makeChip(text) {
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.textContent = text;
  return chip;
}

function makeMeta(label, value, blocked) {
  const item = document.createElement("div");
  const title = document.createElement("span");
  title.textContent = label;
  const body = document.createElement("p");
  body.textContent = value || "—";
  if (blocked) {
    body.classList.add("is-blocked");
  }
  item.append(title, body);
  return item;
}

function renderQueueEmpty(text) {
  const empty = document.createElement("p");
  empty.className = "queue-empty";
  empty.textContent = text;
  ui.queue.replaceChildren(empty);
}

function renderSuggestions(suggestions, aiGenerated = false, stageName = "") {
  ui.queue.replaceChildren();

  if (!suggestions.length) {
    renderQueueEmpty("本轮没有生成建议，检查弹幕或商品资料。");
    return;
  }

  suggestions.forEach((suggestion, index) => {
    const blocked = String(suggestion.compliance_status || "").startsWith("需");
    const cue = document.createElement("article");
    cue.className = "cue";
    cue.dataset.priority = suggestion.priority || "低";
    cue.style.setProperty("--i", String(index));
    if (blocked) {
      cue.classList.add("is-blocked");
    }

    const rank = document.createElement("div");
    rank.className = "cue-rank";
    rank.textContent = String(index + 1).padStart(2, "0");

    const main = document.createElement("div");
    main.className = "cue-main";

    const head = document.createElement("div");
    head.className = "cue-head";
    head.append(makePriority(suggestion.priority));
    if (suggestion.topic) {
      head.append(makeChip(suggestion.topic));
    }
    if (suggestion.intent) {
      head.append(makeChip(suggestion.intent));
    }
    if (aiGenerated && !blocked) {
      const aiChip = makeChip("AI 生成");
      aiChip.classList.add("is-ai");
      aiChip.title = `该话术由 DeepSeek 根据${
        stageName || "当前"
      }阶段和规则草稿生成/润色`;
      head.append(aiChip);
    }

    const score = document.createElement("div");
    score.className = "score";
    const scoreValue = document.createElement("span");
    scoreValue.className = "score-value";
    const numeric = Number(suggestion.score);
    scoreValue.textContent = Number.isFinite(numeric) ? numeric.toFixed(3) : "—";
    const meter = document.createElement("span");
    meter.className = "score-meter";
    const meterFill = document.createElement("span");
    meterFill.style.width = `${Math.round(
      clamp(Number.isFinite(numeric) ? numeric : 0, 0, 1) * 100
    )}%`;
    meter.append(meterFill);
    const scoreLabel = document.createElement("span");
    scoreLabel.textContent = "匹配分";
    score.append(scoreValue, meter, scoreLabel);
    head.append(score);

    const script = document.createElement("p");
    script.className = "cue-script";
    script.textContent = suggestion.suggested_script || "—";

    const meta = document.createElement("div");
    meta.className = "cue-meta";
    meta.append(
      makeMeta("动作", suggestion.recommended_action, false),
      makeMeta("触发", suggestion.trigger_reason, false),
      makeMeta("合规", suggestion.compliance_status, blocked)
    );

    main.append(head, script, meta);

    const replacements = Array.isArray(suggestion.compliance_replacements)
      ? suggestion.compliance_replacements
      : [];
    if (replacements.length) {
      const block = document.createElement("div");
      block.className = "replacements";
      const title = document.createElement("strong");
      title.textContent = "替代表达";
      const list = document.createElement("ul");
      for (const item of replacements) {
        const li = document.createElement("li");
        li.textContent = item;
        list.append(li);
      }
      block.append(title, list);
      main.append(block);
    }

    cue.append(rank, main);
    ui.queue.append(cue);
  });
}

function renderSummary(summary, notes, stage) {
  const excluded = new Set(notes);
  const stageNotes = new Set(
    stage && Array.isArray(stage.notes) ? stage.notes : []
  );
  const lines = summary.filter((line) => {
    if (!line) {
      return false;
    }
    if (
      line.startsWith("直播阶段：") ||
      line.startsWith("下一阶段：") ||
      line.startsWith("当前阶段：")
    ) {
      return false;
    }
    return !excluded.has(line) && !stageNotes.has(line);
  });

  ui.summaryCount.textContent = `${lines.length} 条`;
  ui.summaryList.replaceChildren();

  if (!lines.length) {
    const li = document.createElement("li");
    li.textContent = "无额外明细";
    ui.summaryList.append(li);
    return;
  }

  for (const line of lines) {
    const li = document.createElement("li");
    li.textContent = line;
    ui.summaryList.append(li);
  }
}

function setLiveState(stateName, detail) {
  ui.liveDot.dataset.state = stateName;
  ui.liveState.textContent = LIVE_STATE_LABELS[stateName] || stateName;
  ui.liveDetail.textContent = detail || "";
}

function formatEventTime(value) {
  const numeric = Number(value);
  let milliseconds =
    Number.isFinite(numeric) && numeric > 0 ? numeric : Date.now();
  if (milliseconds < 1e12) {
    milliseconds *= 1000;
  }
  return new Date(milliseconds).toLocaleTimeString("zh-CN", { hour12: false });
}

function formatMoney(value) {
  return `¥${(Number(value) || 0).toFixed(2)}`;
}

function updateLiveCounters(counts) {
  ui.liveDanmaku.textContent = String(counts.danmaku || 0);
}

function updateLiveTotals(totals) {
  if (!totals) {
    return;
  }
  ui.liveGift.textContent = String(totals.gift_items ?? 0);
  ui.liveSuper.textContent = String(totals.super_chat_count ?? 0);
  ui.liveGiftValue.textContent = formatMoney(totals.gift_value_rmb);
  ui.liveSuperValue.textContent = formatMoney(totals.super_chat_value_rmb);
  ui.liveGuard3.textContent = `${totals.guard_3_count ?? 0} · ${formatMoney(
    totals.guard_3_value_rmb
  )}`;
  ui.liveGuard2.textContent = `${totals.guard_2_count ?? 0} · ${formatMoney(
    totals.guard_2_value_rmb
  )}`;
  ui.liveGuard1.textContent = `${totals.guard_1_count ?? 0} · ${formatMoney(
    totals.guard_1_value_rmb
  )}`;
  ui.liveTotalValue.textContent = formatMoney(totals.total_value_rmb);
}

function resetLiveFeed() {
  const empty = document.createElement("p");
  empty.className = "feed-empty";
  empty.textContent = "等待直播事件";
  ui.liveFeed.replaceChildren(empty);
}

function appendFeedRow(event) {
  const empty = ui.liveFeed.querySelector(".feed-empty");
  if (empty) {
    empty.remove();
  }

  const row = document.createElement("div");
  row.className = "feed-row";
  row.dataset.kind = event.kind || "other";

  const time = document.createElement("span");
  time.className = "feed-time";
  time.textContent = formatEventTime(event.received_at || event.timestamp);

  const kind = document.createElement("span");
  kind.className = "feed-kind";
  kind.textContent = LIVE_KIND_LABELS[event.kind] || "事件";

  const text = document.createElement("span");
  text.className = "feed-text";
  let content = event.text || "";
  if (event.kind === "room_interaction" && !content) {
    content = "互动";
  }
  if (event.kind === "gift") {
    content = `送出 ${content || "礼物"}`;
    const metrics = event.metrics || {};
    if (metrics.coin_type === "silver") {
      content += " · 免费";
    } else if (metrics.value_rmb !== undefined) {
      content += ` · ${formatMoney(metrics.value_rmb)}`;
    }
  }
  if (event.kind === "guard") {
    content = `开通 ${content || "舰队"}`;
    if (event.metrics && event.metrics.value_rmb !== undefined) {
      content += ` · ${formatMoney(event.metrics.value_rmb)}`;
    }
  }
  if (
    event.kind === "super_chat" &&
    event.metrics &&
    event.metrics.price_rmb !== undefined
  ) {
    content = `¥${event.metrics.price_rmb} · ${content || "醒目留言"}`;
  }
  if (!content) {
    content = "—";
  }
  if (event.user) {
    const user = document.createElement("span");
    user.className = "feed-user";
    user.textContent = event.user;
    text.append(user);
  }
  const body = document.createElement("span");
  body.className = "feed-body";
  body.textContent = content;
  text.append(body);

  row.append(time, kind, text);

  const nearBottom =
    ui.liveFeed.scrollHeight -
      ui.liveFeed.scrollTop -
      ui.liveFeed.clientHeight <
    80;
  ui.liveFeed.append(row);
  while (ui.liveFeed.children.length > 200) {
    ui.liveFeed.firstElementChild.remove();
  }
  if (nearBottom) {
    ui.liveFeed.scrollTop = ui.liveFeed.scrollHeight;
  }
}

function appendFeedEvent(event) {
  if (!event) {
    return;
  }
  const id = Number(event.id) || 0;
  if (id && id <= state.lastLiveEventId) {
    return;
  }
  if (id) {
    state.lastLiveEventId = id;
  }
  appendFeedRow(event);
}

function updateLiveOnline(metrics, sources) {
  const source = sources && sources.online_count;
  const online = metrics ? Number(metrics.online_count) : NaN;
  if (["bilibili", "external"].includes(source) && Number.isFinite(online)) {
    ui.liveOnline.textContent = String(online);
    ui.liveOnline.title =
      source === "bilibili" ? "来自 B 站房间信息" : "来自外部推送";
  } else {
    ui.liveOnline.textContent = "—";
    ui.liveOnline.title = "未接入在线人数数据源";
  }
}

function applyLiveStatus(status) {
  if (!status) {
    return;
  }
  state.liveListening = status.state === "listening";
  if (status.window_seconds) {
    state.liveWindowSeconds = status.window_seconds;
  }
  if (status.source === "bilibili" || status.source === "simulated") {
    ui.liveSource.value = status.source;
  }
  if (status.target_stage === null || typeof status.target_stage === "string") {
    ui.liveStage.value = status.target_stage || "";
  }
  if (typeof status.auto_analyze === "boolean") {
    ui.liveAuto.checked = status.auto_analyze;
    ui.queueAuto.checked = status.auto_analyze;
  }

  let detail = "";
  if (status.state === "idle") {
    detail = "选择数据源并开始监听";
  } else if (status.state === "starting") {
    detail = "正在连接直播事件源…";
  } else if (status.state === "listening") {
    const analyzeMode = status.auto_analyze
      ? `每 ${status.window_seconds} 秒分析`
      : "手动分析";
    detail =
      status.source === "simulated"
        ? `离线模拟源 · ${analyzeMode}`
        : `房间 ${status.room_id ?? "—"} · ${analyzeMode}`;
  } else if (status.state === "stopped") {
    detail = "监听已停止，可重新开始";
  } else if (status.state === "error") {
    detail = status.error || "直播源连接失败";
  }
  setLiveState(status.state, detail);
  if (status.stage_state) {
    renderStage(status.stage_state);
  }

  const startedAt = Number(status.started_at) || 0;
  if (startedAt && startedAt !== state.liveStartedAt) {
    state.liveStartedAt = startedAt;
    resetLiveFeed();
    state.lastLiveEventId = 0;
    state.lastAnalysisAt = 0;
  }
  updateLiveCounters(status.counts || {});
  updateLiveTotals(status.totals);

  ui.liveStart.hidden =
    status.state === "listening" || status.state === "starting";
  ui.liveStop.hidden = status.state !== "listening";
  ui.liveStart.disabled = status.state === "starting";
  ui.liveSource.disabled =
    status.state === "listening" || status.state === "starting";

  updateLiveOnline(status.metrics, status.sources || {});

  if (status.auto_analyze === false) {
    ui.liveWindowHint.textContent =
      status.state === "listening"
        ? "自动刷新已暂停；点“立即分析本窗口”更新队列"
        : "自动刷新默认关闭；开始监听后点“立即分析本窗口”更新队列";
  } else if (status.last_analysis_at) {
    ui.liveWindowHint.textContent = `上次分析 ${formatEventTime(
      status.last_analysis_at
    )} · 窗口 ${status.window_seconds} 秒`;
  } else {
    ui.liveWindowHint.textContent = `每 ${
      status.window_seconds || state.liveWindowSeconds
    } 秒自动分析一个弹幕窗口`;
  }
}

async function refreshLiveStatus() {
  try {
    const response = await fetch("/live/status", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return;
    }
    applyLiveStatus(await response.json());
  } catch (error) {
    // The SSE connection reports reconnection state; ignore polling failures.
  }
}

function connectLiveStream() {
  if (state.liveStream) {
    return;
  }
  const stream = new EventSource("/live/events");
  state.liveStream = stream;

  stream.addEventListener("snapshot", (event) => {
    handleLiveSnapshot(JSON.parse(event.data));
  });
  stream.addEventListener("status", (event) => {
    applyLiveStatus(JSON.parse(event.data));
  });
  stream.addEventListener("event", (event) => {
    handleLiveEvent(JSON.parse(event.data));
  });
  stream.addEventListener("analysis", (event) => {
    handleLiveAnalysis(JSON.parse(event.data));
  });
  stream.addEventListener("metrics", (event) => {
    handleLiveMetrics(JSON.parse(event.data));
  });
  stream.addEventListener("window", (event) => {
    handleLiveWindow(JSON.parse(event.data));
  });
  stream.addEventListener("live-error", (event) => {
    handleLiveError(JSON.parse(event.data));
  });
  stream.onerror = () => {
    if (state.mode === "live") {
      setLiveState("starting", "连接中断，正在重连…");
    }
  };
}

function closeLiveStream() {
  if (state.liveStream) {
    state.liveStream.close();
    state.liveStream = null;
  }
}

function handleLiveSnapshot(data) {
  applyLiveStatus(data.status);
  resetLiveFeed();
  state.lastLiveEventId = 0;
  for (const event of data.events || []) {
    appendFeedEvent(event);
  }
  if (data.analysis) {
    applyLiveAnalysis(
      data.analysis,
      0,
      data.window_seconds,
      data.status ? data.status.last_analysis_at : 0
    );
  } else if (data.window && Array.isArray(data.window.comments) && data.window.comments.length) {
    ui.queueMeta.textContent = `实时窗口 · 已收到 ${data.window.comments.length} 条弹幕，等待分析`;
  }
}

function handleLiveEvent(data) {
  if (!data.event) {
    return;
  }
  appendFeedEvent(data.event);
  updateLiveCounters(data.counts || {});
  updateLiveTotals(data.totals);
}

function applyLiveAnalysis(output, latency, windowSeconds, at) {
  if (!output) {
    return;
  }
  const analysisAt = Number(at) || 0;
  if (analysisAt && analysisAt === state.lastAnalysisAt) {
    return;
  }
  if (analysisAt) {
    state.lastAnalysisAt = analysisAt;
  }

  renderOutput(output, Number(latency) || 0);
  const count = Array.isArray(output.suggestions) ? output.suggestions.length : 0;
  const seconds = Number(windowSeconds) || state.liveWindowSeconds;
  const interaction =
    output.interaction_mode === "deepseek" ? "AI 语义" : "关键词";
  const generation =
    output.generation_mode === "deepseek" ? "AI 生成" : "规则版";
  ui.queueMeta.textContent = `实时 · ${seconds} 秒窗口 · ${interaction} · ${generation} · ${count} 条建议${
    latency ? ` · ${latency} ms` : ""
  }`;
  ui.liveWindowHint.textContent = `上次分析 ${formatEventTime(
    analysisAt || Date.now() / 1000
  )} · 本窗口 ${seconds} 秒`;
  setStatus("ready", "已更新");
}

function handleLiveAnalysis(data) {
  if (!data.output || !ui.liveAuto.checked) {
    return;
  }
  applyLiveAnalysis(
    data.output,
    data.latency_ms,
    data.window_seconds,
    data.at
  );
}

function handleLiveMetrics(data) {
  updateLiveOnline(data.metrics, data.sources || {});
}

function handleLiveWindow(data) {
  if (data.comments && data.comments.length) {
    ui.liveWindowHint.textContent = `本窗口 ${data.comments.length} 条弹幕待分析`;
    return;
  }
  ui.liveWindowHint.textContent = `本窗口无弹幕 · ${formatEventTime(data.at)}`;
}

function handleLiveError(data) {
  if (!data || !data.message) {
    return;
  }
  showError(data.message);
  if (data.fatal) {
    setLiveState("error", data.message);
  }
}

async function updateLiveConfig(
  body,
  { clearQueue = true, clearSummary = clearQueue } = {}
) {
  if (!state.liveListening) {
    return false;
  }
  try {
    const response = await fetch("/live/config", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `更新失败（HTTP ${response.status}）`);
    }
    applyLiveStatus(data);
    if (clearSummary) {
      renderAiSummary("");
    }
    if (clearQueue) {
      renderQueueEmpty("配置已更新，等待下一窗口或新弹幕");
      ui.queueMeta.textContent = "配置已更新";
    }
    return true;
  } catch (error) {
    showError(error.message || "更新实时监听配置失败");
    return false;
  }
}

function refreshAfterProductChange() {
  if (state.liveListening) {
    const auto = ui.liveAuto.checked;
    updateLiveConfig(
      { product: buildProduct() },
      { clearQueue: auto, clearSummary: true }
    ).then((ok) => {
      if (!ok) {
        return;
      }
      if (auto) {
        runLiveAnalysis();
      } else {
        ui.queueMeta.textContent = "商品已更新 · 自动刷新已暂停";
        ui.liveWindowHint.textContent = "商品已更新；点“立即分析本窗口”刷新队列";
      }
    });
  } else if (state.mode === "replay") {
    runAnalysis();
  }
}

async function startLive() {
  if (!state.scene) {
    showError("场景尚未载入，无法启动实时监听。");
    return;
  }
  hideError();
  resetLiveFeed();
  state.lastLiveEventId = 0;
  state.lastAnalysisAt = 0;
  ui.liveStart.disabled = true;

  const payload = buildPayload();
  const body = {
    source: ui.liveSource.value,
    elapsed_seconds: payload.live_state.elapsed_seconds,
    planned_seconds: payload.live_state.planned_seconds,
    target_stage: ui.liveStage.value || null,
    auto_analyze: ui.liveAuto.checked,
    product: payload.product,
  };

  try {
    const response = await fetch("/live/start", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `启动失败（HTTP ${response.status}）`);
    }
    applyLiveStatus(data);
  } catch (error) {
    setLiveState("error", error.message || "实时监听启动失败");
    showError(error.message || "实时监听启动失败");
  } finally {
    ui.liveStart.disabled = false;
  }
}

async function stopLive() {
  try {
    const response = await fetch("/live/stop", {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    if (response.ok) {
      applyLiveStatus(await response.json());
    }
  } catch (error) {
    showError("停止监听失败，请检查服务状态。");
  }
}

async function runLiveAnalysis() {
  if (!state.liveListening) {
    showError("请先开始实时监听。");
    return;
  }
  ui.runBtn.disabled = true;
  try {
    const response = await fetch("/live/analyze", {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `分析失败（HTTP ${response.status}）`);
    }
    if (data.analysis) {
      applyLiveAnalysis(
        data.analysis,
        0,
        data.window_seconds,
        data.at
      );
    } else {
      ui.queueMeta.textContent = "本窗口暂无弹幕";
      ui.liveWindowHint.textContent = "本窗口暂无弹幕";
    }
  } catch (error) {
    showError(error.message || "实时分析失败");
  } finally {
    ui.runBtn.disabled = false;
  }
}

function setMode(mode) {
  state.mode = mode;
  const isLive = mode === "live";
  ui.modeReplay.setAttribute("aria-pressed", String(!isLive));
  ui.modeLive.setAttribute("aria-pressed", String(isLive));
  ui.replayFields.hidden = isLive;
  ui.livePanel.hidden = !isLive;
  ui.queueAutoWrap.hidden = !isLive;
  ui.resetBtn.hidden = isLive;
  ui.runLabel.textContent = isLive ? "立即分析本窗口" : "生成提词建议";
  ui.modeNote.textContent = isLive
    ? "实时监听：在下方选择阶段，并用“自动刷新提词队列”控制队列是否随 10 秒窗口更新。"
    : "场景回放：拖动进度或用“阶段指令”切换阶段；自动刷新提词队列只在实时监听中可用。";
  hideError();

  if (isLive) {
    connectLiveStream();
    refreshLiveStatus();
  } else {
    closeLiveStream();
  }
}

async function bootstrap() {
  renderQueueEmpty("正在载入演示场景…");
  try {
    const response = await fetch("/demo/bootstrap", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`演示配置加载失败（HTTP ${response.status}）`);
    }
    const data = await response.json();
    state.stages = Array.isArray(data.stages) ? data.stages : [];
    state.scenes = Array.isArray(data.scenes) ? data.scenes : [];
    state.products = Array.isArray(data.products) ? data.products : [];
    if (!state.scenes.length) {
      throw new Error("没有可用的示例场景");
    }
    renderLiveStageOptions();
    renderProductOptions();
    renderTimeline(null);
    selectScene(state.scenes[0].id, false);
    await runAnalysis();
  } catch (error) {
    setStatus("error", "加载失败");
    showError(error.message || "无法加载演示配置");
    renderQueueEmpty("演示配置加载失败，请确认服务已启动。");
  }
}

ui.runBtn.addEventListener("click", () => {
  if (state.mode === "live") {
    runLiveAnalysis();
  } else {
    runAnalysis();
  }
});
ui.resetBtn.addEventListener("click", () => {
  if (!state.sceneId || state.mode !== "replay") {
    return;
  }
  selectScene(state.sceneId, false);
  runAnalysis();
});
ui.elapsed.addEventListener("input", updateElapsedLabel);
ui.elapsed.addEventListener("change", () => {
  if (state.mode === "replay") {
    runAnalysis();
  }
});
ui.directive.addEventListener("change", () => {
  if (state.mode === "replay") {
    runAnalysis();
  }
});
ui.comments.addEventListener("input", updateCommentCount);

ui.modeReplay.addEventListener("click", () => setMode("replay"));
ui.modeLive.addEventListener("click", () => setMode("live"));
ui.liveStart.addEventListener("click", startLive);
ui.liveStop.addEventListener("click", stopLive);
ui.liveStage.addEventListener("change", () => {
  if (!state.liveListening) {
    return;
  }
  const auto = ui.liveAuto.checked;
  updateLiveConfig(
    { target_stage: ui.liveStage.value },
    { clearQueue: auto, clearSummary: true }
  ).then((ok) => {
    if (!ok) {
      return;
    }
    if (auto) {
      runLiveAnalysis();
    } else {
      ui.queueMeta.textContent = "阶段已更新 · 自动刷新已暂停";
      ui.liveWindowHint.textContent = "阶段已更新；点“立即分析本窗口”刷新队列";
    }
  });
});

async function applyAutoRefresh(enabled) {
  ui.liveAuto.checked = enabled;
  ui.queueAuto.checked = enabled;
  if (!state.liveListening) {
    ui.liveWindowHint.textContent = enabled
      ? "开始监听后将自动刷新提词队列"
      : "开始监听后队列保持不动，需手动分析";
    return;
  }
  const ok = await updateLiveConfig(
    { auto_analyze: enabled },
    { clearQueue: false, clearSummary: false }
  );
  if (!ok) {
    ui.liveAuto.checked = !enabled;
    ui.queueAuto.checked = !enabled;
    return;
  }
  if (enabled) {
    runLiveAnalysis();
  } else {
    ui.queueMeta.textContent = "自动刷新已暂停";
    ui.liveWindowHint.textContent = "自动刷新已暂停；点“立即分析本窗口”更新队列";
  }
}

ui.liveAuto.addEventListener("change", () => {
  applyAutoRefresh(ui.liveAuto.checked);
});
ui.queueAuto.addEventListener("change", () => {
  applyAutoRefresh(ui.queueAuto.checked);
});

for (const input of [ui.productName, ui.productSpec, ui.productPrice]) {
  input.addEventListener("input", updateProductSummary);
}
for (const input of [
  ui.productName,
  ui.productSpec,
  ui.productPrice,
  ui.productIngredients,
  ui.productBenefits,
]) {
  input.addEventListener("change", () => {
    if (state.liveListening) {
      refreshAfterProductChange();
    }
  });
}

ui.productPreset.addEventListener("change", () => {
  const sku = ui.productPreset.value;
  if (state.scene && state.scene.product) {
    state.scene.product.sku_id = sku;
  }
  if (!sku) {
    refreshAfterProductChange();
    return;
  }
  const product = state.products.find((item) => item.sku_id === sku);
  if (!product) {
    return;
  }
  ui.productName.value = product.name || "";
  ui.productSpec.value = product.specification || "";
  ui.productPrice.value =
    product.price === null || product.price === undefined ? "" : String(product.price);
  ui.productIngredients.value = Array.isArray(product.ingredients)
    ? product.ingredients.join("，")
    : "";
  ui.productBenefits.value = Array.isArray(product.benefits)
    ? product.benefits.join("，")
    : "";
  updateProductSummary();
  refreshAfterProductChange();
});

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    if (state.mode === "live") {
      runLiveAnalysis();
    } else {
      runAnalysis();
    }
  }
});

setMode("replay");
bootstrap();
