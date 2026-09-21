"""换数据目录（2.3.6）的自测。

这个功能**会动用户的数据**，所以不能只看「接口返回 ok」：
  ① 复制过去的库要能打开、条数要对得上
  ② 校验不通过时**一个字节都不许删源**
  ③ 目标目录选得不对（就是当前目录 / 互相包含）要当场拒绝
  ④ 删源必须用户明确要求过（purge=True），默认不删

跑法：python _自测_迁移.py
"""
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_迁移测试根")
DST = os.path.join(HERE, "_迁移测试根_新位置")
PORT = 8796
BASE = "http://127.0.0.1:%d" % PORT

OK, FAIL = [], []


def ck(cond, name, extra=""):
    (OK if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", name,
                           ("  -- " + str(extra)) if extra else ""))


def post(path, body):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(r, timeout=60))
    except urllib.error.HTTPError as e:
        # ⚠ 被拒的时候服务端返回 400，**正文里才有那句人话**。
        #   不读它的话拿到的只是 "<HTTPError 400>"，测试就会误判成"消息不对"
        #   （第一版就是这么错怪的，其实拒绝得好好的）。
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "msg": "HTTP %s" % e.code}
    except Exception as e:
        return {"ok": False, "msg": repr(e)}


def get(path):
    try:
        return json.load(urllib.request.urlopen(BASE + path, timeout=60))
    except Exception as e:
        return {"ok": False, "msg": repr(e)}


def prepare():
    """造一个像模像样的数据根：库 + 配置 + 笔记 + 备份。"""
    shutil.rmtree(SRC, ignore_errors=True)
    shutil.rmtree(DST, ignore_errors=True)
    os.makedirs(os.path.join(SRC, "_配置"), exist_ok=True)
    os.makedirs(os.path.join(SRC, "笔记", "日报"), exist_ok=True)
    os.makedirs(os.path.join(SRC, "_自动备份"), exist_ok=True)
    io.open(os.path.join(SRC, "_配置", "settings.json"), "w", encoding="utf-8") \
        .write(json.dumps({"theme": "light", "palette": "素纸"}, ensure_ascii=False))
    for i in range(3):
        io.open(os.path.join(SRC, "笔记", "日报", "2026-09-1%d.md" % i),
                "w", encoding="utf-8").write("# 第 %d 天\n今天还行。\n" % i)
    io.open(os.path.join(SRC, "_自动备份", "占位.txt"), "w", encoding="utf-8").write("x")


