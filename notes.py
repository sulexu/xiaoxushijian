# -*- coding: utf-8 -*-
"""笔记存储层：日报 / 周报 / 月报的 Markdown 文件读写与检索。

设计参考 SpringNote（github.com/Radiant303/SpringNote）的笔记体系，落到本系统：

  个人信息统计\笔记\
    日报\2026-09-15.md      一天一篇
    周报\2026-W38.md        一 ISO 周一篇（周一~周日）
    月报\2026-09.md         一自然月一篇

为什么用 Markdown 文件而不是塞进 Excel：
  · 随手记是最高频的写操作，写文件约 1 毫秒，走 Excel 快路径 20~40ms、整表重写 600ms
  · 每次 openpyxl 保存都是对图表/下拉的一次风险，不该让高频写去冒
  · 这套东西的地基本来就是 Markdown（AI 返回 Markdown、用户直接编辑源码）

本模块**不依赖 server.py**，也不做任何 AI 调用 —— 只负责存取、周期换算和检索，
这样能脱离整个系统单独测试。AI 编排在 server.py 里。

关键约定（跟 SpringNote 保持一致）：
  · 文件名即周期标识，周报用 ISO 周历（跨年周归属 ISO 年份，不是自然年）
  · 「有效内容」= 存在非空且不以 # 开头的行。只写了标题的空文件算没有内容，
    这决定了周报该不该生成、已有报告要不要被覆盖。
"""
import base64
import hashlib
import math
import os
import re
import shutil
from datetime import date, datetime, timedelta

# ---------------- 路径 ----------------

KINDS = ("daily", "weekly", "monthly", "essay")
KIND_CN = {"daily": "日报", "weekly": "周报", "monthly": "月报", "essay": "随笔"}
KIND_SUFFIX = {"daily": "日报", "weekly": "周报", "monthly": "月报", "essay": "随笔"}

_ROOT = None                 # 笔记根目录，由 server.py 注入


def set_root(path):
    """由 server.py 在算好 DATA_ROOT 之后调用"""
    global _ROOT
    _ROOT = path


def root():
    if not _ROOT:
        raise RuntimeError("notes.set_root() 还没被调用")
    return _ROOT


def kind_dir(kind, create=False):
    if kind not in KINDS:
        raise ValueError("未知的笔记类型：%s" % kind)
    d = os.path.join(root(), KIND_CN[kind])
    if create:
        os.makedirs(d, exist_ok=True)
    return d


# ---------------- 周期名称 ----------------
# 文件名就是周期标识，所以这三个函数是所有读写的基础

def daily_name(d):
    return d.strftime("%Y-%m-%d")


def essay_name(d):
    """随笔：**按时刻**命名，不是按天。

    ⚠ 一天可以写好几篇随笔，用日报那种 `2026-09-17` 命名会互相覆盖
      —— 而且是**静默覆盖**，用户只会发现"我刚写的没了"。
      带上时分就自然错开了。"""
    return d.strftime("%Y-%m-%d-%H%M")


def weekly_name(d):
    """ISO 周历。跨年周按 ISO 年份命名 —— 2026-12-31 可能属于 2027-W01"""
    y, w, _ = d.isocalendar()
    return "%04d-W%02d" % (y, w)


def monthly_name(d):
    return d.strftime("%Y-%m")


_NAME_RE = {
    "daily": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    # 周数限定 01~53。只写 \d{2} 的话 "2026-W99" 能过校验，
    # 要等到换算日期时才炸，报错还会带着一长串栈信息。
    "weekly": re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$"),
    "monthly": re.compile(r"^\d{4}-(0[1-9]|1[0-2])$"),
    # 随笔按**时刻**命名（一天可以写好几篇，按天会互相覆盖）。
    # ⚠ 加这个 key 是必须的：valid_name 直接查这张表，漏了就是 KeyError，
    #   而报错只有一行 "保存失败: 'essay'"，看不出是哪儿。
    "essay": re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}$"),
}


