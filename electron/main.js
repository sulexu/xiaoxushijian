// 小煦拾简 · 桌面外壳（Electron）
// 职责：启动后端（隐藏控制台窗口）、开一个原生窗口加载它、退出时把后端一起收掉。
//
// 两种运行方式：
//   · 打包后：用随包的 server.exe（自带 Python，目标机器不需要装任何东西）
//   · 开发时：回退到 python server.py
//
// 数据目录：打包后 = exe 所在目录（把 exe 放进 D:\个人信息统计\ 就直接读到那三个 Excel）；
//          开发时 = 统计系统\ 的上级目录。
"use strict";
const _fs0 = require("fs");
const _path0 = require("path");
// 启动日志写在 exe 旁边，出问题时能直接看到走到哪一步了
const LOG = _path0.join(
  process.env.STATS_ROOT || _path0.dirname(process.execPath), "启动日志.txt");
function logLine(msg) {
  try { _fs0.appendFileSync(LOG, new Date().toLocaleString() + "  " + msg + "\n"); } catch (e) {}
}
try { _fs0.writeFileSync(LOG, ""); } catch (e) {}

logLine("进程启动；execPath=" + process.execPath);
logLine("electron=" + (process.versions.electron || "(无)") +
        "  ELECTRON_RUN_AS_NODE=" + (process.env.ELECTRON_RUN_AS_NODE || "(空)"));

if (!process.versions.electron) {
  // 被 ELECTRON_RUN_AS_NODE 拖进纯 Node 模式（本机全局环境变量）。
  // 打包后用户是双击 exe，没法靠 bat 清变量，只能自己重启一次。
  logLine("检测到纯 Node 模式，清掉该变量后重启自己");
  const env = Object.assign({}, process.env);
  delete env.ELECTRON_RUN_AS_NODE;
  try {
    require("child_process").spawn(process.execPath, [], { env, detached: true, stdio: "ignore" }).unref();
  } catch (e) { logLine("重启失败：" + e.message); }
  process.exit(0);
}

const { app, BrowserWindow, dialog, nativeTheme, Menu, ipcMain, shell,
        globalShortcut } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");

const PACKAGED = app.isPackaged;
// 打包后：exe 在 resources 旁边；server.exe 放在 resources 里
const APP_DIR = PACKAGED ? path.dirname(app.getPath("exe")) : path.join(__dirname, "..");
const RES_DIR = PACKAGED ? process.resourcesPath : path.join(__dirname, "..");
const SERVER_EXE = path.join(RES_DIR, "server.exe");
const SERVER_PY = path.join(RES_DIR, "server.py");

// 数据目录（放三个 Excel 的地方）：
//   1) 先看 exe 同层 —— 整个文件夹拷到哪都能用
//   2) 再看上一层 —— 把打包好的文件夹放进 D:\个人信息统计\ 时，数据就在上面一层
// 这样两种摆放都能自动认出来，不用手动配。
function findDataRoot(startDir) {
  const marks = ["每日打卡表.xlsx", "寝室部分物资清单.xlsx", "账单"];
  const looksLikeData = d => marks.some(m => fs.existsSync(path.join(d, m)));
  let d = startDir;
  for (let i = 0; i < 3; i++) {
    if (looksLikeData(d)) return d;
    const up = path.dirname(d);
    if (!up || up === d) break;
    d = up;
  }
  return startDir;
}
// 数据目录的「记住上次选的那个」文件。放在 userData 里（不是数据目录里）——
// 正是因为这个文件的作用就是「告诉你数据目录在哪」，它自己不能也住在
// 那个还没找到的目录里。
const ROOT_CFG = path.join(app.getPath("userData"), "数据位置.txt");

function looksLikeDataDir(d) {
  const marks = ["每日打卡表.xlsx", "寝室部分物资清单.xlsx", "账单", "小煦拾简.db"];
  return marks.some(m => fs.existsSync(path.join(d, m)));
}

/** 决定数据目录。装到 %LOCALAPPDATA% 之后，「从 exe 往上找三层」是永远
 *  找不到用户放在 D 盘的数据的 —— 所以找不到就得**开口问**，并把答案记下来。
 *  这一步不能省：不然后端会因为找不到数据而拒绝开机，装完就是一扇打不开的门。 */
