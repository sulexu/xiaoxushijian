/* 一次性验证：待办筛选（todoFiltered）的过滤逻辑。
   把 app.js 里的纯函数抠出来，喂一份固定数据，逐条验。
   ⚠ 只验逻辑，不验 DOM —— DOM 那部分要无头 Chrome 才算数（见报告盲区）。 */
const fs = require("fs");
const { allSource } = require("./_前端源码.js");   // 跟着 index.html 走，拆分后自动跟上
const src = allSource();

// 抠出 todoFilter 的初值和 todoFiltered()
const filterDecl = src.match(/let todoFilter = \{[^}]*\};/)[0];

let STOCK;                                   // todoFiltered 依赖这个全局
eval(filterDecl);

// todoCard() 还要 esc()（用真的，别抄一份——抄的那份迟早和真身不一致）
// 和 ICON（这里只需要不报错，图标内容与筛选取无关）
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ICON = new Proxy({}, {get: () => ""});

// todoFiltered 里用到的 todoFiltering 也要（拿源码，别抄一份）
const tfLine = src.match(/const todoFiltering = [^;]+;/)[0];

// 直接取 todoFiltered 函数体
function grab(name) {
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
eval(tfLine + "\n" + grab("todoFiltered") + "\n" + grab("todoCard"));

// 这里只验「哪些行进表」，不验表单长什么样 —— 那两个用占位替掉，
// 免得为了一个空表再去拖 todoForm → readTodoForm 一整串。
const todoForm = () => "<form></form>";
const emptyBox = (t) => `<div class="empty">${t}</div>`;

const T = (row, item, cat, pri, stat, due, days, note) =>
  ({row, item, cat, pri, stat, due: due || "", days: days ?? null, note: note || ""});

STOCK = {todo: [
  T(1, "买牙膏",   "采购", "高", "未完成", "2026-09-25",  5,  "楼下超市"),
  T(2, "写实验报告", "学习", "高", "未完成", "2026-09-21", -2, "周三交"),
  T(3, "还书",     "事务", "中", "未完成", "2026-09-23",  3,  "图书馆"),
  T(4, "取快递",   "生活", "低", "未完成", "",           null, ""),
  T(5, "交电费",   "事务", "中", "已完成", "2026-09-10", -13, "已付"),
]};

let pass = 0, fail = 0;
const ids = () => todoFiltered().map(t => t.row).join(",");
const ck = (label, got, want) => {
  const ok = got === want;
  ok ? pass++ : fail++;
  console.log((ok ? "  [OK]   " : "  [FAIL] ") + label +
              (ok ? "" : `\n         got=${got}\n        want=${want}`));
};
const setF = o => { todoFilter = Object.assign({cats: [], pri: "", stat: "open", q: ""}, o); };

console.log("=== 默认：排除已完成（待办页默认就是「只看没做完」）===");
setF({});
ck("默认只剩未完成 4 条", ids(), "1,2,3,4");

console.log("=== 状态三档 ===");
setF({stat: "all"});
ck("全都看 = 5 条", ids(), "1,2,3,4,5");
setF({stat: "done"});
ck("只看已完成 = 第 5 条", ids(), "5");

console.log("=== 按类别（可多选）===");
setF({cats: ["事务"]});
ck("只看事务（未完成）= 3", ids(), "3");
setF({cats: ["采购", "学习"]});
ck("采购+学习 = 1,2", ids(), "1,2");

console.log("=== 按优先级 ===");
setF({pri: "高"});
ck("只看高 = 1,2", ids(), "1,2");
setF({stat: "all", pri: "中"});
ck("全都看+中 = 3,5", ids(), "3,5");

console.log("=== 关键词（搜事项/类别/备注/日期）===");
setF({q: "报告"});
ck("搜事项「报告」= 2", ids(), "2");
setF({q: "超市"});
ck("搜备注「超市」= 1", ids(), "1");
setF({q: "图书馆"});
ck("搜备注「图书馆」= 3", ids(), "3");
setF({q: "事务"});
ck("搜类别「事务」= 3", ids(), "3");
setF({q: "2026-09-2"});
ck("搜日期 = 1,2,3", ids(), "1,2,3");
setF({q: "报告", pri: "高"});
ck("关键词+优先级 同时生效 = 2", ids(), "2");

console.log("=== 大小写不敏感 ===");
STOCK.todo.push(T(6, "Read PDF", "学习", "低", "未完成", "", null, ""));
setF({q: "read pdf"});
ck("小写能搜到大写条目 = 6", ids(), "6");
STOCK.todo.pop();

console.log("=== 组合条件取交集，且不误伤已完成 ===");
setF({stat: "all", cats: ["事务"], pri: "中"});
ck("全都看+事务+中 = 3,5", ids(), "3,5");

console.log("=== 边界：筛不出东西时是空数组（不能退回全部）===");
setF({q: "这个词不存在"});
ck("无匹配 = 空（关键：不能变成「显示全部」）", ids(), "");

console.log("=== 总览页那条提醒卡不受筛选影响 ===");
setF({q: "这个词不存在"});            // 此时 todoFiltered() 是空的
ck("todoCard() 不传参仍画全部 5 条",
   (todoCard().match(/data-todo-edit=/g) || []).length, 5);
ck("todoCard(筛后的 row) 只画 1 条",
   (todoCard([2]).match(/data-todo-edit=/g) || []).length, 1);

console.log("=== todoCard 传入的 row 顺序 = 筛选后的顺序（不被库里的 ord 打乱）===");
ck("传 [3,1] 就按 3,1 画",
   (todoCard([3,1]).match(/data-todo-edit="(\d+)"/g) || []).join(" "),
   'data-todo-edit="3" data-todo-edit="1"');

console.log(`\n通过 ${pass} 项，失败 ${fail} 项`);
process.exit(fail ? 1 : 0);