def valid_name(kind, name):
    """挡掉 ../ 之类的东西 —— 名字直接参与拼路径，必须校验"""
    return bool(name) and bool(_NAME_RE[kind].match(str(name)))


def name_of(kind, d):
    return {"daily": daily_name, "weekly": weekly_name, "monthly": monthly_name}[kind](d)


def parse_name(kind, name):
    """名称 → 该周期的第一天"""
    if kind == "daily":
        return datetime.strptime(name, "%Y-%m-%d").date()
    if kind == "weekly":
        return iso_week_range(name)[0]
    return datetime.strptime(name + "-01", "%Y-%m-%d").date()


def iso_week_range(name):
    """'2026-W28' → (2026-07-06, 2026-07-12)。ISO 第 1 周是含 1 月 4 日的那周"""
    try:
        y, w = str(name).split("-W")
        y, w = int(y), int(w)
        if not (1 <= w <= 53):
            raise ValueError
    except (ValueError, AttributeError):
        raise ValueError("不是合法的 ISO 周：%s" % name)
    jan4 = date(y, 1, 4)
    monday = jan4 - timedelta(days=jan4.isocalendar()[2] - 1) + timedelta(weeks=w - 1)
    # 有的年份只有 52 周。"2026-W53" 这种会一路算出下一年去，必须回头验一下
    if weekly_name(monday) != name:
        raise ValueError("%s 这一年没有第 %d 周" % (y, w))
    return monday, monday + timedelta(days=6)


def week_days(name):
    """该周的 7 个日期（周一~周日）"""
    start, _ = iso_week_range(name)
    return [start + timedelta(days=i) for i in range(7)]


def month_range(name):
    """'2026-09' → (2026-09-01, 2026-09-30)"""
    y, m = int(str(name)[:4]), int(str(name)[5:7])
    first = date(y, m, 1)
    last = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
    return first, last


def week_ym(name):
    """这周该算哪个月 —— 取**天数更多**的那个月。

    跨月的周（W36 = 8/31~9/6）没法两边都算，7 天也不可能对半分，
    所以「多数决」永远不会出现平票。不这么定的话，9 月初那几天会被归到 8 月，
    用户翻 9 月就找不到。
    """
    c = {}
    for d in week_days(name):
        c[(d.year, d.month)] = c.get((d.year, d.month), 0) + 1
    return max(c.items(), key=lambda kv: kv[1])[0]


def display_name(kind, name):
    """给人看的名字。**文件名不变** —— 名字只是显示层。

    文件名（2026-W37）是存储主键：排序、ISO 换算、待补检测、跨月归属全靠它。
    改文件名要迁移，还会引入一堆边界 bug，不值得。
    """
    if kind == "weekly":
        y, w, _ = week_days(name)[0].isocalendar()
        yy, mm = week_ym(name)
        return "%d年%d月 第%d周" % (yy, mm, w)
    if kind == "monthly":
        return "%d年%d月" % (int(name[:4]), int(name[5:7]))
    if kind == "essay":
        try:
            d = datetime.strptime(name, "%Y-%m-%d-%H%M")
            return "%d月%d日 %02d:%02d" % (d.month, d.day, d.hour, d.minute)
        except ValueError:
            return name
    return name


def display_sub(kind, name):
    """副标题：周报给日期区间，月报给起止日，日报给星期"""
    if kind == "weekly":
        a, b = iso_week_range(name)
        return "%d月%d日 – %d月%d日" % (a.month, a.day, b.month, b.day)
    if kind == "monthly":
        a, b = month_range(name)
        return "%d月%d日 – %d月%d日" % (a.month, a.day, b.month, b.day)
    if kind == "essay":
        try:
            d = datetime.strptime(name, "%Y-%m-%d-%H%M")
            return "%d年 星期%s" % (d.year, "一二三四五六日"[d.weekday()])
        except ValueError:
            return ""
    try:
        d = parse_name("daily", name)
        return "星期" + "一二三四五六日"[d.weekday()]
    except ValueError:
        return ""


