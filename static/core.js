/* 小煦拾简 · 前端基础设施（第 1 步拆出来的）
 *
 * 这一段原来是 static/app.js 的开头（第 1 ~ 865 行），整段搬过来的，**函数体一个字没改**。
 *
 * 里面是什么：
 *   · 顶层 const/let：$, $$, esc, money, num2, todayStr, dateToMonthName, WEEK,
 *     IS_SHELL, BILL, charts, chartTheme, DIRTY, STAMP_*, hhmm, LAST_SYNC, ...
 *   · 基础工具：数字/颜色/主题/背景、toast/busy/idle/modal、openDir/copyText、
 *     ICON + paintIcons、emptyBox/badge/gcard/kpi
 *
 * ⚠⚠ 这个文件**必须第一个加载**（index.html 里排在所有其它脚本前面）。
 *     原因：它声明了 109 个顶层 const/let，别的文件全都靠这些名字活着。
 *     现代浏览器里多个 <script> 共享同一个全局环境，所以只要顺序对，互相都看得见。
 *     **不需要任何构建工具。**
 */
/* 小煦拾简 · 前端（原生 JS + ECharts，无构建） */
"use strict";
const $ = (s, root) => (root || document).querySelector(s);
// 第二个参数是作用域根节点，省略时才是全文档。
// ⚠ 必须支持作用域：给局部元素绑事件时若全文档查找，会把别的按钮一起改写掉。
const $$ = (s, root) => [...(root || document).querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = v => "¥" + Number(v || 0).toLocaleString("zh-CN", {minimumFractionDigits:2, maximumFractionDigits:2});
/* 落单的数字（不带 ¥、不带千分位）统一从这里出。
 * ⚠ 浮点累加会漏：库里 sum(exp) 出来的就是 33.75000000000001 /
 *   114.22999999999999。后端已在源头收过一道（load_bill 里 day_exp 那段），
 *   这里是第二道 —— 凡是往 DOM 里塞**金额**的地方都走它，别直接插值。 */
const num2 = v => {
  // ⚠ 空值得单独挡一下：`Number("")` 是 **0**（不是 NaN），
  //   不挡的话空单元格会印成「0」，看着像"这天花了 0 元"。
  if (v === "" || v == null) return "";
  const n = Number(v);
  return isFinite(n) ? String(Math.round(n * 100) / 100) : String(v);
};
const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
};
const dateToMonthName = s => `${s.slice(0,4)}年${s.slice(5,7)}月`;
const WEEK = ["日","一","二","三","四","五","六"];
// 是不是跑在 Electron 壳里。有些功能（桌面小时钟、打开文件夹）只有壳里才有，
// 网页版要**明确地说明为什么用不了**，而不是给一个点了没反应的按钮。
const IS_SHELL = !!(typeof window !== "undefined" && window.xrShell && window.xrShell.isShell);

let BILL = null, CHECK = null, STOCK = null;
let checkMonth = null, checkDay = null, stockSheet = "药品";
// 物资表一次显示多少条（2.4.7）。切到别的表会回到 10 —— 见 renderStock 里那个按钮。
// ⚠ 只影响**显示**，后端查询和列宽判断都还是拿全部行算。
let stockLimit = 10;
// 随笔页的显示模式（2.4.7）。随笔原本只有编辑框，为了能竖排阅读才补的预览。
let essayMode = "edit";        // edit | view | split
const charts = {};
// 每张图当前用的是哪套主题。**不能挂在 ECharts 实例上** —— 实例的 `_theme` 是它自己的
// Theme 对象，覆盖成字符串之后，之后每次 setOption 都会在内部炸掉（图表一片空白）。
const chartTheme = {};

// 设了访问密码的话，每个请求都要带上解锁时拿到的令牌。
// AUTH_TOKEN 在下面「访问密码锁」一节声明 —— 这些函数只在模块跑完之后才被调用，
// 所以不会碰到暂时性死区。
function authHeaders(extra) {
  return Object.assign({}, extra || {}, AUTH_TOKEN ? {"X-Auth-Token": AUTH_TOKEN} : {});
}
async function get(path) {
  const r = await fetch(path, {headers: authHeaders()});
  return r.json();
}
async function post(path, body) {
  const r = await fetch(path, {method:"POST", headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify(body || {})});
  const j = await r.json();
  if (j && j.ok) markDirtyByApi(path);
  return j;
}

/* ---------------- 数据新鲜度 ----------------
   哪些接口动过之后、哪些页要重新拉 —— 写死一张表，**在 post() 里统一处理**。
   以前每个写操作各自清各自的域，切页面又直接用内存里那份，
   于是在别处改的数据（另一个窗口、另一台设备）永远看不到，页面一直拿着旧的那份。
   放在这里而不是各个调用点，是为了不会有「新加的写操作忘了标」这种事。 */
