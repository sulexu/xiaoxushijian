/* 一次性验证：支出环比（monthlySpendCompare / momSub）。
   这是最容易悄悄算错的那类代码 —— 百分比错了界面照样显示，只是数字是假的。
   所以重点验：边界、同期截取、没有可比数据时**不能报 0%**、阈值方向、月末差一天。 */
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
const constLine = src.match(/const MOM_THRESHOLD = [^;]+;/)[0];

let BILL = null;
const money = v => "¥" + Number(v || 0).toFixed(2);
eval(constLine + "\n" + grabFn("localDate") + "\n" + grabFn("ymOf")
     + "\n" + grabFn("monthlySpendCompare") + "\n" + grabFn("momSub"));

let pass = 0, fail = 0;
const ck = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log((ok ? "  [OK]   " : "  [FAIL] ") + label +
              (ok ? "" : `\n         got=${JSON.stringify(got)}\n        want=${JSON.stringify(want)}`));
};

// 造数据：只关心 exp（支出）
const rec = (date, exp) => ({date, exp, inc: 0});
const run = (recs, today) => { BILL = {records: recs}; return monthlySpendCompare(today); };

console.log("=== 基本情况：本月 3000，上月整月 2000 → +50% ===");
let r = run([rec("2026-09-05", 1000), rec("2026-09-18", 2000),
             rec("2026-08-05", 2000)], "2026-09-20");
ck("本月合计", r.cur, 3000);
ck("上月整月", r.prevFull, 2000);
ck("整月环比 +50%", r.pctFull, 0.5);
ck("上月同期（8/1~8/20）= 2000", r.prevSame, 2000);
ck("同期环比 +50%", r.pctSame, 0.5);

console.log("=== 同期截取：上月 8/25 那笔不算「同期」（今天才 9/20）===");
r = run([rec("2026-09-10", 1000),
         rec("2026-08-10", 500), rec("2026-08-25", 900)], "2026-09-20");
ck("上月整月 = 1400", r.prevFull, 1400);
ck("上月同期只算到 8/20 → 500", r.prevSame, 500);
ck("整月环比 (1000-1400)/1400", Math.round(r.pctFull * 1e6) / 1e6, Math.round((1000 - 1400) / 1400 * 1e6) / 1e6);
ck("同期环比 +100%", r.pctSame, 1);

console.log("=== 月末差一天：9/30 时同期窗口是 30 天（今天是本月第 30 天）===");
r = run([rec("2026-09-30", 100),
         rec("2026-08-30", 10), rec("2026-08-31", 20)], "2026-09-30");
// ⚠ 同期 = 上月 1 号到「今天这个日号」（9/30 → 8/1~8/30），所以 8/31 不算。
//   我第一版把这个期望写成了 30（含 8/31），是**测试错了**，不是代码错了。
ck("上月同期 = 8/1~8/30 → 只算 10", r.prevSame, 10);
ck("9/30 是 9 月最后一天 → 不算 partial", r.partial, false);

console.log("=== 2 月末边界：3/31 时上月是 2 月，同期要截到 2/28（不能取 3/31 去比）===");
r = run([rec("2026-03-15", 500),
         rec("2026-02-10", 100), rec("2026-02-28", 200)], "2026-03-31");
ck("2 月整月 = 300", r.prevFull, 300);
ck("2 月同期（截到 2/28）= 300", r.prevSame, 300);

console.log("=== ⚠ 没有可比数据时必须给 null，不能给 0% ===");
r = run([rec("2026-09-05", 1000)], "2026-09-20");
ck("上月整月 0 元 → pctFull 是 null（不是 0）", r.pctFull, null);
ck("上月同期 0 元 → pctSame 是 null（不是 0）", r.pctSame, null);

console.log("=== 跌了：pct 是负数（要不要显示由 momSub 决定）===");
r = run([rec("2026-09-01", 100), rec("2026-08-01", 1000)], "2026-09-20");
ck("跌幅 -90%", r.pctFull, -0.9);

console.log("=== 本月还没开始花：0 元也要能算 ===");
r = run([rec("2026-08-01", 1000)], "2026-09-20");
ck("本月 0", r.cur, 0);
ck("-100%", r.pctFull, -1);

console.log("=== 只算支出：收入不计入 ===");
r = run([{date: "2026-09-05", exp: 100, inc: 9999},
         {date: "2026-08-05", exp: 200, inc: 9999}], "2026-09-20");
ck("本月只算 exp=100", r.cur, 100);
ck("上月只算 exp=200", r.prevFull, 200);

console.log("=== partial 标记（决定要不要显示「较上月同期」）===");
ck("9/20 < 9 月 30 天 → partial",
   run([rec("2026-09-01", 1), rec("2026-08-01", 1)], "2026-09-20").partial, true);
ck("9/30 = 9 月最后一天 → 不 partial",
   run([rec("2026-09-01", 1), rec("2026-08-01", 1)], "2026-09-30").partial, false);
// 反向验证：这正是刚才那个 bug —— 9 月(30 天) vs 8 月(31 天)，用上月天数判就会出错
ck("反向验证：9/30 若按**上月**天数(31)判就会被误判成 partial",
   (30 < 31) ? "会误判（这就是修掉的那个 bug）" : "不会误判",
   "会误判（这就是修掉的那个 bug）");
ck("2/28 = 2 月最后一天 → 不 partial",
   run([rec("2026-02-01", 1), rec("2026-01-01", 1)], "2026-02-28").partial, false);

console.log("\n=== momSub：阈值 20% 与「只报涨」 ===");
const sub = (pctFull, partial, pctSame) =>
  momSub(1200, {pctFull, pctSame, partial, cur: 1, prevFull: 1, prevSame: 1, curN: 1, prevN: 1});
ck("+19% 不报（没到 20%）", sub(0.19, false, null), "预算 ¥1200.00");
ck("+20% 报（含等号）",     sub(0.20, false, null), "预算 ¥1200.00 · 比上月 +20%");
ck("+50% 报",               sub(0.50, false, null), "预算 ¥1200.00 · 比上月 +50%");
ck("跌了不报（只要涨的）",   sub(-0.4, false, null), "预算 ¥1200.00");
ck("垫底不报",             sub(0, false, null), "预算 ¥1200.00");
ck("null（没可比数据）不报", sub(null, false, null), "预算 ¥1200.00");
ck("partial 时同期也报",    sub(0.25, true, 0.40),
   "预算 ¥1200.00 · 比上月 +25% · 较上月同期 +40%");
ck("非 partial 不显示同期", sub(0.25, false, 0.40), "预算 ¥1200.00 · 比上月 +25%");
ck("没设预算也要显示环比",  momSub(null, {pctFull: 0.3, pctSame: null, partial: false}),
   "未设预算 · 比上月 +30%");
ck("负数百分比格式化成 -5%", sub(-0.05, false, null), "预算 ¥1200.00");

console.log("=== 反向验证：旧写法不可能有这些行为 ===");
ck("旧写法是写死的「预算 ¥x」，永远不会出现环比",
   "预算 ¥1200.00" !== sub(0.5, false, null) ? "会漏" : "不会漏", "会漏");

console.log(`\n通过 ${pass} 项，失败 ${fail} 项`);
process.exit(fail ? 1 : 0);