def title_of(kind, name):
    """写进文件第一行的标题"""
    return "%s %s" % (display_name(kind, name), KIND_CN[kind])


def weeks_overlapping_month(month):
    """落在该自然月内的所有 ISO 周。

    一周只要有日期落在目标月内就算 —— 所以跨月周会同时出现在相邻两个月的
    月报来源里，这是 SpringNote 的既定行为，不是 bug。
    """
    first, last = month_range(month)
    cur = first - timedelta(days=first.weekday())      # 该月第一天所在周的周一
    out = []
    while cur <= last:
        out.append(weekly_name(cur))
        cur += timedelta(days=7)
    return out


# ---------------- 读写 ----------------

def note_path(kind, name):
    if not valid_name(kind, name):
        raise ValueError("非法的%s名称：%s" % (KIND_CN[kind], name))
    return os.path.join(kind_dir(kind), "%s.md" % name)


def default_body(kind, name):
    return "# %s %s\n\n" % (name, KIND_SUFFIX[kind])


def read_raw(kind, name):
    """按原样读文件（可能是密文）。回收站要用它 —— 存明文进去等于把加密白做了。"""
    p = note_path(kind, name)
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def read_note(kind, name):
    """读全文；文件不存在返回 None（跟「读到空内容」区分开）"""
    raw = read_raw(kind, name)
    if raw is None:
        return None
    return decrypt_text(raw)          # 明文原样返回；密文则解密


def write_note(kind, name, content):
    """原子写：先写临时文件再替换，中途出错不会留下半截文件"""
    d = kind_dir(kind, create=True)
    p = os.path.join(d, "%s.md" % name)
    if is_encrypted(content):
        text = content                # 已经是密文（回收站恢复回来的），别再加一层
    else:
        text = encrypt_text(content)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, p)
    return p


# ================================================================
# 笔记加密（可选，默认关）
# ================================================================
# 目标说清楚：**让别人翻到 笔记\ 文件夹、用记事本打开 .md 时看到的是乱码**。
# 它挡不住拿到你电脑的人（内存里的密钥、键盘记录、休眠文件都能拿到），
# 真正的保护仍然是 BitLocker + 系统登录密码。
#
# 做法：AES-256-GCM，密钥由访问密码经 PBKDF2-HMAC-SHA256(20 万次) 派生。
#   · **密码和密钥都不落盘**。盐随文件走，密钥只活在进程内存里，重启要重新解锁。
#   · 每个文件一个随机 nonce（GCM 的硬性要求，重用会直接毁掉安全性）。
#   · GCM 自带完整性校验：文件被改过一个字节就解不开，不会悄悄给你一段错内容。
# 文件长这样（两行，记事本打开一眼能看出是加密的）：
#   小煦拾简·加密笔记 v1
#   <base64(盐16 || nonce12 || 密文+tag)>
ENC_HEAD = "小煦拾简·加密笔记 v1"
ENC_ITER = 200000
_key = None                # bytes(32)，解锁后才有
_salt = None               # bytes(16)，跟着密钥一起记着，写文件时嵌进去


class NoteLocked(Exception):
    """笔记是加密的，但当前进程没有密钥（还没解锁 / 密码被清掉了）"""


def crypto_available():
    """AES-GCM 来自 cryptography 库。免安装版打包时如果没带上它，
    宁可让「开启加密」这个开关直接不可用，也不能假装加密成功。"""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except Exception:
        return False


def derive_key(password, salt):
    return hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, ENC_ITER, 32)


def set_key(key, salt=None):
    global _key, _salt
    _key = key
    if salt:
        _salt = salt


def clear_key():
    global _key, _salt
    _key = None
    _salt = None


def key_set():
    return _key is not None


def is_encrypted(text):
    return str(text or "").startswith(ENC_HEAD)