def main():
    prepare()
    print("测试根建好了：%s" % SRC)

    env = dict(os.environ, STATS_ROOT=SRC, STATS_PORT=str(PORT), STATS_NOBROWSER="1")
    import subprocess
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/api/about", timeout=3).read()
                break
            except Exception:
                time.sleep(0.5)

        # 先写一条真数据，确保库里有内容可比对
        r = post("/api/bill/add", {"date": "2026-09-17", "amount": 12.5,
                                   "cat": "餐饮", "note": "测试", "who": "我"})
        print("  塞了一条账单：%s" % r.get("msg"))
        about = get("/api/about").get("data", {})
        before = about.get("files", [])
        print("  当前库：%s" % json.dumps(before, ensure_ascii=False)[:120])

        # ---- ① 目标选得不对要当场拒绝 ----
        d = post("/api/data/inspect", {"to": SRC})
        ck(not d.get("ok") and "当前目录" in (d.get("msg") or ""),
           "目标是当前目录 → 拒绝", d.get("msg"))
        d = post("/api/data/inspect", {"to": os.path.join(SRC, "子目录")})
        ck(not d.get("ok"), "目标在当前目录里面 → 拒绝（不然会自己拷自己）", d.get("msg"))
        d = post("/api/data/inspect", {"to": os.path.dirname(SRC)})
        ck(not d.get("ok"), "当前目录在目标里面 → 也拒绝", d.get("msg"))

        # ---- ② 正常看一眼要搬什么 ----
        d = post("/api/data/inspect", {"to": DST})
        ck(d.get("ok"), "看一眼要搬什么 → ok", d.get("msg"))
        plan = d.get("data") or {}
        names = [i["name"] for i in plan.get("items", [])]
        ck("小煦拾简.db" in names, "清单里有数据库", names)
        ck("笔记" in names, "清单里有笔记", names)
        ck("_配置" in names, "清单里有配置", names)
        ck(plan.get("total", 0) > 0, "算出了总大小", plan.get("total"))
        ck(os.path.isdir(DST), "目标目录被建出来了（不然用户还得自己建）")

        # ---- ③ 不删源地搬 ----
        d = post("/api/data/move", {"to": DST, "purge": False})
        ck(d.get("ok"), "搬（不删源）→ ok", d.get("msg"))
        ck(os.path.exists(os.path.join(SRC, "小煦拾简.db")), "★ 旧目录的库还在（默认不删）")
        ck(os.path.exists(os.path.join(DST, "小煦拾简.db")), "新目录的库在")
        n_old = len(os.listdir(os.path.join(SRC, "笔记", "日报")))
        n_new = len(os.listdir(os.path.join(DST, "笔记", "日报")))
        ck(n_old == n_new == 3, "笔记一篇不少", "%d / %d" % (n_old, n_new))

        # ---- ④ 新库能打开、条数对得上 ----
        import sqlite3

        def count(p):
            c = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
            try:
                return c.execute("SELECT COUNT(*) FROM bill").fetchone()[0]
            finally:
                c.close()

        a, b = count(os.path.join(SRC, "小煦拾简.db")), count(os.path.join(DST, "小煦拾简.db"))
        ck(a == b and a > 0, "★ 新库能打开，条数和老库一样", "%d / %d" % (a, b))

        # ---- ⑤ 再搬一次（目标已有东西）不许把新库弄坏 ----
        d = post("/api/data/move", {"to": DST, "purge": False})
        ck(d.get("ok"), "再搬一次也不会炸（目标已经有东西）", d.get("msg"))
        ck(count(os.path.join(DST, "小煦拾简.db")) == a, "★ 又搬一次，新库条数没变")

        # ---- ⑥ 明确要求删源：写欠条，下次启动才真删 ----
        d = post("/api/data/move", {"to": DST, "purge": True})
        ck(d.get("ok"), "搬（要删源）→ ok", d.get("msg"))
        ck((d.get("data") or {}).get("purge_pending"), "记下了「欠一次删除」",
           json.dumps(d.get("data"), ensure_ascii=False)[:120])
        mark = os.path.join(DST, "_配置", "待删除的旧目录.txt")
        ck(os.path.isfile(mark), "★ 欠条写在了**新**目录里（重启后读的就是它）")
        ck(open(mark, encoding="utf-8").read().strip() == os.path.abspath(SRC),
           "欠条上写的是旧位置", open(mark, encoding="utf-8").read().strip())
        ck(os.path.exists(os.path.join(DST, "小煦拾简.db")), "新库还在")

        # ---- ⑦ 再次启动：欠条要被执行掉 ----
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
        # 以**新目录**为数据根重启 —— 这就模拟了用户换完目录后的下一次开机
        env2 = dict(os.environ, STATS_ROOT=DST, STATS_PORT=str(PORT), STATS_NOBROWSER="1")
        proc = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")],
                                env=env2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/api/about", timeout=3).read()
                break
            except Exception:
                time.sleep(0.5)
        ck(not os.path.exists(mark), "★ 重启之后欠条被收走了")
        ck(not os.path.exists(os.path.join(SRC, "小煦拾简.db")),
           "★★ 说了删，这次真的删掉了（重启之后没人占着那个文件）")
        ck(os.path.exists(os.path.join(DST, "小煦拾简.db")), "新库完好")
        ck(count(os.path.join(DST, "小煦拾简.db")) == a, "★ 删源之后新库条数依然对")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    print("\n通过 %d 项，失败 %d 项" % (len(OK), len(FAIL)))
    if FAIL:
        print("失败：")
        for x in FAIL:
            print("   " + x)
    shutil.rmtree(SRC, ignore_errors=True)
    shutil.rmtree(DST, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