async function resolveDataRoot() {
  if (!PACKAGED) return path.dirname(path.join(__dirname, ".."));
  // ① 免安装版摆法：数据就在 exe 旁边（或往上三层）→ 直接用，一个字都不用问
  const near = findDataRoot(path.dirname(app.getPath("exe")));
  if (looksLikeDataDir(near)) return near;
  // ② 上次用过的那个
  try {
    const saved = fs.readFileSync(ROOT_CFG, "utf8").trim();
    if (saved && looksLikeDataDir(saved)) return saved;
  } catch (e) { /* 头一回，还没记过 */ }
  // ③ 只在「文档」底下碰一碰 —— **不写死盘符**
  //    ⚠ 这里原来还探过 "D:\个人信息统计"、"E:\个人信息统计"。
  //      那是我自己开发时用的路径，被原样打进了发给别人的安装包里。
  //      别人电脑上当然没有，白探一次；更不该的是：那是我的文件夹名。
  const docs = app.getPath("documents");
  for (const guess of [path.join(docs, "个人信息统计")]) {
    if (looksLikeDataDir(guess)) {
      saveRoot(guess);
      return guess;
    }
  }
  // ④ 一个都没找到 —— **问一次，别再默默建一个新的**。
  //
  //   ⚠ 2.4 改的就是这一步。原来是「没得可挑就不要挑」，直接
  //     `mkdir 文档\小煦拾简` + 建空库 + 记下来，一声不吭。
  //
  //     那个决定对**头一次用**的人是对的，但对**从别的版本换过来**的人是灾难：
  //     用户 2026-09-18 就是这么中招的 —— 他一直在用放在 D:\个人信息统计
  //     旁边的那版（那种装法下数据目录就是程序自己的上一级），装了安装版之后
  //     这边找不到，于是在文档里新建了一个空库。他看到的账单 0 条、物资 0 行，
  //     换了谁都会说「我数据没了」。
  //
  //     而"数据在哪"这件事，**程序是问得到的**，只是原来没问。
  //     2.0 那次把这个框删掉是因为它当时**答不上来**：
  //     「没找到你的数据文件夹，你想选哪个？」—— 头一次用的人手里根本没有
  //     "数据文件夹"这个概念，点哪个都是猜，而且它还会在 app ready 之前调
  //     dialog 直接抛异常，表现成「启动失败」。
  //
  //     现在两个问题都解决了：ready 之后才调（main() 里就是这么排的），
  //     而且**选项本身是可回答的** —— 有数据的人知道该指哪儿，没数据的人
  //     一眼就知道该选"建个空的"。多花三秒，换掉"数据没了"这三个字。
  const picked = await askWhereIsData();
  if (picked) { saveRoot(picked); return picked; }

  // 用户在框里选了「不用了，建个空的」——或者框弹不出来（无头/异常）时的兜底
  const fresh = path.join(docs, "小煦拾简");
  try {
    fs.mkdirSync(fresh, { recursive: true });
  } catch (e) {
    logLine("建数据目录失败：" + e.message + " —— 交给后端兜底");
  }
  saveRoot(fresh);
  return fresh;
}

/** 「你的数据在哪？」—— 只在**一个都没找到**的时候问一次。
 *
 *  返回用户选中的目录；返回 null 表示"就建个新的吧"。
 *  ⚠ 这个函数**保证不抛**：它是在启动路径上的，抛了就是"打不开软件"，
 *    而"打不开"比"数据指错地方"更难查（见 E5 那个坑）。 */