def encrypt_text(plain):
    """明文 → 加密后的文件内容。没密钥就原样返回（加密没开时的正常路径）。"""
    if _key is None:
        return plain
    salt = _salt or os.urandom(16)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    ct = AESGCM(_key).encrypt(nonce, str(plain).encode("utf-8"), None)
    return "%s\n%s\n" % (ENC_HEAD, base64.b64encode(salt + nonce + ct).decode("ascii"))


def decrypt_text(text):
    """加密文件内容 → 明文。不是密文就原样返回。"""
    if not is_encrypted(text):
        return text
    if _key is None:
        raise NoteLocked("这篇笔记是加密的，当前没有密钥 —— 请重新打开程序并输入访问密码")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    lines = str(text).splitlines()
    try:
        blob = base64.b64decode(lines[1].strip())
        salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
    except Exception:
        raise NoteLocked("这篇笔记的格式不对，可能不是本程序写的")
    # 盐对不上 = 手里这把钥匙跟这篇文件不是一套。直接说清楚，
    # 否则只会笼统报「密码不对」，让人往错的方向查。
    if _salt is not None and salt != _salt:
        raise NoteLocked("这篇笔记是用另一套密钥（另一个密码或另一张盐）加密的，"
                         "当前密码解不开它")
    try:
        return AESGCM(_key).decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        raise NoteLocked("这篇笔记解不开：密码不对，或者文件被改动过")


def ensure_note(kind, name):
    """文件不存在就建一个只有标题的空文件。已存在则原样返回，绝不覆盖"""
    p = note_path(kind, name)
    if not os.path.isfile(p):
        write_note(kind, name, default_body(kind, name))
    return p


def delete_note(kind, name):
    p = note_path(kind, name)
    if os.path.isfile(p):
        os.remove(p)
        return True
    return False


def has_content(md):
    """有没有「实质内容」。

    只写了标题的空文件（# 2026-09-15 日报）算没内容 —— 否则启动补齐会认为
    这一周已经有周报了，永远不会去生成。这条规则跟 SpringNote 一致。
    """
    if not md:
        return False
    for line in md.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return True
    return False


def strip_title(md):
    """去掉开头的一级标题行，用于生成预览"""
    lines = (md or "").splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith("# "):
        i += 1
    return "\n".join(lines[i:]).strip()


def preview(md, limit=80):
    """列表里显示的一行摘要：优先取第一行正文，跳过标题和空行"""
    for line in strip_title(md).splitlines():
        s = line.strip().lstrip("-*#> ").strip()
        if s:
            return s[:limit]
    return ""


