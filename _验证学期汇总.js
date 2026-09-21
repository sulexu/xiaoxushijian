/* 一次性验证：学期汇总那段说明（semScopeNote）。
   用户要的是「学期维度汇总」。底下那六张卡**本来就是学期口径**（BILL 按学期加载），
   所以这里不加新数字，只要把**口径写清楚**：哪个学期、哪段时间、多少条。
   重点验边界：空数据不能崩、也不能把「还没记」说成「合计 0」。 */
const fs = require("fs");
const { allSource } = require("./_前端源码.js");   // 跟着 index.html 走，拆分后自动跟上
const src = allSource();

function grabFn(name) {
  const key = "function " + name + "(";
  const i = src.indexOf(key);
  if (i < 0) throw new Error("找不到 " + name);
  let j = src.indexOf("{", i), depth = 0, k = j;
  for (; k < src.length; k++) {
    if (src[k] === "{") depth++;
    else if (src[k] === "}") { depth--; if (depth === 0) break; }
  }
  return src.slice(i, k + 1);
}
/* ⚠ 踩过的坑（记下来免得下次再花时间）：
   CommonJS 里 `eval(...)` 是**间接调用** → 代码跑在**全局作用域**，不是模块作用域。
   所以模块里的 `const esc` / `let SEMS` 它都看不见 —— semScopeNote 里那句 `esc(name)`
   会抛 ReferenceError，而异常又在 semScopeNote 内部的表达式里被吞掉，
   表现成「学期名莫名其妙没出现」，看起来特别像代码的 bug。
   解法：把依赖挂到 globalThis 上，间接 eval 就找得到了。 */
globalThis.esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
globalThis.SEMS = null;
const setSems = v => { globalThis.SEMS = v; };
eval(src.match(/function semScopeNote\([\s\S]*?\n\}/)[0]);

let pass = 0, fail = 0;
const ck = (label, ok, extra) => {
  ok ? pass++ : fail++;
  console.log((ok ? "  [OK]   " : "  [FAIL] ") + label + (ok || !extra ? "" : `\n         ${extra}`));
};

const B = (recs) => ({records: recs.map(d => ({date: d, exp: 1, inc: 0}))});

console.log("=== 正常一学期 ===");
setSems({current: "大二上"});
let s = semScopeNote(B(["2026-09-01", "2026-09-20", "2026-08-15"]));
console.log("    " + s);
ck("带学期名", s.includes("大二上"));
ck("日期范围是最早~最晚", s.includes("2026-08-15 ~ 2026-09-20"));
ck("带条数", s.includes("共 3 条流水"));
ck("空数据那句不出现", !s.includes("还没有流水"));

console.log("=== 只有一天：不写成 8/15 ~ 8/15 ===");
s = semScopeNote(B(["2026-09-01"]));
console.log("    " + s);
ck("单日只显示一次日期", s.includes("2026-09-01") && !s.includes("2026-09-01 ~ 2026-09-01"));

console.log("=== 空学期：必须说清是「还没记」，不能像数据丢了 ===");
s = semScopeNote(B([]));
console.log("    " + s);
ck("明说还没流水", s.includes("还没有流水"));
ck("明说那是 0 不是丢数据", s.includes("不是丢了数据"));
ck("不写假的日期范围", !/\d{4}-\d{2}-\d{2}/.test(s));

console.log("=== SEMS 还没回来（页面先渲染）：不能崩、不能写 undefined ===");
setSems(null);
s = semScopeNote(B(["2026-09-01", "2026-09-02"]));
console.log("    " + s);
ck("不抛异常且没有 undefined", typeof s === "string" && !s.includes("undefined"));
ck("仍然给出日期范围", s.includes("2026-09-01 ~ 2026-09-02"));

console.log("=== SEMS 在但 current 为空 ===");
setSems({current: ""});
s = semScopeNote(B(["2026-09-01"]));
ck("不写空学期名", !s.includes("undefined") && typeof s === "string");

console.log("=== 记录日期里有空串（脏数据）不能污染范围 ===");
setSems({current: "大二上"});
s = semScopeNote({records: [{date: ""}, {date: "2026-09-05"}, {date: null}]});
console.log("    " + s);
ck("空日期被跳过，范围从真实日期起", s.includes("2026-09-05") && !s.includes("~ "));
ck("条数按记录总数算（含脏数据）", s.includes("共 3 条流水"));

console.log("=== 学期名要转义（防止名字里带尖括号）===");
setSems({current: "<img>"});
s = semScopeNote(B(["2026-09-01"]));
ck("尖括号被转义", s.includes("&lt;img&gt;") && !s.includes("<img>"));

console.log(`\n通过 ${pass} 项，失败 ${fail} 项`);
process.exit(fail ? 1 : 0);