async function askWhereIsData() {
  if (!dialog || !dialog.showMessageBox) return null;
  for (;;) {                       // 选错了就再来一次，不把用户卡死
    let r;
    try {
      r = await dialog.showMessageBox({
        type: "question",
        title: "小煦拾简 · 第一次在这台电脑上运行",
        message: "没找到你以前的数据",
        detail: "如果你以前用过（比如一直在用免安装版、或者自己挪过文件夹），"
              + "数据就在某个文件夹里 —— 点「选一个文件夹」指给我。\n\n"
              + "头一次用就直接点「建一个空的」。",
        buttons: ["选一个文件夹…", "建一个空的", "先退出"],
        defaultId: 0, cancelId: 2, noLink: true,
      });
    } catch (e) {
      logLine("问数据目录失败（"+e.message+"），按「建个空的」继续");
      return null;
    }
    if (r.response === 1) return null;                    // 建个空的
    if (r.response === 2) { app.quit(); return null; }    // 先退出
    let pick = null;
    try {
      const sel = await dialog.showOpenDialog({
        title: "选你以前的数据文件夹（里面有 小煦拾简.db 或那几本 Excel）",
        properties: ["openDirectory"],
      });
      if (sel && !sel.canceled && sel.filePaths && sel.filePaths[0]) {
        pick = sel.filePaths[0];
      }
    } catch (e) { logLine("选文件夹失败：" + e.message); }
    if (!pick) continue;                                  // 取消了 → 回到上一个框
    if (looksLikeDataDir(pick)) {
      logLine("数据目录由用户指定：" + pick);
      return pick;
    }
    // 选了个不像数据目录的地方 —— 说清楚哪里不对，别让他猜
    try {
      await dialog.showMessageBox({
        type: "warning",
        title: "这个文件夹里没有数据",
        message: "这个文件夹看起来不是数据文件夹",
        detail: pick + "\n\n"
              + "里面应该至少有：小煦拾简.db、每日打卡表.xlsx、"
              + "寝室部分物资清单.xlsx、账单 这几样里的一样。\n\n"
              + "提示：免安装版的数据就在程序文件夹**旁边**；"
              + "如果你之前把整个「个人信息统计」文件夹放在 D 盘，那就是它。",
        buttons: ["知道了"], noLink: true,
      });
    } catch (e) { /* 弹不出来就算了，回到上一个框 */ }
  }
}

function saveRoot(dir) {
  try {
    // ⚠ 先确保目录在。`%APPDATA%\小煦拾简` 正常情况由 Electron 建好，
    //   但**别指望它** —— writeFileSync 到不存在的目录会抛，而这里
    //   原来是 `catch {}` 一吞了事：文件没写成，也没有任何痕迹，
    //   表现是「每次开机都重新决定一遍数据目录」。自检把这条抓出来了。
    fs.mkdirSync(path.dirname(ROOT_CFG), { recursive: true });
    fs.writeFileSync(ROOT_CFG, dir, "utf8");
  } catch (e) {
    logLine("记数据目录失败（下次会重新决定）：" + e.message);
  }
}

// ⚠ 这一行**必须留着**。上次改的时候把原来的 `const DATA_ROOT = ...` 删了、
// 新的 `let` 又没插进来，于是 DATA_ROOT 成了「用了但从没声明」的变量 ——
// `node --check` 只查语法，这种错它一概看不见，一路打包出去，
// 用户双击就是一句「DATA_ROOT is not defined」。
// 所以现在有一道 `_外壳自检.js`，是真把这文件跑起来，不是只查语法。
let DATA_ROOT = null;      // 由 resolveDataRoot() 在 app ready 之后定下来

const PORT = process.env.STATS_PORT || "8765";
const URL = `http://127.0.0.1:${PORT}`;
let back = null;
let win = null;

function serverAlive() {
  return new Promise(resolve => {
    http.get(URL + "/api/bill", res => { res.resume(); resolve(true); })
      .on("error", () => resolve(false));
  });
}

function startServer() {
  return new Promise((resolve, reject) => {
    // 上次异常退出可能留下一个后端进程（比如用任务管理器强杀过窗口），
    // 后端无状态、每次请求都重新读文件，直接复用即可
    serverAlive().then(alive => {
      if (alive) return resolve();
      spawnServer(resolve, reject);
    });
  });
}

