# -*- coding: utf-8 -*-
"""拿**用户真实数据库的副本**验证 store.init() 能不能平滑升到 2.2。

⚠ 原件全程只读（file:...?mode=ro），只操作副本。
   这条红线不能破 —— 里面是几个月的账目和日记。

跑：python _升级校验.py
"""
import io
import os
import shutil
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ⚠ 数据 2026-09-19 搬出了工作目录（现在在 D:\小煦拾简\数据）。
#   原来这里按**目录结构**推算 → 数据一搬，这个 27 项套件就只会打印
#   「找不到真实数据库」然后什么都没验。改成读数据位置配置文件，
#   跟 _自测.py / electron/main.js 用的是同一个权威来源。
#   ⚠ 只读 C 盘这个文件，绝不写。
ROOT_CFG = os.path.join(os.environ.get("APPDATA") or "",
                        "小煦拾简", "数据位置.txt")


def _resolve_live():
    """真实数据库路径：先信配置文件，再退回工作目录。"""
    cands = []
    if os.path.isfile(ROOT_CFG):
        try:
            with open(ROOT_CFG, encoding="utf-8") as f:
                cands.append(f.read().strip())
        except OSError:
            pass
    cands.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for c in cands:
        p = os.path.join(c, "小煦拾简.db")
        if c and os.path.isfile(p):
            return p
    return os.path.join(cands[-1], "小煦拾简.db")


LIVE = _resolve_live()
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_升级测试根")

_ok = _fail = 0


def ck(label, ok, detail=""):
    global _ok, _fail
    if ok:
        _ok += 1
        print("  [OK]   %s%s" % (label, (" -- " + str(detail)) if detail else ""))
    else:
        _fail += 1
        print("  [FAIL] %s%s" % (label, (" -- " + str(detail)) if detail else ""))


