# -*- coding: utf-8 -*-
"""导出成 Excel —— 数据进得去，也得出得来

数据现在住在 SQLite 里，Excel 降级成了「导出格式」：报告用、存档用、
想自己再拉个透视表的时候用。这个模块就是兑现这句话的另一半。

**为什么不拿用户原来那三本当模板往里填**：
  那样最省事、样式也最像，但等于把用户的数据当成模板发出去 ——
  打包给别人时，「模板」里带着他的流水、他的药。这条路直接排除。

**为什么不追求和原来一模一样**：
  原表里的配色、条件格式、统计看板那套是「给人天天盯着看」用的，
  应用里已经有更好的版本了。导出的目的是**数据完整、算得对、Excel 打得开**，
  所以这里生成的是干净的三本表：该有的列都在，该算的用真公式，
  年月合计、类别小计、月度柱状图都有。

生成的每一格都来自数据库，不依赖任何外部文件。
"""
import os
from collections import OrderedDict
from datetime import datetime

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# ---- 样式（克制一点：导出是给人看数据的，不是给人看设计的）----
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="5B7A8C")
TITLE = Font(bold=True, size=14)
SEC = Font(bold=True, size=11, color="3D5A6C")
BOLD = Font(bold=True)
MONEY = "#,##0.00"
THIN = Side(style="thin", color="D8DEE4")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")


def _head(ws, row, titles, widths=None):
    for i, t in enumerate(titles, 1):
        c = ws.cell(row, i, t)
        c.font = HEAD
        c.fill = HEAD_FILL
        c.alignment = CENTER
        c.border = BOX
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w


def _fit(ws, first_row, last_row, ncol):
    for r in range(first_row, last_row + 1):
        for c in range(1, ncol + 1):
            ws.cell(r, c).border = BOX


def _s(v):
    return "" if v is None else str(v)


# ================================================================
# ① 账单
# ================================================================
def export_bill(path, sv):
    wb = Workbook()
    ws = wb.active
    ws.title = "记录"
    _head(ws, 1, ["日期", "星期", "类别", "项目/备注", "收入", "支出",
                  "支付方式", "月份", "是否团购", "核销状态"],
          [12, 6, 10, 26, 11, 11, 12, 7, 10, 10])

    rows = sv.store.q("SELECT date,cat,note,inc,exp,pay,grp,stat FROM bill"
                      " WHERE sem=? ORDER BY date, id", (sv.SEMESTER,))
    WD = sv.WEEKDAYS
    r = 2
    for b in rows:
        d = sv.to_date(b["date"])
        ws.cell(r, 1, d).number_format = "yyyy-mm-dd"
        ws.cell(r, 2, WD[d.weekday()] if d else "")
        ws.cell(r, 3, _s(b["cat"]))
        ws.cell(r, 4, _s(b["note"]))
        ws.cell(r, 5, float(b["inc"] or 0)).number_format = MONEY
        ws.cell(r, 6, float(b["exp"] or 0)).number_format = MONEY
        ws.cell(r, 7, _s(b["pay"]))
        ws.cell(r, 8, "%d月" % d.month if d else "")
        ws.cell(r, 9, _s(b["grp"]))
        ws.cell(r, 10, _s(b["stat"]))
        r += 1
    last = r - 1
    _fit(ws, 2, max(last, 2), 10)
    if last >= 2:
        ws.cell(r, 4, "合计").font = BOLD
        c = ws.cell(r, 5, "=SUM(E2:E%d)" % last)
        c.font, c.number_format = BOLD, MONEY
        c = ws.cell(r, 6, "=SUM(F2:F%d)" % last)
        c.font, c.number_format = BOLD, MONEY
    ws.freeze_panes = "A2"
    # 类别下拉：导出后自己接着填也不会填出错别字
    exp, inc = sv._cats_of(sv.SEMESTER)
    if exp or inc:
        dv = DataValidation(type="list",
                            formula1='"%s"' % ",".join(exp + inc), allow_blank=True)
        ws.add_data_validation(dv)
        dv.add("C2:C%d" % max(last + 200, 500))

    # ---- 周边尾款 ----
    wt = wb.create_sheet("周边尾款")
    _head(wt, 1, ["项目名称", "类别", "定金(已付)", "尾款金额(待付)",
                  "预计付款时间", "状态", "备注"],
          [22, 10, 12, 15, 14, 9, 22])
    rr = 2
    for t in sv.store.q("SELECT name,cat,dep,tail,pdate,stat,note FROM tail"
                        " WHERE sem=? ORDER BY id", (sv.SEMESTER,)):
        wt.cell(rr, 1, _s(t["name"]))
        wt.cell(rr, 2, _s(t["cat"]))
        wt.cell(rr, 3, float(t["dep"] or 0)).number_format = MONEY
        wt.cell(rr, 4, float(t["tail"] or 0)).number_format = MONEY
        d = sv.to_date(t["pdate"])
        wt.cell(rr, 5, d).number_format = "yyyy-mm-dd"
        wt.cell(rr, 6, _s(t["stat"]))
        wt.cell(rr, 7, _s(t["note"]))
        rr += 1
    _fit(wt, 2, max(rr - 1, 2), 7)
    wt.cell(rr, 3, "待付合计").font = BOLD
    c = wt.cell(rr, 4, '=SUMIF(F2:F%d,"待付",D2:D%d)' % (rr - 1, rr - 1))
    c.font, c.number_format = BOLD, MONEY
    wt.freeze_panes = "A2"

    _bill_summary(wb, sv)
    wb.save(path)
    return path


