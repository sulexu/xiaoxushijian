/* 把前端所有脚本按 index.html 里的**顺序**拼成一份源码。
 *
 * 为什么需要它：app.js 现在是好几个文件（见 index.html），
 * 而验证脚本要从源码里抠函数出来跑。写死读 app.js 的话，
 * 函数一搬家验证就失效 —— 那就是「测试绕开了出问题的入口」，
 * 表面全绿、其实什么都没测（交接文档 D4）。
 *
 * 所以统一从这里取：顺序跟浏览器完全一致。
 * ⚠ 顺序有意义：core.js 里是顶层 const/let，后面的文件靠它们。
 */
const fs = require("fs");
const path = require("path");

function scriptFiles(staticDir) {
  const dir = staticDir || "static";
  const html = fs.readFileSync(path.join(dir, "index.html"), "utf8");
  const files = [...html.matchAll(/<script src="\/static\/([^"]+)"><\/script>/g)]
    .map(m => m[1])
    .filter(f => f.endsWith(".js") && !f.includes("echarts"));   // echarts 是第三方，不算
  if (!files.length) return [path.join(dir, "app.js")];          // 兜底
  return files.map(f => path.join(dir, f));
}

/** 按加载顺序拼好的前端源码。 */
function allSource(staticDir) {
  return scriptFiles(staticDir).map(f => fs.readFileSync(f, "utf8")).join("\n");
}

module.exports = { scriptFiles, allSource };