const DIRTY_BY_API = [
  [/^\/api\/(bill|tail|cats)\//,      ["bill", "over"]],
  [/^\/api\/(check|dream)\//,         ["check", "over"]],
  [/^\/api\/(stock|todo)\//,          ["stock", "todo", "over"]],
  [/^\/api\/(notes|recycle)\//,       ["note"]],
  [/^\/api\/(semester|backup)\//,     ["bill", "check", "stock", "over"]],
];
const DIRTY = new Set();
function markDirty(...pages) { pages.forEach(p => DIRTY.add(p)); }
function isDirty(...pages) { return pages.some(p => DIRTY.has(p)); }
function clearDirty(...pages) { pages.forEach(p => DIRTY.delete(p)); }
function markDirtyByApi(path) {
  for (const [re, pages] of DIRTY_BY_API) {
    if (re.test(path)) { markDirty(...pages); syncStamp(); return; }
  }
}

/* ---- 别处改了数据？----
   另开了一个窗口、或者别的地方改了同一份数据，这个窗口是不知道的。
   所以每隔几秒问服务端要一次「数据戳」（几个短字符串），戳变了就在顶上出一条提示。
   **不自动重新加载**：你可能正填着表，自动刷会把没提交的内容冲掉，
   数据看着是新的了，你刚写的东西却没了 —— 那比显示旧数据更糟。 */
let STAMP = null;
let STAMP_TIMER = null;
let STAMP_MUTE = false;      // 自己刚写完数据的这几百毫秒里，别把自己的改动当成「别处改的」
// 点过「知道了」的那一次改动。**按了知道了就别再念同一件事** ——
// 否则 5 秒后轮询又会把同一条弹出来，用户会觉得「说了知道了还一直弹」。
// 但要是之后又有新的改动（戳又变了），那还是要提醒。
let STAMP_ACK = null;

// 把基准戳刷成最新的。两处要调：
//   ① 自己写完数据之后 —— 不然你每记一笔都会被自己的改动弹一次「别处改过」
//   ② 每次成功加载数据之后 —— 不然「别处改了 → 我切页自动重拉了」之后，
//      基准戳还停在旧值，下一轮轮询又会把已经同步好的数据报成「被改过」
// 一句话：只要是「我刚从服务端拿过最新数据」，基准就应该是那一刻。
async function syncStamp() {
  STAMP_MUTE = true;
  try {
    const r = await get("/api/stamp").catch(() => null);
    if (r && r.ok) STAMP = r.data;
  } finally { STAMP_MUTE = false; }
}

async function pollStamp() {
  const r = await get("/api/stamp").catch(() => null);
  if (!r || !r.ok || STAMP_MUTE) return;
  const s = r.data;
  if (STAMP === null) { STAMP = s; return; }      // 头一次只记下来，不算「变了」
  const changed = Object.keys(s).filter(k => k !== "semester" && STAMP[k] !== s[k]);
  const semChanged = s.semester !== STAMP.semester;
  const ackSame = STAMP_ACK && Object.keys(s).every(k => STAMP_ACK[k] === s[k]);
  if ((changed.length || semChanged) && !ackSame) showStaleBar(changed, semChanged, s);
}

function showStaleBar(changed, semChanged, snap) {
  const bar = $("#stale");
  if (!bar || !bar.hidden) return;                // 已经显示着就别重复弹
  const what = semChanged ? "学期被切换过"
    : changed.map(k => ({bill: "账单", check: "打卡表", stock: "物资表", notes: "笔记",
                         backup: "配置"}[k] || k)).join("、");
  bar.innerHTML = `<span>⚠ ${esc(what)}在别处被改过，这儿显示的还是旧的</span>
    <button class="btn sm" id="stale-reload">重新加载</button>
    <button class="btn ghost sm" id="stale-ignore">知道了</button>`;
  bar.hidden = false;
  $("#stale-reload").onclick = async () => {
    bar.hidden = true;
    await reloadAll();
  };
  $("#stale-ignore").onclick = () => {
    bar.hidden = true;
    STAMP_ACK = snap || null;      // 记住「这次我知道了」，同一批改动不再弹
  };
}

// 全量重来：数据、设置、以及当前页
async function reloadAll() {
  BILL = CHECK = STOCK = NOTES = null;
  markDirty("over", "bill", "check", "stock", "note");
  STAMP = null; STAMP_ACK = null;
  const s = await get("/api/settings");
  if (s.ok) { APPCFG = s.data; applyTheme(); }
  await loadSemesters();
  await loadOverview();
  const cur = ($$(".tabbody").find(x => !x.hidden) || {}).id;
  if (cur && cur !== "tab-over") switchTab(cur.replace("tab-", ""));
  toast("已重新加载");
}

function startStampWatch() {
  if (STAMP_TIMER) clearInterval(STAMP_TIMER);
  pollStamp();
  STAMP_TIMER = setInterval(pollStamp, 5000);
}
function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => t.hidden = true, 2600);
}
/* 右上角那个状态。
   ⚠ 这里以前写的是「已连接 + 当前时间」，但那个时间其实只在**重新加载数据时**
   才刷新一次 —— 程序开着不动，它就永远停在那一刻，看着像卡死了（实际被这么误会过）。
   现在拆成两件事：显示的是**实时时钟**（跟系统时间走），
   「上次同步」挪进悬停提示。两个信息都在，但不会互相冒充。 */
const hhmm = d => String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
let LAST_SYNC = null;

function syncTipText() {
  const t = $("#syncTip");
  if (!t) return;
  t.textContent = "已连接 " + hhmm(new Date());
  if (LAST_SYNC) {
    t.title = "上次同步 " + hhmm(LAST_SYNC) + ":" + String(LAST_SYNC.getSeconds()).padStart(2, "0");
  }
}
function busy() { const t = $("#syncTip"); if (t) { t.textContent = "保存中…"; t.dataset.busy = "1"; } }
function idle() {
  const t = $("#syncTip");
  if (t) delete t.dataset.busy;
  LAST_SYNC = new Date();
  syncTipText();
}
// 每 5 秒对一次表：只在文字真的变了才写 DOM（一分钟才变一次，绝大部分时候是空转）
setInterval(() => { if (!document.hidden) syncTipText(); }, 5000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) syncTipText(); });
/* ---------------- 主题（外观设置） ---------------- */
// 三套配色 × 深浅两模式。变量全在 style.css 里，这里只负责把 data-* 打上去。
// --blue 是「主强调色」不是字面的蓝色 —— 米黄配色下它是赭金，名字没改是怕动 100 多处。
let APPCFG = null;
let ABOUT = null;
let CHART_THEME = "xr0";        // 每次换主题换个名字，逼 chartOf 重建图表实例

function cssVar(n, d) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  return v || d;
}

function buildChartTheme() {
  const txt = cssVar("--txt", "#1f2933"), txt2 = cssVar("--txt2", "#475569");
  const mut = cssVar("--mut", "#7b8794"), line = cssVar("--line", "#e3e9f2");
  const card = cssVar("--card", "#fff");
  const axis = {
    axisLine: { lineStyle: { color: line } },
    axisTick: { lineStyle: { color: line } },
    axisLabel: { color: mut },
    splitLine: { lineStyle: { color: line } },
    nameTextStyle: { color: mut },
  };
  return {
    textStyle: { color: txt2 },
    categoryAxis: JSON.parse(JSON.stringify(axis)),
    valueAxis: JSON.parse(JSON.stringify(axis)),
    legend: { textStyle: { color: txt2 } },
    tooltip: { backgroundColor: card, borderColor: line, textStyle: { color: txt } },
  };
}

function applyTheme() {
  const c = APPCFG || {};
  const root = document.documentElement;
  let mode = c.theme || "auto";
  if (mode === "auto") {
    mode = (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches)
      ? "dark" : "light";
  }
  // 素纸原来叫「米黄」。老设置里存的还是旧名字，这里统一正名 ——
  // CSS 那边两个名字都发了一份色块，所以正不正名都不会掉色。
  const pal = c.palette === "米黄" ? "素纸" : (c.palette || "素纸");
  root.dataset.palette = pal;
  root.dataset.theme = mode;
  root.classList.toggle("no-anim", c.animations === false);
  root.style.setProperty("--fs", (Number(c.font_size) || 14) + "px");
  root.style.setProperty("--font",
    c.font ? `"${c.font}", var(--font-base)` : "var(--font-base)");
  // 桌面壳里没去掉原生标题栏，窗口按钮浮在顶栏右侧 —— 要给它们让出位置，
  // 不然「设置」标签会被压在按钮底下。在浏览器里跑时没有这条缝，也就没有这个标记。
  const shell = typeof window !== "undefined" && !!window.xrShell;
  root.classList.toggle("shell", shell);
  if (shell) { try { window.xrShell.setTheme(mode); } catch (e) {} }
  // ECharts 的主题在 init 时固定，换主题必须注册一个新的名字 + 重建实例
  CHART_THEME = "xr" + Date.now().toString(36);
  try { echarts.registerTheme(CHART_THEME, buildChartTheme()); } catch (e) {}
  applyBg();
  applyDiaryFont();
}

/* ================================================================
   日记/随笔竖排正文字体（2.5.1）
   ----------------------------------------------------------------
   ⚠⚠ 为什么是**用 FontFace API 在 JS 里加载**，而不是 CSS 里写 @font-face：
     实测过 —— CSS 那条路**不可靠**。同样的文件、同样的 @font-face 规则，
     裸页面里能注册（document.fonts.size = 1），但在应用页面里
     `document.fonts.size` 一直是 0、字体静默回退成华文行楷。
     用户当时的话是「你日记那里还是用的华文行楷」—— 就是被这个回退骗了。
     改用 FontFace API 之后：加载成功/失败**我们能拿到明确的 status**，
     失败还能报告出来，不再是"看着像生效了其实没有"。
     （CSS 里那条 @font-face 已经删掉，免得两条路打架。）

   ⚠ 字体是**按需加载**的（选哪个下哪个），不是一次下两个：
     瘦金体 12 MB + 行书 5.6 MB = 17.6 MB，全局下载太浪费。
   ⚠ 两个字体都自带在包里（static/fonts/），**不联网**。
================================================================ */
const DIARY_FONTS = {
  // value: [显示名, 字体文件名, 加载后的 family 名]
  shoujin: ["瘦金体", "shoujinti.ttf", "ShouJinTi"],
  mashan:  ["马善政行书", "mashanzheng.ttf", "MaShanZheng"],
};
const _fontLoaded = {};          // family → Promise，避免重复下载

