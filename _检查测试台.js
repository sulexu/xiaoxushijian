/* 检查 static/_test.html 里**每一段内联脚本**的语法。
 *
 * 为什么需要：内联脚本第 1 行的语法错会让**整段**不执行，
 * 页面就永远停在 RUNNING —— 看起来跟「跑得慢」一模一样（交接文档 D2）。
 * 本次就栽在这上面：给一个普通箭头函数里加了 await，整页停摆，
 * 而报错只藏在 #R 里，`--dump-dom` 时机不对就根本看不到。
 *
 * 用法：node _检查测试台.js
 */
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("static/_test.html", "utf8");

// 抠出所有 <script> 里**没有 src 的**（内联的），逐个做语法检查
const re = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;
let m, i = 0, bad = 0;

while ((m = re.exec(html)) !== null) {
  i++;
  const code = m[1];
  // 行号：按 script 开始标签的位置算个大概，报错时好定位
  const upto = html.slice(0, m.index);
  const line = upto.split("\n").length;
  try {
    // 只编译不执行 —— 正是我们要的（执行会需要 DOM）
    new vm.Script(code, {filename: `_test.html 内联脚本 #${i}（约第 ${line} 行）`});
    console.log("  [OK]   第 %d 段（约第 %d 行起，%d 字符）", i, line, code.length);
  } catch (e) {
    bad++;
    console.log("  [FAIL] 第 %d 段（约第 %d 行起）: %s", i, line, e.message);
    // 报出出错行附近的原文，省得再去数行
    const mm = /_test\.html:(\d+)/.exec(e.stack || "");
    if (mm) {
      const n = +mm[1];
      const src = code.split("\n");
      for (let k = Math.max(0, n - 2); k < Math.min(src.length, n + 1); k++) {
        console.log("        %s %s", k + 1 === n ? ">>" : "  ", src[k].trim().slice(0, 110));
      }
    }
  }
}

console.log("\n共 %d 段内联脚本，%d 段有语法错", i, bad);
process.exit(bad ? 1 : 0);