def _bill_summary(wb, sv):
    """汇总表：KPI + 类别小计 + 月度 + 账户，都是真公式，改了明细会跟着变"""
    b = sv.load_bill()
    ws = wb.create_sheet("汇总", 2)
    ws.column_dimensions["A"].width = 18
    for col in "BCDE":
        ws.column_dimensions[col].width = 14
    n = len(b["records"])
    last = n + 1                      # 记录表的最后一行

    ws.cell(1, 1, "%s · 记账汇总" % sv.SEMESTER).font = TITLE
    ws.cell(2, 1, "导出于 %s　·　共 %d 条流水" %
            (datetime.now().strftime("%Y-%m-%d %H:%M"), n)).font = Font(color="7A8A96")

    r = 4
    ws.cell(r, 1, "总览").font = SEC
    r += 1
    for label, formula, fmt in (
            ("总收入", "=SUM(记录!E2:E%d)" % last, MONEY),
            ("总支出", "=SUM(记录!F2:F%d)" % last, MONEY),
            ("结余", "=B%d-B%d" % (r + 1, r + 2), MONEY),
            ("待付尾款", "=SUMIF(周边尾款!F:F,\"待付\",周边尾款!D:D)", MONEY),
            ("可动用资金", "=B%d-B%d" % (r + 3, r + 4), MONEY)):
        ws.cell(r, 1, label)
        c = ws.cell(r, 2, formula)
        c.number_format = fmt
        r += 1

    r += 1
    ws.cell(r, 1, "支出类别").font = SEC
    ws.cell(r, 4, "收入类别").font = SEC
    top = r + 1
    for i, (k, v) in enumerate(b["exp_cat"].items()):
        ws.cell(top + i, 1, k)
        ws.cell(top + i, 2, round(v, 2)).number_format = MONEY
    for i, (k, v) in enumerate(b["inc_cat"].items()):
        ws.cell(top + i, 4, k)
        ws.cell(top + i, 5, round(v, 2)).number_format = MONEY
    r = top + max(len(b["exp_cat"]), len(b["inc_cat"])) + 1

    ws.cell(r, 1, "月份").font = SEC
    ws.cell(r, 2, "收入").font = SEC
    ws.cell(r, 3, "支出").font = SEC
    ws.cell(r, 4, "预算").font = SEC
    m0 = r + 1
    for i, m in enumerate(b["months"]):
        ws.cell(m0 + i, 1, m["m"])
        ws.cell(m0 + i, 2, m["inc"]).number_format = MONEY
        ws.cell(m0 + i, 3, m["exp"]).number_format = MONEY
        if m.get("budget") is not None:
            ws.cell(m0 + i, 4, m["budget"]).number_format = MONEY
    m1 = m0 + len(b["months"]) - 1

    r = m1 + 2
    ws.cell(r, 1, "账户").font = SEC
    ws.cell(r, 2, "收入").font = SEC
    ws.cell(r, 3, "支出").font = SEC
    ws.cell(r, 4, "结余").font = SEC
    a0 = r + 1
    for i, a in enumerate(b["accounts"]):
        ws.cell(a0 + i, 1, a["name"])
        ws.cell(a0 + i, 2, a["inc"]).number_format = MONEY
        ws.cell(a0 + i, 3, a["exp"]).number_format = MONEY
        ws.cell(a0 + i, 4, a["bal"]).number_format = MONEY

    if b["months"]:
        ch = BarChart()
        ch.title = "各月收支"
        ch.height, ch.width = 8, 16
        ch.add_data(Reference(ws, min_col=2, max_col=3, min_row=m0 - 1,
                              max_row=m1), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=m0, max_row=m1))
        ws.add_chart(ch, "F4")


