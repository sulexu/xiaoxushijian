# -*- coding: utf-8 -*-
r"""笔记加密端到端测试（**全程在隔离副本里跑，绝不碰真实笔记**）

覆盖的坑，全是「跨进程 / 跨状态」才暴露得出来的：
  · 开启加密后，磁盘上不能有任何明文 —— 包括 _自动备份 里开加密之前攒下的副本
  · 重启之后密钥还派不派生得出来（盐有没有正确落盘）
  · 改密码之后，活的笔记 + 备份副本都还读不读得出
  · 关掉加密之后，每个文件逐字还原

为什么要重启真服务器：密钥只在进程内存里、盐在设置文件里，
「重启后还能读」是这套设计里最容易坏也最致命的一环，假进程模拟不出来。

跑法：python _自测_加密.py   （不用先停服务器，脚本自己管端口 8769）
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

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "_加密测试根")
PORT = "8769"
BASE = "http://127.0.0.1:%s" % PORT
SEED = os.path.join(HERE, "_测试副本")      # 三个 Excel 的副本，拿它当种子
TOK = [""]
OK = FAIL = 0


def ck(cond, name, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("[OK]   " + name + ((" -- " + str(detail)) if detail else ""))
    else:
        FAIL += 1
        print("[FAIL] " + name + ((" -- " + str(detail)) if detail else ""))


def call(path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Auth-Token": TOK[0]})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())
    except Exception as e:
        return {"ok": False, "msg": "连不上：%s" % e}


def kill():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "(Get-NetTCPConnection -LocalPort %s -State Listen -ErrorAction SilentlyContinue)"
                    ".OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }" % PORT],
                   capture_output=True)
    time.sleep(1.5)


def start():
    subprocess.Popen([sys.executable, "server.py"], cwd=HERE,
                     env={**os.environ, "STATS_PORT": PORT, "STATS_ROOT": ROOT,
                          "STATS_NOBROWSER": "1"},
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(BASE + "/api/auth/state", timeout=3)
            return True
        except urllib.error.HTTPError:
            return True          # 401 也算活着：设了密码之后这个接口本来就要令牌
        except Exception:
            pass
    return False


def snap(root=ROOT):
    out = {}
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith(".md"):
                p = os.path.join(dp, fn)
                out[os.path.relpath(p, root)] = open(p, encoding="utf-8").read()
    return out


def is_cipher(text):
    return text.startswith("小煦拾简·加密笔记")


def build_root():
    """铺一个干净的测试根：三个 Excel 副本 + 几篇明文笔记 + 一份「开加密之前」的备份副本"""
    if os.path.isdir(ROOT):
        shutil.rmtree(ROOT, ignore_errors=True)
    shutil.copytree(SEED, ROOT)
    for sub in ("笔记", "_自动备份", "_配置"):     # 种子里可能有旧的，清掉重来
        d = os.path.join(ROOT, sub)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
    live = os.path.join(ROOT, "笔记", "日报")
    bak = os.path.join(ROOT, "_自动备份", "笔记_20260901", "日报")
    os.makedirs(live, exist_ok=True)
    os.makedirs(bak, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "_配置"), exist_ok=True)
    json.dump({}, open(os.path.join(ROOT, "_配置", "settings.json"), "w", encoding="utf-8"))
    body = {
        "2026-08-06": "# 2026-08-06 日报\n\n加密前就存在的日记正文。\n",
        "2026-09-14": "# 2026-09-14 日报\n\n第二篇，内容不同，用来验证逐字还原。\n",
    }
    for name, text in body.items():
        for d in (live, bak):
            with open(os.path.join(d, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)


def main():
    if not os.path.isdir(SEED):
        print("找不到 %s —— 先跑一次 python _自测.py 让它生成" % SEED)
        return 1
    build_root()
    kill()
    ck(start(), "隔离测试根起来了", ROOT)
    before = snap()
    live_n = sum(1 for k in before if k.startswith("笔记"))
    bak_n = sum(1 for k in before if k.startswith("_自动备份"))
    print("      开加密前：%d 个 .md（活的笔记 %d + 备份副本 %d）\n"
          % (len(before), live_n, bak_n))

    ck(call("/api/auth/set", {"old": "", "new": "pw12345"}).get("ok"), "设访问密码")
    TOK[0] = (call("/api/auth/unlock", {"password": "pw12345"}).get("data") or {}).get("token", "")
    ck(bool(TOK[0]), "解锁拿到令牌")

    r = call("/api/settings/save", {"encrypt_notes": True})
    ck(r.get("ok"), "开启加密", r.get("msg"))
    st = call("/api/settings").get("data", {}).get("crypto", {})
    ck(st.get("enabled") and st.get("unlocked"), "状态：已开启且已解锁", st)

    after = snap()
    live = {k: v for k, v in after.items() if k.startswith("笔记")}
    bak = {k: v for k, v in after.items() if k.startswith("_自动备份")}
    ck(live and all(is_cipher(v) for v in live.values()), "活的笔记全变密文", "%d 篇" % len(live))
    ck(bak and all(is_cipher(v) for v in bak.values()),
       "★备份里的明文副本也一起转了（前门锁了，后门也得锁）", "%d 篇" % len(bak))
    ck(not [k for k, v in before.items() if v[:16] in after.get(k, "")],
       "磁盘上找不到任何一段正文原文")

    key = os.path.join("笔记", "日报", "2026-08-06.md")
    r = call("/api/notes/get", {"type": "daily", "name": "2026-08-06"})
    ck(r.get("ok") and r["data"]["content"] == before[key], "接口读出来还是原文（透明解密）")

    # ★ 换一个进程：密钥只在内存里，重启是这套设计最容易坏的一环
    kill()
    ck(start(), "重启服务器")
    TOK[0] = (call("/api/auth/unlock", {"password": "pw12345"}).get("data") or {}).get("token", "")
    ck(bool(TOK[0]), "重启后能解锁")
    r = call("/api/notes/get", {"type": "daily", "name": "2026-08-06"})
    ck(r.get("ok") and r["data"]["content"] == before[key], "★重启后照样读得出（盐没丢）")

    # 改密码
    r = call("/api/auth/set", {"old": "pw12345", "new": "newpw678"})
    ck(r.get("ok"), "改密码并重新加密", r.get("msg"))
    ck(not call("/api/auth/unlock", {"password": "pw12345"}).get("ok"), "旧密码失效")
    kill()
    ck(start(), "再重启")
    TOK[0] = (call("/api/auth/unlock", {"password": "newpw678"}).get("data") or {}).get("token", "")
    ck(bool(TOK[0]), "新密码能解锁")
    r = call("/api/notes/get", {"type": "daily", "name": "2026-08-06"})
    ck(r.get("ok") and r["data"]["content"] == before[key], "★换密码后笔记仍读得出")
    bak2 = {k: v for k, v in snap().items() if k.startswith("_自动备份")}
    ck(all(is_cipher(v) for v in bak2.values()), "备份副本也跟着换了密钥（没有只换一半）")

    # 关掉 → 逐字还原
    r = call("/api/settings/save", {"encrypt_notes": False})
    ck(r.get("ok"), "关闭加密", r.get("msg"))
    ck(call("/api/auth/clear", {"old": "newpw678"}).get("ok"), "取消访问密码")
    final = snap()
    ck(set(final) == set(before), "文件清单和最初一致",
       "多 %s 少 %s" % (set(final) - set(before), set(before) - set(final)))
    diff = [k for k in before if final.get(k) != before[k]]
    ck(not diff, "★每个文件逐字还原（活的笔记 + 备份副本）", diff or "全部一致")

    kill()
    print()
    print("通过 %d 项，失败 %d 项" % (OK, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
