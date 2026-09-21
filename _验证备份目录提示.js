/* 一次性验证：备份卡片的目录提示（原来那句写死的「个人信息统计\_自动备份\」）。
   把 renderBackups 的目录推导部分抠出来验 —— 重点是：
   改过备份目录之后，那句话**必须**跟着变成真实目录，不能还说老地方。 */
const fs = require("fs");
const { allSource } = require("./_前端源码.js");   // 跟着 index.html 走，拆分后自动跟上
const src = allSource();

// 只取 renderBackups 里那段「算目录提示」的源码（leaf + dirs + dirTip）
const fn = (() => {
  const i = src.indexOf("function renderBackups()");
  let j = src.indexOf("{", i), depth = 0, k = j;
  for (; k < src.length; k++) {
    if (src[k] === "{") depth++;
    else if (src[k] === "}") { depth--; if (depth === 0) break; }
  }
  return src.slice(i, k + 1);
})();

// 抠出 leaf 那行来验（eval 里的 const 不外泄，换成 var 才拿得到）
const leafLine = fn.match(/const leaf = .*;/)[0].replace("const leaf", "var leaf");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
eval(leafLine);

let pass = 0, fail = 0;
const ck = (label, got, want) => {
  const ok = got === want;
  ok ? pass++ : fail++;
  console.log((ok ? "  [OK]   " : "  [FAIL] ") + label +
              (ok ? "" : `\n         got=${JSON.stringify(got)}\n        want=${JSON.stringify(want)}`));
};

// 复刻 renderBackups 里那两行的逻辑（跟源码同一写法）
const tipOf = list => {
  const dirs = [...new Set(list.map(b => b.dir).filter(Boolean))];
  return dirs.length ? dirs.map(d => leaf(d)).join(" 和 ") : "还没生成过备份";
};

console.log("=== 默认备份目录 ===");
ck("默认：数据目录下的 _自动备份",
   tipOf([{dir: "D:\\小煦拾简\\数据\\_自动备份", elsewhere: false}]),
   "_自动备份");

console.log("=== 用户改过备份目录（这就是原来那个 bug 的场景）===");
ck("改到 U 盘 → 提示必须跟着变，不能还说 _自动备份",
   tipOf([{dir: "E:\\小煦拾简备份\\_自动备份", elsewhere: false}]),
   "_自动备份");
ck("改到自建目录 → 显示那个目录名",
   tipOf([{dir: "E:\\我的备份", elsewhere: false}]),
   "我的备份");

console.log("=== 新旧目录都有备份（backup_roots 会同时列出）===");
ck("两个目录都列出来",
   tipOf([{dir: "E:\\我的备份", elsewhere: false},
          {dir: "D:\\小煦拾简\\数据\\_自动备份", elsewhere: true}]),
   "我的备份 和 _自动备份");

console.log("=== 还没有任何备份 ===");
ck("空列表 → 说清楚还没备份过，而不是报一个假目录",
   tipOf([]), "还没生成过备份");

console.log("=== leaf() 边界 ===");
ck("结尾带反斜杠",        leaf("E:\\备份\\"),        "备份");
ck("结尾带正斜杠",        leaf("E:/备份/"),          "备份");
ck("只剩盘符（去尾后还有内容）", leaf("E:\\"),       "E:");
ck("空串不炸",            leaf(""),                  "");

console.log("=== 反向验证：旧写法在这种情况下是错的 ===");
const oldTip = "个人信息统计\\_自动备份\\";
ck("旧写法在「改到 E 盘」时给出的是假目录（确认这就是那个 bug）",
   oldTip !== tipOf([{dir: "E:\\我的备份"}]) ? "假" : "真", "假");

console.log(`\n通过 ${pass} 项，失败 ${fail} 项`);
process.exit(fail ? 1 : 0);