def list_notes(kind):
    """列出该类型的全部笔记，按名称倒序（名称是日期，所以就是时间倒序）"""
    d = kind_dir(kind, create=False)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        if not fn.endswith(".md"):
            continue
        name = fn[:-3]
        if not valid_name(kind, name):
            continue
        p = os.path.join(d, fn)
        locked = False
        try:
            st = os.stat(p)
            with open(p, "r", encoding="utf-8") as f:
                md = f.read()
            # 加密的笔记要解开才能算出「有没有内容」和摘要。解不开（没密钥）
            # 就按「有内容、但摘要看不到」处理 —— 绝不能当成空笔记，
            # 否则周报生成会以为这一周什么都没写，直接跳过。
            if is_encrypted(md):
                try:
                    md = decrypt_text(md)
                except NoteLocked:
                    locked = True
                    md = ""
        except OSError:
            continue
        has = True if locked else has_content(md)
        out.append({"name": name,
                    "display": display_name(kind, name),
                    "sub": display_sub(kind, name),
                    "title": "%s %s" % (name, KIND_SUFFIX[kind]),
                    "preview": "（已加密，解锁后可见）" if locked else preview(md),
                    "empty": not has,
                    "chars": st.st_size if locked else len(md),
                    "locked": locked,
                    "mtime": st.st_mtime,
                    "time": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")})
    out.sort(key=lambda x: x["name"], reverse=True)
    return out


# ---------------- 检索 ----------------

def _norm(s):
    return (s or "").lower()


def _hit_positions(md, keywords, cap=80):
    """所有关键词的命中位置（去重后按位置排序）"""
    low = _norm(md)
    pos = []
    for k in keywords:
        kl = _norm(k)
        if not kl:
            continue
        i = 0
        while len(pos) < cap:
            j = low.find(kl, i)
            if j < 0:
                break
            pos.append(j)
            i = j + len(kl)
    return sorted(set(pos))


def make_snippets(md, keywords, width=360, max_windows=2):
    """命中位置附近各截一段，重叠的合并。

    以前只给第一个命中窗口 —— 问「打球和睡觉」时，如果一篇日记里这两件事
    隔得很远，模型就只能看到其中一处，另一半信息白白漏掉。给两段能明显改善。

    返回 (片段文本, 是否有截断)；一个关键词都没命中返回 (None, False)。
    """
    body = md or ""
    pos = _hit_positions(body, keywords)
    if not pos:
        return None, False
    half = max(0, (width - 1) // 2)
    wins = []
    for i in pos:
        a, b = max(0, i - half), min(len(body), i + half)
        if wins and a <= wins[-1][1]:                  # 与上一段重叠 → 合并
            if b > wins[-1][1]:
                wins[-1] = (wins[-1][0], b)
        else:
            wins.append((a, b))
    wins = wins[:max_windows]
    parts, clipped = [], False
    for a, b in wins:
        seg = body[a:b].strip()
        if a > 0:
            seg = "…" + seg
            clipped = True
        if b < len(body):
            seg = seg + "…"
            clipped = True
        parts.append(seg)
    if len(wins) > 1:
        clipped = True                                 # 只给了前两段，别处还有
    return "\n---\n".join(parts), clipped


def score_of(md, name, keywords):
    """相关度打分。

    以前直接按日期倒序 —— 搜「学习」时最新那篇永远排第一，哪怕只是顺带提了
    一句，而真正写了一大段的那篇排在后面。改成：
        命中次数 × 3（封顶 5 次，免得长文靠重复刷分）+ 命中标题 × 5
        再除以 log(长度) 做长度归一
    """
    low, name_low = _norm(md), _norm(name)
    s = 0.0
    for k in keywords:
        kl = _norm(k)
        if not kl:
            continue
        n = low.count(kl)
        if n:
            s += 3.0 * min(n, 5)
        if kl in name_low:
            s += 5.0
    if s <= 0:
        return 0.0
    return s / math.log(len(md) + 20)


def search(keywords, kind=None, limit=20, snippet_width=360):
    """关键词检索，按相关度排序。

    多个关键词按「任一命中」处理（跟 SpringNote 一致）—— 问「上周打球和睡觉」
    时不该因为某天只提到其中一个就漏掉。
    """
    kws = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    if not kws:
        return []
    kinds = [kind] if kind in KINDS else list(KINDS)
    out = []
    for k in kinds:
        for meta in list_notes(k):
            try:
                md = read_note(k, meta["name"]) or ""
            except (OSError, ValueError):
                continue
            sc = score_of(md, meta["name"], kws)
            sn, clipped = make_snippets(md, kws, snippet_width)
            if sn is None:
                if sc > 0:                            # 命中文件名
                    sn, clipped = preview(md, snippet_width), len(md) > snippet_width
                else:
                    continue
            out.append({"kind": k, "kind_cn": KIND_CN[k], "name": meta["name"],
                        "title": meta["title"], "snippet": sn, "score": round(sc, 2),
                        "truncated": clipped or len(md) > len(sn),
                        "totalCharacters": len(md)})
    # 相关度优先，同分再按时间新的在前。
    # 两趟稳定排序：先排时间，再排分数 —— 第二次排序不会打乱同分者的时间序
    out.sort(key=lambda x: x["name"], reverse=True)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:limit]


# ---------------- 备份 ----------------

def backup_files():
    """笔记全是纯文本，备份成本几乎为零，直接整目录复制一份"""
    d = root()
    if not os.path.isdir(d):
        return None
    return d


def copy_tree(dest):
    """把整个笔记目录复制到 dest（用于 _自动备份）"""
    src = root()
    if not os.path.isdir(src):
        return False
    if os.path.exists(dest):
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(src, dest)
    return True


# ---------------- 待生成报告 ----------------

def daily_dates_with_content():
    """所有有实质内容的日报日期（升序）"""
    out = []
    for meta in list_notes("daily"):
        if not meta["empty"]:
            try:
                out.append(parse_name("daily", meta["name"]))
            except ValueError:
                pass
    out.sort()
    return out


def _earliest_daily():
    ds = daily_dates_with_content()
    return ds[0] if ds else None


def missing_weekly(today):
    """已结束、有来源日报、但还没写内容的周报（升序）"""
    first = _earliest_daily()
    if not first:
        return []
    have = {m["name"] for m in list_notes("weekly") if not m["empty"]}
    have_src = {daily_name(d) for d in daily_dates_with_content()}
    out = []
    cur = first - timedelta(days=first.weekday())
    while True:
        end = cur + timedelta(days=6)
        if end >= today:                       # 本周还没结束，不补
            break
        nm = weekly_name(cur)
        if nm not in have:
            if any(daily_name(cur + timedelta(days=i)) in have_src for i in range(7)):
                out.append(nm)
        cur += timedelta(days=7)
        if len(out) > 60:                      # 兜底，别把首次启动拖死
            break
    return out


def missing_monthly(today):
    """已结束、有来源周报、但还没写内容的月报（升序）"""
    have = {m["name"] for m in list_notes("monthly") if not m["empty"]}
    weeks = [m["name"] for m in list_notes("weekly") if not m["empty"]]
    if not weeks:
        return []
    # 月份必须从周报的**日期范围**推，不能从 "2026-W36" 里切字符串
    # （w[5:7] 会切出 "W3"）。跨月周同时属于相邻两个月。
    months = set()
    for w in weeks:
        try:
            a, b = iso_week_range(w)
        except ValueError:
            continue
        months.add(monthly_name(a))
        months.add(monthly_name(b))
    this_month = today.replace(day=1)
    out = []
    for mo in sorted(months):
        if month_range(mo)[1] >= this_month:      # 本月还没过完，不补
            continue
        if mo not in have:
            out.append(mo)
    return out


_OLD_TITLE = {
    "weekly": re.compile(r"^#\s*\d{4}-W\d{2}\s*周报\s*$"),
    "monthly": re.compile(r"^#\s*\d{4}-\d{2}\s*月报\s*$"),
}


def migrate_titles():
    """把老格式的标题换成新的。

    **只改第一行，而且只改长得像老格式的** —— 你自己手改过的标题不动。
    换完就再也不匹配了，所以这个函数反复跑是安全的。
    """
    changed = []
    for kind in ("weekly", "monthly"):
        pat = _OLD_TITLE[kind]
        for m in list_notes(kind):
            try:
                md = read_note(kind, m["name"])
            except (OSError, ValueError):
                continue
            if not md:
                continue
            lines = md.split("\n")
            if lines and pat.match(lines[0].strip()):
                lines[0] = "# %s" % title_of(kind, m["name"])
                write_note(kind, m["name"], "\n".join(lines))
                changed.append("%s %s" % (KIND_CN[kind], m["name"]))
    return changed


def pending(today=None):
    """启动后台补齐用：哪些周期缺报告"""
    today = today or date.today()
    try:
        return {"weekly": missing_weekly(today), "monthly": missing_monthly(today)}
    except Exception:
        return {"weekly": [], "monthly": []}