function spawnServer(resolve, reject) {
  const env = { ...process.env, STATS_NOBROWSER: "1", STATS_PORT: PORT, STATS_ROOT: DATA_ROOT,
    // 「开机自启」要往注册表写的是**外壳 exe**，不是后端 server.exe ——
    // 后端自己认不出外壳在哪，所以在这里把路径递给它。
    STATS_LAUNCHER: PACKAGED ? process.execPath : "" };
  logLine("准备启动后端；DATA_ROOT=" + DATA_ROOT);
  if (fs.existsSync(SERVER_EXE)) {
    // 打包后的独立后端：自带 Python 运行时
    logLine("用独立后端 " + SERVER_EXE);
    back = spawn(SERVER_EXE, [], { cwd: APP_DIR, env, windowsHide: true });
  } else {
    // 开发模式：用系统 Python 跑源码
    logLine("用系统 Python 跑 " + SERVER_PY);
    back = spawn("python", [SERVER_PY], { cwd: RES_DIR, env, windowsHide: true });
  }
  back.on("error", e => { logLine("后端启动失败：" + e.message); reject(e); });
  back.on("exit", (c, s) => logLine("后端退出，code=" + c + " signal=" + s));

  // 轮询等后端就绪（打包后首次启动要解包，给到 40 秒）
  const limit = PACKAGED ? 40000 : 15000;
  const t0 = Date.now();
  const tryOnce = () => {
    http.get(URL + "/api/bill", res => { res.resume(); resolve(); })
      .on("error", () => {
        if (Date.now() - t0 > limit) reject(new Error("后端 40 秒内未就绪"));
        else setTimeout(tryOnce, 300);
      });
  };
  tryOnce();
}

/* ================================================================
   主题同步：让窗口自己的那点东西（按钮颜色、启动底色）跟着应用主题走
   ----------------------------------------------------------------
   ⚠ 主进程读不到浏览器里的 APPCFG（那是渲染进程的东西），
     所以直接读数据目录下的 _配置\settings.json —— 反正就在手边。
   ================================================================ */
function settingsFile() {
  try { return path.join(DATA_ROOT, "_配置", "settings.json"); } catch (e) { return ""; }
}

/** 读设置里的 theme；auto 则跟随系统 */
function readThemeFromSettings() {
  let t = "auto";
  try {
    const raw = fs.readFileSync(settingsFile(), "utf8");
    t = (JSON.parse(raw).theme) || "auto";
  } catch (e) { /* 没配过、或者还没建库 —— 跟随系统就行 */ }
  if (t === "auto") t = nativeTheme.shouldUseDarkColors ? "dark" : "light";
  return t === "dark" ? "dark" : "light";
}

/** 窗口按钮区的底色。透明 overlay 底下透出来的其实是应用顶栏。 */
const bgOf = () => "#00000000";

/** ⚠ 标题栏那三个窗口按钮（— □ ✕）画什么颜色。
 *
 *  这段注释原来是这么写的：
 *    「顶栏在浅色主题下是深色带、深色主题下反而更暗 —— 两种都得用白图标」
 *  在 2.0 改简约风**之前**这是对的：那时候 `.top` 是一条深蓝实心横幅。
 *  改成素卡之后 `.top{background:var(--card)}` —— **浅色主题下顶栏是白的**，
 *  白图标压在白顶栏上，三个按钮一个字都看不见。
 *  改设计的时候没人回来改这行，用户 2026-09-18 的截图就是它：
 *  右上角那一排细白线，浅色下完全消失。
 *
 *  和 `color-scheme:light`（见 static/style.css）、`titleBarOverlay` 的初始值
 *  是**同一类病**：机制都在、参数也传进来了，唯独少写了浅色那一半。 */
const symbolOf = mode => (mode === "dark" ? "#ffffff" : "#20242b");

/** 窗口按钮区的完整配置。初始建窗和后面切主题都走这一个函数 ——
 *  两边各写一份的话，早晚有一边忘记改（这正是这次出问题的原因）。 */
const titleBarOverlayOf = mode => ({
  color: bgOf(), symbolColor: symbolOf(mode), height: 44,
});

/** 全局快捷键（2.3.6）：在别的程序里按一下，把窗口叫到面前。
 *
 *  ⚠ 只做「叫窗口」这一件事。不做「直接弹随手记输入框」—— 那要处理
 *    「窗口还没建好就按了」「记完焦点还给谁」一串状态，而用户真正缺的
 *    是「不用去任务栏找它」。够用就行。
 *  ⚠ 注册失败（键被别的软件占了）不能拦着程序启动，只往日志写一行。 */
let HOTKEY_ON = null;

