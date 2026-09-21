# ponytail-audit · 小煦拾简

> 用 [ponytail](https://github.com/DietrichGebert/ponytail) 的 `ponytail-audit` 技能
> （DSH 移植版：[gongyijie85/dsh-ponytail](https://github.com/gongyijie85/dsh-ponytail)，MIT）
> 做的一次全仓审计。
>
> **审计时间**：2026-09-21（2.4.9 期间）
> **范围**：只查**过度设计**。按该技能自己的边界，
> **正确性 bug / 安全漏洞 / 性能不在范围内** —— 那几项另走 review 流程。
> **本报告只列不删**（技能原文：`Lists findings, applies nothing. One-shot.`）。

---

## 怎么判的

- 死代码 = 一个顶层函数名在整个仓库里**只出现一次**（定义处），
  且不在路由表 / 字典派发 / 字符串引用里被动态调用。
- 函数体行数用**大括号配对**量，不是"到下一个 def" —— 中间夹的注释不算它的。

扫描结果：前端 268 个顶层函数、后端 268 个顶层 `def`。

---

## 发现（按该删的量排序）

| 标签 | 该删什么 | 替换成 | 位置 | 行数 |
|---|---|---|---|---|
| `delete:` | `build_summary` —— Excel 时代"汇总 Sheet"构建器，2.0 换 SQLite 后无人调 | 无 | `server.py:6244` | **166** |
| `delete:` | `_row_payload` —— Excel 行模型转换，同上去世 | 无 | `server.py:1128` | 17 |
| `delete:` | `write_bill_row` —— Excel 写行助手 | 无 | `server.py:2242` | 13 |
| `delete:` | `set_cat_dv` —— Excel 下拉填充 | 无 | `server.py:6463` | 11 |
| `delete:` | `migrate_cats` —— 一次性迁移残留 | 无 | `server.py:6451` | 10 |
| `delete:` | `tail_write` —— Excel 尾款写行助手 | 无 | `server.py:2257` | 8 |
| `delete:` | `_cell_has_value` —— Excel 空格判断 | 无 | `server.py:2171` | 8 |
| `delete:` | `fast_set` —— Excel 快速赋值 | 无 | `server.py:2162` | 7 |
| `delete:` | `emergencyCard` —— 应急信息旧渲染，被表格版取代 | 无 | `static/app.js:2426` | 6 |
| `delete:` | `clockHourNo` —— 算"现在第几小时"，改过时钟卡后没人用 | 无 | `static/core.js:763` | 5 |

```
net: -251 lines, -0 deps possible.
```

**全部是 `delete:`，一条 `stdlib:` / `native:` / `yagni:` / `shrink:` 都没有。**
也就是说这一轮的改动没有引入"只实现一个的接口"、"没人设的配置"、
"只转发的包装"这类过度设计 —— 唯一一处多余抽象
（`markLatinWords` + `.latin` 让长单词横躺）已在 2.4.9 因为你的要求**直接删掉**了。

---

## 复核命令（可自己跑一遍）

```powershell
# 死函数：名字在整个仓库只出现 1 次（定义处）
$names = '_row_payload','fast_set','_cell_has_value','write_bill_row','tail_write',
         'build_summary','migrate_cats','set_cat_dv','clockHourNo','emergencyCard'
foreach ($n in $names) {
  $c = (Get-ChildItem -Recurse -File -Include *.py,*.js -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch 'node_modules|_打包产物|_build' } |
        Select-String -Pattern ("\b" + $n + "\b")).Count
  "$n : $c 处"
}
# 期望：每个都只有 1 处（就是它自己的定义）
```

---

## 没做的（技能的边界，不是遗漏）

- **不删**。等你确认。
- 不查正确性 / 安全 / 性能 —— 本报告明确不管这三项。
- 不改任何功能。
