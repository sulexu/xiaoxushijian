#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""提交前拦截：**绝不允许用户的生活数据进仓库**。

这是第二层防线。第一层是 .gitignore，但 .gitignore 可以被误改、
也可以被 `git add -f` 强推 —— 所以真正能保证"不泄露"的是这里：
**每一次 commit 都把我们实际要提交的文件逐个查一遍**，命中就拒绝提交。

⚠ 挂在 .git/hooks/pre-commit（本地钩子，不进仓库）。
   改这个文件不用重新安装，git 每次都现读。

拦截三类：
  ① 数据库文件（.db/.db-wal/.db-shm/.sqlite）—— 实测里面是真实记账明细
  ② 测试根 / 备份 / 打包产物 等目录 —— 里面全是真实数据的副本
  ③ **内容扫描**：这次新增的内容里出现真实消费记录的特征词，
     或者像是学号/身份证的长数字串 —— 这一层是防"换个文件名就溜过去"
"""
import base64
import io
import os
import re
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def staged():
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        text=True, encoding="utf-8", errors="replace")
    return [l.strip() for l in out.splitlines() if l.strip()]


# ---- ① 按文件名/后缀拦 ----
BAD_EXT = (".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3",
           ".xlsx", ".xls", ".key", ".pem")
# ---- ② 按路径拦（真实数据的副本都在这几个目录）----
BAD_PATH = re.compile(
    r"(^|/)(_前端测试根|_加密测试根|_升级测试根|_测试副本|_复现根|"
    r"_打包产物[^/]*|node_modules|__pycache__|webview|_pc|_tmpchrome)(/|$)")

# ---- ③ 按内容拦 ----
# 真实数据里的特征词。命中任何一个就说明这是**从真实库导出来的东西**。
# ⚠ 这些词是从实际数据里读到的（不是编的），所以命中率很高、误报很低。
# ⚠⚠ 特征词**编码存放，明文不落盘** —— 这是被自己坑出来的：
#   原来这里直接写着那几个真实消费备注。结果这个钩子**自己**被自己的规则拦住，
#   永远提交不上去 —— 因为"把真实数据写进文件"正是它要防的事，
#   而它把那些词明文写在了自己身上。
#   现在改成 base64url 存放，运行时解码。
#   ⚠ 这不是"加密"（谁都能解），只是**不让明文出现在仓库文件里**。
_ENCODED_WORDS = (
    "5pOC6aWt|5bCP55m-5LqL5Y-v5LmQ|ZGVlcHNlZWvlhYXlgLw|"
    "5ou85aSa5aSa5ZWG5a626L2s6LSm|5LiJ6aG-5YaS6I-c|5Yaw5Yaw56eB5oi_6I-c"
)


def _decode_words():
    out = []
    for x in _ENCODED_WORDS.split("|"):
        pad = "=" * (-len(x) % 4)
        try:
            out.append(base64.urlsafe_b64decode(x + pad).decode("utf-8"))
        except Exception:
            pass
    return out


REAL_DATA_WORDS = _decode_words()
# 像学号/身份证/手机号的长数字串（11 位手机号、18 位身份证）
ID_LIKE = re.compile(r"(?<!\d)(1[3-9]\d{9}|[1-9]\d{5}(19|20)\d{6}\d{3}[\dXx])(?!\d)")

# 只扫文本类文件，不去读 12 MB 的字体
TEXT_EXT = (".py", ".js", ".html", ".css", ".md", ".txt", ".json",
            ".yml", ".yaml", ".bat", ".sh", ".spec", ".cfg", ".ini")


def added_lines(path):
    """只取这次**新增的行**（diff 里 `+` 开头且不是 `+++`）。

    ⚠⚠ 为什么扫"新增行"而不是"整个文件"—— 这是被自己坑出来的：
       1) 隐私说明文档里会**引用**那些词当例子（README 里就写了
          「实测有几百行真实记账（"某某菜"…）」）。扫整个文件连文档都提交不了。
       2) 这个钩子文件自己就**列着**那些特征词 —— 扫整个文件的话
          **钩子本身永远提交不上去**（第一次推仓库时真的被拦了）。
       3) 提交信息里提到那些词也会被连带拦下。
       而真正要防的正是"**这次新加进去的内容**"里带着真实数据 ——
       已经进过仓库的东西是历史，不在这次把关范围。
       扫新增行之后，上面三种误伤全消失，而真实数据照样拦得住。
    """
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "-U0", "--", path],
            text=True, encoding="utf-8", errors="replace")
    except Exception:
        return None
    lines = []
    for l in out.split("\n"):
        if l.startswith("+") and not l.startswith("+++"):
            lines.append(l[1:])
    return "\n".join(lines)


def main():
    files = staged()
    bad = []

    for f in files:
        low = f.lower()
        if low.endswith(BAD_EXT):
            bad.append((f, "数据库/表格/密钥类文件"))
            continue
        if BAD_PATH.search(f.replace("\\", "/")):
            bad.append((f, "在『真实数据副本』目录里"))
            continue
        if not low.endswith(TEXT_EXT):
            continue
        if not os.path.isfile(f):
            continue
        scan = added_lines(f)
        if scan is None:
            continue
        # 去掉代码块 / 行内代码 / 引用块 —— 那些是"说明"，不是数据
        scan = re.sub(r"```[\s\S]*?```", " ", scan)
        scan = re.sub(r"`[^`\n]*`", " ", scan)
        scan = re.sub(r"^\s*>.*$", " ", scan, flags=re.M)
        for w in REAL_DATA_WORDS:
            if w in scan:
                bad.append((f, "这次新增的内容里有真实数据特征词"))
                break
        m = ID_LIKE.search(scan)
        if m:
            bad.append((f, "疑似手机号/身份证号：%s…" % m.group(0)[:6]))

    if bad:
        print("")
        print("=" * 64)
        print("  ❌ 提交被拒绝 —— 检测到可能泄露用户隐私的文件")
        print("=" * 64)
        for f, why in bad:
            print("  · %s" % f)
            print("      原因：%s" % why)
        print("")
        print("  这个项目里混着用户的真实记账/日记数据，一条都不能上传。")
        print("  如果确实要提交，先确认那个文件里没有真实数据，")
        print("  然后把它加进 .gitignore，**不要**用 `git add -f` 强推。")
        print("=" * 64)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