function registerHotkey() {
  try {
    if (!globalShortcut || !app.isReady()) return;
    if (HOTKEY_ON) { try { globalShortcut.unregister(HOTKEY_ON); } catch (e) {} HOTKEY_ON = null; }
    let acc = "";
    try { acc = String(JSON.parse(fs.readFileSync(settingsFile(), "utf8")).hotkey || ""); }
    catch (e) { /* 没配过就算了 */ }
    if (!acc.trim()) return;
    const ok = globalShortcut.register(acc, () => {
      try {
        const w = BrowserWindow.getAllWindows()[0];
        if (!w) return;
        if (w.isMinimized()) w.restore();
        w.show(); w.focus();
      } catch (e) { /* 窗口没了就算了 */ }
    });
    if (ok) { HOTKEY_ON = acc; logLine("全局快捷键已注册：" + acc); }
    else logLine("全局快捷键注册失败（可能被别的软件占用了）：" + acc);
  } catch (e) { logLine("全局快捷键出错：" + e.message); }
}

/* ---------------- 桌面小时钟（2.4.1） ----------------
 *
 * 用户要的：「和 springnote 一样做一个这种小窗口」—— 就是那种
 * 固定在桌面角落、一直显示今天赚了多少的小方块。
 *
 * 几个必须做对的地方：
 *   · position:"top-right" 是**相对屏幕**的，所以它不会挡住主窗口
 *   · 记忆位置：拖到哪儿下次就在哪儿（存一个很小的 JSON，不进数据库 ——
 *     这个位置是"这台电脑上的窗口状态"，不属于用户的数据）
 *   · 主窗口关了它就一起关（留着的话，程序退出了还有个孤儿窗浮在桌面上）
 */
let clockWin = null;
const CLOCK_POS = () => path.join(app.getPath("userData"), "时钟位置.json");

function clockBounds() {
  const { screen } = require("electron");
  let saved = null;
  try { saved = JSON.parse(fs.readFileSync(CLOCK_POS(), "utf8")); } catch (e) {}
  const W = 268, H = 158;
  if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
    // ⚠ 记的位置可能已经在屏幕外了（换显示器、拔了外接屏）——
    //   那样窗口会开在一个看不见的地方，用户以为"点了没反应"。
    try {
      const inside = screen.getAllDisplays().some(d => {
        const a = d.workArea;
        return saved.x > a.x - W + 60 && saved.x < a.x + a.width - 60
            && saved.y > a.y - 20 && saved.y < a.y + a.height - 40;
      });
      if (inside) return { x: saved.x, y: saved.y, width: W, height: H };
    } catch (e) { /* 拿不到屏幕信息就用默认位置 */ }
  }
  return { width: W, height: H, x: undefined, y: undefined };
}

function openClockWin() {
  if (clockWin && !clockWin.isDestroyed()) { clockWin.show(); clockWin.focus(); return; }
  const { BrowserWindow } = require("electron");
  const b = clockBounds();
  clockWin = new BrowserWindow({
    width: b.width, height: b.height, x: b.x, y: b.y,
    frame: false, transparent: true, resizable: false, maximizable: false,
    minimizable: false, fullscreenable: false, skipTaskbar: true,
    alwaysOnTop: true, hasShadow: false, show: false,
    title: "牛马时钟",
    webPreferences: { preload: path.join(__dirname, "preload.js"),
                      contextIsolation: true, nodeIntegration: false },
  });
  clockWin.setAlwaysOnTop(true, "floating");   // 压在普通窗口上面，但不抢焦点
  clockWin.loadURL(URL + "/static/clock.html");
  clockWin.once("ready-to-show", () => clockWin.show());
  const save = () => {
    try {
      if (clockWin && !clockWin.isDestroyed()) {
        const [x, y] = clockWin.getPosition();
        fs.writeFileSync(CLOCK_POS(), JSON.stringify({ x, y }), "utf8");
      }
    } catch (e) { /* 写不进去就算了，下次开在默认位置 */ }
  };
  clockWin.on("moved", save);
  clockWin.on("closed", () => { clockWin = null; });
  logLine("桌面小时钟已打开");
}

function closeClockWin() {
  try { if (clockWin && !clockWin.isDestroyed()) clockWin.close(); } catch (e) {}
  clockWin = null;
}

function unregisterHotkey() {
  try { if (HOTKEY_ON && globalShortcut) globalShortcut.unregister(HOTKEY_ON); } catch (e) {}
  HOTKEY_ON = null;
}

function syncTheme(mode) {
  const m = (mode === "dark" ? "dark" : "light");
  try { nativeTheme.themeSource = m; } catch (e) {}
  if (win && !win.isDestroyed() && win.setTitleBarOverlay) {
    try {
      // ⚠ 这里原来是写死的 "#ffffff"，`mode` 收到了但**一次都没用过** ——
      //   浅色主题下三个窗口按钮是白的压在白顶栏上，完全看不见。
      win.setTitleBarOverlay(titleBarOverlayOf(m));
    } catch (e) {}
  }
}

