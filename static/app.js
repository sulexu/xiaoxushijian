/* ⚠ 原来这里（第 1 ~ 865 行）是基础设施那一段：$, esc, money,
 *   colorOf/hslOf、toast/busy/modal、ICON/paintIcons、applyTheme/applyBg、
 *   buildChartTheme、emptyBox/gcard/kpi 等等。
 *   为了让这个文件短一点，整段搬去了 **static/core.js**（函数体一个字没改）。
 *   那边必须比这里先加载 —— 见 index.html 里的顺序。
 *   ⚠ 别在这里重新定义同名函数：JS 是后定义者胜、而且**不报错**，
 *     会静默盖掉 core.js 里的那个。（copyText 就这么被盖过一次。） */

function renderOverview() {
  const t = todayStr();
  const b = BILL.kpi;
  const td = todayDayObj();
  const ts = td ? dayStats(td, CHECK.settings) : null;
  const mo = curCheckMonth();
  // ⚠ 只统计**到今天为止**的日子。整月 30 天里后面那 14 天一格没填，
  //   算进平均就是拿 0 去稀释完成率 —— 月初打开一看「本月完成率 15%」，
  //   以为是自己的问题，其实是分母把未来的日子也算上了。
  const _td = todayStr();
  const mDays = mo ? mo.days.filter(d => (d.date || '') <= _td)
    .map(d => dayStats(d, CHECK.settings)) : [];
  const mCore = mDays.length ? mDays.reduce((a, x) => a + x.core, 0) / mDays.length : 0;
  const monthExp = BILL.months.find(x => x.m === monthNameOf(t).slice(-3).replace("年",""))?.exp;
  // ⚠ 用 eff_budget（算上预算结转的）而不是 budget（表里填的那个）。
  //   关掉结转时后端返回的两个数是一样的，所以不用在这边判断开关。
  const _mo = BILL.months.find(x => x.m === `${+t.slice(5,7)}月`);
  const monthBudget = _mo ? (_mo.eff_budget != null ? _mo.eff_budget : _mo.budget) : undefined;
  const mom = monthlySpendCompare(t);          // 支出环比（2.4.7）
  const restock = STOCK.overview.reduce((a, v) => a + v.restock, 0);
  const bad = STOCK.overview.reduce((a, v) => a + v.expired + v.soon, 0);
  const todoOpen = STOCK.todo.filter(x => x.stat !== "已完成").length;
  const overdueTails = BILL.tails.filter(x => x.stat === "待付" && x.days !== null && x.days < 0);
  const overdueTodo = STOCK.todo.filter(x => x.stat !== "已完成" && x.days !== null && x.days < 0);
  const dreamN = (CHECK.dream_detail[t] || []).length;
  // 哪几张卡显示由设置里的 overview_cards 决定；空 = 全显示（见 bindPersonal 里的说明）
  const overCards = cfg("overview_cards", []) || [];
  const showCard = k => !overCards.length || overCards.includes(k);

  $("#tab-over").innerHTML = `
  <div class="hero">
    <h1>${ICON.home} 今天 · ${t} 星期${WEEK[new Date(t).getDay()]}</h1>
    ${quickNoteCard()}
    <div class="hstats" id="hero-stats">${heroStats()}</div>
  </div>

  ${(CARD_HTML = cardHtmlMap(b, monthExp, monthBudget, dreamN, td, restock, bad, todoOpen, overdueTodo, mom)) && ""}
  <div class="kpis">
    ${cardOrder().filter(showCard).map(k => CARD_HTML[k] || "").join("")}
  </div>

  <div class="grid2 grid grid-cols-1 min-[860px]:grid-cols-2 gap-4">
    <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><h2 class="sec" style="margin-top:0">${ICON.check} 今日快速打卡</h2>${quickCheckCard(td)}</div>
    <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><h2 class="sec" style="margin-top:0">${ICON.bell} 提醒</h2>${alertCard(overdueTails, overdueTodo, restock, bad)}</div>
  </div>

  <details class="aifold"${AIANALYSIS && Object.keys(AIANALYSIS).length ? " open" : ""}>
  <summary>${ICON.robot} AI 分析 <span class="mini">每周自动看一次；想立刻看就点开</span></summary>
  <div class="grid2 grid grid-cols-1 min-[860px]:grid-cols-2 gap-4">
    ${analyzeCard("all",   "chart",  "整体",   "钱、作息、物资三条线的体检")}
    ${analyzeCard("bill",  "wallet", "账单",   "花销结构是否健康")}
    ${analyzeCard("check", "check",  "打卡",   "生活习惯怎么样")}
    ${analyzeCard("stock", "box",    "物资管家", "缺什么、重了什么、先用什么")}
  </div>
  <div class="aifold-foot"><button class="btn ghost sm" id="ai-run-all">重新分析全部</button></div>
  </details>`;
  setTimeout(() => {
    $$(".goto").forEach(c => c.onclick = () => switchTab(c.dataset.goto));
    bindQuickCheck(td);
    bindQuickNote();
    bindAnalyze();
    maybeAutoAnalyze();
  }, 0);
}
/* ---- 总览 AI 分析 ---- */
const ANALYZE_META = {all:"整体", bill:"账单", check:"打卡", stock:"物资管家"};
function analyzeCard(scope, icon, title, hint) {
  const r = (AIANALYSIS || {})[scope];
  const body = r
    ? `<div class="ai-text">${esc(r.text).replace(/\n/g, "<br>")}</div>
       <div class="mini" style="margin-top:8px">${esc(r.time)} · ${esc(r.model || "")}${
         r.tokens ? " · " + r.tokens + " tokens" : ""}</div>`
    : `<p class="mini">还没生成过。点下面按钮让 AI 看一眼（会消耗一点额度）。</p>`;
  return `<div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><h2 class="sec" style="margin-top:0">${ICON[icon] || ""} ${title}
      <button class="btn ghost sm" data-ai-run="${scope}" style="float:right">${r?"重新分析":"生成"}</button></h2>
    <div class="mini" style="margin-bottom:8px">${hint}</div>${body}</div>`;
}
function bindAnalyze() {
  $$("#tab-over [data-ai-run]").forEach(btn => btn.onclick = () => runAnalyze(btn.dataset.aiRun, btn));
  const all = $("#ai-run-all");
  if (all) all.onclick = async () => {
    for (const s of ["all", "bill", "check", "stock"]) {
      await runAnalyze(s, null);
    }
  };
}
async function runAnalyze(scope, btn) {
  if (btn) { btn.disabled = true; btn.textContent = "分析中…"; }
  else toast("正在分析 " + (ANALYZE_META[scope] || scope) + " …");
  const r = await post("/api/ai/analyze", {scope, force: true});
  if (btn) { btn.disabled = false; btn.textContent = "重新分析"; }
  if (!r.ok) { toast(r.msg, true); return false; }
  AIANALYSIS = AIANALYSIS || {};
  AIANALYSIS[scope] = r.data;
  renderOverview();
  return true;
}
// 每周自动一次：距上次分析超过 7 天就悄悄跑一遍（失败静默，不打扰）
let _autoAnalyzing = false;
async function maybeAutoAnalyze() {
  if (_autoAnalyzing || !AICFG || !AICFG.has_key) return;
  const a = AIANALYSIS || {};
  const need = ["all", "bill", "check", "stock"].filter(s => {
    const r = a[s];
    if (!r || !r.time) return true;
    const days = (Date.now() - new Date(r.time.replace(/-/g, "/")).getTime()) / 86400000;
    return !(days >= 0 && days < 7);
  });
  if (!need.length) return;
  _autoAnalyzing = true;
  toast("已超过一周没分析，正在后台更新…");
  for (const s of need) {
    await runAnalyze(s, null);
  }
  _autoAnalyzing = false;
  toast("AI 分析已更新");
}
function avgSleepOf(m) {
  const sl = m.days.map(d => dayStats(d, CHECK.settings).sleepH).filter(v => v != null);
  return sl.length ? (sl.reduce((a,b)=>a+b,0)/sl.length).toFixed(1) + " h" : "—";
}
function alertCard(overdueTails, overdueTodo, restock, bad) {
  const lines = [];
  overdueTails.forEach(x => lines.push(`<div class="al r">${ICON.wallet} 尾款「${esc(x.name)}」已超期 ${-x.days} 天</div>`));
  overdueTodo.forEach(x => lines.push(`<div class="al a">${ICON.list} 待办「${esc(x.item)}」已逾期 ${-x.days} 天</div>`));
  if (restock) lines.push(`<div class="al a">${ICON.box} ${restock} 件物资需补货</div>`);
  if (bad) lines.push(`<div class="al r">⚠ ${bad} 件物资过期或临期</div>`);
  if (!lines.length) return '<div class="ok">✔ 今天没有需要处理的提醒</div>';
  return lines.join("");
}
function quickCheckCard(td) {
  if (!td) return '<p class="mini">本月的打卡表还没生成，等系统自动建好再来</p>';
  // 快速打卡的按钮**从打卡项表里来**，不写死列号 ——
  // 以前这里硬编码 Q/R/S/T/U，用户改了名字或加了项这儿纹丝不动。
  // 2.3.3 起顺序和取舍也由设置说了算（见 quickOrder / quickShow）。
  const byCol = {};
  checkItems("core").forEach(x => { byCol[x.col] = x; });
  const show = quickShow();
  const core = quickOrder().filter(c => show.includes(c)).map(c => byCol[c]).filter(Boolean);
  const st = dayStats(td, CHECK.settings);
  return `<div class="quick">
    ${core.map(x => {
      const v = td[x.col];
      const sub = v || "";
      return `<button class="tickbtn big ${v==="√"?"yes":(v==="×"?"no":"")}"
        data-qc="${esc(x.col)}" data-sauto="false">${esc(x.name)} ${esc(sub)}</button>`;
    }).join("")}
    <button class="tickbtn big ${st.S==="√"?"yes":(st.S==="×"?"no":"")}"
      data-sauto="true" title="由「小睡(min)」自动判：0 = 没小睡（不达标）">小睡≤30 ${
      +td.L === 0 ? "没小睡" : (st.S || "")}</button>
    <div class="quick2">
      <label>心情</label>
      <select id="q-mood" data-qm>${[""].concat(CHECK.opts.mood).map(o=>`<option ${td.AF===o?"selected":""}>${o}</option>`).join("")}</select>
      <button class="btn ghost sm" id="q-nonap"
        title="今天没小睡：记为 0 分钟，「小睡≤30」判为不达标（扣分）">${ICON.moon} 没小睡</button>
      <span class="mini">改动即存</span>
    </div>
  </div>`;
}
function bindQuickCheck(td) {
  if (!td) return;
  const m = curCheckMonth();
  $$("[data-qc]", $("#tab-over")).forEach(btn => btn.onclick = () => {
    if (btn.dataset.sauto === "true") { toast("小睡≤30 由「小睡(min)」自动推，去打卡页改"); return; }
    const c = btn.dataset.qc, cur = td[c];
    const next = cur === "√" ? "×" : (cur === "×" ? "" : "√");
    btn.textContent = btn.textContent.split(" ")[0] + " " + next;
    btn.className = "tickbtn big " + (next==="√"?"yes":(next==="×"?"no":""));
    post("/api/check/set", {sheet: m.name, day: td.day, col: c, value: next}).then(r => {
      if (r.ok) { td[c] = next; toast(r.msg); refreshHeroStats(); } else toast(r.msg, true);
    });
  });
  $("#q-mood").addEventListener("change", async () => {
    const r = await post("/api/check/set", {sheet: m.name, day: td.day, col: "AF", value: $("#q-mood").value});
    if (r.ok) { td.AF = $("#q-mood").value; toast(r.msg); } else toast(r.msg, true);
  });
  const na = $("#q-nonap");
  if (na) na.onclick = async () => {
    busy();
    const r = await post("/api/check/set", {sheet: m.name, day: td.day, col: "L", value: 0});
    if (!r.ok) return toast(r.msg, true);
    toast("已记为没小睡（小睡≤30 判不达标）");
    // 就地改，不整页重拉 —— 重拉会把「今天」跳回顶部，也会把没提交的输入冲掉
    td.L = 0;
    const s = $$("[data-qc]", $("#tab-over")).find(b => b.dataset.qc === "S");
    if (s) { s.textContent = s.textContent.split(" ")[0] + " 没小睡"; s.className = "tickbtn big no"; }
    refreshHeroStats();
    markDirty("check");                 // 打卡页那边得重新拉一次
  };
}
// 空状态统一成一个样子：主句说「这里现在是空的」，副句说「怎么让它有东西」。
// 以前各处写法不一（有的只有一句话、有的是纯空白），扫过去不知道是没数据还是加载挂了。
function emptyBox(main, hint) {
  return `<div class="empty"><div class="e-main">${main}</div>${
    hint ? `<div class="e-hint">${hint}</div>` : ""}</div>`;
}

// 简约风的一个关键点：**颜色要留给"有情况"**。
// 六张卡配六种颜色看着热闹，但那样一来「待补货 0 件」也在喊，
// 真出问题时反而不显眼。所以平时一律中性色，只有异常才上色。
const NEUTRAL = "var(--line)";
const RED = "var(--red)";
const AMBER = "var(--amber)";

/* ---------------- 线条图标（自己写的 SVG，无外部依赖）----------------
   统一规格：24×24 视框、只用描边不用填充、圆头圆角，跟着 currentColor 走。
   自己写而不是引第三方图标库，是因为一共就用十来个，与其为了它们拖进一整个
   依赖、还得处理授权，不如把这几个几何形状直接写出来（都是直线和方框）。 */
const SVG = (d, extra) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="ic"${extra || ""}>${d}</svg>`;
const ICON = {
  minus: SVG('<path d="M5 12h14"/>'),
  square: SVG('<rect x="6" y="6" width="12" height="12" rx="2"/>'),
  x: SVG('<path d="M6 6l12 12M18 6L6 18"/>'),
  camera: SVG('<path d="M4 8h3l1.5-2h7L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.2"/>'),
  lock: SVG('<rect x="4.5" y="10" width="15" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>'),
  sun: SVG('<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"/>'),
  monitor: SVG('<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M9 21h6M12 17v4"/>'),
  refresh: SVG('<path d="M20 11a8 8 0 1 0-2.3 6.3"/><path d="M20 4v7h-7"/>'),
  user: SVG('<circle cx="12" cy="8.2" r="3.6"/><path d="M4.8 20.2a7.4 7.4 0 0 1 14.4 0"/>'),
  image: SVG('<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><circle cx="8.6" cy="10" r="1.6"/><path d="M4 17l4.8-4.6 3.4 3.2 3-2.8L20 16"/>'),
  folder: SVG('<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2l1.8 2.2h8A2.5 2.5 0 0 1 21 9.7v7.8A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>'),
  pencil: SVG('<path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17z"/><path d="M14.5 6.5 17.5 9.5"/>'),
  quote: SVG('<path d="M9.5 6.5C6.9 7.6 5.5 9.9 5.5 13.2V18h5.2v-5.2H8.2c0-2 .9-3.3 2.6-3.9z"/><path d="M18.5 6.5c-2.6 1.1-4 3.4-4 6.7V18h5.2v-5.2h-2.5c0-2 .9-3.3 2.6-3.9z"/>'),
  home: SVG('<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h14V9.5"/>'),
  wallet: SVG('<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18"/><circle cx="16.5" cy="14" r="1"/>'),
  check: SVG('<path d="M4 12.5 9.5 18 20 6.5"/>'),
  box: SVG('<path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5 12 12l8.5-4.5M12 12v9"/>'),
  book: SVG('<path d="M5 4.5h9.5a3 3 0 0 1 3 3V21H8a3 3 0 0 1-3-3z"/><path d="M5 18a3 3 0 0 1 3-3h9.5"/>'),
  sparkle: SVG('<path d="M12 3.5 13.8 9 19 10.8 13.8 12.6 12 18l-1.8-5.4L5 10.8 10.2 9z"/><path d="M18.5 16.5 19.2 18.8 21.5 19.5 19.2 20.2 18.5 22.5 17.8 20.2 15.5 19.5 17.8 18.8z"/>'),
  gear: SVG('<circle cx="12" cy="12" r="3.2"/><path d="M12 2.8v2.4M12 18.8v2.4M4.6 7.4l2 1.2M17.4 15.4l2 1.2M4.6 16.6l2-1.2M17.4 8.6l2-1.2"/>'),
  print: SVG('<path d="M7 9V4h10v5"/><rect x="4" y="9" width="16" height="7" rx="2"/><path d="M7 14h10v6H7z"/>'),
  bell: SVG('<path d="M6.5 9.5a5.5 5.5 0 0 1 11 0c0 5 1.5 6 1.5 6H5s1.5-1 1.5-6z"/><path d="M10 19a2 2 0 0 0 4 0"/>'),
  list: SVG('<path d="M9 6.5h11M9 12h11M9 17.5h11"/><circle cx="4.6" cy="6.5" r="1.1"/><circle cx="4.6" cy="12" r="1.1"/><circle cx="4.6" cy="17.5" r="1.1"/>'),
  chart: SVG('<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 20v-6M12.7 20V8.5M17.4 20v-9"/>'),
  cart: SVG('<circle cx="9.5" cy="19" r="1.4"/><circle cx="17.5" cy="19" r="1.4"/><path d="M3 4h2.2l2.4 11h11.2l2-8H6"/>'),
  bank: SVG('<path d="M3.5 9.5 12 4l8.5 5.5"/><path d="M5.5 9.5V19M10 9.5V19M14 9.5V19M18.5 9.5V19"/><path d="M3.5 19h17"/>'),
  gift: SVG('<rect x="3.5" y="9" width="17" height="11" rx="2"/><path d="M3.5 13h17M12 9v11"/><path d="M12 9S9.5 4 7.5 5.2 9 9 12 9s4.5-2.6 2.5-3.8S12 9 12 9z"/>'),
  moon: SVG('<path d="M20 14.5A8.2 8.2 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z"/>'),
  smile: SVG('<circle cx="12" cy="12" r="8.5"/><path d="M8.8 14.2a4 4 0 0 0 6.4 0"/><path d="M9.2 9.8h.01M14.8 9.8h.01"/>'),
  run: SVG('<circle cx="14.5" cy="5" r="1.8"/><path d="M12.5 21 14 15l-3.5-2 1-4.5 3 2 3 .5"/><path d="M11.5 8.5 8 10.5l-1 3"/>'),
  tag: SVG('<path d="M4 10.5V5a1 1 0 0 1 1-1h5.5L20 13.5 13.5 20z"/><circle cx="8" cy="8" r="1.2"/>'),
  save: SVG('<path d="M5 4h11l3 3v13H5z"/><path d="M8.5 4v5h7V4"/><rect x="8.5" y="13" width="7" height="7"/>'),
  trash: SVG('<path d="M4.5 7h15"/><path d="M9 7V4.5h6V7"/><path d="M6.5 7l1 13h9l1-13"/><path d="M10.5 11v5M13.5 11v5"/>'),
  calendar: SVG('<rect x="3.5" y="5.5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8.5 3.5v4M15.5 3.5v4"/>'),
  robot: SVG('<rect x="4.5" y="8" width="15" height="11" rx="3"/><circle cx="9.5" cy="13" r="1.2"/><circle cx="14.5" cy="13" r="1.2"/><path d="M12 8V4.5M9 19.5v1.5M15 19.5v1.5"/>'),
  shield: SVG('<path d="M12 3.5 19 6v6c0 4.5-3 7.5-7 8.5-4-1-7-4-7-8.5V6z"/><path d="M9.5 12.2l1.8 1.8 3.4-3.6"/>'),
  palette: SVG('<path d="M12 3.5a8.5 8.5 0 0 0 0 17c1.4 0 2-.9 2-1.8 0-1.4-1.3-1.7-1.3-2.7 0-.8.7-1.5 1.6-1.5h1.4a4.8 4.8 0 0 0 4.8-4.8c0-3.4-3.6-6.2-8.5-6.2z"/><circle cx="8" cy="10" r="1.1"/><circle cx="12" cy="7.8" r="1.1"/><circle cx="16" cy="10" r="1.1"/>'),
  info: SVG('<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8h.01"/>'),
  wrench: SVG('<path d="M15.5 8.5a4 4 0 1 0-5 5L5 19l1.5 1.5 5.5-5.5a4 4 0 0 0 5-5l-2.4 2.4-2.1-.6-.6-2.1z"/>'),
  book2: SVG('<path d="M4 5.5h6a3 3 0 0 1 3 3V20a2.5 2.5 0 0 0-2.5-2.5H4z"/><path d="M20 5.5h-6a3 3 0 0 0-3 3V20a2.5 2.5 0 0 1 2.5-2.5H20z"/>'),
  alert: SVG('<path d="M12 4.5 21 19.5H3z"/><path d="M12 10v4M12 17h.01"/>'),
  // 品牌标：三根纸简，跟应用图标同一母题
  clock: SVG('<circle cx="12" cy="12" r="8.2"/><path d="M12 7.4V12l3.1 1.9"/>'),
  logo: SVG('<rect x="4" y="6" width="16" height="13" rx="2.5"/><path d="M8.5 10.5v4M12 9.5v5.5M15.5 8.5v6.5"/>'),
};

function kpi(lab, num, cls, accent, sub, go) {
  /* ⚠ 2.5.1 起这里**同时**挂着旧类（kpi/lab/num/sub）和 Tailwind 原子类。
     为什么不是直接换成 Tailwind：项目有 342 项前端测试盯着这些类名和结构，
     一次性换掉会同时动到样式和测试。**先并存、跑通、再删旧的**，风险最低。
     Tailwind 的原子类在 `@layer utilities` 里，而老 CSS 是未分层的 ——
     按理未分层的赢，但这里**两边写的是同一组属性**（flex 布局），
     实测生效的是 Tailwind 那组（见 前端重写方案.md 里那张实验表）。 */
  return `<div class="kpi${go ? " goto" : ""} flex flex-col" style="--accent:${accent}"${
    go ? ` data-goto="${go}" title="点击进入"` : ""}><div class="lab">${lab}</div>
    <div class="num ${cls}">${num}</div>${
    sub ? `<div class="sub mt-auto pt-1">${sub}</div>` : ""}</div>`;
}

/* ================================================================
   ② 账单
================================================================ */
async function loadBill() {
  // 账单页要显示「这是哪个学期的合计」，所以顺手把学期名也取回来。
  // ⚠ 两个请求并发，别串行 —— 串起来账单页会慢一拍。
  //   SEMS 取不到也不影响账单：下面取值处有兜底。
  const [r] = await Promise.all([get("/api/bill"), fetchSemesters()]);
  if (!r.ok) return toast(r.msg, true);
  BILL = r.data;
  clearDirty("bill"); syncStamp();
  idle();
  renderBill();
}
/** 汇总区那句话：这一屏的数字到底覆盖哪一段时间。
 *  ⚠ 用户要的是「学期维度汇总」（2.4.7）。但底下那六张卡**本来就是这个学期的合计** ——
 *    BILL 是按学期加载的，`kpi.inc/exp` 全是本学期口径。
 *    所以这里不需要新算一个数，需要的是**把这个口径写出来**：
 *    原来那行只写「汇总」两个字，用户没法知道它算的是这个月还是这个学期。
 *    多算一个同样的数摆上去，只会变成第四个「同一个数算两遍」的坑。 */
function semScopeNote(b) {
  const name = (SEMS && SEMS.current) || "";
  const ds = (b.records || []).map(r => String(r.date || "")).filter(Boolean).sort();
  const from = ds[0], to = ds[ds.length - 1];
  const range = from ? (from === to ? from : `${from} ~ ${to}`) : "";
  const bits = [];
  if (name) bits.push(`<b>${esc(name)}</b>`);
  if (range) bits.push(range);
  bits.push(`共 ${b.records.length} 条流水`);
  // 没有流水时不写「合计 0」—— 说清是还没记，不是记了等于 0
  if (!from) bits.push("（这个学期还没有流水，下面几个数都是 0，不是丢了数据）");
  return bits.join(" · ");
}

function renderBill() {
  const b = BILL, k = b.kpi;
  recLimit = recPageSize;        // 整页重渲染时回到用户选的每页条数
  $("#tab-bill").innerHTML = `
  <div class="pagehead">
    <div class="ph-title">${ICON.wallet} 账单</div>
    <div class="ph-sub">${(SEMS && SEMS.current) || "大二上"} · 共 ${b.records.length} 条 ·
      数据存在数据库里</div>
    <div class="ph-actions">
      <button class="btn ghost sm" id="shot-bill">${ICON.sparkle} 从截图记账</button>
    </div>
  </div>
  <h2 class="sec">${ICON.list} 流水明细 <span class="mini">（退回的行灰掉，不计入统计）</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <details open><summary>＋ 记一笔</summary>${billForm()}</details>
    <div id="tpl-bar" style="margin-top:10px"></div>
    <div style="height:12px"></div>
    <div id="rec-box">${recordsBox()}</div>
  </div>
  <h2 class="sec">${ICON.chart} 这个月花了多少 <span class="mini">（一天一格，点格子跳到那天）</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="bill-cal"></div>
  <h2 class="sec">${ICON.refresh} 订阅与定期扣款 <span class="mini">（每月自动要扣的钱）</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="sub-card"></div>
  <h2 class="sec">${ICON.cart} 团购 / 核销 <span class="mini">（点状态即可切换）</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="group-cards">
      ${gcard("待核销（钱已付、券未用）", money(b.groups.wait), "var(--amber-d)")}
      ${gcard("已核销（已用掉）", money(b.groups.done), "var(--green-d)")}
      ${gcard("计入支出的团购合计", money(b.groups.wait + b.groups.done), "var(--txt)")}
      ${gcard("已退回（不计入统计）", money(b.groups.back), "var(--red-d)")}
    </div>
    ${b.groups.rows.length ? `<table><thead><tr><th>项目</th><th>日期</th><th>金额</th><th>核销状态</th></tr></thead><tbody>
      ${b.groups.rows.map(g=>`<tr class="${g.stat==="退回"?"voidrow":""}"><td>${esc(g.name)}</td><td>${g.date}</td>
        <td class="num">${money(g.amt)}</td><td>${statPicker(g)}</td></tr>`).join("")}</tbody></table>`
      : emptyBox("还没有登记团购", "记流水时把「是否团购」选「是」，这里就会列出来")}
  </div>
  <h2 class="sec">${ICON.bank} 资金账户结余</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <table><thead><tr><th>账户</th><th class="num">存入</th><th class="num">花出</th><th class="num">结余</th></tr></thead><tbody>
      ${b.accounts.map(a=>`<tr><td>${a.name}</td><td class="num g">${money(a.inc)}</td>
        <td class="num r">${money(a.exp)}</td><td class="num ${a.bal>=0?"b":"r"}"><b>${money(a.bal)}</b></td></tr>`).join("")}
    </tbody></table>
  </div>
  <h2 class="sec">${ICON.gift} 周边尾款计划</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    ${cashflowBox()}
    ${tailTable()}
    <details><summary>＋ 登记一笔新尾款</summary>${tailForm()}</details>
  </div>
  <h2 class="sec">${ICON.chart} 汇总 <span class="mini">（下面这几个数是**这个学期**的合计，不是这个月）</span></h2>
  <div class="mini" style="margin:-4px 0 8px">${semScopeNote(b)}</div>
  <div class="kpis">
    ${kpi("总收入", money(k.inc), "g", "var(--green)",
      k.opening ? `含期初余额 ${money(k.opening)} · 和你账本上的「收入合计」对得上`
                : `${Object.keys(b.inc_cat).length} 类来源`)}
    ${kpi("其中真正挣到", money(k.earned), "g", "var(--green)",
      `其余 ${money(k.opening)} 是开学时手里原有的钱`)}
    ${kpi("总支出", money(k.exp), "r", "var(--red)", `${b.records.length - k.void} 笔有效`)}
    ${kpi("结余", money(k.bal), k.bal>=0?"b":"r", "var(--blue)",
      (k.opening ? `总收入 ${money(k.inc)} − 支出 ${money(k.exp)}`
                 : `总收 ${money(k.inc)} / 总支 ${money(k.exp)}`))}
    ${kpi("待付周边尾款", money(k.pending), "a", "var(--amber)", `${b.tails.filter(t=>t.stat==="待付").length} 件待付`)}
    ${kpi("可动用资金", money(k.avail), k.avail>=0?"g":"r", "var(--violet)",
      (b.cashflow && b.cashflow.left_after_all < 0)
        ? `全部尾款付清后还差 ${money(-b.cashflow.left_after_all)}`
        : `全部尾款付清后剩 ${money((b.cashflow||{}).left_after_all || 0)}`)}
  </div>
  <div class="grid2 grid grid-cols-1 min-[860px]:grid-cols-2 gap-4">
    <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><h2 class="sec" style="margin-top:0">${ICON.chart} 支出类别</h2>
      <div class="chart" id="c-exp-pie"></div></div>
    <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><h2 class="sec" style="margin-top:0">${ICON.wallet} 收入类别
      ${k.opening ? `<span class="mini">（「结余」${money(k.opening)} 是期初余额，不是挣来的）</span>` : ""}</h2>
      <div class="chart" id="c-inc-pie"></div></div>
    <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><h2 class="sec" style="margin-top:0">${ICON.calendar} 每月收入 vs 支出</h2>
      <div class="chart" id="c-month-bar"></div></div>
    <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><h2 class="sec" style="margin-top:0">${ICON.chart} 每日支出趋势</h2>
      <div class="chart" id="c-day-line"></div></div>
  </div>
  <div class="foot">改动直接存进数据库，记完立刻生效，统计和图表跟着重算</div>`;
  bindRecords($("#rec-box"));
  bindBillForm(null);
  bindGroupStat();
  renderBillCharts();
  // ---- 2.3.6 加的三块：交易模板条 / 账单日历 / 订阅 ----
  renderTplBar();
  renderBillCal();
  renderSubCard();
}

/* ---- 交易模板（2.3.6）----
   常记的那几笔（食堂 15、公交 2）存成模板，点一下就填好表单。
   ⚠ 只**填**不提交 —— 填完用户自己看一眼再点保存。直接提交太危险：
     记错一笔要翻回去删，比多点一下烦得多。 */
async function renderTplBar() {
  const box = $("#tpl-bar");
  if (!box) return;
  const r = await post("/api/tpl/list", {});
  const list = (r.ok && r.data.tpls) || [];
  box.innerHTML = `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
    <span class="mini">常用：</span>
    ${list.map(t => `<button class="chip" data-tpluse="${t.id}"
      title="${esc([t.cat, t.amount ? "¥" + t.amount : "", t.note].filter(Boolean).join(" · "))}"
      >${esc(t.name)}</button>`).join("")}
    <button class="btn ghost sm" id="tpl-new">＋ 存当前这笔记法</button>
    ${list.length ? '<button class="btn ghost sm" id="tpl-edit">管理</button>' : ""}
  </div>`;
  $$("[data-tpluse]").forEach(b => b.onclick = () => {
    const t = list.find(x => x.id === b.dataset.tpluse);
    if (!t) return;
    // 表单里那几个框的 id 是固定的，直接写进去
    const put = (sel, v) => { const e = $(sel); if (e && v) e.value = v; };
    put("#b-amount", t.amount); put("#b-note", t.note);
    const cs = $("#b-cat"); if (cs && t.cat) cs.value = t.cat;
    const wp = $("#b-pay"); if (wp && t.pay) wp.value = t.pay;
    toast("填好了，看一眼再点保存");
    const a = $("#b-amount"); if (a) a.focus();
  });
  const nw = $("#tpl-new");
  if (nw) nw.onclick = async () => {
    // ⚠ 原来是 prompt() —— **Electron 16+ 已经移除 prompt**，
    //   打包版里点了完全没反应（用户报的就是这条）。改用自家的 askText()。
    const name = await askText({
      title: "给这笔记法起个名字", label: "名字", ph: "食堂",
      hint: "会把「记一笔」里现在填的内容存成一个按钮，以后点一下就能填好。"});
    if (name === null || !name.trim()) return;
    const g = s => { const e = $(s); return e ? e.value : ""; };
    const next = list.concat([{name: name.trim(), amount: g("#b-amount"),
      cat: g("#b-cat"), pay: g("#b-pay"), note: g("#b-note")}]);
    const w = await post("/api/tpl/save", {tpls: next});
    if (!w.ok) return toast(w.msg, true);
    toast("存好了"); renderTplBar();
  };
  const ed = $("#tpl-edit");
  if (ed) ed.onclick = async () => {
    if (!confirm("清空所有常用模板？")) return;
    await post("/api/tpl/save", {tpls: []});
    toast("已清空"); renderTplBar();
  };
}

/* ---- 账单日历（2.3.6）----
   一个月一屏，每格写当天花了多少。数据就是 BILL.day_exp，不用新接口。 */
function renderBillCal() {
  const box = $("#bill-cal");
  if (!box) return;
  const t = todayStr();
  const ym = t.slice(0, 7);
  const [y, m] = ym.split("-").map(Number);
  const first = new Date(y, m - 1, 1);
  const days = new Date(y, m, 0).getDate();
  const pad = (first.getDay() + 6) % 7;          // 周一开头
  const exp = (BILL && BILL.day_exp) || {};
  const vals = [];
  for (let i = 0; i < pad; i++) vals.push(null);
  for (let d = 1; d <= days; d++) {
    const key = `${ym}-${String(d).padStart(2, "0")}`;
    vals.push({ d, key, v: exp[key] || 0 });
  }
  const max = Math.max(1, ...vals.filter(Boolean).map(x => x.v));
  box.innerHTML = `
    <div class="gline2" style="border:0;padding-bottom:2px">
      <span class="mini">${y} 年 ${m} 月 · 全月 ${money(vals.reduce((a, x) => a + (x ? x.v : 0), 0))}</span>
      <span class="mini">最深的那天 ${money(max)}</span></div>
    <div class="bcal">
      ${["一", "二", "三", "四", "五", "六", "日"].map(w => `<i class="bw">${w}</i>`).join("")}
      ${vals.map(x => x === null ? "<i></i>" :
        `<i class="bd${x.v > 0 ? " has" : ""}${x.key === t ? " today" : ""}"
           style="--f:${x.v > 0 ? Math.max(.12, x.v / max) : 0}"
           title="${x.key} 花了 ${money(x.v)}">${x.d}${
           x.v > 0 ? `<b>${x.v >= 1000 ? (x.v / 1000).toFixed(1) + "k" : num2(x.v)}</b>` : ""}</i>`).join("")}
    </div>
    <p class="mini" style="margin-top:8px">格子里是当天花的钱。颜色越深花得越多 ——
      不是叫你省，是让「这个月钱去哪了」一眼看得见。</p>`;
}

/* ---- 订阅与定期扣款（2.3.6）----
   ⚠ 跟「周边尾款计划」不是一回事：尾款是一次性的，订阅是**每月循环**的。 */
async function renderSubCard() {
  const box = $("#sub-card");
  if (!box) return;
  const r = await post("/api/sub/list", {});
  const d = (r.ok && r.data) || {subs: [], monthly: 0, yearly: 0};
  box.innerHTML = `
    <div style="display:flex;gap:22px;align-items:baseline;margin-bottom:10px">
      <div><span class="mini">每月要扣</span> <b style="font-size:1.3em">${money(d.monthly)}</b></div>
      <div class="mini">一年 ${money(d.yearly)}</div>
    </div>
    ${d.subs.length ? d.subs.map(s => `<div class="gline2">
      <span>${esc(s.name)} <span class="mini">${s.cycle}付 · 每月 ${money(s.monthly)}</span></span>
      <span class="mini">下次 ${s.next}（${s.days === 0 ? "今天" : s.days + " 天后"}）
        · ${money(s.amount)}</span></div>`).join("")
      : '<p class="mini">还没有。话费、会员、房租这种每月固定要扣的，记在这儿。</p>'}
    <div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <input id="sub-name" placeholder="名称（话费）" style="width:130px">
      <input id="sub-amt" type="number" placeholder="金额" style="width:100px">
      <select id="sub-cyc"><option>月</option><option>季</option><option>年</option></select>
      <input id="sub-day" type="number" min="1" max="28" placeholder="每月几号扣" style="width:120px">
      <button class="btn sm" id="sub-add">添加</button>
      ${d.subs.length ? '<button class="btn ghost sm" id="sub-clr">清空</button>' : ""}
    </div>`;
  const add = $("#sub-add");
  if (add) add.onclick = async () => {
    const name = $("#sub-name").value.trim();
    if (!name) return toast("给它起个名字", true);
    const next = d.subs.concat([{name, amount: +$("#sub-amt").value || 0,
      cycle: $("#sub-cyc").value, day: +$("#sub-day").value || 1}]);
    const w = await post("/api/sub/save", {subs: next});
    if (!w.ok) return toast(w.msg, true);
    toast("加好了"); renderSubCard();
  };
  const cl = $("#sub-clr");
  if (cl) cl.onclick = async () => {
    if (!confirm("清空订阅清单？")) return;
    await post("/api/sub/save", {subs: []});
    toast("已清空"); renderSubCard();
  };
}
// 团购核销状态的三选一按钮
function statPicker(g) {
  const opts = [["待核销","tagw"],["核销","tagg"],["退回","tagr"]];
  return opts.map(([v, cls]) => {
    const on = g.stat === v;
    return `<button class="badge ${on?cls:"tagd"} gstat" data-row="${g.row}" data-stat="${v}"
      style="${on?"":"opacity:.45;"}border:0;cursor:pointer;margin-right:4px"
      title="点一下把这一行改成「${v}」">${v}</button>`;
  }).join("");
}
function bindGroupStat() {
  $$("#tab-bill .gstat").forEach(btn => btn.onclick = async () => {
    busy();
    const r = await post("/api/bill/stat", {row: +btn.dataset.row, stat: btn.dataset.stat});
    if (r.ok) { toast(r.msg); BILL = null; await loadBill(); } else toast(r.msg, true);
  });
}
function gcard(k, v, c) { return `<div class="gcard"><div class="k">${k}</div><div class="v" style="color:${c}">${v}</div></div>`; }
function badge(s) {
  return `<span class="badge ${({待核销:"tagw",核销:"tagg",退回:"tagr",已付:"tagd",待付:"tagw"}[s]||"tagd")}">${esc(s||"-")}</span>`;
}
function renderBillCharts() {
  const b = BILL;
  const rad = getComputedStyle(document.documentElement).getPropertyValue("--radius").trim() || "10px";
  const cardBg = cssVar("--card", "#fff");
  const lineC = cssVar("--line", "#e3e9f2");
  const mutC = cssVar("--mut", "#8891a0");
  const txtC = cssVar("--txt", "#1f2933");
  const tt = {backgroundColor: cardBg, borderColor: lineC, borderWidth: 1,
              textStyle: {color: txtC, fontSize: ckFs(12)},
              extraCssText: "border-radius:" + rad + ";box-shadow:0 6px 24px rgba(0,0,0,.18)"};
  // 网格线一律虚线：实线在深色底上很"重"，一眼看过去全是格子
  const ax = {
    axisLine: {lineStyle: {color: lineC}}, axisTick: {show: false},
    axisLabel: {color: mutC, fontSize: ckFs(11)},
    splitLine: {lineStyle: {color: lineC, type: "dashed"}},
  };

  /* ---- 饼图：一张图两套标注的时代结束了 ----
     以前扇区上一圈标签、底下一排图例，说的是同一件事，还外带一个
     ◀1/2▶ 翻页条（项目一多就冒出来，末尾那个字还被切半个）。
     现在只留扇区上的标签，图例撤掉。 */
  const pieOpt = (data, total) => {
    // 小于 3% 的不标名字 —— 它们的引线会挤成一团，谁也看不清，
    // 真正该被看见的是那几个大的
    const named = data.filter(d => d.value / total >= 0.03);
    const tiny = data.filter(d => d.value / total < 0.03);
    const series = named.concat(tiny).map(d => {
      const small = tiny.indexOf(d) >= 0;
      return {name: d.name, value: d.value,
        // 淡填充 + 实色描边 —— 颜色按**类别名**取，不用传进来的 d.color，
        // 因为这里要的是同一个色相的两种浓度
        itemStyle: {color: pieFill(d.name), borderColor: colorOf(d.name)},
        label: {show: !small}, labelLine: {show: !small}};
    });
    return {
      tooltip: {trigger: "item", formatter: "{b}<br/>{c} 元（{d}%）", ...tt},
      series: [{
        type: "pie", radius: ["42%", "70%"], center: ["50%", "50%"],
        avoidLabelOverlap: true,
        // 线条勾勒：外圈 2px 实色描边，里面只填一层 15% 的同色。
        // 这样圆环是"勾"出来的，背景（照片/底色）能透上来。
        // ⚠ 颜色一律走 colorOfA（逗号写法），别自己拼字符串。
        itemStyle: {borderWidth: 2, borderRadius: 2},
        label: {formatter: "{b}  {d}%", fontSize: ckFs(11), color: mutC},
        labelLine: {length: 10, length2: 10, lineStyle: {color: lineC}},
        // ⚠ 2.3.7：小扇区的手工避让不够用。收入饼图上「结余」占八成，
        //   剩下三项被挤在一条窄缝里，标签和引线叠成一团谁也读不出来。
        //   hideOverlap 让 ECharts 自己算 —— 放不下的标签直接不画，
        //   鼠标移上去 tooltip 里仍然有名字和金额，信息没丢。
        labelLayout: {hideOverlap: true},
        minAngle: 2,
        data: series,
      }],
      textStyle: {color: mutC},
    };
  };

  const expItems = Object.entries(b.exp_cat);
  const expTotal = expItems.reduce((s2, [, v]) => s2 + v, 0) || 1;
  let expPie = expItems.map(([n, v]) => ({name: n, value: v, color: colorOf(n)}));
  if (expItems.length > 8) {
    // ⚠ 合并出来的这一桶**不能叫「其他小额」** —— 用户自己就有一个叫「其他」的
    //   真类别，两个名字摆在一起，谁也分不清哪个是哪个。叫「其余 N 项」。
    const rest = expItems.slice(8).reduce((s2, [, v]) => s2 + v, 0);
    expPie = expItems.slice(0, 8).map(([n, v]) => ({name: n, value: v, color: colorOf(n)}));
    if (rest > 0) expPie.push({
      name: `其余 ${expItems.length - 8} 项`, value: rest, color: cssVar("--mut", "#8891a0")});
  }
  chartOf("c-exp-pie").setOption(pieOpt(expPie, expTotal), true);

  const incItems = Object.entries(b.inc_cat);
  const incTotal = incItems.reduce((s2, [, v]) => s2 + v, 0) || 1;
  chartOf("c-inc-pie").setOption(pieOpt(
    incItems.map(([n, v]) => ({name: n, value: v, color: colorOf(n)})), incTotal), true);

  /* ---- 每月收支 ----
     柱子改成竖向渐变（上实下淡），跟「每日支出趋势」那张的视觉语言统一；
     预算线改成一条**横贯的参考虚线** —— 只有一个月数据时，原来那个
     line 系列只有一个点，ECharts 就画一个孤零零的紫圆点，看着像渲染坏了。 */
  const grad = (a2, b2) => ({type: "linear", x: 0, y: 0, x2: 0, y2: 1,
    colorStops: [{offset: 0, color: a2}, {offset: 1, color: b2}]});
  // 收入和支出**不能走哈希取色** —— 那样会随机撞成蓝的紫的，跟直觉对着干。
  // 它们有固定语义：收=绿、支=红。但饱和度和明度跟着主题走，
  // 免得主题是淡雅的纸墨调子、柱子却是两管荧光笔。
  const _tone = (v, fallback, dark, l) => {
    const c = hslOf(cssVar(v, fallback));
    return hslCss(c.h, Math.max(22, Math.min(c.s, dark ? 42 : 50)), l);
  };
  const _dark = document.documentElement.dataset.theme === "dark";
  const incC = _tone("--green", "#059669", _dark, _dark ? 58 : 44);
  const expC = _tone("--red", "#dc2626", _dark, _dark ? 58 : 50);
  // 渐变的下半截：同一个色相，明度往底色方向推一点
  const _tail = c => {
    const o = hslOf(c);
    return hslCss(o.h, o.s, Math.max(12, o.l + (_dark ? 12 : -14)));
  };
  const incC2 = _tail(incC), expC2 = _tail(expC);
  const mn = b.months.map(m => m.ym ? m.ym.slice(2).replace("-", "年") + "月" : m.m);
  const bud = b.months.map(m => (m.eff_budget != null ? m.eff_budget : m.budget))
    .filter(v => v != null && v > 0);
  // 预算有好几个不同值时画阶梯线，只有一个值（或全都一样）时画一条横贯的参考线
  const budUniq = [...new Set(bud)];
  const barSeries = [
    {name: "收入", type: "bar", barMaxWidth: 26, barGap: "18%",
     data: b.months.map(m => m.inc),
     itemStyle: {borderRadius: [6, 6, 2, 2], color: grad(incC, incC2)}},
    {name: "支出", type: "bar", barMaxWidth: 26,
     data: b.months.map(m => m.exp),
     itemStyle: {borderRadius: [6, 6, 2, 2], color: grad(expC, expC2)},
     ...(budUniq.length === 1 ? {
       markLine: {silent: true, symbol: "none",
         lineStyle: {type: "dashed", color: cssVar("--amber", "#f59e0b"), width: 1.4},
         label: {formatter: "预算 ¥{c}", color: cssVar("--amber-d", "#b45309"),
                 fontSize: ckFs(11), position: "insideEndTop"},
         data: [{yAxis: budUniq[0]}]}} : {})},
  ];
  if (budUniq.length > 1) {
    barSeries.push({name: "预算", type: "line", symbol: "circle", symbolSize: 5,
      data: b.months.map(m => (m.eff_budget != null ? m.eff_budget : m.budget)),
      lineStyle: {type: "dashed", color: cssVar("--amber", "#f59e0b"), width: 1.4},
      itemStyle: {color: cssVar("--amber", "#f59e0b")}});
  }
  chartOf("c-month-bar").setOption({
    tooltip: {trigger: "axis", valueFormatter: v => money(v), ...tt},
    legend: {bottom: 0, textStyle: {fontSize: ckFs(11), color: mutC}, itemGap: 18},
    // ⚠ 用 containLabel 而不是写死 left —— 坐标轴的字号跟着「字号设置」缩放，
    //   用户把字号调到 22 时，"3,500" 能有 50px 宽，写死 58 就被切成了「00」。
    grid: {containLabel: true, left: 8, right: 18, top: 26, bottom: 46},
    xAxis: {type: "category", data: mn, ...ax},
    yAxis: {type: "value", ...ax},
    series: barSeries,
  }, true);

  /* ---- 每日支出趋势（这张用户是满意的，只统一一下配色和网格） ---- */
  const days = Object.keys(b.day_exp).sort();
  chartOf("c-day-line").setOption({
    tooltip: {trigger: "axis", valueFormatter: v => money(v), ...tt},
    grid: {containLabel: true, left: 8, right: 18, top: 22, bottom: 52},
    xAxis: {type: "category", data: days,
            axisLabel: {formatter: v => v.slice(5), fontSize: ckFs(10), color: mutC},
            axisLine: {lineStyle: {color: lineC}}, axisTick: {show: false}},
    yAxis: {type: "value", ...ax},
    series: [{type: "line", data: days.map(d => b.day_exp[d]), smooth: true,
      areaStyle: {opacity: .18, color: expC}, itemStyle: {color: expC},
      lineStyle: {color: expC, width: 2},
      symbolSize: 4, showSymbol: days.length < 40}],
  }, true);
}
// 「保存后不清空表单」时把上一笔留在表单里，方便改一改接着记
let billDraft = null;
// ⚠ 表单里的字段 ID 在页面上和弹窗里是**同一套**，取值时必须限定作用域，
//   否则全文档查找会命中页面上那张「记一笔」（它排在弹窗前面），改的就不是你打开的这条。
function readBillForm(box) {
  const el = id => $("#" + id, box || document);
  return {date: el("f-date").value, cat: el("f-cat").value, note: el("f-note").value.trim(),
    amt: parseFloat(el("f-amt").value) || 0, isIn: el("f-in").classList.contains("on"),
    pay: el("f-pay").value, grp: el("f-grp").value, stat: el("f-stat").value};
}
function billForm(rec) {
  const r = rec || (rec === undefined ? (billDraft || {}) : {});
  return `<div class="form">
    <div class="f"><label>日期</label><input type="date" id="f-date" value="${r.date || todayStr()}"></div>
    <div class="f"><label>类别</label>${catSelect(r.cat || "")}</div>
    <div class="f"><label>项目 / 备注</label><input id="f-note" data-sug="billnote" value="${esc(r.note||"")}" style="min-width:180px" placeholder="买了什么 / 钱从哪来"></div>
    <div class="f"><label>金额</label>
      <div class="frow"><input id="f-amt" type="number" step="0.01" value="${r.inc || r.exp || ""}">
        <div class="seg"><button type="button" id="f-in" class="${r.inc?"on":""}">收入</button><button type="button" id="f-out" class="${!r.inc?"on":""}">支出</button></div></div></div>
    <div class="f"><label>支付方式</label><select id="f-pay">${pays().map(p=>`<option${(r.pay||pays()[0])===p?" selected":""}>${p}</option>`).join("")}</select></div>
    <div class="f"><label>是否团购</label><select id="f-grp">${["否","是"].map(v=>`<option${(r.grp||"否")===v?" selected":""}>${v}</option>`).join("")}</select></div>
    <div class="f"><label>核销状态</label><select id="f-stat"${(r.grp||"否")==="是"?"":' disabled title="只有团购才需要核销"'}>
      <option value=""${(r.stat||"")===""?" selected":""}>（不团购）</option>
      ${["待核销","核销","退回"].map(v=>`<option${(r.stat||"")===v?" selected":""}>${v}</option>`).join("")}
    </select></div>
    <button class="btn" id="f-save">${r.row ? "保存修改" : "记一笔"}</button>
  </div>`;
}
function bindBillForm(rec, root) {
  const box = root || document;
  const el = id => $("#" + id, box);
  const bf = cfg("bill_form", {}) || {};
  el("f-in").onclick = () => { el("f-in").classList.add("on"); el("f-out").classList.remove("on"); };
  el("f-out").onclick = () => { el("f-out").classList.add("on"); el("f-in").classList.remove("on"); };
  // 只有团购才需要核销。选「否」时把核销状态置灰并清空 ——
  // 以前那个下拉默认选中「待核销」，于是每一笔普通支出都被打上这个标，
  // 记录列表里看着像全是团购，其实一个都不是。
  const grpSel = el("f-grp"), statSel = el("f-stat");
  if (grpSel && statSel) {
    const syncStat = () => {
      const isGrp = grpSel.value === "是";
      statSel.disabled = !isGrp;
      statSel.title = isGrp ? "" : "只有团购才需要核销";
      if (!isGrp) statSel.value = "";
      else if (!statSel.value) statSel.value = "待核销";
    };
    grpSel.onchange = syncStat;
    syncStat();
  }
  const save = async () => {
    const f = readBillForm(box);
    const body = {date: f.date, cat: f.cat, note: f.note,
      inc: f.isIn ? f.amt : "", exp: f.isIn ? "" : f.amt, pay: f.pay, grp: f.grp, stat: f.stat};
    if (rec && rec.row) body.row = rec.row;
    busy();
    const r = await post(rec && rec.row ? "/api/bill/edit" : "/api/bill/add", body);
    if (!r.ok) return toast(r.msg, true);
    toast(r.msg);
    // 「保存后自动清空」关掉时，把日期/支付方式这些连着几笔都一样的留着，金额和备注清掉
    billDraft = bf.clear_after_save === false
      ? {date: f.date, cat: f.cat, pay: f.pay, grp: f.grp, stat: f.stat, inc: f.isIn ? 1 : 0}
      : null;
    BILL = null; await loadBill();
    if (billDraft) { const a = $("#f-amt"); if (a) a.focus(); }
  };
  el("f-save").onclick = save;
  // 回车即保存：备注和金额最常用，日期/下拉框上按回车也顺手接上
  if (bf.enter_to_save !== false)
    ["f-date", "f-amt", "f-note"].forEach(id => {
      const i = el(id);
      if (i) i.addEventListener("keydown", e => {
        if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); save(); }
      });
    });
}
// 明细默认只显示最新 10 条，底部「加载更多」每次再加 10 条
let recLimit = 10;            // 当前显示多少条（点「加载更多」会变大）
let recPageSize = 10;         // 用户选的每页条数；换筛选/重渲染都回到这个值

function recRow(r) {
  return `<tr class="${r.stat==="退回"?"voidrow":""}">
    <td class="muted">${r.row}</td><td>${r.date}</td>
    <td><span class="dot" style="background:${colorOf(r.cat)}"></span>${esc(r.cat)}</td>
    <td>${esc(r.note)}</td>
    <td class="num g">${r.inc ? money(r.inc) : ""}</td>
    <td class="num r">${r.exp ? money(r.exp) : ""}</td>
    <td>${esc(r.pay)}</td>
    <td>${r.grp==="是"?'<span class="badge tagv">团购</span>':""} ${r.stat?badge(r.stat):""}</td>
    <td style="white-space:nowrap">
      <button class="btn ghost sm" data-edit="${r.row}">改</button>
      <button class="btn warn sm" data-del="${r.row}">删</button></td></tr>`;
}
// 筛选状态。纯前端过滤 —— 数据本来就全在 BILL.records 里，点一下立刻出结果，
// 不用请求后端、也不重查数据库。
let recFilter = {cats: [], q: "", flow: "all", month: ""};
const recFiltering = () => !!(recFilter.cats.length || recFilter.q.trim()
                              || recFilter.flow !== "all" || recFilter.month);

function recFiltered() {
  const f = recFilter, q = f.q.trim().toLowerCase();
  return BILL.records.filter(r => {
    if (f.cats.length && !f.cats.includes(r.cat)) return false;
    if (f.flow === "out" && !(r.exp > 0)) return false;
    if (f.flow === "in" && !(r.inc > 0)) return false;
    if (f.month && String(r.date || "").slice(0, 7) !== f.month) return false;
    if (q) {
      const hay = `${r.note || ""} ${r.cat || ""} ${r.pay || ""} ${r.date || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function recFilterBar() {
  // 只列出当前记录里真实出现过的类别和月份，免得列一堆空按钮
  const cats = [...new Set(BILL.records.map(r => r.cat).filter(Boolean))];
  const months = [...new Set(BILL.records.map(r => String(r.date || "").slice(0, 7))
                   .filter(m => m.length === 7))].sort().reverse();
  return `<div class="recfilter">
    <div class="rf-row">
      <input id="rf-q" placeholder="搜备注 / 类别 / 支付方式…" value="${esc(recFilter.q)}">
      <select id="rf-flow">
        <option value="all"${recFilter.flow === "all" ? " selected" : ""}>收支都看</option>
        <option value="out"${recFilter.flow === "out" ? " selected" : ""}>只看支出</option>
        <option value="in"${recFilter.flow === "in" ? " selected" : ""}>只看收入</option>
      </select>
      <select id="rf-month">
        <option value="">全部月份</option>
        ${months.map(m => `<option value="${m}"${recFilter.month === m ? " selected" : ""}>${
          m.slice(0, 4)}年${+m.slice(5, 7)}月</option>`).join("")}
      </select>
      ${recFiltering() ? `<button class="btn ghost sm" id="rf-clear">清空筛选</button>` : ""}
    </div>
    <div class="rf-cats">
      ${cats.map(c => `<button class="rf-cat${recFilter.cats.includes(c) ? " on" : ""}"
        data-rfcat="${esc(c)}" title="点一下只看这个类别，可以多选">
        <span class="dot" style="background:${colorOf(c)}"></span>${esc(c)}</button>`).join("")}
    </div>
  </div>`;
}

function recordsBox() {
  const all = BILL.records;
  const rows = recFiltered();
  const shown = Math.min(recLimit, rows.length);
  const more = shown < rows.length
    ? `<div style="text-align:center;margin-top:12px">
         <button class="btn ghost" id="rec-more">加载更多（还有 ${rows.length - shown} 条）</button></div>`
    : "";
  const sum = recFiltering()
    ? `共 ${all.length} 条 · <b>筛选后 ${rows.length} 条</b>，显示最新 ${shown} 条`
    : `共 ${all.length} 条，显示最新 ${shown} 条`;
  return `${recFilterBar()}
    <div class="mini reclimit" style="margin:8px 0"><span>${sum}${
      BILL.kpi.void ? ` · 其中 ${BILL.kpi.void} 条已退回（灰掉，不计入统计）` : ""}</span>
      <span>每页
        ${[10, 25, 50, 99999].map(n => `<button class="segbtn${recPageSize === n ? " on" : ""}"
          data-reclimit="${n}" title="${n > 9999 ? "全部显示（条数多时页面会很长）" : "每页显示 " + n + " 条"}"
          >${n > 9999 ? "全部" : n}</button>`).join("")}</span></div>
    ${rows.length ? `<table><thead><tr><th>行</th><th>日期</th><th>类别</th><th>项目/备注</th>
      <th class="num">收入</th><th class="num">支出</th><th>支付</th><th>团购/核销</th><th></th></tr></thead>
      <tbody>${rows.slice(0, shown).map(recRow).join("")}</tbody></table>`
    : emptyBox("没有符合筛选条件的记录", "试试清空筛选，或者换个关键词")}
    ${more}`;
}
// 只刷新明细区，不整页重渲染（保住滚动位置和「记一笔」表单里已填的内容）
function renderRecords() {
  const box = $("#rec-box");
  if (!box) return;
  box.innerHTML = recordsBox();
  bindRecords(box);
}
// 绑定范围严格限定在 root 内 —— 用全文档选择器会误伤并改写其它按钮的点击事件
function bindRecords(root) {
  if (!root) return;
  $$("[data-edit]", root).forEach(btn => btn.onclick = () => {
    const rec = BILL.records.find(r => r.row === +btn.dataset.edit);
    if (!rec) return;
    modal("修改流水（第 " + rec.row + " 行）", billForm(rec), async () => {
      const f = readBillForm($("#modalCard"));      // ← 只读弹窗里那张表单
      busy();
      const r = await post("/api/bill/edit", {row: rec.row, date: f.date, cat: f.cat, note: f.note,
        inc: f.isIn ? f.amt : "", exp: f.isIn ? "" : f.amt, pay: f.pay, grp: f.grp, stat: f.stat});
      if (r.ok) { toast(r.msg); BILL = null; await loadBill(); return true; }
      toast(r.msg, true); return false;
    });
    bindBillForm(rec, $("#modalCard"));
  });
  $$("[data-del]", root).forEach(btn => btn.onclick = async () => {
    if (!confirm("确定删除第 " + btn.dataset.del + " 行？")) return;
    busy();
    const r = await post("/api/bill/del", {row: +btn.dataset.del});
    if (r.ok) { toast(r.msg); BILL = null; await loadBill(); } else toast(r.msg, true);
  });
  const more = $("#rec-more", root);
  if (more) more.onclick = () => { recLimit += 10; renderRecords(); };
  // 每页条数：105 条按 10 条一页要点十几次「加载更多」，不如直接选
  $$("[data-reclimit]", root).forEach(b => b.onclick = () => {
    recPageSize = recLimit = +b.dataset.reclimit;   // 选一次就记住，切筛选也沿用
    renderRecords();
  });

  // ---- 筛选。改条件后把分页重置回 10 条，否则「筛出 3 条却显示 30 条」很怪 ----
  const refilter = () => { recLimit = recPageSize; renderRecords(); };
  const q = $("#rf-q", root);
  if (q) {
    let t = null;
    q.oninput = () => {                       // 打字时防抖，别每按一键就重排 DOM
      clearTimeout(t);
      t = setTimeout(() => { recFilter.q = q.value; refilter(); }, 220);
    };
    q.onkeydown = e => { if (e.key === "Escape") { q.value = ""; recFilter.q = ""; refilter(); } };
  }
  const fl = $("#rf-flow", root);
  if (fl) fl.onchange = () => { recFilter.flow = fl.value; refilter(); };
  const mo = $("#rf-month", root);
  if (mo) mo.onchange = () => { recFilter.month = mo.value; refilter(); };
  const cl = $("#rf-clear", root);
  if (cl) cl.onclick = () => { recFilter = {cats: [], q: "", flow: "all", month: ""}; refilter(); };
  $$("[data-rfcat]", root).forEach(b => b.onclick = () => {
    const c = b.dataset.rfcat;
    const i = recFilter.cats.indexOf(c);
    if (i >= 0) recFilter.cats.splice(i, 1); else recFilter.cats.push(c);
    refilter();
  });
}
/* 付清尾款：确认金额、付款账户和日期，一步完成「标已付 + 记一笔支出」 */
function payTailModal(t) {
  modal(`付清尾款 · ${esc(t.name)}`, `
    <div class="warn" style="font-weight:400">
      会做两件事：① 把这一笔标为「已付」；② 在「记录」里记一笔支出。
      两处在同一个事务里，要么都成、要么都不做 —— 不会出现「尾款标了已付、
      账上却没这笔钱」。
    </div>
    <div class="form">
      <div class="f"><label>金额（尾款）</label>
        <input id="tp-amt" type="number" step="0.01" value="${t.tail}" style="width:110px"></div>
      <div class="f"><label>从哪个账户付的</label>
        <select id="tp-pay">${pays().map(p => `<option${p === pays()[0] ? " selected" : ""}>${p}</option>`).join("")}</select></div>
      <div class="f"><label>付款日期</label>
        <input id="tp-date" type="date" value="${todayStr()}"></div>
    </div>
    <p class="mini" style="margin-top:10px">记账类别会取这笔尾款的类别；若它不是账单类别则记为「周边」。</p>
  `, async () => {
    busy();
    const r = await post("/api/tail/pay", {row: t.row, pay: $("#tp-pay").value,
                                           date: $("#tp-date").value,
                                           amount: $("#tp-amt").value});
    if (!r.ok) { toast(r.msg, true); return false; }
    toast(r.msg);
    BILL = null;
    await loadBill();
    return true;
  });
}

/* 尾款现金流：未来几个月扛不扛得住 */
function cashflowBox() {
  const cf = BILL.cashflow;
  if (!cf || !cf.months || !cf.months.length) return "";
  return `<div style="margin-bottom:14px">
    <div class="dsec-h" style="margin-bottom:6px">${ICON.wallet} 尾款压力
      <span class="mini">按最近 ${cf.surplus_src || 0} 个月的平均结余估算</span>
      ${cf.tight ? '<span class="badge tagr">有月份会紧张</span>' : '<span class="badge tagg">扛得住</span>'}
    </div>
    <table><thead><tr><th>月份</th><th class="num">待付尾款</th>
      <th class="num">预估结余</th><th class="num">付完还剩</th><th></th></tr></thead><tbody>
      ${cf.months.map(m => `<tr class="${m.warn ? "voidrow" : ""}">
        <td>${m.month}</td>
        <td class="num">${money(m.tail)}</td>
        <td class="num muted">${money(m.est_surplus)}</td>
        <td class="num ${m.net < 0 ? "r" : "g"}"><b>${money(m.net)}</b></td>
        <td>${m.warn ? '<span class="badge tagr">这个月会紧张</span>' : ""}</td>
      </tr>`).join("")}
    </tbody></table>
    ${cf.surplus_src < 2 ? `<div class="warn" style="font-weight:400">
      ⚠ 目前只有 ${cf.surplus_src} 个月的数据，预估结余参考意义有限 ——
      等记满 2~3 个月再看这个表会准得多。
    </div>` : ""}
    <p class="mini" style="margin-top:8px">
      「预估结余」= 近几个月（<b>已剔除期初结余</b>${cf.opening_total ? "，本次剔除了 " + money(cf.opening_total) : ""}）
      的实际收支差平均值，只是参考。当前全部尾款合计 ${money(BILL.kpi.pending)}，
      一次性付清后账上${cf.left_after_all < 0 ? "<b class='r'>还差 " + money(-cf.left_after_all) + "</b>" : "还剩 " + money(cf.left_after_all)}。
    </p>
  </div>`;
}
function tailForm(t) {
  const r = t || {};
  return `<div class="form">
    <div class="f"><label>项目名称</label><input id="t-name" data-sug="tailname" value="${esc(r.name||"")}" style="min-width:170px"></div>
    <div class="f"><label>类别</label><input id="t-cat" value="${esc(r.cat||"")}" style="min-width:80px"></div>
    <div class="f"><label>定金(已付)</label><input id="t-dep" type="number" step="0.01" value="${r.dep||""}"></div>
    <div class="f"><label>尾款金额(待付)</label><input id="t-tail" type="number" step="0.01" value="${r.tail||""}"></div>
    <div class="f"><label>预计付款时间</label><input id="t-pdate" type="date" value="${r.pdate||""}"></div>
    <div class="f"><label>状态</label><select id="t-stat">${["待付","已付"].map(v=>`<option${(r.stat||"待付")===v?" selected":""}>${v}</option>`).join("")}</select></div>
    <div class="f"><label>备注</label><input id="t-note" value="${esc(r.note||"")}"></div>
    <button class="btn" id="t-save">${r.row ? "保存" : "添加"}</button>
  </div>`;
}
// 同 readBillForm：页面上和弹窗里的尾款表单字段 ID 一样，取值必须限定作用域
function readTailForm(box) {
  const el = id => $("#" + id, box || document);
  return {name: el("t-name").value, cat: el("t-cat").value, dep: el("t-dep").value,
    tail: el("t-tail").value, pdate: el("t-pdate").value,
    stat: el("t-stat").value, note: el("t-note").value};
}
function tailTable() {
  const rows = BILL.tails.map(t => {
    const d = t.days === null ? "" : (t.days < 0 ? `已超期 ${-t.days} 天` : `还有 ${t.days} 天`);
    return `<tr><td>${esc(t.name)}</td><td>${esc(t.cat)}</td>
      <td class="num">${money(t.dep)}</td><td class="num"><b>${money(t.tail)}</b></td>
      <td>${t.pdate}</td><td>${badge(t.stat)}</td>
      <td class="${t.days !== null && t.days < 0 && t.stat==="待付" ? "r" : "muted"}">${d}</td>
      <td style="white-space:nowrap">
        <button class="btn ghost sm" data-tedit="${t.row}">改</button>
        ${t.stat === "待付"
          ? `<button class="btn sm" data-tpay="${t.row}" title="标为已付，并在「记录」里记一笔支出">${ICON.wallet} 付清并记账</button>
             <button class="btn ghost sm" data-ttoggle="${t.row}" title="只改状态，不记账（适合已经在别处记过账的）">只标已付</button>`
          : `<button class="btn ghost sm" data-ttoggle="${t.row}">标回待付</button>`}
        <button class="btn warn sm" data-tdel="${t.row}">删</button></td></tr>`;
  }).join("");
  setTimeout(() => {
    $$("#tab-bill [data-tedit]").forEach(btn => btn.onclick = () => {
      const t = BILL.tails.find(x => x.row === +btn.dataset.tedit);
      modal("修改尾款（第 " + t.row + " 行）", tailForm(t), async () => {
        const body = Object.assign(readTailForm($("#modalCard")), {row: t.row});
        busy();
        const r = await post("/api/tail/edit", body);
        if (r.ok) { toast(r.msg); BILL = null; await loadBill(); return true; }
        toast(r.msg, true); return false;
      });
    });
    $$("#tab-bill [data-ttoggle]").forEach(btn => btn.onclick = async () => {
      const t = BILL.tails.find(x => x.row === +btn.dataset.ttoggle);
      busy();
      const r = await post("/api/tail/edit", {row: t.row, name: t.name, cat: t.cat, dep: t.dep,
        tail: t.tail, pdate: t.pdate, stat: t.stat === "待付" ? "已付" : "待付", note: t.note});
      if (r.ok) { toast(r.msg); BILL = null; await loadBill(); } else toast(r.msg, true);
    });
    $$("#tab-bill [data-tpay]").forEach(btn => btn.onclick = () => {
      const t = BILL.tails.find(x => x.row === +btn.dataset.tpay);
      if (t) payTailModal(t);
    });
    $$("#tab-bill [data-tdel]").forEach(btn => btn.onclick = async () => {
      if (!confirm("确定删除这条尾款记录？")) return;
      busy();
      const r = await post("/api/tail/del", {row: +btn.dataset.tdel});
      if (r.ok) { toast(r.msg); BILL = null; await loadBill(); } else toast(r.msg, true);
    });
    $("#t-save").onclick = async () => {
      const body = readTailForm($("#tab-bill"));
      busy();
      const r = await post("/api/tail/add", body);
      if (r.ok) { toast(r.msg); BILL = null; await loadBill(); } else toast(r.msg, true);
    };
  }, 0);
  return BILL.tails.length ? `<table><thead><tr><th>项目</th><th>类别</th><th class="num">定金</th>
    <th class="num">尾款</th><th>预计付款</th><th>状态</th><th>提醒</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table>` : emptyBox("还没有登记尾款", "用下面的「＋ 登记一笔新尾款」");
}

/* ================================================================
   ③ 打卡（日历 + 单日卡片）
================================================================ */
const SEL_OPTS = {M:["清晰记得","模糊记得","不记得"], K:["是","否"]};
function timeToMin(t) {                       // 跨夜口径：12:00 前 +1440
  if (!t) return null;
  const [h, m] = t.split(":").map(Number);
  let v = h * 60 + m;
  return v < 720 ? v + 1440 : v;
}
function dayStats(d, s) {
  d = {...d};
  // 小睡口径：空=未填；0=「没小睡」，判不达标（扣分）；1~30=达标；>30=睡太久
  d.S = (d.L === "" || d.L == null) ? ""
      : ((+d.L > 0 && +d.L <= 30) ? "√" : "×");
  // 完成率按**打卡项表**算，不写死列号 —— 不然用户自己加的项永远不计分，
  // 删掉的项还会一直在分母里拖着
  //
  // ⚠ 分子和分母**必须同源**。2.2 让打卡项可自定义之后，上面那句注释是对的、
  //   下面那行 `core / 5` 是错的：用户加一个核心项，分子变 6、分母还是 5，
  //   完成率当场显示 120%；删掉一项则永远到不了 100%。
  //   分母也得从同一张表里数出来。
  const coreList = checkItems("core"), bonusList = checkItems("bonus");
  const core = coreList.filter(x => d[x.col] === "√").length;
  const bonus = bonusList.filter(x => d[x.col] === "√").length;
  const sport = (+d.AA > 0) ? 1 : 0;
  const screen = (d.AB !== "" && d.AB != null && +d.AB <= +s.screen) ? 1 : 0;
  let sleepH = null;
  if (d.C && d.D) {
    const a = timeToMin(d.C), b = timeToMin(d.D);
    sleepH = ((b - a) / 60 + 24) % 24;
  }
  const tmin = timeToMin(d.C);
  const emin = timeToMin(s.early), lmin = timeToMin(s.late);
  const judge = tmin == null ? "" : (tmin <= emin ? "早睡" : (tmin <= lmin ? "偏晚" : "熬夜"));
  const okDur = sleepH != null && sleepH >= +s.min_sleep && sleepH <= +s.max_sleep;
  const pass = (judge && okDur) ? (s.strict === "早睡" ? judge === "早睡" : judge !== "熬夜") : false;
  // 分母从同一张表数出来；+2 是「运动」和「屏幕」这两项固定项。
  // 表被清空时兜个 1，不然会除出 NaN、整页数字变 "NaN%"。
  const coreN = Math.max(1, coreList.length);
  const totalN = Math.max(1, coreList.length + bonusList.length + 2);
  return {core: core / coreN, total: (core + bonus + sport + screen) / totalN,
    sleepH, judge, pass, quality: +d.I || 0};
}
async function loadCheck() {
  const r = await get("/api/check");
  if (!r.ok) return toast(r.msg, true);
  CHECK = r.data;
  clearDirty("check"); syncStamp();
  if (!checkMonth) checkMonth = curCheckMonth().name;
  if (!checkDay) checkDay = todayStr().slice(8, 10).replace(/^0/, "");
  idle();
  checkSkeleton();
  renderCheckData();
  renderCheckCharts();
  loadCheckExtra();          // 连续天数 / 热力图 / 趋势图 / 积分（自己拉自己那份数据）
  watchBackfill();
}

// 断月回填在后台跑，用户看不到过程 —— 补完了说一声，方便他确认「看板怎么多了几个月」
// 只提示一次：提示后会重新加载打卡页，而加载又会调回这里，不加标记会死循环
let backfillTold = false;
function watchBackfill() {
  clearInterval(watchBackfill._t);
  const poll = async () => {
    const r = await get("/api/check/backfill");
    if (!r.ok) return false;
    const s = r.data;
    if (s.running) {
      $("#syncTip").textContent = `补月表 ${s.done}/${s.total}…`;
      return true;
    }
    clearInterval(watchBackfill._t);
    idle();
    if (!backfillTold && s.created && s.created.length) {
      backfillTold = true;
      toast(`补上了 ${s.created.length} 个月的打卡表（${s.created[0]} 起）`);
      CHECK = null;
      await loadCheck();
    }
    return false;
  };
  poll().then(busyNow => {
    if (busyNow) watchBackfill._t = setInterval(poll, 2000);
  });
}
/* 页面骨架只建一次；保存后只局部刷新（不重建 DOM、不重画图表） */
/* ================= 打卡的「回头看」（2.3.6）=================
   连续天数、一年热力图、心情/精力/睡眠趋势、积分 —— 四样都靠
   `/api/check/series` 一个接口（近 N 天每天一行）。放在打卡页最下面。

   ⚠ 这些是**派生数据**（从已有的打卡记录现算），所以不存表、不用迁移，
     改了历史某天的卡，这里下次刷新就是对的。 */
let CKSER = null, GAMEST = null;

async function loadCheckExtra() {
  const r = await post("/api/check/series", {days: 400});
  if (r.ok) CKSER = r.data;
  const g = await post("/api/game/state", {});
  if (g.ok) GAMEST = g.data;
  renderCheckExtra();
}

function _streak(days) {
  /* 连续天数。**从今天往回数**，但今天还没打卡不算断 ——
     否则每天早上打开都显示"已断"，早上就先把人劝退了。
     「算一天」的门槛：核心项至少打了一个√。 */
  let cur = 0, best = 0, run = 0;
  const byD = {};
  days.forEach(x => { byD[x.d] = x; });
  const t = new Date();
  const ymd = d => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0")
    + "-" + String(d.getDate()).padStart(2, "0");
  const today = ymd(t);
  const yest = ymd(new Date(t.getTime() - 86400000));
  const hit = d => (byD[d] && byD[d].hit > 0) ? 1 : 0;
  // 当前连续：今天没打就从昨天起算
  let i = 0, start = hit(today) ? 0 : 1;
  for (i = start; ; i++) {
    const d = ymd(new Date(t.getTime() - i * 86400000));
    if (hit(d)) cur++;
    else break;
  }
  // 最长纪录：整段扫一遍
  let prev = null;
  days.forEach(x => {
    const d = new Date(x.d + "T00:00:00");
    if (x.hit > 0) {
      run = (prev && (d - prev) === 86400000) ? run + 1 : 1;
      if (run > best) best = run;
      prev = d;
    } else { run = 0; prev = null; }
  });
  void yest;
  return {cur, best};
}

function renderCheckExtra() {
  const box = $("#ck-extra");
  if (!box || !CKSER) return;
  const days = CKSER.days || [];
  const st = _streak(days);
  const coreN = CKSER.coreN || 5;
  // 热力图：按「周」排成列，每列 7 行（周一到周日），跟 GitHub 一个排法
  const map = {};
  days.forEach(x => { map[x.d] = x; });
  const today = new Date();
  const cells = [];
  const start = new Date(today.getTime() - 364 * 86400000);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));   // 回到周一
  for (let d = new Date(start); d <= today; d.setDate(d.getDate() + 1)) {
    const k = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0")
      + "-" + String(d.getDate()).padStart(2, "0");
    const x = map[k];
    const lv = !x || !x.hit ? 0 : Math.min(4, Math.ceil(x.hit / Math.max(1, coreN) * 4));
    cells.push(`<i class="hm l${lv}" title="${k}${x ? " · " + x.hit + "/" + coreN : " · 没记"}"></i>`);
  }
  // 趋势图：睡眠小时 / 心情 / 精力（后两个是下拉选项，用**选项下标**当数值）
  const last30 = days.slice(-30);
  const moodOpts = (CHECK.opts && CHECK.opts.mood) || [];
  const enOpts = (CHECK.opts && CHECK.opts.energy) || [];
  const idxOf = (arr, v) => (v && arr.indexOf(v) >= 0) ? arr.indexOf(v) + 1 : null;
  const g = GAMEST || {total: 0, left: 0, spent: 0, rewards: []};
  box.innerHTML = `
  <h2 class="sec">${ICON.chart} 回头看</h2>
  <div class="kpis">
    <div class="kpi"><div class="lab">连续打卡</div>
      <div class="num">${st.cur}<span style="font-size:.5em"> 天</span></div>
      <div class="sub">最长纪录 ${st.best} 天</div></div>
    <div class="kpi"><div class="lab">这一年记了</div>
      <div class="num">${days.filter(x => x.hit > 0).length}<span style="font-size:.5em"> 天</span></div>
      <div class="sub">攒了 ${g.total} 分，还剩 ${g.left}</div></div>
  </div>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" style="overflow-x:auto">
    <h2 class="sec" style="margin-top:0">${ICON.chart} 这一年</h2>
    <div class="heatmap">${cells.join("")}</div>
    <p class="mini" style="margin-top:8px">一格一天，越深打勾越多。
      鼠标停上去看那一天。空白的格子不是"没坚持"，是没记 —— 别拿它自责。</p>
  </div>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <h2 class="sec" style="margin-top:0">${ICON.chart} 最近 30 天</h2>
    <div class="chart small" id="c-ck-trend"></div>
  </div>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <h2 class="sec" style="margin-top:0">${ICON.sparkle} 积分与奖励</h2>
    <div id="game-box"></div>
  </div>`;
  renderGame();
  const c = chartOf("c-ck-trend");
  if (c) c.setOption({
    tooltip: {trigger: "axis"}, legend: {bottom: 0},
    grid: {left: 40, right: 40, top: 20, bottom: 44, containLabel: true},
    xAxis: {type: "category", data: last30.map(x => x.d.slice(5)),
            axisLabel: {fontSize: ckFs(10)}},
    yAxis: [{type: "value", name: "小时", nameTextStyle: {fontSize: ckFs(10)}},
            {type: "value", name: "档", min: 0, max: 5,
             nameTextStyle: {fontSize: ckFs(10)}, splitLine: {show: false}}],
    series: [
      {name: "睡眠", type: "line", smooth: true, connectNulls: true,
       data: last30.map(x => x.sleepH), itemStyle: {color: colorOf("睡眠")}},
      {name: "心情", type: "line", smooth: true, connectNulls: true, yAxisIndex: 1,
       data: last30.map(x => idxOf(moodOpts, x.mood)), itemStyle: {color: colorOf("心情")}},
      {name: "精力", type: "line", smooth: true, connectNulls: true, yAxisIndex: 1,
       data: last30.map(x => idxOf(enOpts, x.energy)), itemStyle: {color: colorOf("精力")}},
    ],
  }, true);
}

/** 积分与奖励。积分是**现算的**（见后端 game_state 那段），这里只管画和兑换。 */
function renderGame() {
  const b = $("#game-box");
  if (!b || !GAMEST) return;
  const g = GAMEST;
  b.innerHTML = `
    <div style="display:flex;gap:22px;align-items:baseline;margin-bottom:12px">
      <div><span class="mini">攒了</span> <b style="font-size:1.4em">${g.total}</b> <span class="mini">分</span></div>
      <div><span class="mini">花掉</span> ${g.spent} · <span class="mini">还剩</span> <b>${g.left}</b></div>
      <span class="mini" style="margin-left:auto">每天打一个勾算 1 分，全勤那天额外 +5</span>
    </div>
    <div class="gline2"><span>我想兑换的</span></div>
    ${(g.rewards || []).map(r => `
      <div class="gline2">
        <span>${r.got ? "✔ " : ""}${esc(r.name)}
          <span class="mini">${r.cost} 分</span></span>
        <button class="btn ${r.got ? "ghost" : ""} sm" data-redeem="${r.id}">
          ${r.got ? "取消兑换" : "兑换"}</button>
      </div>`).join("") || '<p class="mini">还没有奖励。想一个：攒够 50 分买杯奶茶？</p>'}
    <div style="margin-top:10px;display:flex;gap:8px;align-items:center">
      <input id="rw-name" placeholder="奖励名字" maxlength="20" style="width:160px">
      <input id="rw-cost" type="number" placeholder="要多少分" min="1" style="width:100px">
      <button class="btn ghost sm" id="rw-add">加一条</button>
    </div>`;
  b.querySelectorAll("[data-redeem]").forEach(x => x.onclick = async () => {
    const r = await post("/api/game/redeem", {id: x.dataset.redeem});
    if (!r.ok) return toast(r.msg, true);
    toast(r.msg);
    GAMEST.rewards = r.data.rewards;
    loadCheckExtra();
  });
  const add = $("#rw-add");
  if (add) add.onclick = async () => {
    const name = $("#rw-name").value.trim();
    const cost = +$("#rw-cost").value || 0;
    if (!name) return toast("给它起个名字", true);
    const list = (g.rewards || []).concat([{name, cost}]);
    const r = await post("/api/game/save", {rewards: list});
    if (!r.ok) return toast(r.msg, true);
    toast("加好了");
    loadCheckExtra();
  };
}

function checkSkeleton() {
  // 左栏放「日历 + 两张图」，右栏是单日面板。
  // 以前两张图在页面底部，日历下面就空出几百像素 —— 看着像没加载出来。
  $("#tab-check").innerHTML = `
  <div class="pagehead">
    <div class="ph-title">${ICON.check} 打卡</div>
    <div class="ph-sub" id="ck-head"></div>
    <div class="ph-actions">
      <button class="btn ghost sm" id="shot-sleep">${ICON.sparkle} 从截图录睡眠</button>
    </div>
  </div>
  <div id="ck-kpis" class="kpis"></div>
  <div class="checkwrap">
    <div class="checkleft">
      <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
        <div id="ck-pills" class="grid-tab"></div>
        <div id="ck-cal"></div>
      </div>
      <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><h2 class="sec" style="margin-top:0">${ICON.chart} 每日完成度</h2><div class="chart small" id="c-check-day"></div></div>
      <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><h2 class="sec" style="margin-top:0">${ICON.chart} 各月汇总</h2><div class="chart small" id="c-check-month"></div></div>
    </div>
    <div id="ck-day"></div>
  </div>
  <div id="ck-extra"></div>
  <h2 class="sec">${ICON.moon} 梦境记录 <span class="mini">（逐梦明细，按日期倒序）</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="ck-dreams"></div>
  <div class="foot">改动直接存进数据库；缺了的月份在系统启动时自动补齐</div>`;
}
function checkMonthObj() {
  return CHECK.months.find(x => x.name === checkMonth) || CHECK.months[0];
}
// 渲染出错时给出可见提示，而不是让面板静默变空白（曾经踩过这个坑）
// 另外：渲染会重建 .daypanel（它自身就是滚动容器 max-height:76vh;overflow:auto），
// 新元素的 scrollTop 天然为 0 —— 表现为"每点一个打卡项就跳回顶部"。
// 所以这里做「渲染前存、渲染后还原」，顺带还原输入框焦点与光标位置。
function renderCheckData() {
  const oldPanel = $("#ck-day .daypanel");
  const keepScroll = oldPanel ? oldPanel.scrollTop : 0;
  const keepWinY = window.scrollY;
  const act = document.activeElement;
  let focusSel = null, caret = null;
  if (act && act.closest && act.closest("#ck-day") &&
      (act.tagName === "INPUT" || act.tagName === "SELECT")) {
    if (act.dataset.dc) focusSel = `[data-dc="${act.dataset.dc}"]`;
    else if (act.id) focusSel = "#" + act.id;
    if (act.selectionStart != null) caret = act.selectionStart;
  }
  try { renderCheckDataInner(); }
  catch (e) {
    const box = $("#ck-day");
    if (box) box.innerHTML = `<div class="warn">⚠ 打卡页渲染出错：${esc(e.message)}<br>
      <span class="mini">可先切到其他页面再切回来；若一直报错，把这行文字反馈一下。</span></div>`;
    if (window.console) console.error(e);
  }
  const newPanel = $("#ck-day .daypanel");
  if (newPanel && keepScroll) newPanel.scrollTop = keepScroll;
  if (keepWinY) window.scrollTo(0, keepWinY);
  if (focusSel) {
    const el = $("#ck-day " + focusSel);
    if (el) {
      el.focus();
      if (caret != null && el.setSelectionRange) {
        try { el.setSelectionRange(caret, caret); } catch (e) { /* number 类型不支持，忽略 */ }
      }
    }
  }
}
// 默认选中「今天」。必须在这里兜底：总览页已预加载 CHECK，
// 之后切到打卡标签会跳过 loadCheck()（那里才初始化 checkDay），
// 导致 checkDay 为 null、面板停在当月第一天。
function ensureCheckState() {
  if (!checkMonth) checkMonth = curCheckMonth().name;
  const m = checkMonthObj();
  if (checkDay == null && m.days.length) {
    const t = todayStr(), td = +t.slice(8, 10);
    checkDay = m.days.some(d => d.day === td && d.date === t) ? td : m.days[0].day;
  }
}
function renderCheckDataInner() {
  ensureCheckState();
  const s = CHECK.settings;
  const m = checkMonthObj();
  // 分母只算「到今天为止」的日子。月份表给整月每天都预写了日期（含未来），
  // 若拿全部天数当分母，没到的日子会被算成失败、完成率被稀释成个位数
  // （曾经显示成 2%）。当初 Excel 那版月卡片用的也是 COUNTIF(日期,"<="&TODAY())，口径要一致。
  const past = m.days.filter(x => x.date <= todayStr());
  const pStats = past.map(d => dayStats(d, s));
  const coreRate = pStats.length ? pStats.reduce((a, b) => a + b.core, 0) / pStats.length : 0;
  const totRate = pStats.length ? pStats.reduce((a, b) => a + b.total, 0) / pStats.length : 0;
  const sleeps = pStats.filter(x => x.sleepH != null);
  const avgSleep = sleeps.length ? sleeps.reduce((a, b) => a + b.sleepH, 0) / sleeps.length : 0;
  const early = pStats.filter(x => x.judge === "早睡").length;
  const late = pStats.filter(x => x.judge === "熬夜").length;
  const pass = pStats.filter(x => x.pass).length;
  $("#ck-kpis").innerHTML = `
    ${kpi("核心完成率(月)", (coreRate*100).toFixed(0)+"%", coreRate>=0.8?"g":"a", "var(--green)",
         `${m.ym} · 已记 ${pStats.length} 天`)}
    ${kpi("总完成率(月)", (totRate*100).toFixed(0)+"%", totRate>=0.7?"g":"a", "var(--violet)", "核心+加分+运动+屏幕 /14")}
    ${kpi("平均睡眠", avgSleep.toFixed(1)+" h", "b", "var(--blue)", `目标 ${s.goal_sleep} h`)}
    ${kpi("早睡天数", early+" 天", "g", "var(--green)", `熬夜 ${late} 天`)}
    ${kpi("综合达标", pass+" 天", "b", "var(--amber)", `口径：${s.strict==="早睡"?"早睡严格":"非熬夜宽松"}`)}`;
  const hd = $("#ck-head");
  if (hd) hd.textContent = `${m.ym} · 已记 ${pStats.length} 天 · 目标完成率 ${(s.goal_rate*100).toFixed(0)}%`;
  $("#ck-pills").innerHTML = CHECK.months.map(x =>
    `<button class="pill ${x.name===m.name?"on":""}" data-m="${x.name}">${x.ym.replace(/^2026年/,"")}</button>`).join("");
  $("#ck-cal").innerHTML = calendarOf(m);
  $("#ck-day").innerHTML = dayPanel(m);
  $("#ck-dreams").innerHTML = dreamList();
  $$("#ck-pills [data-m]").forEach(btn => btn.onclick = () => {
    const same = checkMonth === btn.dataset.m;
    checkMonth = btn.dataset.m;
    checkDay = checkMonth === monthNameOf(todayStr()) ? +todayStr().slice(8,10) : 1;
    renderCheckData();
    if (!same) renderCheckCharts();
  });
  bindCalendar(m);
  bindDayPanel(m);
  bindDsec();
}
function renderCheckCharts() {
  const s = CHECK.settings;
  const m = checkMonthObj();
  const stats = m.days.map(d => dayStats(d, s));
  chartOf("c-check-day").setOption({
    tooltip:{trigger:"axis", valueFormatter:v => (v*100).toFixed(0)+"%"}, legend:{bottom:0},
    grid:{left:40, right:12, top:24, bottom:40},
    xAxis:{type:"category", data:m.days.map(d=>d.day+"日"), axisLabel:{fontSize:ckFs(10)}},
    yAxis:{type:"value", max:1, axisLabel:{formatter:v=>v*100+"%"}},
    series:[
      {name:"核心完成率", type:"bar", data:stats.map(x=>+x.core.toFixed(2)), itemStyle:{color:cssVar("--green","#059669"), borderRadius:[3,3,0,0]}},
      {name:"总完成率", type:"bar", data:stats.map(x=>+x.total.toFixed(2)), itemStyle:{color:cssVar("--violet","#8b5cf6"), borderRadius:[3,3,0,0]}},
      {name:"目标", type:"line", data:stats.map(()=>+s.goal_rate), lineStyle:{type:"dashed", color:cssVar("--red","#dc2626")},
       symbol:"none"}]});
  const ms = CHECK.months.map(x => {
    const st = x.days.map(d => dayStats(d, s));
    const sl = st.filter(a => a.sleepH != null);
    return {name: x.ym.replace(/^2026年/,""), sleep: sl.length ? +(sl.reduce((a,b)=>a+b.sleepH,0)/sl.length).toFixed(1) : 0,
      early: st.filter(a=>a.judge==="早睡").length, late: st.filter(a=>a.judge==="熬夜").length};
  });
  chartOf("c-check-month").setOption({
    tooltip:{trigger:"axis"}, legend:{bottom:0},
    grid:{left:36, right:40, top:24, bottom:40},
    xAxis:{type:"category", data:ms.map(x=>x.name)},
    yAxis:[{type:"value", name:"天数"}, {type:"value", name:"小时", min:0, max:12}],
    series:[
      {name:"早睡天数", type:"bar", data:ms.map(x=>x.early), itemStyle:{color:cssVar("--green","#059669")}},
      {name:"熬夜天数", type:"bar", data:ms.map(x=>x.late), itemStyle:{color:cssVar("--red","#dc2626")}},
      {name:"平均睡眠(h)", type:"line", yAxisIndex:1, data:ms.map(x=>x.sleep), itemStyle:{color:cssVar("--blue","#2563eb")}}]});
}
/* ---- 日历 ---- */
function calendarOf(m) {
  const t = todayStr();
  const first = new Date(m.days[0].date);
  const offset = (first.getDay() + 6) % 7;      // 周一开头
  const cells = [];
  let marked = false;      // 9月表跨到10月，day 会重复；只高亮第一个（与 dayPanel 的取值一致）
  for (let i = 0; i < offset; i++) cells.push('<span class="calday empty"></span>');
  for (const d of m.days) {
    const st = dayStats(d, CHECK.settings);
    const rate = Math.round(st.core * 100);
    const cls = rate >= 80 ? "good" : (rate >= 50 ? "mid" : "none");
    const sel = (!marked && +checkDay === d.day) ? (marked = true, " on") : "";
    const today = d.date === t ? " today" : "";
    cells.push(`<button class="calday ${cls}${sel}${today}" data-cd="${d.day}">
      <b>${d.day}</b><span>${d.M && d.M !== "不记得" ? ICON.moon : ""}${rate>0?rate+"%":""}</span></button>`);
  }
  return `<div class="calhead">${["一","二","三","四","五","六","日"].map(w=>`<span>${w}</span>`).join("")}</div>
    <div class="calwrap">${cells.join("")}</div>
    <div class="mini" style="margin-top:8px">颜色 = 当天核心完成度 · 月亮 = 做了梦 · 点格子填写那天</div>`;
}
function bindCalendar(m) {
  const cal = $("#ck-cal");
  if (!cal) return;
  $$("[data-cd]", cal).forEach(btn => btn.onclick = () => {
    checkDay = +btn.dataset.cd;
    renderCheckData();       // 换天 → 重画日历高亮和单日面板
    renderCheckCharts();
  });
}
/* ---- 单日卡片 ---- */
// 单日面板各段是否展开。**必须记住** —— 面板每次改动都会重建，
// 不记的话你刚展开「梦境」，填一个数它自己就收回去。
const DSEC_KEY = "xr_dsec";
function dsecOpen(id) {
  try {
    const m = JSON.parse(localStorage.getItem(DSEC_KEY) || "{}");
    return m[id] === undefined ? true : !!m[id];   // 默认全展开，不改原来的习惯
  } catch (e) { return true; }
}
function bindDsec() {
  $$("#ck-day details.dsec").forEach(d => d.ontoggle = () => {
    try {
      const m = JSON.parse(localStorage.getItem(DSEC_KEY) || "{}");
      m[d.dataset.dsec] = d.open;
      localStorage.setItem(DSEC_KEY, JSON.stringify(m));
    } catch (e) {}
  });
}

function dayPanel(m) {
  const d = m.days.find(x => x.day === +checkDay) || m.days[0];
  const st = dayStats(d, CHECK.settings);
  const idx = m.days.indexOf(d);
  const prev = m.days[idx - 1], next = m.days[idx + 1];
  const dreamed = d.M && d.M !== "不记得";
  const dd = CHECK.dream_detail[d.date] || [];
  const n = dd.length || 1;
  const s = CHECK.settings;
  return `<div class="daypanel">
    <div class="daynav">
      <button class="btn ghost sm" id="d-prev" ${prev?"":"disabled"}>◀ 前一天</button>
      <div class="daytitle">${d.date.slice(5).replace("-","月")}日 · 星期${WEEK[new Date(d.date).getDay()]}${d.date===todayStr()?' <span class="badge tagg">今天</span>':""}</div>
      <button class="btn ghost sm" id="d-next" ${next?"":"disabled"}>后一天</button>
      <button class="btn sm" id="d-today">回今天</button>
    </div>
    <details class="dsec" data-dsec="sleep"${dsecOpen("sleep") ? " open" : ""}>
      <summary class="dsec-h">${ICON.moon} 睡眠</summary>
      <div class="dsec-b">
      <div class="drow"><label>入睡时间</label><input type="time" data-dc="C" value="${d.C||""}">
        <label>起床时间</label><input type="time" data-dc="D" value="${d.D||""}">
        <label>时长</label><span class="mini">${st.sleepH!=null?st.sleepH.toFixed(1)+" h":"—"}</span>
        <span class="badge ${st.judge==="早睡"?"tagg":(st.judge==="熬夜"?"tagr":"tagd")}">${st.judge||"未记"}</span></div>
      <div class="drow"><span class="fgroup"><label>睡眠质量</label><span class="pillrow" data-dc="I">${[1,2,3,4,5].map(v=>`<button class="pill ${+d.I===v?"on":""}" data-v="${v}">${v}</button>`).join("")}</span></span>
        <span class="fgroup"><label>夜醒</label><input type="number" style="width:64px" data-dc="J" value="${d.J??""}"><span class="unit">次</span></span>
        <span class="fgroup"><label>睡前手机</label><span class="pillrow" data-dc="K">${["是","否"].map(v=>`<button class="pill ${d.K===v?"on":""}" data-v="${v}">${v}</button>`).join("")}</span></span>
        <span class="fgroup"><label>小睡</label><input type="number" style="width:64px" data-dc="L" value="${d.L??""}"><span class="unit">min</span></span>
        <button class="btn ghost sm" data-nonap
          title="今天没小睡：记为 0 分钟，「小睡≤30」判为不达标（扣分）">${ICON.moon} 没小睡</button></div>
    </div></details>
    <details class="dsec" data-dsec="dream"${dsecOpen("dream") ? " open" : ""}>
      <summary class="dsec-h">${ICON.moon} 梦境 <span class="mini">先问做没做梦，再填次数和内容</span></summary>
      <div class="dsec-b">
      <div class="drow"><label>做梦了吗</label><span class="pillrow" id="d-m">${SEL_OPTS.M.map(v=>`<button class="pill ${d.M===v?"on":""}" data-v="${v}">${v}</button>`).join("")}</span>
        <span id="d-count-wrap" ${dreamed?"":"style='display:none'"}>
          <label>次数</label><input type="number" id="d-count" min="1" max="5" value="${n}" style="width:56px"></span></div>
      <div id="d-blocks">${dreamed ? dreamBlocks(d, n) : '<p class="mini">选了「不记得」就代表昨晚没做梦，不用填下面这些。</p>'}</div>
    </div></details>
    <details class="dsec" data-dsec="core"${dsecOpen("core") ? " open" : ""}>
      <summary class="dsec-h">${ICON.check} 核心打卡 · 计入完成率 <span class="mini">今天 ${Math.round(st.core*100)}% · 总 ${Math.round(st.total*100)}%</span></summary>
      <div class="dsec-b">
      <div class="drow wrap">
        ${checkItems("core").map(({col:c, name:n}) => {
          const v = c === "S" ? st.S : d[c];        // 用算好的口径：空=未填，不再误显示成 ×
          const sub = (c === "S" && +d.L === 0) ? "没小睡" : (v || "未填");
          return `<button class="tickbtn big ${v==="√"?"yes":(v==="×"?"no":"")}" data-dt="${c}" data-sauto="${c==="S"}">${esc(n)}<br>${sub}</button>`;
        }).join("")}
      </div>
      </div></details>
    <details class="dsec" data-dsec="bonus"${dsecOpen("bonus") ? " open" : ""}>
      <summary class="dsec-h">${ICON.check} 加分打卡 · 做了白赚，没做不扣分</summary>
      <div class="dsec-b">
      <div class="drow wrap">
        ${checkItems("bonus").map(({col:c, name:n}) => {
          const v = d[c];
          return `<button class="tickbtn ${v==="√"?"yes":(v==="×"?"no":"")}" data-dt="${c}">${esc(n)}<br>${v||"未打"}</button>`;
        }).join("")}
      </div>
      <div class="drow"><span class="fgroup"><label>运动类型</label><select data-dc="Z">${[""].concat(CHECK.opts.sport).map(o=>`<option ${d.Z===o?"selected":""}>${o}</option>`).join("")}</select></span>
        <span class="fgroup"><label>运动时长</label><input type="number" style="width:64px" data-dc="AA" value="${d.AA??""}"><span class="unit">min</span></span>
        <button class="btn ${d.Z === "未运动" ? "done" : "ghost"} sm" data-nosport
          title="今天未运动：记 0 分钟并标注，好在数据里和「忘记填」区分开">${d.Z === "未运动"
            ? `<span class="bi" data-icon="check"></span>今天未运动`
            : `<span class="bi" data-icon="run"></span>未运动`}</button>
        <span class="fgroup"><label>屏幕时长</label><input type="number" step="0.5" style="width:64px" data-dc="AB" value="${d.AB??""}"><span class="unit">h</span>
          <span class="mini">目标 ≤${s.screen} h</span></span></div>
      ${d.Z==="未运动" ? `<div class="mini" style="margin-top:6px">${ICON.run} 今天记为「未运动」。运动是加分项，不得分但也不扣分。</div>` : ""}
      </div></details>
    <details class="dsec" data-dsec="mood"${dsecOpen("mood") ? " open" : ""}>
      <summary class="dsec-h">${ICON.smile} 状态与备注</summary>
      <div class="dsec-b">
      <div class="drow"><label>心情</label><select data-dc="AF">${[""].concat(CHECK.opts.mood).map(o=>`<option ${d.AF===o?"selected":""}>${o}</option>`).join("")}</select>
        <label>精力</label><span class="pillrow" data-dc="AG">${[1,2,3,4,5].map(v=>`<button class="pill ${+d.AG===v?"on":""}" data-v="${v}">${v}</button>`).join("")}</span>
        <label>备注</label><input class="wide" data-dc="AH" value="${esc(d.AH||"")}" placeholder="想记什么写这里"></div>
      ${customItemsBlock(d)}
      </div></details>
  </div>`;
}

/* 用户在设置里自建的打卡项。
   上面那些是精心排过的手写表单（睡眠、小睡、运动、心情各成一组），
   自建项没法定制版面，就按类型排成一行一个，够用就行。
   **只列「手写表单里没有的」** —— 不然会跟上面那些重复一遍。 */
const CK_HANDWRITTEN = new Set(["C", "D", "I", "J", "K", "L", "M", "N", "O", "P",
                                "Q", "R", "S", "T", "U", "V", "W", "X", "Y",
                                "Z", "AA", "AB", "AC", "AD", "AE", "AF", "AG", "AH"]);
function customItemsBlock(d) {
  const mine = [...checkItems("core"), ...checkItems("bonus"), ...checkItems("other")]
    .filter(x => !CK_HANDWRITTEN.has(x.col) && x.kind !== "derived");
  if (!mine.length) return "";
  return `<div class="drow" style="flex-wrap:wrap;gap:10px;margin-top:10px">
    ${mine.map(x => {
      const v = d[x.col];
      const label = `<label>${esc(x.name)}</label>`;
      if (x.kind === "tick") {
        const on = v === "√";
        return `<span class="fgroup">${label}<button class="tickbtn big${on ? " yes" : ""}"
          data-custom="${esc(x.col)}">${on ? "√" : "—"}</button></span>`;
      }
      if (x.kind === "num") {
        return `<span class="fgroup">${label}<input type="number" style="width:74px"
          data-custom="${esc(x.col)}" value="${esc(v ?? "")}"></span>`;
      }
      if (x.kind === "time") {
        return `<span class="fgroup">${label}<input type="time"
          data-custom="${esc(x.col)}" value="${esc(v || "")}"></span>`;
      }
      if (x.kind === "sel") {
        const opts = String(x.opts || "").split(/[,，]/).map(s => s.trim()).filter(Boolean);
        return `<span class="fgroup">${label}<select data-custom="${esc(x.col)}">
          ${[""].concat(opts).map(o => `<option${v === o ? " selected" : ""}>${esc(o)}</option>`).join("")}
        </select></span>`;
      }
      return `<span class="fgroup">${label}<input class="wide" data-custom="${esc(x.col)}"
        value="${esc(v || "")}"></span>`;
    }).join("")}
  </div>`;
}
// 打卡项由后端给（设置页可改名、可隐藏）。后端没给就退回出厂清单，
// 免得老缓存或接口异常时整个单日面板空白 —— 列号是死的，不能改。
const CHECK_ITEMS_FALLBACK = {
  core: [["Q", "喝水1.5L ★"], ["R", "记账 ★"], ["S", "小睡≤30 ★"],
         ["T", "按时吃药 ★"], ["U", "少外卖奶茶 ★"]],
  bonus: [["V", "早起不赖床"], ["W", "吃早饭"], ["X", "学习/作业推进"], ["Y", "睡前洗漱"],
          ["AC", "收拾桌面/倒垃圾"], ["AD", "洗衣服/打水"], ["AE", "跟家人联系"]],
};
function checkItems(group) {
  const got = (CHECK && CHECK.items || {})[group];
  const list = (got && got.length)
    ? got : CHECK_ITEMS_FALLBACK[group].map(([col, name]) => ({col, name, on: true}));
  return list.filter(x => x.on !== false);
}

function dreamBlocks(d, n) {
  const dd = CHECK.dream_detail[d.date] || [];
  // 注意：下拉选项在 CHECK.opts，不在 CHECK.settings —— 之前写成 s.opts 会抛异常，
  // 导致「做梦了吗」一选就整个单日面板渲染失败、页面空白
  const opts = CHECK.opts || {};
  return [...Array(n)].map((_, i) => {
    const g = dd[i] || {};
    return `<div class="dreamblock"><b>梦 ${i+1}</b>
      <select data-db="type" data-i="${i}">${[""].concat(opts.dream_type || []).map(o=>`<option ${g.type===o?"selected":""}>${o}</option>`).join("")}</select>
      <select data-db="mood" data-i="${i}">${[""].concat(opts.dream_mood || []).map(o=>`<option ${g.mood===o?"selected":""}>${o}</option>`).join("")}</select>
      <select data-db="clarity" data-i="${i}">${[""].concat(opts.clarity || []).map(o=>`<option ${g.clarity===o?"selected":""}>${o}</option>`).join("")}</select>
      <input data-db="content" data-i="${i}" value="${esc(g.content||"")}" placeholder="梦到了什么…" style="flex:2">
      <input data-db="read" data-i="${i}" value="${esc(g.read||"")}" placeholder="现实联想/解读" style="flex:1">
    </div>`;
  }).join("") + `<button class="btn" id="d-save-dream">${ICON.save} 保存梦境</button>
    <span class="mini">保存后写进梦境明细，当天的数据也跟着更新</span>`;
}
function bindDayPanel(m) {
  const d = m.days.find(x => x.day === +checkDay) || m.days[0];
  const idx = m.days.indexOf(d);
  const panel = $("#ck-day");        // 全部绑定限定在单日面板内，避免误伤其他按钮
  if (!panel) return;
  $("#d-prev").onclick = () => { if (m.days[idx-1]) { checkDay = m.days[idx-1].day; renderCheckData(); } };
  $("#d-next").onclick = () => { if (m.days[idx+1]) { checkDay = m.days[idx+1].day; renderCheckData(); } };
  $("#d-today").onclick = () => {
    const tm = monthNameOf(todayStr());
    const same = checkMonth === tm;
    checkMonth = tm;
    checkDay = +todayStr().slice(8,10);
    renderCheckData();
    if (!same) renderCheckCharts();
  };
  // 普通单元格控件：改动即存
  $$("[data-dc]", panel).forEach(el => {
    if (el.classList.contains("pillrow")) {
      $$("button", el).forEach(b => b.onclick = () => {
        const v = +b.dataset.v === +d[el.dataset.dc] ? "" : b.dataset.v;
        saveDayCell(d, m, el.dataset.dc, v);
      });
      return;
    }
    el.addEventListener("change", () => saveDayCell(d, m, el.dataset.dc, el.value));
  });
  // 自建打卡项（设置里加的）。打勾的那几个是按钮，其余是普通输入框。
  $$("[data-custom]", panel).forEach(el => {
    if (el.tagName === "BUTTON") {
      el.onclick = () => saveDayCell(d, m, el.dataset.custom,
                                     d[el.dataset.custom] === "√" ? "" : "√");
      return;
    }
    el.addEventListener("change", () => saveDayCell(d, m, el.dataset.custom, el.value));
  });
  // 「未运动」：一键把运动类型标为未运动、时长记 0（加分项，不得分也不扣分）
  const nosport = $("[data-nosport]", panel);
  if (nosport) nosport.onclick = () => {
    if (d.Z === "未运动") {                       // 再点一下取消
      saveDayCells(d, m, {Z: "", AA: ""});
      return;
    }
    saveDayCells(d, m, {Z: "未运动", AA: 0});
  };
  // 「没小睡」：一键把小睡记 0，小睡≤30 随即判为不达标（扣分）
  const nonap = $("[data-nonap]", panel);
  if (nonap) nonap.onclick = () => {
    if (+d.L === 0) { toast("今天已经记过「没小睡」了"); return; }
    saveDayCell(d, m, "L", 0);
  };
  // 打勾按钮：√ → × → 空
  $$("[data-dt]", panel).forEach(btn => btn.onclick = () => {
    if (btn.dataset.sauto === "true") { toast("小睡≤30 由「小睡(min)」自动推"); return; }
    const c = btn.dataset.dt;
    const next = d[c] === "√" ? "×" : (d[c] === "×" ? "" : "√");
    saveDayCell(d, m, c, next);
  });
  // 做梦了吗（保存 M + dreamed）
  $$("#d-m .pill", panel).forEach(b => b.onclick = () => {
    const v = b.dataset.v;
    const dreamed = v !== "不记得";
    post("/api/dream/save", {date: d.date, dreamed, m: v, dreams: currentDreamBlocks()}).then(r => {
      if (r.ok) { toast(r.msg); syncDreamLocal(d, dreamed, v, currentDreamBlocks()); renderCheckData(); }
      else toast(r.msg, true);
    });
  });
  $("#d-count").addEventListener("change", () => renderCheckData());   // 只改块数，点保存才落库
  const sb = $("#d-save-dream");
  if (sb) sb.onclick = async () => {
    const v = ($("#d-m .pill.on") || {}).dataset?.v || "不记得";
    const dreamed = v !== "不记得";
    busy();
    const r = await post("/api/dream/save", {date: d.date, dreamed, m: v, dreams: currentDreamBlocks()});
    if (r.ok) { toast(r.msg); syncDreamLocal(d, dreamed, v, currentDreamBlocks()); renderCheckData(); }
    else toast(r.msg, true);
  };
}
function currentDreamBlocks() {
  const out = [];
  const panel = $("#ck-day") || document;      // 只读单日面板里的梦境块
  $$("[data-db='type']", panel).forEach((el, i) => {
    out[i] = out[i] || {};
    out[i].type = el.value;
  });
  $$("[data-db='mood']", panel).forEach((el, i) => out[i].mood = el.value);
  $$("[data-db='clarity']", panel).forEach((el, i) => out[i].clarity = el.value);
  $$("[data-db='content']", panel).forEach((el, i) => out[i].content = el.value);
  $$("[data-db='read']", panel).forEach((el, i) => out[i].read = el.value);
  return out;
}
function syncDreamLocal(d, dreamed, mVal, dreams) {
  d.M = mVal;
  if (dreamed && dreams.length) {
    d.N = dreams[0].type || "";
    d.O = dreams[0].mood || "";
    d.P = dreams.map(g => (g.content || "").trim()).join("、").slice(0, 50);
  } else {
    d.N = d.O = d.P = "";
  }
  if (dreamed && dreams.length) CHECK.dream_detail[d.date] = dreams;
  else delete CHECK.dream_detail[d.date];
}
// 一次改多格（如「未运动」要同时写类型和时长）：写完全部再重绘一次，避免闪两下
async function saveDayCells(d, m, pairs) {
  busy();
  let failed = null;
  for (const [col, value] of Object.entries(pairs)) {
    const r = await post("/api/check/set", {sheet: m.name, day: d.day, col, value});
    if (r.ok) d[col] = value;
    else { failed = r.msg; break; }
  }
  if (failed) toast(failed, true);
  else toast("已记录");
  renderCheckData();
  renderCheckCharts();
}
async function saveDayCell(d, m, col, value) {
  busy();
  const r = await post("/api/check/set", {sheet: m.name, day: d.day, col, value});
  if (r.ok) {
    d[col] = value;
    toast(r.msg);
    renderCheckData();          // 局部刷新；图表只更新数据不重建 DOM
    renderCheckCharts();
  } else toast(r.msg, true);
}
function dreamList() {
  const dates = Object.keys(CHECK.dream_detail).sort().reverse().slice(0, 20);
  if (!dates.length) return emptyBox("还没有录过梦",
    "打卡页选中某天 → 「做梦了吗」选清晰/模糊记得 → 填次数和内容");
  const rows = dates.map(dt => {
    const gs = CHECK.dream_detail[dt];
    return `<tr><td>${dt}</td><td>${gs.map(g => `<div style="padding:2px 0">[${g.seq||"?"}] ${esc(g.type)} · ${esc(g.mood)} · ${esc(g.clarity)}　${esc(g.content)}</div>`).join("")}</td></tr>`;
  }).join("");
  return `<details open><summary>最近 ${dates.length} 天有梦</summary>
    <table><thead><tr><th style="width:110px">日期</th><th>梦境明细</th></tr></thead><tbody>${rows}</tbody></table></details>`;
}

/* ================================================================
   ④ 物资
================================================================ */
const STOCK_DEF = {
  "药品": [
    ["A","药名","text",150],["B","是否开封","sel:已开封,未开封"],["C","有效日期","date"],
    ["Q","开封日期","date"],["R","开封后(月)","num",86],
    ["D","数量","num",62],["E","单位","text",56],["F","最低库存","num",72],
    ["_restock","补货状态","badge"],["_days","剩余天数","plain"],["_status","效期状态","badge"],
    ["_open_exp","开封后到期","plain"],
    ["J","备注","text",160]],
  "日用品": [
    ["A","名称","text",130],["B","类别","sel:日用品,护肤品"],["C","开封日期","date"],
    ["R","开封后(月)","num",86],
    ["D","生产日期","date"],["E","保质期(月)","num",74],["F","包装到期日","date"],
    ["J","数量","num",62],["K","单位","text",56],["L","最低库存","num",72],
    ["_restock","补货","badge"],["_days","剩余天数","plain"],["_status","状态","badge"],
    ["_open_exp","开封后到期","plain"],
    ["N","备注","text",150]],
  "零食": [
    ["A","名称","text",130],["B","生产日期","date"],["C","保质期","num",62],
    ["D","单位","sel:月,天,周",60],["N","有效期(直接填)","date"],
    ["Q","开封日期","date"],["R","开封后(月)","num",86],
    ["H","是否食用","sel:未食用,已食用"],
    ["I","数量","num",62],["J","数量单位","text",66],["K","最低库存","num",72],
    ["_restock","补货","badge"],["_days","剩余天数","plain"],["_status","状态","badge"],
    ["_open_exp","开封后到期","plain"],
    ["M","备注","text",140]],
};
const STOCK_ADD_FIELDS = {
  "药品": [["name","药名","text",150],["B","是否开封","sel:已开封,未开封"],["C","有效日期","date"],
           ["Q","开封日期","date"],["R","开封后(月)","num",86],
           ["D","数量","num",64],["E","单位","text",56],["F","最低库存","num",72],
           ["J","备注","text",160]],
  // ⚠ 这张表要**覆盖下面表格里的全部输入列**。以前只列了一小半，
  // 于是「新增」时填不了开封日期/生产日期/保质期/包装到期日 ——
  // 得先存下来再去表格里补，可表格里那些列明明有，看着就像功能丢了。
  "日用品": [["name","名称","text",130],["B","类别","sel:日用品,护肤品"],
             ["C","开封日期","date"],["D","生产日期","date"],["E","保质期(月)","num",74],
             ["F","包装到期日","date"],["J","数量","num",64],
             ["K","单位","text",56],["L","最低库存","num",72],
             ["N","备注","text",150]],
  "零食": [["name","名称","text",130],["B","生产日期","date"],["C","保质期","num",64],
           ["D","单位","sel:月,天,周",60],["N","有效期(直接填)","date"],
           ["Q","开封日期","date"],["R","开封后(月)","num",86],
           ["I","数量","num",64],["J","数量单位","text",64],["K","最低库存","num",72]],
};
async function loadStock() {
  const r = await get("/api/stock");
  if (!r.ok) return toast(r.msg, true);
  STOCK = r.data;
  clearDirty("stock"); syncStamp();
  idle();
  renderStock();
}
function renderStock() {
  const o = STOCK;
  const alerts = [];
  for (const name of ["药品","日用品","零食"]) {
    for (const row of o.sheets[name].rows) {
      if (row._restock) alerts.push(`<b>需补货</b> · ${name}「${esc(row.A||"?")}」剩 ${row.D ?? row.J ?? row.I ?? "?"} ${esc(row.E ?? row.K ?? row.J ?? "")}`);
      if (row._status === "已过期") alerts.push(`<b class="r">已过期</b> · ${name}「${esc(row.A||"?")}」`);
      else if (row._status === "临期") alerts.push(`<b class="a">临期</b> · ${name}「${esc(row.A||"?")}」剩 ${row._days} 天`);
    }
  }
  const pills = Object.keys(STOCK_DEF).map(n =>
    `<button class="pill ${n===stockSheet?"on":""}" data-s="${n}">${n}</button>`).join("");
  $("#tab-stock").innerHTML = `
  <div class="pagehead">
    <div class="ph-title">${ICON.box} 物资</div>
    <div class="ph-sub">共 ${o.overview.reduce((a, v) => a + v.total, 0)} 条 ·
      ${o.overview.map(v => `${v.cat} ${v.total}`).join(" · ")}</div>
  </div>
  <div class="kpis">
    ${o.overview.map(v => kpi(v.cat, v.total + " 条",
      v.expired>0?"r":(v.soon>0?"a":"g"), "var(--blue)",
      `过期${v.expired} · 临期${v.soon} · 待补货${v.restock}`)).join("")}
  </div>
  ${alerts.length ? `<div class="warn">⚠ 有 ${alerts.length} 条提醒：<br>${alerts.join("<br>")}</div>`
    : `<div class="ok">✔ 没有过期、临期或需补货的物资</div>`}
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="grid-tab">${pills}</div>
    ${stockTable(stockSheet)}
  </div>
  <div class="foot">改动直接存进数据库；剩余天数 / 效期状态 / 补货状态 / 开封后到期
  都是<b>现算的</b>，存的是日期和数量这些原料，不会悄悄变假</div>`;
  /* ⚠「加载更多」**同步绑**，不能放进下面那个 setTimeout。
     原因：setTimeout(...,0) 要等一轮事件循环，在那之前这个按钮是**没有 onclick** 的 ——
     任何"渲染完立刻点"的路径（连点、程序化点击、测试）都会点在空气上。
     这个按钮只追加行、不重画整页，所以它自己不会被换掉，绑一次就一直有效。
     （其余控件仍然放 setTimeout 里 —— 它们要等 DOM 都就位，那个时机是原来就对的。） */
  const _more = $("#st-more");
  if (_more) _more.onclick = () => stockLoadMore(stockSheet);
  setTimeout(() => {
    $$("#tab-stock [data-s]").forEach(b => b.onclick = () => {
      stockSheet = b.dataset.s;
      stockLimit = 10;              // 换一张表就回到「先看 10 条」，别把上一张的页码带过来
      renderStock();
    });
    bindStockCells();
    bindStockAdd();
  }, 0);
}

/* ================================================================
   ③+ 待办（独立一页）

   以前它挂在物资页最底下，得滚到底才看得见 —— 而「今天要干什么」
   是每天都要看的东西，跟「寝室里有什么」是两回事。拆开各归各的。
================================================================ */
/** 待办改完之后刷新。**两边都可能要看** ——
 *  待办页要它自己刷新，物资页和总览上的「待办未完成」也跟着变。
 *  以前这里直接 loadStock()，人在待办页按了按钮，刷的却是藏起来的物资页，
 *  眼前那一条纹丝不动，看着就像没生效。 */
async function refreshStockAndTodo() {
  STOCK = null;
  const r = await get("/api/stock");
  if (!r.ok) return toast(r.msg, true);
  STOCK = r.data;
  clearDirty("stock", "todo");
  if ($("#tab-stock") && !$("#tab-stock").hidden) renderStock();
  if ($("#tab-todo") && !$("#tab-todo").hidden) renderTodoPage();
  markDirty("over");          // 总览上有「待办未完成」那张卡
}

async function loadTodoPage() {
  const r = await get("/api/stock");
  if (!r.ok) return toast(r.msg, true);
  STOCK = r.data;
  clearDirty("stock");
  renderTodoPage();
}

function renderTodoPage() {
  // ⚠ 每次进这一页都把筛选条件清掉。理由：筛完「只看高优先级」再切走、
  //   数据刷新后回来，如果筛选还留着，页头说「12 件没做完」而表里只有 3 条，
  //   看起来就像待办丢了。宁可每次从头看全部。
  todoFilter = {cats: [], pri: "", stat: "open", q: ""};
  const all = (STOCK && STOCK.todo) || [];
  const open = all.filter(t => t.stat !== "已完成");
  const late = open.filter(t => t.days !== null && t.days < 0);
  const soon = open.filter(t => t.days !== null && t.days >= 0 && t.days <= 3);
  $("#tab-todo").innerHTML = `
  <div class="pagehead">
    <div class="ph-title">${ICON.list} 待办</div>
    <div class="ph-sub">${open.length} 件没做完${
      late.length ? ` · <b class="r">${late.length} 件已过期</b>` : ""}${
      soon.length ? ` · <b class="a">${soon.length} 件三天内到期</b>` : ""}</div>
  </div>
  ${late.length ? `<div class="warn">已经过了截止日：${
    late.map(t => esc(t.item) + "（" + Math.abs(t.days) + " 天前）").join("、")}</div>` : ""}
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">${todoFilterBar()}
    <div id="tf-cats" class="rf-cats"></div>
    <div id="todo-box"></div>
  </div>
  <div class="foot">删除会先进回收站（设置 → 数据 → 回收站），随时能捡回来。</div>`;
  setTimeout(() => renderTodoBox(), 0);
}
/** 把一批物资行渲染成 <tr>。
 *  ⚠ 抽出来是为了「加载更多」能**直接追加行**，不必整页重画 renderStock()。
 *    为什么不能重画：renderStock() 用 `setTimeout(...,0)` 绑事件，
 *    而重画之后那个新按钮**在下一轮事件循环之前是没有 onclick 的** ——
 *    于是「连点两次加载更多」第二次点在空气上（B1 那族：元素在、事件没绑）。
 *    改为追加行 + **同步**绑按钮，点几次都立刻生效，也不会有整页闪一下。 */
function stockRowHtml(name, r, blankCol) {
  const cols = STOCK_DEF[name];
  const isSnack = name === "零食";
  const isDrug = name === "药品";
  const eaten = r.H === "已食用";
  const hasAI = isDrug && (r.K || r.L || r.M || r.N);
  return `<tr class="${eaten?"eaten":""}">
    ${cols.map(([c, label, typ]) => {
      if (typ === "badge") return `<td>${stockBadge(c, r[c])}</td>`;
      if (typ === "plain") return `<td class="${r[c] != null && r[c] < 0 ? "r" : "muted"}">${r[c] ?? ""}</td>`;
      // 零食的「数量」格子旁边挂一个「吃掉 1 个」—— 用户原话是
      // 「我点击未食用，它就会减少一个」，也就是希望**在数量那儿一点就减**。
      // 原来只有"操作"列最右边那个按钮，离数量太远、不好找。
      // ⚠⚠ 按钮必须和 .editcell **并列**，不能嵌在它里面：
      //   .editcell 的点击就是「打开编辑框」（bindStockCells），
      //   嵌进去的话点「−1」会一起冒泡上去，编辑框当场打开 —— 点一下干两件事。
      //   （第一版就是这么写的，写在这里免得以后有人"顺手"挪回去。）
      if (name === "零食" && c === "I") {
        const qty = r[c] == null || r[c] === "" ? "—" : stockText(r[c], typ);
        return `<td class="nowrap"><span class="editcell" data-sheet="${name}" data-row="${r.row}"
          data-col="${c}" data-typ="${typ}">${qty}</span>${
          eaten ? "" : `<button class="btn ghost sm eatone" data-eat="${r.row}"
            title="吃掉 1 个：数量减 1，减到 0 会自动标成「已食用」">−1</button>`}</td>`;
      }
      const cls = [blankCol[c] ? "narrow" : "", typ === "date" ? "nowrap" : ""].filter(Boolean).join(" ");
      return `<td${cls ? ` class="${cls}"` : ""}><span class="editcell" data-sheet="${name}" data-row="${r.row}" data-col="${c}"
        data-typ="${typ}">${stockText(r[c], typ)}</span></td>`;
    }).join("")}
    <td class="opcol" style="white-space:nowrap">
      ${isSnack ? `<button class="btn ghost sm" data-eat="${r.row}">${ICON.cart} 吃掉1个</button>
      <button class="btn ${eaten?"ghost":"warn"} sm" data-cross="${r.row}">${eaten?"恢复":"划掉"}</button>` : ""}
      ${isDrug ? `<button class="btn ${hasAI?"ghost":""} sm opbtn" data-ai="${r.row}"
        title="让 AI 生成「针对疾病/使用方法/功效/副作用」，核对后再保存">${ICON.robot} AI</button>` : ""}
      <button class="btn ghost sm opbtn" data-shelf="${r.row}"
        title="问 AI：这个东西开封之后大概还能用多久？结果会先填进「开封后(月)」那一格，你看过觉得不合适可以直接改">${ICON.robot} 开封后多久</button>
    </td></tr>`;
}

function stockTable(name) {
  const {rows} = STOCK.sheets[name];
  // 整列一个值都没有的列（比如某类物资没人填过「最低库存」）就压窄。
  // 27 行药里「最低库存」「补货状态」全是「—」，白占着宽度，
  // 挤得药名要折行 —— 表格越宽越难看，信息密度反而更低。
  const cols = STOCK_DEF[name];
  const blankCol = {};
  cols.forEach(([c, _l, typ]) => {
    blankCol[c] = rows.length > 0 && rows.every(r => r[c] == null || r[c] === "");
  });
  const head = cols.map(([c, label]) =>
    `<th${blankCol[c] ? ' class="narrow" title="这一列目前整列都是空的"' : ""}>${label}</th>`).join("")
    + '<th class="opcol">操作</th>';
  /* 分页（2.4.7）：一次先显示 10 条，剩下的点「加载更多」。
     ⚠ 只切**显示**，一行都没少 —— 列宽挤压的判断（上面 blankCol）仍然拿**全部**行算，
       否则「加载到第 2 页时某一列突然变宽」会让人以为数据变了。
     ⚠ 也不动任何后端查询。 */
  const shown = rows.slice(0, stockLimit);
  const rest = rows.length - shown.length;
  const trs = shown.map(r => stockRowHtml(name, r, blankCol)).join("");
  const more = rest > 0
    ? `<div style="text-align:center;margin-top:12px">
         <button class="btn ghost" id="st-more">加载更多（还有 ${rest} 条）</button></div>`
    : "";
  const count = `<div class="mini" id="st-count" style="margin:8px 0">共 ${rows.length} 条${
    rest > 0 ? `，显示前 ${shown.length} 条` : ""}</div>`;
  return `${stockAddForm(name)}
    ${count}
    <table class="stocktable"><thead><tr>${head}</tr></thead><tbody>${trs}</tbody></table>
    ${more}`;
}

/** 「加载更多」：**只追加 10 行**，不重画整页。
 *  追加的格子要重新绑编辑事件，所以调 bindStockCells()（它只认新格子，不会重复绑老的）。 */
function stockLoadMore(name) {
  const {rows} = STOCK.sheets[name];
  const tbody = document.querySelector("#tab-stock table.stocktable tbody");
  if (!tbody) return;
  const cols = STOCK_DEF[name];
  const blankCol = {};
  cols.forEach(([c, _l, typ]) => {
    blankCol[c] = rows.length > 0 && rows.every(r => r[c] == null || r[c] === "");
  });
  const from = stockLimit;
  stockLimit += 10;
  const next = rows.slice(from, stockLimit);
  tbody.insertAdjacentHTML("beforeend",
    next.map(r => stockRowHtml(name, r, blankCol)).join(""));
  bindStockCells();                 // 新格子才有编辑行为；老格子不动
  const rest = rows.length - stockLimit;
  const cnt = document.querySelector("#st-count");
  if (cnt) cnt.textContent = `共 ${rows.length} 条${rest > 0 ? `，显示前 ${stockLimit} 条` : ""}`;
  const more = document.querySelector("#st-more");
  if (more) {
    if (rest > 0) more.textContent = `加载更多（还有 ${rest} 条）`;
    else more.remove();             // 加载完了就把按钮撤掉
  }
}
function stockAddForm(name) {
  return `<details class="addform"><summary>＋ 新增一条${name}</summary>
    <div class="form" id="st-form">
    ${STOCK_ADD_FIELDS[name].map(([c, label, typ]) => {
      const id = "sa-" + c;
      // 名称那一格挂上历史补全（药品/日用品/零食各自的池子）
      const sug = c === "name" ? ` data-sug="${SUG_KIND[name]}"` : "";
      if (typ === "text") return `<div class="f"><label>${label}</label><input id="${id}"${sug} style="min-width:${typ.endsWith("text")?110:70}px"></div>`;
      if (typ === "num") return `<div class="f"><label>${label}</label><input id="${id}" type="number"></div>`;
      if (typ === "date") return `<div class="f"><label>${label}</label><input id="${id}" type="date"></div>`;
      if (typ.startsWith("sel")) return `<div class="f"><label>${label}</label><select id="${id}">${typ.slice(4).split(",").map(o=>`<option>${o}</option>`).join("")}</select></div>`;
    }).join("")}
    <button class="btn" id="st-save">保存</button></div></details>`;
}
function bindStockAdd() {
  const sb = $("#st-save");
  if (!sb) return;
  sb.onclick = async () => {
    const body = {sheet: stockSheet, name: $("#sa-name").value.trim()};
    for (const [c, label, typ] of STOCK_ADD_FIELDS[stockSheet]) {
      if (c === "name") continue;
      const v = $("#sa-" + c).value;
      if (v !== "") body[c] = v;
    }
    if (!body.name) return toast("先填名称", true);
    busy();
    const r = await post("/api/stock/add", body);
    if (r.ok) { toast(r.msg); STOCK = null; await loadStock(); } else toast(r.msg, true);
  };
}
function stockBadge(c, v) {
  if (c === "_restock") return v ? '<span class="badge tagr">需补货</span>' : '<span class="muted">–</span>';
  const map = {"已过期":"tagr","临期":"tagw","正常":"tagg","长期有效":"tagv","已食用":"tagd"};
  return v ? `<span class="badge ${map[v]||"tagd"}">${v}</span>` : '<span class="muted">–</span>';
}
function stockText(v, typ) {
  if (v === "" || v == null) return '<span class="muted">–</span>';
  if (typ === "date") return String(v).slice(0, 10);
  return esc(v);
}
function bindStockCells() {
  $$("#tab-stock .editcell").forEach(cell => cell.onclick = () => {
    if (cell.querySelector("input,select")) return;
    const {sheet, row, col, typ} = cell.dataset;
    const cur = (STOCK.sheets[sheet].rows.find(r => r.row === +row) || {})[col];
    let el;
    if (typ === "text") {
      // 名称列（A）挂历史补全
      const sug = col === "A" ? ` data-sug="${SUG_KIND[sheet]}"` : "";
      el = `<input value="${esc(cur||"")}"${sug} style="min-width:110px">`;
    }
    else if (typ === "num") el = `<input type="number" value="${cur??""}" style="width:72px">`;
    else if (typ === "date") el = `<input type="date" value="${String(cur||"").slice(0,10)}">`;
    else if (typ.startsWith("sel")) el = `<select>${typ.slice(4).split(",").map(o =>
      `<option ${String(cur)===o?"selected":""}>${o}</option>`).join("")}</select>`;
    cell.innerHTML = el;
    const inp = cell.firstChild;
    inp.focus();
    const commit = async () => {
      busy();
      const r = await post("/api/stock/set", {sheet, row: +row, col, value: inp.value});
      if (r.ok) { toast(r.msg); STOCK = null; await loadStock(); } else { toast(r.msg, true); cell.textContent = cur || ""; }
    };
    inp.addEventListener("change", commit);
    inp.addEventListener("keydown", e => { if (e.key === "Enter") commit(); if (e.key === "Escape") cell.textContent = cur || ""; });
  });
  // 零食：吃掉 / 划掉
  $$("#tab-stock [data-eat]").forEach(btn => btn.onclick = async () => {
    busy();
    const r = await post("/api/stock/eat", {row: +btn.dataset.eat});
    if (r.ok) { toast(r.msg); STOCK = null; await loadStock(); } else toast(r.msg, true);
  });
  $$("#tab-stock [data-cross]").forEach(btn => btn.onclick = async () => {
    const row = STOCK.sheets["零食"].rows.find(r => r.row === +btn.dataset.cross);
    const next = row.H === "已食用" ? "未食用" : "已食用";
    busy();
    const r = await post("/api/stock/set", {sheet: "零食", row: row.row, col: "H", value: next});
    if (r.ok) { toast(r.msg); STOCK = null; await loadStock(); } else toast(r.msg, true);
  });
  $$("#tab-stock [data-ai]").forEach(btn => btn.onclick = () => {
    const row = STOCK.sheets["药品"].rows.find(r => r.row === +btn.dataset.ai);
    if (row) drugAIModal(row);
  });
  // 三张表都有：问 AI「开封之后还能用多久」
  $$("#tab-stock [data-shelf]").forEach(btn => btn.onclick = () =>
    shelfAsk(stockSheet, +btn.dataset.shelf));
}

/** 「开封后多久不能用了」——
 *  AI 只给建议，**填进输入框让他自己确认**。这东西直接决定他会不会把
 *  一瓶开了三个月的眼药水往眼睛里滴，不能让模型一句话就定了，所以他得看见、
 *  得能改。所以这里不静默写库，走的是「填好 → 他自己点保存」。
 */
async function shelfAsk(sheet, rowId) {
  const row = STOCK.sheets[sheet].rows.find(r => r.row === rowId);
  if (!row) return;
  busy();
  const r = await post("/api/ai/shelf", {sheet, name: row.A || "", note: row.N || row.J || row.M || ""});
  idle();
  if (!r.ok) return toast(r.msg, true);
  const {months, why} = r.data;
  modal(`开封后建议用完`, `
    <p style="margin:0 0 10px">「${esc(row.A || "")}」——AI 估的是
      <b>开封后 ${months} 个月</b>${why ? `<span class="mini">（${esc(why)}）</span>` : ""}。</p>
    <p class="mini" style="margin:0 0 10px">
      这是按同类东西的通用常识估的，<b>以包装说明为准</b>；觉得不合适直接改下面的数字。</p>
    <div class="form"><div class="f"><label>开封后可用月数</label>
      <input id="sh-m" type="number" step="0.5" min="0.1" value="${months}"></div></div>`,
    async () => {
      const m = ($("#sh-m") || {}).value;
      if (m === undefined) return false;
      busy();
      const rr = await post("/api/stock/set", {sheet, row: rowId, col: "R", value: m});
      if (!rr.ok) { toast(rr.msg, true); return false; }
      toast("已填好。别忘了填「开封日期」，填了才会按它算到期日");
      STOCK = null; await loadStock();
    }, "robot");
}
/* ---- 待办 ---- */
/** 待办表格。
 *  ⚠ 不传参 = 全部（总览页那张提醒卡就是这么调的）。
 *    传一组 row 号 = 只画这几条（待办页的筛选结果）。
 *    这样两个调用点共用同一张表和同一套按钮绑定，不会长出第二份要单独维护的表格。 */
function todoCard(onlyRows) {
  const pick = onlyRows ? STOCK.todo.filter(t => onlyRows.includes(t.row)) : STOCK.todo;
  const items = onlyRows ? pick.slice().sort((a, b) => onlyRows.indexOf(a.row) - onlyRows.indexOf(b.row)) : pick;
  const rows = items.map(t => {
    const done = t.stat === "已完成";
    const days = t.days === null ? "" : (t.days < 0 ? `逾期 ${-t.days} 天` : `剩 ${t.days} 天`);
    return `<tr class="${done?"voidrow":""}">
      <td><button class="btn ${done?"ghost":"warn"} sm" data-todo-toggle="${t.row}">${done?"↩ 恢复":"✔ 完成"}</button></td>
      <td>${esc(t.item)}</td>
      <td><span class="badge tagd">${esc(t.cat||"—")}</span></td>
      <td>${t.due||"—"}</td>
      <td class="${t.days!==null&&t.days<0&&!done?"r":""}">${days}</td>
      <td>${esc(t.pri)}</td>
      <td class="muted">${esc(t.note)}</td>
      <td style="white-space:nowrap">
        <!-- 加到日历（2.4.5）。⚠ 只给**未完成的**行 —— 做完了的不用提醒，
             日历是拿来提醒「还要做什么」的。已完成的那些行这里空着。 -->
        ${done ? "" : `<button class="btn ghost sm" data-todo-ics="${t.row}"
          title="${t.due ? "把这条加到日历（当天和前一天各提醒一次）"
                         : "先在「截止日期」里填一天，才能加到日历"}">${ICON.calendar}</button>`}
        <button class="btn ghost sm" data-todo-edit="${t.row}">改</button>
        <button class="btn warn sm" data-todo-del="${t.row}">删</button></td></tr>`;
  }).join("");
  return `
    <details open><summary>＋ 添加待办</summary>${todoForm()}</details>
    ${items.length ? `<table><thead><tr><th></th><th>事项</th><th>类别</th><th>截止日期</th><th>剩余</th><th>优先级</th><th>备注</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>` : emptyBox("还没有待办", "用上面的「＋ 添加待办」加一条")}`;
}

/* ---- 待办筛选（纯前端过滤，跟账单页 recFilter 同一套写法）--------------
   数据本来就全在 STOCK.todo 里，点一下立刻出结果，不请求后端、不重查库。
   ⚠ 只作用于 #tab-todo 这个整页视图。总览页那张提醒卡**故意不跟着筛** ——
     它是用来提醒「还有什么事没做」的，被筛选条件藏掉就成了会漏事的卡。 */
let todoFilter = {cats: [], pri: "", stat: "open", q: ""};
const todoFiltering = () => !!(todoFilter.cats.length || todoFilter.pri
                               || todoFilter.stat !== "open" || todoFilter.q.trim());

function todoFiltered() {
  const f = todoFilter, q = f.q.trim().toLowerCase();
  return STOCK.todo.filter(t => {
    if (f.stat === "open" && t.stat === "已完成") return false;
    if (f.stat === "done" && t.stat !== "已完成") return false;
    // ⚠ 字符串比较前先 trim：待办表单不会产生空格，但写待办的调用方不止表单一个
    //   （AI 从日记里提出来的待办、导入），不 trim 就可能「点了没筛出来，其实是空格」。
    if (f.cats.length && !f.cats.includes(String(t.cat || "").trim())) return false;
    if (f.pri && String(t.pri || "").trim() !== f.pri) return false;
    if (q) {
      const hay = `${t.item || ""} ${t.cat || ""} ${t.pri || ""} ${t.note || ""} ${t.due || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/* ⚠ 筛选条**分成两半**渲染，这是为了不毁掉正在打字的那只输入框：
     固定的一半（搜索框 + 两个下拉 + 清空）**不进** #todo-box，
     重渲染时不会被替换，所以光标和输入内容都保得住 ——
     否则每打一个字就被重建一次，焦点当场丢掉（账单页当初也踩过这个）。
     会变的一半（类别按钮）跟着明细一起重渲染。
   ⚠ 另外：这段和 bindTodo() 里的查询都**必须**限定在 #tf-fixed / #todo-box 内。
     全文档选择器会误伤别的页面 —— 待办那几个「点了没反应」的坑就是这么来的。 */
function todoFilterBar() {
  return `<div class="recfilter">
    <div class="rf-row" id="tf-fixed">
      <input id="tf-q" placeholder="搜事项 / 类别 / 备注…" value="${esc(todoFilter.q)}">
      <select id="tf-stat">
        <option value="open"${todoFilter.stat === "open" ? " selected" : ""}>只看没做完</option>
        <option value="done"${todoFilter.stat === "done" ? " selected" : ""}>只看已完成</option>
        <option value="all"${todoFilter.stat === "all" ? " selected" : ""}>全都看</option>
      </select>
      <select id="tf-pri">
        <option value="">全部优先级</option>
        ${["高", "中", "低"].map(p => `<option value="${p}"${todoFilter.pri === p ? " selected" : ""}>${p}</option>`).join("")}
      </select>
      ${todoFiltering() ? `<button class="btn ghost sm" id="tf-clear">清空筛选</button>` : ""}
    </div>
    <div class="rf-cats" id="tf-cats"></div>
  </div>`;
}

/** 类别按钮那一行。它跟明细一起重渲染，所以单独一个函数供两处调用。 */
function todoCatChips() {
  // 跟账单页一样：只列**当前待办里真实出现过**的类别，免得列一堆空按钮
  const cats = [...new Set(STOCK.todo.map(t => String(t.cat || "").trim()).filter(Boolean))];
  return cats.map(c => `<button class="rf-cat${todoFilter.cats.includes(c) ? " on" : ""}"
    data-tfcat="${esc(c)}" title="点一下只看这个类别，可以多选">${esc(c)}</button>`).join("");
}

/** 明细那一半：类别按钮 + 「共几条」+ 表格。 */
function todoBox() {
  const all = STOCK.todo;
  const rows = todoFiltered();
  return `${todoCatChips()}
    <div class="mini reclimit" style="margin:8px 0"><span>共 ${all.length} 条${
      todoFiltering() ? ` · <b>筛选后 ${rows.length} 条</b>` : ""}</span></div>
    ${rows.length ? todoCard(rows.map(t => t.row))
      : emptyBox("没有符合筛选条件的待办",
                 "试试清空筛选，或者把「只看没做完」换成「全都看」")}`;
}

/** 只重渲染会变的那一半（#tf-cats + #todo-box），不整页重画。
    ⚠ 这样做的唯一目的是**保住 #tf-q 那个正在打字的输入框** ——
      整页重渲染会把它重建一次，光标和内容当场丢掉。
    ⚠ 重渲染之后必须重新绑一次事件（里面全是新造的按钮）。
      这里直接复用 bindTodo() 整份，不另起第二份绑定清单 ——
      手抄清单漏一处，就长出「点了没反应」的死按钮（交接文档 B1，栽过 5 次）。 */
function renderTodoBox() {
  const cats = $("#tf-cats");
  if (cats) cats.innerHTML = todoCatChips();
  const box = $("#todo-box");
  if (box) box.innerHTML = todoBox();
  bindTodo();
}
function todoForm(t) {
  const r = t || {};
  return `<div class="form">
    <div class="f"><label>事项</label><input id="td-item" data-sug="todo" value="${esc(r.item||"")}" style="min-width:180px" placeholder="要做什么"></div>
    <div class="f"><label>类别</label><select id="td-cat">${["采购","事务","学习","生活","其他"].map(o=>`<option ${(r.cat||"事务")===o?"selected":""}>${o}</option>`).join("")}</select></div>
    <div class="f"><label>优先级</label><select id="td-pri">${["高","中","低"].map(o=>`<option ${(r.pri||"中")===o?"selected":""}>${o}</option>`).join("")}</select></div>
    <div class="f"><label>截止日期</label><input id="td-due" type="date" value="${r.due||""}"></div>
    <div class="f"><label>备注</label><input id="td-note" value="${esc(r.note||"")}"></div>
    <button class="btn" id="td-save">${r.row?"保存":"添加"}</button>
  </div>`;
}
// 同 readBillForm：页面上的「添加待办」和弹窗里的「修改待办」字段 ID 一样
function readTodoForm(box) {
  const el = id => $("#" + id, box || document);
  return {item: el("td-item").value.trim(), cat: el("td-cat").value, pri: el("td-pri").value,
    due: el("td-due").value, note: el("td-note").value.trim()};
}
/** 生成这条待办的 .ics 并交给系统打开。
 *  ⚠ 只写文件、**不动待办本身** —— 加不加日历是"提醒方式"，
 *    不是"这件事的状态"，导出一次就被标成干完了那是灾难。 */
async function todoToCal(row) {
  busy();
  const r = await post("/api/todo/ics", {row});
  if (!r.ok) return toast(r.msg, true);
  // 打开它 —— 系统会问「要不要加到日历」。
  // ⚠ 说人话：别说"已打开文件夹"，那是 openDirOrCopy 的通用文案，
  //   这里打开的是一个日历文件，用户会莫名其妙。
  if (await openDir(r.data.path)) return toast("已打开日历文件，在弹出来的窗口里确认一下");
  if (await copyText(r.data.path)) {
    return toast("打不开日历程序 —— 文件路径已复制，位置在「_导出\日历」下");
  }
  toast("日历文件在：" + r.data.path, true);
}

function bindTodo() {
  // ---- 筛选。改了条件只重画会变的那一半（见 renderTodoBox），
  //      这样正在打字的 #tf-q 不会被重建、光标不会丢。----
  // ⚠ 查询一律限定在 #tf-fixed / #todo-box 内。用全文档选择器会误伤别的页面，
  //   待办那几个「点了没反应」的坑就是这么来的（交接文档 B 类）。
  const scope = $("#tf-fixed") || document;
  const listBox = $("#todo-box") || document;
  const tq = $("#tf-q", scope);
  if (tq) {
    let timer = null;
    tq.oninput = () => {                     // 打字防抖，别每按一键就重排 DOM
      clearTimeout(timer);
      timer = setTimeout(() => { todoFilter.q = tq.value; renderTodoBox(); }, 220);
    };
    tq.onkeydown = e => {
      if (e.key === "Escape") { tq.value = ""; todoFilter.q = ""; renderTodoBox(); }
    };
  }
  const tstat = $("#tf-stat", scope);
  if (tstat) tstat.onchange = () => { todoFilter.stat = tstat.value; renderTodoBox(); };
  const tpri = $("#tf-pri", scope);
  if (tpri) tpri.onchange = () => { todoFilter.pri = tpri.value; renderTodoBox(); };
  const tclr = $("#tf-clear", scope);
  if (tclr) tclr.onclick = () => {
    todoFilter = {cats: [], pri: "", stat: "open", q: ""};
    // 固定那一半里的控件得跟着回到默认值 —— 只重画明细是不行的
    const q = $("#tf-q", scope), s = $("#tf-stat", scope), pr = $("#tf-pri", scope);
    if (q) q.value = ""; if (s) s.value = "open"; if (pr) pr.value = "";
    renderTodoBox();
  };
  $$("[data-tfcat]", listBox).forEach(b => b.onclick = () => {
    const c = b.dataset.tfcat;
    const i = todoFilter.cats.indexOf(c);
    if (i >= 0) todoFilter.cats.splice(i, 1); else todoFilter.cats.push(c);
    renderTodoBox();
  });
  const sb = $("#td-save");
  if (sb) sb.onclick = async () => {
    // ⚠ 2.2 把待办从物资页搬到了 #tab-todo，这里的容器**必须跟着改**。
    //   原来写的是 #tab-stock，于是在物资页里找待办的输入框 —— 一个都找不到，
    //   读表单直接读到 null。
    const f = readTodoForm($("#tab-todo"));
    if (!f.item) return toast("先写事项", true);
    busy();
    const r = await post("/api/todo/add", Object.assign(f, {stat: "未完成"}));
    if (r.ok) { toast(r.msg); await refreshStockAndTodo(); } else toast(r.msg, true);
  };
  // ⚠ 同理：这里原来是 `$$("[data-todo-toggle]", $("#tab-stock"))` ——
  //   限定在物资页里找待办的「完成」按钮，结果**一个都没绑上**，
  //   点了没有任何反应。用户报的「待办无法点击」就是它。
  //   （「改」「删」两处没加限定，所以一直是好的 —— 这种"一半好用一半不好"
  //     最容易被当成偶发问题放过去。）
  // 加到日历（2.4.5）：后端写一个 .ics 文件，然后用系统默认的日历程序打开它
  // （Windows 上是 Outlook / 日历应用，会弹「要导入吗」）。
  // ⚠ 只写文件、**不动待办本身** —— 加不加日历是"提醒方式"，
  //   不是"这件事的状态"，导出一次就被标成干完了那是灾难。
  $$("[data-todo-ics]", $("#tab-todo")).forEach(btn => btn.onclick = async () => {
    const row = +btn.dataset.todoIcs;
    const t = STOCK.todo.find(x => x.row === row);
    if (!t) return;
    if ((t.due || "").trim()) return todoToCal(row);
    // 没填截止日期 —— **当场弹个小框让他选一天**，别让人先跑去改待办再回来点。
    // （原来是一句 toast 打发，用户的原话是"你问我问题啊" —— 那就问。）
    modal("这条还没填截止日期", `
      <p class="mini" style="margin:0 0 10px">日历里总得知道放哪天。
        「${esc(t.item)}」你打算哪天做？</p>
      <div class="form"><div class="f"><label>日期</label>
        <input type="date" id="ics-due" value="${todayStr()}"></div></div>
      <p class="mini" style="margin:10px 0 0">选完会**顺手把这条待办的截止日期也填上**，
        不然下次点它又得问一遍。</p>`, async () => {
      const d = $("#ics-due").value;
      if (!d) { toast("先选一天", true); return false; }
      const e = await post("/api/todo/edit", {row, item: t.item, cat: t.cat, pri: t.pri,
                                              due: d, note: t.note, stat: t.stat});
      if (!e.ok) { toast(e.msg, true); return false; }
      await refreshStockAndTodo();
      await todoToCal(row);
    }, "calendar");
    const ok = $("#m-ok");
    if (ok) ok.textContent = "加到日历";
  });
  $$("[data-todo-toggle]", $("#tab-todo")).forEach(btn => btn.onclick = async () => {
    const t = STOCK.todo.find(x => x.row === +btn.dataset.todoToggle);
    busy();
    const r = await post("/api/todo/toggle", {row: t.row, stat: t.stat === "已完成" ? "未完成" : "已完成"});
    if (r.ok) { toast(r.msg); await refreshStockAndTodo(); } else toast(r.msg, true);
  });
  $$("[data-todo-edit]").forEach(btn => btn.onclick = () => {
    const t = STOCK.todo.find(x => x.row === +btn.dataset.todoEdit);
    modal("修改待办（第 " + t.row + " 行）", todoForm(t), async () => {
      busy();
      const r = await post("/api/todo/edit",
        Object.assign(readTodoForm($("#modalCard")), {row: t.row, stat: t.stat}));
      if (r.ok) { toast(r.msg); await refreshStockAndTodo(); return true; }
      toast(r.msg, true); return false;
    });
  });
  $$("[data-todo-del]").forEach(btn => btn.onclick = async () => {
    if (!confirm("确定删除这条待办？")) return;
    busy();
    const r = await post("/api/todo/del", {row: +btn.dataset.todoDel});
    if (r.ok) { toast(r.msg); await refreshStockAndTodo(); } else toast(r.msg, true);
  });
}
function emergencyCard() {
  const items = STOCK.emergency;
  if (!items.length) return '<p class="mini">应急信息页还没有内容</p>';
  return items.map(cells => `<div style="padding:4px 0">${cells.map(esc).join("　·　")}</div>`).join("");
}

/* ================================================================
   ⑤ 设置（AI / DeepSeek）
================================================================ */
let AICFG = null;
let AIUSAGE = null;
let AIANALYSIS = null;         // 总览 AI 分析结果（页面会被整块重建，必须存这里）
/* ---------------- 前端错误收集 ----------------
 *
 * 打包版没有控制台，用户能看到的只有「点了没反应」和一片空白。
 * 这里把 JS 报的错攒起来，设置页顶上给一条提示、能一键复制 ——
 * 不然每次都是「我这儿好好的」，来回猜。
 */
const JS_ERRORS = [];
function noteJsError(msg) {
  const s = String(msg || "").slice(0, 300);
  if (s && !JS_ERRORS.includes(s)) JS_ERRORS.push(s);
  const bar = $("#jserr");
  if (bar) renderJsErr();
}
window.addEventListener("error", e => noteJsError(
  (e.message || "脚本出错") + " @" + String(e.filename || "").split("/").pop() + ":" + e.lineno));
window.addEventListener("unhandledrejection", e => noteJsError(
  (e.reason && (e.reason.message || e.reason)) || "有个异步操作失败了"));

function renderJsErr() {
  const bar = $("#jserr");
  if (!bar) return;
  if (!JS_ERRORS.length) { bar.hidden = true; bar.innerHTML = ""; return; }
  bar.hidden = false;
  bar.innerHTML = `<b>这次打开出过 ${JS_ERRORS.length} 个脚本错误</b>
    <button class="btn ghost sm" id="jserr-copy">复制</button>
    <div class="mini" style="margin-top:6px">${JS_ERRORS.map(esc).join("<br>")}</div>`;
  const b = $("#jserr-copy");
  if (b) b.onclick = async () => {
    await copyText("小煦拾简脚本错误：\n" + JS_ERRORS.join("\n"));
    toast("已复制，发给我就能定位");
  };
}

/** 一张卡独立加载。挂了就**把原因写在卡里**，不连累别人。
 *
 * ⚠ 以前这五张卡是**串联**的：renderSettings → 学期 → 备份 → 导出 → 回收站，
 * 中间任何一步抛异常，后面的全都不执行 —— 卡停在「空盒子」状态，
 * 里面的按钮自然点了没反应，而且五个框全空、看不出是哪一步断的。
 * 现在改成各管各的：谁挂了只影响谁，原因就写在那一张卡里。 */
async function cardLoad(sel, name, fn) {
  const card = $(sel);
  if (!card) return;
  try {
    await fn();
    if (!card.innerHTML.trim()) card.innerHTML = `<p class="mini">（${name}没有内容）</p>`;
  } catch (e) {
    const why = (e && (e.message || e)) || "未知原因";
    card.innerHTML = `<div class="warn" style="font-weight:400">
      <b>${esc(name)}没加载出来</b><br>${esc(String(why))}</div>`;
    noteJsError(name + "加载失败：" + why);
  }
}

async function loadSettings() {
  // 这几步的失败不该拦住整个设置页 —— 字体拿不到就用默认的，AI 配置拿不到
  // 也照样能改主题和类别。所以各自 try 一下。
  try { await loadFonts(); } catch (e) { noteJsError("字体列表：" + e.message); }
  let rc = {ok: false}, ru = {ok: false};
  try { [rc, ru] = await Promise.all([get("/api/ai/config"), get("/api/ai/usage")]); }
  catch (e) { noteJsError("AI 配置：" + e.message); }
  if (BILL === null) { try { const rb = await get("/api/bill"); if (rb.ok) BILL = rb.data; }
                       catch (e) { noteJsError("账单：" + e.message); } }
  if (STOCK === null) { try { const rs = await get("/api/stock"); if (rs.ok) STOCK = rs.data; }
                        catch (e) { noteJsError("物资：" + e.message); } }
  if (!rc.ok && rc.msg) toast(rc.msg, true);
  AICFG = rc.ok ? rc.data : (AICFG || {});
  AIUSAGE = ru.ok ? ru.data : null;
  // 应急信息是**同步**渲染的（模板字符串里塞 Promise 会变成 [object Promise]），
  // 所以数据必须赶在 renderSettings() 之前拿到手。
  // ⚠ 这里不能走 cardLoad —— #em-card 要等 renderSettings() 才存在，
  // 那时候卡里根本没有这个元素，cardLoad 会静默跳过，数据永远拉不到。
  try { await loadEmergency(); }
  catch (e) { noteJsError("应急信息：" + e.message); EMDATA = EMDATA || {sections: []}; }
  renderSettings();
  renderJsErr();
  // ---- 下面各管各的，谁挂了都不连累别人 ----
  catDraftInit();
  // ⚠ **别再在这儿手抄一份绑定清单了。** 这里原来写的是
  //   bindEmergency / bindSetNav / bindPersonalization / bindPersonal ——
  //   一眼看去挺全，其实漏了 bindBg()：从标签页进设置，「换一张」按钮
  //   元素在、事件没绑，点上去**毫无反应还不报错**（用户就是这么撞上的）。
  //   afterRenderSettings() 才是那份唯一清单，新控件在那儿登记一次就够。
  await afterRenderSettings();
  try { const ra = await get("/api/about");
        if (ra.ok) { ABOUT = ra.data; renderAboutCard(); renderWhereCard(); } }
  catch (e) { noteJsError("关于：" + e.message); }
}

function renderAboutCard() {
  const box = $$(".setsec").find(s => s.dataset.sec === "关于");
  if (box) box.innerHTML = secAbout();
}

/* 个性化设置的所有控件。都是「点一下就存」，不用找保存按钮。 */
function bindPersonalization() {
  $$("[data-theme-set]").forEach(b => b.onclick = () =>
    saveCfg({theme: b.dataset.themeSet}, "主题已切换"));
  $$("[data-pal-set]").forEach(b => b.onclick = () =>
    saveCfg({palette: b.dataset.palSet}, "配色已切换"));
  const f = $("#set-font");
  if (f) f.onchange = () => {
    const pv = $("#font-prev");
    if (pv) pv.style.fontFamily = f.value ? `'${f.value}'` : "var(--font-base)";
    saveCfg({font: f.value}, "字体已切换");
  };
  /* 日记字体（2.5.1）。⚠ 必须**当场 applyDiaryFont()** ——
     只改 APPCFG 的话预览要等下次渲染才变，看着像"点了没反应"
     （背景那几处也栽过同样的坑，见 applyBg 的注释）。 */
  const df = $("#set-diary-font");
  if (df) df.onchange = async () => {
    await saveCfg({diary_font: df.value}, "日记字体已切换");
    applyDiaryFont();                       // 加载新字体并写进 --diary-font
    const pv = $("#diary-font-prev");
    if (pv) pv.style.fontFamily = "var(--diary-font, STXingkai)";
  };
  const fc = $("#font-count");
  if (fc) {
    const all = FONTS || [];
    fc.textContent = all.length ? `（系统里有 ${all.length} 个字体，中文的都在下面）`
                               : "（没读到系统字体，只能先用默认）";
  }
  const fs = $("#set-fs");
  if (fs) {
    fs.oninput = () => {                      // 拖动时先实时预览，松手才存
      document.documentElement.style.setProperty("--fs", fs.value + "px");
      const v = $("#set-fs-val"); if (v) v.textContent = fs.value;
    };
    fs.onchange = () => saveCfg({font_size: +fs.value}, "字号已改");
  }
  $$("[data-anim]").forEach(b => b.onclick = () =>
    saveCfg({animations: b.dataset.anim === "1"}, b.dataset.anim === "1" ? "动画已开" : "动画已关"));
  const tb = $("#set-tab");
  if (tb) tb.onchange = () => saveCfg({default_tab: tb.value}, "默认页面已改");
  $$("[data-auto]").forEach(b => b.onclick = async () => {
    const on = b.dataset.auto === "1";
    const r = await post("/api/settings/save", {autostart: on});
    if (!r.ok) return toast(r.msg, true);
    APPCFG.autostart = on;
    toast(r.msg);
    renderSettings();
    afterRenderSettings();
  });
  $$("[data-bf]").forEach(b => b.onclick = () => {
    const patch = {}; patch[b.dataset.bf] = b.dataset.v === "1";
    const cur = Object.assign({}, cfg("bill_form", {}), patch);
    saveCfg({bill_form: cur}, "已更新");
  });
  $$("[data-enc]").forEach(b => b.onclick = async () => {
    const on = b.dataset.enc === "1";
    const cr = (APPCFG && APPCFG.crypto) || {};
    if (on && !(APPCFG && APPCFG.has_password)) return toast("先设置访问密码 —— 密钥由它派生", true);
    if (on && cr.available === false) return toast("这台机器缺少加密库，用不了", true);
    if (on && !confirm("开启后 笔记\\ 里的 .md 会变成密文，记事本打开是乱码。\n" +
        "密钥由访问密码派生，密码和密钥都不存盘。\n" +
        "⚠ 密码忘了 = 笔记永久打不开，没有后门。\n\n" +
        "确定开启？（随时可以关掉，关掉就变回明文）")) return;
    const r = await post("/api/settings/save", {encrypt_notes: on});
    toast(r.msg, !r.ok);
    // 服务端可能没照做（比如当时没解锁），所以用它回的状态为准，别自己写死
    const s = await get("/api/settings");
    if (s.ok) APPCFG = s.data;
    renderSettings(); afterRenderSettings();
  });
  $$("[data-err]").forEach(b => b.onclick = () =>
    saveCfg({error_log: b.dataset.err === "1"}, "已更新"));
  // 密码
  const ps = $("#pw-set"), pc = $("#pw-change"), px = $("#pw-clear");
  if (ps) ps.onclick = () => passwordModal(false);
  if (pc) pc.onclick = () => passwordModal(true);
  if (px) px.onclick = () => passwordModal(true, true);
  // 高级
  const ac = $("#adv-cache");
  if (ac) ac.onclick = async () => {
    const r = await post("/api/cache/clear", {});
    toast(r.msg); if (r.ok) { BILL = null; CHECK = null; STOCK = null; } await showDebug();
  };
  const ad = $("#adv-debug");
  if (ad) ad.onclick = () => showDebug();
  const ae = $("#adv-errlog");
  if (ae) ae.onclick = () => showErrorLog();
  const av = $("#adv-csv");
  if (av) av.onclick = () => exportCsv();
  // 打印按钮的绑定挪进 bindEmergency() 了 —— 那边要先把表单里的改动读回来，
  // 打出来的才是你现在看到的内容，而不是上次保存的版本
  // 反馈：诊断信息是现攒的（版本/路径/开关/错误日志），不含 API Key 和数据内容
  const fbc = $("#fb-copy");
  if (fbc) fbc.onclick = async () => {
    const t = await feedbackText();
    const ok = await copyText(t);
    const m = $("#fb-msg");
    if (m) m.textContent = ok ? "已复制，去粘贴吧" : "复制不了，点「先看看内容」手动选";
    toast(ok ? "诊断信息已复制到剪贴板" : "复制失败", !ok);
  };
  const fbs = $("#fb-show");
  if (fbs) fbs.onclick = async () => {
    const t = await feedbackText();
    const box = $("#fb-box");
    if (box) box.innerHTML = `<pre class="errlog" style="margin-top:10px">${esc(t)}</pre>`;
  };
  const fbv = $("#fb-save");
  if (fbv) fbv.onclick = async () => {
    const t = await feedbackText();
    const blob = new Blob([t], {type: "text/plain;charset=utf-8"});
    const a2 = document.createElement("a");
    a2.href = URL.createObjectURL(blob);
    a2.download = "小煦拾简_诊断信息.txt";
    a2.click();
    setTimeout(() => URL.revokeObjectURL(a2.href), 3000);
    toast("已存到你浏览器的下载目录");
  };
}

function passwordModal(needOld, isClear) {
  modal(isClear ? "取消访问密码" : (needOld ? "修改访问密码" : "设置访问密码"), `
    ${needOld ? `<div class="f"><label>原密码</label><input type="password" id="pw-old"></div>` : ""}
    <div class="f"><label>${isClear ? "" : "新"}密码</label><input type="password" id="pw-new" ${isClear ? "disabled" : ""}></div>
    <p class="mini">至少 4 位。数据是明文存在硬盘上的，这把锁只挡「别人顺手点开你的程序」。</p>`,
    async () => {
      const body = {old: ($("#pw-old") || {}).value || ""};
      if (!isClear) {
        body.new = $("#pw-new").value;
        if ((body.new || "").length < 4) { toast("密码至少 4 位", true); return false; }
      }
      const r = await post(isClear ? "/api/auth/clear" : "/api/auth/set", body);
      if (!r.ok) { toast(r.msg, true); return false; }
      toast(r.msg);
      AUTH_TOKEN = ""; try { sessionStorage.removeItem("xr_token"); } catch (e) {}
      if (!isClear) {
        // 设/改密码会让服务端把所有旧令牌作废，这里手里的令牌已经不管用了。
        // 不重新解锁的话，接下来每个请求都是 401 —— 界面看着就像坏了。
        setTimeout(() => showLock(), 400);
        return true;
      }
      const s = await get("/api/settings"); if (s.ok) APPCFG = s.data;
      renderSettings(); afterRenderSettings();
    });
}

async function showDebug() {
  const box = $("#adv-box");
  if (!box) return;
  const r = await get("/api/debug");
  if (!r.ok) return toast(r.msg, true);
  box.innerHTML = `<table class="kvtable"><tbody>${
    Object.entries(r.data).map(([k, v]) =>
      `<tr><td class="mini">${esc(k)}</td><td class="mini">${esc(
        Array.isArray(v) ? v.join("、") : String(v))}</td></tr>`).join("")}</tbody></table>`;
}

async function showErrorLog() {
  const box = $("#adv-box");
  if (!box) return;
  const r = await get("/api/error/log");
  if (!r.ok) return toast(r.msg, true);
  box.innerHTML = `<div style="display:flex;gap:8px;margin-bottom:8px">
      <button class="btn ghost sm" id="err-clear">清空日志</button>
      <span class="mini">共 ${Math.round((r.data.size || 0) / 1024)} KB</span></div>
    <pre class="errlog">${esc(r.data.text || "（还没有错误记录，很好）")}</pre>`;
  const c = $("#err-clear");
  if (c) c.onclick = async () => { const x = await post("/api/error/clear", {}); toast(x.msg); showErrorLog(); };
}

/* CSV 导出：走浏览器下载，不经过后端 —— 数据本来就在内存里 */
function exportCsv() {
  if (!BILL || !BILL.records) return toast("账单还没加载", true);
  const rows = [["日期", "类别", "项目/备注", "收入", "支出", "支付方式", "团购", "核销状态"]];
  recFiltered().forEach(r => rows.push([r.date, r.cat, r.note, r.inc || "", r.exp || "",
                                        r.pay, r.grp, r.stat]));
  const csv = rows.map(r => r.map(c => {
    const s = String(c === null || c === undefined ? "" : c);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }).join(",")).join("\r\n");
  // 加 BOM，否则 Excel 打开中文会乱码
  const blob = new Blob(["﻿" + csv], {type: "text/csv;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `流水_${todayStr().replace(/-/g, "")}${recFiltering() ? "_已筛选" : ""}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);
  toast(`已导出 ${rows.length - 1} 条到 CSV`);
}
/* ================================================================
   设置页：左侧分区导航 + 右侧内容
================================================================ */
const SET_SECTIONS = [["外观", "palette"], ["个性化", "sparkle"], ["应急", "alert"],
                      ["行为", "gear"], ["数据", "save"], ["隐私", "shield"],
                      ["AI", "robot"], ["关于", "info"], ["高级", "wrench"]];
let setSection = "外观";

function setNav() {
  return `<div class="setwrap"><div class="setnav">${
    SET_SECTIONS.map(([n, ic]) => `<button class="setnavbtn${n === setSection ? " on" : ""}"
      data-setsec="${n}"><span class="bi" data-icon="${ic}"></span><span>${n}</span></button>`).join("")}</div>`;
}

function bindSetNav() {
  $$("[data-setsec]").forEach(b => b.onclick = () => {
    setSection = b.dataset.setsec;
    $$("[data-setsec]").forEach(x => x.classList.toggle("on", x.dataset.setsec === setSection));
    $$(".setsec").forEach(s => s.hidden = s.dataset.sec !== setSection);
  });
  $$(".setsec").forEach(s => s.hidden = s.dataset.sec !== setSection);
}

const cfg = (k, d) => (APPCFG && APPCFG[k] !== undefined ? APPCFG[k] : d);

/* ---- 设了就用它，并且立刻存；不用找保存按钮 ---- */
async function saveCfg(patch, msg) {
  const r = await post("/api/settings/save", patch);
  if (!r.ok) return toast(r.msg, true);
  APPCFG = Object.assign({}, APPCFG || {}, patch);
  applyTheme();
  redrawAll();
  toast(msg || r.msg);
  // 外观那几项会改变控件自己的状态（哪个按钮高亮），所以要重画这一区。
  // ⚠ 重画会换掉整片 DOM，**必须把事件重新绑一遍** —— 以前漏了这一步，
  //   结果改一次设置之后所有按钮都是死的，得切走再切回来才行
  if (setSection === "外观") { renderSettings(); afterRenderSettings(); }
}

/* ---------------- 字体清单 ----------------
   哪些字体能用，**由后端枚举**（GDI 的 EnumFontFamiliesEx，不读文件、不碰 C 盘）。
   一开始我在前端用 canvas 量文字宽度来判断字体装没装，那个办法在无头浏览器里
   完全测不出来（所有字体量出来一样宽），靠不住 —— 能验证的才敢用。 */
let FONTS = null;          // 后端给的「这台机器装了哪些字体」
// 值得优先摆出来的几个（装了才显示）
const FONT_PICK = ["微软雅黑", "楷体", "宋体", "黑体", "仿宋", "隶书", "幼圆",
                   "华文行楷", "华文楷体", "华文宋体", "华文隶书", "等线",
                   "微软雅黑 Light", "方正舒体", "方正姚体"];

async function loadFonts() {
  if (FONTS) return;
  const r = await get("/api/fonts").catch(() => null);
  if (r && r.ok && (r.data.fonts || []).length) FONTS = r.data.fonts;
}

function secAppearance() {
  // 清单来自后端枚举：装了什么就列什么，选了就一定有效果
  const all = FONTS || [];
  const cn = all.filter(n => /[一-鿿]/.test(n));       // 中文名字的都是中文字体
  const head = FONT_PICK.filter(n => all.includes(n));           // 优先摆的几个
  const rest = cn.filter(n => !head.includes(n));
  const fonts = [["", "（默认 · 微软雅黑）"]]
    .concat(head.map(n => [n, n]))
    .concat(rest.map(n => [n, n]));
  // 配色小圆点：[名字, 底色, 主色]。2.3.3 加了粉色系四套。
  const palettes = [["素纸", "#fbfaf8", "#9d4034"], ["青瓷", "#f6fbfb", "#2d6d6d"],
                    ["墨色", "#f0efec", "#5a5a57"],
                    ["樱粉", "#fdeef0", "#cf6f8c"], ["蓝粉", "#eef2fa", "#a86bb5"],
                    ["藕荷", "#f1eef4", "#8a6f9e"], ["奶茶", "#f6f0e8", "#b5824a"]];
  return `
  <h2 class="sec">${ICON.palette} 外观</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="f" style="margin-bottom:14px"><label>主题</label>
      <div class="seg">${[["light", "sun", "浅色"], ["dark", "moon", "深色"], ["auto", "monitor", "跟随系统"]]
        .map(([v, ic, t]) => `<button class="segbtn${cfg("theme", "auto") === v ? " on" : ""}"
          data-theme-set="${v}"><span class="bi" data-icon="${ic}"></span>${t}</button>`).join("")}</div>
    </div>
    <div class="f" style="margin-bottom:14px"><label>配色</label>
      <div class="seg">${palettes.map(([n, bg, ac]) =>
        `<button class="segbtn${(cfg("palette", "素纸") === n || (n === "素纸" && cfg("palette") === "米黄")) ? " on" : ""}" data-pal-set="${n}">
          <span class="pal-dot" style="background:${bg};border-color:${ac}"></span>
          <span class="pal-dot" style="background:${ac}"></span>${n}</button>`).join("")}</div>
    </div>
    <div class="form">
      <div class="f"><label>字体 <span class="mini" id="font-count"></span></label>
        <select id="set-font">${fonts.map(([v, label]) =>
          `<option value="${v}"${cfg("font", "") === v ? " selected" : ""}${
            v ? ` style="font-family:'${v}'"` : ""}>${label}</option>`).join("")}</select>
        <div class="fontprev" id="font-prev" style="font-family:${cfg("font", "") ? `'${cfg("font", "")}'` : "var(--font-base)"}">
          永和九年，岁在癸丑 —— 今天天气不错，记一笔。</div>
      </div>
      <div class="f"><label>字号 <b id="set-fs-val">${cfg("font_size", 14)}</b> px</label>
        <input type="range" id="set-fs" min="12" max="22" step="1"
          value="${cfg("font_size", 14)}" style="width:220px">
        <span class="mini">调到 22 相当于「大字号」；右边还能直接输数字</span>
      </div>
      <!-- 日记字体（2.5.1）。⚠ 只管**日记/随笔的竖排正文**，
           跟上面那个「界面字体」是两件事 —— 编辑框仍然是等宽字体。 -->
      <div class="f"><label>日记字体 <span class="mini">（只看日记和随笔的竖排正文）</span></label>
        <select id="set-diary-font">
          <option value="shoujin"${cfg("diary_font", "shoujin") === "shoujin" ? " selected" : ""}>瘦金体（宋徽宗那种细瘦带锋）</option>
          <option value="mashan"${cfg("diary_font", "shoujin") === "mashan" ? " selected" : ""}>马善政行书（毛笔行书，流畅）</option>
          <option value=""${cfg("diary_font", "shoujin") === "" ? " selected" : ""}>系统书法体（华文行楷，不额外加载）</option>
        </select>
        <div class="fontprev" id="diary-font-prev" style="writing-mode:vertical-rl;text-orientation:upright;
          height:168px;padding:8px 14px;font-family:var(--diary-font,STXingkai)">
          拾寸简以记沐小煦而行</div>
        <span class="mini">两个自带字体都在安装包里，**不用联网**。瘦金体 12 MB、行书 5.6 MB，按需加载。</span>
      </div>
      <div class="f"><label>界面动画</label>
        <div class="seg"><button class="segbtn${cfg("animations", true) ? " on" : ""}" data-anim="1">开</button>
        <button class="segbtn${cfg("animations", true) ? "" : " on"}" data-anim="0">关</button></div>
      </div>
    </div>
    <p class="mini" style="margin-top:10px">七套配色都由同一个公式算出来（12 级色阶），对比度是算过的、不是凭眼睛调的。素纸是中性纸色配朱砂，青瓷偏冷青，墨色最素。</p>
  </div>
  <h2 class="sec">${ICON.image} 背景图 <span class="mini">用自己的照片当底</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    ${bgCard()}
  </div>`;
}

/* 背景图这块。选图 → 在浏览器里缩到 1600px → 存到 _配置\背景\
   ⚠ 缩放必须在浏览器里做：服务端只有标准库，没有 PIL。
     一张手机原图五六兆，不缩的话每次开页面都要传一遍，还得进备份。 */
function bgCard() {
  // 壁纸三模式（2.3.6）。⚠ 老设置里只有 bg_image、没有 bg_mode，
  // 所以模式缺省时**看有没有图**反推 —— 不这么办，一升级背景就没了。
  const mode = cfg("bg_mode", "") || (cfg("bg_image", "") ? "image" : "none");
  const fill = cfg("bg_fill", "cover");
  const has = mode === "image" && !!cfg("bg_image", "");
  // 同一个滑块，在深浅两套主题里干的是**相反**的事：它铺的就是主题底色，
  // 深色主题下它是压暗照片，浅色主题下它是给照片垫一层浅底（越拖越白）。
  // 名字得跟着主题走，不然浅色下写着「压暗」却越拖越白，没法自圆其说。
  //
  // ⚠ 2.3.8：**默认 0（不蒙）**。用户 2026-09-18 的原话是
  //   「不要在全屏蒙一层图层，只改卡片的背景色」—— 这层膜从 2.3.5 起
  //   就是「雾蒙蒙」的头号嫌疑人，前两版一直在调薄，其实它就不该在。
  //   文案也跟着改了：以前写成"建议调一点"，现在是"默认不用，看不清再说"。
  const dark = document.documentElement.dataset.theme === "dark";
  const dimWord = dark ? "压暗" : "衬底";
  const dimHint = "默认 0：你的照片原样显示，不蒙任何东西。"
    + (dark ? "照片特别亮、字读不出来时才往上拖。" : "照片特别花、字读不出来时才往上拖。");
  const MODES = [["image", "照片"], ["solid", "纯色"], ["none", "不要"]];
  const FILLS = [["cover", "铺满"], ["contain", "完整显示"], ["center", "居中不缩放"]];
  return `
  <div class="f" style="margin:0 0 12px">
    <label>背景用哪种</label>
    <div class="seg segsm">
      ${MODES.map(([v, t]) => `<button class="segbtn${mode === v ? " on" : ""}"
        data-bgmode="${v}">${t}</button>`).join("")}
    </div>
  </div>
  ${mode === "solid" ? `
  <div class="f" style="margin:0 0 12px">
    <label>底色</label>
    <input type="color" id="bg-solid" value="${esc(cfg("bg_solid", "") || "#e9edf5")}"
      style="width:64px;height:34px;padding:2px">
    <span class="mini">整页就用这一个颜色。想更省事就点上面的「不要」，用主题底色</span>
  </div>` : ""}
  ${mode === "none" ? `
  <p class="mini">用主题自己的底色，干干净净。下面这些设置先留着，换回照片就生效。</p>` : ""}
  ${mode === "image" ? `
  <div class="f" style="margin:0 0 12px">
    <label>照片怎么放</label>
    <div class="seg segsm">
      ${FILLS.map(([v, t]) => `<button class="segbtn${fill === v ? " on" : ""}"
        data-bgfill="${v}">${t}</button>`).join("")}
    </div>
    <span class="mini">比例跟屏幕对不上时，「铺满」会裁掉一点，「完整显示」会留边</span>
  </div>` : ""}
  <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">
    ${mode === "image" ? `<div class="bgprev${has ? " has" : ""}" id="bg-prev">
      ${has ? "" : '<span class="mini">还没有背景图</span>'}
    </div>` : ""}
    <div style="flex:1;min-width:260px">
      <div class="form" style="align-items:center">
        <button class="btn" id="bg-pick">${ICON.image} ${has ? "换一张" : "选一张图片"}</button>
        ${has ? `<button class="btn ghost" id="bg-del">去掉这张</button>` : ""}
        <input type="file" id="bg-file" accept="image/*" hidden>
      </div>
      ${has ? `
      <div class="f" style="margin-top:12px"><label>${dimWord} <b id="bg-dim-val">${cfg("bg_dim", 0)}</b>%</label>
        <input type="range" id="bg-dim" min="0" max="90" step="5"
          value="${cfg("bg_dim", 0)}" style="width:220px">
        <span class="mini">${dimHint}</span>
      </div>
      <div class="f" style="margin-top:8px"><label>模糊 <b id="bg-blur-val">${cfg("bg_blur", 0)}</b> px</label>
        <input type="range" id="bg-blur" min="0" max="20" step="1"
          value="${cfg("bg_blur", 0)}" style="width:220px">
        <span class="mini">照片太花、太抢眼时用它</span>
      </div>
      <div class="f" style="margin-top:8px"><label>卡片透出多少照片 <b id="bg-glass-val">${cfg("bg_glass", 0)}</b>%</label>
        <input type="range" id="bg-glass" min="0" max="85" step="5"
          value="${cfg("bg_glass", 0)}" style="width:220px">
        <span class="mini">默认 <b>0：卡片是纯色块</b>，照片只在卡片外面看得见 ——
          字最多的地方先保证看得清。调大照片会从卡片里透出来，最透也在 86% 不透明。</span>
      </div>
      <div class="pillrow" style="margin:6px 0 0 0">
        ${[[30, "轻"], [55, "中"], [75, "透"]].map(([v, t]) =>
          `<button class="pill${Number(cfg("bg_glass", 0)) === v ? " on" : ""}"
             data-glass="${v}">${t} ${v}%</button>`).join("")}
        <span class="mini" style="align-self:center">
          拿不准就点「中」—— 照片看得见，字也稳</span>
      </div>` : ""}
    </div>
  </div>
  <p class="mini" style="margin-top:10px">
    图片会缩到 1600 px 存进 <code>_配置\\背景\\背景.jpg</code>。
    <b>卡片和表格仍然是实心的</b> —— 字最多的地方得先保证看得清。
  </p>`;
}

/** 选图 → 缩 → 上传。全过程在浏览器里完成，用户看不到中间文件。 */
function bindBg() {
  const pick = $("#bg-pick"), file = $("#bg-file");
  if (!pick || !file) return;
  pick.onclick = () => file.click();
  file.onchange = async () => {
    const f = file.files && file.files[0];
    if (!f) return;
    if (!/^image\//.test(f.type)) return toast("这不是图片文件", true);
    busy();
    let data;
    try {
      data = await shrinkImage(f, 1600, 0.85);
    } catch (e) {
      idle(); return toast("这张图读不出来：" + e.message, true);
    }
    // ⚠ 2.3.8：**不再自动算一个「衬底浓度」填给你了**。
    //   以前选完图会采样照片明暗，自动把遮罩拖到 5~45% 之间的某个值
    //   （suggestDim / imageTone 那一套）。用户 2026-09-18 定的规矩是
    //   「不要在全屏蒙一层图层，只改卡片的背景色」—— 那自动填一个非零值
    //   就是在偷偷把那层膜加回来，而且是用户没要的。所以整块删掉，
    //   滑块留在设置里，真觉得看不清时自己拖。
    //   顺带少了三个函数和一个 32×32 的 canvas 采样。
    const r = await post("/api/settings/bg", {data});
    if (!r.ok) return toast(r.msg, true);
    APPCFG = Object.assign({}, APPCFG || {}, {bg_image: r.data.file,
                                               bg_rev: r.data.rev || ""});
    // ⚠ **必须当场 applyBg()**。以前只更新了 APPCFG 就重画设置页
    //   —— 设置存下来了、预览框里也看到图了，可页面背景还是纯色，
    //   非得刷新一次才出现。用户看到的就是「我明明选了图，背景呢？」
    //   预览框是普通 <img> 背景，跟 body::before 那两层是两码事，
    //   一个变了不代表另一个也变了。
    applyBg();
    toast("背景已换好");
    renderSettings(); afterRenderSettings();
  };
  const del = $("#bg-del");
  if (del) del.onclick = async () => {
    if (!confirm("去掉背景图，回到纯色？图片文件会一起删掉。")) return;
    busy();
    const r = await post("/api/settings/bg/clear", {});
    if (!r.ok) return toast(r.msg, true);
    APPCFG = Object.assign({}, APPCFG || {}, {bg_image: "", bg_rev: ""});
    applyBg();                    // 同上：去掉也要当场生效，不能等刷新
    toast("已回到纯色");
    renderSettings(); afterRenderSettings();
  };
  // 两个滑块**拖的时候即时预览**，松手才存 —— 存一次是写一次磁盘，
  // 拖动过程中每动一格存一次会把设置文件写烂（而且卡）。
  const bindSlide = (sel, key, valSel, unit) => {
    const el = $(sel);
    if (!el) return;
    el.oninput = () => {
      $(valSel).textContent = el.value;
      APPCFG = Object.assign({}, APPCFG || {}, {[key]: Number(el.value)});
      applyBg();                       // 只改 CSS 变量，立刻见效
    };
    el.onchange = () => saveCfg({[key]: Number(el.value)}, "已保存");
    void unit;
  };
  // ---- 壁纸三模式 / 填充方式 / 纯色（2.3.6）----
  // 都是「点一下就存」。模式变了要显示/隐藏不同的控件，所以存完必须重画 ——
  // saveCfg 在「外观」这一区会自动重画设置页（见它自己那段注释）。
  $$("[data-bgmode]").forEach(b => b.onclick = () => {
    saveCfg({bg_mode: b.dataset.bgmode}, "背景已切换");
    applyBg();
  });
  $$("[data-bgfill]").forEach(b => b.onclick = () => {
    saveCfg({bg_fill: b.dataset.bgfill}, "已换");
    applyBg();
  });
  const sc = $("#bg-solid");
  if (sc) {
    // input 是拖动时连续触发、change 才是松手 —— 和三个滑块一个规矩，
    // 不然拖一次颜色要写几十遍设置文件。
    sc.oninput = () => { APPCFG = Object.assign({}, APPCFG || {}, {bg_solid: sc.value}); applyBg(); };
    sc.onchange = () => saveCfg({bg_solid: sc.value}, "底色已换");
  }
  bindSlide("#bg-dim", "bg_dim", "#bg-dim-val");
  bindSlide("#bg-blur", "bg_blur", "#bg-blur-val");
  bindSlide("#bg-glass", "bg_glass", "#bg-glass-val");
  // 三个预设。点了等于把滑块拖到那个值 —— 走同一条保存通路，不另开逻辑。
  $$("[data-glass]").forEach(b => b.onclick = () => {
    const v = Number(b.dataset.glass);
    $$("[data-glass]").forEach(x => x.classList.toggle("on", Number(x.dataset.glass) === v));
    const r = $("#bg-glass");
    if (r) { r.value = v; $("#bg-glass-val").textContent = v; }
    saveCfg({bg_glass: v}, `卡片通透 ${v}%`);
  });
}

/** 把图片缩到最长边 max，返回 JPEG 的 dataURL。
 *  用 canvas 做 —— 浏览器本来就带，不用引任何库（「零第三方依赖」那条底线还在）。 */
function shrinkImage(file, max, quality) {
  return new Promise((ok, fail) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      let {width: w, height: h} = img;
      if (!w || !h) return fail(new Error("图片尺寸读不出来"));
      const k = Math.min(1, max / Math.max(w, h));
      w = Math.max(1, Math.round(w * k));
      h = Math.max(1, Math.round(h * k));
      const cv = document.createElement("canvas");
      cv.width = w; cv.height = h;
      const cx = cv.getContext("2d");
      // 先铺一层白：带透明通道的 PNG 直接转 JPEG 会把透明区变成黑块
      cx.fillStyle = "#fff"; cx.fillRect(0, 0, w, h);
      cx.drawImage(img, 0, 0, w, h);
      ok(cv.toDataURL("image/jpeg", quality));
    };
    img.onerror = () => { URL.revokeObjectURL(url); fail(new Error("不是有效的图片")); };
    img.src = url;
  });
}

function secBehavior() {
  const tabs = [["over", "home", "总览"], ["bill", "wallet", "账单"],
                ["check", "check", "打卡"], ["stock", "box", "物资"],
                ["note", "book", "日记"], ["memory", "sparkle", "回忆书"]];
  const bf = cfg("bill_form", {}) || {};
  return `
  <h2 class="sec">${ICON.gear} 行为</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="form">
      <div class="f"><label>打开时默认进</label>
        <select id="set-tab">${tabs.map(([v, t]) =>
          `<option value="${v}"${cfg("default_tab", "over") === v ? " selected" : ""}>${t}</option>`).join("")}</select>
      </div>
      <div class="f"><label>开机自启</label>
        <div class="seg"><button class="segbtn${cfg("autostart", false) ? " on" : ""}" data-auto="1">开</button>
        <button class="segbtn${cfg("autostart", false) ? "" : " on"}" data-auto="0">关</button></div>
      </div>
    </div>
    <p class="mini" style="margin-top:8px">开机自启会往注册表 <code>HKCU\\...\\Run</code> 写一条，
      指向主程序。只对免安装版有效（源码模式没有外壳 exe）。</p>
    <h2 class="sec" style="font-size:14px;margin-top:18px">记一笔的交互</h2>
    ${[["clear_after_save", "保存后自动清空表单，方便连着记几笔"],
       ["enter_to_save", "在金额/备注里按回车直接保存"],
       ["autofocus", "打开账单页时自动聚焦到金额输入框"]].map(([k, t]) =>
      `<div class="gline2"><span>${t}</span>
        <div class="seg segsm"><button class="segbtn${bf[k] !== false ? " on" : ""}" data-bf="${k}" data-v="1">开</button>
        <button class="segbtn${bf[k] !== false ? "" : " on"}" data-bf="${k}" data-v="0">关</button></div></div>`).join("")}
  </div>`;
}

function secPrivacy() {
  const hasPw = !!(APPCFG && APPCFG.has_password);
  const cr = (APPCFG && APPCFG.crypto) || {};
  const encOn = cfg("encrypt_notes", false);
  const canEnc = cr.available !== false && hasPw && (cr.unlocked || !encOn);
  return `
  <h2 class="sec">${ICON.shield} 隐私安全</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="warn" style="font-weight:400">
      ⚠ 先说实话：<b>只加密笔记，账目/打卡/物资这些数字不加密</b>。下面这些只挡
      「别人顺手点开你的程序、翻到你的文件夹」，<b>挡不住已经拿到你电脑的人</b> ——
      内存里的密钥、键盘记录、休眠文件都能拿到。真正的保护是
      <b>BitLocker 全盘加密 + 系统登录密码</b>，这个功能只是多一层。
    </div>
    <div class="gline2"><span>访问密码锁 ${hasPw ? '<span class="badge tagg">已开启</span>' : ""}</span>
      <span>${hasPw
        ? `<button class="btn ghost sm" id="pw-change">改密码</button>
           <button class="btn warn sm" id="pw-clear">取消密码</button>`
        : `<button class="btn sm" id="pw-set">设置密码</button>`}</span></div>
    <p class="mini">开启后，每次打开程序要先输密码；后端接口也会要求令牌。
      忘了密码只能改 <code>_配置\\settings.json</code> 手动清掉——
      但那样<b>加密过的笔记就永远打不开了</b>。</p>

    <div class="gline2" style="margin-top:12px">
      <span>笔记加密 ${encOn ? '<span class="badge tagg">已开启</span>' : ""}</span>
      <div class="seg segsm">
        <button class="segbtn${encOn ? " on" : ""}" data-enc="1" ${canEnc ? "" : 'disabled title="要先设访问密码"'}>开</button>
        <button class="segbtn${encOn ? "" : " on"}" data-enc="0">关</button></div></div>
    ${cr.available === false ? '<div class="warn" style="font-weight:400">这台机器上缺少加密库，笔记加密用不了。</div>' : ""}
    <p class="mini" style="line-height:1.8">
      <b>只加密 笔记\\ 里的 .md</b>，数字类的数据不动 —— 它们住在一整个数据库文件里，
      加密它就得把整个程序改一遍，收益不划算。
      算法是 <b>AES-256-GCM</b>，密钥由访问密码经 PBKDF2 派生 20 万次，
      <b>密码和密钥都不落盘</b>，密钥只活在内存里，所以每次重开程序都要重新解锁。<br>
      加密后：用记事本打开 .md 是乱码；<code>_自动备份</code> 里的笔记副本、回收站里的日记
      也一并是密文，不会漏。<b>改密码会自动把所有笔记重新加密一遍</b>，不会把你锁在门外。<br>
      ⚠ 代价说在前面：<b>密码忘了 = 笔记永久打不开</b>，没有后门，我也救不了。
      所以要么把密码记牢，要么先「关」掉加密再用。
      ${encOn && !cr.unlocked ? '<br><b class="r">当前没有密钥</b>：重新打开程序输一次密码就能读。' : ""}
    </p>

    <div class="gline2" style="margin-top:12px"><span>本地错误日志</span>
      <div class="seg segsm">
        <button class="segbtn${cfg("error_log", true) ? " on" : ""}" data-err="1">开</button>
        <button class="segbtn${cfg("error_log", true) ? "" : " on"}" data-err="0">关</button></div></div>
    <p class="mini">出问题时把异常写进 <code>_配置\\错误日志.txt</code>，方便回头查。</p>
  </div>`;
}

/* ---- 个性化：称呼 / AI 口吻 / 总览卡片 / 打卡项 ---- */
// 总览页那六张卡的 key，要和 renderOverview 里用的 key 一致
// [键, 图标名, 文字]。图标名对应 ICON 表里的线条 SVG ——
// 以前这里直接写彩色表情当图标，全站就剩这几处跟线条图标风格不搭，
// 跟旁边的线条图标摆在一起特别跳。
const OVER_CARDS = [["bal", "wallet", "结余"], ["avail", "bank", "可动用资金"],
                    ["budget", "chart", "本月支出 vs 预算"], ["dream", "moon", "今日梦境"],
                    ["stock", "box", "待补货"], ["todo", "list", "待办未完成"],
                    ["clock", "clock", "牛马时钟"]];
const TONES = [["brief", "从简", "短句为主，一件事一两句写完"],
               ["natural", "适中", "该说清楚的说清楚，不铺开也不压缩"],
               ["rich", "舒展", "细节和感受写充分一些"]];

let ITEMS_DRAFT = null;        // 打卡项的编辑草稿（改了还没保存）

function secPersonal() {
  const it = ITEMS_DRAFT || (CHECK && CHECK.items) || null;
  const cards = cfg("overview_cards", []) || [];
  const on = k => !cards.length || cards.includes(k);
  return `
  <h2 class="sec">${ICON.sparkle} 个性化</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="form">
      <div class="f"><label>AI 怎么称呼你</label>
        <input id="set-callme" value="${esc(cfg("call_me", ""))}" placeholder="留空 = 用「你」" style="min-width:140px"></div>
    </div>
    <p class="mini" style="margin-top:6px">用在<b>回忆书</b>和<b>总览页的 AI 分析</b>里 —— 那两处 AI 是对着你说话的。
      日报周报月报是拿第一人称写的，塞称呼进去会很怪，所以不动它们。</p>

    <h2 class="sec" style="font-size:14px;margin-top:18px">AI 写日记的详略</h2>
    <div class="gline2"><span>口吻</span>
      <div class="seg segsm">${TONES.map(([v, t]) =>
        `<button class="segbtn${cfg("note_tone", "natural") === v ? " on" : ""}" data-tone="${v}"
          title="${t}">${t}</button>`).join("")}</div></div>
    <p class="mini">${esc((TONES.find(t => t[0] === cfg("note_tone", "natural")) || TONES[1])[2])}。
      只影响写得详略，<b>不影响事实口径</b> —— 三档都不许编造。</p>

    <h2 class="sec" style="font-size:14px;margin-top:18px">总览页的卡片</h2>
    <p class="mini" style="margin:0 0 8px">
      勾选决定显示哪些，右边的 <b>↑ ↓</b> 决定谁在前。<b>也可以直接拖</b>。</p>
    <div id="card-list">${cardListHtml()}</div>
    <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
      <button class="btn ghost sm" id="card-reset">恢复默认顺序</button>
      <span class="mini">一张都不勾会退回「全显示」—— 空白的总览页没有意义</span>
    </div>

    <h2 class="sec" style="font-size:14px;margin-top:18px">总览页的快速打卡按钮</h2>
    <p class="mini" style="margin:0 0 8px">
      勾选决定「今日快速打卡」里出现哪几个，<b>↑ ↓</b> 或直接拖决定谁在前。
      勾掉只是不在这儿显示，<b>记过的数据一条都不会少</b>。</p>
    <div id="quick-list">${quickListHtml()}</div>
    <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
      <button class="btn ghost sm" id="quick-reset">恢复默认</button>
      <span class="mini">打卡项在下面「打卡项」那一区增删改名，这里跟着变</span>
    </div>
  </div>

  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" style="margin-top:14px">
    <div class="pagehead" style="margin-bottom:6px">
      <div class="ph-title" style="font-size:14px">打卡项</div>
      <div class="ph-actions">
        <button class="btn sm" id="items-save">${ICON.save} 保存</button>
        <button class="btn ghost sm" id="items-reset">还原默认</button>
      </div>
    </div>
    ${itemsEditor()}
    <p class="mini" style="margin-top:10px">
      改完记得点<b>保存</b>。删掉一项，它已经记下的数据<b>不会丢</b> ——
      只是不再显示，以后加回来还在。<br>
      类型决定打卡时怎么填：<b>打勾</b>是一下点掉，<b>数字</b>填数，<b>时间</b>填 HH:MM，
      <b>下拉</b>从你给的选项里挑，<b>文本</b>随便写。</p>
  </div>`;
}

/* ---- 打卡项编辑器 ----
   以前这里只能改名和隐藏：打卡数据在 Excel 月表里，每项固定占一列，
   旁边的公式全按列号引用，插一列就把它们带偏。
   换成 SQLite 窄表之后「一项」就是 check_val 里的一组行，加删都不影响别的。 */
const CK_KINDS_CN = {tick: "打勾", num: "数字", time: "时间", sel: "下拉", text: "文本"};
// **只列核心和加分两组**。「其它」那 16 项（入睡时间、睡眠质量、运动时长…）
// 是单日页那张手写表单的字段，标签是写死的 —— 在这儿改了名，单日页那边
// 不会跟着变，反而对不上。它们不是「打卡项」，是作息记录。
const CK_GRPS = [["core", "核心打卡", "计入完成率"],
                 ["bonus", "加分打卡", "做了白赚，没做不扣分"]];

function itemsEditor() {
  const it = ITEMS_DRAFT;
  if (!it) return '<p class="mini">打卡数据还没加载，切到打卡页看一眼再回来。</p>';
  return CK_GRPS.map(([g, cn, hint]) => `
    <div class="mini" style="margin:12px 0 5px"><b>${cn}</b> · ${hint}</div>
    <div class="itemsedit">${
      (it[g] || []).map((x, i) => itemRow(g, x, i)).join("")
      || '<div class="mini" style="opacity:.55">（这一组空的）</div>'}</div>
    <button class="btn ghost sm" data-itemadd="${g}" style="margin-top:6px">＋ 加一项</button>`)
    .join("");
}

function itemRow(g, x, i) {
  const col = esc(x.col);
  const list = ITEMS_DRAFT[g] || [];
  if (x.kind === "derived") {          // 自动算出来的，只给看
    return `<div class="itemrow">
      <input data-item="${col}" value="${esc(x.name)}" readonly
        title="由别的项自动算出来，改不了名字">
      <span class="badge tagd">自动算</span>
    </div>`;
  }
  return `<div class="itemrow">
    <input data-item="${col}" value="${esc(x.name)}" maxlength="20" placeholder="名字">
    <select data-itemkind="${col}" title="这一项怎么填">${
      Object.entries(CK_KINDS_CN).map(([k, v]) =>
        `<option value="${k}"${x.kind === k ? " selected" : ""}>${v}</option>`).join("")}</select>
    ${x.kind === "sel" ? `<input data-itemopts="${col}" value="${esc(x.opts || "")}"
      placeholder="选项，逗号分隔" style="min-width:140px">` : ""}
    <button class="segbtn" data-itemmv="${col}:-1" ${i === 0 ? "disabled" : ""} title="上移">↑</button>
    <button class="segbtn" data-itemmv="${col}:1" ${i >= list.length - 1 ? "disabled" : ""} title="下移">↓</button>
    <button class="segbtn${x.on !== false ? " on" : ""}" data-itemon="${col}"
      title="隐藏后打卡页不显示，已经记的数据都还在">${x.on !== false ? "显示" : "已隐藏"}</button>
    <button class="btn warn sm" data-itemdel="${col}" title="删掉这一项（已记的数据保留）">删</button>
  </div>`;
}

// 按钮的亮/灭要跟当前设置一致 —— 存储空数组是「全开」的意思，
// 直接拿数组判断会把「全开」显示成「全灭」。
/** 设置页那张「卡片列表」的 HTML。
 *  顺序取自 cardOrder()（也就是当前实际显示的顺序），不是写死的 OVER_CARDS ——
 *  不然用户排完顺序、再进来一看又变回出厂顺序，会以为没保存上。 */
function cardListHtml() {
  const cur = cfg("overview_cards", []) || [];
  const on = k => !cur.length || cur.includes(k);
  const info = {};
  OVER_CARDS.forEach(([k, ic, t]) => { info[k] = [ic, t]; });
  return cardOrder().map((k, i, arr) => `
    <div class="gline2 cardrow" draggable="true" data-cardrow="${k}">
      <span style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" data-card="${k}"${on(k) ? " checked" : ""}>
        <span class="bi" data-icon="${info[k][0]}"></span>${info[k][1]}
      </span>
      <span style="white-space:nowrap">
        <button class="btn ghost sm" data-cardmv="${k}:-1" ${i === 0 ? "disabled" : ""}>↑</button>
        <button class="btn ghost sm" data-cardmv="${k}:1" ${i === arr.length - 1 ? "disabled" : ""}>↓</button>
      </span>
    </div>`).join("");
}

/** 设置页那张「快速打卡按钮」列表。和卡片列表一个样子、一个交互，
 *  只是键换成打卡项的列号（U1/U2…）。 */
function quickListHtml() {
  const show = quickShow();
  const byCol = {};
  checkItems("core").forEach(x => { byCol[x.col] = x; });
  if (!Object.keys(byCol).length) return '<p class="mini">打卡项还没加载出来</p>';
  return quickOrder().filter(c => byCol[c]).map((c, i, arr) => `
    <div class="gline2 cardrow" draggable="true" data-quickrow="${c}">
      <span style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" data-quick="${c}"${show.includes(c) ? " checked" : ""}>
        ${esc(byCol[c].name)}
      </span>
      <span style="white-space:nowrap">
        <button class="btn ghost sm" data-quickmv="${c}:-1" ${i === 0 ? "disabled" : ""}>↑</button>
        <button class="btn ghost sm" data-quickmv="${c}:1" ${i === arr.length - 1 ? "disabled" : ""}>↓</button>
      </span>
    </div>`).join("");
}

/** 「可勾选 + 可排序」列表的交互 —— 总览卡片、快速打卡按钮共用这一套。
 *  两处的需求一模一样（勾选管显示、↑↓/拖拽管顺序、全勾且是出厂顺序就存空数组），
 *  抄两份迟早走样，所以参数化。传进来的键一律是「列的 key」：
 *  卡片是 bal/avail…，打卡项是 U1/U2…。
 *  ⚠ 存完必须 await 再重画。saveCfg 只更新 APPCFG、**不会重画设置页**
 *    （只有「外观」那一区会重画），不等它就往下走，紧接着那次重画读到的还是
 *    旧设置，画出来当然还是旧顺序 —— 表现是「存进去了，列表纹丝不动」。 */
function bindRowList(o) {
  const box = $(o.sel);
  if (!box || !o.all.length) return;
  const rows = () => $$(`[data-${o.row}]`, box).map(x => x.dataset[o.row]);
  // ⚠ visible() **每次现读设置**，不能用绑定那一刻那份。
  //   每存一次只更新 APPCFG、不重画这一块，闭包里那份就旧了 ——
  //   连着点两下会拿旧数据去算，表现是「第二次点没反应」。
  const visible = () => {
    const c = (cfg(o.showKey, []) || []).filter(k => o.all.includes(k));
    return c.length ? c : o.all.slice();
  };
  const dump = () => ({order: rows(), visible: visible()});
  const store = async (order, vis) => {
    const allOn = o.all.every(k => vis.includes(k));
    await saveCfg({
      // 顺序单独存一份**完整排列**。不能从「显示哪些」反推 ——
      // 关掉一张卡它就从那个数组里没了，再打开只能补到队尾。
      [o.orderKey]: order.slice(),
      [o.showKey]: (order.join(",") === o.all.join(",") && allOn) ? []
        : order.filter(k => vis.includes(k)),
    }, o.msg);
    o.rerender();
  };

  $$(`[data-${o.chk}]`, box).forEach(cb => cb.onchange = () => {
    const d = dump();
    let v = d.visible;
    const k = cb.dataset[o.chk];
    if (cb.checked) { if (!v.includes(k)) v = v.concat([k]); }
    else v = v.filter(x => x !== k);
    if (!v.length) { toast(o.emptyMsg); v = o.all.slice(); }
    store(d.order, v);
  });

  $$(`[data-${o.mv}]`, box).forEach(b => b.onclick = () => {
    const [k, delta] = b.dataset[o.mv].split(":");
    const d = dump();
    const i = d.order.indexOf(k), j = i + +delta;
    if (i < 0 || j < 0 || j >= d.order.length) return;
    [d.order[i], d.order[j]] = [d.order[j], d.order[i]];
    store(d.order, d.visible);
  });

  // 拖拽。HTML5 原生 drag —— 不引库。
  let dragKey = null;
  $$(`[data-${o.row}]`, box).forEach(row => {
    row.ondragstart = e => { dragKey = row.dataset[o.row]; e.dataTransfer.effectAllowed = "move"; };
    row.ondragover = e => {
      e.preventDefault();
      if (!dragKey || dragKey === row.dataset[o.row]) return;
      const d = dump();
      const from = d.order.indexOf(dragKey), to = d.order.indexOf(row.dataset[o.row]);
      if (from < 0 || to < 0) return;
      d.order.splice(to, 0, d.order.splice(from, 1)[0]);
      // 只重排 DOM、不整块重画 —— 重画会让拖拽中断（draggable 的元素被换掉）
      d.order.forEach(k => {
        const el = $(`[data-${o.row}="${k}"]`, box);
        if (el) box.appendChild(el);
      });
    };
    row.ondrop = e => {
      e.preventDefault();
      if (!dragKey) return;
      const d = dump();
      store(d.order, d.visible);
      dragKey = null;
    };
    row.ondragend = () => { dragKey = null; };
  });

  const rs = $(o.resetSel);
  if (rs) rs.onclick = async () => {
    // 显示和顺序**两份都要清**。只清一份的话顺序还留着上一版的排列，
    // 用户点了「恢复默认」会发现顺序没回去。
    await saveCfg({[o.showKey]: [], [o.orderKey]: []}, o.resetMsg);
    o.rerender();
  };
}

/** o.rerender 用：重画一块列表并重新绑事件 */
const repaintList = (sel, html, bind) => () => {
  const b = $(sel);
  if (b) { b.innerHTML = html(); bind(); }
};
const bindCardList = () => bindRowList({
  sel: "#card-list", row: "cardrow", chk: "card", mv: "cardmv",
  orderKey: "overview_order", showKey: "overview_cards",
  all: OVER_CARDS.map(([k]) => k),
  msg: "总览卡片已更新", emptyMsg: "至少留一张卡，已恢复全显示",
  resetSel: "#card-reset", resetMsg: "已恢复默认顺序",
  rerender: repaintList("#card-list", cardListHtml, () => bindCardList()),
});
const bindQuickList = () => bindRowList({
  sel: "#quick-list", row: "quickrow", chk: "quick", mv: "quickmv",
  orderKey: "quick_order", showKey: "quick_items", all: quickAllKeys(),
  msg: "快速打卡按钮已更新", emptyMsg: "至少留一个按钮，已恢复全显示",
  resetSel: "#quick-reset", resetMsg: "已恢复默认",
  rerender: repaintList("#quick-list", quickListHtml, () => bindQuickList()),
});

function bindPersonal() {
  const cm = $("#set-callme");
  if (cm) {
    const save = () => saveCfg({call_me: cm.value.trim()}, "称呼已保存");
    cm.onchange = save;
    cm.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); cm.blur(); } };
  }
  $$("[data-tone]").forEach(b => b.onclick = () => {
    $$("[data-tone]").forEach(x => x.classList.toggle("on", x === b));
    saveCfg({note_tone: b.dataset.tone}, "口吻已改");
  });
  // 总览卡片、快速打卡按钮那两块的勾选 / 排序，共用 bindRowList()，见上面 */
  bindCardList();
  bindQuickList();
  // 打卡项：改的是草稿，点保存才提交（改名要迁移已记的数据，不适合每敲一键就存）
  ITEMS_DRAFT = ITEMS_DRAFT || (CHECK && CHECK.items ? JSON.parse(JSON.stringify(CHECK.items)) : null);
  bindItemsEditor();
  const sv = $("#items-save");
  if (sv) sv.onclick = async () => {
    if (!ITEMS_DRAFT) return toast("没有可保存的打卡项", true);
    // 界面上的改动是「草稿」，提交前先把输入框里的字收进草稿 ——
    // 不然刚敲完名字就直接点保存，存下去的还是旧的
    collectItemsDraft();
    busy();
    const r = await post("/api/check/items/save", {items: ITEMS_DRAFT});
    idle();
    toast(r.msg, !r.ok);
    if (r.ok) { CHECK = null; await loadCheck(); ITEMS_DRAFT = null; await afterRenderSettings(); }
  };
  const rs = $("#items-reset");
  if (rs) rs.onclick = async () => {
    if (!confirm("把打卡项的名字和显示状态都还原成出厂设置？\n（已经记下的数据不受影响）")) return;
    busy();
    const r = await post("/api/check/items/save", {items: {core: [], bonus: []}});
    idle();
    toast(r.msg, !r.ok);
    if (r.ok) { CHECK = null; await loadCheck(); ITEMS_DRAFT = null; await afterRenderSettings(); }
  };
}

/** 打卡项编辑器的所有交互。加、删、改名、改类型、上下移、显示隐藏。 */
function bindItemsEditor() {
  if (!ITEMS_DRAFT) return;
  const find = col => {
    for (const g of ["core", "bonus", "other"]) {
      const row = (ITEMS_DRAFT[g] || []).find(x => x.col === col);
      if (row) return [g, row];
    }
    return [null, null];
  };
  $$("[data-item]").forEach(i => i.oninput = () => {
    const [, row] = find(i.dataset.item);
    if (row) row.name = i.value;
  });
  $$("[data-itemkind]").forEach(sel => sel.onchange = () => {
    const [, row] = find(sel.dataset.itemkind);
    if (!row) return;
    row.kind = sel.value;
    renderItemsEditorInto();          // 选「下拉」要多出一个「选项」输入框
  });
  $$("[data-itemopts]").forEach(i => i.oninput = () => {
    const [, row] = find(i.dataset.itemopts);
    if (row) row.opts = i.value;
  });
  $$("[data-itemon]").forEach(b => b.onclick = () => {
    const [, row] = find(b.dataset.itemon);
    if (!row) return;
    row.on = row.on === false;
    b.classList.toggle("on", row.on !== false);
    b.textContent = row.on !== false ? "显示" : "已隐藏";
  });
  $$("[data-itemmv]").forEach(b => b.onclick = () => {
    const [col, d] = b.dataset.itemmv.split(":");
    const [g, row] = find(col);
    const list = ITEMS_DRAFT[g] || [];
    const i = list.indexOf(row), j = i + (+d);
    if (i < 0 || j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    renderItemsEditorInto();
  });
  $$("[data-itemdel]").forEach(b => b.onclick = () => {
    const [g, row] = find(b.dataset.itemdel);
    if (!row) return;
    if (!confirm(`删掉「${row.name}」？\n\n已经记下的数据**不会丢** —— ` +
                 `只是网页上不再显示。以后想要，加回来名字对上就还能看到。`)) return;
    ITEMS_DRAFT[g] = (ITEMS_DRAFT[g] || []).filter(x => x !== row);
    renderItemsEditorInto();
  });
  $$("[data-itemadd]").forEach(b => b.onclick = () => {
    const g = b.dataset.itemadd;
    ITEMS_DRAFT[g] = ITEMS_DRAFT[g] || [];
    ITEMS_DRAFT[g].push({col: "", name: "", kind: "tick", opts: "", on: true});
    renderItemsEditorInto();
    const box = $(".itemsedit");
    const inputs = $$("[data-item]");
    if (inputs.length) inputs[inputs.length - 1].focus();
  });
}

/** 把输入框里的字收回草稿 —— 提交前必须调一次 */
function collectItemsDraft() {
  $$("[data-item]").forEach(i => {
    for (const g of ["core", "bonus", "other"]) {
      const row = (ITEMS_DRAFT[g] || []).find(x => x.col === i.dataset.item);
      if (row) { row.name = i.value; return; }
    }
  });
  $$("[data-itemopts]").forEach(i => {
    for (const g of ["core", "bonus", "other"]) {
      const row = (ITEMS_DRAFT[g] || []).find(x => x.col === i.dataset.itemopts);
      if (row) { row.opts = i.value; return; }
    }
  });
}

/** 只重画编辑器那一块，不动整页 —— 整页重画会丢滚动位置 */
function renderItemsEditorInto() {
  const card = $$(".itemsedit")[0];
  if (!card) return;
  const holder = card.parentElement;
  const kids = [...holder.children];
  const first = kids.find(x => x.classList.contains("itemsedit"));
  if (!first) return;
  // 用一个临时容器接住 HTML，然后逐个替换
  const wrap = document.createElement("div");
  wrap.innerHTML = itemsEditor();
  const olds = [...holder.children].filter(x =>
    x.classList.contains("itemsedit") || x.hasAttribute("data-itemadd") ||
    (x.classList.contains("mini") && /核心打卡|加分打卡|其它/.test(x.innerText)));
  // ⚠ 锚点要**在删之前**把「它爹」和「它后面是谁」记下来。
  //   这段栽过两次，两次都是「拿了个马上就会被删掉的节点当锚点」：
  //   ① 先 remove 再读 anchor.parentElement —— 锚点自己就在 olds 里，
  //      删完 parentElement 是 null，报
  //      `Cannot read properties of null (reading 'insertBefore')`。
  //   ② 改成先记下来，可记的是** olds[0] 的下一个兄弟**，而它多半也是
  //      olds 中的一员（编辑器长这样：标题、.itemsedit、加一项按钮、下一组标题…），
  //      一起被删掉之后就不在树上了，于是报
  //      `NotFoundError: The node before which the new node is to be inserted
  //       is not a child of this node`。
  //   正解：取**这一串里最后一个**的后面那个兄弟 —— 按定义它不属于 olds，
  //   删完仍挂在 parent 上，是唯一能用的锚点（null 表示插到末尾）。
  const last = olds[olds.length - 1];
  const parent = olds[0].parentElement;
  if (!parent || !last) return;
  const next = last.nextSibling;
  olds.forEach(x => x.remove());
  [...wrap.children].forEach(n => parent.insertBefore(n, next));
  bindItemsEditor();
}

/* ---- 应急信息 ----
   从物资页搬过来的：它跟"物资"不是一回事，而且需要能打印出来随身带。
   2.0 起它拆成了两张正经的小表（em_field 标签→值 / em_contact 联系人），
   所以**现在是可编辑的**（当初从 Excel 那张手工排版、单元格合并得很随意的
   Sheet 里搬过来时还是只读）。 */
/* ---- 应急信息（可编辑） ---- */
// 每节一行放几组「标签/值」。和服务器上的 EM_COLS 是同一份版面约定。
const EM_SECS = [["基本信息", 3], ["医疗警示", 1], ["紧急联系人", 0],
                 ["常用电话", 3], ["就医与其他", 1]];
let EMDATA = null;

function secEmergency() {
  // 同步函数：模板字符串里塞 Promise 会渲染成 [object Promise]。
  // 数据由 loadSettings() 提前拉好。
  return `
  <h2 class="sec">${ICON.alert} 应急信息</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="pagehead" style="margin-bottom:8px">
      <div class="ph-sub">血型、过敏史、紧急联系人这些 —— 出事的时候别人要能一眼找到。
        建议填完<b>打印一份</b>贴在宿舍、再塞一张在钱包里。</div>
      <div class="ph-actions">
        <button class="btn ghost sm" id="em-print">${ICON.print} 打印</button>
        <button class="btn sm" id="em-save">${ICON.save} 保存</button>
      </div>
    </div>
    <div id="em-card" class="emcard">${
      EMDATA ? emForm(EMDATA) : '<p class="mini">载入中…</p>'}</div>
  </div>`;
}

function emForm(data) {
  return (data.sections || []).map(s => {
    const cols = (EM_SECS.find(x => x[0] === s.sec) || [0, 1])[1];
    if (cols === 0) {                       // 紧急联系人：一张小表
      return `<div class="emsub">${esc(s.sec)}</div>
        <table class="emtab"><thead><tr><th>姓名</th><th>关系</th>
          <th>联系电话</th><th></th></tr></thead><tbody>
        ${(s.contacts || []).map((p, i) => `<tr>
          <td><input data-em="c" data-sec="${esc(s.sec)}" data-i="${i}" data-k="name" value="${esc(p.name || "")}"></td>
          <td><input data-em="c" data-sec="${esc(s.sec)}" data-i="${i}" data-k="rel" value="${esc(p.rel || "")}"></td>
          <td><input data-em="c" data-sec="${esc(s.sec)}" data-i="${i}" data-k="phone" value="${esc(p.phone || "")}"></td>
          <td><button class="btn ghost sm" data-em-delc="${i}">删</button></td>
        </tr>`).join("")}</tbody></table>
        <button class="btn ghost sm" data-em-addc="1">+ 加一位联系人</button>`;
    }
    return `<div class="emsub">${esc(s.sec)}</div>
      <div class="emgrid c${cols}">${
        s.fields.map((f, i) => `<div class="emf">
          <input class="eml" data-em="f" data-sec="${esc(s.sec)}" data-i="${i}" data-k="label" value="${esc(f.label || "")}" title="标签">
          <input class="emv" data-em="f" data-sec="${esc(s.sec)}" data-i="${i}" data-k="value" value="${esc(f.value || "")}">
        </div>`).join("")}</div>
      <button class="btn ghost sm" data-em-addf="${esc(s.sec)}">+ 加一项</button>`;
  }).join("");
}

/** 从表单读回数据。**必须按 data-sec 归位** —— 页面上好几个节的字段长得一样，
 *  只看 data-i 的话，第二个节的第 0 项会盖掉第一个节的。 */
function readEmForm() {
  const data = {sections: (EMDATA && EMDATA.sections || []).map(
    s => ({sec: s.sec, fields: [], contacts: []}))};
  const bySec = {};
  data.sections.forEach(s => { bySec[s.sec] = s; });
  $$("#em-card [data-em]").forEach(el => {
    const sec = bySec[el.dataset.sec];
    if (!sec) return;
    const i = +el.dataset.i;
    if (el.dataset.em === "f") {
      sec.fields[i] = sec.fields[i] || {label: "", value: ""};
      sec.fields[i][el.dataset.k] = el.value;
    } else {
      sec.contacts[i] = sec.contacts[i] || {name: "", rel: "", phone: ""};
      sec.contacts[i][el.dataset.k] = el.value;
    }
  });
  data.sections.forEach(s => {
    s.fields = (s.fields || []).filter(Boolean);
    s.contacts = s.sec === "紧急联系人" ? (s.contacts || []).filter(Boolean) : [];
  });
  return data;
}

function bindEmergency() {
  const card = $("#em-card");
  if (!card) return;
  const redraw = () => {
    EMDATA = readEmForm();
    card.innerHTML = emForm(EMDATA);
    bindEmergency();
  };
  $$("#em-card [data-em-addf]").forEach(b => b.onclick = () => {
    EMDATA = readEmForm();
    const s = EMDATA.sections.find(x => x.sec === b.dataset.emAddf);
    if (s) s.fields.push({label: "", value: ""});
    card.innerHTML = emForm(EMDATA);
    bindEmergency();
  });
  const ac = $("#em-card [data-em-addc]");
  if (ac) ac.onclick = () => {
    EMDATA = readEmForm();
    const s = EMDATA.sections.find(x => x.sec === "紧急联系人");
    if (s) s.contacts.push({name: "", rel: "", phone: ""});
    card.innerHTML = emForm(EMDATA);
    bindEmergency();
  };
  $$("#em-card [data-em-delc]").forEach(b => b.onclick = () => {
    EMDATA = readEmForm();
    const s = EMDATA.sections.find(x => x.sec === "紧急联系人");
    if (s) s.contacts.splice(+b.dataset.emDelc, 1);
    card.innerHTML = emForm(EMDATA);
    bindEmergency();
  });
  const sv = $("#em-save");
  if (sv) sv.onclick = async () => {
    busy();
    const r = await post("/api/emergency/save", readEmForm());
    idle();
    if (!r.ok) { toast(r.msg, true); return; }
    toast("应急信息已保存");
    await loadEmergency();
    const box = $$(".setsec").find(x => x.dataset.sec === "应急");
    if (box) { box.innerHTML = secEmergency(); bindEmergency(); }
  };
  const ep = $("#em-print");
  if (ep) ep.onclick = () => {
    EMDATA = readEmForm();                 // 打印的是你现在看到的内容，不是上次存的
    document.body.classList.add("printing-em");
    window.print();
    setTimeout(() => document.body.classList.remove("printing-em"), 800);
  };
}

async function loadEmergency() {
  const r = await get("/api/emergency").catch(() => null);
  EMDATA = (r && r.ok) ? r.data : {sections: []};
}

function secAbout() {
  const a = ABOUT || {};
  const kb = n => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
  return `
  <h2 class="sec">${ICON.info} 关于</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="abouthead">
      <div class="aboutname">小煦拾简</div>
      <div class="aboutver">v${esc(a.version || "—")} · 构建于 ${esc(a.built || "—")}</div>
      <div class="aboutslogan">拾寸简以记，沐小煦而行</div>
      <div class="aboutslogan2">拾简记吾岁</div>
      <div class="aboutpoem">朝夕细碎，散若尘简；<br>拾而录之，煦照流年。</div>
    </div>
    <table style="margin-top:14px"><tbody>
      <tr><td class="mini">数据目录</td><td class="mini">${esc(a.data_root || "—")}</td></tr>
      <tr><td class="mini">配置目录</td><td class="mini">${esc(a.conf_dir || "—")}</td></tr>
      <tr><td class="mini">笔记</td><td class="mini">${(a.notes || {}).count || 0} 个文件 · ${kb((a.notes || {}).size || 0)}</td></tr>
      ${(a.files || []).map(f => `<tr><td class="mini">${esc(f.label)}</td><td class="mini">${kb(f.size)}</td></tr>`).join("")}
      <tr><td class="mini">运行方式</td><td class="mini">${
        a.frozen ? "免安装版（自带运行时）" : "源码版（Python " + esc(a.python || "") + "）"}</td></tr>
    </tbody></table>
    <p class="mini" style="margin-top:10px">
      这套系统没有发布渠道，也就没有「检查更新」可做 —— 与其放个点了报错的按钮，不如把版本和路径摆出来。</p>

    <h2 class="sec" style="font-size:14px;margin-top:18px">反馈 / 求助</h2>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <button class="btn sm" id="fb-copy">复制诊断信息</button>
      <button class="btn ghost sm" id="fb-show">先看看内容</button>
      <button class="btn ghost sm" id="fb-save">存成文件</button>
      <span class="mini" id="fb-msg"></span>
    </div>
    <p class="mini" style="margin-top:8px">
      出问题的时候，把这份信息连同你当时在做什么一起发出来，比空口说「用不了」有用得多：
      里面有版本、运行方式、缓存状态、设置项开关和最近的错误堆栈。<br>
      <b>不含 API Key、不含密码、不含你的账单/打卡/日记内容</b> —— 只有路径和状态。
      路径里可能有你的用户名，介意的话自己动手删几行再发。</p>
    <div id="fb-box"></div>
  </div>`;
}

async function feedbackText() {
  const a = ABOUT || {};
  const d = ((await get("/api/debug")) || {}).data || {};
  const e = ((await get("/api/error/log")) || {}).data || {};
  const L = ["===== 小煦拾简 诊断信息 =====",
             "版本：%s    构建：%s".replace("%s", a.version || "?").replace("%s", a.built || "?"),
             "运行方式：" + (a.frozen ? "免安装版（自带运行时）" : "源码版"),
             "操作系统：" + navigator.platform + " / " + (navigator.userAgent || "").slice(0, 80),
             ""];
  Object.entries(d).forEach(([k, v]) => L.push("%s：%s".replace("%s", k).replace("%s",
    Array.isArray(v) ? v.join("、") : String(v))));
  L.push("", "----- 最近错误（最多 1500 字）-----");
  L.push(((e.text || "").trim().slice(-1500)) || "（没有错误记录）");
  L.push("", "----- 我遇到的问题是 -----", "（在这里写：做了什么、期望怎样、实际怎样）");
  return L.join("\n");
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    // 剪贴板接口要安全上下文，file:// 或老浏览器可能不给用，退回老办法
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;left:-9999px";
      document.body.appendChild(ta); ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e2) { return false; }
  }
}

function secAdvanced() {
  return `
  <h2 class="sec">${ICON.wrench} 高级</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">
      <button class="btn ghost sm" id="adv-cache">清理内存缓存</button>
      <button class="btn ghost sm" id="adv-debug">刷新调试信息</button>
      <button class="btn ghost sm" id="adv-errlog">查看错误日志</button>
      <button class="btn ghost sm" id="adv-csv">导出流水 CSV</button>
    </div>
    <div id="adv-box"></div>
    <p class="mini" style="margin-top:10px">
      内存缓存是刚查出来的数据，写入时会自动失效。清掉只会让下次读取慢一点点，没有副作用。</p>
  </div>`;
}

function renderSettings() {
  const c = AICFG, u = AIUSAGE;
  const t = (u && u.total) || {calls:0, total:0, cost:0};
  const scopeName = {drug:"药品信息", analyze:"总览分析", suggest:"名称补全", test:"连接测试", other:"其他"};
  const scopeRows = u ? Object.entries(u.by_scope).map(([k, v]) =>
    `<div class="gline2"><span>${scopeName[k] || k}</span>
      <span>${v.calls} 次 · ${v.total.toLocaleString()} tokens ·
      <b>¥${v.cost.toFixed(4)}</b></span></div>`).join("") : "";
  $("#tab-set").innerHTML = `
  <div class="settop">
    <div class="ph-title">${ICON.gear} 设置</div>
    <div class="ph-sub">左边选一个分区。下面这些<b>点一下就存</b>，不用找保存按钮；改动立刻生效，不用重启。</div>
  </div>
  <div id="jserr" class="warn" hidden></div>
  ${setNav()}
  <div class="setbody">
  <div class="setsec" data-sec="外观">${secAppearance()}</div>
  <div class="setsec" data-sec="个性化">${secPersonal()}</div>
  <div class="setsec" data-sec="应急">${secEmergency()}</div>
  <div class="setsec" data-sec="行为">
  <h2 class="sec">${ICON.wallet} 牛马时钟 <span class="mini">填了日薪就算时薪；不填就不显示</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="clock-card"></div>
  <h2 class="sec">${ICON.gear} 顺手的小开关 <span class="mini">快捷键 · 预算结转</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="misc-card"></div>${secBehavior()}</div>
  <div class="setsec" data-sec="AI">
  <h2 class="sec">${ICON.robot} AI 写东西的规矩 <span class="mini">改坏了 AI 会写得一塌糊涂 —— 清空即恢复默认</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="prompt-card"></div>
  <h2 class="sec">${ICON.sparkle} 回忆书翻找得有多用力 <span class="mini">调小更快更省，调大看得更多</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="mem-card"></div>
  <h2 class="sec">${ICON.robot} AI 设置（DeepSeek）</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="warn" style="font-weight:400">
      AI 生成的是<b>参考信息</b>，用于辅助整理备药清单，<b>不能替代说明书或医嘱</b>。
      调用时只会把<b>药名和备注</b>发给 DeepSeek，不含你的其他数据。
    </div>
    ${c.model_note ? `<div class="warn" style="font-weight:400">⚠ ${esc(c.model_note)}</div>` : ""}
    <div class="form" style="align-items:flex-end">
      <div class="f" style="flex:1;min-width:260px">
        <label>API Key ${c.has_key?`（已保存：${esc(c.api_key_masked)}）`:"（还没配）"}</label>
        <input type="password" id="ai-key"
          placeholder="${c.has_key ? "留空 = 不改动，填新值则覆盖" : "sk-xxxxxxxx"}" style="min-width:240px">
      </div>
      <div class="f"><label>整理/生成模型</label>
        <select id="ai-model">${c.models.map(m=>`<option ${c.model===m?"selected":""}>${m}</option>`).join("")}</select>
      </div>
      <div class="f"><label>回忆书模型</label>
        <select id="ai-mem-model">
          <option value=""${!c.memory_model?" selected":""}>（跟随上面）</option>
          ${c.models.map(m=>`<option ${c.memory_model===m?"selected":""}>${m}</option>`).join("")}
        </select>
      </div>
      <div class="f"><label>看图模型</label>
        <select id="ai-vis-model" title="账单截图、睡眠截图靠它认。必须是能读图的模型">
          <option value=""${!c.vision_model?" selected":""}>（跟随上面）</option>
          ${c.models.map(m=>`<option ${c.vision_model===m?"selected":""}>${m}</option>`).join("")}
        </select>
      </div>
      <div class="f" style="flex:1;min-width:200px"><label>Base URL</label>
        <input id="ai-base" value="${esc(c.base_url)}" style="min-width:200px">
      </div>
      <button class="btn" id="ai-save">保存</button>
      <button class="btn ghost" id="ai-test">测试连接</button>
      <button class="btn ghost" id="ai-models" title="从 DeepSeek 拉取当前可用的模型名">${ICON.refresh} 刷新模型列表</button>
      ${c.has_key?`<button class="btn warn" id="ai-clear">清除 Key</button>`:""}
    </div>
    <p class="mini" style="margin-top:12px">
      申请地址：platform.deepseek.com → API Keys。Key 保存在本机
      <code>个人信息统计\_配置\ai_config.json</code>。<br>
      ⚠ 说明：**用 AI 功能时，被整理的那段内容会发到 DeepSeek 去处理**
      （日报整理、药品信息、回忆书问答都一样），不然它没法帮你整理。
      不用 AI 就不会有任何内容发出去。<br>
      <b>整理/生成模型</b>管日报整理、周报月报、药品信息；<b>回忆书模型</b>管问答，
      可以单独选一个更强的，留「跟随上面」就共用一个。<br>
      <b>deepseek-flash</b> 便宜快（短问答足够）；<b>deepseek-v4-pro</b> 更强但贵约 3.7 倍。
      模型名官方改过多次，失效时点「刷新模型列表」即可。<br>
      <span class="muted">注：deepseek-chat / deepseek-reasoner 已于 2026-07-24 停用，系统会自动迁移。</span>
    </p>
  </div>
  <h2 class="sec">${ICON.user} 个人基本情况 <span class="mini">AI 分析时会带上这段，建议才贴你的实际</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <p class="mini" style="margin:0 0 10px">
      写给 AI 看的自我介绍。比如作息习惯、身体状况、这学期在忙什么、想改善什么。
      <b>每次分析都会原样带上</b> —— 填得越具体，它给的结论越不像模板话。
      留空则完全不带。
    </p>
    <textarea id="pf-text" rows="7" style="width:100%"
      placeholder="例：大三在读，课集中在上午，习惯一点睡。胃不太好，医生让少吃辣。&#10;这学期在准备考研，压力大的时候会熬夜刷手机。想先把作息调规律。"
      >${esc(cfg("personal", ""))}</textarea>
    <div style="display:flex;align-items:center;gap:12px;margin-top:10px;flex-wrap:wrap">
      <button class="btn" id="pf-save">保存</button>
      <label class="mini" style="display:flex;align-items:center;gap:6px;cursor:pointer">
        <input type="checkbox" id="pf-notes"${cfg("ai_use_notes") ? " checked" : ""}>
        分析时也参考最近 3 天的日记
      </label>
      <span class="mini muted" id="pf-note-warn"></span>
    </div>
    <p class="mini" style="margin-top:8px">
      日记那一项<b>默认关闭</b>。打开后只取最近 3 天的日报正文，和上面的基本情况一起发出去；
      周报月报不带。随时关掉，关掉就不再发。
    </p>
  </div>
  <h2 class="sec">${ICON.chart} Token 用量与花费</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="kpis" style="margin-bottom:12px">
      ${kpi("累计调用", t.calls + " 次", "b", "#2563eb")}
      ${kpi("累计 tokens", (t.total||0).toLocaleString(), "b", "#8b5cf6",
            `输入 ${(t.prompt||0).toLocaleString()} · 输出 ${(t.completion||0).toLocaleString()}`)}
      ${kpi("估算花费", "¥" + (t.cost||0).toFixed(4), "a", "#f59e0b",
            (u && u.peak_now) ? "当前为高峰时段" : "当前为空闲时段（半价）")}
    </div>
    ${scopeRows || emptyBox("还没有调用记录")}
    ${u && u.recent && u.recent.length ? `<details style="margin-top:12px">
      <summary>最近 ${u.recent.length} 次调用</summary>
      <table><thead><tr><th>时间</th><th>用途</th><th>模型</th>
        <th class="num">输入</th><th class="num">输出</th><th class="num">费用</th></tr></thead><tbody>
        ${u.recent.map(r=>`<tr><td>${r.time.slice(5)}</td>
          <td>${scopeName[r.scope] || r.scope}</td><td>${esc(r.model)}</td>
          <td class="num">${(r.prompt||0).toLocaleString()}</td>
          <td class="num">${(r.completion||0).toLocaleString()}</td>
          <td class="num">¥${(r.cost||0).toFixed(4)}</td></tr>`).join("")}
      </tbody></table></details>` : ""}
    ${t.calls ? `<div style="text-align:right;margin-top:10px">
      <button class="btn ghost sm" id="ai-uclr">清空用量统计</button></div>` : ""}
    <p class="mini" style="margin-top:10px">
      按 DeepSeek 官方价目估算（元/百万 tokens，高峰 = 周一至周五 9:00-12:00、14:00-18:00，
      其余时段半价）。实际扣费以官方账单为准。
    </p>
  </div>
  </div>
  <div class="setsec" data-sec="数据">
  <h2 class="sec">${ICON.folder} 数据放在哪 <span class="mini">换地方会把数据一起搬过去</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="where-card"></div>
  <h2 class="sec">${ICON.book2} 学期管理 <span class="mini">账单按学期分开，可切换、可对比</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="sem-card"></div>
  <h2 class="sec">${ICON.save} 数据备份 <span class="mini">自动备份每天首次改动时存一份，保留最近 7 份</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="bak-card"></div>
  <h2 class="sec">${ICON.print} 导出成 Excel <span class="mini">给报告、存档、或者自己想再算算的时候用</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="exp-card"></div>
  <h2 class="sec">${ICON.trash} 回收站 <span class="mini">删掉的东西先放这儿，随时能捡回来</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="rc-card"></div>
  <h2 class="sec">${ICON.tag} 账单类别 <span class="mini">增删改排序，按学期分开管</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="cat-card"></div>
  <h2 class="sec">${ICON.bank} 资金类型 <span class="mini">微信、支付宝、校园卡……记一笔时能选的那些</span></h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto" id="pays-card"></div>
  </div>
  <div class="setsec" data-sec="隐私">${secPrivacy()}</div>
  <div class="setsec" data-sec="AI">
  <h2 class="sec">${ICON.robot} 药品信息怎么用 AI</h2>
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <p class="mini" style="font-size:13px">
      到「物资 → 药品」，每行右侧点「AI」→ 生成「针对疾病 / 使用方法 / 大致功效 / 副作用」→
      <b>核对、修改后</b>再点保存，才会写进那四列（表头标着「AI补充」的
      「针对疾病 / 使用方法 / 大致功效 / 副作用」）。
    </p>
  </div>
  </div>
  <div class="setsec" data-sec="关于">${secAbout()}</div>
  <div class="setsec" data-sec="高级">${secAdvanced()}</div>
  </div>
  </div>`;
  $("#ai-save").onclick = saveSettings;
  $("#ai-test").onclick = testAI;
  $("#ai-models").onclick = refreshModels;
  // 个人基本情况：文本框不像开关那样「点一下就存」，给个明确的保存按钮。
  // ⚠ 保存后 APPCFG 要跟着更新，否则切走再切回来会看到旧内容（读的是缓存）。
  $("#pf-save").onclick = async () => {
    busy();
    const v = $("#pf-text").value;
    const r = await post("/api/settings/save", {personal: v});
    if (r.ok) { APPCFG = Object.assign({}, APPCFG || {}, {personal: v}); toast("已保存"); }
    else toast(r.msg, true);
  };
  $("#pf-notes").onchange = async e => {
    const on = e.target.checked;
    const r = await post("/api/settings/save", {ai_use_notes: on});
    if (r.ok) {
      APPCFG = Object.assign({}, APPCFG || {}, {ai_use_notes: on});
      toast(on ? "分析时会参考最近 3 天的日记" : "已关掉，分析不再读日记");
    } else { e.target.checked = !on; toast(r.msg, true); }
  };
  // 日记还锁着的时候打开这个开关等于白开 —— 后端读不出内容会静默跳过。
  // 这里提前说一声，省得他以为 AI 看了其实没看。
  const pfw = $("#pf-note-warn");
  if (pfw && cfg("ai_use_notes") && APPCFG && APPCFG.crypto &&
      APPCFG.crypto.enabled && !APPCFG.crypto.unlocked) {
    pfw.innerHTML = "⚠ 笔记还锁着，现在打开也读不到内容，先解锁再说";
  }
  const clr = $("#ai-clear");
  if (clr) clr.onclick = async () => {
    if (!confirm("确定清除已保存的 API Key？")) return;
    busy();
    const r = await post("/api/ai/config/save", {clear_key: true});
    if (r.ok) { toast("已清除"); await loadSettings(); } else toast(r.msg, true);
  };
  const uc = $("#ai-uclr");
  if (uc) uc.onclick = async () => {
    if (!confirm("清空用量统计？这只清统计数字，不影响任何数据。")) return;
    busy();
    const r = await post("/api/ai/usage/clear", {});
    if (r.ok) { toast(r.msg); await loadSettings(); } else toast(r.msg, true);
  };
  // ⚠ 必须放在**渲染完之后**：设置页左侧那排分区按钮是这里现生成的，
  // 启动时那次 paintIcons() 根本还没见过它们，不补这一步就是九个空方块。
  // 位置也讲究 —— 之前把这一行写到模块顶层去了，等于每次加载只跑一次，白搭。
  paintIcons();
}
async function refreshModels() {
  busy();
  const r = await post("/api/ai/models", {api_key: $("#ai-key").value.trim()});
  if (r.ok) { toast(r.msg); await loadSettings(); } else toast(r.msg, true);
}

/* ---- 设置页重渲染的**唯一收尾入口** ----
 *
 * ⚠ 这个坑已经踩过四回，每回都是「渲染完了，后处理没做」：
 *     ① saveCfg 忘了重绑  → 改一个设置之后，后面所有控件都点不动
 *     ② renderNoteEditor  → 日记的编辑/分栏/预览三个按钮失灵
 *     ③ renderSettings    → 左侧分区导航九个空图标位
 *     ④ 数据分区那四张卡（学期/备份/回收站/类别）是**另外**几个函数填的，
 *        重渲染一次就全变空白，因为没人再去填
 *   根子是：renderSettings() 把 #tab-set 整个 innerHTML 换掉，
 *   所有绑定和所有异步填充的内容一起没了。所以别再让每个调用点自己
 *   记着「要补哪几个」—— 只留这一个入口，谁都调它。
 */
async function afterRenderSettings() {
  paintIcons();                 // ①
  bindSetNav();
  bindPersonalization();
  bindPersonal();
  bindEmergency();              // 应急信息是同步渲染的，这里只需重绑
  bindBg();                     // 背景图那些控件也是现生成的
  // 这三张卡是同步渲染的（数据直接从 APPCFG 取），登记在这一处就够
  renderPromptCard();
  renderMemCard();
  renderClockCard();
  renderMiscCard();
  renderJsErr();
  // ④ 数据分区那几张卡重新填内容。同样各管各的 ——
  // 这里以前是裸调用，任何一张挂了后面的就都不填了。
  await cardLoad("#where-card", "数据位置", async () => renderWhereCard());
  await cardLoad("#pays-card", "资金类型", async () => bindPays());
  await cardLoad("#cat-card", "账单类别", async () => bindCatManager());
  await cardLoad("#sem-card", "学期管理", async () => { await loadSemesters(); bindSemesterCard(); });
  await cardLoad("#bak-card", "数据备份", loadBackups);
  await cardLoad("#exp-card", "导出 Excel", async () => renderExport());
  await cardLoad("#rc-card", "回收站", loadRecycle);
}

/* ---- 数据备份 ---- */
let BAKLIST = null;
async function loadBackups() {
  const r = await get("/api/backup/list");
  BAKLIST = r.ok ? (r.data || []) : [];
  renderBackups();
}
function renderBackups() {
  const card = $("#bak-card");
  if (!card) return;
  const list = BAKLIST || [];
  const kb = n => n > 1024 * 1024 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
  /* ⚠ 这里原来是一句**写死的**字符串「目录：个人信息统计\_自动备份\」。
     设置里能改备份目录（server.py 的 backup_dir），改完之后那句话就成了假话 ——
     界面指着 A 目录，真备份在 B 目录。而「我的备份在哪」正是最不该说错的一句话。
     后端 backup_list 其实**每项都带 dir**（和 elsewhere），照着列就行，不用改后端。
     只取目录名，不显示整条盘符路径 —— 太长会把这行挤烂；完整路径放 title 里。 */
  const leaf = p => String(p || "").replace(/[\\/]+$/, "").split(/[\\/]/).filter(Boolean).pop() || p;
  const dirs = [...new Set(list.map(b => b.dir).filter(Boolean))];
  const dirTip = dirs.length
    ? `目录：${dirs.map(d => `<span title="${esc(d)}">${esc(leaf(d))}</span>`).join(" 和 ")}`
    : "目录：还没生成过备份";
  card.innerHTML = `
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
      <button class="btn" id="bak-now">立即备份</button>
      <button class="btn ghost sm" id="bak-refresh">刷新列表</button>
      <span class="mini">${list.length} 份备份 · ${dirTip}</span>
    </div>
    ${list.length ? `<table><thead><tr><th>时间</th><th>数据</th><th>文件</th>
      <th class="num">大小</th><th>类型</th><th></th></tr></thead><tbody>
      ${list.map(b => `<tr>
        <td>${b.mtime}</td><td>${esc(b.target)}</td>
        <td class="mini">${esc(b.file)}${b.elsewhere
          ? ` <span class="badge tagw" title="这份备份在旧目录里（${esc(b.dir)}）">旧位置</span>` : ""}</td>
        <td class="num">${kb(b.size)}</td>
        <td>${b.prerestore ? '<span class="badge tagw">恢复前存档</span>'
              : b.manual ? '<span class="badge tagg">手动</span>'
              : '<span class="badge tagd">自动</span>'}</td>
        <td><button class="btn ghost sm" data-bak-restore="${esc(b.file)}">恢复</button></td>
      </tr>`).join("")}</tbody></table>`
      : emptyBox("还没有备份", "点上面的「立即备份」存一份")}
    <p class="mini" style="margin-top:10px">
      ⚠ 恢复会<b>覆盖当前数据</b>。为防止误操作，恢复前系统会自动把当前状态另存一份
      （列表里标「恢复前存档」的那些），所以恢复本身也是可以退回去的。
    </p>`;
  $("#bak-now").onclick = async () => {
    busy();
    const r = await post("/api/backup/now", {});
    if (r.ok) { toast(r.msg); await loadBackups(); } else toast(r.msg, true);
  };
  $("#bak-refresh").onclick = () => loadBackups();
  $$("#bak-card [data-bak-restore]").forEach(btn => btn.onclick = async () => {
    const file = btn.dataset.bakRestore;
    if (!confirm(`用这份备份覆盖当前数据？\n\n${file}\n\n` +
                 `· 当前状态会先自动另存一份，可以再退回来\n` +
                 `· 恢复期间别关程序`)) return;
    busy();
    const r = await post("/api/backup/restore", {file});
    if (!r.ok) { toast(r.msg, true); return; }
    toast(r.msg);
    BILL = null; CHECK = null; STOCK = null;
    await loadBackups();
    await loadOverview();
  });
}

/* ================================================================
   看图录入：账单截图 / 睡眠截图

   三步：**选图 → 识别 → 核对 → 确认**。中间那步不能省。
   模型看错一位数是常事，而账目和睡眠是长期数据，错一笔要翻半天账。
   所以后端那个接口一个字都不写库，只把认出来的东西还回来；
   真正落库走的是**普通那条 bill/add、check/set 通路** ——
   跟手动输的完全一样，出了问题也好排查。
================================================================ */
let SHOT = null;
let SHOT_PASTE = null;

function openShot(kind) {
  SHOT = {kind: kind, dataUrl: null, result: null, busy: false};
  modal(kind === "bill" ? "从截图记一笔" : "从截图录睡眠", shotBody(), null, ICON.camera);
  // 这张卡是两步的，底部那个「保存」不适用 —— 藏掉，用卡里自己的按钮
  const ok = $("#m-ok");
  if (ok) ok.hidden = true;
  bindShot();
  // Ctrl+V 直接贴图。监听器挂在 document 上，所以关弹窗时一定要摘掉，
  // 不然贴一次图会往这个已经关掉的卡片里塞十遍
  SHOT_PASTE = e => {
    const items = (e.clipboardData && e.clipboardData.items) || [];
    for (const it of items) {
      if (it.type && it.type.startsWith("image/")) {
        e.preventDefault();
        readShotFile(it.getAsFile());
        return;
      }
    }
  };
  document.addEventListener("paste", SHOT_PASTE);
}

function closeShot() {
  if (SHOT_PASTE) { document.removeEventListener("paste", SHOT_PASTE); SHOT_PASTE = null; }
  $("#modal").hidden = true;
}

function shotBody() {
  const isBill = SHOT.kind === "bill";
  return `
  <div class="mini" style="margin-bottom:10px;font-size:13px">
    ${isBill ? "微信/支付宝的付款截图、外卖订单、银行短信截图都行。"
             : "手环/手表/手机健康 App 的睡眠记录截图。"}
    认出来的东西会先摊在这儿让你核对，<b>你觉得对了才写进去</b>。
  </div>
  <div id="shot-drop" class="shotdrop">
    <div class="shotbig">${ICON.camera}</div>
    <div>把截图拖进来，或点这里选一张</div>
    <div class="mini">也可以直接按 <kbd>Ctrl</kbd>+<kbd>V</kbd> 粘贴</div>
    <input type="file" id="shot-file" accept="image/*" hidden>
  </div>
  <div id="shot-prev"></div>
  <div id="shot-res"></div>`;
}

function bindShot() {
  const drop = $("#shot-drop");
  if (!drop) return;
  const fi = $("#shot-file");
  drop.onclick = () => fi.click();
  fi.onchange = () => { if (fi.files && fi.files[0]) readShotFile(fi.files[0]); };
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("on"); };
  drop.ondragleave = () => drop.classList.remove("on");
  drop.ondrop = e => {
    e.preventDefault(); drop.classList.remove("on");
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) readShotFile(f);
  };
}

function readShotFile(file) {
  if (!file || !file.type || !file.type.startsWith("image/")) {
    return toast("这个不是图片文件", true);
  }
  const rd = new FileReader();
  rd.onload = () => {
    SHOT.dataUrl = String(rd.result || "");
    SHOT.result = null;
    renderShotPreview();
  };
  rd.onerror = () => toast("这张图读不出来", true);
  rd.readAsDataURL(file);
}

function renderShotPreview() {
  const box = $("#shot-prev");
  if (!box) return;
  const mb = (SHOT.dataUrl.length * 0.75 / 1048576).toFixed(1);
  box.innerHTML = `
    <div class="shotprev"><img src="${SHOT.dataUrl}" alt="预览"></div>
    <div class="mini" style="margin:6px 0 10px">约 ${mb} MB</div>
    <div style="display:flex;gap:8px">
      <button class="btn" id="shot-run">${ICON.sparkle} 让 AI 认一下</button>
      <button class="btn ghost sm" id="shot-again">换一张</button>
      <button class="btn ghost sm" id="shot-cancel">取消</button>
    </div>
    <div id="shot-res"></div>`;
  $("#shot-run").onclick = runShot;
  $("#shot-again").onclick = () => { SHOT.dataUrl = null; SHOT.result = null;
    $("#shot-prev").innerHTML = ""; $("#shot-drop").hidden = false; bindShot(); };
  $("#shot-cancel").onclick = closeShot;
  $("#shot-drop").hidden = true;
}

async function runShot() {
  const btn = $("#shot-run");
  if (btn) { btn.disabled = true; btn.textContent = "识别中…（一张图大概十几秒）"; }
  const res = $("#shot-res");
  if (res) res.innerHTML = '<p class="mini">正在看图…</p>';
  const r = await post("/api/ai/vision", {kind: SHOT.kind, image: SHOT.dataUrl});
  if (!r.ok) {
    if (btn) { btn.disabled = false; btn.textContent = "再试一次"; }
    if (res) res.innerHTML = `<div class="warn">${esc(r.msg)}</div>`;
    return;
  }
  SHOT.result = r.data;
  renderShotResult();
}

function renderShotResult() {
  const d = SHOT.result || {};
  const res = $("#shot-res");
  const warn = d.tip ? `<div class="warn" style="font-weight:400">⚠ ${esc(d.tip)}</div>` : "";
  const head = `
    <div style="display:flex;gap:8px;margin-top:10px">
      <button class="btn" id="shot-ok">${ICON.check} 确认录入</button>
      <button class="btn ghost sm" id="shot-retry">认错了，换一张</button>
      <button class="btn ghost sm" id="shot-cancel2">取消</button>
    </div>
    <p class="mini" style="margin-top:8px">
      原图存在 <code>附件\\${esc((d.attach || "").split("/")[0])}\\</code>，
      没被引用的图 30 天后会自动清掉。
    </p>`;

  if (SHOT.kind !== "bill") {                    // 睡眠：还是那一张表单
    const f = d.fields || {};
    res.innerHTML = `
      <hr style="margin:14px 0">
      <div style="font-weight:600;margin-bottom:6px">核对一下</div>
      ${warn}
      <div class="form">
        <div class="f"><label>日期（起床那天）</label><input id="s-date" type="date" value="${esc(f.date || "")}"></div>
        <div class="f"><label>入睡</label><input id="s-sleep" placeholder="HH:MM" value="${esc(f.sleep || "")}"></div>
        <div class="f"><label>起床</label><input id="s-wake" placeholder="HH:MM" value="${esc(f.wake || "")}"></div>
        <div class="f"><label>质量</label><select id="s-quality">
          ${((CHECK && CHECK.opts && CHECK.opts.mood) || ["好", "一般", "差"]).map(c =>
            `<option${c === f.quality ? " selected" : ""}>${esc(c)}</option>`).join("")}
        </select></div>
        <div class="f"><label>夜醒次数</label><input id="s-wakecount" type="number" min="0"
          value="${f.wake_count === null || f.wake_count === undefined ? "" : esc(f.wake_count)}"></div>
      </div>
      ${head}`;
    $("#shot-ok").onclick = confirmShot;
  } else {
    SHOT.items = (d.items || []).map(x => Object.assign({_on: true}, x));
    res.innerHTML = `
      <hr style="margin:14px 0">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">
        <b>认出 ${SHOT.items.length} 条</b>
        <button class="btn ghost sm" id="shot-all">全不选</button>
        <span class="mini" id="shot-sum"></span>
      </div>
      ${warn}
      <div class="shotlist"><table><thead><tr>
        <th></th><th>日期</th><th>方向</th><th class="num">金额</th>
        <th>类别</th><th>项目</th><th>支付</th></tr></thead>
        <tbody id="shot-rows"></tbody></table></div>
      ${head}`;
    renderShotRows();
    $("#shot-all").onclick = () => {
      const on = SHOT.items.some(x => !x._on);       // 有没选的 → 全选；否则全不选
      SHOT.items.forEach(x => { x._on = on; });
      renderShotRows();
    };
    $("#shot-ok").onclick = confirmShot;
  }
  $("#shot-retry").onclick = () => { SHOT.dataUrl = null; SHOT.result = null;
    $("#shot-prev").innerHTML = ""; $("#shot-drop").hidden = false; bindShot(); };
  $("#shot-cancel2").onclick = closeShot;
}

/** 逐条渲染成可改的行。「哪一条不要」用勾选框，改错了直接改格子。 */
function renderShotRows() {
  const box = $("#shot-rows");
  if (!box) return;
  box.innerHTML = SHOT.items.map((it, i) => `<tr class="${it._on ? "" : "off"}">
    <td><input type="checkbox" data-son="${i}"${it._on ? " checked" : ""}></td>
    <td><input type="date" data-sf="${i}" data-k="date" value="${esc(it.date || "")}"></td>
    <td><select data-sf="${i}" data-k="direction">
      ${["支出", "收入"].map(v => `<option${it.direction === v ? " selected" : ""}>${v}</option>`).join("")}
    </select></td>
    <td><input type="number" step="0.01" class="num" data-sf="${i}" data-k="amount"
        value="${it.amount || ""}"></td>
    <td><select data-sf="${i}" data-k="cat">
      <option value=""${!it.cat ? " selected" : ""}>（未认出）</option>
      ${[...expCats(), ...incCats()].map(c =>
        `<option${it.cat === c ? " selected" : ""}>${esc(c)}</option>`).join("")}
    </select></td>
    <td><input data-sf="${i}" data-k="note" value="${esc(it.note || "")}"></td>
    <td><select data-sf="${i}" data-k="pay">
      <option value=""${!it.pay ? " selected" : ""}>（未认出）</option>
      ${pays().map(c => `<option${it.pay === c ? " selected" : ""}>${esc(c)}</option>`).join("")}
    </select></td>
  </tr>`).join("");
  box.onchange = e => {
    const el = e.target;
    if (el.dataset.son !== undefined) {
      SHOT.items[+el.dataset.son]._on = el.checked;
      const tr = el.closest("tr");
      if (tr) tr.classList.toggle("off", !el.checked);
      shotSummary();
      return;
    }
    const i = +el.dataset.sf, k = el.dataset.k;
    if (!el.dataset.sf || !k) return;
    SHOT.items[i][k] = k === "amount" ? (parseFloat(el.value) || 0) : el.value;
    shotSummary();
  };
  shotSummary();
}

function shotSummary() {
  const el = $("#shot-sum");
  if (!el) return;
  const on = SHOT.items.filter(x => x._on);
  const sum = on.reduce((a, x) => a + (x.direction === "收入" ? 0 : (Number(x.amount) || 0)), 0);
  el.innerHTML = `已勾选 ${on.length} 条 · 支出合计 <b>${money(sum)}</b>` +
    (on.some(x => !x.date) ? ` · <span class="a">有 ${on.filter(x => !x.date).length} 条没日期</span>` : "");
}

async function confirmShot() {
  const g = id => { const el = $("#" + id); return el ? el.value : ""; };
  const kind = SHOT.kind;
  if (kind !== "bill") {
    const date = g("s-date");
    if (!date) return toast("先把日期填上", true);
    const r = await saveSleepShot(date);
    if (!r.ok) return toast(r.msg, true);
    toast("已录入 —— " + r.msg);
    closeShot();
    CHECK = null; await loadCheck();
    return;
  }

  // 账单：把勾上的逐条写进去。
  // **逐条调用普通的 bill/add** —— 不复用截图专线，跟手动记一笔走的是同一条路，
  // 出了问题好排查，也不会有「AI 专线写坏了没人知道」这种事。
  const on = (SHOT.items || []).filter(x => x._on);
  if (!on.length) return toast("一条都没勾，没什么可录的", true);
  const noDate = on.filter(x => !x.date).length;
  if (noDate) return toast(`有 ${noDate} 条没填日期，补上再确认`, true);

  busy();
  let ok = 0;
  const bad = [];
  for (const it of on) {
    const amt = Number(it.amount) || 0;
    if (amt <= 0) { bad.push((it.note || "某一条") + "（金额是 0）"); continue; }
    const r = await post("/api/bill/add", {
      date: it.date, cat: it.cat || "其他", note: it.note,
      inc: it.direction === "收入" ? amt : "",
      exp: it.direction === "支出" ? amt : "",
      pay: it.pay || "微信", grp: "否", stat: ""});
    if (r.ok) ok++; else bad.push((it.note || "某一条") + "（" + r.msg + "）");
  }
  idle();
  if (!ok) return toast("一条都没写进去：" + bad.slice(0, 2).join("；"), true);
  toast(bad.length
    ? `录进 ${ok} 条，${bad.length} 条没成：${bad.slice(0, 2).join("；")}`
    : `已录入 ${ok} 条`);
  closeShot();
  BILL = null; await loadBill();
}

/** 睡眠截图要写四个格子（入睡/起床/质量/夜醒）。
 *  check/set 一次只写一个，所以连发几次 —— 都是小事务，没有「写一半」的问题。 */
async function saveSleepShot(date) {
  const g = id => { const el = $("#" + id); return el ? el.value.trim() : ""; };
  const d = new Date(date + "T00:00:00");
  const sheet = d.getFullYear() + "年" + String(d.getMonth() + 1).padStart(2, "0") + "月";
  const day = d.getDate();
  const jobs = [["C", g("s-sleep")], ["D", g("s-wake")],
                ["I", g("s-quality")], ["J", g("s-wakecount")]];
  let n = 0;
  for (const [col, val] of jobs) {
    if (val === "") continue;
    const r = await post("/api/check/set", {sheet: sheet, day: day, col: col, value: val});
    if (!r.ok) return r;
    n++;
  }
  return n ? {ok: true, msg: "写了 " + n + " 项到 " + sheet + " " + day + " 号"}
           : {ok: false, msg: "一项都没填，没什么可录的"};
}

/* ---- 导出成 Excel ---- */
let EXPLAST = null;
/* ---- 打开文件夹 / 选文件夹（2.3.6）----
   ⚠ 这两件事**只有桌面版做得到**。浏览器里没这个能力，也不能假装有 ——
     统一在这里判一次，做不了就返回 false，让调用方去走「复制路径」那条退路。
     不要在十几处各写一遍 `window.xrShell && …`（那种散落的判断迟早漏一处）。 */
function canOpenDir() { return !!(window.xrShell && window.xrShell.openPath); }

/** 数据目录。是问后端要的（/api/about），可能比设置页晚到 ——
 *  所以用函数现取，不要在模块加载时算死一个值。 */
const dataDir = () => (ABOUT && ABOUT.data_root) || "";

/* ⚠ 这里**曾经**有一个 `const sleep = ms => …`，删掉了。
   原因：测试页 _test.html 自己也声明了一个顶层 `sleep`，而两个顶层
   `const` 同名时，**后加载的那个脚本整个解析失败** —— app.js 直接不执行，
   页面一片空白，`node --check` 还查不出来（单看这个文件是合法的）。
   表现是「总览页什么都没渲染 + APPCFG is not defined」，查了好一阵。
   所以：**别给 app.js 加通用的工具名**（sleep/esc/qs… 测试页都可能有）。
   要等一会儿就就地写 `new Promise(r => setTimeout(r, ms))`。 */

/** 打开一个文件夹。传的是文件就打开它所在的目录。返回 true = 真的打开了 */
async function openDir(p) {
  if (!canOpenDir()) return false;
  const err = await window.xrShell.openPath(p);
  if (err) toast(err, true);
  return !err;
}

/** 打开文件夹并把这个文件选中（导出之后最想要的其实是这个） */
async function showItem(p) {
  if (!(window.xrShell && window.xrShell.showItem)) return false;
  const err = await window.xrShell.showItem(p);
  if (err) toast(err, true);
  return !err;
}

/* ⚠ 这里原来有**第二个** copyText —— 只试 navigator.clipboard，失败就 return false。
   而上面（约 4499 行）那个版本带「退回老办法」（临时 textarea + execCommand）。
   同一个名字定义两次，**后定义的赢**（函数声明整体提升，后者覆盖前者），
   于是那份完整的兜底**从来没生效过**：
     · file:// 打开、或老浏览器不给剪贴板权限时，copyText 一律 false
     · 结果 app.js 里两处调用会给出**相反的提示** ——
       「加到日历」那条本该说「路径已复制」，却去说「日历文件在：<路径>」（那是打不开时的文案）
       复制脚本错误那条点了没反应
   这就是交接文档 B1 那一家的：**不报错，只是行为跟你以为的不一样。**
   现已删掉这个简化版，只留带兜底的那个。 */

/** 「打开所在文件夹」的统一退路：打不开就把路径塞进剪贴板 */
async function openDirOrCopy(p) {
  if (await openDir(p)) { toast("已打开文件夹"); return; }
  if (await copyText(p)) { toast("打不开文件夹，路径已复制 —— 去资源管理器粘一下"); return; }
  toast("打不开文件夹，路径是：" + p, true);
}

/* ---- 笔记导出（2.3.6）----
   正文的 HTML 在**前端**用屏幕上那套 md() 生成好再传上去。
   后端没有 Markdown 解析器，也不打算为导出再写一个 —— 两边各写一套，
   迟早出现「屏幕上一个样、导出一个样」。
   Word 版是「HTML 存成 .doc」：Word 本来就能开 HTML，省掉手写 OOXML 的两百行。 */
async function _inlineImages(text) {
  /* 导出成单文件时，图片得**内嵌**进去 —— 留个「附件/x.jpg」的相对路径，
     文件发给别人就是一堆裂图。这里把每张图读成 base64 替换掉。 */
  const names = [...new Set([...String(text).matchAll(/\]\(附件\/([^)\s]+)\)/g)]
    .map(m => m[1]))];
  let out = String(text);
  for (const n of names) {
    try {
      const b = await (await fetch("/attach/" + n)).blob();
      const data = await new Promise(ok => {
        const fr = new FileReader();
        fr.onload = () => ok(fr.result);
        fr.readAsDataURL(b);
      });
      out = out.split("附件/" + n).join(data);
    } catch (e) {
      // 图没了就留着原路径 —— 不能因为一张图让整次导出失败
    }
  }
  return out;
}

async function exportNotes(kind, fmt) {
  const r0 = await get("/api/notes/list");
  const list = ((r0.data || {})[kind] || []);
  if (!list.length) return toast("这一类还没有内容", true);
  busy();
  let html = "", n = 0;
  try {
    for (const it of (fmt === "md" ? [] : list)) {
      const r = await post("/api/notes/get", {type: kind, name: it.name});
      if (!r.ok) continue;
      const body = await _inlineImages((r.data || {}).content || "");
      html += `<h2>${esc(it.title || it.display)}</h2>` + md(body) + "<hr>";
      n++;
    }
    const r = await post("/api/notes/export", {type: kind, fmt, html, count: n});
    idle();
    if (!r.ok) return toast(r.msg, true);
    const dir = r.data.kind === "dir" ? r.data.path
      : r.data.path.replace(/[\\/][^\\/]*$/, "");
    toast(r.msg);
    if (canOpenDir() && confirm(r.msg + "\n\n现在打开那个文件夹吗？")) {
      await openDirOrCopy(dir);
    }
  } catch (e) {
    idle();
    toast("导出出错：" + e.message, true);
  }
}

/* ---- 笔记插图（2.3.6）----
   选图 → 缩到 1600px → 传上去 → 在光标处插一段 Markdown。
   缩放直接复用背景图那套 shrinkImage（同一份逻辑，不另写一个），
   服务端只落盘、按内容哈希命名（同一张图传两次只存一份）。 */
function bindInsertImage(btnSel, taSel) {
  const btn = $(btnSel), ta = $(taSel);
  if (!btn || !ta) return;
  btn.onclick = () => {
    // ⚠ 每次现建一个 input。复用一个的话，**选同一张图第二次不触发 change**
    //   （value 没变），表现成「点了没反应」。
    const f = document.createElement("input");
    f.type = "file";
    f.accept = "image/*";
    f.onchange = async () => {
      const file = f.files && f.files[0];
      if (!file) return;
      busy();
      try {
        const data = await shrinkImage(file, 1600, 0.85);
        const r = await post("/api/notes/attach", {data});
        if (!r.ok) { idle(); return toast(r.msg, true); }
        const s = ta.selectionStart == null ? ta.value.length : ta.selectionStart;
        ta.value = ta.value.slice(0, s) + "\n" + r.data.md + "\n" + ta.value.slice(s);
        // 手动派发 input：不派发的话自动保存不会触发，图就白插了
        ta.dispatchEvent(new Event("input"));
        toast("图插进来了（" + r.data.kb + " KB）");
      } catch (e) {
        toast("这张图读不出来：" + e.message, true);
      }
      idle();
    };
    f.click();
  };
}

/* ================= 随笔 + 摘抄（2.3.6）=================

   随笔 = notes 的一种（kind=essay），**跟日记同目录、不同文件**，
   所以回忆书搜得到，又不会跟日报混在一起（用户明确要的）。
   摘抄 = kv 里的一份 JSON 清单。

   ⚠ 页面**不复制日记页那套**（它有生成周报、提取待办这些随笔用不上的按钮），
     但存储和接口跟日记是同一套 —— 别再造一份读写逻辑。 */
let QUOTES = null, essayCur = null, essaySub = "essay", essayDraft = null;

async function loadEssay() {
  const [l, q] = await Promise.all([get("/api/notes/list"), post("/api/quote/list", {})]);
  if (l.ok) NOTES = l.data;
  if (q.ok) QUOTES = q.data;
  renderEssay();
}

function renderEssay() {
  const box = $("#tab-essay");
  if (!box) return;
  const list = (NOTES && NOTES.essay) || [];
  if (!essayCur && list.length) essayCur = list[0].name;
  const cur = list.find(x => x.name === essayCur);
  box.innerHTML = `
  <div class="pagehead">
    <div class="ph-title">${ICON.quote} 随笔</div>
    <div class="ph-sub">想到什么写什么。跟日记分开存，但回忆书两边都能搜到。</div>
    <div class="ph-actions">
      <div class="seg segsm">
        <button class="segbtn${essaySub === "essay" ? " on" : ""}" data-esub="essay">随笔</button>
        <button class="segbtn${essaySub === "quote" ? " on" : ""}" data-esub="quote">摘抄</button>
      </div>
    </div>
  </div>
  ${essaySub === "essay" ? `
  <!-- ⚠ 这里原来写的是 class="nwrap" / "nt" / "ns" / "nmain" ——
       **四个类名在 style.css 里一个都没有**。2.3.6 加随笔页时起了名字，
       样式从来没写，所以整页是"没布局"的状态：
         · 左边那列被拉成整页宽
         · 「写一篇」按钮横贯整个页面（用户截图里那根色条的真正原因）
         · 编辑区掉到列表下面去
       现在改用日记页**已经在用**的那套（nlayout / nside / nitem /
       nname / nprev / nhead），一个类名都不用新增。
       这比"给 nwrap 补一条样式"更对：本来就是同一个形状，
       没道理为它单独维护一套。 -->
  <div class="nlayout">
    <div class="nside">
      <div style="padding:9px 10px 4px">
        <button class="btn line sm" id="es-new" style="width:100%">
          ${ICON.pencil} 写一篇</button>
      </div>
      <div class="nlist">
      ${list.length ? list.map(x => `<div class="nitem${x.name === essayCur ? " on" : ""}"
        data-es="${esc(x.name)}">
        <div class="nname">${esc(x.display)}</div>
        <div class="nprev">${esc(x.preview || x.sub || "")}</div></div>`).join("")
        : '<p class="mini" style="padding:12px">还没有随笔。点上面那个按钮写第一篇。</p>'}
      </div>
    </div>
    <div class="ncard">
      ${cur ? `
        <div class="nhead">
          <b>${esc(cur.display)}</b><span class="mini"> · ${esc(cur.sub || "")}</span>
          <span style="margin-left:auto"></span>
          <!-- 随笔原本**只有编辑框、没有预览**（日记页早就有编辑/预览/对照三档）。
               2.4.7 补上：这样随笔也能用竖排「像古籍那样读」，
               而编辑那一侧仍然是现代的横排框。 -->
          <div class="seg segsm nmode">
            <button class="segbtn${essayMode === "edit" ? " on" : ""}" data-emode="edit"
              title="只显示编辑框">编辑</button>
            <button class="segbtn${essayMode === "view" ? " on" : ""}" data-emode="view"
              title="只显示排好版的正文">预览</button>
            <button class="segbtn${essayMode === "split" ? " on" : ""}" data-emode="split"
              title="左边写、右边看">对照</button>
          </div>
          <button class="btn ghost sm" id="es-img">${ICON.image} 插图</button>
          <button class="btn ghost sm" id="es-exp">导出</button>
          <button class="btn ghost sm" id="es-del">删</button>
          <button class="btn sm" id="es-save">保存</button>
        </div>
        <div class="nbody ${essayMode}">
          <textarea id="es-body" rows="18"></textarea>
          <div class="nview md" id="es-view"></div>
        </div>`
        : '<div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><p class="mini" style="margin:0">左边选一篇，或者点「写一篇」。</p></div>'}
    </div>
  </div>` : `
  <div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="form" style="align-items:flex-end">
      <div class="f" style="flex:1;min-width:220px">
        <label>记下一句</label>
        <textarea id="q-text" rows="2" placeholder="读到、听到、想到的一句话"></textarea>
      </div>
      <div class="f"><label>出处</label>
        <input id="q-from" placeholder="谁说的 / 哪本书" style="width:150px"></div>
      <div class="f"><label>标签</label>
        <input id="q-tags" placeholder="用空格分开" style="width:150px"></div>
      <div class="f" style="flex:1;min-width:180px">
        <label>我为什么记它</label>
        <input id="q-note" placeholder="当时想到了什么"></div>
      <button class="btn" id="q-add">收下</button>
    </div>
    ${QUOTES && QUOTES.n ? `<p class="mini" style="margin:10px 0 0">
      共 ${QUOTES.n} 条${Object.keys(QUOTES.tags || {}).length ? " · " + Object.keys(QUOTES.tags)
        .map(t => `<a href="#" data-qtag="${esc(t)}" style="margin-right:8px">#${esc(t)}
        <span class="mini">${QUOTES.tags[t]}</span></a>`).join("") : ""}</p>` : ""}
  </div>
  ${(QUOTES && QUOTES.quotes || []).length ? (QUOTES.quotes || []).map(q => `
    <div class="card qcard bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
      <div class="qtext">${esc(q.text)}</div>
      ${q.from ? `<div class="mini">—— ${esc(q.from)}</div>` : ""}
      ${q.note ? `<div class="qnote">${esc(q.note)}</div>` : ""}
      <div style="display:flex;gap:8px;align-items:center;margin-top:8px">
        ${(q.tags || []).map(t => `<span class="chip">#${esc(t)}</span>`).join("")}
        <span class="mini" style="margin-left:auto">${esc(q.at)}</span>
        <button class="btn ghost sm" data-qdel="${q.id}">删</button>
      </div>
    </div>`).join("") : '<div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto"><p class="mini" style="margin:0">还没有摘抄。</p></div>'}`}`;
  bindEssay();
}

/** 随笔预览（2.4.7）。跟日记的 renderNotePreview 一个套路，只是容器和数据源不同。
 *  ⚠ 随笔的正文**只有一个来源**：`#es-body` 那个 textarea。
 *    没有「已保存内容」的缓存对象（日记才用 noteCur）——
 *    所以这里**不要**去碰 noteCur，那是日记的变量，随笔引用它只会读到别人的内容。
 *  ⚠ 随笔**也竖排**（用户 2026-09-20 说「随笔也是」）。
 *    这里直接 add，不走日记那个白名单 —— 两条路径各自显式声明，
 *    比共用一个名单更难漏（交接文档 B1：共用清单漏一处就长出死按钮）。 */
function renderEssayPreview() {
  const box = $("#es-view");
  if (!box) return;
  const ta = $("#es-body");
  box.classList.add("nview-v");
  box.innerHTML = md(ta ? ta.value : "");
  // ⚠ 随笔也是竖排，所以同样要把成串的拉丁字母转回横躺 ——
  //   不然随笔里写 `DeepSeek` 会变成一列上下叠着的字母。
}

function bindEssay() {
  $$("[data-esub]").forEach(b => b.onclick = () => { essaySub = b.dataset.esub; renderEssay(); });
  $$("[data-emode]").forEach(b => b.onclick = () => {
    essayMode = b.dataset.emode;
    // ⚠ 只保存起「已输入但还没落盘」的内容，然后整页重渲染 ——
    //   跟日记页一样：模式按钮是 segbtn，重画才会上/下高亮。
    const ta = $("#es-body");
    if (ta && essayCur && ta.value !== (essayDraft ? essayDraft.text : null)) {
      essayDraft = {name: essayCur, text: ta.value};
    }
    renderEssay();
  });
  $$("[data-es]").forEach(x => x.onclick = async () => {
    essayCur = x.dataset.es;
    await loadEssayBody();
    renderEssay();
  });
  const nw = $("#es-new");
  if (nw) nw.onclick = async () => {
    const r = await post("/api/notes/new", {type: "essay"});
    if (!r.ok) return toast(r.msg, true);
    essayCur = r.data.name;
    NOTES = null;
    await loadEssay();
    const b = $("#es-body");
    if (b) { b.value = ""; b.focus(); }
  };
  const body = $("#es-body");
  if (body && essayCur) {
    if (essayDraft && essayDraft.name === essayCur) body.value = essayDraft.text;
    else loadEssayBody().then(renderEssayPreview);   // 正文到了再画预览（竖排那侧）
    // 停手 1.5 秒自动保存 —— 跟日记页一个规矩，不留「保存」焦虑
    let t = 0;
    body.oninput = () => {
      essayDraft = {name: essayCur, text: body.value};
      if (essayMode === "split") renderEssayPreview();
      clearTimeout(t);
      t = setTimeout(() => saveEssay(true), 1500);
    };
    if (essayMode !== "edit") renderEssayPreview();
  }
  const sv = $("#es-save");
  if (sv) sv.onclick = () => saveEssay(false);
  bindInsertImage("#es-img", "#es-body");
  const ex = $("#es-exp");
  if (ex) ex.onclick = async () => {
    // ⚠ 原来用 prompt()（Electron 16+ 已移除 → 打包版点了没反应）。改 askText。
    //   这个箭头函数**必须 async**：askText 返回 Promise。
    const f = await askText({
      title: "把随笔导出成什么格式", label: "格式", value: "1", ph: "1",
      hint: "1 = Word（能改、能发人）　2 = Markdown（原样留底）　3 = HTML（打开后 Ctrl+P 存成 PDF）"});
    if (f === null || !f.trim()) return;
    exportNotes("essay", f.trim() === "2" ? "md" : (f.trim() === "3" ? "html" : "doc"));
  };
  const del = $("#es-del");
  if (del) del.onclick = async () => {
    if (!confirm("删掉这篇随笔？会先进回收站，能捡回来。")) return;
    const r = await post("/api/notes/del", {type: "essay", name: essayCur});
    if (!r.ok) return toast(r.msg, true);
    toast("已删");
    essayCur = null; essayDraft = null; NOTES = null;
    loadEssay();
  };
  // 摘抄
  const add = $("#q-add");
  if (add) add.onclick = async () => {
    const text = $("#q-text").value.trim();
    if (!text) return toast("至少写一句", true);
    const list = [{
      text, from: $("#q-from").value.trim(),
      tags: $("#q-tags").value.trim().split(/\s+/).filter(Boolean),
      note: $("#q-note").value.trim(),
    }].concat((QUOTES && QUOTES.quotes) || []);
    const r = await post("/api/quote/save", {quotes: list});
    if (!r.ok) return toast(r.msg, true);
    toast("收下了");
    ["#q-text", "#q-from", "#q-tags", "#q-note"].forEach(s => { const e = $(s); if (e) e.value = ""; });
    QUOTES = r.data; renderEssay();
  };
  $$("[data-qdel]").forEach(b => b.onclick = async () => {
    const list = ((QUOTES && QUOTES.quotes) || []).filter(q => q.id !== b.dataset.qdel);
    const r = await post("/api/quote/save", {quotes: list});
    if (!r.ok) return toast(r.msg, true);
    QUOTES = r.data; toast("已删"); renderEssay();
  });
}

async function loadEssayBody() {
  if (!essayCur) return;
  const r = await post("/api/notes/get", {type: "essay", name: essayCur});
  const b = $("#es-body");
  if (b && r.ok) b.value = (r.data || {}).content || "";
}

async function saveEssay(quiet) {
  const b = $("#es-body");
  if (!b || !essayCur) return;
  // 正文第一行就是标题，写回去时会重排 —— 直接把编辑区原文存下去
  const r = await post("/api/notes/save", {type: "essay", name: essayCur, content: b.value});
  if (!r.ok) return toast(r.msg, true);
  essayDraft = null;
  if (!quiet) toast("已保存");
  NOTES = null;
  markDirty("note");
}

/* ---- AI 提示词 / 回忆书检索参数 / 牛马时钟（2.3.6）----
   三张卡都是「读设置 → 画控件 → 存回去」，没有别的花样。
   ⚠ 提示词的约定（和后端 prompt_override 一致）：**空 = 用代码里那份**。
     所以「恢复默认」就是把输入框清空再保存，不需要另开一个接口。 */
const PROMPT_DEFS = [
  ["prompt_daily", "日报整理", "把随手记揉成一篇日报时用。它决定 AI 的语气和详略"],
  ["prompt_weekly", "周报汇总", "读一周的日报生成周报时用"],
  ["prompt_monthly", "月报汇总", "读一个月的周报生成月报时用"],
  ["prompt_memory", "回忆书回答", "回忆书里 AI 怎么回答你。里面 {who} 会被换成对你的称呼"],
];

function renderPromptCard() {
  const c = $("#prompt-card");
  if (!c) return;
  // 省钱提示。数字全部来自用户自己的用量记录 —— 说「AI 很贵」没用，
  // 说「你这 76% 花在输入框补全上、59% 花在高峰时段」才有用。
  const tr = (AIUSAGE && AIUSAGE.calls) || [];
  const tot = tr.reduce((a, x) => a + (x.cost || 0), 0);
  const peak = tr.reduce((a, x) => a + (x.peak ? (x.cost || 0) : 0), 0);
  const by = {};
  tr.forEach(x => { by[x.scope] = (by[x.scope] || 0) + (x.cost || 0); });
  const top = Object.entries(by).sort((a, b) => b[1] - a[1])[0];
  const SCOPE_CN = {suggest: "输入框补全", analyze: "总览分析", report: "周报月报",
                    memory: "回忆书", drug: "药品信息", shelf: "开封后估期",
                    test: "连接测试", other: "其他"};
  const now = new Date();
  const isPeak = now.getDay() >= 1 && now.getDay() <= 5 &&
    ((now.getHours() >= 9 && now.getHours() < 12) ||
     (now.getHours() >= 14 && now.getHours() < 18));
  const tips = [];
  if (top && tot > 0 && top[1] / tot > 0.4) {
    tips.push(`你这 ¥${tot.toFixed(3)} 里有 <b>${Math.round(top[1] / tot * 100)}%</b>
      花在「${SCOPE_CN[top[0]] || top[0]}」上（¥${top[1].toFixed(3)}）。`);
  }
  if (tot > 0 && peak / tot > 0.3) {
    tips.push(`<b>${Math.round(peak / tot * 100)}%</b> 花在高峰时段
      （工作日 9:00–12:00、14:00–18:00，那段单价翻倍）。
      周报月报这类不急的活儿挪到晚上或周末跑，能省一截。`);
  }
  if (isPeak) tips.push("现在<b>正在高峰时段</b>。");
  c.innerHTML = `
    ${tips.length ? `<div class="warn" style="font-weight:400;margin-bottom:10px">
      <b>省钱提示</b>（按你自己的用量算的）<br>${tips.join("<br>")}</div>` : ""}
    <p class="mini" style="margin-top:0">留空就用程序里自带的那份（推荐）。</p>` + `
    <p class="mini" style="margin-top:0">留空就用程序里自带的那份（推荐）。
      改之前先想清楚：这些字会**原样**发给 DeepSeek，别把私人的东西写进去。</p>
    ${PROMPT_DEFS.map(([k, name, tip]) => `
      <div class="f" style="margin-top:12px">
        <label>${name} <span class="mini">${tip}</span></label>
        <textarea data-prompt="${k}" rows="3"
          placeholder="留空 = 用自带的">${esc(cfg(k, ""))}</textarea>
      </div>`).join("")}
    <div style="margin-top:12px;display:flex;gap:10px;align-items:center">
      <button class="btn sm" id="prompt-save">保存这四段</button>
      <button class="btn ghost sm" id="prompt-reset">全部恢复默认</button>
      <span class="mini" id="prompt-hint"></span>
    </div>`;
  const save = async (patch, msg) => {
    const r = await saveCfg(patch, msg);
    void r;
  };
  const sv = $("#prompt-save");
  if (sv) sv.onclick = () => {
    const p = {};
    $$("[data-prompt]").forEach(x => { p[x.dataset.prompt] = x.value.trim(); });
    save(p, "提示词已保存");
  };
  const rs = $("#prompt-reset");
  if (rs) rs.onclick = () => {
    if (!confirm("四段提示词全部恢复成程序自带的那份？")) return;
    $$("[data-prompt]").forEach(x => { x.value = ""; });
    save({prompt_daily: "", prompt_weekly: "", prompt_monthly: "", prompt_memory: ""},
         "已恢复默认");
  };
}

const MEM_DEFS = [
  ["mem_search_limit", "一次搜索最多返回几条", 3, 60],
  ["mem_snippet_chars", "每条搜索结果给多少字", 120, 2000],
  ["mem_read_chars", "单篇日记最多读多少字", 500, 30000],
  ["mem_total_chars", "一轮里所有材料加起来的上限", 4000, 200000],
  ["mem_max_turns", "一轮问答最多翻几次记录", 1, 20],
];

function renderMemCard() {
  const c = $("#mem-card");
  if (!c) return;
  c.innerHTML = `
    <p class="mini" style="margin-top:0">回忆书每次回答，AI 会自己去翻你的日记和数字。
      这几个是「翻多用力」的上限 —— 调小更快更省 token，调大能看到更多材料。
      拿不准就别动。</p>
    ${MEM_DEFS.map(([k, name, lo, hi]) => `
      <div class="gline2"><span>${name}</span>
        <span><input type="number" data-mem="${k}" value="${cfg(k, "")}"
          min="${lo}" max="${hi}" style="width:110px"> <span class="mini">${lo}~${hi}</span></span>
      </div>`).join("")}
    <div style="margin-top:12px;display:flex;gap:10px;align-items:center">
      <button class="btn sm" id="mem-save">保存</button>
      <span class="mini">这些是「上限」，不是「必须用满」</span>
    </div>`;
  const sv = $("#mem-save");
  if (sv) sv.onclick = () => {
    const p = {};
    $$("[data-mem]").forEach(x => {
      const n = Number(x.value);
      if (Number.isFinite(n) && n > 0) p[x.dataset.mem] = Math.round(n);
    });
    saveCfg(p, "检索参数已保存");
  };
}

function renderClockCard() {
  const c = $("#clock-card");
  if (!c) return;
  const wage = +cfg("clock_wage", 0) || 0;
  const hours = +cfg("clock_hours", 8) || 8;
  const per = wage > 0 && hours > 0 ? (wage / hours) : 0;
  c.innerHTML = `
    <p class="mini" style="margin-top:0">给它一个日薪和每天干几小时，它算给你时薪，
      并在总览页显示「今天已经赚了多少」。纯属自嘲用。</p>
    <div class="gline2"><span>日薪（元）</span>
      <input type="number" id="ck-wage" value="${wage}" min="0" step="10" style="width:130px"></div>
    <div class="gline2"><span>每天工作几小时</span>
      <input type="number" id="ck-hours" value="${hours}" min="0.5" max="24" step="0.5"
        style="width:130px"></div>
    <div class="gline2"><span>几点上班
      <span class="mini">不然早上打开会显示"已经赚了七小时"</span></span>
      <input type="time" id="ck-start" value="${esc(cfg("clock_start", "09:00"))}"
        style="width:130px"></div>
    <p class="mini" style="margin-top:8px">${per > 0
      ? `时薪 ¥${per.toFixed(2)} —— 今天每干一小时，就是这个数`
      : "不填日薪就不显示这块"}</p>
    ${per > 0 ? `<div class="gline2"><span>现在
      <span class="mini">累计工作 ${(CLOCK_TOTAL_MIN / 60).toFixed(1)} 小时${
        clockLevelOf(CLOCK_TOTAL_MIN).leftMin
          ? " · 再干 " + Math.ceil(clockLevelOf(CLOCK_TOTAL_MIN).leftMin / 60) + " 小时升级"
          : " · 已经到顶了"}</span></span>
      <b>Lv.${clockLevelOf(CLOCK_TOTAL_MIN).lv} ${clockLevelOf(CLOCK_TOTAL_MIN).name}</b></div>
    <div class="bar" style="height:4px;border-radius:2px;background:var(--soft2);overflow:hidden">
      <i style="display:block;height:100%;border-radius:2px;background:var(--blue);
        width:${(clockLevelOf(CLOCK_TOTAL_MIN).pct * 100).toFixed(1)}%"></i></div>` : ""}
    ${per > 0 ? `
    <div class="gline2"><span>桌面上放一个小的
      <span class="mini">${IS_SHELL ? "像个小组件一样浮在最上面，能拖" : "浏览器里开不了，得用桌面版"}</span></span>
      <button class="btn ghost sm" id="ck-widget"${IS_SHELL ? "" : " disabled"}>
        ${IS_SHELL ? "打开小时钟" : "只有桌面版能用"}</button></div>` : ""}
    <div style="margin-top:10px"><button class="btn sm" id="ck-save">保存</button></div>`;
  const sv = $("#ck-save");
  if (sv) sv.onclick = () => {
    saveCfg({clock_wage: Math.max(0, +$("#ck-wage").value || 0),
             clock_hours: Math.max(0.5, +$("#ck-hours").value || 8),
             clock_start: $("#ck-start").value || "09:00"}, "已保存");
  };
  // 桌面小时钟（2.4.1）。⚠ 这是**开窗口**，不是个设置项 ——
  //   所以不存任何 state，点了就开、再点就关，状态由主进程说了算。
  const wb = $("#ck-widget");
  if (wb) wb.onclick = async () => {
    try {
      const on = await window.xrShell.clockToggle();
      toast(on === "on" ? "小时钟开好了，可以用鼠标拖着放" : "小时钟关掉了");
    } catch (e) { toast("打不开小时钟：" + e.message, true); }
  };
}

function renderMiscCard() {
  const c = $("#misc-card");
  if (!c) return;
  const hk = cfg("hotkey", "");
  const carry = !!cfg("budget_carry", false);
  const isShell = !!(window.xrShell && window.xrShell.isShell);
  c.innerHTML = `
    <div class="gline2"><span>全局快捷键
      <span class="mini">在别的程序里按一下，把这个窗口叫到面前</span></span>
      <span><input id="hk-in" value="${esc(hk)}" placeholder="CommandOrControl+Alt+X"
        style="width:230px" ${isShell ? "" : "disabled"}></span></div>
    <p class="mini" style="margin:4px 0 0 0">${isShell
      ? "填 <code>CommandOrControl+Alt+X</code> 这种写法；清空 = 不用。**改完要重启才生效**（键是开机时注册的）"
      : "浏览器版没有全局快捷键 —— 那是桌面壳才有的能力"}</p>
    <div class="gline2" style="margin-top:12px"><span>预算结转
      <span class="mini">上个月没花完的，加到下个月</span></span>
      <button class="segbtn${carry ? " on" : ""}" id="bc-tog">${carry ? "开" : "关"}</button></div>
    <p class="mini" style="margin:4px 0 0 0">只结转**正结余**：上个月超支了不倒扣下个月 ——
      那会让一次超支连着惩罚后面好几个月。关掉开关，看到的就还是你原本填的那个数。</p>
    <div style="margin-top:12px"><button class="btn sm" id="misc-save">保存</button></div>`;
  const sv = $("#misc-save");
  if (sv) sv.onclick = () => saveCfg({
    hotkey: ($("#hk-in") ? $("#hk-in").value.trim() : hk),
    budget_carry: !carry,
  }, "已保存（快捷键重启后生效）");
  const tg = $("#bc-tog");
  if (tg) tg.onclick = () => {
    // 单独点这一下也立即生效，不用再去点保存
    saveCfg({budget_carry: !carry}, !carry ? "预算结转已开" : "预算结转已关")
      .then(() => { BILL = null; });
  };
}

/* ---- 数据放哪儿 / 换目录（2.3.6）----
   ⚠ 换目录这件事**只有桌面版做得到**：新位置要写进 Electron 的启动配置，
     而且换完必须重启（Python 那边的 DATA_ROOT 是进程启动时定死的）。
     浏览器版就老老实实说做不到，不要给一个按下去没反应的按钮。 */

function renderWhereCard() {
  const card = $("#where-card");
  if (!card) return;
  const canMove = !!(window.xrShell && window.xrShell.pickFolder);
  card.innerHTML = `
    <div class="gline2"><span>现在放在</span>
      <span class="mini" style="word-break:break-all">${esc(dataDir() || "（还不知道）")}</span></div>
    <div style="margin-top:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <button class="btn ghost sm" id="where-open">${ICON.folder} 打开这个文件夹</button>
      <button class="btn sm" id="where-move" ${canMove ? "" : "disabled"}>换个地方</button>
      <span class="mini">${canMove
        ? "换了会把数据库、配置、笔记、备份一起搬过去，然后自动重启"
        : "浏览器版换不了 —— 数据位置是启动时定的，得用桌面版"}</span>
    </div>`;
  const op = $("#where-open");
  if (op) op.onclick = () => openDirOrCopy(dataDir());
  const mv = $("#where-move");
  if (mv) mv.onclick = changeDataDir;
}

/** 换数据目录：选目录 → 看清要搬什么 → 复制校验 → 写配置 → 重启 */
async function changeDataDir() {
  if (!(window.xrShell && window.xrShell.pickFolder)) return;
  // 先问「是不是就用安装目录」——那是「数据跟着程序走」这个需求最常见的答案，
  // 让它一步到位，省得用户去资源管理器里翻 exe 在哪。
  let to = "";
  const inst = window.xrShell.installDir ? await window.xrShell.installDir() : "";
  if (inst) {
    to = confirm("数据放哪？\n\n【确定】= 放在安装目录（exe 旁边）\n" + inst +
                 "\n\n【取消】= 我自己选一个文件夹") ? inst
      : await window.xrShell.pickFolder();
  } else {
    to = await window.xrShell.pickFolder();
  }
  if (!to) return;                                   // 用户取消了
  busy();
  const r = await post("/api/data/inspect", {to});
  idle();
  if (!r.ok) { toast(r.msg, true); return; }
  const d = r.data;
  const mb = n => n > 1048576 ? (n / 1048576).toFixed(1) + " MB"
                              : Math.max(1, Math.round(n / 1024)) + " KB";
  const lines = d.items.map(i =>
    `· ${i.name}（${i.kind}${i.files > 1 ? "，" + i.files + " 个文件" : ""}）`).join("\n");
  if (!confirm(
      `把数据搬到这儿？\n\n${d.to}\n\n要搬的东西：\n${lines}\n\n一共 ${mb(d.total)}。\n\n` +
      `· 全程只读不删：先复制过去、逐项核对，核对过了才算数\n` +
      `· 核对通过后旧目录仍然保留，你确认没问题了再自己删`)) return;

  busy();
  const r2 = await post("/api/data/move", {to: d.to, purge: false});
  idle();
  if (!r2.ok) { toast(r2.msg, true); return; }
  // 写进 Electron 的启动配置并重启。不重启的话后端还在用旧目录 ——
  // 用户会看到「搬完了但东西还在老地方」，最让人困惑的一种结果。
  const err = await window.xrShell.setDataRoot(d.to);
  if (err) { toast("搬好了，但记住新位置时出错：" + err, true); return; }
  toast("搬好了，正在重启…");
  await new Promise(r => setTimeout(r, 900));   // 让 toast 露个脸再重启
  await window.xrShell.relaunch();
}

function renderExport() {
  const card = $("#exp-card");
  if (!card) return;
  card.innerHTML = `
    <p class="mini" style="font-size:13px;margin-bottom:10px">
      数据平时住在数据库里。想拿去打印、存档、或者自己再拉个透视表的时候，
      点这里生成三本 Excel —— <b>内容和这儿看到的完全一致</b>，
      汇总表的合计数是活公式，改了明细会跟着变。
    </p>
    <div style="display:flex;gap:10px;align-items:center">
      <button class="btn" id="exp-run">${ICON.save} 导出三本 Excel</button>
      <span class="mini" id="exp-hint">导出到「个人信息统计\\_导出\\」，文件名带日期</span>
    </div>
    ${EXPLAST ? `
    <table style="margin-top:12px"><thead><tr><th>表</th><th>文件</th><th></th></tr></thead>
      <tbody>${EXPLAST.files.map(f => `<tr>
        <td>${esc(f.name)}</td><td class="mini">${esc(f.path.split("\\\\").pop())}</td>
        <td class="mini">${esc(EXPLAST.dir)}</td></tr>`).join("")}</tbody></table>
    <div style="margin-top:10px;display:flex;gap:10px;align-items:center">
      <button class="btn ghost sm" id="exp-open">${ICON.folder} 打开所在文件夹</button>
      <span class="mini">${canOpenDir() ? "直接跳到那个目录" : "浏览器版打不开文件夹，会帮你把路径复制下来"}</span>
    </div>
    <p class="mini" style="margin-top:8px">
      同一天导两次会覆盖同一个文件（<b>不会碰任何原始数据</b>）。想留着就自己改个名。
    </p>` : ""}`;
  const btn = $("#exp-run");
  if (btn) btn.onclick = async () => {
    busy();
    const r = await post("/api/export/excel", {});
    idle();
    if (!r.ok) { toast(r.msg, true); return; }
    EXPLAST = r.data;
    toast("三本 Excel 已导出");
    renderExport();
  };
  // ⚠ 「打开所在文件夹」只有**导出过之后**才渲染出来（它整块包在 EXPLAST 的
  //   三元里）—— 绑定放在这个函数末尾，因为此刻 innerHTML 已经写好、元素在
  //   树上了；放到别处绑就会绑到一个还不存在的节点。
  const ob = $("#exp-open");
  if (ob) ob.onclick = () => openDirOrCopy(EXPLAST.dir);
}

/* ---- 回收站 ---- */
let RCLIST = null;
const RC_ICON = {"账单流水": "wallet", "周边尾款": "gift", "待办": "list", "日记": "book"};
async function loadRecycle() {
  const r = await get("/api/recycle/list");
  RCLIST = r.ok ? r.data : {items: [], keep: 0, days: 0};
  renderRecycle();
}
function renderRecycle() {
  const card = $("#rc-card");
  if (!card) return;
  const d = RCLIST || {items: [], keep: 0, days: 0};
  card.innerHTML = `
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
      <button class="btn ghost sm" id="rc-refresh">刷新列表</button>
      ${d.items.length ? `<button class="btn warn sm" id="rc-clear">清空回收站</button>` : ""}
      <span class="mini">${d.items.length} 条 · 最多留 ${d.keep} 条 / ${d.days} 天</span>
    </div>
    ${d.items.length ? `<table><thead><tr><th>删除时间</th><th>类型</th>
      <th>内容</th><th></th><th></th></tr></thead><tbody>
      ${d.items.map(it => `<tr>
        <td class="mini">${esc(it.time)}</td>
        <td>${ICON[RC_ICON[it.kind_cn]] || ""} ${esc(it.kind_cn)}</td>
        <td>${esc(it.label)}</td>
        <td><button class="btn sm" data-rc-back="${esc(it.file)}">恢复</button></td>
        <td><button class="btn ghost sm" data-rc-kill="${esc(it.file)}">彻底删除</button></td>
      </tr>`).join("")}</tbody></table>`
      : emptyBox("回收站是空的", "删掉流水、尾款、待办或日记时，会先放一份到这里")}
    <p class="mini" style="margin-top:10px">
      恢复流水和尾款时，<b>行号会变</b>（补到当前最后一行），金额日期类别都不变。<br>
      日记如果已经重新写过了，恢复会被拒绝 —— 不会覆盖你后来写的。
    </p>`;
  const rb = $("#rc-refresh");
  if (rb) rb.onclick = () => loadRecycle();
  const cb = $("#rc-clear");
  if (cb) cb.onclick = async () => {
    if (!confirm("清空回收站？清空后就真的找不回来了。")) return;
    const r = await post("/api/recycle/clear", {});
    if (r.ok) { toast(r.msg); await loadRecycle(); } else toast(r.msg, true);
  };
  $$("#rc-card [data-rc-back]").forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = "恢复中…";
    const r = await post("/api/recycle/restore", {file: b.dataset.rcBack});
    if (!r.ok) { toast(r.msg, true); b.disabled = false; b.textContent = "恢复"; return; }
    toast(r.msg);
    BILL = null; STOCK = null; NOTES = null;      // 让相关页重新拉
    await loadRecycle();
  });
  $$("#rc-card [data-rc-kill]").forEach(b => b.onclick = async () => {
    if (!confirm("彻底删除这一条？之后就找不回来了。")) return;
    const r = await post("/api/recycle/purge", {file: b.dataset.rcKill});
    if (r.ok) { toast(r.msg); await loadRecycle(); } else toast(r.msg, true);
  });
}

/* ---- 类别管理（在草稿上编辑，点保存才落库并迁移历史）---- */
let CATDRAFT = null;      // {exp:[], inc:[], renames:{旧名:新名|null}}
function catDraftInit() {
  if (!BILL || !BILL.cats) { CATDRAFT = null; return; }
  CATDRAFT = {exp: [...BILL.cats.exp], inc: [...BILL.cats.inc], renames: {}};
}
function catManagerCard() {
  if (!CATDRAFT) return '<p class="mini">账单数据还没加载好，稍后再来</p>';
  const group = (kind, title, list) => `
    <div style="margin-bottom:14px">
      <div class="dsec-h" style="margin-bottom:6px">${title}
        <span class="mini">共 ${list.length} 个</span></div>
      ${list.map((name, i) => `
        <div class="gline2">
          <span><span class="dot" style="background:${colorOf(name)}"></span>${esc(name)}${
            CATDRAFT.renames[name] ? ` <span class="badge tagw">改为「${esc(CATDRAFT.renames[name])}」</span>` : ""}</span>
          <span style="white-space:nowrap">
            <button class="btn ghost sm" data-cat="mv:${kind}:${i}:-1" ${i===0?"disabled":""}>↑</button>
            <button class="btn ghost sm" data-cat="mv:${kind}:${i}:1" ${i===list.length-1?"disabled":""}>↓</button>
            <button class="btn ghost sm" data-cat="rn:${kind}:${i}">改名</button>
            <button class="btn warn sm" data-cat="del:${kind}:${i}">删</button>
          </span>
        </div>`).join("")}
      <div style="margin-top:8px">
        <button class="btn ghost sm" data-cat="add:${kind}">＋ 新增${title.replace("类别","")}类别</button>
      </div>
    </div>`;
  return `${group("exp", "支出类别", CATDRAFT.exp)}
    ${group("inc", "收入类别", CATDRAFT.inc)}
    <div class="warn" style="font-weight:400">
      改动保存后立即生效，按学期分开管。
      <b>改名或删除会把历史记录一起迁移</b>，删掉的归入「其他」/「其他收入」。
      保存前会自动备份。
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <button class="btn" id="cat-save">保存类别</button>
      <button class="btn ghost" id="cat-reset">放弃改动</button>
      <span class="mini" id="cat-hint"></span>
    </div>`;
}
/* 资金 / 账户类型管理。
   ⚠ 跟「账单类别」不是一回事，别照抄那套：
     类别改动要**迁移历史记录**（删掉的归入「其他」），所以得走
     草稿 + 保存 + 备份那一整套，不能改一下就存一下。
     资金类型只是个**设置数组**，改完立刻存就行，不碰任何数据。
   ⚠ 但删掉一个类型时，**它名下的历史记录不会消失** ——
     服务端列账户时会带上「数据里真正出现过的」那些（见 _account_list）。*/
function paysCard() {
  const list = pays();
  return `
    ${list.map((n, i) => `
      <div class="gline2">
        <span>${esc(n)}</span>
        <span style="white-space:nowrap">
          <button class="btn ghost sm" data-pay="mv:${i}:-1" ${i===0?"disabled":""}>↑</button>
          <button class="btn ghost sm" data-pay="mv:${i}:1" ${i===list.length-1?"disabled":""}>↓</button>
          <button class="btn warn sm" data-pay="del:${i}"
            ${list.length<=1?"disabled title='至少留一个'":""}>删</button>
        </span>
      </div>`).join("")}
    <div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <input id="pay-new" placeholder="新类型名，比如「校园卡」" style="min-width:180px">
      <button class="btn ghost sm" id="pay-add">＋ 添加</button>
      <span class="mini">排在前面的会作为记账时的默认选中项</span>
    </div>`;
}
function bindPays() {
  const card = $("#pays-card");
  if (!card) return;
  card.innerHTML = paysCard();
  const save = v => saveCfg({pays: v}, "资金类型已更新");
  $$("[data-pay]", card).forEach(btn => btn.onclick = () => {
    const [act, i, d] = btn.dataset.pay.split(":");
    const list = [...pays()];
    if (act === "mv") {
      const j = +i + +d;
      if (j < 0 || j >= list.length) return;
      [list[i], list[j]] = [list[j], list[i]];
      save(list);
    } else if (act === "del") {
      const n = list[+i];
      if (list.length <= 1) return toast("至少留一个", true);
      if (!confirm(`删掉资金类型「${n}」？

已经用它的那些记录**不受影响**，` +
                   `账户结余里照样看得到 —— 只是以后记账时选不到了。`)) return;
      list.splice(+i, 1);
      save(list);
    }
  });
  const add = () => {
    const el = $("#pay-new");
    const v = (el.value || "").trim();
    if (!v) return toast("先写个名字", true);
    if (v.includes(",") || v.includes("，")) return toast("名字里不能带逗号", true);
    const list = [...pays()];
    if (list.includes(v)) return toast("已经有这个类型了", true);
    list.push(v);
    save(list);
  };
  const ok = $("#pay-add");
  if (ok) ok.onclick = add;
  const inp = $("#pay-new");
  if (inp) inp.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); add(); } };
}

function bindCatManager() {
  const card = $("#cat-card");
  if (!card) return;
  card.innerHTML = catManagerCard();
  $$("[data-cat]", card).forEach(btn => btn.onclick = async () => {
    const [act, kind, i, d] = btn.dataset.cat.split(":");
    const list = kind === "exp" ? CATDRAFT.exp : CATDRAFT.inc;
    if (act === "mv") {
      const j = +i + +d;
      if (j < 0 || j >= list.length) return;
      [list[i], list[j]] = [list[j], list[i]];
    } else if (act === "rn") {
      const old = list[+i];
      // ⚠ 这里原本是 prompt() —— Electron 16+ 已移除，打包版点了没反应。改 askText。
      const v = await askText({
        title: "改类别名", label: "新名字", value: CATDRAFT.renames[old] || old, ph: old,
        hint: "改完只影响显示和历史归类，不会动已经记好的流水。"});
      if (v === null) return;
      const nv = v.trim();
      if (!nv || nv === old) { delete CATDRAFT.renames[old]; }
      else if (nv.includes(",") || nv.includes("，")) { toast("类别名不能带逗号", true); return; }
      else { CATDRAFT.renames[old] = nv; list[+i] = nv; }
    } else if (act === "del") {
      const old = list[+i];
      if (old === "其他" || old === "其他收入") { toast(`「${old}」是兜底类别，不能删`, true); return; }
      if (old === "理财" && kind === "exp") { toast("提示：收入侧也有「理财」，删的是支出侧这个", true); }
      if (!confirm(`删除「${old}」？\n它名下的历史记录会全部归入「其他」。`)) return;
      list.splice(+i, 1);
      CATDRAFT.renames[old] = null;
    } else if (act === "add") {
      // ⚠ 原本 prompt()（Electron 16+ 已移除）。改 askText。
      const v = await askText({
        title: `新增一个${kind === "exp" ? "支出" : "收入"}类别`,
        label: "类别名", ph: kind === "exp" ? "比如：打印" : "比如：奖学金",
        hint: "名字里不能带逗号。只属于当前学期，换学期可以照搬。"});
      if (v === null) return;
      const nv = v.trim();
      if (!nv) return;
      if (nv.includes(",") || nv.includes("，")) { toast("类别名不能带逗号", true); return; }
      if (list.includes(nv)) { toast("已经有这个类别了", true); return; }
      // 「其他」永远保持最后
      const tail = list[list.length - 1];
      if (tail === "其他" || tail === "其他收入") list.splice(list.length - 1, 0, nv);
      else list.push(nv);
    }
    bindCatManager();
  });
  const sv = $("#cat-save");
  if (sv) sv.onclick = async () => {
    busy();
    $("#cat-hint").textContent = "正在保存类别并迁移历史记录…";
    const r = await post("/api/bill/cats/save", {exp: CATDRAFT.exp, inc: CATDRAFT.inc,
                                                 renames: CATDRAFT.renames});
    if (!r.ok) { $("#cat-hint").textContent = ""; toast(r.msg, true); return; }
    toast(r.msg);
    BILL = null;
    await loadBill();
    catDraftInit();
    await loadSettings();
  };
  const rs = $("#cat-reset");
  if (rs) rs.onclick = () => { catDraftInit(); bindCatManager(); toast("已放弃改动"); };
}
async function saveSettings() {
  busy();
  const memSel = $("#ai-mem-model");
  const visSel = $("#ai-vis-model");
  const body = {api_key: $("#ai-key").value.trim(), model: $("#ai-model").value,
                base_url: $("#ai-base").value.trim(),
                memory_model: memSel ? memSel.value : "",
                vision_model: visSel ? visSel.value : ""};
  const r = await post("/api/ai/config/save", body);
  if (r.ok) { toast(r.msg); await loadSettings(); } else toast(r.msg, true);
}
async function testAI() {
  busy();
  const r = await post("/api/ai/test", {api_key: $("#ai-key").value.trim()});
  toast(r.msg, !r.ok);
  if (r.ok) idle();
}
/* 药品 AI 弹窗：先生成 → 预览可改 → 确认才保存 */
function drugAIModal(row) {
  const fields = [["K","针对疾病","disease"],["L","使用方法","usage"],
                  ["M","大致功效","effect"],["N","副作用与注意","side_effect"]];
  const body = `
    <div class="warn" style="font-weight:400">⚠ AI 生成内容仅供参考，<b>不能替代说明书或医嘱</b>，请核对后再保存。</div>
    <p class="mini">药品：<b>${esc(row.A||"")}</b>${row.J?`　备注：${esc(row.J)}`:""}</p>
    <div id="ai-gen-fields">
      ${fields.map(([col,label,k]) => `<div class="f" style="margin-bottom:8px;display:block">
        <label>${label}</label>
        <input id="ai-f-${k}" value="${esc(row[col]||"")}" style="width:100%"></div>`).join("")}
    </div>
    <div class="modal-actions" style="justify-content:flex-start;margin-top:6px">
      <button class="btn ghost" id="ai-do">${ICON.robot} 生成</button>
      <span class="mini" id="ai-hint">先点「生成」，确认无误后再保存</span>
    </div>`;
  $("#modalCard").innerHTML = `<h3>AI 补充药品信息（第 ${row.row} 行）</h3>${body}
    <div class="modal-actions"><button class="btn ghost" id="m-cancel">取消</button>
    <button class="btn" id="m-ok">保存</button></div>`;
  $("#modal").hidden = false;
  $("#modal").onclick = e => { if (e.target === $("#modal")) $("#modal").hidden = true; };
  $("#m-cancel").onclick = () => $("#modal").hidden = true;
  $("#ai-do").onclick = async () => {
    const btn = $("#ai-do");
    btn.disabled = true;
    $("#ai-hint").textContent = "生成中…（首次可能要几秒）";
    const r = await post("/api/ai/drug", {name: row.A, note: row.J || ""});
    btn.disabled = false;
    if (!r.ok) { $("#ai-hint").textContent = r.msg; toast(r.msg, true); return; }
    fields.forEach(([, , k]) => { $("#ai-f-" + k).value = (r.data || {})[k] || ""; });
    $("#ai-hint").textContent = "已生成，请核对/修改后点「保存」";
    toast(r.msg);
  };
  $("#m-ok").onclick = async () => {
    const pairs = fields.map(([col, , k]) => [col, $("#ai-f-" + k).value.trim()]);
    busy();
    for (const [col, val] of pairs) {
      const r = await post("/api/stock/set", {sheet: "药品", row: row.row, col, value: val});
      if (!r.ok) { toast(r.msg, true); return; }
    }
    toast("已保存到那四列");
    $("#modal").hidden = true;
    STOCK = null;
    await loadStock();
  };
}

/* ================================================================
   ⑥ 输入补全：本地历史优先（即时免费）+ 没命中时 AI 兜底
   用 document 级事件委托 + 一个全局 datalist，所有输入框共用一套，
   新增输入点只要加 data-sug="键名" 即可。
================================================================ */
const SUG_KIND = {"药品": "drug", "日用品": "daily", "零食": "snack"};
const _sugTimers = {};

function sugPool(kind) {
  const uniq = a => [...new Set(a.filter(Boolean).map(s => String(s).trim()).filter(Boolean))];
  try {
    if (kind === "drug" || kind === "daily" || kind === "snack") {
      const name = {"drug":"药品","daily":"日用品","snack":"零食"}[kind];
      return uniq(((STOCK && STOCK.sheets[name]) || {rows:[]}).rows.map(r => r.A));
    }
    if (kind === "todo")     return uniq(((STOCK && STOCK.todo) || []).map(t => t.item));
    if (kind === "billnote") return uniq(((BILL && BILL.records) || []).map(r => r.note));
    if (kind === "tailname") return uniq(((BILL && BILL.tails) || []).map(t => t.name));
  } catch (e) { /* 数据还没加载好就算了，补全不该影响主流程 */ }
  return [];
}
function sugFillOptions(list) {
  const dl = $("#dl-sug");
  if (dl) dl.innerHTML = list.slice(0, 60).map(s => `<option value="${esc(s)}"></option>`).join("");
}
function sugMatch(el) {
  const kind = el.dataset.sug;
  if (!kind) return 0;
  const q = (el.value || "").trim().toLowerCase();
  let pool = sugPool(kind);
  if (q) pool = pool.filter(s => s.toLowerCase().includes(q) && s.toLowerCase() !== q);
  sugFillOptions(pool);
  el.setAttribute("list", "dl-sug");
  return pool.length;
}
/* AI 兜底补全。
   ⚠ 这里是**全应用最烧钱的一处**：实测 42 次调用花了 ¥0.36，占全部 AI 花费的
     **76%** —— 比回忆书、周报月报、总览分析加起来还多好几倍。
     原因不是「本地没匹配上才问」那条（那个是对的），而是**每敲一个字都问一次**：
     打「复方感冒灵」五个字就是 5 次调用，每次 1400 多 token，而五次问出来的
     候选几乎一模一样。
   所以加了三道闸（按省下来的钱排序）：
     ① 一个字不问 —— 「复」能猜出的东西没有参考价值，纯浪费
     ② **一次输入只问一次** —— 问过之后就把这一串记下来，后面的延伸不再问。
        用户改主意删掉重打（长度回到比问过的还短）才算新的一轮
     ③ 问过的词进缓存，同一个词永远不问第二遍                                */
const _sugAsked = new Set();      // 已经问过 AI 的前缀
let   _sugCache = {};             // 前缀 → 候选（换页也不清，进程内有效）

function sugAI(el, kind) {
  const q = (el.value || "").trim();
  if (q.length < 2) return;                       // ① 一个字不问
  const key = kind + "\0" + q;
  if (_sugAsked.has(key)) return;                 // ② 这一串已经问过了
  clearTimeout(_sugTimers[kind]);
  _sugTimers[kind] = setTimeout(async () => {
    if ((el.value || "").trim() !== q || document.activeElement !== el) return;
    // 用户在这 600ms 里又打了字 —— 那就等下一次，别把这一串也问出去
    _sugAsked.add(key);
    let names = _sugCache[key];
    if (!names) {
      const r = await post("/api/ai/suggest", {kind, text: q});
      if (!r.ok || !r.data || !r.data.names || !r.data.names.length) return;
      names = r.data.names;
      _sugCache[key] = names;
      if (Object.keys(_sugCache).length > 400) _sugCache = {};   // 别无限涨
      toast("AI 猜了几个：" + names.slice(0, 3).join("、"));
    }
    if (document.activeElement !== el) return;
    sugFillOptions(names.concat(sugPool(kind)));
    el.setAttribute("list", "dl-sug");
  }, 900);                                        // 防抖从 600 提到 900：多等 0.3 秒，少问好几次
}
/** 用户把这个框清空了 → 当成新的一轮，之前问过的允许再问 */
function sugReset(el) {
  if (!el || !el.dataset || !el.dataset.sug) return;
  const k = el.dataset.sug;
  [..._sugAsked].forEach(x => { if (x.startsWith(k + "\0")) _sugAsked.delete(x); });
}
function initSuggest() {
  document.addEventListener("focusin", e => {
    const el = e.target;
    if (el && el.dataset && el.dataset.sug) sugMatch(el);
  });
  document.addEventListener("input", e => {
    const el = e.target;
    if (!el || !el.dataset || !el.dataset.sug) return;
    if (el.dataset.sugBusy === "1") return;
    if (!(el.value || "").trim()) sugReset(el);  // 清空了 = 新的一轮
    const n = sugMatch(el);
    if (n === 0) sugAI(el, el.dataset.sug);     // 本地一条都没匹配上 → 让 AI 猜
  });
}

/* ================================================================
   ⑦ 学期切换
================================================================ */
let SEMS = null;
/** 只把学期数据取回来（SEMS）。**不碰任何 DOM** ——
 *  所以账单页也能安全地调它，不像 loadSemesters() 那样依赖 #semPick 已经存在。 */
async function fetchSemesters() {
  const r = await get("/api/semesters");
  if (r.ok) SEMS = r.data;
}
async function loadSemesters() {
  await fetchSemesters();
  if (!SEMS) return;
  const sel = $("#semPick");
  if (!sel) return;
  sel.innerHTML = SEMS.semesters.map(s =>
    `<option value="${esc(s.name)}" ${s.active ? "selected" : ""}>${ICON.book2} ${esc(s.name)}${
      s.records >= 0 ? `（${s.records} 条）` : ""}</option>`).join("");
  sel.onchange = async () => {
    const name = sel.value;
    if (!confirm(`切换到「${name}」？\n\n只切换当前查看的学期，不会改动任何数据文件。`)) {
      sel.value = SEMS.current;
      return;
    }
    busy();
    const rr = await post("/api/semester/switch", {name});
    if (!rr.ok) { toast(rr.msg, true); sel.value = SEMS.current; return; }
    toast(rr.msg);
    BILL = null; CHECK = null; STOCK = null; AIANALYSIS = null;
    await loadSemesters();
    await loadOverview();
  };
}
function semesterCard() {
  const s = SEMS;
  if (!s) return '<p class="mini">加载中…</p>';
  return `
    <p class="mini" style="margin-bottom:10px">
      一个学期一份账，数据按学期分开存。切换只是换「现在看哪一份」，
      不动任何数据。当前：<b>${esc(s.current)}</b>
    </p>
    <table><thead><tr><th>学期</th><th class="num">记录</th><th></th></tr></thead><tbody>
      ${s.semesters.map(x => `<tr class="${x.active ? "total" : ""}">
        <td>${esc(x.name)}${x.active ? ' <span class="badge tagg">当前</span>' : ""}</td>
        <td class="num">${x.records >= 0 ? x.records : "?"}</td>
        <td>${x.active ? "" : `<button class="btn ghost sm" data-sem-go="${esc(x.name)}">切换</button>`}</td>
      </tr>`).join("")}
    </tbody></table>
    <div style="margin-top:12px">
      <button class="btn" id="sem-new">＋ 新建学期</button>
      <span class="mini">清空流水和尾款，但把<b>类别</b>照搬过去，开学不用从零配</span>
    </div>`;
}
function bindSemesterCard() {
  const card = $("#sem-card");
  if (!card) return;
  card.innerHTML = semesterCard();
  $$("#sem-card [data-sem-go]").forEach(btn => btn.onclick = async () => {
    const name = btn.dataset.semGo;
    busy();
    const r = await post("/api/semester/switch", {name});
    if (!r.ok) { toast(r.msg, true); return; }
    toast(r.msg);
    BILL = null; CHECK = null; STOCK = null; AIANALYSIS = null;
    await loadSemesters();
    await loadSettings();
  });
  const nb = $("#sem-new");
  if (nb) nb.onclick = async () => {
    // ⚠ 原本 prompt()（Electron 16+ 已移除 → 打包版点了没反应）。改 askText。
    const name = await askText({
      title: "新建学期", label: "学期名", ph: "大二下",
      hint: "会清空流水和尾款，但把**类别**照搬过去，开学不用从零配。"});
    if (name === null || !name.trim()) return;
    busy();
    const r = await post("/api/semester/create", {name: name.trim()});
    if (!r.ok) { toast(r.msg, true); return; }
    toast(r.msg);
    await loadSemesters();
    await loadSettings();
  };
}

/* ================================================================
   ⑥ 日记（日报 / 周报 / 月报）
   存储是 Markdown 文件，不进数据库 —— 日记是长文本，塞进表里既不好查
   也不好改；存成 .md 还有个好处：记事本、VS Code 都能直接打开改。
================================================================ */
let NOTES = null;              // {daily:[], weekly:[], monthly:[], pending:{}}
let noteKind = "daily";
let noteCur = null;            // {name, content} 当前打开的那篇
// 默认「纯编辑」。
// 以前默认分栏，一半写一半预览 —— 手机/窄窗口下两栏都挤得没法看，
// 而且左边那栏还因为背景写死成浅色、深色模式下变成白底白字（已修）。
// 写日记本来 95% 的时间就是在写，要看效果点一下「预览」就行。
let noteMode = "edit";         // edit | split | view
let noteSaveTimer = null;
let notePollTimer = null;

/* ---------- 极简 Markdown 渲染 ----------
   先整体转义再解析：这样代码块里的 < > 天然是安全的，
   也不用担心笔记内容里的尖括号被当成标签。 */
/* 链接协议白名单。⚠ `esc()` 挡不住这个：`javascript:alert(1)` 里
 * 一个需要转义的字符都没有，转完还是原样，于是
 * `[点我](javascript:...)` 会生成一个**可点的可执行锚点**。
 * 笔记是 Markdown 文件、能手工编辑也能导入，所以这不该靠「只有我自己写」兜底。
 * 不通过就退成纯文本 —— 宁可链接不可点，也不能让它可执行。 */
const SAFE_URL = /^(https?:|mailto:|tel:|#|\/|\.\/|\.\.\/)/i;
function safeUrl(u) {
  const raw = String(u || "").trim();
  // 浏览器会忽略 URL 里的控制字符和零宽字符，所以剥掉之后才能判
  const t = raw.replace(/[\u0000-\u001F\u007F\u200B-\u200D\uFEFF]/g, "");
  return SAFE_URL.test(t) ? raw : null;
}
function mdLink(text, href) {
  const u = safeUrl(href);
  return u ? `<a href="${u}" target="_blank" rel="noopener">${text}</a>` : text;
}
function mdInline(s) {
  return s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    // ⚠ 正文里写的是「附件/xxx.jpg」—— 那是**跟笔记文件放一起**的相对路径，
    //   而页面是拿 /static/ 当根的。不重写的话浏览器会去要
    //   /static/附件/xxx.jpg，404，图裂。
    .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, src) => {
      // ⚠ 先认「附件/」—— 它不在 SAFE_URL 的名单里（没斜杠开头、也不是 ./），
      //   走 safeUrl 会被判成不可信，把正常插图全退成文字。这是自己踩的坑。
      const u = /^附件\//.test(src) ? "/attach/" + src.slice(3) : safeUrl(src);
      if (!u) return alt;                       // 图片地址不可信 → 只留说明文字
      return `<img alt="${alt}" loading="lazy" src="${u}">`;
    })
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, text, href) => mdLink(text, href))
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*\w])\*([^*\n]+)\*/g, "$1<i>$2</i>")
    .replace(/~~([^~]+)~~/g, "<s>$1</s>");
}
function md(src) {
  // 结构判断必须用**原始行**：先整体转义的话 `>` 会变成 `&gt;`，
  // 引用块的正则再也匹配不上（转义只发生在输出那一刻）
  const lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
  const inline = s => mdInline(esc(s));
  const out = [];
  let i = 0, para = [];
  const flush = () => {
    if (para.length) { out.push("<p>" + para.map(inline).join("<br>") + "</p>"); para = []; }
  };
  while (i < lines.length) {
    const ln = lines[i], m = ln.match(/^(#{1,6})\s+(.*)$/);
    if (/^```/.test(ln)) {                                   // 代码块
      flush();
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      out.push("<pre><code>" + esc(buf.join("\n")) + "</code></pre>");
    } else if (!ln.trim()) {
      flush(); i++;
    } else if (m) {                                          // 标题
      flush();
      out.push("<h" + m[1].length + ">" + inline(m[2]) + "</h" + m[1].length + ">");
      i++;
    } else if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(ln)) {  // 分隔线
      flush(); out.push("<hr>"); i++;
    } else if (/^\s*>\s?/.test(ln)) {                         // 引用
      flush();
      const buf = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i]))
        buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push("<blockquote>" + buf.map(inline).join("<br>") + "</blockquote>");
    } else if (/^\s*[-*+]\s+/.test(ln)) {                     // 无序列表
      flush();
      const buf = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i]))
        buf.push(lines[i++].replace(/^\s*[-*+]\s+/, ""));
      out.push("<ul>" + buf.map(x => "<li>" + inline(x) + "</li>").join("") + "</ul>");
    } else if (/^\s*\d+[.)]\s+/.test(ln)) {                   // 有序列表
      flush();
      const buf = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i]))
        buf.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ""));
      out.push("<ol>" + buf.map(x => "<li>" + inline(x) + "</li>").join("") + "</ol>");
    } else if (/^\s*\|.*\|\s*$/.test(ln)) {                   // 表格
      flush();
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(lines[i++]);
      const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const isSep = r => /^[\s|:-]+$/.test(r) && r.includes("-");
      const head = cells(rows[0]);
      const body = rows.slice(rows[1] && isSep(rows[1]) ? 2 : 1);
      out.push("<table><thead><tr>" + head.map(c => "<th>" + inline(c) + "</th>").join("") +
        "</tr></thead><tbody>" + body.map(r =>
          "<tr>" + cells(r).map(c => "<td>" + inline(c) + "</td>").join("") + "</tr>").join("") +
        "</tbody></table>");
    } else {
      para.push(ln); i++;
    }
  }
  flush();
  return out.join("");
}

/* ---------- 总览页的「随手记」----------- */
function quickNoteCard() {
  return `<div class="quicknote">
    <textarea id="qn-text" rows="2" placeholder="随手记一句… 想到什么写什么，AI 会帮你整理进日报（Ctrl+Enter 提交）"></textarea>
    <button class="btn" id="qn-send">记下</button>
    <button class="btn ghost" id="qn-tpl" title="不知道写什么？照着模板填">${ICON.pencil} 用模板写</button>
    <!-- 补写（2.4.7）：默认是今天，改一下日期就往那天的日报里写。
         ⚠ 后端 /api/notes/quick 本来就收 date 参数（server.py 里那段
           【if body.get("date")】），只是前端一直没把它露出来 ——
           所以这个功能不需要动后端一个字。
         ⚠ 这段注释在**模板字符串**里，所以里面**绝不能出现反引号** ——
           会当场把模板串截断（这次就栽了，node --check 立刻报 Unexpected token）。 -->
    <label class="mini" style="display:flex;align-items:center;gap:6px;margin-left:auto"
      title="改这个日期，就往那一天的日报里写（补写以前漏掉的日记）">
      写进 <input type="date" id="qn-date" style="width:auto">
    </label>
  </div>`;
}

/* ================= 日记模板（2.3.6）=================

   用户的原话：「我不会写日记」。所以这里给的是**填空**，不是空白页 ——
   每一栏都有引导语，填完自动拼成一段有结构的 Markdown 贴进今天的日报。

   ⚠ 这些模板之间**没有代码差异**，只有数据不同。所以下面就是一个数组 +
   一个通用渲染器，不要给每个模板写一份界面 —— 加模板就是往数组里加一项。
   ⚠ 模板的排列顺序就是界面上的顺序，按「门槛从低到高」排：
   一句话 → 小确幸 → 321 → KPT → YWT → 三件好事 → 斯多葛 → STAR →
   结构化表达 → 五分钟 → Gibbs → CBT → PERMA → 晨间随笔 → 自由书写。 */
const DIARY_TPL = [
  { k: "one", g: "随手就能写", n: "一句话日记", t: "今天最想说的一句话",
    d: "实在不想写的时候，就写这一句", f: [{ l: "今天…", p: "今天最想说的一句话", r: 2 }] },

  { k: "small", g: "随手就能写", n: "今日小确幸", t: "今天有哪些微小但开心的事",
    d: "不用深刻，记那些让自己嘴角动了一下的瞬间", f: [
      { l: "今天的小确幸", p: "食堂多给了一块肉 / 路上看到一只猫 / 快递比预计早到", r: 4 }] },

  { k: "g321", g: "感恩 · 心态", n: "321 日记法", t: "三件感恩、两件改进、一件鼓励",
    d: "门槛最低的一套，三五分钟能写完", f: [
      { l: "今天值得感恩的三件事", p: "可以很小。感谢谁、感谢什么事", r: 3 },
      { l: "今天可以做得更好的两件事", p: "不是自责 —— 写「下次怎么做」就行", r: 2 },
      { l: "今天要鼓励自己的一件事", p: "哪怕只是「今天没崩」", r: 1 }] },

  { k: "good3", g: "感恩 · 心态", n: "三件好事 + 原因", t: "每件好事都多写一句为什么",
    d: "比 321 多一步：写原因。研究里这一步才是效果关键", f: [
      { l: "今天的三件好事", p: "发生了什么", r: 3 },
      { l: "它们为什么会发生", p: "跟自己有关的、能重复的原因 —— 这样下次还能再发生", r: 4 }] },

  { k: "kpt", g: "复盘 · 改进", n: "KPT 复盘", t: "Keep / Problem / Try",
    d: "日本 IT 圈最常用的每日复盘，不记流水账", f: [
      { l: "K · 哪些做得不错，要保持", p: "今天哪件事的方式是对的", r: 3 },
      { l: "P · 哪里出了问题", p: "只说事，不评价自己", r: 3 },
      { l: "T · 下次试什么", p: "一个具体的、下次就能做的动作", r: 3 }] },

  { k: "ywt", g: "复盘 · 改进", n: "YWT", t: "做了 / 懂了 / 接下来",
    d: "比 KPT 更轻，不强调「问题」，心理负担小", f: [
      { l: "做了（やった）", p: "今天实际做了什么", r: 3 },
      { l: "懂了（わかった）", p: "做完之后明白了什么", r: 3 },
      { l: "接下来（次やる）", p: "明天要做的", r: 3 }] },

  { k: "stoic", g: "复盘 · 改进", n: "斯多葛晚间三问", t: "睡前问自己三个问题",
    d: "塞涅卡那套。三句话就完，适合睡前躺床上想", f: [
      { l: "今天我哪里做错了", p: "不找借口", r: 3 },
      { l: "什么事我没有做", p: "该做却没做的", r: 3 },
      { l: "还有什么该做没做", p: "还欠着的、拖着的事", r: 3 }] },

  { k: "star", g: "表达 · 情绪", n: "STAR 法", t: "情境 · 任务 · 行动 · 结果",
    d: "讲一件事的通用结构，面试、汇报、跟人解释都能用", f: [
      { l: "S · 情境", p: "什么时候、在哪儿、周围是什么情况", r: 3 },
      { l: "T · 任务", p: "当时要解决的是什么", r: 2 },
      { l: "A · 行动", p: "你具体做了什么（一步一步）", r: 4 },
      { l: "R · 结果", p: "最后怎么样，有数就写上数", r: 3 }] },

  { k: "strict", g: "表达 · 情绪", n: "结构化表达", t: "结果 → 原因 → 影响 → 场景 → 观点 → 即兴",
    d: "练「把一件事说清楚」。六步走完，表达就成形了", f: [
      { l: "1 结果", p: "先说结论：到底发生了什么", r: 2 },
      { l: "2 原因", p: "为什么会这样", r: 3 },
      { l: "3 影响", p: "这件事带来了什么（好或坏）", r: 3 },
      { l: "4 场景", p: "把当时的样子具体描述出来 —— 谁在哪、说了什么、什么表情", r: 5 },
      { l: "5 观点", p: "你自己怎么看", r: 3 },
      { l: "6 即兴表达", p: "假设有人当面问你这件事，你会怎么开口？放开写，不用改", r: 5 }] },

  { k: "cbt", g: "表达 · 情绪", n: "CBT 情绪日记", t: "情绪上来的时候用",
    d: "认知行为疗法那套：把「自动冒出来的想法」写下来，再去检验它", f: [
      { l: "情境", p: "发生了什么", r: 3 },
      { l: "当时的自动想法", p: "脑子里第一时间冒出来的那句话，别修饰", r: 3 },
      { l: "情绪 + 强度（0-100）", p: "难过 80 / 生气 60 / 焦虑 70", r: 2 },
      { l: "支持这个想法的证据", p: "客观事实，不是感觉", r: 3 },
      { l: "反对这个想法的证据", p: "同样要是事实", r: 3 },
      { l: "换个说法", p: "把第一句自动想法改写成一个更站得住的说法", r: 4 }] },

  { k: "perma", g: "表达 · 情绪", n: "PERMA 五要素", t: "五个角度各写一句",
    d: "积极心理学。更适合每周/每月回顾，不适合天天写", f: [
      { l: "P 积极情绪", p: "今天有哪些让我感觉好的时刻", r: 2 },
      { l: "E 投入", p: "什么时候我完全投入、忘了时间", r: 2 },
      { l: "R 关系", p: "今天跟谁有真实的连接", r: 2 },
      { l: "M 意义", p: "今天做的哪件事，我觉得值得", r: 2 },
      { l: "A 成就", p: "今天我完成了什么（多小都算）", r: 2 }] },

  { k: "m5", g: "成套的方法", n: "五分钟日记", t: "早上三问 + 晚上三问",
    d: "《The 5-Minute Journal》，卖得最好的一本日记书。早上填一次、晚上再填一次", f: [
      { l: "早上：今天期待的三件事", p: "今天有什么值得期待的", r: 3 },
      { l: "早上：今天想成为怎样的人", p: "耐心的人 / 专注的人 / 主动的人", r: 2 },
      { l: "早上：今天最重要的三件事", p: "只写三件，别贪", r: 3 },
      { l: "晚上：今天的三件好事", p: "发生了什么好事", r: 3 },
      { l: "晚上：今天学到了什么", p: "一句话也行", r: 2 },
      { l: "晚上：今天最好的一刻", p: "哪一个瞬间最想留住", r: 2 }] },

  { k: "gibbs", g: "成套的方法", n: "Gibbs 反思循环", t: "复盘一件事的六步",
    d: "学术圈做反思的标准框架。适合复盘**某一件事**，不用天天写", f: [
      { l: "1 描述", p: "发生了什么", r: 3 },
      { l: "2 感受", p: "当时你的感觉是什么", r: 3 },
      { l: "3 评价", p: "哪里做得好、哪里不好", r: 3 },
      { l: "4 分析", p: "为什么好、为什么不好 —— 试着解释，不是重复描述", r: 4 },
      { l: "5 结论", p: "从这件事里学到什么", r: 3 },
      { l: "6 行动计划", p: "如果再来一次，你会怎么做", r: 3 }] },

  { k: "pages", g: "自由书写", n: "晨间三页", t: "写满三页，不评判、不停笔",
    d: "Julia Cameron 那套。写完不用回看，练的是「不停下来删改」", f: [
      { l: "随手写（不用分段、不用改）", p: "想到哪写到哪。卡住了就写「我不知道写什么」接着写", r: 12 }] },

  { k: "free", g: "自由书写", n: "自由书写", t: "不限主题，不限长度",
    d: "想写什么写什么，最后贴进今天的日报", f: [
      { l: "今天想写的", p: "随便写", r: 12 }] },
];

/* 日记模板的填写界面。
   ⚠ 我第一版凭空假设了个 `modal(title, html, {wide, onMount})` 的接口 ——
     仓库里**没有**这个签名（只有 `modal(title, html, onOk, icon)`，而且
     底部是固定的「取消 / 保存」两个钮）。所以改成**一屏搞定**：
     上面一个下拉选模板，下面直接出那一套的填写框。少一层跳转，代码也短。 */
function openDiaryTpl() {
  const groups = [];
  DIARY_TPL.forEach(x => {
    let g = groups.find(y => y.n === x.g);
    if (!g) { g = { n: x.g, items: [] }; groups.push(g); }
    g.items.push(x);
  });
  const first = DIARY_TPL[0].k;
  const html = `
    <div class="f" style="margin-top:2px">
      <label>用哪一套</label>
      <select id="tpl-sel">
        ${groups.map(g => `<optgroup label="${esc(g.n)}">${
          g.items.map(x => `<option value="${x.k}">${esc(x.n)} — ${esc(x.t)}</option>`)
        }</optgroup>`).join("")}
      </select>
    </div>
    <p class="mini" id="tpl-desc" style="margin:2px 0 4px"></p>
    <div id="tpl-fields"></div>
    <p class="mini" style="margin-top:10px">填几栏都行，空着的不会被写进去。
      写完贴进<b>今天的日报</b>，回忆书和周报月报都能检索到。</p>`;

  modal("写日记", html, async () => {
    const t = DIARY_TPL.find(x => x.k === $("#tpl-sel").value);
    const parts = [`### ${t.n}`, `_${t.t}_`];
    let filled = 0;
    t.f.forEach((f, i) => {
      const el = document.querySelector(`[data-tplf="${i}"]`);
      const v = el ? (el.value || "").trim() : "";
      if (!v) return;
      filled++;
      parts.push(`**${f.l}**\n\n${v}`);
    });
    if (!filled) { toast("一栏都没填", true); return false; }
    const r = await post("/api/notes/append", {text: parts.join("\n\n")});
    if (!r.ok) { toast(r.msg, true); return false; }
    toast("写进今天的日报了");
    NOTES = null;
    if (!$("#tab-note").hidden) loadNotes();
  }, "pencil");

  const paint = () => {
    const t = DIARY_TPL.find(x => x.k === $("#tpl-sel").value) || DIARY_TPL[0];
    $("#tpl-desc").textContent = t.d;
    $("#tpl-fields").innerHTML = t.f.map((f, i) => `
      <div class="f" style="margin-top:10px">
        <label>${esc(f.l)}</label>
        <textarea data-tplf="${i}" rows="${f.r || 3}"
          placeholder="${esc(f.p || "")}"></textarea>
      </div>`).join("");
    const m = $("#modalCard h3");
    if (m) m.textContent = t.n;
  };
  $("#tpl-sel").value = first;
  $("#tpl-sel").onchange = paint;
  paint();
}
function bindQuickNote() {
  const ta = $("#qn-text"), btn = $("#qn-send");
  if (!ta || !btn) return;
  const dp = $("#qn-date");
  // 默认写今天。每次重绑都重置 —— 补写完一天之后不该「一直写那一天」，
  // 那是很容易记错的事（下一条随手记会悄悄进到昨天的日报里）。
  if (dp) dp.value = todayStr();
  const send = async () => {
    const text = ta.value.trim();
    if (!text) return;
    const body = {text};
    // 只有和今天不同才带 date 发出去 —— 让「平常随手记」走原来那条路径，
    // 行为一个字不变（少一个可能出岔子的参数）。
    if (dp && dp.value && dp.value !== todayStr()) {
      // ⚠ 前端也拦一道未来日期。后端会认，但「写进明天的日报」不是用户想要的，
      //   而且他看不到任何提示。宁可这里就说清楚。
      if (dp.value > todayStr()) return toast("还不能写将来的日记", true);
      body.date = dp.value;
    }
    btn.disabled = true; btn.textContent = "整理中…";
    const r = await post("/api/notes/quick", body);
    btn.disabled = false; btn.textContent = "记下";
    if (!r.ok) return toast(r.msg, true);
    ta.value = "";
    if (dp) dp.value = todayStr();
    toast(r.msg);
    NOTES = null;
    if (!$("#tab-note").hidden) loadNotes();
  };
  btn.onclick = send;
  // 「用模板写」（2.3.6）。**跟随手记走同一条绑定路径** ——
  // 别另开一处去绑，不然又是一份「谁忘了谁就点不动」的清单。
  const tpl = $("#qn-tpl");
  if (tpl) tpl.onclick = () => openDiaryTpl(dp ? dp.value : null);
  ta.onkeydown = e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); }
  };
}

/* ---------- 日记页 ---------- */
const NOTE_KIND_CN = {daily: "日报", weekly: "周报", monthly: "月报"};

async function loadNotes() {
  const [l, p] = await Promise.all([get("/api/notes/list"), get("/api/notes/pending")]);
  if (!l.ok) return toast("日记加载失败", true);
  NOTES = l.data;
  clearDirty("note"); syncStamp();
  NOTES.pending = p.ok ? p.data : {total: 0, job: {}};
  renderNotes();
  // 首次进来要自动打开最新一篇，否则右边只有一句「左边选一篇」的占位提示
  if (!noteCur && NOTES[noteKind] && NOTES[noteKind].length) {
    openNote(NOTES[noteKind][0].name);
  }
}

function noteBanner() {
  const p = NOTES.pending || {}, j = p.job || {};
  if (j.running) {
    return `<div class="nbanner run">⏳ 正在后台补 ${j.total} 篇报告（${j.done}/${j.total}）
      ${j.current ? "· 当前：" + esc(j.current) : ""}</div>`;
  }
  if (p.total) {
    return `<div class="nbanner">
      <span>${ICON.book2} 有 <b>${p.total}</b> 篇报告可以生成${
        p.weekly.length ? `（周报 ${p.weekly.length}）` : ""}${
        p.monthly.length ? `（月报 ${p.monthly.length}）` : ""}</span>
      <button class="btn sm" id="nb-genall">一键补齐</button></div>`;
  }
  if (j.finished && j.finished.length) {
    const bad = j.finished.filter(x => !x.ok);
    return `<div class="nbanner ok">${ICON.check} 已自动补齐 ${j.finished.length - bad.length} 篇报告${
      bad.length ? `，${bad.length} 篇失败` : ""}</div>`;
  }
  return "";
}

function renderNotes() {
  const list = (NOTES && NOTES[noteKind]) || [];
  const tabs = Object.keys(NOTE_KIND_CN).map(k =>
    `<button class="nkind${k === noteKind ? " on" : ""}" data-kind="${k}">${NOTE_KIND_CN[k]}
      <span class="mini">${((NOTES && NOTES[k]) || []).length}</span></button>`).join("");
  const items = list.length ? list.map(x => `
    <div class="nitem${noteCur && noteCur.name === x.name ? " on" : ""}" data-name="${x.name}">
      <div class="nname">${esc(x.display || x.name)}${x.empty ? ' <span class="mini">（还没写）</span>' : ""}</div>
      <div class="nsub">${esc(x.sub || "")}</div>
      <div class="nprev">${esc(x.preview || "—")}</div>
    </div>`).join("") : emptyBox("还没有${NOTE_KIND_CN[noteKind]}", "去总览随手记一句，或者在右边直接写")

  $("#tab-note").innerHTML = `
  <div id="nbanner">${noteBanner()}</div>
  <div class="nlayout">
    <div class="nside">
      <div class="nkinds">${tabs}</div>
      <div class="nlist">${items}</div>
    </div>
    <div class="nmain" id="nmain"></div>
  </div>`;
  renderNoteEditor();
  bindNotes();
}

// 编辑器内部那些控件的绑定。**每次重渲染后都要重新调** ——
// 切模式（编辑/预览/对照）会把 #nmain 整个换掉，不重绑按钮就是死的。
// （设置页也踩过同一个坑：重渲染了却没重绑。）
function bindNoteEditorCtl() {
  // 三个模式按钮：点哪个是哪个，不再是一个按钮循环切
  $$("[data-nmode]").forEach(b => b.onclick = () => {
    noteMode = b.dataset.nmode;
    saveNote(true);              // 切之前先把没存的内容落盘，别切丢了
    renderNoteEditor();
  });
  const sb = $("#n-save");
  if (sb) sb.onclick = () => saveNote();
  bindInsertImage("#n-img", "#n-edit");
  const eb = $("#n-exp");
  if (eb) eb.onclick = async () => {
    const CN = {daily: "日报", weekly: "周报", monthly: "月报"};
    // ⚠ 原本 prompt()（Electron 16+ 已移除 → 打包版点了没反应）。改 askText。
    const f = await askText({
      title: `把「${CN[noteKind] || noteKind}」导出成什么格式`,
      label: "格式", value: "1", ph: "1",
      hint: "1 = Word（能改、能发人）　2 = Markdown（原样留底）　3 = HTML（打开后 Ctrl+P 存成 PDF）"});
    if (f === null || !f.trim()) return;
    exportNotes(noteKind, f.trim() === "2" ? "md" : (f.trim() === "3" ? "html" : "doc"));
  };
  const rb = $("#n-regen");
  if (rb) rb.onclick = async () => {
    if (!confirm(`重新生成 ${noteCur.name} ${NOTE_KIND_CN[noteKind]}？\n\n会重新读取来源记录并覆盖当前内容。`)) return;
    rb.disabled = true; rb.textContent = "生成中…";
    const r = await post("/api/notes/generate",
      {type: noteKind, name: noteCur.name, force: true});
    if (!r.ok) { toast(r.msg, true); rb.disabled = false; rb.textContent = "重新生成"; return; }
    noteCur.content = r.data.content;
    renderNotes();
    toast(r.msg);
  };
  const ab = $("#n-ai");
  if (ab) ab.onclick = async () => {
    if (!confirm("让 AI 把当前内容重新整理一遍？会覆盖这一篇。")) return;
    ab.disabled = true; ab.textContent = "整理中…";
    const r = await post("/api/notes/quick",
      {text: "（按已有内容重新整理，不要新增事实）", date: noteCur.name});
    if (!r.ok) { toast(r.msg, true); ab.disabled = false; ab.textContent = "AI 重新整理"; return; }
    noteCur.content = r.data.content;
    renderNotes();
    toast(r.msg);
  };
  const tb = $("#n-todo");
  if (tb) tb.onclick = async () => {
    tb.disabled = true; tb.textContent = "提取中…";
    const r = await post("/api/notes/todo", {type: kind, name: noteCur.name});
    tb.disabled = false; tb.textContent = "提取待办";
    if (!r.ok) return toast(r.msg, true);
    const list = r.data.todos;
    if (!list.length) return toast(r.msg);
    todoPickModal(list);
  };
  const db = $("#n-del");
  if (db) db.onclick = async () => {
    if (!confirm(`删除 ${noteCur.name} ${NOTE_KIND_CN[noteKind]}？不可恢复。`)) return;
    const r = await post("/api/notes/del", {type: noteKind, name: noteCur.name});
    if (!r.ok) return toast(r.msg, true);
    noteCur = null; NOTES = null;
    await loadNotes();
    toast(r.msg);
  };
  startNotePoll();
}

/* ---- 日记预览（2.4.7 起：日记正文竖排）--------------------------------
 * 用户要的是「阅读像古籍」，**编辑那一侧照旧横排**（在竖排输入框里写字是自虐）。
 *
 * ⚠ 为什么竖排只能给日记：
 *   ① 随笔页是**另一个 tab**（#tab-essay），有自己的编辑器和预览容器，
 *      根本不走 #n-view —— 所以这里天然只影响日记。
 *   ② 但**不能靠这个巧合**。所以下面显式判断 noteKind，
 *      哪天真把随笔也接到这个编辑器上，这里会挡住它，不会误伤。
 *   ③ 回忆书用的 `.md` 气泡是公共样式，绝不加竖排（见 style.css 里 .nview-v 那段）。
 *
 * ⚠ 只在这一个函数里加/去类，别在别处再写一次 innerHTML ——
 *   分散写就会出现「某条路径漏了竖排」或「随笔被竖排了」这种半对半错的状态。
 */
const NOTE_KINDS_VERTICAL = {daily: 1, weekly: 1, monthly: 1};   // 随笔(essay)不在里面

function renderNotePreview() {
  const box = $("#n-view");
  if (!box) return;
  const src = (noteMode === "split" && $("#n-edit")) ? $("#n-edit").value
             : (noteCur ? noteCur.content : "");
  box.classList.toggle("nview-v", !!NOTE_KINDS_VERTICAL[noteKind]);
  box.innerHTML = md(src);
  // ⚠ 必须在 innerHTML 之后：每次重画都会把 span 冲掉，得重套一遍。
}

function renderNoteEditor() {
  const box = $("#nmain");
  if (!box) return;
  if (!noteCur || noteCur.content === null) {
    box.innerHTML = `<div class="card bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">${emptyBox("左边选一篇看看", "或者回总览页随手记一句")}</div>`;
    return;
  }
  const kind = noteKind;
  // 显示名从列表里查（noteCur 只存了文件名和正文）。查不到就退回文件名，
  // 比如刚随手记写完还没重新拉列表的时候。
  const meta = ((NOTES && NOTES[kind]) || []).find(x => x.name === noteCur.name) || {};
  box.innerHTML = `
  <div class="card ncard bg-[var(--card)] border border-[var(--line)] rounded-[14px] px-[18px] py-4 mb-4 overflow-x-auto">
    <div class="nhead">
      <b>${esc(meta.display || noteCur.name)}</b>
      ${meta.sub ? `<span class="mini">${esc(meta.sub)}</span>` : `<span class="mini">${NOTE_KIND_CN[kind]}</span>`}
      <span class="mini" id="n-stat"></span>
      <span style="flex:1"></span>
      <div class="seg segsm nmode">
        <button class="segbtn${noteMode === "edit" ? " on" : ""}" data-nmode="edit"
          title="只显示编辑区，写字最舒服">编辑</button>
        <button class="segbtn${noteMode === "view" ? " on" : ""}" data-nmode="view"
          title="只显示渲染后的效果">预览</button>
        <button class="segbtn${noteMode === "split" ? " on" : ""}" data-nmode="split"
          title="左右对照（窗口窄的时候会挤）">对照</button>
      </div>
      ${kind !== "daily" ? `<button class="btn ghost sm" id="n-regen">重新生成</button>` : ""}
      ${kind === "daily" ? `<button class="btn ghost sm" id="n-ai">AI 重新整理</button>` : ""}
      ${kind === "daily" ? `<button class="btn ghost sm" id="n-todo">提取待办</button>` : ""}
      <button class="btn ghost sm" id="n-img">${ICON.image} 插图</button>
      <button class="btn ghost sm" id="n-exp">导出</button>
      <button class="btn ghost sm" id="n-del">删除</button>
      <button class="btn sm" id="n-save">保存</button>
    </div>
    <div class="nbody ${noteMode}">
      <textarea id="n-edit" spellcheck="false"></textarea>
      <div class="nview md" id="n-view"></div>
    </div>
  </div>`;
  const ta = $("#n-edit");
  ta.value = noteCur.content;
  renderNotePreview();
  const st = $("#n-stat");
  st.textContent = `${noteCur.content.length} 字`;
  ta.oninput = () => {
    noteCur.content = ta.value;
    if (noteMode === "split") renderNotePreview();
    st.textContent = "未保存…";
    clearTimeout(noteSaveTimer);
    noteSaveTimer = setTimeout(() => saveNote(true), 1500);   // 停手 1.5 秒自动存
  };
  ta.onkeydown = e => {
    if (e.key === "Tab") {                                     // Tab 缩进而不是跳走
      e.preventDefault();
      const s = ta.selectionStart;
      ta.value = ta.value.slice(0, s) + "  " + ta.value.slice(ta.selectionEnd);
      ta.selectionStart = ta.selectionEnd = s + 2;
      ta.oninput();
    }
    if (e.key === "s" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); saveNote(); }
  };
  // ⚠ 每次渲染完都要重绑一遍：这个函数会换掉 #nmain 里所有 DOM，
  // 不重绑的话切完模式按钮就全死了（设置页踩过一模一样的坑）
  bindNoteEditorCtl();
}

async function openNote(name) {
  const r = await post("/api/notes/get", {type: noteKind, name});
  if (!r.ok) return toast(r.msg, true);
  noteCur = {name, content: r.data.content};
  renderNotes();
}

async function saveNote(auto) {
  if (!noteCur || noteCur.content === null) return;
  clearTimeout(noteSaveTimer);
  const r = await post("/api/notes/save",
    {type: noteKind, name: noteCur.name, content: noteCur.content});
  if (!r.ok) return toast(r.msg, true);
  const st = $("#n-stat");
  if (st) st.textContent = `${noteCur.content.length} 字 · 已保存 ${new Date().toTimeString().slice(0,5)}`;
  if (!auto) toast("已保存");
  const idx = (NOTES[noteKind] || []).find(x => x.name === noteCur.name);
  if (idx) { idx.empty = !/\S/.test(noteCur.content.replace(/^#.*$/m, "")); }
}

function bindNotes() {
  $$(".nkind").forEach(b => b.onclick = () => {
    if (b.dataset.kind === noteKind) return;
    noteKind = b.dataset.kind;
    noteCur = null;
    loadNotes();
  });
  $$(".nitem").forEach(el => el.onclick = () => openNote(el.dataset.name));
  const g = $("#nb-genall");
  if (g) g.onclick = async () => {
    g.disabled = true; g.textContent = "生成中…";
    const p = NOTES.pending;
    for (const n of p.weekly) await post("/api/notes/generate", {type: "weekly", name: n, force: false});
    for (const n of p.monthly) await post("/api/notes/generate", {type: "monthly", name: n, force: false});
    NOTES = null; noteCur = null;
    await loadNotes();
  };

}

// 后台补齐进行中 → 每 3 秒看一眼进度。
// 注意只换提示条那一块，不能整页重渲染 —— 那样会把正在输入的内容冲掉。
function startNotePoll() {
  clearInterval(notePollTimer);
  const j = (NOTES.pending || {}).job || {};
  if (!j.running) return;
  notePollTimer = setInterval(async () => {
    const p = await get("/api/notes/pending");
    if (!p.ok) return;
    const wasRunning = (NOTES.pending.job || {}).running;
    NOTES.pending = p.data;
    if (wasRunning && !p.data.job.running) {         // 跑完了，重载列表
      clearInterval(notePollTimer);
      const keep = noteCur;
      await loadNotes();
      if (keep) await openNote(keep.name);
    } else {
      const box = $("#nbanner");
      if (box) {
        box.innerHTML = noteBanner();
        const g = $("#nb-genall");
        if (g) g.onclick = () => bindNotes();
      }
    }
  }, 3000);
}

/* ================================================================
   ⑦ 回忆书（和过去的记录对话）
   工具调用循环在后端，这里只管展示：气泡、可折叠的工具过程、新对话。
================================================================ */
/* ---- 回忆书（2.4.1：对话落盘 + 分会话）----
 *
 * ⚠ 2.4.1 之前 `MEM.messages` **只活在内存里** —— 刷新一下、切个标签页
 *   回来就全没了。用户的原话是「回忆书没有对话历史吗，这个需要存下来」。
 *   现在消息存在数据库的 mem_msg 表里，前端只拿一个 `chat` 会话号。
 *
 * 会话号的来源：发第一句问题时后端建一个，随回答一起发回来。
 * 不这么做的话（比如前端自己造），多开几个窗口就会撞号。 */
let MEM = {chat: "", chats: [], messages: [], busy: false};
const MEM_EXAMPLES = ["我上周都干了什么？", "这个月花了多少钱，主要花在哪？",
                      "最近睡得怎么样？", "开学到现在有什么变化？"];

function memStamp() {
  const d = new Date();
  const p = n => String(n).padStart(2, "0");
  return `[发送时间：${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ` +
         `${p(d.getHours())}:${p(d.getMinutes())} 星期${WEEK[d.getDay()]}]`;
}

/** 拉会话列表 + 当前会话的消息。第一次进来时自动开最近那个。 */
async function loadMemory(chat) {
  const r = await post("/api/memory/chats", {});
  MEM.chats = (r.ok && r.data && r.data.chats) || [];
  const want = chat || MEM.chat || (MEM.chats[0] && MEM.chats[0].chat) || "";
  if (want) {
    const h = await post("/api/memory/history", {chat: want});
    if (h.ok) { MEM.chat = h.data.chat; MEM.messages = h.data.messages || []; }
  } else {
    MEM.chat = ""; MEM.messages = [];
  }
}

function memSideHtml() {
  return `<div class="nside">
    <button class="btn line sm mnew" id="m-new">${ICON.pencil} 开一个新对话</button>
    <div class="nlist">
      ${MEM.chats.length ? MEM.chats.map(c => `
        <div class="nitem${c.chat === MEM.chat ? " on" : ""}" data-chat="${esc(c.chat)}">
          <div class="nname">${esc(c.title)}</div>
          <div class="nprev">${esc((c.ts || "").slice(5, 16))} · ${c.n} 条</div>
        </div>`).join("")
        : '<div class="mini" style="padding:14px 12px">还没有对话。在右边问一句试试。</div>'}
    </div>
  </div>`;
}

function renderMemory() {
  const msgs = MEM.messages;
  const body = msgs.length ? msgs.map(m => {
    if (m.role === "user") {
      const plain = m.content.replace(/\n*\[发送时间：.*?\]\s*$/s, "");
      return `<div class="mmsg me"><div class="mbubble">${esc(plain).replace(/\n/g, "<br>")}</div></div>`;
    }
    const tr = (m.trace || []).length ? `
      <details class="mtrace">
        <summary>查了 ${m.trace.length} 次记录</summary>
        ${m.trace.map(t => {
          const n = t.result && (t.result.count ?? (t.result.results || []).length);
          const err = t.result && t.result.error;
          return `<div class="mtline${err ? " bad" : ""}">
            <code>${esc(t.tool)}</code>
            <span class="mini">${esc(JSON.stringify(t.args))}</span>
            ${err ? `<b>${esc(err)}</b>` : (n !== undefined ? `<b>${n} 条</b>` : "")}
          </div>`;
        }).join("")}
      </details>` : "";
    return `<div class="mmsg"><div class="mbubble md">${md(m.content)}${tr}</div></div>`;
  }).join("") : `
    <div class="mempty">
      <div class="mtitle">${ICON.sparkle} 回忆书</div>
      <div class="mini">问它任何关于你过去记录的问题。它会自己去翻日报、周报、月报，也能查打卡和账单里的数字，然后基于查到的东西回答——查不到就说查不到，不会编。</div>
      ${(AICFG && !AICFG.has_key) ? `<div class="warn" style="margin:14px auto 0;max-width:560px;text-align:left">
        <b>还没配 API Key</b>，现在问它只会回答「查不到」。去
        设置 → AI 填上，再回来。</div>` : ""}
      <div class="mex">${MEM_EXAMPLES.map(q => `<button class="mexbtn">${q}</button>`).join("")}</div>
    </div>`;

  $("#tab-memory").innerHTML = `
  <div class="mwrap">
    <div class="mhead">
      <b>${ICON.sparkle} 回忆书</b>
      <span class="mini">基于你自己的记录回答，不会编造</span>
      <span style="flex:1"></span>
      <!-- ⚠ 对话存在数据库里，所以「清空」必须说清楚它删的是什么、
           不删什么 —— 用户最怕的就是点一下把日记也带走。 -->
      ${MEM.chat ? `<button class="btn ghost sm" id="m-del"
        title="只删这一串对话，笔记一个字都不动">删除这串对话</button>` : ""}
    </div>
    <div class="mbody">
      ${memSideHtml()}
      <div class="mlist" id="mlist">${body}
        ${MEM.busy ? `<div class="mmsg"><div class="mbubble"><span class="mdots">正在翻记录…</span></div></div>` : ""}
      </div>
    </div>
    <div class="minput">
      <textarea id="m-text" rows="2" placeholder="问点什么…（Ctrl+Enter 发送，Enter 换行）"></textarea>
      <button class="btn" id="m-send">发送</button>
    </div>
  </div>`;
  bindMemory();
  const box = $("#mlist");
  if (box) box.scrollTop = box.scrollHeight;
}

function bindMemory() {
  const ta = $("#m-text"), btn = $("#m-send");
  $$(".mexbtn").forEach(b => b.onclick = () => { ta.value = b.textContent; ta.focus(); });
  // 点会话列表切过去
  $$("#tab-memory .nitem").forEach(el => el.onclick = async () => {
    const c = el.dataset.chat;
    if (!c || c === MEM.chat) return;
    MEM.busy = false;
    await loadMemory(c);
    renderMemory();
  });
  const nb = $("#m-new");
  if (nb) nb.onclick = () => {
    // 新会话**不马上建**，等第一句问题发出去、后端建号 —
    // 开了又不用的话，列表里会堆一堆空标题。
    MEM.chat = ""; MEM.messages = []; MEM.busy = false;
    renderMemory();
  };
  const db = $("#m-del");
  if (db) db.onclick = async () => {
    if (!confirm("删掉这串对话？\n\n只删对话记录，你的日记、周报、账单一个字都不会动。")) return;
    const r = await post("/api/memory/clear", {chat: MEM.chat});
    if (!r.ok) return toast(r.msg, true);
    MEM.chat = ""; MEM.messages = [];
    await loadMemory();
    toast("已删除");
    renderMemory();
  };
  if (!ta || !btn) return;
  btn.disabled = MEM.busy;
  const send = async () => {
    const text = ta.value.trim();
    if (!text || MEM.busy) return;
    ta.value = "";
    // 先把这句摆上去（含时间戳，跟存进库的那份一致），不然点了发送没反应
    MEM.messages.push({role: "user", content: text + "\n\n" + memStamp()});
    MEM.busy = true;
    renderMemory();
    // ⚠ 只发**会话号 + 这一句**。历史在后端从库里读 ——
    //   以前是把整个 messages 数组发上去，刷新一次上下文就断了。
    const r = await post("/api/memory/chat", {chat: MEM.chat, question: text});
    MEM.busy = false;
    if (!r.ok) {
      MEM.messages.push({role: "assistant", content: "**出错了**：" + r.msg, trace: []});
    } else {
      MEM.chat = r.data.chat || MEM.chat;
      MEM.messages.push({role: "assistant", content: r.data.answer || "（没有回答）",
                         trace: r.data.trace || []});
      await post("/api/memory/chats", {}).then(x => {
        if (x.ok && x.data) MEM.chats = x.data.chats || MEM.chats;
      });
    }
    renderMemory();
  };
  btn.onclick = send;
  ta.onkeydown = e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); }
  };
  ta.focus();
}

/* ---------- 从日报提取待办：先勾选，确认后才写进待办表 ---------- */
function todoPickModal(list) {
  $("#modalCard").innerHTML = `<h3>从这篇日报里找到 ${list.length} 条待办</h3>
    <div class="mini" style="margin-bottom:10px">勾选要加的，确认后才写进物资表的「待办」Sheet。可以就地改。</div>
    <div class="tpick">${list.map((t, i) => `
      <div class="tprow">
        <input type="checkbox" id="tp-${i}" checked>
        <input class="tp-item" data-i="${i}" value="${esc(t.item)}">
        <select class="tp-cat" data-i="${i}">${["采购","事务","学习","生活","其他"]
          .map(c => `<option${c === t.cat ? " selected" : ""}>${c}</option>`).join("")}</select>
        <select class="tp-pri" data-i="${i}">${["高","中","低"]
          .map(c => `<option${c === t.pri ? " selected" : ""}>${c}</option>`).join("")}</select>
        <input type="date" class="tp-due" data-i="${i}" value="${esc(t.due || "")}">
      </div>`).join("")}</div>
    <div class="modal-actions"><button class="btn ghost" id="m-cancel">取消</button>
    <button class="btn" id="m-ok">加入待办</button></div>`;
  $("#modal").hidden = false;
  $("#m-cancel").onclick = () => $("#modal").hidden = true;
  $("#modal").onclick = e => { if (e.target === $("#modal")) $("#modal").hidden = true; };
  $("#m-ok").onclick = async () => {
    const picked = [];
    $$(".tprow").forEach((row, i) => {
      if (!row.querySelector(`#tp-${i}`).checked) return;
      const item = $(`.tp-item[data-i="${i}"]`).value.trim();
      if (!item) return;
      picked.push({stat: "未完成", item,
        cat: $(`.tp-cat[data-i="${i}"]`).value,
        pri: $(`.tp-pri[data-i="${i}"]`).value,
        due: $(`.tp-due[data-i="${i}"]`).value || "",
        note: list[i].note || ""});
    });
    if (!picked.length) { toast("一条都没勾"); return; }
    const btn = $("#m-ok");
    btn.disabled = true; btn.textContent = "写入中…";
    let done = 0, errs = [];
    for (const t of picked) {
      const r = await post("/api/todo/add", t);
      if (r.ok) done++; else errs.push(r.msg);
    }
    $("#modal").hidden = true;
    STOCK = null;                                  // 让物资页重新拉
    toast(done ? `已加入 ${done} 条待办${errs.length ? "，" + errs.length + " 条失败" : ""}`
               : "都没写进去：" + errs[0], !done);
  };
}

/* ---------------- 访问密码锁 ---------------- */
// 说明白：数据是明文躺在硬盘上的，这把锁只挡「别人顺手点开你的程序」。
// 挡不住拿到你电脑的人 —— 真正的保护是 BitLocker + 系统登录密码。
function showLock() {
  const el = $("#lock");
  el.hidden = false;
  el.innerHTML = `<div class="lockcard">
    <div class="lockicon">${ICON.lock}</div>
    <div class="locktitle">小煦拾简</div>
    <div class="mini">输入密码解锁</div>
    <input type="password" id="lock-pw" placeholder="密码" autocomplete="current-password">
    <button class="btn" id="lock-go">解锁</button>
    <div class="mini" id="lock-msg" style="min-height:18px"></div>
  </div>`;
  const go = async () => {
    const pw = $("#lock-pw").value;
    if (!pw) return;
    const btn = $("#lock-go");
    btn.disabled = true; btn.textContent = "验证中…";
    const r = await post("/api/auth/unlock", {password: pw});
    btn.disabled = false; btn.textContent = "解锁";
    if (!r.ok) {
      $("#lock-msg").textContent = r.msg;
      $("#lock-pw").value = "";
      return;
    }
    AUTH_TOKEN = r.data.token;
    try { sessionStorage.setItem("xr_token", AUTH_TOKEN); } catch (e) {}
    el.hidden = true;
    await bootAfterAuth();
  };
  $("#lock-go").onclick = go;
  $("#lock-pw").onkeydown = e => { if (e.key === "Enter") go(); };
  setTimeout(() => $("#lock-pw").focus(), 100);
}

let AUTH_TOKEN = "";
try { AUTH_TOKEN = sessionStorage.getItem("xr_token") || ""; } catch (e) {}

/* ---------------- 启动 ---------------- */
/* ---------------- 桌面外壳的窗口控制 ----------------
   在桌面版里窗口是**无系统标题栏**的（要微信那种干净边框），所以最小化/
   最大化/关闭得自己画。浏览器版没有 window.pywebview，这一整段不会运行。
   拖动窗口交给外壳用 Win32 原生方式处理 —— 在 JS 里逐像素挪窗口会拖影。 */
function setupDesktopShell() {
  if (!window.pywebview || !window.pywebview.api) return;
  document.documentElement.classList.add("in-shell");
  const bar = document.querySelector(".top");
  if (!bar || bar.querySelector(".winbtns")) return;
  const box = document.createElement("div");
  box.className = "winbtns";
  box.innerHTML =
    `<button class="winbtn" data-win="min" title="最小化">${ICON.minus}</button>
     <button class="winbtn" data-win="max" title="最大化 / 还原">${ICON.square}</button>
     <button class="winbtn close" data-win="close" title="关闭">${ICON.x}</button>`;
  bar.appendChild(box);
  // 顶栏空白处按住就能拖窗口；点在按钮/下拉上不算
  bar.addEventListener("mousedown", e => {
    if (e.button !== 0) return;
    if (e.target.closest("button,select,input,a")) return;
    window.pywebview.api.drag_start();
  });
  bar.addEventListener("dblclick", e => {
    if (e.target.closest("button,select,input,a")) return;
    window.pywebview.api.win_max();
  });
  box.querySelectorAll("[data-win]").forEach(b => b.onclick = () => {
    const k = b.dataset.win;
    if (k === "min") window.pywebview.api.win_min();
    else if (k === "max") window.pywebview.api.win_max();
    else window.pywebview.api.win_close();
  });
  // 最大化时圆角要去掉，不然四个角会露出桌面
  const sync = () => window.pywebview.api.win_state().then(st =>
    document.documentElement.classList.toggle("maxed", !!st.maximized));
  sync();
  window.addEventListener("resize", sync);
}

// 把 HTML 里的 <span data-icon="xxx"> 换成对应的线条图标。
// 图标只在 ICON 表里定义一次，页面各处引用它，不会两边各维护一份。
function paintIcons(root) {
  $$("[data-icon]", root || document).forEach(el => {
    const svg = ICON[el.dataset.icon];
    if (svg && el.innerHTML !== svg) el.innerHTML = svg;
  });
}

function bindShotEntry() {
  /** 「从截图记账 / 录睡眠」这两个按钮是**页面重渲染时现生成**的，
   *  每次重渲染都重新绑一遍很容易漏。但 #tab-bill / #tab-check 这两个
   *  <section> 本身是 index.html 里的常驻元素，从头到尾没被换过 ——
   *  所以在它们身上挂一次委托，之后不管里面重渲染多少回都管用。 */
  const hook = (sel, kind) => {
    const box = $("#" + sel);
    if (!box) return;
    box.addEventListener("click", e => {
      if (e.target.closest("#shot-" + kind)) openShot(kind);
    });
  };
  hook("tab-bill", "bill");
  hook("tab-check", "sleep");
}

/** 开机要告诉你的一件事（比如「数据刚从 Excel 搬进数据库」）。
 *  打包版没有控制台，那些字用户一个字都看不见 —— 但「我的数据被动了」
 *  这种事必须当面说清楚，不然心里没底。
 *  接口是取走即清，所以只会看见一次。 */
async function showNotice() {
  const r = await get("/api/notice").catch(() => null);
  const msg = (r && r.ok && r.data && r.data.msg) || "";
  if (!msg) return;
  modal("有一件事要告诉你", `
    <div style="white-space:pre-wrap;line-height:1.7;font-size:13px">${esc(msg)}</div>
    <p class="mini" style="margin-top:12px">
      原来的三本 Excel 还在原地，没删也没改。想拿一份回 Excel，
      到「设置 → 数据 → 导出成 Excel」。
    </p>`, async () => true);
  $("#m-cancel").hidden = true;             // 只有「知道了」
  $("#m-ok").textContent = "知道了";
}

function startApp() {
  startStampWatch();          // 盯着「数据有没有在别处被改过」
  paintIcons();               // 顶栏/导航的线条图标
  bindShotEntry();
  showNotice();
  // pywebview 的 API 是注入进来的，可能比脚本执行晚一点
  let _t = 0; const _w = setInterval(() => {
    if (window.pywebview && window.pywebview.api) { clearInterval(_w); setupDesktopShell(); }
    else if (++_t > 40) clearInterval(_w);
  }, 100);
  initSuggest();
  loadSemesters();
  loadOverview();
  const t = (APPCFG && APPCFG.default_tab) || "over";
  if (t && t !== "over") switchTab(t);
}

async function bootAfterAuth() {
  const r = await get("/api/settings");
  if (r.ok) { APPCFG = r.data; applyTheme(); }
  startApp();
}

(async function boot() {
  // 1) 先拿设置上主题，免得先闪一下默认色
  const s = await get("/api/settings").catch(() => ({ok: false}));
  if (s.ok) { APPCFG = s.data; }
  applyTheme();
  // 2) 看要不要解锁（这一步不需要令牌）
  const st = await get("/api/auth/state").catch(() => ({ok: false}));
  if (st.ok && st.data.need_password && !st.data.unlocked) {
    showLock();
    return;
  }
  startApp();
})();

/* 开屏：点一下可以提前跳过。不点也会自己淡出（动画在 CSS 里）。 */
(function splash() {
  const el = document.getElementById("splash");
  if (!el) return;
  el.onclick = () => { el.style.animation = "splashOut .3s ease forwards"; };
  // 淡出动画结束后彻底摘掉，免得那层 fixed 覆盖还留在 DOM 里挡点击
  setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 2600);
})();

/* ---------------- 全局 ---------------- */
function resizeCharts() { Object.values(charts).forEach(c => c.resize()); }
window.addEventListener("resize", () => setTimeout(resizeCharts, 100));

