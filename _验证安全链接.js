/* 一次性验证：把 app.js 里的 safeUrl / mdLink / mdInline 抠出来真跑一遍。
   反向验证：确认危险协议**真的**会被拦，正常链接和插图**真的**不受影响。
   ⚠ 第一版只测了 safeUrl，漏了「附件/」这条重写路径 —— 于是把正常插图
     判成不可信。所以这一版**必须测 mdInline 的整体输出**，不只测零件。 */
const fs = require("fs");
const { allSource } = require("./_前端源码.js");   // 跟着 index.html 走，拆分后自动跟上
const src = allSource();

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
const constLine = src.match(/const SAFE_URL = .*;/)[0];
eval(constLine + "\n" + grab("safeUrl") + "\n" + grab("mdLink") + "\n" + grab("mdInline"));

let pass = 0, fail = 0;
const ck = (label, got, want) => {
  const ok = got === want;
  ok ? pass++ : fail++;
  console.log((ok ? "  [OK]   " : "  [FAIL] ") + label +
              (ok ? "" : `\n         got=${JSON.stringify(got)}\n        want=${JSON.stringify(want)}`));
};

console.log("=== 危险协议必须被拦（退成纯文本）===");
ck("javascript:", mdLink("点我", "javascript:alert(1)"), "点我");
ck("大小写混写 JaVaScRiPt:", mdLink("点我", "JaVaScRiPt:alert(1)"), "点我");
ck("前导空格 + javascript:", mdLink("点我", "  javascript:alert(1)"), "点我");
ck("内嵌控制字符 java\\x00script:", mdLink("点我", "java\u0000script:alert(1)"), "点我");
ck("内嵌零宽字符 java\\u200Bscript:", mdLink("点我", "java\u200Bscript:alert(1)"), "点我");
ck("vbscript:", mdLink("点我", "vbscript:msgbox(1)"), "点我");
ck("data:text/html:", mdLink("点我", "data:text/html,<script>x</script>"), "点我");
ck("file://", mdLink("点我", "file:///C:/Windows/System32/calc.exe"), "点我");

console.log("=== 正常链接必须不受影响 ===");
ck("https", mdLink("站", "https://example.com"),
   '<a href="https://example.com" target="_blank" rel="noopener">站</a>');
ck("http", mdLink("站", "http://example.com/a?b=c"),
   '<a href="http://example.com/a?b=c" target="_blank" rel="noopener">站</a>');
ck("mailto", mdLink("信", "mailto:a@b.com"),
   '<a href="mailto:a@b.com" target="_blank" rel="noopener">信</a>');
ck("锚点 #", mdLink("顶", "#top"),
   '<a href="#top" target="_blank" rel="noopener">顶</a>');
ck("根路径 /", mdLink("图", "/attach/x.jpg"),
   '<a href="/attach/x.jpg" target="_blank" rel="noopener">图</a>');
ck("相对 ./", mdLink("同", "./a.md"),
   '<a href="./a.md" target="_blank" rel="noopener">同</a>');

console.log("=== 插图：附件/ 重写必须照旧工作（上一版就是漏了这条）===");
ck("附件/ 插图 → 重写成 /attach/",
   mdInline("![猫](附件/abc.jpg)"),
   '<img alt="猫" loading="lazy" src="/attach/abc.jpg">');
ck("https 插图 → 原样",
   mdInline("![猫](https://a.com/b.png)"),
   '<img alt="猫" loading="lazy" src="https://a.com/b.png">');
ck("危险插图地址（无括号）→ 只留 alt 文字",
   mdInline("![猫](javascript:void(0))"),
   "猫)");
// ⚠ 上面那个尾随 ")" 是**既有限制**，不是这次安全修复引入的：
//   图片/链接正则都是 `([^)\s]+)`，URL 里一出现 ")" 就在那里截断。
//   旧代码同样如此（连维基那种正常链接也一起坏）。这里把它记下来当基线，
//   哪天有人修了括号解析，这条会变红，正好提醒同步更新。
ck("既有限制基线：URL 含括号会截断（与安全修复无关）",
   mdInline("![图](https://en.wikipedia.org/wiki/Foo_(bar))"),
   '<img alt="图" loading="lazy" src="https://en.wikipedia.org/wiki/Foo_(bar">)');
ck("危险链接（无括号）→ 纯文本",
   mdInline("[点我](javascript:void(0))"),
   "点我)");

console.log("=== 正文其它 Markdown 不受影响 ===");
ck("粗体", mdInline("**粗**"), "<b>粗</b>");
ck("斜体", mdInline("x *斜* y"), "x <i>斜</i> y");
ck("删除线", mdInline("~~删~~"), "<s>删</s>");
ck("行内代码", mdInline("`code`"), "<code>code</code>");
ck("混排：正文+安全链接",
   mdInline("见 [文档](https://a.com) 和 ![图](附件/x.png)"),
   '见 <a href="https://a.com" target="_blank" rel="noopener">文档</a> 和 <img alt="图" loading="lazy" src="/attach/x.png">');

console.log(`\n通过 ${pass} 项，失败 ${fail} 项`);
process.exit(fail ? 1 : 0);
