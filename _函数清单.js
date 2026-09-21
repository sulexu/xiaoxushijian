/* 拆分安全网：对比「拆分前」和「拆分后」的函数清单。
   用途：拆 app.js 之前先 dump 一份基线，拆完再 dump 一次，
   两份必须**完全一致** —— 少一个 = 搬丢了，多一个 = 搬重了。
   ⚠ 这一步很重要：拆文件最典型的错误是「搬走了一个函数但忘了删原来的」，
     或者「两个文件都定义了它」—— 而 JS 是后定义者胜、**不报错**。
     本次就是在排查这个毛病时抓到 copyText 被定义两遍的。

   用法：
     node _函数清单.js > _函数清单_基线.txt     # 拆之前
     node _函数清单.js > _函数清单_之后.txt     # 拆之后
     node _函数清单.js --compare _函数清单_基线.txt
*/
const fs = require("fs");
const path = require("path");

/* 读取当前所有前端脚本。**不写死 app.js** ——
   拆分之后脚本会变成好几个，这里要自动跟着 index.html 走，
   否则拆完这个安全网就自己失效了（那就成了「测试绕开了出问题的入口」）。 */
function scriptFiles() {
  const html = fs.readFileSync("static/index.html", "utf8");
  const files = [...html.matchAll(/<script src="\/static\/([^"]+)"><\/script>/g)]
    .map(m => m[1])
    .filter(f => f.endsWith(".js") && !f.includes("echarts"))   // echarts 是第三方库，不算
    .map(f => path.join("static", f));
  return files.length ? files : ["static/app.js"];              // 兜底
}

function topFunctions(src) {
  const out = [];
  for (const line of src.split("\n")) {
    const m = line.match(/^(?:async\s+)?function\s+(\w+)\s*\(/);
    if (m) out.push(m[1]);
  }
  return out;
}

const files = scriptFiles();
const all = [];
const perFile = {};
for (const f of files) {
  const src = fs.readFileSync(f, "utf8");
  const names = topFunctions(src);
  perFile[f] = names;
  all.push(...names);
}

// 重名检测（同一名字在**任意**文件里出现两次都是危险的）
const dup = {};
for (const n of all) dup[n] = (dup[n] || 0) + 1;
const dups = Object.keys(dup).filter(n => dup[n] > 1).sort();

const sorted = [...all].sort();

const arg = process.argv[2];
if (arg === "--dump") {
  // 自己写文件，别让 shell 重定向插一脚 ——
  // ⚠ PowerShell 的 `>` 写的是 UTF-16LE，而 Get-Content 默认按 UTF-8 读，
  //   于是基线文档里每个字符之间多一个空格，比对时全红。编码这种事别经 shell。
  const lines = [`# 前端顶层函数清单（${files.length} 个文件，${sorted.length} 个函数）`,
                 `# 文件: ${files.join(", ")}`,
                 ...(dups.length ? [`# ⚠ 重名: ${dups.map(n => n + "×" + dup[n]).join(", ")}`] : []),
                 ...sorted];
  fs.writeFileSync(process.argv[3] || "_函数清单_基线.txt", lines.join("\n") + "\n", "utf8");
  console.log("已写入 %s：%d 个文件 / %d 个函数%s",
              process.argv[3] || "_函数清单_基线.txt", files.length, sorted.length,
              dups.length ? "（⚠ 有重名：" + dups.join(", ") + "）" : "");
  process.exit(0);
}
if (arg === "--compare") {
  const base = fs.readFileSync(process.argv[3], "utf8")
    .split("\n").map(s => s.trim()).filter(s => s && !s.startsWith("#"));
  const nowSet = new Set(sorted), baseSet = new Set(base);
  const lost = base.filter(n => !nowSet.has(n));
  const added = sorted.filter(n => !baseSet.has(n));
  console.log(`基线 ${base.length} 个 / 现在 ${sorted.length} 个`);
  if (lost.length) console.log("❌ 少了这些（搬丢了）: " + lost.join(", "));
  if (added.length) console.log("❌ 多了这些（凭空出现 / 搬重了）: " + added.join(", "));
  if (!lost.length && !added.length) console.log("✅ 函数清单完全一致，一个没丢没多");
  process.exit(lost.length || added.length ? 1 : 0);
}

console.log("# 前端顶层函数清单（%d 个文件，%d 个函数）", files.length, all.length);
console.log("# 文件: " + files.join(", "));
if (dups.length) console.log("# ⚠ 重名: " + dups.map(n => `${n}×${dup[n]}`).join(", "));
for (const n of sorted) console.log(n);