/** 网页那边切了深浅色，会通过 preload 报过来 */
/* ---- 打开文件夹 / 选文件夹 / 重启（2.3.6）----
   ⚠ 一律用 ipcMain.handle（网页那边 await），不用 send —— 选文件夹要拿返回值，
     而且失败时得能回一句人话，不是静默什么都没发生。
   ⚠ 注册（ipcMain.handle）随时都行，但**真正调用** shell/dialog 必须等 app ready
     —— 这几个 handler 只在用户点按钮时才跑，那时早就 ready 了。
     （踩过的坑：dialog 在 ready 前调会直接抛，报错那句还看不懂。） */
if (ipcMain && ipcMain.handle) {
  ipcMain.handle("shell:open-path", async (e, p) => {
    try {
      if (!p) return "没给路径";
      const r = await shell.openPath(p);      // 成功返回空串，失败返回错误描述
      return r || "";
    } catch (err) { return "打不开：" + err.message; }
  });
  ipcMain.handle("shell:show-item", (e, p) => {
    try {
      if (!p) return "没给路径";
      shell.showItemInFolder(p);              // 无效路径是静默失败，只能事后看
      return "";
    } catch (err) { return "打不开：" + err.message; }
  });
  ipcMain.handle("dialog:pick-folder", async () => {
    try {
      const r = await dialog.showOpenDialog({
        title: "选一个文件夹放数据",
        properties: ["openDirectory", "createDirectory"],
      });
      return (r && !r.canceled && r.filePaths && r.filePaths[0]) || "";
    } catch (err) { return ""; }
  });
  ipcMain.handle("app:relaunch", () => {
    try { app.relaunch(); app.exit(0); return ""; }
    catch (err) { return "重启失败：" + err.message; }
  });
  // 换完数据目录要把新位置记下来，否则重启后又回到老地方 ——
  // 用户会看到「明明说搬好了，重启一看还是原来的」。
  // ⚠ saveRoot 自己会先建目录（这个文件里踩过一次：%APPDATA% 下那层
  //   不存在时静默失败，于是每次开机都重新决定一遍数据放哪）。
  ipcMain.handle("app:set-data-root", (e, dir) => {
    try { if (!dir) return "没给目录"; saveRoot(dir); return ""; }
    catch (err) { return err.message; }
  });
  ipcMain.handle("clock:open", () => { openClockWin(); return ""; });
  ipcMain.handle("clock:close", () => { closeClockWin(); return ""; });
  ipcMain.handle("clock:toggle", () => {
    if (clockWin && !clockWin.isDestroyed()) { closeClockWin(); return "off"; }
    openClockWin(); return "on";
  });
  ipcMain.handle("clock:is-open", () =>
    (clockWin && !clockWin.isDestroyed()) ? "on" : "off");
  ipcMain.handle("app:install-dir", () => {
    try { return PACKAGED ? path.dirname(app.getPath("exe")) : ""; }
    catch (err) { return ""; }
  });
}

ipcMain && ipcMain.on && ipcMain.on("theme-changed", (e, mode) => {
  syncTheme(mode === "dark" ? "dark" : "light");
  if (win && !win.isDestroyed()) {
    try { win.setBackgroundColor(mode === "dark" ? "#1b1e22" : "#f2eada"); } catch (e) {}
  }
});