function loadDiaryFontFile(value) {
  const info = DIARY_FONTS[value];
  if (!info) return Promise.resolve(null);
  const family = info[2];
  if (_fontLoaded[family]) return _fontLoaded[family];
  _fontLoaded[family] = (async () => {
    try {
      const r = await fetch("/static/fonts/" + info[1]);
      if (!r.ok) throw new Error("HTTP " + r.status);
      const buf = await r.arrayBuffer();
      const ff = new FontFace(family, buf);
      await ff.load();
      document.fonts.add(ff);
      return family;
    } catch (e) {
      // ⚠ 失败要说出来。以前静默回退成行楷，看着"像是生效的"，
      //   用户报了两次我才查出来 —— 这种静默失败最坑。
      if (typeof noteJsError === "function") noteJsError("日记字体加载失败：" + info[1] + " " + e.message);
      return null;
    }
  })();
  return _fontLoaded[family];
}

/** 把用户选的日记字体应用到 --diary-font（CSS 里 .nview-v 用它）。 */
async function applyDiaryFont() {
  const v = (APPCFG || {}).diary_font;
  const root = document.documentElement;
  if (!v || !DIARY_FONTS[v]) {
    // 空 = 让 CSS 用系统书法体回退链（华文行楷那几个）
    root.style.removeProperty("--diary-font");
    return;
  }
  const fam = await loadDiaryFontFile(v);
  if (fam) root.style.setProperty("--diary-font", `"${fam}"`);
  else root.style.removeProperty("--diary-font");   // 加载失败 → 退回系统字体
}

/* 背景图。做法是在 body 上挂一层固定的 ::before 由 CSS 画，
   这里只负责把地址和三个参数塞进 CSS 变量。

   ⚠ 为什么不用 body{background-image}：那样背景会跟着页面滚，
   长页面滚到下面就变成一片纯色；而且没法单独模糊它（filter 会连内容一起糊掉）。
   固定定位的伪元素两层就干净了：底下是照片，上面压一层半透明遮罩保证字看得清。 */
function applyBg() {
  const c = APPCFG || {};
  const root = document.documentElement;
  // 壁纸三模式（2.3.6）：image 照片 / solid 纯色 / none 不要。
  // ⚠ 老设置里只有 bg_image、没有 bg_mode —— 所以 mode 缺省时**看有没有图**
  //   反推，不然一升级所有人的背景就没了。
  const mode = c.bg_mode || (c.bg_image ? "image" : "none");
  const has = mode === "image" && !!c.bg_image;
  const solidOn = mode === "solid" && !!c.bg_solid;
  root.classList.toggle("has-bg", has);
  root.classList.toggle("solid-bg", solidOn);
  if (solidOn) root.style.setProperty("--bg-solid", c.bg_solid);
  // 填充方式：只有照片模式用得上。
  // contain / center 时不能配 scale(1.06)（那是给 cover 顶模糊边缘用的），
  // 不然居中的小图会被放大一点点、位置也不对。
  const fill = c.bg_fill || "cover";
  root.style.setProperty("--bg-size",
    fill === "contain" ? "contain" : (fill === "center" ? "auto" : "cover"));
  // 只有铺满时才把照片放大一点点（顶掉模糊糊出来的半透明边缘）
  root.style.setProperty("--bg-zoom", fill === "cover" ? "1.06" : "1");
  if (!has) {
    root.style.setProperty("--bg-img", "none");
    applyGlass(0);            // 没照片，通透没有意义（后面什么都没有）
    return;
  }
  // ⚠ 版本号必须用 **bg_rev（图片文件的改动时间）**，不能用文件名。
  //   文件名换图之后还是「背景.jpg」，URL 一模一样 —— 浏览器认不出这是新图，
  //   直接把缓存里那张旧的端出来。实测：传了红色再传蓝色，取回来的还是红的。
  //   服务端现在对 /bg 也发了 no-store，这里是第二道保险。
  root.style.setProperty("--bg-img",
    `url("/bg?v=${encodeURIComponent(c.bg_rev || c.bg_image || "0")}")`);
  root.style.setProperty("--bg-dim", (Number(c.bg_dim == null ? 0 : c.bg_dim) / 100).toFixed(3));
  root.style.setProperty("--bg-blur", (Number(c.bg_blur) || 0) + "px");
  // 没背景图的时候通透没有意义（后面什么都没有），强制关掉
  applyGlass(has ? (Number(c.bg_glass) || 0) : 0);
}

/* ---- 卡片通透：把照片透出来 ----
 *
 * ⚠ 为什么是在 JS 里改 --card，而不是写一条 CSS 规则：
 *   论写法只有一种：
 *     :root.bg-glass{--card: color-mix(in srgb, var(--card) 72%, transparent)}
 *   而这是**自己引用自己**。CSS 变量循环引用会被判为无效，
 *   整条声明直接作废 —— 页面上什么都不会变，也不报错。这个坑踩过一次。
 *   所以改成：JS 从配色块里读出那个实色，算好 rgba 再写回去。
 *
 * 一处覆盖、30 处生效 —— 全站 30 个 `background:var(--card)` 都是引用的这个变量，
 * 改它一个就够，不用去动那 30 行。
 */
const GLASS_VARS = ["--card", "--soft", "--soft2", "--top-bg", "--chip-bg",
                    "--chip-line", "--input-bg"];
// 卡片**再怎么透也留在 86% 不透明**（2.3.7 从 55% 提上来）。
//
// ⚠ 55% 那一版是配着 `backdrop-filter` 用的：卡片只有一半实体，靠模糊把
//   背后的照片揉成一片色块，字才压得住。2.3.7 把毛玻璃整个去掉之后，
//   55% 就变成了「照片清晰地透过卡片」—— 字直接坐在照片纹理上，
//   比原来还难看。既然定了「卡片改实心纸面」，下限就得跟着上去。
//
// 滑块拉到最透（100）时卡片 = 86%，照片是**一层被压淡的清晰影像**，
// 不是一片糊的色块 —— 这正是用户要的效果。
const GLASS_MIN = 0.86;
function applyGlass(amount) {
  const root = document.documentElement;
  // ⚠ 必须先清掉上一次写进去的值再读。不清的话第二次读到的是自己写的
  //   rgba(...)，拿去再乘一次透明度 —— 越拖越透，最后整页透明。
  GLASS_VARS.forEach(v => root.style.removeProperty(v));
  root.classList.toggle("bg-glass", amount > 0);
  if (amount <= 0) return;
  // 把 0~100 整段映射到 1.0~GLASS_MIN。
  // ⚠ 不能写成 max(GLASS_MIN, 1 - amount/100)：那样 55% 和 75% 两档会被
  //   同一个下限压成一样，滑块后半段变成死区。
  const a = 1 - (amount / 100) * (1 - GLASS_MIN);
  GLASS_VARS.forEach(v => {
    // ⚠ --chip-bg 的默认值是 `var(--bg)` 这个**字面量**，不是解析好的颜色。
    //   getPropertyValue 拿回来的就是那串文本，toRgba 认不出来只能原样返回，
    //   结果就是这块永远实心。所以它得绕一道，去取 --bg 的真颜色。
    // 这几个的默认值都是 `var(--别的)` 这种**字面量**，不是解析好的颜色。
    // getPropertyValue 拿回来的就是那串文本，toRgba 认不出来只能原样返回 ——
    // 结果就是这块永远实心。所以它们得绕一道去取真正那个变量的颜色。
    const SRC = {"--chip-bg": "--bg", "--chip-line": "--line", "--input-bg": "--card"};
    const base = cssVar(SRC[v] || v, "");
    if (!base) return;
    // 卡片、顶栏用主透明度；
    // ⚠ --soft/--soft2 是**叠在卡片上面**的次级面板（AI 分析框、表格条纹…）。
    //   要是也按同一个透明度来，两层相乘会变得几乎不透（照片一点看不见），
    //   和外面那张半透明的卡片对不上。所以它们用更低的透明度来抵消叠加。
    //
    // --chip-bg 正相反，要**比卡片更实**：胶囊按钮/标签底下就是字，
    //   透过头了按钮就找不着了（它是靠底色立住的，又没有边框）。
    //   · --soft/--soft2 是叠在卡片上面的次级面板，用更低的透明度抵消叠加
    //   · --chip-bg（ghost 按钮的底）要比卡片实一点，它是靠底色立住的
    //   · --chip-line 是输入框那圈线：完全透明底上，线得够看得见
    //   · --input-bg 只给一层**极淡**的底（不是深色填充），
    //     让输入框在玻璃卡片上还能认出"这里能填字"
    const K = {"--soft": 0.55, "--soft2": 0.55, "--chip-bg": 0.6,
               "--chip-line": 0.18, "--input-bg": 0.78};
    const k = K[v] === undefined ? 1 : K[v];
    root.style.setProperty(v, toRgba(base, 1 - (1 - a) * k));
  });
}

