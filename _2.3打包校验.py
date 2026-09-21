# -*- coding: utf-8 -*-
"""拿**真实数据库的副本**验证 2.3.0 的打包版能不能正常起来、数据一条不少。

⚠ 原件全程只读（mode=ro），只操作副本。
跑：python _2.3打包校验.py
"""
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def snapshot(src, dst):
    """用 SQLite 自己的备份接口拷一份。

    ⚠ **不 import _升级校验 里的那个** —— 它模块顶层会重设 sys.stdout，
      我这个 wrapper 被回收时会把底层 buffer 一起关掉，
      后面一 print 就是「I/O operation on closed file」。十来行的事，自带一份。
    ⚠ 也**不能 shutil.copy** —— 那个库正开着 WAL，直拷主文件会漏掉没落盘的部分。"""
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


# 编码设置放在最后 —— 上面那个 import 要是换了 stdout，这里还能再包一次
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

R = r"D:\个人信息统计"
W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_打包校验根")
EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "_打包产物_2.3.2", "win-unpacked", "resources", "server.exe")
PORT = 8797
TABLES = ("bill", "stock", "check_val", "check_item", "em_field",
          "attach", "cat", "tail", "dream")


def ro(path):
    return sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)


def main():
    if not os.path.isfile(EXE):
        print("找不到打包产物：%s" % EXE)
        return 1
    shutil.rmtree(W, ignore_errors=True)
    os.makedirs(W)
    snapshot(os.path.join(R, "小煦拾简.db"), os.path.join(W, "小煦拾简.db"))
    shutil.copytree(os.path.join(R, "_配置"), os.path.join(W, "_配置"))

    c = ro(os.path.join(R, "小煦拾简.db"))
    before = {t: c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in TABLES}
    c.close()
    print("真实库行数已记录：%s\n" % before)

    env = dict(os.environ, STATS_ROOT=W, STATS_PORT=str(PORT), STATS_NOBROWSER="1")
    p = subprocess.Popen([EXE], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    up = False
    try:
        for _ in range(60):
            time.sleep(0.5)
            try:
                up = urllib.request.urlopen("http://127.0.0.1:%d/" % PORT).status == 200
                break
            except Exception:
                pass
        print("2.3.0 打包版启动:", "成功" if up else "★ 失败")
        if up:
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/about" % PORT)
            except urllib.error.HTTPError as e:
                print("  密码锁生效:", e.code, "（401 = 正常）")
        p.terminate()
        time.sleep(0.8)
        out = p.stdout.read().decode("utf-8", "replace") if p.stdout else ""
        bad = [l for l in out.split("\n")
               if "Traceback" in l or "Error" in l or "结构" in l]
        print("  启动异常:", bad if bad else "无")
    finally:
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            p.kill()

    print("\n跑完之后数据比对：")
    c2 = ro(os.path.join(W, "小煦拾简.db"))
    # ⚠ 这里踩过两次，都是**假设写死了**：
    #   第一版要求「所有表一行都不能变」→ 把 2.3.1 正确的「补 5 个收入类别」
    #   报成了失败。改成 `EXPECT={"cat": 5}` 之后又过期 —— 真实库跑过一次
    #   2.3.1，基线已经是 27 了，再 +5 当然对不上。
    #   现在写成**规则**而不是数字：
    #     · cat（类别定义，不是账目）—— 只增不减，因为那个修补是幂等的，
    #       跑第二次不该再加
    #     · 别的表 —— 一行都不能动，那才是真数据
    ok = True
    for t in TABLES:
        m = c2.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
        if t == "cat":
            good = m >= before[t]
        else:
            good = m == before[t]
        if not good:
            ok = False
        print("   %-12s %3d -> %3d%s" % (t, before[t], m,
              "" if good else "  ★不该是这个数"))
    # 类别只许增不许减 —— 自己删过的类别不能被"补"回来，也不许被吞掉
    ka = {(r[0], r[1], r[2]) for r in ro(os.path.join(R, "小煦拾简.db")).execute(
        "SELECT sem,kind,name FROM cat")}
    kb = {(r[0], r[1], r[2]) for r in c2.execute("SELECT sem,kind,name FROM cat")}
    gone = sorted(ka - kb)
    print("   类别里被删掉的：%s" % (gone if gone else "一个都没有 ✓"))
    if gone:
        ok = False
    c2.close()
    print("\n" + ("=== 数据一条没少 ===" if ok else "=== ★ 有出入，要查 ==="))
    return 0 if (ok and up) else 1


if __name__ == "__main__":
    sys.exit(main())