def snapshot(src, dst):
    """用 SQLite 自己的备份接口拷一份。**绝不 shutil.copy** ——
    那个库正开着 WAL，直接拷主文件会漏掉还没落盘的部分。"""
    if os.path.exists(dst):
        os.remove(dst)
    s = sqlite3.connect("file:%s?mode=ro" % src.replace("\\", "/"), uri=True)
    try:
        d = sqlite3.connect(dst)
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def tables_of(path):
    c = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    try:
        return sorted(r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"))
    finally:
        c.close()


def counts(path, names):
    c = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    out = {}
    try:
        for n in names:
            try:
                out[n] = c.execute("SELECT COUNT(*) FROM %s" % n).fetchone()[0]
            except sqlite3.Error:
                out[n] = None
    finally:
        c.close()
    return out


def main():
    if not os.path.isfile(LIVE):
        print("找不到真实数据库：%s" % LIVE)
        return 1

    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    copy = os.path.join(WORK, "小煦拾简.db")
    snapshot(LIVE, copy)

    print("真实库：%s" % LIVE)
    print("  大小 %.1f MB" % (os.path.getsize(LIVE) / 1048576.0))
    print("  覆盖前的表和行数将全程比对；下面只动副本。\n")

    MAIN = ["bill", "tail", "budget", "cat", "check_val", "check_cfg",
            "check_month", "dream", "stock", "stock_header", "todo",
            "em_field", "em_contact", "attach"]
    # ⚠ 把副本**还原成 2.1 的样子**：抹掉 2.2 才有的、升级时该被建出来的东西。
    #
    # 为什么必须这么做：真实库是**活的**。用户装上修好的版本跑一次，check_item
    # 就建出来了，这个脚本再拿它当「升级前的旧库」用，前提就没了 ——
    # 表现是测试自己变红，而且跟代码改没改毫无关系。第一版就是这么写的，
    # 用户一跑新版这里就报了假失败。
    # 现在改成「主动造一个 2.1 的库」，跑多少次、库变成什么样，结果都一样。
    raw = sqlite3.connect(copy)
    raw.execute("DROP TABLE IF EXISTS check_item")
    raw.commit()
    raw.close()

    before_t = tables_of(copy)
    before_c = counts(copy, MAIN)
    print("副本已还原成 2.1 的样子（%d 张表）：%s\n" % (len(before_t), "、".join(before_t)))

    # ① 老代码那套守卫必须先能被复现（不然就不知道到底修没修）
    print("对照：旧的 check_schema() 会怎么判")
    import store
    store.use(copy)
    lack = store.check_schema()
    ck("新 check_schema() 正确认出「缺的是整张表」而不是缺列",
       "check_item" in lack["缺表"] and not lack["缺列"],
       "缺表=%s 缺列=%s" % (lack["缺表"], lack["缺列"]))

    # ② 升级
    print("\n跑 store.init()（这就是启动时走的那条路）")
    try:
        store.init()
        ck("init() 不抛异常，库能正常打开", True)
    except Exception as e:
        ck("init() 不抛异常，库能正常打开", False, repr(e))
        return 1

    lack2 = store.check_schema()
    ck("升级后结构完全对得上", not lack2["缺表"] and not lack2["缺列"],
       "缺表=%s 缺列=%s" % (lack2["缺表"], lack2["缺列"]))

    after_t = tables_of(copy)
    ck("新表 check_item 建出来了", "check_item" in after_t,
       "共 %d 张表（+%d）" % (len(after_t), len(after_t) - len(before_t)))

    # ③ 最要紧的一条：原有数据一行都不能少
    print("\n核对原有数据有没有被动过")
    after_c = counts(copy, MAIN)
    for n in MAIN:
        ck("%s 行数不变" % n, before_c[n] == after_c[n],
           "%s -> %s" % (before_c[n], after_c[n]))

    # ④ 新表要能用（种子打卡项是 apply_fixes 干的，这里只验表本身可用）
    with store.tx("check") as c:
        c.execute("INSERT INTO check_item(col,name,kind,grp,opts,ord,enabled,builtin)"
                  " VALUES('__t','测试','tick','other','',0,1,0)")
    ck("check_item 能写能读",
       store.one("SELECT name FROM check_item WHERE col='__t'") == "测试")
    store.x("DELETE FROM check_item WHERE col='__t'")

    print("\n升级是「只加不减」——没有任何一张表被删掉")
    gone = [t for t in before_t if t not in after_t]
    ck("没有表消失", not gone, gone)

    # ⑥ ★ 钉死那个把 2.2 挡在门外的 bug -------------------------------------
    # 「缺一张**还没建**的新表」和「已有的表缺列」是两回事，以前混在一起，
    # 结果旧库一升级就报「缺 check_item.col、check_item.name…」拒绝启动 ——
    # 看着像库坏了，其实只差一张 CREATE TABLE 就能建出来的表。
    print("\n★ 回归：类似「只多了一张新表」的旧库，绝不能再被拦在门外")
    W2 = os.path.join(WORK, "_nocheck")
    os.makedirs(W2, exist_ok=True)
    c2 = os.path.join(W2, "旧库.db")
    if os.path.exists(c2):
        os.remove(c2)
    snapshot(LIVE, c2)
    raw = sqlite3.connect(c2)
    raw.execute("DROP TABLE IF EXISTS check_item")      # 退回 2.1 的样子
    raw.commit()
    raw.close()
    ck("  先把 check_item 这张表去掉，造出 2.1 的库",
       "check_item" not in tables_of(c2))

    for m in [k for k in list(sys.modules) if k in ("store",)]:
        del sys.modules[m]
    import store as store2
    store2.use(c2)
    try:
        store2.init()
        booted = True
        err = ""
    except Exception as e:
        booted, err = False, repr(e)
    ck("  ★ init() 不再拒绝启动", booted, err)
    if booted:
        lack3 = store2.check_schema()
        ck("  ★ 新表自己建出来了，结构完全对得上",
           not lack3["缺表"] and not lack3["缺列"],
           "缺表=%s 缺列=%s" % (lack3["缺表"], lack3["缺列"]))
        ck("  ★ 原有数据依然一行没少",
           counts(c2, ["bill", "stock", "check_val"]) ==
           counts(copy, ["bill", "stock", "check_val"]),
           "bill=%s" % counts(c2, ["bill"])["bill"])

    # ⑦ 另一半：**已有的表缺列**时，得真的把那列补上去
    # （上面测的是「缺整张表」，这里测的是「表在但少一列」，两条路不一样）
    print("\n★ 回归：已有的表少一列时，自动 ALTER 补上")
    c3 = os.path.join(WORK, "_nocol", "缺列.db")
    os.makedirs(os.path.dirname(c3), exist_ok=True)
    if os.path.exists(c3):
        os.remove(c3)
    snapshot(LIVE, c3)
    raw = sqlite3.connect(c3)
    try:
        raw.execute("ALTER TABLE bill DROP COLUMN src")
        raw.commit()
        dropped = True
    except sqlite3.Error as e:
        dropped = False
        why = str(e)
    raw.close()
    if not dropped:
        print("  [--]   这台机器的 SQLite 不支持 DROP COLUMN，跳过（%s）" % why[:60])
    else:
        for m in [k for k in list(sys.modules) if k in ("store",)]:
            del sys.modules[m]
        import store as store3
        store3.use(c3)
        try:
            store3.init()
            ok2, err2 = True, ""
        except Exception as e:
            ok2, err2 = False, repr(e)
        ck("  ★ 缺列也能正常启动（不再报「结构对不上」）", ok2, err2)
        cols = {r[1] for r in store3.q("PRAGMA table_info(bill)")}
        ck("  ★ bill.src 被自动补回来了", "src" in cols)
        ck("  ★ 补列之后结构完全对得上",
           not any(store3.check_schema().values()), store3.check_schema())

    print("\n通过 %d 项，失败 %d 项" % (_ok, _fail))
    print("副本留在：%s" % WORK)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
