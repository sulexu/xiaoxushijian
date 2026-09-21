# 小煦拾简

> 拾寸简以记，沐小煦而行。

一套**装在自己电脑上的**生活记录本。打卡、记账、物资、待办、日记、随笔、回忆书，
都在一个窗口里。数字后端 + 桌面外壳，**零前端依赖**（原生 JS，没有框架、没有打包器）。

## ⬇ 下载

**[小煦拾简 2.5.1 安装包（Windows 64 位，130.8 MB）](https://github.com/sulexu/xiaoxushijian/releases/download/v2.5.1/xiaoxushijian-2.5.1-setup.exe)**

双击 → 一路「下一步」→ 桌面出现「小煦拾简」→ 双击打开。

> 安装包是**空程序**，里面没有任何人的数据。第一次打开会自己建数据库，
> 数据存在你自己电脑上（默认 `文档\小煦拾简\数据\`）。
>
> 所有版本见 [Releases](https://github.com/sulexu/xiaoxushijian/releases)。

---

## 这是什么

一个大学生给自己写的个人生活统计系统。做它的起因很朴素：
**想记账、想打卡、想写日记，但不想把生活交给任何一个 App 的服务器。**

于是有了这个：一个双击就能打开的窗口，数据全在自己的硬盘上。

| 模块 | 干什么 |
|---|---|
| **总览** | 今天该看的一屏：结余、可动用资金、本月支出、今日梦境、待补货、待办、牛马时钟 |
| **账单** | 记账（收入/支出/团购/核销状态）、分类统计、月度图表、环比提醒、从截图记账 |
| **打卡** | 日常打卡项、连续天数、心情记录 |
| **物资** | 药品/日用品/应急信息三张表，库存与过期提醒 |
| **待办** | 类别/优先级/状态/关键词筛选，能加进电脑日历 |
| **日记** | 每日/每周/每月，**古书竖排版式**（界格线、织纹、朱印） |
| **随笔** | 随手记，竖排 |
| **回忆书** | 把日记整理成问答形式回顾 |
| **AI 分析** | 可选：把内容交给 DeepSeek 整理成日报（**不用就不会发出任何东西**） |

---

## ⚠ 数据在哪（重要）

**你的数据不在这个仓库里，也永远不会在。**

这一点是硬约束，不是"尽量"：

- 记账明细、日记、待办、体检记录 —— 全在**你自己电脑上的 SQLite 数据库**里
  （默认在 `文档\小煦拾简\数据\`，路径记在 `%APPDATA%\小煦拾简\数据位置.txt`）
- 仓库里带了 **`.gitignore` + 提交前钩子**两层拦截：
  数据库文件、测试数据副本、Excel 导出、密钥一律进不来
- 钩子还会**扫文件内容**——出现真实消费记录的特征词就拒绝提交

> 用 AI 功能时，**被整理的那段内容**会发去 DeepSeek 处理（日报整理、药品信息、回忆书问答）。
> 不用 AI 就什么都没发出去。

---

## 怎么装

**方式一：安装包**（推荐）

从上面那个 **[下载链接](https://github.com/sulexu/xiaoxushijian/releases/download/v2.5.1/xiaoxushijian-2.5.1-setup.exe)**
拿到 `xiaoxushijian-2.5.1-setup.exe`，双击、一路下一步。

**方式二：免安装**

把整个文件夹拷到哪都能跑，双击里面的 `小煦拾简.exe`。
双击没反应就试 `启动.bat`，再不行用 `浏览器版.bat`（功能一样，只是用浏览器当窗口）。

**方式三：从源码跑**

```bash
python server.py          # 后端起在 http://127.0.0.1:8765
```

然后浏览器打开那个地址。**只需要 Python 3 标准库，不用 pip 装任何东西。**

---

## 技术栈

| 层 | 用了什么 | 为什么 |
|---|---|---|
| 后端 | **Python 3 标准库**（`ThreadingHTTPServer`） | 零依赖。不用 Flask，因为不需要 |
| 存储 | **SQLite**（`store.py`）+ Markdown 文件（`notes.py`） | 单文件、好备份、能直接看 |
| 前端 | **原生 JS**（`core.js` + `app.js`，无框架无构建） | 改完刷新就见效，没有工具链要维护 |
| 图表 | ECharts（本地文件，不是 CDN） | 离线可用 |
| 桌面壳 | Electron | 一个窗口，不要浏览器地址栏 |
| 打包 | PyInstaller（后端）+ electron-builder（外壳） | 出一个 exe |
| 样式 | 手写 CSS + **Tailwind/daisyUI**（渐进迁移中） | 见 `前端重写方案.md` |

**全部离线**：前端没有任何外部 URL（没有 CDN、没有在线字体、没有远程脚本）。
AI 功能是唯一会联网的地方，且必须你自己配 Key。

---

## 界面一瞥

- **七套配色** × **深浅两模式**，颜色全部由变量驱动
  （素纸 / 米黄 / 青瓷 / 墨色 / 樱粉 / 蓝粉 / 藕荷）
- **日记/随笔是古书竖排**：`writing-mode: vertical-rl` + `text-orientation: upright`，
  **所有文字符号都竖排**（含英文和数字），配界格线、织纹、朱印
- **两套自带书法字体**可在设置里换（都是允许再分发的授权）：

  | 字体 | 文件 | 授权 |
  |---|---|---|
  | 瘦金体 | `static/fonts/shoujinti.ttf`（12.1 MB） | **MIT** |
  | 马善政行书 | `static/fonts/mashanzheng.ttf`（5.6 MB） | **OFL** |

  ⚠ 用 `FontFace API` 加载，**不是 CSS `@font-face`** —— 后者在这个项目里会静默失败
  （同样的文件在裸页面能注册、在应用页面注册不上）。见 `项目历程.md` 2.5.1。

- **背景图**：可选，支持填充方式/模糊/遮罩/卡片通透

---

## 文件地图

```
server.py          后端全部路由（约 7000 行）
store.py           SQLite 存储层
notes.py           Markdown 笔记（日记/随笔）
export.py          导出
vision.py          看图录入（调 AI）

static/
  index.html       壳
  core.js          基础设施（必须最先加载）：$ / esc / money / toast / 主题 / 背景 / 字体
  app.js           所有页面
  style.css        手写样式
  _src.css         Tailwind 构建入口（下划线开头 → 不进包）
  tw.css           Tailwind 产物（构建生成，别手改）
  fonts/           两套自带字体
  _test.html       前端回归测试台（350+ 项）
  clock.html       牛马时钟独立小窗

electron/
  main.js          桌面外壳
  preload.js       桥
  package.json     electron-builder 配置

_build/server.spec PyInstaller 配置
```

---

## 开发

**改前端样式**：`static/` 下的文件改完**刷新浏览器**就行。
但如果动了 `class` 里的 Tailwind 原子类，要重新构建：

```bash
npm run css          # 构建 static/tw.css
npm run css:watch    # 监听模式
```

> ⚠ 忘了跑 `npm run css` **不会报错**，只是样式不生效 —— 这是加 Tailwind 的代价。

**测试**（这个项目的测试是认真的，改完必须全跑）：

```bash
# 后端
python _自测.py              # 195 项
python _自测_notes.py        #  79 项
python _自测_加密.py         #  22 项
python _升级校验.py          #  27 项

# 前端（350+ 项，在浏览器里跑）
node _检查测试台.js          # 先查测试台自身语法
# 然后打开 static/_test.html，或：
chrome --headless --dump-dom http://127.0.0.1:8765/static/_test.html

# 针对性的小套件
node _验证安全链接.js        #  24 项
node _验证支出环比.js        #  35 项
node _验证待办筛选.js        #  19 项
node _验证学期汇总.js        #  14 项
node _验证备份目录提示.js     #  10 项
```

**打包**：

```bash
python -m PyInstaller _build/server.spec --noconfirm --distpath _build/dist
cd electron && npx electron-builder --win
```

---

## 设计上踩过的坑（都写在文档里了）

这个项目最值钱的部分不是代码，是**踩过的坑的记录**。定了几条硬规矩：

| 规矩 | 为什么 |
|---|---|
| **不许用 `window.prompt()`** | Electron 16+ 移除了它。浏览器里正常、打包版里**按钮点了完全没反应** |
| **加设置项必须登记进 `SETTINGS_DEFAULTS`** | 不登记会被 `settings_load` 丢掉（`notes_salt` 没登记 → 加密笔记全部打不开） |
| **三套「加载器」必须同步** | `index.html` / `_test.html` / 打包 filter 各有一份文件清单，漏一个就"网页好的、测试台坏的" |
| **`@font-face` 不可靠，用 `FontFace API`** | 静默回退，看着像生效 |
| **背景图靠 `body::before`，所以有背景时 `body` 必须透明** | 负 z-index 的伪元素画在所属元素背景**之下** |
| **Tailwind 不要 preflight** | 这份 CSS 是在没有 reset 的前提下写了 20 个版本的，中途加会把界面弄坏 |
| **daisyUI 全部加 `ds-` 前缀** | 它的 `.hero/.card/.btn` 跟应用的类名撞车，会把布局搞散 |

详细经过见 **`项目历程.md`**（逐版本）和 **`项目交接.md`**（架构与约定）。

---

## 文档

| 文件 | 给谁看 |
|---|---|
| `新手说明.txt` | 讲**怎么上手** |
| `使用说明.txt` | 讲**每个功能的细节** |
| `项目交接.md` | 给**改代码的人**：架构、三条铁律、踩过的坑 |
| `项目历程.md` | **每一版改了什么、为什么**（包括翻车记录） |
| `前端重写方案.md` | Tailwind/daisyUI 迁移的实测根因与进度 |
| `ponytail审计报告.md` | 一次全仓过度设计审计（查出 251 行死代码） |

---

## 授权

代码：你自己用。

**第三方字体**：
- **瘦金体** —— 源自 [`erza-di/shufa-generator`](https://github.com/erza-di/shufa-generator)，
  其 README 注明来自 [`caicaibuchicai/textFont`](https://github.com/caicaibuchicai/textFont)，**MIT**
- **马善政行书** —— [Google Fonts](https://fonts.google.com/specimen/Ma+Shan+Zheng)，**OFL**

两套都是允许打包再分发的授权。授权说明也写在 `static/style.css` 的文件头和
`static/core.js` 的 `DIARY_FONTS` 旁边 —— 以后有人问"这字体哪来的"有据可查。

**第三方库**：ECharts（Apache-2.0）、Tailwind CSS（MIT）、daisyUI（MIT）。
