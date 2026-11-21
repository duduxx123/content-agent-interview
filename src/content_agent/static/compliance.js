const riskLabels = {
  high_review: "高风险",
  review: "需核验",
};

const state = {
  data: null,
  risk: "",
  query: "",
};

const ui = {
  search: document.getElementById("rules-search"),
  filters: document.getElementById("rules-filters"),
  groups: document.getElementById("rules-groups"),
  count: document.getElementById("rules-count"),
  notice: document.getElementById("rules-notice"),
  empty: document.getElementById("rules-empty"),
  statTerms: document.getElementById("stat-terms"),
  statGroups: document.getElementById("stat-groups"),
  statHigh: document.getElementById("stat-high"),
};

function makeRiskBadge(risk) {
  const badge = document.createElement("span");
  badge.className = "risk-badge";
  badge.dataset.risk = risk;
  badge.textContent = riskLabels[risk] || "需复核";
  return badge;
}

function renderStats(data) {
  const groups = Array.isArray(data.groups) ? data.groups : [];
  const terms = groups.flatMap((group) => group.terms || []);
  const highTerms = groups
    .filter((group) => group.risk_level === "high_review")
    .flatMap((group) => group.terms || []);
  ui.statTerms.textContent = String(new Set(terms).size);
  ui.statGroups.textContent = String(groups.length);
  ui.statHigh.textContent = String(new Set(highTerms).size);
  ui.notice.textContent = data.notice || "";
}

function renderGroup(group, terms) {
  const section = document.createElement("section");
  section.className = "rules-group";

  const head = document.createElement("div");
  head.className = "rules-group-head";

  const title = document.createElement("h2");
  title.textContent = group.category || "未分类";
  const count = document.createElement("span");
  count.className = "rules-group-count";
  count.textContent = `${terms.length} 条`;
  head.append(title, count, makeRiskBadge(group.risk_level));

  const replacement = document.createElement("p");
  replacement.className = "rules-replacement";
  replacement.textContent = `替代方向：${group.replacement || "按商品资料重新表述。"}`;

  const grid = document.createElement("div");
  grid.className = "rules-term-grid";
  for (const term of terms) {
    const item = document.createElement("article");
    item.className = "rules-term";
    const name = document.createElement("strong");
    name.textContent = term;
    item.append(name, makeRiskBadge(group.risk_level));
    grid.append(item);
  }

  section.append(head, replacement, grid);
  return section;
}

function render() {
  if (!state.data) {
    return;
  }
  const query = state.query.trim().toLowerCase();
  const groups = (state.data.groups || [])
    .map((group) => {
      const matchesRisk = !state.risk || group.risk_level === state.risk;
      const haystack = `${group.category || ""} ${group.replacement || ""}`.toLowerCase();
      const terms = (group.terms || []).filter((term) => {
        if (!matchesRisk) {
          return false;
        }
        return !query || String(term).toLowerCase().includes(query) || haystack.includes(query);
      });
      return { group, terms };
    })
    .filter((entry) => entry.terms.length > 0);

  ui.groups.replaceChildren();
  for (const entry of groups) {
    ui.groups.append(renderGroup(entry.group, entry.terms));
  }

  const total = groups.reduce((sum, entry) => sum + entry.terms.length, 0);
  const riskText = state.risk ? riskLabels[state.risk] : "全部等级";
  ui.count.textContent = query
    ? `搜索“${state.query.trim()}” · ${riskText} · ${total} 条`
    : `${riskText} · ${total} 条`;
  ui.empty.textContent = "没有匹配的词条，换个关键词试试。";
  ui.empty.hidden = total > 0;
}

async function load() {
  try {
    const response = await fetch("/compliance/rules", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.data = await response.json();
    renderStats(state.data);
    render();
  } catch (error) {
    ui.count.textContent = "词库加载失败";
    ui.notice.textContent = "请确认服务已启动，然后刷新页面。";
    ui.groups.replaceChildren();
    ui.empty.hidden = false;
    ui.empty.textContent = "合规词库暂时不可用。";
  }
}

ui.search.addEventListener("input", () => {
  state.query = ui.search.value;
  render();
});

ui.filters.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-risk]");
  if (!button) {
    return;
  }
  state.risk = button.dataset.risk || "";
  for (const item of ui.filters.querySelectorAll("button[data-risk]")) {
    item.setAttribute("aria-pressed", String(item === button));
  }
  render();
});

load();