/** 把配色块里那些 #fff / #fffdf7 换算成带透明度的 rgba。
 *  认不出来就原样返回 —— 顶多是这一处不透，不该把整个变量弄坏。 */
function toRgba(c, alpha) {
  const s = String(c || "").trim();
  let r, g, b;
  if (s[0] === "#") {
    let h = s.slice(1);
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    if (h.length < 6) return s;
    const n = parseInt(h.slice(0, 6), 16);
    if (isNaN(n)) return s;
    r = (n >> 16) & 255; g = (n >> 8) & 255; b = n & 255;
  } else {
    const m = s.match(/(\d+(?:\.\d+)?)\D+(\d+(?:\.\d+)?)\D+(\d+(?:\.\d+)?)/);
    if (!m) return s;
    r = +m[1]; g = +m[2]; b = +m[3];
  }
  return `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
}

// 跟随系统：系统切深浅时自动跟（只在 theme=auto 时生效）
if (window.matchMedia) {
  const mq = matchMedia("(prefers-color-scheme: dark)");
  const onSys = () => {
    if ((APPCFG || {}).theme === "auto" && APPCFG) { applyTheme(); redrawAll(); }
  };
  mq.addEventListener ? mq.addEventListener("change", onSys) : mq.addListener(onSys);
}

function redrawAll() {
  Object.keys(charts).forEach(k => {
    try { charts[k].dispose(); } catch (e) {}
    delete charts[k]; delete chartTheme[k];
  });
  const cur = $$(".tabbody").find(s => !s.hidden);
  if (!cur) return;
  if (cur.id === "tab-bill" && BILL) renderBill();
  else if (cur.id === "tab-check" && CHECK) { renderCheckData(); renderCheckCharts(); }
  else if (cur.id === "tab-over" && BILL && CHECK && STOCK) renderOverview();
}

function chartOf(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  // DOM 重建过、或主题换过 → 旧实例作废
  if (!charts[id] || charts[id].getDom() !== el || chartTheme[id] !== CHART_THEME) {
    if (charts[id]) { try { charts[id].dispose(); } catch (e) {} }
    charts[id] = echarts.init(el, CHART_THEME);
    chartTheme[id] = CHART_THEME;
  }
  return charts[id];
}
function modal(title, html, onOk, icon) {
  // icon 可选：传 ICON 表里的线条图标名。不传就只有标题文字。
  $("#modalCard").innerHTML = `<h3>${
    icon ? `<span class="bi" data-icon="${icon}"></span>` : ""}${title}</h3>${html}
    <div class="modal-actions"><button class="btn ghost" id="m-cancel">取消</button>
    <button class="btn" id="m-ok">保存</button></div>`;
  $("#modal").hidden = false;
  $("#m-cancel").onclick = () => $("#modal").hidden = true;
  $("#m-ok").onclick = async () => { const r = await onOk(); if (r !== false) $("#modal").hidden = true; };
  $("#modal").onclick = e => { if (e.target === $("#modal")) $("#modal").hidden = true; };
  paintIcons($("#modalCard"));     // 标题里那个 .bi 得现补上，不然是个空方块
}

/** 问用户要一段文字（prompt 的替代品）。返回 Promise：确定→字符串，取消→null。
 *
 *  ⚠⚠ 为什么不能用 `window.prompt()`：
 *    **Electron 从 16 起把 prompt() 移除了**（官方 BREAKING CHANGE：
 *    "window.prompt() is no longer supported"），而本项目用的是 Electron 44。
 *    也就是说打包版里所有 prompt() 都是**点了没反应**（在浏览器里却正常）——
 *    用户报的「保存记法点击没反应」就是它，同一原因一共有 6 处。
 *    这类 bug 只在打包版出现，开发和测试都在浏览器里，所以一直没被发现。
 *
 *  ⚠ 别用 `confirm()` 也一样的原因 —— Electron 里 confirm 是**支持的**，
 *    所以那几处留着没问题；只有 prompt 必须换掉。
 *
 *  用法：
 *    const name = await askText({title:"给这笔记法起个名字", ph:"食堂"});
 *    if (name === null) return;        // 用户取消
 */
function askText(opts) {
  const o = opts || {};
  return new Promise(resolve => {
    let done = false;
    const finish = v => { if (!done) { done = true; resolve(v); } };
    const field = o.multi
      ? `<textarea id="ask-v" rows="4" placeholder="${esc(o.ph || "")}">${esc(o.value || "")}</textarea>`
      : `<input id="ask-v" value="${esc(o.value || "")}" placeholder="${esc(o.ph || "")}">`;
    modal(o.title || "请输入", `
      ${o.label ? `<div class="f"><label>${esc(o.label)}</label></div>` : ""}
      <div class="form"><div class="f" style="align-items:baseline">${field}</div></div>
      ${o.hint ? `<p class="mini" style="margin:8px 0 0">${o.hint}</p>` : ""}`,
      () => { const e = $("#ask-v"); finish(e ? e.value : ""); },
      o.icon);
    // 覆盖「取消」：原来它只是关掉弹窗，这里要让 await 拿到 null
    const cancel = $("#m-cancel");
    if (cancel) cancel.onclick = () => { finish(null); $("#modal").hidden = true; };
    // 点遮罩关掉也算取消
    $("#modal").onclick = e => {
      if (e.target === $("#modal")) { finish(null); $("#modal").hidden = true; }
    };
    const ok = $("#m-ok");
    if (ok) ok.textContent = o.ok || "确定";
    const el = $("#ask-v");
    if (el) {
      el.focus();
      if (el.select) el.select();
      // 单行框回车即确定（多行框留给 Ctrl+Enter 的老习惯）
      if (!o.multi) el.onkeydown = ev => { if (ev.key === "Enter") { ev.preventDefault(); finish(el.value); $("#modal").hidden = true; } };
    }
  });
}

/* 图表里的字号也得跟着字号设置走。
   ECharts 的 fontSize 只认数字（px），不吃 rem，所以在这儿手动换算：
   ckFs(11) 在 14px 基准下就是 11，调到 22 就变成 17。 */
const ckFs = px => Math.max(8, Math.round(px * ((Number(cfg("font_size", 14)) || 14) / 14)));

/* 图表色板 —— **从当前配色的主强调色推出来**，不再写死。
 *
 * 以前这里是两张死表：22 个 Flat-UI 饱和色（纯红 #e74c3c、纯蓝 #3498db、
 * 纯紫 #9b59b6…）+ 18 个兜底色。它们**换主题一动不动** ——
 * 界面是纸墨调子（赭金/青瓷/墨色），图表却是塑料色，
 * 看着就像从别的应用里抠过来贴上的。用户说的「老土」就是这个。
 *
 * 现在：拿主强调色的色相做起点，按黄金角铺开 12 个，
 * 饱和度和明度**锁在一个舒服的band里** —— 十几个颜色才像一家人，
 * 而不是十二种各自鲜艳的塑料。
 */
function hslOf(hex) {
  const s = String(hex || "").trim().replace("#", "");
  if (s.length < 6) return {h: 36, s: 50, l: 50};
  const n = parseInt(s.slice(0, 6), 16);
  if (isNaN(n)) return {h: 36, s: 50, l: 50};
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0;
  if (d) {
    if (mx === r) h = ((g - b) / d) % 6;
    else if (mx === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
  }
  h = Math.round(h * 60);
  if (h < 0) h += 360;
  const l = (mx + mn) / 2;
  return {h, s: Math.round(d ? d / (1 - Math.abs(2 * l - 1)) * 100 : 0), l: Math.round(l * 100)};
}
// ⚠⚠ **必须用逗号分隔，不能写成 `hsl(36 52% 46%)`。**
//   空格写法浏览器认（CSS Color 4），ECharts 首次渲染也能画出来 ——
//   因为它把字符串直接丢给 canvas。**可它内部那个颜色解析器是按逗号切的**，
//   高亮/重绘时拿到的是 ["36 52% 46%"] 这种长度 1 的数组，
//   判定「参数不是 3 段」→ 直接设成 rgba(0,0,0,0) 全透明。
//   表现：**图看着好好的，一点就整张没了**，只剩标签引线还活着。
//   这个坑 2.3.0 踩过，2.3.1 修回来。
const hslCss = (h, s, l) => `hsl(${Math.round((h % 360 + 360) % 360)}, ${Math.round(s)}%, ${Math.round(l)}%)`;

/** 同一个类别的颜色，带透明度。
 *  线条风要用：描边是实色，里面填一层很淡的同色。
 *  ⚠ 一样得用逗号 —— 见上面 hslCss 那段。 */
const colorOfA = (c, a) => colorOf(c).replace("hsl(", "hsla(").replace(")", `, ${a})`);

/** 扇区里那层**淡填充**要多淡 —— 深浅两套主题给的答案不一样。
 *
 *  ⚠ 「淡」是相对**底色**说的，不是相对某个固定数字。0.22 是照着浅色底
 *    （白卡片）配的：22% 的靛蓝压在白底上是一块清透的藕荷色。
 *    同一个 22% 压到深色卡片上，结果是 0.22×靛蓝 + 0.78×近黑 —— 一块
 *    几乎看不出色相的深灰。实测深色主题下八个扇区全糊成一个颜色，
 *    只能靠 2px 的描边区分，用户看到的是一圈"脏兮兮的暗环"。
 *    深色下要**更浓**才对：底色是暗的，颜色得自己亮起来。 */
const pieFill = c => colorOfA(c, document.documentElement.dataset.theme === "dark" ? 0.5 : 0.22);

/* ---- 图表色相环（2.3.7 重做）----
 *
 * ⚠ 2.3.0~2.3.6 用的是「主色 + 黄金角 137.5°」：能保证相邻两项分得开，
 *   **但不保证取到的是好看的颜色** —— 色相是跟着主色**整圈旋转**的，
 *   换一套配色就换一组脏色。实测「蓝粉」下餐饮被算成 340 的洋红、
 *   医疗 88 的橄榄绿、购物 224 的蓝，一张饼上同时出现橄榄绿和土黄，
 *   用户的原话是「混搭」「不好看」。而且它没法逐套调 —— 七套配色 × 深浅
 *   十四个组合，每个都得单独看一遍。
 *
 * 改成「固定色相环」：下面这 11 个色相是手挑的，**刻意跳过 25°~75°**
 * 那段黄绿 / 土橙（AI 味和"土"感最重的一段）；顺序也打散过，
 * 相邻两项至少差 122°，不会撞色。**只让饱和度和明度跟着主题走**，
 * 于是七套配色共用同一组干净色相，深浅两态各自调浓淡。
 * 换主题时图表不再是"另一组颜色"，只是"同组颜色换了个浓淡"。 */
const HUE_RING = [78, 201, 323, 109, 231, 354, 139, 262, 12, 170, 293];

/* 常用类别在色环上的**位置**（下标，不是色相、更不是相对偏移）。
 * 「餐饮暖、交通蓝、医疗绿」这种直觉保留，但落点必须在上面那 11 个里。
 * 类别比色位多，所以有意让不常同时出现的两个共用一个色位
 * （饼图只画前 8 大项，撞上的概率很低）。
 * 没列在这里的自建类别走哈希兜底 —— 兜底**也只在这 11 个里挑**。 */
const CAT_HUE = {
  "餐饮": 8, "人情": 8,                    // 珊瑚 25
  "零食": 5,                               // 红 354
  "饮料": 2, "服饰": 2,                    // 玫瑰 323
  "周边": 10, "游戏": 10,                  // 洋红 293
  "学习": 7, "理财": 4,                    // 紫 262 / 靛 231
  "购物": 4,                               // 靛 231
  "生活": 3, "生活费": 3,                  // 绿 109
  "医疗": 6, "兼职": 6,                    // 翠 139
  "交通": 1, "奖学金": 1,                  // 天蓝 201
  "通讯": 9, "日用品": 9, "其他收入": 9,   // 青 170
  "娱乐": 0,                               // 黄绿 78
};

/** 类别 → 颜色。**同一个类别在哪儿都是同一个颜色**（颜色不落盘，零迁移成本）。
 *
 *  ⚠ 「其他」和「结余」是特例，都不走色环：
 *    · 其他 / 其余 N 项 —— 中性灰。它是兜底桶，不该跟真类别抢注意力。
 *    · 结余 —— 低饱和的中性色。2.3.7 起它进了收入饼图，而且一进就是八成
 *      （实测 2826.93 / 3427.44），给它一个饱和的颜色等于把整张图染成一块。
 *      低饱和同时在说一件事：**这笔钱不是挣来的**。 */
const colorOf = c => {
  const s = String(c || "?");
  const base = hslOf(cssVar("--blue", "#a9762b"));
  const dark = document.documentElement.dataset.theme === "dark";
  if (s === "结余") return hslCss(base.h, 14, dark ? 58 : 50);
  if (s === "其他" || s === "其他收入" || /^其余 \d+ 项$/.test(s)) {
    return cssVar("--mut", "#8891a0");
  }
  let i = CAT_HUE[s];
  if (i == null) {
    let h = 0;
    for (let n = 0; n < s.length; n++) h = (h * 31 + s.charCodeAt(n)) >>> 0;
    i = h % HUE_RING.length;
  }
  // 饱和度和明度**不跟着主色走**：主色是强调色，可以很浓；
  // 一组分类色要的是清爽，浓了就成了荧光笔。
  // ⚠ 深色下饱和度**不能低**：底色本来就暗，色相再淡就彻底看不出来，
  //   八个扇区会糊成同一块灰（实测踩过，见 pieFill 那段）。
  //   深色 48 / 浅色 46 看着接近，效果差得远 —— 一个是在暗底上"点亮"，
  //   一个是在白底上"压住"，本来就该往两个方向调。
  return hslCss(HUE_RING[i % HUE_RING.length], dark ? 48 : 46, dark ? 63 : 46);
};
// 类别以库里的 cat 表为准（设置页可增删改排序），这里是拿不到数据时的兜底
const EXP_CATS_FALLBACK = ["餐饮","零食","饮料","服饰","日用品","购物","交通","通讯","学习","娱乐","游戏","周边","医疗","生活","人情","理财","其他"];
const INC_CATS_FALLBACK = ["生活费","兼职","奖学金","报销","返现","红包","二手","退款","理财","其他收入"];
const expCats = () => (BILL && BILL.cats && BILL.cats.exp && BILL.cats.exp.length) ? BILL.cats.exp : EXP_CATS_FALLBACK;
const incCats = () => (BILL && BILL.cats && BILL.cats.inc && BILL.cats.inc.length) ? BILL.cats.inc : INC_CATS_FALLBACK;
// 资金 / 账户类型。**可配置** —— 设置在「设置 → 数据 → 资金类型」。
// 这里这份只是兜底（后端没给、或者还没加载出来时用）。
const PAYS_FALLBACK = ["微信","支付宝","现金","农业银行卡","农商银行卡"];
const pays = () => {
  const v = cfg("pays", []);
  return (Array.isArray(v) && v.length) ? v : PAYS_FALLBACK;
};
function catSelect(cur) {
  return `<select id="f-cat">
    <optgroup label="── 收入 ──">${incCats().map(c=>`<option${cur===c?" selected":""}>${c}</option>`).join("")}</optgroup>
    <optgroup label="── 支出 ──">${expCats().map(c=>`<option${cur===c?" selected":""}>${c}</option>`).join("")}</optgroup>
  </select>`;
}

/* ---------------- 标签切换 ---------------- */
function switchTab(name) {
  $$(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tabbody").forEach(s => s.hidden = s.id !== "tab-" + name);
  // 数据已在、而且这期间没有别处改动过 → 直接渲染（秒开）；
  // 缺数据、或者被标脏了 → 重新拉一次
  if (name === "over") {
    if (BILL && CHECK && STOCK && !isDirty("over")) renderOverview(); else loadOverview();
  } else if (name === "bill") {
    if (BILL && !isDirty("bill")) renderBill(); else loadBill();
  } else if (name === "check") {
    if (CHECK && !isDirty("check")) {
      if (!$("#ck-kpis")) checkSkeleton();
      renderCheckData();
      renderCheckCharts();
    } else loadCheck();
  } else if (name === "stock") {
    if (STOCK && !isDirty("stock")) renderStock(); else loadStock();
  } else if (name === "todo") {
    if (STOCK && !isDirty("stock")) renderTodoPage(); else loadTodoPage();
  } else if (name === "note") {
    if (NOTES && !isDirty("note")) renderNotes(); else loadNotes();
  } else if (name === "essay") {
    if (NOTES && !isDirty("note")) renderEssay(); else loadEssay();
  } else if (name === "memory") {
    // ⚠ 必须**先拉历史再画**。2.4.1 之前这里直接 renderMemory()，
    //   而消息只在内存里 —— 于是"切出去再回来对话就没了"。
    //   现在消息在库里，每次进这个页面重新读一遍（别的窗口问过的也能看见）。
    (async () => { await loadMemory(); renderMemory(); })();
  } else if (name === "set") {
    loadSettings();
  }
  setTimeout(resizeCharts, 30);
}
$$(".tab").forEach(btn => btn.onclick = () => switchTab(btn.dataset.tab));

/* ================================================================
   ① 总览
================================================================ */
async function loadOverview() {
  const [b, c, s, a, cfg, ck] = await Promise.all([
    get("/api/bill"), get("/api/check"), get("/api/stock"),
    get("/api/ai/analysis"), get("/api/ai/config"),
    // ⚠ 时钟接口**顺手把累计工时记了一笔**（后端 clock_state 里那段），
    //   所以哪怕不开桌面小时钟，只要打开过总览页，工时就在累计。
    //   漏了这一次调用的话，等级永远停在 Lv.1。
    get("/api/clock")]);
  if (ck && ck.ok && ck.data) CLOCK_TOTAL_MIN = ck.data.total_min || 0;
  if (!b.ok || !c.ok || !s.ok) return toast("加载失败", true);
  BILL = b.data; CHECK = c.data; STOCK = s.data;
  clearDirty("over", "bill", "check", "stock"); syncStamp();
  if (a.ok) AIANALYSIS = a.data;
  if (cfg.ok) AICFG = cfg.data;
  idle();
  renderOverview();
}
function monthNameOf(t) { return dateToMonthName(t); }
function curCheckMonth() {
  const t = todayStr();
  return CHECK.months.find(m => m.name === monthNameOf(t)) || CHECK.months[CHECK.months.length - 1];
}
function todayDayObj() {
  const m = curCheckMonth();
  return m ? m.days.find(d => d.date === todayStr()) : null;
}
// 总览顶部那排数字。**抽成单独函数**，是为了打完勾能就地重算：
// 以前快速打卡只换按钮文字，上面的完成度还停在旧值，得切走再切回才对，
// 看着就像「不刷新」。
function heroStats() {
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
  const restock = STOCK.overview.reduce((a, v) => a + v.restock, 0);
  const todayExp = (BILL.day_exp || {})[todayStr()];
  // 牛马时钟（2.3.6）：填了日薪才算，没填这一格整块不出现 ——
  // 不留一个「—」在那儿占地方。
  // ⚠ 2.4.1：这里原来自己算了一遍（`从今天 0 点算到现在`）——
  //   早上七点打开会显示"已经赚了七小时"。现在统一走 clockEarned()，
  //   跟总览卡片、桌面小时钟是同一套口径。三处各算一遍是这套代码的老毛病。
  let clock = "";
  if (clockOn()) {
    clock = `<div class="hs"><div class="k">今天已赚（时薪 ${money(clockHourly())}）</div>
      <div class="v">${money(clockEarned())}</div></div>`;
  }
  void restock;
  return `
      <div class="hs"><div class="k">今日核心完成度</div><div class="v">${ts ? Math.round(ts.core*100)+"%" : "还没记"}</div></div>
      <div class="hs"><div class="k">本月核心完成率</div><div class="v">${Math.round(mCore*100)}%</div></div>
      <div class="hs"><div class="k">本月平均睡眠</div><div class="v">${mo ? avgSleepOf(mo) : "—"}</div></div>
      <div class="hs"><div class="k">今日支出</div><div class="v">${todayExp ? money(todayExp) : "—"}</div></div>
      ${clock}`;
}

// 只把顶部那排数字换掉，不动整页（保住滚动位置和你正在填的东西）
function refreshHeroStats() {
  const box = $("#hero-stats");
  if (box) box.innerHTML = heroStats();
}

/* 总览页六张卡：**先做成字典，再按顺序取**。
   以前是一次数组字面量直接铺出来，顺序是写死的 —— 想排序就没处下手。
   现在顺序由 cardOrder() 决定（设置里能拖能按箭头），
   这里只负责「每一张长什么样」。 */
/* ---- 牛马时钟的算法（2.4.1）----
 *  ⚠ 跟后端 clock_state() 是**同一套口径**，两边算出来必须一样。
 *    这里在前端算，是因为总览页刷新时要**秒级跟着走**（后端返回的是
 *    上一次请求的瞬间值，用它画出来的数字会一跳一跳）。
 *    上班时间默认 09:00 —— 原来的算法是从今天 0 点算起，
 *    早上七点打开会显示"已经赚了七小时"。 */
function clockStartMin() {
  const m = /^(\d{1,2})\s*[:：]\s*(\d{1,2})/.exec(String(cfg("clock_start", "09:00")));
  if (!m) return 9 * 60;
  const h = Math.min(23, +m[1] || 0), mi = Math.min(59, +m[2] || 0);
  return h * 60 + mi;
}
function clockHourly() {
  const w = +cfg("clock_wage", 0) || 0, h = +cfg("clock_hours", 8) || 8;
  return h > 0 ? w / h : 0;
}
function clockDoneMin() {
  const total = (+cfg("clock_hours", 8) || 8) * 60;
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
  return Math.max(0, Math.min(nowMin - clockStartMin(), total));
}
function clockEarned() { return clockHourly() * clockDoneMin() / 60; }
function clockHourNo() {
  const total = (+cfg("clock_hours", 8) || 8) * 60;
  const d = clockDoneMin();
  return d >= total ? Math.round(total / 60) : Math.floor(d / 60) + 1;
}
function clockOn() { return (+cfg("clock_wage", 0) || 0) > 0; }

/* 等级表。⚠ 跟 server.py 的 CLOCK_LEVELS **必须一模一样** ——
 * 改一处就要改两处。之所以前端也留一份，是因为总览页要在**没有网络往返**
 * 的情况下立刻画出等级（后端那份只在 /api/clock 回来时才知道）。
 * clockTotMin 是后端每次问时钟时顺手记下来的累计分钟，缓存在这儿。 */
const CLOCK_LEVELS = [[0, "实习生"], [20, "试用期"], [60, "正式工"], [140, "熟练工"],
                      [300, "老员工"], [600, "骨干"], [1000, "卷王"], [2000, "牛马之王"]];
let CLOCK_TOTAL_MIN = 0;
function clockLevelOf(min) {
  const h = min / 60;
  let idx = 0;
  for (let i = 0; i < CLOCK_LEVELS.length; i++) {
    if (h >= CLOCK_LEVELS[i][0]) idx = i; else break;
  }
  const lo = CLOCK_LEVELS[idx][0];
  const hi = idx + 1 < CLOCK_LEVELS.length ? CLOCK_LEVELS[idx + 1][0] : lo;
  return {lv: idx + 1, name: CLOCK_LEVELS[idx][1],
          pct: hi > lo ? Math.max(0, Math.min(1, (h - lo) / (hi - lo))) : 1,
          leftMin: hi > lo ? Math.round((hi - h) * 60) : 0};
}
const CLOCK_LV = {get lv() { return clockLevelOf(CLOCK_TOTAL_MIN).lv; },
                  get name() { return clockLevelOf(CLOCK_TOTAL_MIN).name; }};

/* ---- 支出环比（2.4.7）------------------------------------------------
   口径是**用户自己定的**（2026-09-20）：
     · 两个基准都要：①上一个**自然月**（整月比整月）
                     ②上月**同期**（本月 1 号到今天 vs 上月 1 号到同一天）
       ① 在月中看会显得偏低（9 月才过一半去比 8 月整月），所以必须有 ② 兜着。
     · **上涨超过 20% 才报**。跌了不报（用户只要涨的）。
   ⚠ 全部在前端从 BILL.records 现算，不新增后端字段 —— 少一个「同一个数算两遍」的地方。 */
const MOM_THRESHOLD = 0.20;

/** 把 "2026-09-20" 当**本地日期**解析。
 *  ⚠ 不能直接 new Date("2026-09-20") —— 那按 UTC 解析，在 UTC+8 会变成 9 月 20 日 08:00，
 *    取 getDate() 拿到的是本地 20 号没错，但减一个月再取月末时会整体偏一天，
 *    「上月同期」就会少算或多算一天。这类差一天最难发现，所以一开始就拆开构造。 */
function localDate(iso) {
  const [y, m, d] = String(iso || "").split("-").map(Number);
  return (y && m && d) ? new Date(y, m - 1, d) : null;
}

function ymOf(iso) { return String(iso || "").slice(0, 7); }

/** 本月支出：自然月 + 上月同期，两个都算。
 *  返回 {cur, prevFull, prevSame, pctFull, pctSame, partial}
 *  pct* 为 null = 上期没有可比数据（那个月没记账 / 是第一个月），**不是 0%**。
 *  ⚠ 这个区分很重要：「没有可比数据」说成「+0%」就是在编数字。 */
function monthlySpendCompare(today) {
  if (!BILL || !BILL.records) return null;
  const t = today || todayStr();
  const cur = t.slice(0, 7);                     // "2026-09"
  const d = localDate(t);
  if (!d) return null;
  const y = d.getFullYear(), m0 = d.getMonth();  // m0 是 0-based
  const day = d.getDate();
  const prevDate = new Date(y, m0 - 1, 1);
  const prev = `${prevDate.getFullYear()}-${String(prevDate.getMonth() + 1).padStart(2, "0")}`;
  // 上个月的最后一个自然日（下个月 0 号），以及**本月**最后一个自然日。
  const prevLastDay = new Date(y, m0, 0).getDate();
  const curLastDay = new Date(y, m0 + 1, 0).getDate();

  let curSum = 0, prevFull = 0, prevSame = 0, curDays = new Set();
  let curN = 0, prevN = 0;
  for (const r of BILL.records) {
    const amt = +r.exp || 0;
    if (amt <= 0) continue;
    const ym = ymOf(r.date);
    if (ym === cur) {
      curSum += amt; curN++; curDays.add(+String(r.date).slice(8, 10));
    } else if (ym === prev) {
      prevFull += amt; prevN++;
      // 同期：上月 1 号到**和今天同一个日号**（上月没 31 号就截到月末）
      if (+String(r.date).slice(8, 10) <= Math.min(day, prevLastDay)) prevSame += amt;
    }
  }
  const r2 = n => Math.round(n * 100) / 100;
  const pct = (a, b) => (b > 0 ? (a - b) / b : null);
  // partial = **本月还没走完** → 这时整月比整月不公平，要拿同期兜着。
  // ⚠ 这里必须用**本月**的天数判断，不能用上月的。原来写的是
  //   `day < prevLastDay` —— 9 月 30 天、8 月 31 天，于是 9/30（本月底，
  //   已经是完整一个月）会被判成「月中」，月末平白多显示一句「较上月同期」。
  //   差一天这类错最难发现，所以专门有一条测试钉它。
  const partial = day < curLastDay;
  return {cur: r2(curSum), prevFull: r2(prevFull), prevSame: r2(prevSame),
          pctFull: pct(curSum, prevFull), pctSame: pct(curSum, prevSame),
          partial, curN, prevN};
}

/** 「本月支出」那张卡的副标题：预算 + （够 20% 才出现的）环比。 */
function momSub(monthBudget, mom) {
  const parts = [monthBudget ? `预算 ${money(monthBudget)}` : "未设预算"];
  const fmt = p => (p >= 0 ? "+" : "") + Math.round(p * 100) + "%";
  if (mom) {
    // 只在**上涨且过阈值**时报。跌了不报 —— 用户明确只要涨的。
    if (mom.pctFull !== null && mom.pctFull >= MOM_THRESHOLD)
      parts.push(`比上月 ${fmt(mom.pctFull)}`);
    // 月中时「同期」更公平，单独标出来，免得跟上面那个整月数字打架
    if (mom.partial && mom.pctSame !== null && mom.pctSame >= MOM_THRESHOLD)
      parts.push(`较上月同期 ${fmt(mom.pctSame)}`);
  }
  return parts.join(" · ");
}

function cardHtmlMap(b, monthExp, monthBudget, dreamN, td, restock, bad, todoOpen, overdueTodo, mom) {
  return {
    bal: kpi("结余", money(b.bal), b.bal >= 0 ? "b" : "r", NEUTRAL,
             `总收入 ${money(b.inc)} － 支出 ${money(b.exp)}`, "bill"),
    avail: kpi("可动用资金", money(b.avail), b.avail >= 0 ? "b" : "r", NEUTRAL,
               `待付尾款 ${money(b.pending)}`, "bill"),
    budget: kpi("本月支出", monthExp != null ? money(monthExp) : "—",
                (monthBudget != null && monthExp > monthBudget) ? "r" : "b",
                (monthBudget != null && monthExp > monthBudget) ? RED : NEUTRAL,
                // ⚠ 这里原来是 `预算 ¥x` 或 `未设预算`。环比（2.4.7）挂在同一个副标题上，
                //   不再单起一张卡 —— 它说的就是这一格数字的事，分开摆会让人两个数对着看。
                momSub(monthBudget, mom), "bill"),
    dream: kpi("今日梦境", dreamN ? `${dreamN} 个` : "没做梦", "b", NEUTRAL,
               (td && td.M) || "未记录", "check"),
    stock: kpi("待补货", restock + " 件", restock ? "a" : "b", restock ? AMBER : NEUTRAL,
               `过期+临期 ${bad} 件`, "stock"),
    todo: kpi("待办未完成", todoOpen + " 件", todoOpen > 5 ? "a" : "b",
              todoOpen ? AMBER : NEUTRAL, `逾期 ${overdueTodo.length} 件`, "stock"),
    // 牛马时钟（2.4.1）。
    // ⚠ 没填日薪时**这里返回空字符串**，不是"显示成 ¥0.00"——
    //   渲染处是 `CARD_HTML[k] || ""`，空串就等于不占位。
    //   为什么改成在这里空、而不是像以前那样把它从 cardOrder() 里滤掉：
    //   滤掉之后它在**设置页的卡片列表里也不存在**，用户从没见过这张卡、
    //   也就永远不知道要先填日薪（2.4.8 修的死锁，见 cardOrder 那段注释）。
    // 2.4.7：用户说它「没有存在感」，所以补了今日进度（干了多久/百分比）。
    clock: clockOn() ? kpi("今天已赚", money(clockEarned()), "g", "var(--green)",
                           clockSub(), "set") : "",
  };
}

/** 牛马时钟那张卡的副标题。
 *  目的：让「今天已经干到哪了」一眼看出来，而不是只有一个金额。
 *  ⚠ 全部由 clockDoneMin() / clockHourly() 现算，跟卡片主数字**同源** ——
 *    另起一套算法就会变成「同一个数算两遍」（交接文档 C 类那个慢性病）。
 *  ⚠ 2.4.9 缩短成**一行**：.kpis 降到 152px 之后 7 张卡能在宽屏排成一行，
 *    但每张卡就窄了 —— 原来那两行（含 <br>）在这张最密的卡里当场折行，
 *    把整排卡撑高。副标题就该一行，进度条也省掉：
 *    「Lv.3 正式工 · 55% · 今日 4.4/8h」这一句已经把该说的说完了。 */
function clockSub() {
  const total = (+cfg("clock_hours", 8) || 8) * 60;
  const done = clockDoneMin();
  const pct = total > 0 ? Math.max(0, Math.min(100, Math.round(done / total * 100))) : 0;
  const h = m => (m / 60).toFixed(1).replace(/\.0$/, "");
  const lv = CLOCK_LV;
  return `Lv.${lv.lv} ${lv.name} · ${pct}% · 今日 ${h(done)}/${h(total)}h`;
}
let CARD_HTML = {};

/** 卡片该按什么顺序排。
 *  设置里那个数组现在有两个身份：**哪些要显示** + **按什么顺序显示**。
 *    · 空数组 = 全显示、出厂顺序（老用户没动过设置，行为不变）
 *    · 非空   = 就按这个数组；里面没提到的（理论上不会有）补在最后，
 *               免得加了新卡片之后老设置里少一张、它就永远不显示 */
function cardOrder() {
  /* ⚠ 关于「没填日薪时的牛马时钟」（2.4.8 改）：
     原来是在**这里**就把 clock 从列表里滤掉 —— 于是它不只是"总览页不显示"，
     而是**在设置页那张卡片列表里也不存在**。结果：用户从没见过这张卡，
     也就永远不知道要先去填日薪。他自己想不起来有这么个功能。
     现在改成：**排序里一直留着 clock**，只是「没填日薪时渲染不出内容」
     （CARD_HTML.clock 为空 → 总览页自然不占位，不会摆一个 ¥0.00）。
     这样设置页那份列表能看见它、可以勾选，用户也就找得到了。 */
  const all = OVER_CARDS.map(([k]) => k);
  // 2.3.3 起顺序单独存在 overview_order 里（六个键的完整排列）。
  // 为什么不能拿 overview_cards 当顺序：那个数组是「哪些要显示」，
  // 关掉一张卡它就从数组里没了 —— 再打开时只能补到最后，卡会莫名其妙
  // 跑到队尾。分开存之后，关掉再打开还在原来那一格。
  const saved = (cfg("overview_order", []) || []).filter(k => all.includes(k));
  if (saved.length === all.length) return saved;
  /* ⚠ 原来这里只看 `saved` 的长度对不对，于是有个**死锁**（2.4.8 修的）：
     某张卡**当时不可用**时（就是没填日薪的牛马时钟），它会从 `overview_order`
     里消失；等它重新可用（填了日薪），`saved.length` 永远 ≠ `all.length`，
     于是走下面那条 concat —— 而列表里没有 clock，**它永远补不回来**。
     用户唯一出路是去设置里手动勾上，可他又不知道要勾（界面上从来没见过它）。

     ⚠⚠ 但**不能无差别地"把不在列表里的卡补回去"** ——
       用户**故意关掉**的卡也不在列表里，那样一补设置就失效了。
       我第一版就是这么写的，验证时当场暴露：
       「关掉『今日梦境』」那一组它被重新加回来了（❌ 设置失效）。
     所以只在**「这张卡刚变成可用」**时才补 —— 判据是 `availableNow`：
       它现在在 `all` 里（可用），但用户设置里两边都没提到它，
       而且它**以前也不可能被用户选择**（那时它不可用）。
     逐个判断太绕，直接挑明：**目前只有 clock 这一个条件卡**。
     以后再加条件卡，往 CONDITIONAL_CARDS 里加一个键就行。
     普通卡（用户能随时开关的那种）一律不补，用户的开关说了算。 */
  const CONDITIONAL_CARDS = { clock: () => clockOn() };
  const userList0 = cfg("overview_cards", []) || [];
  const seen = new Set([...saved, ...userList0]);
  const revive = all.filter(k =>
    !seen.has(k) && CONDITIONAL_CARDS[k] && CONDITIONAL_CARDS[k]());
  const userList = userList0.filter(k => all.includes(k));
  if (saved.length) return saved.concat(revive);
  if (userList.length) return userList.concat(revive);
  // 两处都是空 = 用户从没设置过 → 全显示（含新加的卡）
  return all;
}

// ---- 总览页「今日快速打卡」按钮的显示与排序（2.3.3）----
// 和卡片同一套约定：quick_items 空 = 全显示，quick_order 是完整排列。
// 区别是打卡项**用户自己会增删**，所以顺序里认不出来的键直接丢掉，
// 新加的项补在最后 —— 不然加了一项，用户排的顺序就整个失效了。
function quickAllKeys() {
  return checkItems("core").filter(x => x.kind !== "derived").map(x => x.col);
}
function quickOrder() {
  const all = quickAllKeys();
  const saved = (cfg("quick_order", []) || []).filter(c => all.includes(c));
  return saved.length ? saved.concat(all.filter(c => !saved.includes(c))) : all;
}
function quickShow() {
  const all = quickAllKeys();
  const cur = (cfg("quick_items", []) || []).filter(c => all.includes(c));
  return cur.length ? cur : all;
}
