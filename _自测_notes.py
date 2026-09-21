# -*- coding: utf-8 -*-
"""notes.py 单元测试：周期换算 / 路径安全 / 有效内容判定 / 读写 / 检索 / 待补报告。

跟 _自测.py 分开：那个测的是 HTTP 接口，这个测的是纯存储层（不碰 AI、不起服务）。
跑：python _自测_notes.py
"""
import io
import os
import shutil
import sys
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notes  # noqa: E402

TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_测试副本", "_notes")

_ok = _fail = 0


def ck(label, got, want):
    global _ok, _fail
    if got == want:
        _ok += 1
        print("  [OK]   %s" % label)
    else:
        _fail += 1
        print("  [FAIL] %s\n         得到 %r\n         期望 %r" % (label, got, want))


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP)
    notes.set_root(TMP)

    # ── 周期换算 ────────────────────────────────────────────
    print("=== 周期换算 ===")
    ck("W28 起止", notes.iso_week_range("2026-W28"), (date(2026, 7, 6), date(2026, 7, 12)))
    ck("周一属于哪周", notes.weekly_name(date(2026, 9, 14)), "2026-W38")
    ck("周日归本周", notes.weekly_name(date(2026, 9, 20)), "2026-W38")
    ck("跨年周归 ISO 年", notes.weekly_name(date(2027, 1, 1)), "2026-W53")
    ck("月范围 9 月", notes.month_range("2026-09"), (date(2026, 9, 1), date(2026, 9, 30)))
    ck("闰年 2 月", notes.month_range("2028-02"), (date(2028, 2, 1), date(2028, 2, 29)))
    ck("12 月的下月不进位错",
       notes.month_range("2026-12"), (date(2026, 12, 1), date(2026, 12, 31)))
    ck("跨月周覆盖两个自然月",
       notes.weeks_overlapping_month("2026-09"),
       ["2026-W36", "2026-W37", "2026-W38", "2026-W39", "2026-W40"])
    ck("名称→周期首日", notes.parse_name("weekly", "2026-W38"), date(2026, 9, 14))

    # ── 路径安全（名称直接拼路径，必须挡死）────────────────
    print("=== 路径安全 / 名称校验 ===")
    for kind, bad in [("daily", "../../evil"), ("daily", "..\\evil"),
                      ("daily", "2026-09-15/../x"), ("daily", ""), ("daily", "abc"),
                      ("daily", "2026-9-1"), ("daily", None),
                      ("weekly", "2026-W99"), ("weekly", "2026-W00"),
                      ("weekly", "2026-W54"), ("weekly", "2026-W1"),
                      ("weekly", "2026-09-15"),
                      ("monthly", "2026-13"), ("monthly", "2026-00"), ("monthly", "2026-9")]:
        ck("挡掉 %s %r" % (kind, bad), notes.valid_name(kind, bad), False)
    for kind, good in [("daily", "2026-09-15"), ("weekly", "2026-W01"),
                       ("weekly", "2026-W53"), ("monthly", "2026-09"), ("monthly", "2026-12")]:
        ck("放行 %s %r" % (kind, good), notes.valid_name(kind, good), True)
    # 2025 年只有 52 周，"2025-W53" 不该算出一个 2026 年的日期
    try:
        notes.iso_week_range("2025-W53")
        ck("52 周的年份拒绝 W53", "没抛", "抛了")
    except ValueError:
        ck("52 周的年份拒绝 W53", "抛了", "抛了")
    ck("53 周的年份接受 W53", notes.iso_week_range("2026-W53")[0].year, 2026)
    try:
        notes.note_path("daily", "../evil")
        ck("非法名拼路径会抛错", "没抛", "抛了")
    except ValueError:
        ck("非法名拼路径会抛错", "抛了", "抛了")

    # ── 有效内容判定（决定周报要不要生成）──────────────────
    print("=== 有效内容判定 ===")
    ck("只有标题算空", notes.has_content("# 2026-09-15 日报\n\n"), False)
    ck("多级标题仍算空", notes.has_content("# a\n## b\n### c\n"), False)
    ck("空白算空", notes.has_content("   \n\n"), False)
    ck("None 算空", notes.has_content(None), False)
    ck("有正文算有", notes.has_content("# 标题\n\n今天很累"), True)
    ck("列表算有", notes.has_content("# t\n- 打了球"), True)

    # ── 读写 ────────────────────────────────────────────────
    print("=== 读写 ===")
    notes.write_note("daily", "2026-09-01", "# 2026-09-01 日报\n\n开学第一天。\n")       # W36
    notes.write_note("daily", "2026-09-08", "# 2026-09-08 日报\n\n去图书馆写作业。\n")   # W37
    notes.write_note("daily", "2026-09-15", "# 2026-09-15 日报\n\n今天打了球，很累。\n")  # W38
    notes.write_note("daily", "2026-09-14", "# 2026-09-14 日报\n\n" + "很长的一段。" * 200 + "\n")
    notes.ensure_note("daily", "2026-09-17")
    ck("读回正文", "打了球" in (notes.read_note("daily", "2026-09-15") or ""), True)
    ck("不存在返回 None", notes.read_note("daily", "2020-01-01"), None)
    ck("建空文件带标题", notes.read_note("daily", "2026-09-17"), "# 2026-09-17 日报\n\n")
    ls = notes.list_notes("daily")
    ck("列表按时间倒序", [x["name"] for x in ls],
       ["2026-09-17", "2026-09-15", "2026-09-14", "2026-09-08", "2026-09-01"])
    ck("预览取正文首行",
       [x for x in ls if x["name"] == "2026-09-15"][0]["preview"], "今天打了球，很累。")
    ck("空文件被标记", [x for x in ls if x["name"] == "2026-09-17"][0]["empty"], True)
    notes.ensure_note("daily", "2026-09-15")
    ck("ensure 不覆盖已有",
       notes.read_note("daily", "2026-09-15"), "# 2026-09-15 日报\n\n今天打了球，很累。\n")
    ck("删除", notes.delete_note("daily", "2026-09-17"), True)
    ck("删了就读不到", notes.read_note("daily", "2026-09-17"), None)
    ck("删不存在的返回 False", notes.delete_note("daily", "2020-01-01"), False)

    # ── 检索 ────────────────────────────────────────────────
    print("=== 检索 ===")
    r = notes.search(["球"])
    ck("命中 1 条", len(r), 1)
    ck("命中的是哪篇", r[0]["name"], "2026-09-15")
    ck("带类型标签", r[0]["kind_cn"], "日报")
    ck("多关键词任一命中", len(notes.search(["球", "图书馆"])), 2)
    ck("限定类型查不到", len(notes.search(["球"], kind="weekly")), 0)
    ck("空关键词不返回", notes.search([]), [])
    ck("搜不到就是空", notes.search(["量子力学"]), [])
    ck("英文不分大小写", len(notes.search(["ABC"])), len(notes.search(["abc"])))
    lh = notes.search(["很长"], snippet_width=200)[0]
    ck("超长被截断", lh["truncated"], True)
    ck("截断加省略号", "…" in lh["snippet"], True)
    ck("原文长度照实报", lh["totalCharacters"], len(notes.read_note("daily", "2026-09-14")))
    notes.write_note("weekly", "2026-W37", "# 2026-W37 周报\n\n这周在图书馆待了很久。\n")
    ck("跨类型能搜到 2 条", len(notes.search(["图书馆"])), 2)
    ck("限定 weekly 只 1 条",
       [x["name"] for x in notes.search(["图书馆"], kind="weekly")], ["2026-W37"])

    # ── 相关度排序 ──────────────────────────────────────────
    # 加一篇「只是顺带提一句」的最新日报，验证它不会因为最新就排第一
    print("=== 相关度排序 ===")
    notes.write_note("daily", "2026-09-20",
                     "# 2026-09-20 日报\n\n今天上课，路过图书馆，晚上打游戏。\n")
    notes.write_note("daily", "2026-09-19",
                     "# 2026-09-19 日报\n\n" + "一整天都在图书馆，上午查资料，下午写作业。" * 5 + "\n")
    r = notes.search(["图书馆"])
    print("       " + " | ".join("%s %.2f" % (h["name"], h["score"]) for h in r))
    ck("写得多的排第一（不再是最新那篇第一）", r[0]["name"], "2026-09-19")
    ck("最新但只提一句的排后面", r[-1]["name"], "2026-09-20")
    ck("分数从高到低", all(r[i]["score"] >= r[i + 1]["score"] for i in range(len(r) - 1)), True)
    ck("每条都带 score 字段", all("score" in h for h in r), True)

    print("=== 多命中窗口 ===")
    notes.write_note("daily", "2026-09-18",
                     "# 2026-09-18 日报\n\n早上先跑步了三公里。" +
                     "中间全是无关内容。" * 60 + "晚上睡前又想起跑步的事。\n")
    h = [x for x in notes.search(["跑步"]) if x["name"] == "2026-09-18"][0]
    ck("相隔很远时给 2 个窗口", h["snippet"].count("\n---\n") + 1, 2)
    ck("两处内容都在片段里",
       "跑步了三公里" in h["snippet"] and "又想起跑步" in h["snippet"], True)
    notes.write_note("daily", "2026-09-17",
                     "# 2026-09-17 日报\n\n早上跑步了。" + "中间全是无关内容。" * 30 + "晚上又想起跑步。\n")
    h2 = [x for x in notes.search(["跑步"]) if x["name"] == "2026-09-17"][0]
    ck("相隔很近时合并成 1 段（不给重复内容）", h2["snippet"].count("\n---\n") + 1, 1)
    ck("单个命中只有 1 段",
       [x for x in notes.search(["很长"])][0]["snippet"].count("\n---\n") + 1, 1)

    # ── 待补报告 ────────────────────────────────────────────
    # 此刻 W37 已有内容周报，所以它不该在待补里；W36、W38 该在（9/15 时 W38 未结束）
    print("=== 待补报告（今天=2026-09-15）===")
    p = notes.pending(date(2026, 9, 15))
    print("      weekly  : %s" % p["weekly"])
    print("      monthly : %s" % p["monthly"])
    ck("W38 本周未结束不补", "2026-W38" in p["weekly"], False)
    ck("W36 有来源待补", "2026-W36" in p["weekly"], True)
    ck("W37 已有周报不补", "2026-W37" in p["weekly"], False)
    ck("9 月未过完不补月报", p["monthly"], [])

    print("=== 待补报告（今天=2026-11-01）===")
    notes.write_note("weekly", "2026-W36", "# 2026-W36 周报\n\n这周还行。\n")
    p2 = notes.pending(date(2026, 11, 1))
    print("      weekly  : %s" % p2["weekly"])
    print("      monthly : %s" % p2["monthly"])
    ck("已有周报不再待补", "2026-W36" in p2["weekly"], False)
    ck("月报从周报日期范围推（不是切字符串）", "2026-09" in p2["monthly"], True)
    ck("跨月周也归 8 月", "2026-08" in p2["monthly"], True)
    notes.write_note("monthly", "2026-08", "# 2026-08 月报\n\n八月总结。\n")
    ck("已有月报不再待补",
       "2026-08" in notes.pending(date(2026, 11, 1))["monthly"], False)

    # ── 目录形状 ────────────────────────────────────────────
    print("=== 目录形状 ===")
    got = {d: sorted(os.listdir(os.path.join(TMP, d))) for d in sorted(os.listdir(TMP))}
    for d, files in got.items():
        print("      %s/  %s" % (d, files))
    ck("三个子目录都在", sorted(got.keys()), ["周报", "日报", "月报"])
    ck("没有临时文件残留", [f for fs in got.values() for f in fs if f.endswith(".tmp")], [])

    shutil.rmtree(TMP, ignore_errors=True)
    print("\n通过 %d 项，失败 %d 项" % (_ok, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
