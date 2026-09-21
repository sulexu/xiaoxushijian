/* 验证「拆分没改任何业务代码」。
 *
 * 思路：把拆分后的 core.js + app.js 拼起来，去掉我新加的头部注释和指路注释，
 * 然后跟拆分前的备份**逐行比对**。
 * 只要不是「一行不差」，就说明搬运过程动了代码 —— 那就必须查清楚动了什么。
 *
 * ⚠ 这比「跑一遍测试」更硬：测试只覆盖它测到的路径，
 *   而逐行比对覆盖**每一行**（包括注释、包括没人测的分支）。
 */
const fs = require("fs");

const BACKUP = "_备份_app.js.拆分前";
const NOW = ["static/core.js", "static/app.js"];

const backup = fs.readFileSync(BACKUP, "utf8").split("\n");
const now = NOW.flatMap(f => fs.readFileSync(f, "utf8").split("\n"));

/* 去掉我在拆分时新加的注释行 —— 这些是预期的差异，不是业务代码变化。
   判定方式：新文件里那些「拆分说明」注释块。用标记认，别用行号硬编码。 */
function isAddedBlock(line, inBlock) {
  const t = line.trim();
  if (inBlock) return { add: true, inBlock: !t.endsWith("*/") };
  // 头部说明块 / 指路注释块。两种都以 `/*` 开头、若干行后以 `*/` 收尾。
  if (/^\/\* 小煦拾简 · 前端基础设施/.test(t)) return { add: true, inBlock: true };
  if (/^\/\* ⚠ 原来这里（第 \d+ ~ \d+ 行）是基础设施那一段/.test(t)) return { add: true, inBlock: true };
  return { add: false, inBlock: false };
}

const cleaned = [];
let inBlock = false;
for (const l of now) {
  const r = isAddedBlock(l, inBlock);
  inBlock = r.inBlock;
  if (!r.add) cleaned.push(l);
}

/* 规范化后再比 —— 以下都是拆分**必然**带来的格式差异，不是业务代码变化：
     · 行尾 \r（源文件是 CRLF，我写新文件时用 \n，拼接处会多出一个空的"\r"行）
     · 文件/接缝处的空行
   规范化之后必须**一行不差**；差一行就说明真动了代码。 */
const norm = a => a.map(s => String(s).replace(/\r+$/, "")).filter(s => s.trim() !== "");

const A = norm(backup), B = norm(cleaned);
console.log("拆分前 %d 行", backup.length);
console.log("拆分后 %d 行 → 规范化后：旧 %d 行 / 新 %d 行", now.length, A.length, B.length);

if (A.length === B.length && A.every((s, i) => s === B[i])) {
  console.log("\n✅ 逐行一致（规范化后）：拆分**没有改动任何业务代码**，注释也一行没丢");
  process.exit(0);
}

const diffs = [];
for (let i = 0; i < Math.max(A.length, B.length) && diffs.length < 20; i++) {
  if (A[i] !== B[i]) diffs.push({ at: i + 1, old: A[i], now: B[i] });
}
console.log("\n❌ 规范化后仍有 %d 处差异（只列前 20）：", diffs.length);
for (const d of diffs) {
  console.log("  规范行 %d", d.at);
  console.log("    旧: %s", JSON.stringify(d.old));
  console.log("    新: %s", JSON.stringify(d.now));
}
process.exit(1);
