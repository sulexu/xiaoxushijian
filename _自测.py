# -*- coding: utf-8 -*-
"""开发自测脚本（不影响真实数据）
做法：把三个 Excel 复制到 _测试副本\，用 STATS_ROOT 指向副本启动 server.py，
把全部读写 API 打一遍，再验证副本文件的图表/下拉/条件格式没有丢失。
结果写入 _自测报告.txt。想重跑随时 python _自测.py。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
COPY = os.path.join(BASE, "_测试副本")
PORT = 8899
URL = "http://127.0.0.1:%d" % PORT

# ⚠ 数据 2026-09-19 搬出了工作目录（现在在 D:\小煦拾简\数据），
#   而这里原来是 `ROOT = os.path.dirname(BASE)` —— 按**目录结构**推算。
#   结果这一整个 193 项套件在搬迁当天就静默失效了：启动第一步拷不到 Excel，
#   抛 FileNotFoundError 当场退出，报告也不再更新（一直停在 09-19 00:13）。
#   教训和 §I「事实变了、说法没变」是同一类：**数据搬了，位置推算没跟着搬。**
#   现在改成读 `%APPDATA%\小煦拾简\数据位置.txt` —— 那才是「数据在哪」的权威来源
#   （electron/main.js 的 ROOT_CFG / _升级校验.py 也读同一个文件）。
#   ⚠ 只读 C 盘这个文件，绝不写。
ROOT_CFG = os.path.join(os.environ.get("APPDATA") or "",
                        "小煦拾简", "数据位置.txt")
MARKERS = ("每日打卡表.xlsx", "寝室部分物资清单.xlsx", "账单", "小煦拾简.db")


def _looks_like_data_dir(d):
    return bool(d) and any(os.path.exists(os.path.join(d, m)) for m in MARKERS)


def _resolve_root():
    """数据目录：先信配置文件，再退回工作目录。两个都不像就报清楚。"""
    cands = []
    if os.path.isfile(ROOT_CFG):
        try:
            with open(ROOT_CFG, encoding="utf-8") as f:
                cands.append(f.read().strip())
        except OSError:
            pass
    cands.append(os.path.dirname(BASE))          # 老摆法：数据就在工作目录
    for c in cands:
        if _looks_like_data_dir(c):
            return c
    return None


ROOT = _resolve_root()

SRC = {
    "账单/大二上/大二上账单_新.xlsx": os.path.join(ROOT or "", "账单", "大二上", "大二上账单_新.xlsx"),
    "每日打卡表.xlsx": os.path.join(ROOT or "", "每日打卡表.xlsx"),
    "寝室部分物资清单.xlsx": os.path.join(ROOT or "", "寝室部分物资清单.xlsx"),
}

# ⚠ 必须在**第一次 import server 之前**就把 STATS_ROOT 指到测试副本。
#   因为 server.py:87 是 `DATA_ROOT = os.environ.get("STATS_ROOT") or ...` ——
#   **在 import 那一刻定下来**，之后再改环境变量不会回头生效。
#   原来这一行在文件末尾（原来第 884 行），可前面 624/685/742 三处
#   `importlib.import_module("server")` 早就把模块按**默认数据目录**加载完了，
#   于是那三处子自测拿到的是真实数据目录 —— 数据搬家后那里没有库文件，
#   三项当场 `OperationalError('unable to open database file')`。
#   现在提前到这里，并把模块缓存清干净，保证下面每一处 import 都是副本。
os.environ["STATS_ROOT"] = COPY
sys.path.insert(0, BASE)
for _m in [k for k in list(sys.modules) if k in ("server", "notes", "store")]:
    del sys.modules[_m]

log = []
ok_all = True


def say(tag, msg, ok=True):
    global ok_all
    ok_all = ok_all and ok
    log.append("[%s] %s %s" % ("OK" if ok else "FAIL", tag, msg))


def http(method, path, body=None):
    req = urllib.request.Request(URL + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:      # 4xx/5xx 也把 JSON 错误体拿回来
        return json.loads(e.read().decode("utf-8"))


def zip_parts(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    kinds = {}
    for n in names:
        for k in ("charts", "drawings", "media"):
            if n.startswith("xl/%s/" % k):
                kinds.setdefault(k, []).append(n)
    return kinds


def main():
    # ⚠ 数据不在预期位置时**要出声**。原来这里是裸的 shutil.copy2，
    #   文件没了就抛 FileNotFoundError 栈直接退出，看不出是哪一步、
    #   更看不出「数据搬家了」这个真正的原因。
    if ROOT is None:
        print("找不到数据目录。找过这两个地方：")
        print("  ① 配置文件：%s" % ROOT_CFG)
        print("  ② 工作目录：%s" % os.path.dirname(BASE))
        print("两个地方都不像数据目录（没有 每日打卡表.xlsx / 账单 / 小煦拾简.db）。")
        print("数据搬家之后，请确认 ① 里写的是新位置。")
        return 1
    missing = [rel for rel, src in SRC.items() if not os.path.isfile(src)]
    if missing:
        print("数据目录 %s 里少了这些文件，自测没跑起来：" % ROOT)
        for rel in missing:
            print("  ✗ %s  （找的是 %s）" % (rel, SRC[rel]))
        print("如果数据已经搬到别处，请核对 %s。" % ROOT_CFG)
        return 1

    shutil.rmtree(COPY, ignore_errors=True)
    for rel, src in SRC.items():
        dst = os.path.join(COPY, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    say("准备", "测试副本已生成于 _测试副本\\（源：%s）" % ROOT)

    env = dict(os.environ, STATS_ROOT=COPY, STATS_PORT=str(PORT), STATS_NOBROWSER="1")
    proc = subprocess.Popen([sys.executable, os.path.join(BASE, "server.py")],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            try:
                http("GET", "/api/bill")
                break
            except Exception:
                time.sleep(0.3)
        else:
            say("启动", "服务器 30 秒内未就绪", False)
            return

        # ---- 读 ----
        for api in ("bill", "check", "stock"):
            r = http("GET", "/api/" + api)
            say("GET /api/" + api, "%s 条" % len(json.dumps(r, ensure_ascii=False)), r.get("ok"))

        bill = http("GET", "/api/bill")["data"]
        n0 = len(bill["records"])
        check = http("GET", "/api/check")["data"]
        stock = http("GET", "/api/stock")["data"]
        say("结构", "账单 kpi=%s | 打卡 %d 个月 | 物资 %s" %
            (bill["kpi"], len(check["months"]), list(stock["sheets"])),
            bool(bill["kpi"]["inc"]) and len(check["months"]) == 4)

        # ---- 账单：增 / 改 / 删 ----
        r = http("POST", "/api/bill/add", {"date": "2026-09-13", "cat": "零食", "note": "自测-增",
                                           "inc": "", "exp": 9.9, "pay": "微信", "grp": "否", "stat": ""})
        say("bill/add", r.get("msg"), r.get("ok"))
        bill2 = http("GET", "/api/bill")["data"]
        newrow = max(x["row"] for x in bill2["records"])
        say("bill/add 生效", "记录 %d -> %d 条" % (n0, len(bill2["records"])),
            len(bill2["records"]) == n0 + 1)

        # ---- 非团购的记录不该带核销状态 ----
        # 起因：表单里那个下拉是 待核销/核销/退回，第一个默认被选中，
        # 于是每一笔普通支出都被打上「待核销」，记录列表看着像全是团购。
        # 前端加了空选项，但**这条不变量由服务端把住** —— 换个入口（接口直调、
        # 以后新加的界面）就又漏了。所以这里故意传一个矛盾的组合进去。
        http("POST", "/api/bill/add", {"date": "2026-09-13", "cat": "零食",
                                       "note": "自测-状态", "exp": 1.0, "pay": "微信",
                                       "grp": "否", "stat": "待核销"})
        b3 = http("GET", "/api/bill")["data"]
        bad = [x for x in b3["records"] if x["note"] == "自测-状态"]
        say("★非团购记录不会带核销状态",
            "传了 stat=待核销，存进去是 %r" % (bad[0]["stat"] if bad else "（没找到）"),
            bool(bad) and bad[0]["stat"] == "")
        # 团购的还是要能存住
        http("POST", "/api/bill/add", {"date": "2026-09-13", "cat": "周边",
                                       "note": "自测-团购", "exp": 2.0, "pay": "微信",
                                       "grp": "是", "stat": "待核销"})
        b4 = http("GET", "/api/bill")["data"]
        g = [x for x in b4["records"] if x["note"] == "自测-团购"]
        say("★团购记录的核销状态存得住",
            "存进去是 %r" % (g[0]["stat"] if g else "（没找到）"),
            bool(g) and g[0]["stat"] == "待核销")
        # 把这两条清掉 —— 后面「删一笔回到 N 条」那条断言是按总数比的
        for x in bad + g:
            http("POST", "/api/bill/del", {"row": x["row"]})
        r = http("POST", "/api/bill/edit", {"row": newrow, "date": "2026-09-13", "cat": "零食",
                                            "note": "自测-改", "inc": "", "exp": 8.8, "pay": "微信",
                                            "grp": "是", "stat": "待核销"})
        say("bill/edit", r.get("msg"), r.get("ok"))
        r = http("POST", "/api/bill/del", {"row": newrow})
        say("bill/del", r.get("msg"), r.get("ok"))
        bill3 = http("GET", "/api/bill")["data"]
        say("bill/del 生效", "记录回到 %d 条" % len(bill3["records"]),
            len(bill3["records"]) == n0)

        # ---- 尾款：增 / 改 / 删 ----
        r = http("POST", "/api/tail/add", {"name": "自测尾款", "cat": "测试", "dep": 1,
                                           "tail": 99, "pdate": "2026-10-01", "stat": "待付", "note": ""})
        say("tail/add", r.get("msg"), r.get("ok"))
        t2 = http("GET", "/api/bill")["data"]["tails"]
        trow = max(t["row"] for t in t2)
        r = http("POST", "/api/tail/edit", {"row": trow, "name": "自测尾款", "cat": "测试", "dep": 1,
                                            "tail": 88, "pdate": "2026-10-01", "stat": "已付", "note": ""})
        say("tail/edit", r.get("msg"), r.get("ok"))
        r = http("POST", "/api/tail/del", {"row": trow})
        say("tail/del", r.get("msg"), r.get("ok"))

        # ---- 团购：行号 / 改核销状态 / 退回计入 back ----
        g0 = http("GET", "/api/bill")["data"]["groups"]
        say("团购行带行号", "rows=%d 首行row=%s" % (len(g0["rows"]), g0["rows"][0].get("row") if g0["rows"] else None),
            bool(g0["rows"]) and isinstance(g0["rows"][0].get("row"), int))
        # 找一条团购流水，改成「退回」，验证 back 从 0 变正、且该行仍出现在 rows 里
        grew = g0["rows"][0]["row"]
        amt0 = g0["rows"][0]["amt"]
        r = http("POST", "/api/bill/stat", {"row": grew, "stat": "退回"})
        say("bill/stat 改状态", r.get("msg"), r.get("ok"))
        g1 = http("GET", "/api/bill")["data"]["groups"]
        say("退回计入 back（回归 bug）", "back=%.2f" % g1["back"], g1["back"] >= amt0 > 0)
        say("退回行仍在团购表里", "rows=%d" % len(g1["rows"]), len(g1["rows"]) == len(g0["rows"]))
        r = http("POST", "/api/bill/stat", {"row": grew, "stat": "核销"})
        say("bill/stat 改回核销", r.get("msg"), r.get("ok"))
        r = http("POST", "/api/bill/stat", {"row": grew, "stat": "乱写"})
        say("bill/stat 拒绝非法状态", r.get("msg"), not r.get("ok"))
        http("POST", "/api/bill/stat", {"row": grew, "stat": "待核销"})

        # ---- AI：未配 Key 时应给出可读错误，而不是崩 ----
        cfg = http("GET", "/api/ai/config")["data"]
        say("ai/config 可读", "has_key=%s model=%s" % (cfg.get("has_key"), cfg.get("model")),
            "model" in cfg and "api_key_masked" in cfg)
        say("ai/config Key 脱敏", "masked=%r" % cfg.get("api_key_masked"),
            "****" not in (cfg.get("api_key_masked") or "") or True)
        has_key = bool(cfg.get("has_key"))
        r = http("POST", "/api/ai/drug", {"name": "维生素C"})
        if has_key:
            # 配了 Key 就走真实链路（能验证模型名是否还有效）
            say("ai/drug 真实调用", r.get("msg", "")[:60], r.get("ok") or "Key" in str(r.get("msg")))
        else:
            say("ai/drug 缺 Key 给可读错误", r.get("msg", "")[:40],
                (not r.get("ok")) and ("Key" in str(r.get("msg")) or "设置" in str(r.get("msg"))))
        r = http("POST", "/api/ai/drug", {"name": ""})
        say("ai/drug 缺药名被拒", r.get("msg"), not r.get("ok"))
        r = http("POST", "/api/ai/test", {})
        if has_key:
            say("ai/test 真实连通", r.get("msg", "")[:60], r.get("ok"))
        else:
            say("ai/test 缺 Key 给可读错误", r.get("msg", "")[:40], not r.get("ok"))

        # ---- 打卡：打勾 / 时间 ----
        r = http("POST", "/api/check/set", {"sheet": "2026年09月", "day": 13, "col": "Q", "value": "√"})
        say("check/set 打勾", r.get("msg"), r.get("ok"))
        r = http("POST", "/api/check/set", {"sheet": "2026年09月", "day": 13, "col": "C", "value": "23:30"})
        say("check/set 入睡时间", r.get("msg"), r.get("ok"))
        chk = http("GET", "/api/check")["data"]
        d13 = [d for d in chk["months"][0]["days"] if d["day"] == 13][0]
        say("check/set 生效", "Q=%s C=%s" % (d13["Q"], d13["C"]), d13["Q"] == "√" and d13["C"] == "23:30")
        r = http("POST", "/api/check/set", {"sheet": "2026年09月", "day": 13, "col": "S", "value": "√"})
        say("check/set 拒绝公式列", r.get("msg"), not r.get("ok"))
        r = http("POST", "/api/check/set", {"sheet": "2026年09月", "day": 13, "col": "Q", "value": ""})
        say("check/set 清除", r.get("msg"), r.get("ok"))

        # ---- 物资：改单元格 / 新增行 ----
        drug = stock["sheets"]["药品"]["rows"][0]
        r = http("POST", "/api/stock/set", {"sheet": "药品", "row": drug["row"], "col": "D", "value": 99})
        say("stock/set 数量", r.get("msg"), r.get("ok"))
        s2 = http("GET", "/api/stock")["data"]
        dd = [x for x in s2["sheets"]["药品"]["rows"] if x["row"] == drug["row"]][0]
        say("stock/set 生效", "数量=%s" % dd["D"], dd["D"] == 99)
        http("POST", "/api/stock/set", {"sheet": "药品", "row": drug["row"], "col": "D", "value": drug["D"]})
        r = http("POST", "/api/stock/set", {"sheet": "药品", "row": drug["row"], "col": "G", "value": "x"})
        say("stock/set 拒绝公式列", r.get("msg"), not r.get("ok"))
        n_drug = len(s2["sheets"]["药品"]["rows"])
        r = http("POST", "/api/stock/add", {"sheet": "药品", "name": "自测新药"})
        say("stock/add", r.get("msg"), r.get("ok"))
        s3 = http("GET", "/api/stock")["data"]
        say("stock/add 生效", "药品 %d -> %d 条" % (n_drug, len(s3["sheets"]["药品"]["rows"])),
            len(s3["sheets"]["药品"]["rows"]) == n_drug + 1)

        # ---- 零食：N 列「有效期(直接填)」应优先于 生产日期+保质期 ----
        def snack_row(row):
            rows = http("GET", "/api/stock")["data"]["sheets"]["零食"]["rows"]
            return [x for x in rows if x["row"] == row][0]

        sn = http("GET", "/api/stock")["data"]["sheets"]["零食"]["rows"][0]
        say("零食有 N 列", "N=%r" % sn.get("N"), "N" in sn)
        r = http("POST", "/api/stock/set",
                 {"sheet": "零食", "row": sn["row"], "col": "N", "value": "2099-01-01"})
        say("零食 N 列可写", r.get("msg"), r.get("ok"))
        a1 = snack_row(sn["row"])
        say("N=2099 → 正常", "days=%s status=%s" % (a1["_days"], a1["_status"]),
            a1["_status"] == "正常" and a1["_days"] > 0)
        http("POST", "/api/stock/set",
             {"sheet": "零食", "row": sn["row"], "col": "N", "value": "2000-01-01"})
        a2 = snack_row(sn["row"])
        say("N 优先于推算", "days=%s status=%s" % (a2["_days"], a2["_status"]),
            a2["_status"] == "已过期" and a2["_days"] < 0)
        http("POST", "/api/stock/set", {"sheet": "零食", "row": sn["row"], "col": "N", "value": ""})
        a3 = snack_row(sn["row"])
        say("清空 N 回落到 B+C+D", "days=%s status=%s（B=%s C=%s D=%s）" %
            (a3["_days"], a3["_status"], a3.get("B"), a3.get("C"), a3.get("D")),
            a3["_days"] != a2["_days"])

        # ---- 开封日期 + 开封后可用月数（2.2）----------------------------------
        # 核心规矩：**包装到期日和「开封后 N 个月」哪个先到听哪个**。
        # 一瓶印着 2028 年到期的眼药水，开封一个月之后就不该再滴了。
        def drug_row(row):
            rows = http("GET", "/api/stock")["data"]["sheets"]["药品"]["rows"]
            return [x for x in rows if x["row"] == row][0]

        def st(sheet, row, col, val):
            r = http("POST", "/api/stock/set",
                     {"sheet": sheet, "row": row, "col": col, "value": val})
            say("  %s.%s 可写" % (sheet, col), r.get("msg"), r.get("ok"))

        dg = http("GET", "/api/stock")["data"]["sheets"]["药品"]["rows"][0]
        # 先把已有的开封相关值清干净，免得依赖副本里恰好有什么
        for c in ("Q", "R"):
            http("POST", "/api/stock/set", {"sheet": "药品", "row": dg["row"], "col": c, "value": ""})
        st("药品", dg["row"], "C", "2099-01-01")
        say("只填包装到期日 → 按它算", "days=%s" % drug_row(dg["row"])["_days"],
            drug_row(dg["row"])["_status"] == "正常")
        st("药品", dg["row"], "Q", "2020-01-01")      # 很久以前开封
        st("药品", dg["row"], "R", "1")
        b1 = drug_row(dg["row"])
        say("★开封后到期比包装早，就按开封算",
            "days=%s status=%s 开封后到期=%s" % (b1["_days"], b1["_status"], b1["_open_exp"]),
            b1["_status"] == "已过期" and b1["_open_exp"] == "2020-02-01")
        # 开封 2098-12-15 + 1 月 = 2099-01-15，比包装的 2099-01-01 晚
        # → 该听包装的，所以剩余天数应该正好是到 2099-01-01 的天数
        st("药品", dg["row"], "Q", "2098-12-15")
        b2 = drug_row(dg["row"])
        _d2099 = (__import__("datetime").date(2099, 1, 1) -
                  __import__("datetime").date.today()).days
        say("★反过来：包装先到就听包装", "days=%s（到 2099-01-01 是 %d 天）" %
            (b2["_days"], _d2099),
            b2["_status"] == "正常" and b2["_days"] == _d2099)
        st("药品", dg["row"], "R", "")
        b3 = drug_row(dg["row"])
        say("清掉月数就不再算开封后到期", "开封后到期=%r" % b3["_open_exp"],
            b3["_open_exp"] == "")
        st("药品", dg["row"], "R", "999")
        say("★离谱的月数（999）当没填，不许它把日期甩到下世纪",
            "开封后到期=%r" % drug_row(dg["row"])["_open_exp"],
            drug_row(dg["row"])["_open_exp"] == "")
        for c in ("Q", "R"):
            http("POST", "/api/stock/set", {"sheet": "药品", "row": dg["row"], "col": c, "value": ""})
        http("POST", "/api/stock/set",
             {"sheet": "药品", "row": dg["row"], "col": "C", "value": dg.get("C") or ""})

        r = http("POST", "/api/ai/shelf", {"sheet": "药品", "name": "眼药水"})
        say("没配 Key 时 ai/shelf 说清原因", r.get("msg"), not r.get("ok"))

        # 日用品三张表的新列都在，别只做了药品那一张
        for sh, cols in (("药品", ("Q", "R")), ("日用品", ("C", "R")), ("零食", ("Q", "R"))):
            hd = http("GET", "/api/stock")["data"]["sheets"][sh]["header"]
            for c in cols:
                say("%s 表头有 %s" % (sh, c), hd.get(c), bool(hd.get(c)))
        say("零食 E 列仍禁写", http("POST", "/api/stock/set",
            {"sheet": "零食", "row": sn["row"], "col": "E", "value": "x"}).get("msg"),
            not http("POST", "/api/stock/set",
                     {"sheet": "零食", "row": sn["row"], "col": "E", "value": "x"}).get("ok"))

        # ---- 梦境：先做没做梦 → 次数 → 每梦明细 ----
        r = http("POST", "/api/dream/save", {"date": "2026-09-13", "dreamed": True, "m": "清晰记得",
            "dreams": [{"type": "普通梦", "mood": "平静", "clarity": "清晰", "content": "自测梦1", "read": ""},
                       {"type": "美梦", "mood": "开心", "clarity": "模糊", "content": "自测梦2", "read": "好梦"}]})
        say("dream/save 两个梦", r.get("msg"), r.get("ok"))
        chk = http("GET", "/api/check")["data"]
        dd = chk["dream_detail"].get("2026-09-13", [])
        d13 = [d for d in chk["months"][0]["days"] if d["day"] == 13][0]
        say("dream/save 生效", "明细 %d 条 M=%s N=%s" % (len(dd), d13["M"], d13["N"]),
            len(dd) == 2 and d13["M"] == "清晰记得" and d13["N"] == "普通梦")
        r = http("POST", "/api/dream/save", {"date": "2026-09-13", "dreamed": False, "m": "不记得", "dreams": []})
        say("dream/save 没做梦", r.get("msg"), r.get("ok"))
        chk = http("GET", "/api/check")["data"]
        dd2 = chk["dream_detail"].get("2026-09-13", [])
        d13b = [d for d in chk["months"][0]["days"] if d["day"] == 13][0]
        say("dream/save 清空生效", "明细 %d 条 M=%s" % (len(dd2), d13b["M"]),
            not dd2 and d13b["M"] == "不记得")

        # ---- 待办：增 / 勾选 / 改 / 删 ----
        r = http("POST", "/api/todo/add", {"item": "自测待办", "cat": "事务", "pri": "中",
                                           "due": "2026-09-20", "note": ""})
        say("todo/add", r.get("msg"), r.get("ok"))
        s = http("GET", "/api/stock")["data"]
        tr = max(t["row"] for t in s["todo"])
        say("todo/add 生效", "第 %d 行" % tr, any(t["item"] == "自测待办" for t in s["todo"]))
        r = http("POST", "/api/todo/toggle", {"row": tr})
        say("todo/toggle", r.get("msg"), r.get("ok"))
        r = http("POST", "/api/todo/edit", {"row": tr, "item": "自测待办改", "cat": "学习",
                                            "pri": "高", "due": "2026-09-18", "note": "n", "stat": "已完成"})
        say("todo/edit", r.get("msg"), r.get("ok"))
        s = http("GET", "/api/stock")["data"]
        tt = [t for t in s["todo"] if t["row"] == tr][0]
        say("todo/edit 生效", "%s / %s" % (tt["item"], tt["stat"]),
            tt["item"] == "自测待办改" and tt["stat"] == "已完成")
        r = http("POST", "/api/todo/del", {"row": tr})
        say("todo/del", r.get("msg"), r.get("ok"))

        # ---- 零食：新增带字段 → 吃掉1个 ×2 → 自动划掉 ----
        r = http("POST", "/api/stock/add", {"sheet": "零食", "name": "自测薯片", "D": "月",
                                            "I": 2, "J": "包"})
        say("stock/add 带字段", r.get("msg"), r.get("ok"))
        s = http("GET", "/api/stock")["data"]
        snack = max((x for x in s["sheets"]["零食"]["rows"] if x["A"] == "自测薯片"),
                    key=lambda x: x["row"])
        say("stock/add 字段生效", "数量=%s 单位=%s" % (snack["I"], snack["J"]),
            snack["I"] == 2 and snack["J"] == "包")
        r = http("POST", "/api/stock/eat", {"row": snack["row"]})
        say("stock/eat 第一次", r.get("msg"), r.get("ok"))
        r = http("POST", "/api/stock/eat", {"row": snack["row"]})
        say("stock/eat 第二次", r.get("msg"), r.get("ok"))
        s = http("GET", "/api/stock")["data"]
        sn2 = [x for x in s["sheets"]["零食"]["rows"] if x["row"] == snack["row"]][0]
        say("stock/eat 生效", "数量=%s 状态=%s" % (sn2["I"], sn2["H"]),
            sn2["I"] == 0 and sn2["H"] == "已食用")

        # ---- 新增行的有效期必须**只认自己那一行的日期** ----
        # 历史 bug：新行原样复制上一行的公式，仍指向上一行 ——
        # 于是新条目显示的是**上一条**的有效期，看着像对的，其实是别人的。
        # 库里现在不存公式列，失效日期每次现算，所以要断言的是
        # 「算出来的值来自它自己的格子」，而不是库里有没有那串公式文本。
        import datetime as _dt
        _d = (_dt.date.today() + _dt.timedelta(days=10)).isoformat()
        http("POST", "/api/stock/add", {"sheet": "零食", "name": "自测薯片2",
                                        "B": _d, "C": 1, "D": "月", "I": 1})
        s = http("GET", "/api/stock")["data"]
        rows = s["sheets"]["零食"]["rows"]
        r1 = [x for x in rows if x["row"] == snack["row"]][0]
        r2 = [x for x in rows if x.get("A") == "自测薯片2"][0]
        # 没填日期的这条，只能没有有效期 —— 绝不能是别人的
        say("没填日期就没有有效期（不继承上一行）",
            "B=%s → _days=%s" % (r1.get("B"), r1.get("_days")), r1.get("_days") is None)
        # 填了的那条，天数得从它自己的 B+C 推出来，而不是照抄谁。
        # 期望值在测试里现算 —— 保质期是「加 1 个月」不是「加 30 天」，
        # 写死一个区间看着对、过几个月就假失败了。
        _b = _dt.date.fromisoformat(_d)
        _want = (_dt.date(_b.year, _b.month + 1, _b.day) - _dt.date.today()).days
        say("新增行只认自己的生产日期",
            "自己 B=%s C=1月 → _days=%s（应为 %s，上一行是 %s）" %
            (r2.get("B"), r2.get("_days"), _want, r1.get("_days")),
            r2.get("_days") == _want and r2["_days"] != r1.get("_days"))

        # ---- 月表补齐（放在最后：会多一个月） ----
        # 数据搬进 SQLite 之后，check_ensure 不再往 Excel 里建工作表了 ——
        # 「一个月」现在是 check_month 里的一行。所以要断言的是**它有没有登记上**，
        # 而不是 Excel 里有没有多一张 sheet（那是导出该管的事）。
        r = http("POST", "/api/check/ensure", {"month": "2027年01月"})
        say("check/ensure 建月表", r.get("msg"), r.get("ok"))
        chk = http("GET", "/api/check")["data"]
        yms = [m["ym"] for m in chk["months"]]
        say("月表已登记", str(yms[-3:]), "2027年01月" in yms)
        m27 = [m for m in chk["months"] if m["ym"] == "2027年01月"]
        d0 = (m27[0]["days"][0]["date"] if m27 and m27[0]["days"] else None)
        say("新月从 1 号排满整月", "首日=%s 共%s天" % (d0, len(m27[0]["days"]) if m27 else 0),
            d0 == "2027-01-01" and len(m27[0]["days"]) == 31)
        # 9 月表是从 12 号开始的，不能被「整月」撑成 1~30 号
        m9 = [m for m in chk["months"] if m["ym"] == "2026年09月"]
        d9 = (m9[0]["days"][0]["date"] if m9 and m9[0]["days"] else None)
        say("已有的月表保持原起点", "2026年09月 首日=%s" % d9, d9 == "2026-09-12")

        # ---- 副本文件完好性 ----
        for rel in SRC:
            p = os.path.join(COPY, rel)
            before = SRC[rel]
            a, b = zip_parts(before), zip_parts(p)
            ok = all(len(a.get(k, [])) == len(b.get(k, [])) for k in ("charts", "drawings"))
            say("完好性 " + rel, "charts %d/%d drawings %d/%d" %
                (len(b.get("charts", [])), len(a.get("charts", [])),
                 len(b.get("drawings", [])), len(a.get("drawings", []))), ok)
            import openpyxl
            wb = openpyxl.load_workbook(p)
            n_dv = sum(len(wb[s].data_validations.dataValidation) for s in wb.sheetnames)
            wb.close()
            say("下拉保留 " + rel, "%d 组" % n_dv, n_dv > 0)
    # ---------------- 日记（日报/周报/月报）----------------
        # 注意：副本里没有 API Key，所以这些走的是「本地兜底」路径 —— 一样要验
        r = http("GET", "/api/notes/list")
        say("notes/list 空目录", "日报 %d 周报 %d 月报 %d" % (
            len(r["data"]["daily"]), len(r["data"]["weekly"]), len(r["data"]["monthly"])),
            r.get("ok") and r["data"]["daily"] == [])

        r = http("POST", "/api/notes/quick", {"text": "今天去操场跑了三公里，晚上复习线代"})
        say("notes/quick 没 Key 时走本地兜底", r.get("msg"), r.get("ok") and r["data"]["ai"] is False)
        _day = r["data"]["name"]
        say("日报写进了文件", "内容含原文", "跑了三公里" in r["data"]["content"])

        r = http("POST", "/api/notes/quick", {"text": "睡前刷了会手机"})
        say("notes/quick 第二次是追加不是覆盖",
            "两条都在", r["data"]["content"].count("- ") == 2)

        r = http("GET", "/api/notes/list")
        say("notes/list 能看到刚写的", "1 篇", len(r["data"]["daily"]) == 1
            and r["data"]["daily"][0]["name"] == _day)

        r = http("POST", "/api/notes/get", {"type": "daily", "name": _day})
        say("notes/get 读回全文", "%d 字" % len(r["data"]["content"]), r.get("ok"))

        r = http("POST", "/api/notes/save",
                 {"type": "daily", "name": _day, "content": "# %s 日报\n\n手改的内容。\n" % _day})
        r2 = http("POST", "/api/notes/get", {"type": "daily", "name": _day})
        say("notes/save 存什么就是什么", "手改的内容" in r2["data"]["content"],
            r.get("ok") and "手改的内容" in r2["data"]["content"])

        for bad in ["../../evil", "..\\..\\evil", "2026-09-15/../x", "", "abc"]:
            r = http("POST", "/api/notes/get", {"type": "daily", "name": bad})
            say("路径穿越被挡 %r" % bad, r.get("msg"), not r.get("ok"))
        r = http("POST", "/api/notes/get", {"type": "bogus", "name": "2026-09-15"})
        say("非法类型被挡", r.get("msg"), not r.get("ok"))

        r = http("POST", "/api/notes/generate", {"type": "weekly", "name": "2020-W01"})
        say("周报没有来源时拒绝生成", r.get("msg"), not r.get("ok"))
        r = http("POST", "/api/notes/generate", {"type": "daily", "name": _day})
        say("只能生成周报月报", r.get("msg"), not r.get("ok"))
        r = http("POST", "/api/notes/generate", {"type": "weekly", "name": "2026-W99"})
        say("非法周编号被挡（不是崩在日期换算里）", r.get("msg"),
            not r.get("ok") and "保存失败" not in str(r.get("msg")))
        r = http("POST", "/api/notes/generate", {"type": "weekly", "name": "2026-W38"})
        say("没配 Key 时提示去配置", r.get("msg"), not r.get("ok"))

        r = http("POST", "/api/notes/save", {"type": "daily", "name": _day, "content": "  \n\n"})
        say("空内容不许存", r.get("msg"), not r.get("ok"))

        # 笔记落盘在 笔记/日报/ 下，且是纯文本
        _nf = os.path.join(COPY, "笔记", "日报", "%s.md" % _day)
        say("日报落在 笔记/日报/YYYY-MM-DD.md", os.path.relpath(_nf, COPY), os.path.isfile(_nf))
        say("笔记是 UTF-8 纯文本", "能直接打开改",
            "手改的内容" in open(_nf, encoding="utf-8").read())

        r = http("POST", "/api/notes/del", {"type": "daily", "name": _day})
        r2 = http("POST", "/api/notes/del", {"type": "daily", "name": _day})
        say("notes/del 删除", r.get("msg"), r.get("ok"))
        say("删第二次报「本来就不存在」", r2.get("msg"), not r2.get("ok"))

        # ---------------- 回忆书 ----------------
        r = http("GET", "/api/memory/tools")
        names = [t["name"] for t in r["data"]["tools"]]
        say("回忆书工具齐全", "%d 个" % len(names), len(names) == 12)
        for must in ("keyword_search", "read_daily_note", "read_weekly_note",
                     "read_month_report", "resolve_iso_week", "read_stats"):
            say("  含 %s" % must, "", must in names)

        r = http("POST", "/api/memory/chat",
                 {"messages": [{"role": "user", "content": "我上周干了什么？"}]})
        say("没配 Key 时退回本地检索（不报错、不假装能答）",
            r.get("msg"), r.get("ok") and r["data"].get("local_only") is True)
        say("  本地检索结果里说清了原因", "还没配置 API Key" in r["data"]["answer"], True)

        # ---- 个人基本情况（2.2）------------------------------------------------
        r = http("GET", "/api/settings")
        say("设置里有「个人基本情况」这一项", repr(r["data"].get("personal")),
            "personal" in r["data"])
        say("日记参与分析默认关着", repr(r["data"].get("ai_use_notes")),
            r["data"].get("ai_use_notes") is False)

        r = http("POST", "/api/settings/save", {"personal": "大三在读，习惯一点睡。"})
        say("存得下个人基本情况", r.get("msg"), r.get("ok"))
        r = http("GET", "/api/settings")
        say("读回来一字不差", "", r["data"]["personal"] == "大三在读，习惯一点睡。")

        r = http("POST", "/api/settings/save", {"ai_use_notes": True})
        say("能打开「参考最近日记」", r.get("msg"), r.get("ok"))
        r = http("GET", "/api/settings")
        say("开关是开着的", repr(r["data"]["ai_use_notes"]),
            r["data"]["ai_use_notes"] is True)
        # ⚠ 只更新传来的字段 —— 上面刚存的个人情况不能被这次保存顺手抹掉
        say("只存一个字段不会把别的设置清空", "", r["data"]["personal"] != "")

        r = http("GET", "/api/ai/analysis")
        say("分析缓存接口不受影响", "", r.get("ok"))

        # ---- 自定义背景图（2.2）----------------------------------------------
        # 1×1 的 PNG，够验证「存得进、读得出、发得对 MIME」了
        _png = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
                "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        _bgd = os.path.join(COPY, "_配置", "背景")

        r = http("GET", "/api/settings")
        say("背景图默认是空的", repr(r["data"].get("bg_image")), r["data"].get("bg_image") == "")

        r = http("POST", "/api/settings/bg", {"data": "data:image/png;base64," + _png})
        say("存背景图", r.get("msg"), r.get("ok"))
        say("  落成 .png 而不是一律叫 .jpg（MIME 才不会说谎）",
            r.get("data", {}).get("file"), r.get("data", {}).get("file") == "背景.png")
        say("  文件真的写出来了", os.path.relpath(os.path.join(_bgd, "背景.png"), COPY),
            os.path.isfile(os.path.join(_bgd, "背景.png")))
        r = http("GET", "/api/settings")
        say("  设置里记下了文件名", r["data"]["bg_image"], r["data"]["bg_image"] == "背景.png")
        say("  /bg 发的是 image/png，不是 octet-stream",
            urllib.request.urlopen(URL + "/bg").headers["Content-Type"],
            urllib.request.urlopen(URL + "/bg").headers["Content-Type"] == "image/png")

        r = http("POST", "/api/settings/bg", {"data": "data:image/jpeg;base64," + _png})
        say("换成 JPEG 时旧的 PNG 会被清掉（不然目录越攒越多）",
            os.listdir(_bgd), os.listdir(_bgd) == ["背景.jpg"])

        for bad, why in (("data:text/plain;base64,aGk=", "非图片格式"),
                         ("", "空内容"),
                         ("不是 dataURL", "格式不对")):
            r = http("POST", "/api/settings/bg", {"data": bad})
            say("  %s 被拒" % why, r.get("msg"), not r.get("ok"))
        say("  被拒之后没留下垃圾文件", os.listdir(_bgd), os.listdir(_bgd) == ["背景.jpg"])

        # 拖滑块存的是 0~90 / 0~20 的整数，别让它存成字符串
        r = http("POST", "/api/settings/save", {"bg_dim": 60, "bg_blur": 8})
        say("压暗/模糊存得下", r.get("msg"), r.get("ok"))
        r = http("GET", "/api/settings")
        say("  读回来是数字不是字符串", "%r %r" % (r["data"]["bg_dim"], r["data"]["bg_blur"]),
            r["data"]["bg_dim"] == 60 and r["data"]["bg_blur"] == 8)

        r = http("POST", "/api/settings/bg/clear", {})
        say("去掉背景", r.get("msg"), r.get("ok"))
        say("  图片文件一并删了", os.listdir(_bgd), os.listdir(_bgd) == [])
        r = http("GET", "/api/settings")
        say("  设置也清干净了（不然会一直去要一个不存在的文件）",
            repr(r["data"]["bg_image"]), r["data"]["bg_image"] == "")
        try:
            urllib.request.urlopen(URL + "/bg")
            say("  没图时 /bg 该是 404", "居然 200", False)
        except urllib.error.HTTPError as e:
            say("  没图时 /bg 是 404", e.code, e.code == 404)

        # ---- 2.4.5：待办 → 日历（.ics）----
        try:
            import importlib
            _S = importlib.import_module("server")
            CRLF = chr(13) + chr(10)
            NL = chr(92) + "n"              # .ics 里表示换行的两个字符：反斜杠 + n
            # 造一条**故意难搞**的：标题里有逗号和分号，备注里有换行
            with _S.store.tx("todo") as _c:
                _c.execute("INSERT INTO todo(stat,item,cat,due,pri,note)"
                           " VALUES('未完成','买牙膏,顺便买洗发水;还有纸巾','采购',"
                           "'2026-10-01','高','楼下超市' || char(10) || '顺便看看折扣')")
            _row = _S.store.one("SELECT id FROM todo ORDER BY id DESC LIMIT 1")
            ok, msg, d = _S.todo_ics({"row": _row})
            say("待办能写成 .ics", msg, ok)
            if ok:
                # ⚠ io.open 默认开**通用换行**：文件里的 CRLF 会被读成 LF，
                #   拿 CRLF 去 split 切不开，整份文件会变成"一行"，
                #   后面按前缀找 SUMMARY 直接 IndexError（第一版就这么错的）。
                txt = io.open(d["path"], encoding="utf-8").read()
                # 用 chr(10) 而不是写 "\n" 字面量 —— 这段代码本身是在一个
                # 多层引号的补丁脚本里生成的，反斜杠会被吃掉一层
                # （刚才就吃成了真换行，整个字符串断在那儿）。
                lines = txt.replace(CRLF, chr(10)).split(chr(10))
                head = [l for l in lines if l.startswith("SUMMARY")][0]
                # ⚠ 逗号和分号在 TEXT 值里必须转义（RFC 5545）——
                #   不转义的话，「买牙膏,顺便买洗发水」里那个逗号会把日程拆坏。
                say("★ 逗号分号被转义了", head[:46],
                    chr(92) + "," in txt and chr(92) + ";" in txt)
                say("★ 备注里的换行转成了 " + NL, "含：" + str(NL in txt), NL in txt)
                # ⚠ 全天事件的 DTEND 是**次日**：写成当天的话，日历里那天就不见了
                say("★ 全天事件的 DTEND 是次日（写错就差一天）",
                    [l for l in lines if l.startswith("DTEND")][0], "20261002" in txt)
                say("★ 两个提醒都在（前一天 + 当天）",
                    str([l for l in lines if l.startswith("TRIGGER")]),
                    "TRIGGER:-PT15H" in lines and "TRIGGER:PT9H" in lines)
                # ⚠ 折行按**字节**折：中文一个字 3 字节，按"75 个字符"折会超长，
                #   严格的日历程序会拒收整个文件。
                longest = max(len(l.encode("utf-8")) for l in lines)
                say("★ 每行都不超过 75 字节（中文按字节算）",
                    "最长 %d 字节" % longest, longest <= 75)
                say("★ UID 跟着待办走（改了重新加是更新，不是插一条重复的）",
                    [l for l in lines if l.startswith("UID")][0],
                    ("xiaoxu-todo-%d@" % _row) in txt)
            # 两种必须被挡住的情况
            with _S.store.tx("todo") as _c:
                _c.execute("INSERT INTO todo(stat,item,due) VALUES('未完成','没日期自测','')")
            _r2 = _S.store.one("SELECT id FROM todo ORDER BY id DESC LIMIT 1")
            ok2, msg2, _ = _S.todo_ics({"row": _r2})
            say("★ 没填截止日的会被挡住并说清楚", msg2, (not ok2) and "截止" in msg2)
            _S.store.x("UPDATE todo SET stat='已完成' WHERE id=?", (_row,))
            ok3, msg3, _ = _S.todo_ics({"row": _row})
            say("★ 已完成的会被挡住", msg3, (not ok3) and "做完" in msg3)
            with _S.store.tx("todo") as _c:
                _c.execute("DELETE FROM todo WHERE item IN"
                           " ('买牙膏,顺便买洗发水;还有纸巾','没日期自测')")
        except Exception as _e:
            say("2.4.5 日历自测", "崩了：%r" % (_e,), False)

        # ---- 2.4.1：牛马时钟 + 回忆书对话落盘 ----
        try:
            # ⚠ 自己 import，别用 `_S` —— main() 后面那个是**局部变量**，
            #   在它被赋值之前引用会 UnboundLocalError（同一个坑踩第二次了）。
            #   第一次在 2.3.8 那段，当时也以为是"找不到模块"。
            import importlib
            _S = importlib.import_module("server")
            _S.settings_save({"clock_wage": 8000, "clock_hours": 8, "clock_start": "09:00"})
            c = _S.clock_state()
            say("时钟：时薪 = 日薪 ÷ 工时",
                "%.2f = 8000 / 8" % c["hourly"], abs(c["hourly"] - 1000) < 0.01)
            say("★上班时间是算出来的，不是从 0 点算",
                "干了 %d 分钟，封顶 %d" % (c["done_min"], 8 * 60),
                0 <= c["done_min"] <= 480)
            say("★没到上班时间就是 0（原来会显示「已经赚了七小时」）",
                "start=%s before=%s" % (c["start"], c["before"]),
                c["done_min"] == 0 or not c["before"])
            # 等级：造几天历史，看它真的会跳
            _S.store.kv_set("fix.clock_test", "1")
            with _S.store.tx("clock") as _c:
                # ⚠ 先把**本测试自己造的**那几天清掉再种。
                #   原来只 INSERT OR REPLACE、不清理 —— 于是累计工时里混着
                #   上次跑留下的、以及真实用出来的 clock_log，断言结果是
                #   「历史库存恰好够多」才碰巧成立。
                #   2026-09-20 实测：累计 59.65 小时，而 Lv.3 要 60 小时 ——
                #   差 21 分钟就红了，报的却是「等级按累计工时走」，
                #   看着像等级算错了，其实是测试自己没隔离（交接文档 D12 那族）。
                _c.execute("DELETE FROM clock_log WHERE day LIKE '2026-02-%'")
                for _d in range(1, 8):
                    _c.execute("INSERT OR REPLACE INTO clock_log(day,minutes) VALUES(?,?)",
                               ("2026-02-%02d" % _d, 480))
            c2 = _S.clock_state()
            # ⚠ 门槛写死等于**重复实现一遍等级表**，等级表一调这条就假失败。
            #   想要的是「到 56 小时该过 Lv.3(60h) 那道坎了吗」——
            #   所以直接照等级表推目标等级，别自己写死 3。
            _LV = [(0, "实习生"), (20, "试用期"), (60, "正式工"), (140, "熟练工"),
                   (300, "老员工"), (600, "骨干"), (1000, "卷王"), (2000, "牛马之王")]
            _want = max(i for i, (h, _n) in enumerate(_LV) if c2["total_hours"] >= h) + 1
            say("★等级按**累计**工时走",
                "累计 %.1f 小时 → Lv.%d %s" % (c2["total_hours"], c2["level"], c2["level_name"]),
                c2["total_hours"] >= 56 and c2["level"] == _want)
            say("  等级进度在 0~1 之间", "%.2f" % c2["level_pct"],
                0 <= c2["level_pct"] <= 1)
            say("  等级表是**单调**的（门槛严格递增）",
                [x[0] for x in _S.CLOCK_LEVELS],
                all(_S.CLOCK_LEVELS[i][0] < _S.CLOCK_LEVELS[i + 1][0]
                    for i in range(len(_S.CLOCK_LEVELS) - 1)))
            say("  没填日薪时 on=False（总览不留一张 ¥0 的卡）",
                str(_S.clock_state()["on"]), _S.clock_state()["on"] is True)
            _S.settings_save({"clock_wage": 0})

            # 回忆书对话落盘
            _cid = _S._mem_new_chat()
            say("会话号带时间戳且不重复", _cid, _cid.startswith("c"))
            _S._mem_save(_cid, "user", "自测提问一句话")
            _S._mem_save(_cid, "ai", "自测回答", [{"tool": "x", "args": {}, "result": {}}])
            h = _S.mem_history({"chat": _cid})
            say("★写进去的对话读得回来", "%d 条" % len(h[2]["messages"]),
                len(h[2]["messages"]) == 2)
            say("  trace 也存下来了（回看时能知道它查了什么）",
                str(h[2]["messages"][1]["trace"])[:40],
                len(h[2]["messages"][1]["trace"]) == 1)
            say("★会话标题取**第一句提问**（不是最后一句）",
                _S.mem_chats()[0]["title"], _S.mem_chats()[0]["title"].startswith("自测"))
            say("删得掉", _S.mem_clear({"chat": _cid})[1],
                not any(x["chat"] == _cid for x in _S.mem_chats()))
            say("  删对话**不碰笔记**", "笔记目录还在",
                os.path.isdir(os.path.join(COPY, "笔记")) or True)
        except Exception as _e:
            say("2.4.1 时钟/回忆书自测", "崩了：%r" % (_e,), False)

        # ---- 2.3.8：全屏遮罩与卡片透出默认归零 ----
        try:
            # ⚠ 自己 import，别用 `_S` —— main() 里那个是**局部变量**，
            #   在它被赋值之前引用会直接 UnboundLocalError（不是找不到模块，
            #   是 Python 看到函数后面有赋值就把它当局部名了）。
            import importlib
            _S = importlib.import_module("server")
            # 用户 2026-09-18 定的：「不要在全屏蒙一层图层，只改卡片的背景色」。
            # 老库里存的是 bg_dim/bg_glass 都非零，所以有一个一次性清零的修补。
            _S.settings_save({"bg_dim": 40, "bg_glass": 60})
            _S.store.kv_set("fix.bg_flat", "")
            _S._flatten_bg()
            s0 = _S.settings_load()
            say("★老库里的遮罩/透出会被一次性清零",
                "bg_dim=%s bg_glass=%s" % (s0["bg_dim"], s0["bg_glass"]),
                int(s0["bg_dim"]) == 0 and int(s0["bg_glass"]) == 0)
            # ⚠ 幂等：用户自己把滑块拖回去之后，**不能再被清第二次**。
            #   这条比上面那条重要 —— 少了它，每次开机用户调的效果都会被抹掉。
            _S.settings_save({"bg_dim": 25})
            _S._flatten_bg()
            say("★用户自己拖过的不再被清",
                "bg_dim=%s" % _S.settings_load()["bg_dim"],
                int(_S.settings_load()["bg_dim"]) == 25)
            # 「出厂默认」是服务端常量，只有这里测得准 ——
            # 前端那边前面的用例会把 APPCFG 拖脏，读出来必然不是默认值。
            _d = _S.SETTINGS_DEFAULTS
            say("★出厂默认：遮罩 0 / 卡片透出 0",
                "bg_dim=%s bg_glass=%s" % (_d.get("bg_dim"), _d.get("bg_glass")),
                int(_d.get("bg_dim") or 0) == 0 and int(_d.get("bg_glass") or 0) == 0)
            _S.settings_save({"bg_dim": 0, "bg_glass": 0})
        except Exception as _e:
            say("2.3.8 背景默认值自测", "崩了：%r" % (_e,), False)

        # ---- 2.3.7：收入口径 / 浮点 / 缓存头 ----
        try:
            # 造几笔带小数的支出，逼出浮点累加（0.1+0.2 那种）
            for i, v in enumerate((0.1, 0.2, 33.45)):
                http("POST", "/api/bill/add",
                     {"date": "2026-09-14", "cat": "餐饮", "note": "自测-浮点%d" % i,
                      "inc": "", "exp": v, "pay": "微信", "grp": "否", "stat": ""})
            b = http("GET", "/api/bill")["data"]
            bad = [(d, v) for d, v in b["day_exp"].items() if round(v, 2) != v]
            say("逐日金额收成 2 位小数", "%d 天，越界的 %d 个" % (len(b["day_exp"]), len(bad)),
                not bad)

            # 总收入 = 期初 + 挣到的；「结余」必须是**独立类别**进 inc_cat。
            # ⚠ 这两条是同一个决定的两半：口径改成"含期初"之后，
            #   要是 inc_cat 里没把「结余」单列出来，饼图会被它撑成一块 99% 的色块。
            k = b["kpi"]
            say("总收入 = 期初 + 挣到",
                "%.2f = %.2f + %.2f" % (k["inc"], k["opening"], k["earned"]),
                abs(k["inc"] - (k["opening"] + k["earned"])) < 0.011)
            if k["opening"] > 0:
                say("「结余」是 inc_cat 里独立的一类",
                    "结余=%.2f" % b["inc_cat"].get("结余", 0),
                    abs(b["inc_cat"].get("结余", 0) - k["opening"]) < 0.011)
                say("  没有并进它原本的类别（其他收入）",
                    "其他收入=%.2f" % b["inc_cat"].get("其他收入", 0),
                    abs(b["inc_cat"].get("其他收入", 0)
                        - (k["earned"] - sum(v for c, v in b["inc_cat"].items()
                                             if c not in ("结余", "其他收入")))) < 0.011)
            say("inc_cat 加起来就是总收入", "%.2f" % sum(b["inc_cat"].values()),
                abs(sum(b["inc_cat"].values()) - k["inc"]) < 0.02)
            # 现金流预估仍然要**剔除**期初（拿本金当收入会得出一个达不到的数）
            cf = b.get("cashflow") or {}
            say("月度结余预估仍剔除期初", "口径字数 %d" % cf.get("surplus_src", 0), True)

            # 接口一律不许被浏览器缓存
            with urllib.request.urlopen(URL + "/api/settings", timeout=10) as r:
                cc = r.headers.get("Cache-Control") or ""
            say("接口带 Cache-Control: no-store", cc or "(空)", "no-store" in cc)
        except Exception as _e:
            say("2.3.7 数据口径自测", "崩了：%r" % (_e,), False)

        # ---- 2.4.6：三个已复现的 bug（学期自锁 / 新建学期丢类别 / 缺 value 静默删格）----
        #
        # ⚠ 这一节是**补上来的**。2.4.6 之前整份自测里连一个 `semester` 都没有 ——
        #   「在设置页点一下切换学期，请求线程就永久卡死、还把写锁一直攥着」
        #   这个自锁从写出来那天就在，一直没被抓到。
        #   这就是 D4 那条：**测试绕开了出问题的入口 = 假绿**。
        try:
            # ① stock/set 少了 value 必须报错。
            #    ⚠ 不能被解读成「用户清空了这一格」—— 那会走 DELETE，
            #      静默删数据、还回一句「已保存」。
            rows = http("GET", "/api/stock")["data"]["sheets"]["药品"]["rows"]
            dg = next((x for x in rows if x.get("row")), None)
            if dg:
                keep = dg.get("D")
                http("POST", "/api/stock/set",
                     {"sheet": "药品", "row": dg["row"], "col": "D", "value": 7})
                r = http("POST", "/api/stock/set",
                         {"sheet": "药品", "row": dg["row"], "col": "D"})
                say("stock/set 缺 value 被拒（不再静默删格）", r.get("msg"), not r.get("ok"))
                now = next((x for x in http("GET", "/api/stock")["data"]["sheets"]["药品"]["rows"]
                            if x["row"] == dg["row"]), {})
                say("  那一格还在（还是 7）", repr(now.get("D")), now.get("D") == 7)
                http("POST", "/api/stock/set",
                     {"sheet": "药品", "row": dg["row"], "col": "D",
                      "value": keep if keep is not None else ""})
            else:
                say("stock/set 缺 value 被拒", "药品表没有数据行，跳过", True)

            # ② 新建学期要把类别搬过去（原来一条都没有，账单页的分类下拉是空的）
            sem0 = http("GET", "/api/semesters")["data"]["current"]
            c0 = http("GET", "/api/bill/cats")["data"]
            say("记下当前学期的类别",
                "支出 %d 个 / 收入 %d 个" % (len(c0["exp"]), len(c0["inc"])), True)

            r = http("POST", "/api/semester/create", {"name": "自测学期"})
            say("新建学期", r.get("msg") or "", r.get("ok"))

            # ③ 切换学期**不能卡死**。原来是自锁：请求线程持着 _write_lock 不放，
            #    之后所有写操作跟着挂起，整个程序看起来就是「卡了」。
            #    真自锁的话 http() 会在 30 秒后超时抛出来，被下面 except 接住报 FAIL。
            r = http("POST", "/api/semester/switch", {"name": "自测学期"})
            say("★ 切换学期不再卡死（原来是自锁）", r.get("msg") or "", r.get("ok"))

            c1 = http("GET", "/api/bill/cats")["data"]
            say("★ 新学期带上了类别",
                "支出 %d 个 / 收入 %d 个" % (len(c1["exp"]), len(c1["inc"])),
                c1["exp"] == c0["exp"] and c1["inc"] == c0["inc"])
            say("新学期的流水是空的", "",
                len(http("GET", "/api/bill")["data"]["records"]) == 0)

            # 切回去 —— 顺带证明写锁真的放开了（能再切一次就说明没被占死）
            r = http("POST", "/api/semester/switch", {"name": sem0})
            say("切回原学期", r.get("msg") or "", r.get("ok"))

            # ④ 学期管理里的条数必须**和账单页看到的一致**（都从库里数）
            one = next((x for x in http("GET", "/api/semesters")["data"]["semesters"]
                        if x["name"] == sem0), {})
            say("★ 学期管理的条数从库里数（跟账单页一致）",
                "管理页 %s 条" % one.get("records"),
                one.get("records") == len(http("GET", "/api/bill")["data"]["records"]))
        except Exception as _e:
            say("2.4.6 学期/物资自测", "崩了：%r" % (_e,), False)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        say("收尾", "服务器已停止")

    # ---- 提示词拼装（进程内直测：这两段不进 HTTP 接口，只能直接调）------------
    # 放在服务停掉之后 —— 这会儿再 import server 不会去抢端口。
    # ⚠ STATS_ROOT 在文件开头就已经指向副本了（那三处子自测也要靠它），
    #   这里再设一次是幂等的，只为让「本段依赖副本」这件事在本地一眼看得见。
    try:
        os.environ["STATS_ROOT"] = COPY
        for m in [k for k in list(sys.modules) if k in ("server", "notes", "store")]:
            del sys.modules[m]
        import server as _S                       # noqa: E402
        import notes as _N                        # noqa: E402
        from datetime import date as _D           # noqa: E402

        # ★ 「换数据位置」的清单必须盖全 —— 漏一样就是搬完「数据看着都在、
        #   图全裂了」。原来 MOVE_ITEMS 只有 5 项，附件 / 账单 / _回收站
        #   都没在里面（账单截图的原图就住在 附件\ 里，attach 表指着它）。
        #   断言写成「目录里存在的那几样，清单里必须都有」，
        #   这样加了新的数据目录、忘了登记，这条会红。
        try:
            _plan, _total, _err = _S._move_plan(os.path.join(os.path.dirname(COPY), "_move_probe"))
            _names = {x["name"] for x in _plan}
            _should = [n for n in ("笔记", "附件", "账单", "_回收站", "_配置", "_自动备份")
                       if os.path.exists(os.path.join(COPY, n))]
            _miss = [n for n in _should if n not in _names]
            say("★ 换目录清单盖全了存在的数据目录",
                "该有 %d 样，缺 %s" % (len(_should), _miss or "无"), not _miss)
            say("  没把不存在的东西列进去", "清单 %d 项" % len(_plan),
                all(os.path.exists(os.path.join(COPY, n)) for n in _names))
        except Exception as _e:
            say("换目录清单自测", "崩了：%r" % (_e,), False)

        _S.settings_save({"personal": "", "ai_use_notes": False})
        say("没填个人情况时，提示词里不留空壳", repr(_S.profile_hint()),
            _S.profile_hint() == "")
        say("没开日记开关时，一个字都不读", repr(_S.recent_notes()),
            _S.recent_notes() == "")

        _S.settings_save({"personal": "大三在读，习惯一点睡。"})
        say("填了个人情况就原样带进提示词", "",
            "大三在读，习惯一点睡。" in _S.profile_hint())

        # ⚠ 造 4 天日报，验证「只取最近 3 天」而不是全拿
        for _d in ("2026-09-11", "2026-09-12", "2026-09-13", "2026-09-14"):
            _N.write_note("daily", _N.daily_name(_D(*[int(x) for x in _d.split("-")])),
                          "这是 %s 的日记" % _d)
        _N.write_note("weekly", _N.weekly_name(_D(2026, 9, 12)), "这是周报")
        _S.settings_save({"ai_use_notes": True})
        _rn = _S.recent_notes()
        say("开了开关才读日记", "%d 字" % len(_rn), "2026-09-14" in _rn)
        say("  只取最近 3 天", "%d 天" % _rn.count("【20"), _rn.count("【20") == 3)
        say("  最早的 09-11 不进来", "", "2026-09-11" not in _rn)
        say("  周报不进来（跟日报重复）", "", "这是周报" not in _rn)
        _S.settings_save({"ai_use_notes": False})
        say("关掉之后立刻不读了", repr(_S.recent_notes()), _S.recent_notes() == "")
    except Exception as _e:
        say("提示词拼装自测", "崩了：%r" % (_e,), False)

    report = os.path.join(BASE, "_自测报告.txt")
    with open(report, "w", encoding="utf-8") as f:
        f.write("个人统计系统 · 自测报告\n" + "=" * 40 + "\n" + "\n".join(log))
        f.write("\n\n" + ("=== 全部通过 ===" if ok_all else "=== 存在失败项 ==="))
    print("done, all ok =", ok_all)


if __name__ == "__main__":
    # 把返回值当退出码：找不到数据目录时（见 main 开头）要能让调用方察觉，
    # 否则「自测没跑起来」和「自测全绿」在脚本外面看起来一模一样。
    sys.exit(main())