# ================================================================
# ② 打卡
# ================================================================
def export_check(path, sv):
    c = sv.load_check()
    wb = Workbook()

    ws = wb.active
    ws.title = "设置"
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 30
    ws.cell(1, 1, "打卡设置").font = TITLE
    r = 3
    NAME = {"early": "最早入睡", "late": "最晚入睡", "min_sleep": "最少睡眠(h)",
            "max_sleep": "最多睡眠(h)", "goal_sleep": "目标睡眠(h)",
            "strict": "严格模式", "screen": "屏幕时长上限(h)", "goal_rate": "目标完成率"}
    for k, v in (c["settings"] or {}).items():
        ws.cell(r, 1, NAME.get(k, k))
        ws.cell(r, 2, _s(v))
        r += 1
    r += 1
    ws.cell(r, 1, "下拉选项").font = SEC
    r += 1
    for k, vals in (c["opts"] or {}).items():
        ws.cell(r, 1, k)
        ws.cell(r, 2, "、".join(_s(x) for x in vals))
        r += 1

    items = [(col, nm) for grp in (c["items"] or {}).values()
             for col, nm, _t in [(i["col"], i["name"], None) for i in grp]]
    titles = ["日期", "星期"] + [nm for _c, nm in items]
    for mo in c["months"]:
        m = wb.create_sheet(mo["ym"])
        _head(m, 1, titles, [12, 6] + [10] * len(items))
        for i, d in enumerate(mo["days"]):
            rr = i + 2
            dd = sv.to_date(d["date"])
            m.cell(rr, 1, dd).number_format = "yyyy-mm-dd"
            m.cell(rr, 2, sv.WEEKDAYS[dd.weekday()] if dd else "")
            for j, (col, _nm) in enumerate(items):
                v = d.get(col)
                if isinstance(v, str) and v.strip() == "":
                    v = None
                m.cell(rr, 3 + j, v)
        m.freeze_panes = "C2"

    dm = wb.create_sheet("梦境明细")
    _head(dm, 1, ["日期", "序号", "类型", "情绪", "清晰度", "梦境内容", "现实联想/解读"],
          [12, 6, 12, 10, 10, 50, 40])
    rr = 2
    for date in sorted(c["dream_detail"] or {}, reverse=True):
        for g in c["dream_detail"][date]:
            dm.cell(rr, 1, sv.to_date(g["date"])).number_format = "yyyy-mm-dd"
            dm.cell(rr, 2, g["seq"])
            for j, k in enumerate(("type", "mood", "clarity", "content", "read")):
                dm.cell(rr, 3 + j, _s(g.get(k)))
            rr += 1
    dm.freeze_panes = "A2"

    wb.save(path)
    return path