async function main() {
  // 不关的话按住 Alt 会从顶上拽出一排英文菜单（File / Edit / View…），
  // 一个中文应用里蹦出这个，穿帮。autoHideMenuBar 只是「藏起来」，不是「没有」。
  try { Menu.setApplicationMenu(null); } catch (e) {}
  // FAIL_STAGE 是给报错用的：出错时得让人知道**卡在哪一步**，
  // 只说「后端没能起来」等于什么都没说 —— 上面那次就是栽在这。
  FAIL_STAGE = "找数据文件夹";
  DATA_ROOT = await resolveDataRoot();
  if (!DATA_ROOT) return;            // 理论上不会；留个保险
  FAIL_STAGE = "启动后端";
  logLine("数据目录：" + DATA_ROOT);
  await startServer();
  FAIL_STAGE = "创建窗口";
  syncTheme(readThemeFromSettings());
  registerHotkey();          // 全局快捷键（没配就什么都不做）

  win = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 980,
    minHeight: 640,
    title: "小煦拾简",
    // ⚠ 把 Windows 的原生标题栏去掉。
    //   留着的话顶上会有**两条**杠：一条系统画的（颜色跟应用主题毫无关系 ——
    //   应用是深绿、系统是浅色时就是一条白杠压在深绿页面上），
    //   下面还有应用自己那条带 logo 和八个标签的顶栏。同一个名字写两遍，
    //   还白占 30px。现在窗口按钮浮在应用自己的顶栏右侧，只剩一层。
    titleBarStyle: "hidden",
    // ⚠ 建窗时的颜色**必须**和后面切主题时用同一个函数算。
    //   原来这里写死 symbolColor:"#ffffff"，和 syncTheme 各写一份 ——
    //   浅色主题下白图标压白顶栏，三个按钮完全看不见。
    titleBarOverlay: titleBarOverlayOf(readThemeFromSettings()),
    // 窗口还没画出网页时先铺这个色。以前写死浅色 #eef1f6 ——
    // 用深色主题的话每次开窗先闪一下白，再跳成深绿。
    backgroundColor: bgOf(readThemeFromSettings()),
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true, nodeIntegration: false,
      // 只为了让网页能告诉主进程「主题换了，把窗口按钮的颜色换一下」。
      // 没有 preload 就做不到 —— contextIsolation 下渲染进程够不着主进程。
      preload: path.join(__dirname, "preload.js"),
    },
  });
  await win.loadURL(URL);
}

/** 出事了。
 *
 *  ⚠ **这个函数自己绝对不能抛异常。** 它原来直接调 dialog.showErrorBox ——
 *    可 dialog 在 app ready 之前是不能用的。于是真实流程变成：
 *      出错 → 想报错 → 报错的代码自己又炸 → 用户看到的是
 *      「dialog module can only be used after app is ready」，
 *      而真正的原因（比如数据目录探测失败）一个字都没显示出来。
 *    报错的地方必须先保证自己不会死。*/
function onFatal(e) {
  const msg = String((e && e.message) || e);
  const stage = FAIL_STAGE || "启动";
  logLine("启动失败[" + stage + "]：" + msg);
  let body =
    "在「" + stage + "」这一步出错了。\n\n" +
    "错误信息：\n" + msg + "\n\n" +
    (PACKAGED
      ? "可以试试：\n" +
        "  1. 看「启动日志.txt」最后几行（和数据放在一起）\n" +
        "  2. 数据默认放在「文档\\小煦拾简」。想换个地方，\n" +
        "     就改这个文件里的那一行（或删掉它重开）：\n" +
        "     %APPDATA%\\小煦拾简\\数据位置.txt\n" +
        "  3. 双击「小煦拾简.exe」完全没反应时，改用「启动.bat」，\n" +
        "     它会留着黑窗口不关，能看到完整报错\n\n"
      : "开发模式需要系统装了 Python 和 openpyxl。\n\n");
  try {
    dialog.showErrorBox("启动失败", body);
  } catch (e2) {
    // 连弹框都用不了（多半就是 app 还没 ready）—— 至少别把原因吞掉
    console.error(body + "\n（弹框也失败了：" + e2.message + "）");
  }
  try { app.quit(); } catch (e3) { process.exit(1); }
}

let FAIL_STAGE = "";

// ⚠ **必须等 app ready 再跑 main()**。
//   main() 里第一件事就是 resolveDataRoot()，那里可能弹框；
//   而 dialog / app.getPath 这些在 ready 之前全是不能用的。
//   原来写的是裸的 `main().catch(...)` —— 在模块顶层直接调用，
//   等于在 ready 之前就跑，于是安装完必炸、而且炸出来的是
//   「dialog module can only be used after app is ready」这种看不懂的话。
app.whenReady().then(() => {
  FAIL_STAGE = "准备";
  return main();
}).catch(onFatal);

// 无论从哪条路径退出，都把后端一起收掉
app.on("quit", () => {
  if (back) { try { back.kill(); } catch (e) {} }
});
app.on("window-all-closed", () => app.quit());