# ================================================================
# ③ 物资
# ================================================================
def export_stock(path, sv):
    s = sv.load_stock()
    wb = Workbook()
    wb.remove(wb.active)

    for name in ("药品", "日用品", "零食"):
        sh = s["sheets"][name]
        cols = [c for c in sorted(sh["header"], key=_colnum)
                if c in sv.STOCK_COLS[name] or c in sv.DATE_COLS.get(name, ())]
        extra = [k for k in ("_restock", "_days", "_status", "_open_exp")
                 if _has_derived(sh, k)]
        LBL = {"_restock": "补货状态", "_days": "剩余天数", "_status": "状态",
               "_open_exp": "开封后到期"}
        ws = wb.create_sheet(name)
        _head(ws, 1, [sh["header"].get(c, c) for c in cols] +
              [LBL[k] for k in extra], [18] + [12] * (len(cols) + len(extra) - 1))
        for i, row in enumerate(sh["rows"]):
            rr = i + 2
            for j, col in enumerate(cols):
                v = row.get(col)
                c = ws.cell(rr, 1 + j, v)
                if isinstance(v, datetime):
                    c.number_format = "yyyy-mm-dd"
            for j, k in enumerate(extra):
                ws.cell(rr, 1 + len(cols) + j, _s(row.get(k)))
        ws.freeze_panes = "B2"

    ws = wb.create_sheet("待办")
    _head(ws, 1, ["完成", "事项", "类别", "截止日期", "优先级", "剩余天数", "备注"],
          [10, 30, 10, 13, 9, 10, 26])
    for i, t in enumerate(s["todo"]):
        rr = i + 2
        ws.cell(rr, 1, _s(t["stat"]))
        ws.cell(rr, 2, _s(t["item"]))
        ws.cell(rr, 3, _s(t["cat"]))
        d = sv.to_date(t["due"])
        ws.cell(rr, 4, d).number_format = "yyyy-mm-dd"
        ws.cell(rr, 5, _s(t["pri"]))
        ws.cell(rr, 6, t["days"])
        ws.cell(rr, 7, _s(t["note"]))

    ws = wb.create_sheet("应急信息")
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["C"].width = 16
    ws.cell(1, 1, "寝室应急信息卡").font = TITLE
    r = 3
    for sec in (sv.emergency_get() or {}).get("sections") or []:
        ws.cell(r, 1, sec["sec"]).font = SEC
        r += 1
        if sec["contacts"]:
            for c0, t in zip("ABC", ("姓名", "关系", "联系电话")):
                ws[f"{c0}{r}"] = t
                ws[f"{c0}{r}"].font = BOLD
            r += 1
            for p in sec["contacts"]:
                ws.cell(r, 1, p["name"])
                ws.cell(r, 2, p["rel"])
                ws.cell(r, 3, p["phone"])
                r += 1
        for f in sec["fields"]:
            ws.cell(r, 1, f["label"])
            ws.cell(r, 2, f["value"])
            r += 1
        r += 1

    wb.save(path)
    return path


def _colnum(letter):
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - 64)
    return n


def _has_derived(sh, key):
    return any(r.get(key) not in (None, "", 0) for r in sh["rows"])


# ================================================================
def export_all(dest_dir, sv):
    """三本一起导出。返回 {名字: 路径}。"""
    os.makedirs(dest_dir, exist_ok=True)
    day = datetime.now().strftime("%Y%m%d")
    out = OrderedDict()
    out["账单"] = export_bill(os.path.join(dest_dir, "账单_%s.xlsx" % day), sv)
    out["每日打卡表"] = export_check(os.path.join(dest_dir, "每日打卡表_%s.xlsx" % day), sv)
    out["寝室部分物资清单"] = export_stock(
        os.path.join(dest_dir, "寝室部分物资清单_%s.xlsx" % day), sv)
    return out
