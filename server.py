# -*- coding: utf-8 -*-
"""小煦拾简 · 本地服务器（零第三方依赖，仅 openpyxl + 标准库）

数据源 = 上级工作区里的三个 Excel 文件：
  账单   账单/大二上/大二上账单_新.xlsx    （记录 / 周边尾款 / 汇总 / 图表）
  打卡   每日打卡表.xlsx                   （设置 / 2026年09~12月 / 梦境档案）
  物资   寝室部分物资清单.xlsx             （药品 / 日用品 / 零食 / 总览 / 待办 / 应急信息）

用法：python server.py  →  自动打开浏览器 http://127.0.0.1:8765
数据根目录可用环境变量 STATS_ROOT 覆盖（自测时指向测试副本）。

写入策略（已实测）：openpyxl 往返保存三个工作簿后，图表/图形/下拉/条件格式
全部完好；公式会保留、由 Excel 打开时重算（保存时置 fullCalcOnLoad）。
写操作全部走“临时文件 + 原子替换”，文件被 Excel 占用时会给出明确报错。
"""
import base64
import copy
import hashlib
import hmac
import json
import os
import secrets
import sys
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
from calendar import monthrange
from datetime import date, datetime, timedelta, time as dtime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import openpyxl
import store
import export
import vision
from openpyxl.formatting.rule import CellIsRule
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

import notes                      # 日报/周报/月报的 Markdown 存取（纯文件层，不依赖本文件）

# ---------------- 路径 ----------------
# 打包成 exe 后要区分两种目录：
#   · 可写目录（配置、备份、日志）= exe 所在目录 —— 绝不能写进 PyInstaller 的
#     临时解包目录，那里退出就被清空，配置会丢
#   · 只读资源（static 网页文件）= 解包目录 _MEIPASS
# 开发时两者都等于本脚本所在目录，行为不变。
def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _res_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", _app_dir())
    return os.path.dirname(os.path.abspath(__file__))


def _find_data_root(start):
    r"""从 start 开始往上找放着三个 Excel 的那一层。

    打包后 exe 在「小煦拾简」文件夹里、数据在上层「个人信息统计」文件夹里，
    所以不能只看一层。找不到就退回 start（后面 MISSING 检查会明确报出来）。
    """
    marks = ["每日打卡表.xlsx", "寝室部分物资清单.xlsx", "账单"]
    d = start
    for _ in range(3):
        if any(os.path.exists(os.path.join(d, m)) for m in marks):
            return d
        up = os.path.dirname(d)
        if not up or up == d:
            break
        d = up
    return start


BASE = _app_dir()                     # 可写：配置 / 备份
RES = _res_dir()                      # 只读：static
# 数据（三个 Excel）：Electron 会传 STATS_ROOT 精确指定；
# 单独跑 server.exe（比如浏览器版）时自己往上找一层。
DATA_ROOT = os.environ.get("STATS_ROOT") or _find_data_root(os.path.dirname(BASE))
BILL_ROOT = os.path.join(DATA_ROOT, "账单")
CHECK = os.path.join(DATA_ROOT, "每日打卡表.xlsx")
STOCK = os.path.join(DATA_ROOT, "寝室部分物资清单.xlsx")
WEB = os.path.join(RES, "static")
# 备份放在数据目录旁（跟三个 Excel 一起），不放应用目录：
# 一是数据在哪备份就在哪更直观，二是自测/E2E 用副本跑时不会把测试数据备到应用目录里
BACKUP_DIR = os.path.join(DATA_ROOT, "_自动备份")
BACKUP_KEEP = 7                      # 每个文件保留最近几份每日备份

# ---------------- 数据库 ----------------
# 数据现在住在 SQLite 里（标准库自带，零依赖这条底线没破）。
# 三本 Excel 还在原地，但降级成了「导出格式」—— 想用 Excel 看就导出，
# 迁移时也会自动复制一份存档，不会删。
DATA_DB = store.db_path(DATA_ROOT)
store.use(DATA_DB)
store.init()
# 配置文件也放数据目录：程序文件夹是可以整个换掉的（升级/重装），
# 配置放程序里一换就丢 —— API Key 丢了用户只会看到"AI 突然不能用了"。
# 自测用 STATS_ROOT 指向副本时，配置也跟着隔离，不会动到真实 Key。
CONF_DIR = os.path.join(DATA_ROOT, "_配置")
# 日报/周报/月报的 Markdown 笔记（跟三个 Excel 并排放在数据目录里）
NOTES_ROOT = os.path.join(DATA_ROOT, "笔记")
notes.set_root(NOTES_ROOT)
AI_CONFIG = os.path.join(CONF_DIR, "ai_config.json")   # 放 static 外面，不会被 HTTP 暴露
DATA_CONFIG = os.path.join(CONF_DIR, "data_config.json")   # 当前学期等
PORT = int(os.environ.get("STATS_PORT") or 8765)


def _migrate_conf():
    """早期版本把配置写在程序目录里，搬到数据目录的 _配置 下（只搬一次）。

    不搬的话用户升级后 API Key 就"消失"了，只会看到 AI 功能莫名其妙不能用了。
    """
    if os.environ.get("STATS_ROOT"):
        return            # 自测/E2E 模式：BASE 还是源码目录，别把真实 Key 搬进测试副本
    for name in ("ai_config.json", "data_config.json", "ai_usage.json", "ai_analysis.json"):
        old = os.path.join(BASE, name)
        new = os.path.join(CONF_DIR, name)
        if os.path.exists(old) and not os.path.exists(new):
            try:
                os.makedirs(CONF_DIR, exist_ok=True)
                shutil.move(old, new)
            except OSError:
                pass          # 搬不动就算了，不耽误启动


_migrate_conf()

# 账单按学期分目录放（账单\大二上\...）。BILL 是可变全局：
# 全仓的读写函数都是迟绑定引用它，所以切换学期只要重新赋值即可，一行调用点都不用改。
DEFAULT_SEMESTER = "大二上"
SEMESTER = DEFAULT_SEMESTER
BILL = os.path.join(BILL_ROOT, DEFAULT_SEMESTER, DEFAULT_SEMESTER + "账单_新.xlsx")


def missing_files():
    """每次调用重新算 —— 切学期后路径变了，写死一次会误报或漏报"""
    return [p for p in (BILL, CHECK, STOCK) if not os.path.exists(p)]


MISSING = missing_files()            # 保留这个名字，兼容启动检查

# ---------------- 缓存（按文件 mtime 失效） ----------------
_cache = {}
_cache_lock = threading.Lock()
# ⚠ 必须是 **RLock（可重入）**，不能是普通 Lock。
#
#   它护的是「写文件/写库」这**一件事**，而几个辅助函数是「谁调都自己加锁」
#   的写法 —— 最典型的是 _save_json()，它自己 `with _write_lock`。
#   于是只要有一个调用方**先持锁再调它**，普通 Lock 当场自锁死：
#
#       with _write_lock:          # semester_switch 第 374 行
#           _save_data_config()    # → _save_json() → with _write_lock ← 死在这儿
#
#   2.4.6 实测撞上：在设置页点一次「切换学期」，那个请求线程就永久卡住，
#   而且**锁没释放** —— 之后所有写操作（记一笔、打卡、改物资）全部跟着挂起，
#   整个程序看起来「卡了」。查了半天才定位到是自锁，不是慢。
#
#   为什么一直没发现：**自测从来没覆盖过学期切换**（_自测.py 和 _test.html
#   里连一个 semester 都没有），所以这条路径从写出来那天就是坏的，
#   而用户只有这一个学期、从没点过那个按钮。
#
#   换 RLock 之后语义不变（跨线程照样互斥），只是同一个线程可以再进来一次 ——
#   这正是「辅助函数自己加锁」这个写法本来就依赖的前提。
_write_lock = threading.RLock()


def cached(path, loader):
    """缓存键 = 文件 mtime + **数据版本号**。

    只看 mtime 是不够的：写数据库根本不碰 Excel 文件，mtime 一点不动，
    改完数据页面还会一直显示旧的。store.rev() 每次写自增一次，
    同一秒里改两次也分得清（这正是当年 mtime 方案漏掉的）。
    过渡期两种存储混着用，所以两把尺子都量上，谁变了都算失效。"""
    try:
        st = os.stat(path)
        fk = (st.st_mtime_ns, st.st_size)
    except OSError:
        fk = None
    # 只查一个 kv 单行，代价可以忽略
    try:
        key = (fk, store.rev())
    except Exception:
        key = (fk, None)
    with _cache_lock:
        hit = _cache.get(path)
        if hit and hit[0] == key:
            return hit[1]
        data = loader(path)
        _cache[path] = (key, data)
        return data


def drop_cache(path):
    with _cache_lock:
        _cache.pop(path, None)


# ---------------- 通用小工具 ----------------
def dstr(v):
    """日期/时间 → 'YYYY-MM-DD' 字符串"""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return str(v) if v is not None else ""


def to_date(s):
    """'YYYY-MM-DD' → datetime；空 → None"""
    if not s:
        return None
    return datetime.strptime(s.strip()[:10], "%Y-%m-%d")


def to_time_fraction(s):
    """'HH:MM' → 一天中的小数（与打卡表 C/D 列口径一致）；空 → None"""
    if not s:
        return None
    h, m = s.strip().split(":")
    return (int(h) * 3600 + int(m) * 60) / 86400.0


def frac_to_time(v):
    """小数 / datetime.time / 'HH:MM' 文本 → 统一 'HH:MM'
    （openpyxl 往返保存后，时间单元格会变成 datetime.time，三种都要接住）"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dtime):
        return "%02d:%02d" % (v.hour, v.minute)
    mins = round(float(v) * 24 * 60)
    return "%02d:%02d" % (mins // 60, mins % 60)


def to_num(s):
    if s is None or str(s).strip() == "":
        return None
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return str(s).strip()


def backup_root():
    """备份放哪。设置里填了自定义目录就用它，否则用数据目录下的 _自动备份。
    读设置时会吞异常 —— 备份路径读不出来也绝不能挡住正常保存。"""
    try:
        d = str(settings_load().get("backup_dir") or "").strip()
        if d:
            return d
    except Exception:
        pass
    return BACKUP_DIR


def backup_roots():
    """出现在界面上的备份目录：当前用的 + 老地方。
    用户改过备份路径后，老备份还在 _自动备份 里，不列出来就等于「备份不见了」。"""
    cur = backup_root()
    out = [cur]
    if os.path.normcase(os.path.abspath(cur)) != os.path.normcase(os.path.abspath(BACKUP_DIR)):
        out.append(BACKUP_DIR)
    return out


def backup_keep():
    try:
        n = int(settings_load().get("backup_keep") or BACKUP_KEEP)
    except Exception:
        n = BACKUP_KEEP
    return max(1, min(200, n))


def auto_backup(path):
    """写之前每天留一份备份，保留最近 N 份。
    备份失败绝不能挡住正常保存，所以整个函数吞掉异常。"""
    try:
        root = backup_root()
        os.makedirs(root, exist_ok=True)
        name = os.path.splitext(os.path.basename(path))[0]
        dst = os.path.join(root, "%s_%s.xlsx" % (name, date.today().strftime("%Y%m%d")))
        if os.path.exists(dst):          # 今天已经备过，直接返回（每天只备一次）
            return
        shutil.copy2(path, dst)
        keep = backup_keep()
        olds = sorted(f for f in os.listdir(root)
                      if f.startswith(name + "_") and f.endswith(".xlsx"))
        for f in olds[:-keep]:           # 只留最近 N 份
            try:
                os.remove(os.path.join(root, f))
            except OSError:
                pass
    except Exception:
        pass


# ================================================================
# 学期管理
# ================================================================
def _semester_bill_file(sem):
    """在 账单\\{学期}\\ 里找账单数据文件：含「记录」sheet、且不是备份"""
    d = os.path.join(BILL_ROOT, sem)
    if not os.path.isdir(d):
        return None
    cands = []
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".xlsx") or f.startswith("备份_") or f.startswith("~$"):
            continue
        cands.append(os.path.join(d, f))
    for p in cands:                       # 优先认带「账单」二字的
        if "账单" in os.path.basename(p):
            return p
    for p in cands:                       # 否则看谁有「记录」sheet
        try:
            wb = openpyxl.load_workbook(p, read_only=True)
            ok = "记录" in wb.sheetnames
            wb.close()
            if ok:
                return p
        except Exception:
            continue
    return cands[0] if cands else None


def list_semesters():
    out = []
    try:
        names = sorted(os.listdir(BILL_ROOT))
    except OSError:
        names = []
    for sem in names:
        if sem.startswith("_") or sem.startswith("."):
            continue
        if not os.path.isdir(os.path.join(BILL_ROOT, sem)):
            continue
        f = _semester_bill_file(sem)
        # ⚠ 条数从**库里**数，不从那个 .xlsx 数。
        #   2.0 换存储之后写入全进 SQLite，Excel 只在「导出」时才重新生成 ——
        #   拿它数出来的条数从换存储那天起就偏了，而且**只会越差越多**，
        #   还不会报错。（2.4.6 实测：设置页显示 106，库里其实是 104。）
        #   目录扫描还留着：学期的"注册表"仍是 账单\<学期>\ 这一层，
        #   新建学期要在那儿落一个模板文件。
        n = store.one("SELECT COUNT(*) FROM bill WHERE sem=?", (sem,), 0)
        out.append({"name": sem, "file": os.path.basename(f) if f else None,
                    "records": n, "active": sem == SEMESTER})
    return {"semesters": out, "current": SEMESTER,
            "bill_dir": os.path.relpath(BILL_ROOT, DATA_ROOT)}


def _save_data_config():
    """把当前学期落盘。**成功返回 True，失败返回 False（不抛异常）。**

    ⚠ 这里原来是 `except Exception: pass` —— 弹层直接吞掉。
    `_save_data_config()` 是"改全局状态"的那条路径，调用方**必须**知道
    有没有真的存住；吞掉返回值的话，调用方只能无条件说"成功"。
    见 semester_switch()：落盘失败时界面会说"已切到 X"，而重启后
    仍然是旧学期 —— 静默说反话，正是 §5.3 最不能接受的那种。
    """
    try:
        cfg = _load_json(DATA_CONFIG, {})
        cfg["semester"] = SEMESTER
        _save_json(DATA_CONFIG, cfg)
        return True
    except Exception as e:
        log_error("save_data_config", e)
        return False


def load_data_config():
    """启动时按配置恢复上次用的学期"""
    global SEMESTER, BILL
    sem = str(_load_json(DATA_CONFIG, {}).get("semester") or "").strip()
    if sem and os.path.isdir(os.path.join(BILL_ROOT, sem)):
        f = _semester_bill_file(sem)
        if f:
            SEMESTER, BILL = sem, f
            return
    SEMESTER, BILL = DEFAULT_SEMESTER, os.path.join(
        BILL_ROOT, DEFAULT_SEMESTER, DEFAULT_SEMESTER + "账单_新.xlsx")


def semester_switch(body):
    """切换当前学期。只重新绑定全局 BILL + 清缓存，不动任何数据文件。"""
    global SEMESTER, BILL
    name = str(body.get("name") or "").strip()
    if not name:
        return False, "没指定学期"
    if name == SEMESTER:
        return True, "已经在这个学期了"
    f = _semester_bill_file(name)
    if not f:
        return False, "「%s」里没找到账单文件（应有 账单\\%s\\*账单*.xlsx）" % (name, name)
    with _write_lock:
        old, old_sem = BILL, SEMESTER
        SEMESTER, BILL = name, f
        # ⚠ 落盘失败必须回头，不能把「内存里改了」当成「切好了」。
        #   原来这里不看返回值，于是无论存没存住都往下走到
        #   `return True, "已切到「%s」"` —— 界面说成功，重启回到旧学期。
        #   现在失败就把内存状态退回去，并说清「只是没记住，数据没动」。
        saved = _save_data_config()
        if not saved:
            SEMESTER, BILL = old_sem, old
            return False, ("切到「%s」没存住（数据文件没有动，还是「%s」）。"
                           "多半是磁盘满、或者配置文件被杀毒软件锁住了，"
                           "看一眼 设置 → 错误日志。" % (name, old_sem))
    drop_cache(old)
    drop_cache(BILL)
    # AI 分析是按 scope 缓存的、不含学期，不清掉会拿旧学期的结论冒充
    try:
        cache = _load_json(AI_ANALYSIS_FILE, {})
        for k in ("all", "bill"):
            cache.pop(k, None)
        _save_json(AI_ANALYSIS_FILE, cache)
    except Exception:
        pass
    return True, "已切到「%s」" % name


def semester_create(body):
    """新建学期：复制当前学期当模板，清空记录，保留类别/公式/格式/下拉"""
    name = str(body.get("name") or "").strip()
    if not name:
        return False, "没填学期名"
    if any(c in name for c in '\\/:*?"<>|'):
        return False, "学期名不能包含 \\ / : * ? \" < > |"
    d = os.path.join(BILL_ROOT, name)
    if os.path.isdir(d) and os.listdir(d):
        return False, "「%s」已经存在了" % name
    src = BILL
    if not os.path.exists(src):
        return False, "找不到当前学期的账单文件，无法作为模板"
    os.makedirs(d, exist_ok=True)
    # 文件名带上学期，避免 _自动备份 按 basename 保留时跨学期互相顶掉
    dst = os.path.join(d, name + "账单_新.xlsx")
    with _write_lock:
        shutil.copy2(src, dst)
        wb = openpyxl.load_workbook(dst)
        ws = wb["记录"]
        cleared = 0
        for r in range(2, 1004):
            if ws.cell(r, 1).value is None:
                continue
            cleared += 1
            for c in range(1, 11):
                ws.cell(r, c).value = None          # 只清值，样式/公式列保留
        wt = wb["周边尾款"]
        tcleared = 0
        for r in range(2, 1001):
            if wt.cell(r, 1).value is None:
                continue
            tcleared += 1
            for c in range(1, 8):
                wt.cell(r, c).value = None
        if "汇总" in wb.sheetnames:               # 标题跟着换
            wb["汇总"].cell(1, 1).value = "%s · 记账汇总" % name
        # 预算清空（新学期重新设）
        ws2 = wb["汇总"]
        for r in range(1, min(ws2.max_row, 400) + 1):
            if str(ws2.cell(r, 1).value or "").strip() == "月份":
                for rr in range(r + 1, r + 25):
                    if not ws2.cell(rr, 1).value or str(ws2.cell(rr, 1).value) == "合计":
                        break
                    ws2.cell(rr, 5).value = None
                break
        save_atomic(wb, dst)
    # ⚠ 类别必须**从库里复制一份到新学期**，光靠上面那个 Excel 模板不够。
    #   2.0 换存储之后类别住在 cat 表里、按 sem 分区，而上面整个 with 块
    #   只动 Excel —— 于是新建出来的学期一条类别都没有：账单页的分类下拉是空的，
    #   记一笔时无类别可选。**更糟的是返回的消息还写着「类别和格式都保留」**，
    #   等于撒了个谎，用户只会以为类别是真带过来了。
    #   2.4.6 实测复现（隔离副本里）：_cats_of("大二下") → ([], [])，
    #   cat 表里只有「大二上」那 27 条。用户定的是「从当前学期复制」。
    n_cat = 0
    with store.tx("bill") as c:
        # ⚠ 先 fetchall 再插 —— 边遍历游标边往同一个游标上 execute，
        #   遍历会被打断（这个项目在别处已经栽过一次同类问题）。
        rows = c.execute("SELECT kind,name,ord FROM cat WHERE sem=?"
                         " ORDER BY kind,ord", (SEMESTER,)).fetchall()
        for kind, nm, o in rows:
            c.execute("INSERT OR REPLACE INTO cat(sem,kind,name,ord) VALUES(?,?,?,?)",
                      (name, kind, nm, o))
            n_cat += 1
    return True, "已新建学期「%s」（清空了 %d 条流水、%d 条尾款，%d 个类别照搬过来了）" % (
        name, cleared, tcleared, n_cat)


def semesters_compare():
    """跨学期对比：只取每学期的总收支，不按月份合并（避免不同学年同月份撞车）"""
    out = []
    for s in list_semesters()["semesters"]:
        try:
            b = load_bill(sem=s["name"])
            out.append({"name": s["name"], "inc": b["kpi"]["inc"], "exp": b["kpi"]["exp"],
                        "bal": b["kpi"]["bal"], "records": len(b["records"]),
                        "from": min((r["date"] for r in b["records"]), default=""),
                        "to": max((r["date"] for r in b["records"]), default="")})
        except Exception as e:
            out.append({"name": s["name"], "error": str(e)})
    return out


def export_excel(body=None):
    """一键把库里的数据导出成三本 Excel。

    导出到数据根下的「_导出」文件夹，文件名带日期 —— 同一天导两次会覆盖，
    但**不会碰任何原始文件**。想留着就自己改个名。"""
    dest = os.path.join(DATA_ROOT, "_导出")
    try:
        files = export.export_all(dest, sys.modules[__name__])
    except PermissionError:
        return False, "导出失败：目标文件正被 Excel/WPS 打开，先关掉再试"
    except Exception as e:
        log_error("export_excel", e)
        return False, "导出失败：%s" % e
    # ⚠ 必须是 **3 元组** (ok, msg, data)。写成 (True, {...}) 的话路由会把
    # 那个 dict 当成 msg，data 位置是空的 —— 前端 r.data 拿到 undefined，
    # 而且不报错，只是「点了没反应」，极难查。
    return True, "已导出三本 Excel 到 %s" % dest, {
        "dir": dest,
        "files": [{"name": k, "path": v} for k, v in files.items()],
    }


# ---------------- 换数据目录（2.3.6）----------------
# 设置页里能换数据放哪儿，换了要把东西搬过去。
#
# ⚠ 顺序是**复制 → 校验 → 最后才删源**，一步都不能提前。
#   反过来（先删再复制）中途断电/被杀毒拦/目标盘写满，就是两边都没有。
#   这个功能必须做成一「最坏情况是留下两份」，而不是「最坏情况是全丢」。
#   删源还得用户**明确点过一次**（前端确认框里选「删掉旧的」），不默认删。
#
# ⚠ 搬之前先把 WAL 收回去。数据库开着 WAL，最近几次写入可能还在
#   `-wal` 那个旁挂文件里；只拷 .db 会丢掉最后几条记录，而且**不报错**
#   ——拷过去的库能打开、就是少东西，最难查的那种。
# ⚠ 这份清单必须**把数据目录里所有属于「数据」的东西都列上**。
#   原来只有 5 项，漏了 附件 / 账单 / _回收站 —— 它们的后果分别是：
#     · 附件\   → **账单截图和睡眠截图的原图**（attach 表按 `202609/x.jpg`
#                 这样的相对路径指向它）。搬完截图全打不开，而且不报错。
#     · 账单\   → 学期目录。list_semesters() 是扫这个目录来列学期的，
#                 搬完学期管理直接空掉。
#     · _回收站\ → 删掉的东西捡不回来了。
#   2.4.6 实测发现：这个数据目录里 附件\ 有 10 条 attach 记录指着，
#   照原清单搬完就是「数据看着都在、图全裂了」。
MOVE_ITEMS = ["小煦拾简.db", "_配置", "笔记", "附件", "账单",
              "_回收站", "_自动备份", "_导出"]
# 「欠条」文件名：换目录时说好要删的旧位置，记在这儿，下次启动再执行
PURGE_MARK = "待删除的旧目录.txt"


def CONF_DIR_NEW(root):
    return os.path.join(root, "_配置")


def _purge_pending():
    """把上一次「换数据目录」欠下的删除做完（2.3.6）。

    ⚠ 欠条里写的是**绝对路径**，所以宁可少删也不能多删：
      · 只删认得出的那几样（见 MOVE_ITEMS），**不整个 rmtree 欠条上那个路径**
      · 当前正在用的目录一律不碰
      · 只认盘符下面至少两层的路径，防止欠条被改成一个盘根
      · 删不掉就留着欠条下次再试，不报错打扰用户
    """
    mark = os.path.join(CONF_DIR, PURGE_MARK)
    if not os.path.isfile(mark):
        return
    try:
        old = open(mark, encoding="utf-8").read().strip()
    except OSError:
        return
    cur = os.path.abspath(DATA_ROOT)
    old = os.path.abspath(old) if old else ""
    if (not old or old == cur or old == os.path.dirname(old)
            or cur.startswith(old + os.sep)):
        _drop_mark(mark)
        return
    left = []
    for name in MOVE_ITEMS:
        p = os.path.join(old, name)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)
        except OSError:
            left.append(name)               # 有东西还占着，下次再说
    if left:
        print("[数据] 旧目录还有 %d 样删不掉，下次启动再试：%s" % (len(left), "、".join(left)))
    else:
        _drop_mark(mark)
        print("[数据] 旧数据目录已清理：%s" % old)


def _drop_mark(mark):
    try:
        os.remove(mark)
    except OSError:
        pass


def _tree(root):
    """列一个目录下所有文件，返回 [(相对路径, 字节数)]。"""
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            fp = os.path.join(dirpath, f)
            try:
                out.append((os.path.relpath(fp, root), os.path.getsize(fp)))
            except OSError:
                pass
    return sorted(out)


def _move_plan(to):
    """要搬哪些东西、各多大。返回 (清单, 总字节, 错误信息)"""
    to = os.path.abspath(to or "")
    if not to:
        return [], 0, "没给目标目录"
    cur = os.path.abspath(DATA_ROOT)
    # ⚠ 目标不能套在源里面（会自己拷自己，无限递归），也不能把源套进去
    if to == cur:
        return [], 0, "这就是当前目录，不用搬"
    if to.startswith(cur + os.sep) or cur.startswith(to + os.sep):
        return [], 0, "新旧目录不能互相包含（选个别的盘或别的文件夹）"
    items = []
    for name in MOVE_ITEMS:
        p = os.path.join(cur, name)
        if os.path.isfile(p):
            items.append({"name": name, "kind": "文件", "files": 1,
                          "bytes": os.path.getsize(p)})
        elif os.path.isdir(p):
            tr = _tree(p)
            items.append({"name": name, "kind": "文件夹", "files": len(tr),
                          "bytes": sum(s for _f, s in tr)})
    # 三本 Excel 也一起搬 —— 它们是「导出格式」，但用户可能还在用
    for name in ("每日打卡表.xlsx", "寝室部分物资清单.xlsx"):
        p = os.path.join(cur, name)
        if os.path.isfile(p):
            items.append({"name": name, "kind": "文件", "files": 1,
                          "bytes": os.path.getsize(p)})
    return items, sum(i["bytes"] for i in items), ""


def data_inspect(body=None):
    """换目录**之前**先看一眼：搬什么、多大、目标能不能写。不动任何东西。"""
    body = body or {}
    to = str(body.get("to") or "")
    items, total, err = _move_plan(to)
    if err:
        return False, err, None
    ok_dir = os.path.isdir(to)
    try:
        if ok_dir:
            probe = os.path.join(to, ".xr_writable")
            with open(probe, "w") as fh:
                fh.write("1")
            os.remove(probe)
        writable = ok_dir
    except OSError as e:
        return False, "目标目录写不进去：%s" % e, None
    if not ok_dir:
        # 还没建就先建 —— 建不出来（盘符不存在、没权限）当场说清楚
        try:
            os.makedirs(to, exist_ok=True)
            writable = True
        except OSError as e:
            return False, "建不了这个目录：%s" % e, None
    return True, "看好了", {
        "from": os.path.abspath(DATA_ROOT), "to": os.path.abspath(to),
        "items": items, "total": total, "writable": writable,
        "same": os.path.abspath(to) == os.path.abspath(DATA_ROOT),
    }


def data_move(body=None):
    """真搬。复制 → 逐项校验 → （用户要求的话）删源。

    ⚠ 校验不通过就**原地停下、不删任何东西**，并且把已经复制过去的那份留着
      —— 让用户自己看着办，总比替他决定删掉强。"""
    body = body or {}
    to = str(body.get("to") or "")
    purge = bool(body.get("purge"))
    items, total, err = _move_plan(to)
    if err:
        return False, err, None
    if not items:
        return False, "数据目录里没找到可搬的东西", None

    # ① 把 WAL 收回主库（见上面那段说明，不做这步会静默丢最后几条）
    # ⚠ 不能用 store.tx() —— checkpoint 不能在事务里跑（会直接报错），
    #   拿当前线程那条连接裸执行就行。
    try:
        store.conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception as e:
        log_error("data_move.checkpoint", e)

    os.makedirs(to, exist_ok=True)
    copied = []
    try:
        for it in items:
            src = os.path.join(os.path.abspath(DATA_ROOT), it["name"])
            dst = os.path.join(to, it["name"])
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            copied.append(it["name"])
    except (OSError, shutil.Error) as e:
        log_error("data_move.copy", e)
        return False, "复制到一半失败了：%s（原数据一个字没动，放心）" % e, {
            "copied": copied, "purged": False}

    # ② 逐项校验。**不通过就停在这儿**，源一个字节都不删。
    bad = []
    for it in items:
        src = os.path.join(os.path.abspath(DATA_ROOT), it["name"])
        dst = os.path.join(to, it["name"])
        if os.path.isfile(src):
            if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
                bad.append(it["name"])
        else:
            a, b = _tree(src), _tree(dst)
            if len(a) != len(b) or [f for f, _s in a] != [f for f, _s in b] or \
               sum(s for _f, s in a) != sum(s for _f, s in b):
                bad.append(it["name"])
    # 数据库还要能真的打开、条数对得上 —— 只比字节数不够
    try:
        src_db = os.path.join(os.path.abspath(DATA_ROOT), "小煦拾简.db")
        dst_db = os.path.join(to, "小煦拾简.db")
        if os.path.exists(src_db):
            def counts(p):
                c = store.connect(p)          # 走 store 那层，连接参数（WAL 等）一致
                try:
                    out = {}
                    for (t,) in c.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"):
                        try:
                            out[t] = c.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
                        except Exception:
                            pass
                    return out
                finally:
                    c.close()
            if counts(src_db) != counts(dst_db):
                bad.append("小煦拾简.db（内容对不上）")
    except Exception as e:
        log_error("data_move.verify", e)
        bad.append("小煦拾简.db（校验时出错：%s）" % e)

    if bad:
        return False, "校验没通过，**原数据一个字没删**。有问题的：%s" % "、".join(bad), {
            "copied": copied, "purged": False, "to": to}

    # ③ 校验全过，才轮到删源 —— 而且要用户明确要求过
    purged = False
    if purge:
        # ⚠ Windows 上**删不掉自己正开着的数据库文件**，报 WinError 32
        #   「另一个程序正在使用此文件」—— 那个"另一个程序"就是本进程。
        #   （自测里当场撞上了。）而且这套是**每线程一条连接**，
        #   主线程、后台回填线程手里各有一条，store.close() 只关当前线程那条，
        #   根本没法保证全放开。
        #   所以不硬删：在这里写一张**欠条**，等下次启动、谁都没开库的时候再删。
        #   代价是「删旧的」要等到下次开机才生效，好处是永远不会删一半失败。
        try:
            os.makedirs(CONF_DIR_NEW(to), exist_ok=True)
            with open(os.path.join(CONF_DIR_NEW(to), PURGE_MARK), "w",
                      encoding="utf-8") as fh:
                fh.write(os.path.abspath(DATA_ROOT))
        except OSError as e:
            log_error("data_move.mark", e)

    # ⚠ 必须是**一个** 3 元组 (ok, msg, data)。写成两行会被解析成
    #   `return (True, msg), {...}` —— 路由拿到的是个二元组，data 位置错位，
    #   前端 r.data 拿到 undefined 而且不报错。这个坑在本项目里踩过。
    return True, ("搬完了，下次启动会自动清掉旧目录" if purge else "搬完了"), {
        "copied": copied, "purged": purged, "purge_pending": bool(purge),
        "to": to, "from": os.path.abspath(DATA_ROOT)}


def data_files():
    """三个数据文件：{显示名: 路径}"""
    return {"每日打卡表": CHECK, "寝室部分物资清单": STOCK, "账单": BILL}


def _backup_target_of(filename):
    """备份文件名 → 属于哪个数据文件。前缀最长匹配（账单的文件名带学期，要优先匹配）"""
    base = os.path.basename(filename)
    if not base.endswith(".xlsx"):
        return None
    best = None
    for label, path in data_files().items():
        stem = os.path.splitext(os.path.basename(path))[0]
        if base.startswith(stem + "_") and (best is None or len(stem) > len(best[1])):
            best = (label, stem, path)
    return best


def _stamp_file(path):
    """一个文件的「戳」：修改时间 + 大小。用来判断内容变没变。"""
    try:
        st = os.stat(path)
        return "%d-%d" % (st.st_mtime_ns, st.st_size)
    except OSError:
        return ""


def _stamp_notes():
    """笔记目录：最新修改时间 + 文件数。目录里任何一篇被动过都会变。"""
    latest, n = 0, 0
    for dp, _, fns in os.walk(NOTES_ROOT):
        for fn in fns:
            if not fn.endswith(".md"):
                continue
            n += 1
            try:
                latest = max(latest, os.stat(os.path.join(dp, fn)).st_mtime_ns)
            except OSError:
                pass
    return "%d-%d" % (latest, n)


def notice_take(body=None):
    """取走「开机要告诉你的一件事」。**取走就清掉** —— 这种通知只该看见一次，
    每次刷新都弹一遍就成了骚扰。"""
    msg = store.kv_get("notice", "")
    if msg:
        store.kv_del("notice")
    return {"msg": msg}


def data_stamp(body=None):
    """给前端比对的「数据戳」。

    前端每隔几秒问一次，发现戳变了就在顶上出一条「数据在别处被改过」的提示。
    **刻意不自动重新加载** —— 你可能正在填表，自动刷会把没提交的内容冲掉。
    只回几个短字符串，比把整份数据传过去便宜得多。"""
    # 账单已经住进库里，文件永远不动 —— 再看 Excel 的 mtime 就永远是同一个值，
    # 「别处改过」这条提示再也不会出现。改看数据库的分域版本号。
    # 打卡/物资还在 Excel 里，继续看 mtime，等它们也搬完再统一。
    def _db_stamp(domain, path):
        try:
            return "db%d" % store.rev(domain)
        except Exception:
            return _stamp_file(path)
    return {"bill": _db_stamp("bill", BILL),
            "check": _db_stamp("check", CHECK),
            "stock": _db_stamp("stock", STOCK),
            "notes": _stamp_notes(),
            "semester": SEMESTER}          # 切学期也要让前端发现


def list_fonts(body=None):
    """列出这台机器真的装了哪些字体族。

    为什么在后端做：前端用 canvas 量文字宽度来判断字体存不存在，那个办法
    在无头浏览器里完全不работает（所有字体量出来一样宽），靠不住。
    这里走 GDI 的 EnumFontFamiliesEx —— **纯 ctypes、不读任何文件、不碰 C 盘**，
    只是问系统「你装了哪些字体」。
    """
    if os.name != "nt":
        return {"fonts": [], "note": "只有 Windows 支持枚举字体"}
    try:
        import ctypes
        from ctypes import wintypes
        gdi32, user32 = ctypes.windll.gdi32, ctypes.windll.user32

        class LOGFONTW(ctypes.Structure):
            _fields_ = [("lfHeight", wintypes.LONG), ("lfWidth", wintypes.LONG),
                        ("lfEscapement", wintypes.LONG), ("lfOrientation", wintypes.LONG),
                        ("lfWeight", wintypes.LONG), ("lfItalic", ctypes.c_byte),
                        ("lfUnderline", ctypes.c_byte), ("lfStrikeOut", ctypes.c_byte),
                        ("lfCharSet", ctypes.c_byte), ("lfOutPrecision", ctypes.c_byte),
                        ("lfClipPrecision", ctypes.c_byte), ("lfQuality", ctypes.c_byte),
                        ("lfPitchAndFamily", ctypes.c_byte),
                        ("lfFaceName", ctypes.c_wchar * 32)]

        class ENUMLOGFONTEXW(ctypes.Structure):
            _fields_ = [("elfLogFont", LOGFONTW),
                        ("elfFullName", ctypes.c_wchar * 64),
                        ("elfStyle", ctypes.c_wchar * 32),
                        ("elfScript", ctypes.c_wchar * 32)]

        found = []
        hdc = user32.GetDC(0)
        if not hdc:
            return {"fonts": [], "note": "拿不到设备上下文"}
        try:
            lf = LOGFONTW()
            lf.lfCharSet = 1                    # DEFAULT_CHARSET：中英文都要
            lf.lfFaceName = ""
            PROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.POINTER(ENUMLOGFONTEXW),
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.LPARAM)

            def cb(lpelfe, _tm, _type, _lp):
                try:
                    found.append(lpelfe.contents.elfLogFont.lfFaceName)
                except Exception:
                    pass
                return 1                     # 返回 1 = 继续枚举

            gdi32.EnumFontFamiliesExW(hdc, ctypes.byref(lf), PROC(cb), 0, 0)
        finally:
            user32.ReleaseDC(0, hdc)
        names = sorted({n for n in found if n and not n.startswith("@")})
        return {"fonts": names, "count": len(names)}
    except Exception as e:
        log_error("list_fonts", e)
        return {"fonts": [], "note": "枚举失败：%s" % e}


def _db_name(stamp):
    """备份文件名：小煦拾简_20260916.db"""
    return "%s_%s.db" % (os.path.splitext(os.path.basename(DATA_DB))[0], stamp)


def auto_backup_db():
    """每天第一次写数据之前，给数据库留一份快照。

    ⚠ 以前这个钩子挂在 save_atomic 上（写 Excel 之前先备份）。
    数据搬进 SQLite 之后写操作根本不落 Excel，那个钩子**再也不会被触发** ——
    自动备份就这么悄没声地停了。现在挂在写接口的入口上。
    备份失败绝不能挡住正常保存，所以整个函数吞掉异常。"""
    try:
        root = backup_root()
        os.makedirs(root, exist_ok=True)
        dst = os.path.join(root, _db_name(date.today().strftime("%Y%m%d")))
        if os.path.exists(dst):          # 今天已经备过，直接返回（每天只备一次）
            return
        store.snapshot(dst)
        keep = backup_keep()
        olds = sorted(f for f in os.listdir(root)
                      if f.endswith(".db") and not f.startswith("restore前_"))
        for f in olds[:-keep]:           # 名字带日期，字符串排序就是时间排序
            try:
                os.remove(os.path.join(root, f))
            except OSError:
                pass
    except Exception:
        pass                      # 备份是保险，不是主流程


def backup_list():
    """列出所有备份，最新的在前。

    会同时列出「当前备份目录」和「默认的 _自动备份」—— 改过备份路径之后，
    老备份还在老地方，只列新目录的话用户会以为备份全没了。
    也会同时列出 .db（新）和 .xlsx（搬库之前的旧备份，留着有用）。"""
    out, seen = [], set()
    for root in backup_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for f in names:
            if f in seen:
                continue
            is_db = f.endswith(".db")
            is_xlsx = f.endswith(".xlsx")
            if not (is_db or is_xlsx):
                continue
            full = os.path.join(root, f)
            try:
                st = os.stat(full)
            except OSError:
                continue
            seen.add(f)
            if is_db:
                target, manual = "全部数据（数据库）", "_" in f[:-3]
            else:
                hit = _backup_target_of(f.replace("restore前_", "", 1))
                target = hit[0] if hit else "?"
                manual = "_" in f[:-5].split("_", 1)[-1]
            out.append({"file": f, "target": target, "size": st.st_size,
                        "dir": root, "kind": "db" if is_db else "xlsx",
                        "elsewhere": os.path.normcase(os.path.abspath(root))
                                     != os.path.normcase(os.path.abspath(backup_root())),
                        "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "manual": manual,
                        "prerestore": f.startswith("restore前_")})
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def _backup_path(name):
    """把界面传来的文件名解析成真实路径。**防路径穿越**：只接受纯文件名，
    且必须落在已知的备份目录里。找不到就返回 None。"""
    if not name or name != os.path.basename(name) or ".." in name or os.path.isabs(name):
        return None
    for root in backup_roots():
        full = os.path.join(root, name)
        if os.path.isfile(full):
            return full
    return None


def backup_now(body=None):
    """手动备份一份，名字带时分秒（区别于每日自动备份）"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = backup_root()
    try:
        os.makedirs(root, exist_ok=True)
        dst = os.path.join(root, _db_name(stamp))
        store.snapshot(dst)
    except OSError as e:
        return False, "备份失败：%s" % e
    return True, "已备份一份（%s）" % os.path.basename(dst)


def backup_restore(body):
    """从备份恢复。恢复前会先把当前状态另存一份，否则这个操作不可逆。"""
    name = str(body.get("file") or "")
    src = _backup_path(name)            # 里面已经做了路径穿越校验
    if not src:
        return False, "找不到这个备份文件（文件名不合法或不在备份目录里）"
    is_db = name.endswith(".db")
    label = "全部数据" if is_db else None
    if not is_db:
        hit = _backup_target_of(name.replace("restore前_", "", 1))
        if not hit:
            return False, "这个备份认不出属于哪个数据文件，为安全起见不恢复"
        label = hit[0]
    with _write_lock:
        # ① 先把当前状态存一份 —— 恢复是破坏性的，必须留退路
        pre = None
        try:
            os.makedirs(backup_root(), exist_ok=True)
            pre = os.path.join(backup_root(), "restore前_%s" %
                               _db_name(datetime.now().strftime("%Y%m%d_%H%M%S")))
            store.snapshot(pre)
        except Exception as e:
            return False, "恢复前的安全备份失败，已中止：%s" % e
        # ② 灌回去
        try:
            if is_db:
                store.restore_from(src)
            else:
                # 旧格式的 Excel 备份：搬库之前的东西，没法直接灌回数据库，
                # 但可以放回原位，用户想看旧账还能打开
                hit = _backup_target_of(name.replace("restore前_", "", 1))
                shutil.copy2(src, hit[2])
        except PermissionError:
            return False, "%s 正被占用，请先关闭再恢复" % label
        except Exception as e:
            log_error("backup_restore", e)
            return False, "恢复失败：%s" % e
    drop_cache(BILL)
    drop_cache(CHECK)
    drop_cache(STOCK)
    return True, "已用 %s 恢复「%s」（当前状态已另存为 %s）" % (name, label, os.path.basename(pre))




# ================================================================
# 回收站：删除可撤销
# ================================================================
# 核心思路：**不另写一套「恢复」逻辑**，而是存「重建它需要什么」，
# 恢复时重放对应的新增函数（bill_add / tail_add / todo_add / write_note）。
# 那几条路径已经被自测跑了无数遍，比自己写恢复逻辑安全得多。
#
# 一条删除 = 一个 JSON 文件，文件名带时间戳，按名字排序天然就是时间序。
# 删除时**先写回收站再删**：写失败就中止删除 —— 跟本系统其他地方一个口径，
# 要么都成、要么都不做。
RECYCLE_DIR = os.path.join(DATA_ROOT, "_回收站")
RECYCLE_KEEP = 300          # 最多留几条
RECYCLE_DAYS = 90           # 最多留几天（先到为准）

# 能从回收站恢复的「新增」接口。真正的函数定义在下面，
# 所以在文件末尾（HTTP 之前）才绑定进来。
RECYCLE_ADD = {}


def _recycle_put(kind, label, api, payload):
    """写一条回收站记录。抛 OSError 表示没写成，调用方要中止删除。"""
    os.makedirs(RECYCLE_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = os.path.join(RECYCLE_DIR, "%s_%s.json" % (stamp, kind))
    n = 1
    while os.path.exists(p):                      # 同一秒删两条会撞名
        p = os.path.join(RECYCLE_DIR, "%s_%s_%d.json" % (stamp, kind, n))
        n += 1
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "kind": kind, "kind_cn": RECYCLE_CN.get(kind, kind),
                   "label": label, "api": api, "payload": payload},
                  f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    _recycle_prune()
    return os.path.basename(p)


RECYCLE_CN = {"bill": "账单流水", "tail": "周边尾款",
              "todo": "待办", "note": "日记"}


def _recycle_prune():
    """先按天数清，再按条数清。清理失败不影响主流程。"""
    try:
        names = sorted(n for n in os.listdir(RECYCLE_DIR) if n.endswith(".json"))
        now = time.time()
        for n in names:
            p = os.path.join(RECYCLE_DIR, n)
            try:
                if now - os.path.getmtime(p) > RECYCLE_DAYS * 86400:
                    os.remove(p)
            except OSError:
                pass
        names = sorted(n for n in os.listdir(RECYCLE_DIR) if n.endswith(".json"))
        for n in names[:-RECYCLE_KEEP] if len(names) > RECYCLE_KEEP else []:
            try:
                os.remove(os.path.join(RECYCLE_DIR, n))
            except OSError:
                pass
    except OSError:
        pass


def _row_payload(ws, r, fields):
    """按 {字段名: 列号} 把一行读成 dict。
    日期要转成 'YYYY-MM-DD' 字符串 —— JSON 存不了 datetime 对象。"""
    out = {}
    for k, c in fields.items():
        v = ws.cell(r, c).value
        if isinstance(v, (datetime, date)):
            v = dstr(v)
        out[k] = v
    return out


BILL_COLS = {"date": 1, "cat": 3, "note": 4, "inc": 5, "exp": 6,
             "pay": 7, "grp": 9, "stat": 10}
TAIL_COLS = {"name": 1, "cat": 2, "dep": 3, "tail": 4, "pdate": 5,
             "stat": 6, "note": 7}
TODO_COLS = {"stat": 1, "item": 2, "cat": 3, "due": 4, "pri": 5, "note": 7}


def _bill_label(t):
    amt = _f(t.get("exp")) or _f(t.get("inc"))
    return "%s %s ¥%.2f%s" % (str(t.get("date") or "")[5:], t.get("cat") or "", amt,
                              (" " + str(t["note"])) if t.get("note") else "")


def _tail_label(t):
    return "%s ¥%s（%s）" % (t.get("name") or "", _f(t.get("tail")), t.get("stat") or "待付")


def _todo_label(t):
    return "%s（%s/%s）" % (t.get("item") or "", t.get("cat") or "-", t.get("pri") or "-")


def recycle_list(body=None):
    if not os.path.isdir(RECYCLE_DIR):
        return {"items": [], "keep": RECYCLE_KEEP, "days": RECYCLE_DAYS}
    items = []
    for n in sorted(os.listdir(RECYCLE_DIR), reverse=True):
        if not n.endswith(".json"):
            continue
        p = os.path.join(RECYCLE_DIR, n)
        try:
            rec = json.load(open(p, encoding="utf-8"))
            st = os.stat(p)
        except (OSError, ValueError):
            continue
        items.append({"file": n, "time": rec.get("time") or "",
                      "kind_cn": rec.get("kind_cn") or "",
                      "label": rec.get("label") or "",
                      "size": st.st_size})
    return {"items": items, "keep": RECYCLE_KEEP, "days": RECYCLE_DAYS}


def recycle_restore(body):
    """恢复一条。重放对应的新增接口，成功后把回收站那条删掉。"""
    fn = str(body.get("file") or "")
    if not fn or fn != os.path.basename(fn) or not fn.endswith(".json"):
        return False, "文件名不合法"
    p = os.path.join(RECYCLE_DIR, fn)
    if not os.path.isfile(p):
        return False, "这条记录已经不在了（可能被清理过）"
    try:
        rec = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError) as e:
        return False, "记录读不出来：%s" % e
    api = str(rec.get("api") or "")
    payload = rec.get("payload") or {}

    if api == "note/write":
        kind, name = payload.get("type"), str(payload.get("name") or "")
        if not notes.valid_name(kind, name):
            return False, "记录里的名称不合法"
        if notes.read_raw(kind, name) is not None:   # 只问「文件在不在」，不解密
            return False, "「%s」现在已经有了，没动它（免得覆盖你后来写的）" % name
        notes.write_note(kind, name, payload.get("content") or "")
        _note_backup()
        os.remove(p)
        return True, "已恢复 %s %s" % (name, notes.KIND_CN.get(kind, ""))

    f = RECYCLE_ADD.get(api)
    if not f:
        return False, "不认识这条记录的恢复方式：%s" % api
    try:
        res = f(payload)
    except PermissionError:
        return False, "文件正被 Excel/WPS 打开，请先关闭再恢复"
    except Exception as e:
        return False, "恢复失败：%s" % e
    ok, msg = res if isinstance(res, tuple) else (True, res)   # 有的返回 str，有的返回 (ok, msg)
    if not ok:
        return False, "恢复失败：%s" % msg
    os.remove(p)
    return True, "已恢复（%s）" % msg


def recycle_purge(body):
    """彻底删掉回收站里的一条"""
    fn = str(body.get("file") or "")
    if not fn or fn != os.path.basename(fn) or not fn.endswith(".json"):
        return False, "文件名不合法"
    p = os.path.join(RECYCLE_DIR, fn)
    if not os.path.isfile(p):
        return False, "这条记录已经不在了"
    os.remove(p)
    return True, "已彻底删除"


def recycle_clear(body=None):
    n = 0
    if os.path.isdir(RECYCLE_DIR):
        for f in os.listdir(RECYCLE_DIR):
            if f.endswith(".json"):
                try:
                    os.remove(os.path.join(RECYCLE_DIR, f))
                    n += 1
                except OSError:
                    pass
    return True, "已清空回收站（%d 条）" % n


# ================================================================
# 应用设置（外观 / 行为 / 数据 / 隐私 / 高级 都读这一份）
# ================================================================
# 存在 _配置\settings.json。为什么不塞进 Excel：这些是「程序怎么表现」，
# 不是「用户的数据」，混在一起会污染那三个表，也不好做默认值合并。
APP_VERSION = "2.5.1"      # 2.5.1：跳过 2.5.0（用户指定）。内容 = 2.4.9
                           #       + 竖排里英文也竖排（删掉"按词横躺"那层）
                           #       + 总览卡片排齐（flex 列 + 152px）
                           # 2.4.8：牛马时钟「填了日薪也不出现」的死锁
                           #       + 竖排数字正立（长单词仍横躺）
                           #       + **自带瘦金体**（12MB，MIT 可再分发）+ 静态子目录白名单
                           #       + 删掉界面/文档里「纯本地/不上传」的说法
                           # 2.4.7：修 6 处 prompt —— Electron 16+ 移除了 prompt，
                           #       打包版里那些按钮**点了完全没反应**（浏览器里却正常）
                           #       + 物资表分页（10 条 + 加载更多）
                           #       + 日记/随笔正文竖排（古籍样式，表格保持横排）
                           #       + 补写过去的日记（随手记旁边加日期）
                           #       + 待办筛选（类别/优先级/状态/关键词）
                           #       + 支出环比（自然月 + 上月同期，涨 20% 才报）
                           #       + 学期汇总口径写在界面上 + 备份目录提示不再写死
                           # 2.4.6：修「切换学期自锁」（点一下就卡死）+ 新建学期丢类别
                           #       + 缺 value 静默删格；界面文案统一改成数据库口径
                           # 2.4.4：宽表格不再溢出卡片（.card 加 overflow-x:auto，19 张表一起修）
                           # 2.4.3：删掉照片上那圈白光晕（实测只值 0.22，代价是肉眼可见的毛边）
                           # 2.4.2：随笔页补上布局（类名写了样式没写）+ 「写一篇/新对话」改线性勾勒
                           # 2.4.1：回忆书对话落盘 + 分会话 / 牛马时钟等级制 + 桌面小时钟窗口
                           # 2.4.0：**找不到数据时不再默默新建空库** —— 改成问一次（可以回答的框）
                           # 2.3.9：修右上角那三个窗口按钮（浅色主题下白压白，完全看不见）
                           # 2.3.8：全屏遮罩默认关掉（不再往照片上蒙一层）
                           #        + 照片上的字加宽光晕 + 卡片默认全不透明
                           # 2.3.7：**去掉毛玻璃**（「雾蒙蒙」的真正根源，修了三次）
                           #        + color-scheme 深色（滚动条/滑块白了五个版本）
                           #        + 收入口径统一 + 图表色板重做 + 表单控件统一
                           # 2.3.6：配色系统重做（OKLCH 12 级色阶）+ 换数据目录带迁移
                           #        + 日记模板 / 随笔摘抄 / 插图 / 导出
                           #        + 打卡连续天数与热力图 + 账单订阅日历
                           #        + AI 省钱（输入框补全那一处占了 76%）
APP_SETTINGS = os.path.join(CONF_DIR, "settings.json")

# 自定义背景图。**存在 _配置 下，不进数据库也不进附件目录** ——
# 它是一张装饰图，不是要长期留档的数据，备份数据库时没必要捎上它。
BG_DIR = os.path.join(CONF_DIR, "背景")
BG_STEM = "背景"
BG_MAX_BYTES = 3 * 1024 * 1024      # 前端已经缩到 1600px 了，超过这个数是异常


def bg_path(name=None):
    """背景图的真实路径。name 空则从设置里取。

    ⚠ **扩展名要跟内容对得上**。以前不管存进去的是 PNG 还是 WebP，
    都一律叫「背景.jpg」，于是 /bg 按 .jpg 发出 image/jpeg 头 ——
    内容是 PNG 却自称 JPEG。浏览器大多靠嗅探能猜对，但这是在赌。"""
    if not name:
        try:
            name = str(settings_load().get("bg_image") or "")
        except Exception:
            name = ""
    name = os.path.basename(name or "")
    if not name:
        return ""
    return os.path.join(BG_DIR, name)

SETTINGS_DEFAULTS = {
    # 外观
    "theme": "auto",              # light | dark | auto
    "palette": "米黄",             # 米黄 | 青瓷 | 墨色
    "font": "",                   # 空 = 用主题自带字体
    "font_size": 14,
    # 日记/随笔**竖排正文**用的字体（2.5.1 加）。
    # ⚠ 跟上面那个 `font` 是两件事：`font` 是**整个界面**的字体，
    #   这个是**只看日记/随笔的竖排那一侧** —— 编辑框仍然是等宽字体（写字要清楚）。
    # 值：shoujin=瘦金体 / mashan=马善政行书 / ""=系统书法体回退链。
    # ⚠ **必须登记在这里**：settings_load 会把不在 SETTINGS_DEFAULTS 里的键丢掉
    #   （`notes_salt` 没登记，导致过「加密笔记全部打不开」）。
    "diary_font": "shoujin",
    "animations": True,
    # 背景图。bg_image 只存文件名（真实文件在 _配置\背景\背景.jpg），
    # 存文件名而不是布尔值：以后想放多张、想换格式都不用改设置结构。
    "bg_image": "",
    # 背景图的「这是哪一版」标记（图片文件的改动时间）。
    # ⚠ **必须在这里登记**：settings_load 会把不在 SETTINGS_DEFAULTS 里的键丢掉，
    #   不登记的话每次读设置它都没了，版本号永远是空 —— 缓存问题原样回来。
    "bg_rev": "",
    # 资金 / 账户类型（微信、支付宝、校园卡…）。空 = 用出厂那五个。
    # ⚠ 必须登记，不然 settings_load 会把它丢掉。
    "pays": [],
    # 全屏遮罩浓度 %：深色下是压暗照片，浅色下是给照片垫一层底。
    # 35 → 20 → 10 → **0**（2.3.8）。
    # ⚠ 用户 2026-09-18 定的：「不要在全屏蒙一层图层，只改卡片的背景色」。
    #   这层东西从 2.3.5 起就是「雾蒙蒙」的头号嫌疑人，前两版一直在**调薄**，
    #   其实根子在于**它本来就不该存在** —— 它是一层蒙在所有东西前面的膜，
    #   再怎么薄也是一层膜。现在默认不加，滑块留着（0~90），
    #   照片实在太花、字看不清时用户自己拖。
    "bg_dim": 0,
    # ---- 2.3.6 新增 ----
    # ⚠ 这几行**必须登记**：settings_load() 会把不在这个表里的键整个丢掉，
    #   而且是静默丢掉 —— 表现成「设置存了但下次开机又变回去」。
    #   （notes_salt 没登记过一次，结果加密笔记全部打不开。）
    "bg_mode": "image",           # image | solid | none（壁纸三模式）
    "bg_fill": "cover",           # cover | contain | center（只有 image 模式用得上）
    "bg_solid": "",               # 纯色模式的颜色；空 = 用主题底色
    "prompt_daily": "",           # 空 = 用代码里那份（见 prompt_override）
    "prompt_weekly": "",
    "prompt_monthly": "",
    "prompt_memory": "",
    "mem_search_limit": 20,       # 回忆书：一次搜索最多几条
    "mem_snippet_chars": 420,     # 搜索片段长度
    "mem_read_chars": 6000,       # 单篇读取上限
    "mem_total_chars": 40000,     # 一次工具调用的总预算
    "mem_max_turns": 8,           # 一轮问答最多查几次
    "clock_wage": 0,              # 牛马时钟：日薪（0 = 不显示这块）
    "clock_hours": 8,             # 每天工作几小时
    # ---- 2.4.1 ----
    # 几点上班。⚠ 必须有这个 —— 原来的算法是「从今天 0 点算到现在」，
    # 于是早上 7 点打开就显示「已经赚了 7 小时的工资」。
    "clock_start": "09:00",
    "clock_widget": False,        # 桌面那个小的牛马时钟窗口开不开
    "hotkey": "",                 # 全局快捷键（比如 CommandOrControl+Alt+X）；空 = 不注册
    "budget_carry": False,        # 预算结转：上个月没花完的，加到下个月
    "bg_blur": 0,                 # 模糊半径 px：照片太花时用它能救回来
    # 卡片透出多少照片 %：0 = **完全不透明**（2.3.8 起的默认值）。
    # 调大让卡片变成半透明，后面的照片以一层淡影的形式透出来。
    # ⚠ 别在这里写「配上毛玻璃模糊」—— 毛玻璃 2.3.7 已经删掉了，
    #   它是「雾蒙蒙」的真正来源（见 static/style.css 里那段注释）。
    "bg_glass": 0,
    # 行为
    "autostart": False,
    "default_tab": "over",
    "bill_form": {"clear_after_save": True, "enter_to_save": True, "autofocus": True},
    # 数据
    "backup_dir": "",             # 空 = 数据目录下的 _自动备份
    "backup_keep": 7,
    "note_tone": "natural",       # brief | natural | rich
    "call_me": "",                # AI 对用户的称呼，空 = 用「你」
    # AI 的个人基本情况。用户自己写的几行背景（作息习惯、身体状况、专业、
    # 这阵子在忙什么…），**每次分析都会原样带进提示词**，好让 AI 的建议
    # 贴着他的实际情况来，而不是给一套放之四海皆准的废话。
    "personal": "",
    # 分析时要不要顺带参考最近的日报。默认关：日记是最私密的东西，
    # 该由用户自己决定它要不要参与分析，不该默认就喂出去。
    "ai_use_notes": False,
    "overview_cards": [],         # 空 = 全显示；否则只显示列出的
    "overview_order": [],         # 六张卡的完整排列；空 = 出厂顺序（2.3.3）
    "quick_items": [],            # 总览页快速打卡按钮显示哪些；空 = 全显示（2.3.3）
    "quick_order": [],            # 那些按钮的完整排列（2.3.3）
    "check_items": [],            # 只存改过的打卡项 [{col,name,on}]，其余用出厂值
    # 隐私
    "password_hash": "",          # PBKDF2，格式 salt$iter$hash
    "encrypt_notes": False,
    # 笔记加密专用盐。⚠ **必须在这里登记**：settings_load 会把不认识键丢掉，
    # 不登记的话每次读设置都当它不存在，于是每次解锁都新生成一张盐 ——
    # 密钥跟着变，已经加密的笔记就再也解不开了（这个坑踩过一次）。
    "notes_salt": "",
    "error_log": True,
}


def settings_load():
    """读设置。缺的字段用默认值补齐，所以以后加新设置不用写迁移"""
    raw = _load_json(APP_SETTINGS, {}) or {}
    out = copy.deepcopy(SETTINGS_DEFAULTS)
    for k, v in raw.items():
        if k not in out:
            continue                      # 不认识的就丢掉，别让脏数据留下来
        if isinstance(out[k], dict) and isinstance(v, dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def settings_get(body=None):
    """给前端的设置。**绝不能把 password_hash 发出去** —— 虽然是哈希，
    但拿到就能离线爆破，等于把锁的图纸给了人。只回一个「有没有设」。"""
    cfg = settings_load()
    has_pw = bool(str(cfg.get("password_hash") or "").strip())
    cfg.pop("password_hash", None)
    cfg["has_password"] = has_pw
    cfg["crypto"] = note_crypto_state()      # 只读状态，前端据此决定开关能不能点
    return cfg


def settings_save(body):
    """**只更新传来的字段**，没传的保持原样。

    这条很关键：设置页分了好几个区，各区各自保存。要是这里整体覆盖，
    「外观」页一保存就会把「隐私」页的设置清空。
    """
    body = body or {}
    cur = settings_load()
    touched = []
    for k, v in body.items():
        if k not in SETTINGS_DEFAULTS:
            continue
        if isinstance(SETTINGS_DEFAULTS[k], dict) and isinstance(v, dict):
            cur[k].update(v)
        else:
            cur[k] = v
        touched.append(k)
    _save_json(APP_SETTINGS, cur)
    warn = _settings_side_effects(cur, touched)
    return True, "设置已保存" + ("（%s）" % warn if warn else "")


def _settings_side_effects(cfg, touched):
    """有些设置不只是存起来，还要真的生效。返回一句提醒（没有就返回空串）"""
    notes_msgs = []
    if "autostart" in touched:
        ok, msg = _apply_autostart(cfg.get("autostart"))
        if not ok:
            notes_msgs.append(msg)
    if "backup_dir" in touched:
        d = str(cfg.get("backup_dir") or "").strip()
        if d:
            try:
                os.makedirs(d, exist_ok=True)
                t = os.path.join(d, ".write_test")
                open(t, "w").close()
                os.remove(t)
            except OSError as e:
                notes_msgs.append("备份目录不可写：%s" % e)
    if "password_hash" in touched:
        _auth_lock_all()                   # 改了密码就让所有已解锁的会话失效
    if "encrypt_notes" in touched:
        want = bool(cfg.get("encrypt_notes"))
        why = ""
        if want and not notes.crypto_available():
            why = "缺少加密库，没能开启"
        elif want and not str(cfg.get("password_hash") or "").strip():
            why = "要先设访问密码（密钥由它派生），没能开启"
        elif want and not notes.key_set():
            why = "请重新打开程序、输一次密码解锁后再开"
        else:
            ok, msg = _notes_convert(want)
            why = msg if ok else ("没成功：%s" % msg)
        if want and why and not notes.key_set():
            # 任何一步没成就别把开关留在「开」的位置 —— 那会让人以为已经加密了
            cfg["encrypt_notes"] = False
            _save_json(APP_SETTINGS, cfg)
        notes_msgs.append(why)
    return "；".join([m for m in notes_msgs if m])


# ---------- 开机自启（写 HKCU 的 Run 项，跟 Electron 的 setLoginItemSettings 是同一处）----------
AUTOSTART_NAME = "小煦拾简"


def _launcher_path():
    """要自启的是**外壳 exe**，不是后端 server.exe。
    Electron 启动后端时会用 STATS_LAUNCHER 把外壳路径传进来。"""
    p = os.environ.get("STATS_LAUNCHER")
    if p and os.path.isfile(p):
        return p
    if getattr(sys, "frozen", False):
        # 兜底：后端在 <app>\resources\ 下，外壳在上一层
        up = os.path.dirname(BASE)
        for fn in os.listdir(up) if os.path.isdir(up) else []:
            if fn.lower().endswith(".exe") and fn.lower() != "server.exe":
                return os.path.join(up, fn)
    return None


def _apply_autostart(on):
    try:
        import winreg
    except ImportError:
        return False, "只有 Windows 支持开机自启"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
    except OSError as e:
        return False, "打不开注册表启动项：%s" % e
    try:
        if on:
            exe = _launcher_path()
            if not exe:
                return False, "找不到主程序路径（源码模式下不支持自启）"
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, '"%s"' % exe)
            return True, "已设为开机自启"
        try:
            winreg.DeleteValue(key, AUTOSTART_NAME)
        except FileNotFoundError:
            pass
        return True, "已取消开机自启"
    except OSError as e:
        return False, "写注册表失败：%s" % e
    finally:
        winreg.CloseKey(key)


def autostart_state():
    """读注册表看现在到底是不是自启状态（用户可能在别处改过）"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_READ)
        try:
            v, _ = winreg.QueryValueEx(key, AUTOSTART_NAME)
            return True, v
        except FileNotFoundError:
            return False, ""
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False, ""


# ---------- 访问密码（防君子不防小人）----------
# 必须说清楚：数据是明文躺在硬盘上的，这个锁只挡「别人顺手点开你的程序」，
# 挡不住拿到你电脑的人。真正的保护是 BitLocker + 系统登录密码。
_auth_lock = threading.Lock()
_auth_token = [None]          # 当前有效的会话令牌；None = 未设密码或已锁定


def _hash_password(pw, salt=None, iters=200000):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), iters)
    return "%s$%d$%s" % (salt, iters, h.hex())


def _verify_password(pw, stored):
    try:
        salt, iters, want = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"),
                                  bytes.fromhex(salt), int(iters)).hex()
        return hmac.compare_digest(got, want)
    except (ValueError, AttributeError):
        return False


def _auth_lock_all():
    with _auth_lock:
        _auth_token[0] = None
    notes.clear_key()              # 锁上就把笔记密钥一起忘掉，别留在内存里


def auth_state():
    """前端启动时问：要不要弹锁屏？我手里这个令牌还有效吗？"""
    cfg = settings_load()
    need = bool(str(cfg.get("password_hash") or "").strip())
    with _auth_lock:
        unlocked = (not need) or (_auth_token[0] is not None)
    return {"need_password": need, "unlocked": unlocked}


def auth_unlock(body):
    cfg = settings_load()
    stored = str(cfg.get("password_hash") or "").strip()
    if not stored:
        return True, "没设密码", {"token": ""}
    pw = str((body or {}).get("password") or "")
    if not _verify_password(pw, stored):
        time.sleep(0.4)                    # 稍微拖一下，纯暴力试密码会很难受
        return False, "密码不对"
    tok = secrets.token_hex(24)
    with _auth_lock:
        _auth_token[0] = tok
    _note_unlock(pw, cfg)                  # 把笔记密钥装进内存
    extra = ""
    if cfg.get("encrypt_notes") and not notes.key_set():
        extra = "（笔记加密开着，但这次没装上密钥，笔记会读不出来）"
    elif cfg.get("encrypt_notes"):
        # 后台扫一遍：备份目录里不该还躺着明文（开加密之前攒下的那些）
        threading.Thread(target=note_backup_sweep, daemon=True).start()
    return True, "已解锁" + extra, {"token": tok}


def auth_set(body):
    """设 / 改 / 清 密码。改密码要验旧的。

    ⚠ 笔记加密开着的时候，改密码**必须把所有笔记用新密钥重新加密一遍** ——
    密钥是从密码派生的，只改 password_hash 会让所有笔记永远解不开。
    """
    body = body or {}
    cfg = settings_load()
    stored = str(cfg.get("password_hash") or "").strip()
    old = str(body.get("old") or "")
    if stored and not _verify_password(old, stored):
        return False, "原密码不对"
    new = str(body.get("new") or "")
    if len(new) < 4:
        return False, "新密码至少 4 位"
    rekeyed = ""
    if cfg.get("encrypt_notes"):
        if not stored:
            return False, "笔记加密开着但没有密码，状态异常；请先在设置里关掉笔记加密"
        ok, msg = _notes_rekey(old, new, cfg)
        if not ok:
            return False, "换密钥失败，密码没改：%s" % msg
        rekeyed = "，%s" % msg
    cfg = settings_load()                  # _notes_rekey 可能改过 settings，重新读
    cfg["password_hash"] = _hash_password(new)
    _save_json(APP_SETTINGS, cfg)
    _auth_lock_all()
    # _auth_lock_all 刚把密钥清了。这里用新密码重新装上 —— 否则紧接着点「开启
    # 笔记加密」会因为拿不到密钥而失败。
    notes.set_key(*_note_key_of(new, cfg))
    return True, "密码已设置，下次打开需要输入" + rekeyed


def auth_clear(body):
    cfg = settings_load()
    stored = str(cfg.get("password_hash") or "").strip()
    old = str((body or {}).get("old") or "")
    if stored and not _verify_password(old, stored):
        return False, "原密码不对"
    if cfg.get("encrypt_notes"):
        # 密码一清，密钥就再也派生不出来了 —— 必须先把笔记解密回明文，
        # 否则用户下次打开会看到一 folder 永远打不开的乱码。
        if not _note_unlock(old, cfg):
            return False, "要先用原密码解开笔记才能取消密码；请重启程序、用原密码解锁后重试"
        ok, msg = _notes_convert(False)
        if not ok:
            return False, "解密笔记失败，密码没取消：%s" % msg
    cfg = settings_load()
    cfg["password_hash"] = ""
    cfg["encrypt_notes"] = False
    _save_json(APP_SETTINGS, cfg)
    _auth_lock_all()
    return True, "已取消密码"


# ---------- 笔记加密的密钥管理 ----------
def _note_salt(cfg=None, make=False):
    """笔记加密用的盐。它跟 password_hash 里的盐是两码事（那个只验密码）。
    存在设置里、同时嵌在每个加密文件里 —— 设置丢了还能靠文件和密码救回来。"""
    cfg = cfg or settings_load()
    s = str(cfg.get("notes_salt") or "").strip()
    if s:
        return s
    if not make:
        return ""
    s = secrets.token_hex(16)
    cfg["notes_salt"] = s
    _save_json(APP_SETTINGS, cfg)
    return s


def _note_key_of(password, cfg=None):
    """返回 (key, salt_bytes)"""
    cfg = cfg or settings_load()
    salt = bytes.fromhex(_note_salt(cfg, make=True))
    return notes.derive_key(password, salt), salt


def _note_unlock(password, cfg=None):
    """解锁时就把笔记密钥装进内存。装上了返回 True。

    **这里不能判断 encrypt_notes** —— 那会死锁：要开加密得先有密钥，
    而密钥只在「已经开着加密」的时候才派生，于是一辈子也开不了。
    代价是每次解锁多算一次 PBKDF2（约 0.1 秒），可以接受。
    """
    cfg = cfg or settings_load()
    try:
        notes.set_key(*_note_key_of(password, cfg))
        return True
    except Exception as e:
        log_error("_note_unlock", e)
        return False


def _note_backup_files():
    """_自动备份\\笔记_* 里的那些副本。

    **开加密时必须连它们一起转**：备份是每天复制一份笔记得到的，
    你在开加密之前已经存在的那些副本里，装的是**明文**。
    只加密 笔记\\ 而不管备份，等于前门上了锁、后门还开着 ——
    而且这个后门很隐蔽，没人会想起来去看 _自动备份。
    """
    out = []
    for root in backup_roots():
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            d = os.path.join(root, name)
            if not name.startswith("笔记_") or not os.path.isdir(d):
                continue
            for dp, _, fns in os.walk(d):
                for fn in fns:
                    if fn.endswith(".md"):
                        out.append(os.path.join(dp, fn))
    return out


def _conv_one(p, on):
    """转一个文件。返回 (ok, 错误消息)；已经是对的状态就返回 (True, "")。"""
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        return False, "读不了 %s：%s" % (os.path.basename(p), e)
    enc = notes.is_encrypted(raw)
    if on and enc or (not on and not enc):
        return True, ""
    try:
        text = notes.encrypt_text(raw) if on else notes.decrypt_text(raw)
    except notes.NoteLocked as e:
        return False, "《%s》%s" % (os.path.basename(p), e)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, p)
    except OSError as e:
        return False, "写不了 %s：%s" % (os.path.basename(p), e)
    return True, ""


def note_backup_sweep():
    """加密开着的时候，备份目录里不该还躺着明文 —— 每次解锁后顺手扫一遍。

    为什么需要它：开关那一瞬间的转换只能管到「以后」，
    而用户可能在开加密之前就已经攒了好几天的备份。这个扫尾保证
    「只要加密是开的，磁盘上就不会有明文的笔记副本」，不管它是哪来的。
    """
    if not notes.key_set():
        return 0
    n = 0
    for p in _note_backup_files():
        try:
            with open(p, "r", encoding="utf-8") as f:
                if notes.is_encrypted(f.read()):
                    continue
        except OSError:
            continue
        ok, err = _conv_one(p, True)
        if ok:
            n += 1
        else:
            log_error("note_backup_sweep", Exception(err))
    return n


def _notes_convert(on):
    """把所有笔记整体加密 / 解密。

    **先全部转完再逐个落盘**：中途有任何一篇失败就一篇都不写，
    不会留下「一半加密一半明文」这种最难收拾的状态。
    """
    if on and not notes.crypto_available():
        return False, "缺少加密库（cryptography），没法开启笔记加密"
    if on and not notes.key_set():
        return False, "还没解锁，拿不到密钥"
    # 活的笔记 + 备份里的副本，一起转。只转前者的话，_自动备份 里
    # 开加密之前攒下的那些明文副本会原封不动地留着（等于白加密）。
    files = [p for _k, _n, p in _note_files()] + _note_backup_files()
    plan = []
    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            return False, "读不了《%s》：%s" % (os.path.basename(p), e)
        enc = notes.is_encrypted(raw)
        if on and not enc:
            plan.append((p, notes.encrypt_text(raw)))
        elif (not on) and enc:
            try:
                plan.append((p, notes.decrypt_text(raw)))
            except notes.NoteLocked as e:
                return False, "《%s》%s" % (os.path.basename(p), e)
    for p, text in plan:
        tmp = p + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            os.replace(tmp, p)
        except OSError as e:
            return False, "写不了 %s：%s" % (os.path.basename(p), e)
    n_backup = sum(1 for p, _t in plan if os.sep + "笔记_" in p)
    tail = "，含备份里的 %d 篇" % n_backup if n_backup else ""
    return True, "%s了 %d 篇笔记%s" % ("加密" if on else "解密", len(plan), tail)


def _notes_rekey(old_pw, new_pw, cfg):
    """换密码时重新加密全部笔记：先用旧密钥全部解密到内存，再换新盐+新密钥写回。
    新盐是故意换的 —— 换密码不换盐，等于给爆破的人省了一半事。"""
    if not _note_unlock(old_pw, cfg):
        return False, "原密码解不开笔记"
    plain = []
    # 备份里的副本也要换密钥 —— 不换的话它们会变成「用旧密钥加密、谁也打不开」，
    # 不至于泄密，但等于把你唯一的退路悄悄废掉了
    for p in [x[2] for x in _note_files()] + _note_backup_files():
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = f.read()
            if not notes.is_encrypted(raw):
                continue                      # 备份里要是还有明文，交给扫尾去处理
            plain.append((p, notes.decrypt_text(raw)))
        except notes.NoteLocked as e:
            return False, "《%s》%s" % (os.path.basename(p), e)
        except OSError as e:
            return False, "读不了《%s》：%s" % (os.path.basename(p), e)
    cfg = settings_load()
    cfg["notes_salt"] = secrets.token_hex(16)      # 换盐
    _save_json(APP_SETTINGS, cfg)
    notes.set_key(*_note_key_of(new_pw, cfg))
    for p, text in plain:
        tmp = p + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(notes.encrypt_text(text))
            os.replace(tmp, p)
        except OSError as e:
            return False, "写不了 %s：%s" % (os.path.basename(p), e)
    return True, "已用新密码重新加密 %d 篇笔记" % len(plain)


def _note_files():
    """全部 .md 笔记：(类型, 名字, 路径)"""
    out = []
    for kind in notes.KINDS:
        d = notes.kind_dir(kind, create=False)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".md") and notes.valid_name(kind, fn[:-3]):
                out.append((kind, fn[:-3], os.path.join(d, fn)))
    return out


def note_crypto_state():
    """给设置页看的状态：能不能加密、开没开、现在有没有密钥"""
    cfg = settings_load()
    return {"available": notes.crypto_available(),
            "enabled": bool(cfg.get("encrypt_notes")),
            "has_password": bool(str(cfg.get("password_hash") or "").strip()),
            "unlocked": notes.key_set()}


def auth_check(token):
    """每个请求调一次：没设密码、或令牌对得上，就放行"""
    cfg = settings_load()
    if not str(cfg.get("password_hash") or "").strip():
        return True
    with _auth_lock:
        cur = _auth_token[0]
    return bool(cur) and hmac.compare_digest(str(token or ""), cur)


# ---------- 本地错误日志 ----------
ERROR_LOG = os.path.join(CONF_DIR, "错误日志.txt")


def log_error(where, exc):
    """只写本地文件，不上传任何地方。设置里可以关掉。"""
    try:
        if not settings_load().get("error_log", True):
            return
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write("%s  [%s] %s: %s\n" % (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                where, type(exc).__name__, exc))
        # 太大就砍掉前一半，别让它无限长
        if os.path.getsize(ERROR_LOG) > 512 * 1024:
            lines = open(ERROR_LOG, encoding="utf-8").read().splitlines()
            with open(ERROR_LOG, "w", encoding="utf-8") as f:
                f.write("\n".join(lines[len(lines) // 2:]) + "\n")
    except Exception:
        pass                               # 记日志失败绝不能再抛异常


def error_log_read(body=None):
    try:
        if not os.path.isfile(ERROR_LOG):
            return {"text": "", "size": 0}
        txt = open(ERROR_LOG, encoding="utf-8", errors="replace").read()
        return {"text": txt[-20000:], "size": os.path.getsize(ERROR_LOG)}
    except OSError as e:
        return {"text": "读不出来：%s" % e, "size": 0}


def error_log_clear(body=None):
    try:
        if os.path.isfile(ERROR_LOG):
            os.remove(ERROR_LOG)
    except OSError:
        pass
    return True, "错误日志已清空"


# ---------- 关于 / 调试 / 缓存 ----------
def _dir_size(path):
    n = sz = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                sz += os.path.getsize(os.path.join(root, f)); n += 1
            except OSError:
                pass
    return n, sz


def app_about(body=None):
    """关于页：版本、构建时间、数据在哪、占多大。不做「检查更新」——
    这套系统没有发布渠道也没有更新服务器，弹个报错的按钮不如不放。"""
    exe = _launcher_path()
    if exe:
        stamp = exe                      # 打包后：外壳 exe 的修改时间 ≈ 构建时间
    else:
        stamp = os.path.join(BASE, "server.py")   # 源码模式：别拿 python.exe 的安装时间糊弄
    try:
        built = datetime.fromtimestamp(os.path.getmtime(stamp)).strftime("%Y-%m-%d %H:%M")
    except OSError:
        built = "—"
    files = []
    for label, p in (("每日打卡表", CHECK), ("物资清单", STOCK), ("账单", BILL)):
        try:
            files.append({"label": label, "size": os.path.getsize(p)})
        except OSError:
            files.append({"label": label, "size": 0})
    try:
        n_notes, sz_notes = _dir_size(NOTES_ROOT)
    except OSError:
        n_notes, sz_notes = 0, 0
    return {"version": APP_VERSION, "built": built, "exe": exe,
            "data_root": DATA_ROOT, "conf_dir": CONF_DIR,
            "notes": {"count": n_notes, "size": sz_notes},
            "files": files,
            "python": sys.version.split()[0],
            "frozen": bool(getattr(sys, "frozen", False))}


def debug_info(body=None):
    """调试面板：出问题时能一眼看到系统现在是什么状态"""
    cfg = settings_load()
    auto_on, auto_val = autostart_state()
    info = {
        "版本": APP_VERSION,
        "打包运行": bool(getattr(sys, "frozen", False)),
        "数据目录": DATA_ROOT,
        "配置目录": CONF_DIR,
        "程序目录": BASE,
        "Python": sys.version.split()[0],
        "端口": PORT,
        "开机自启": ("开 → %s" % auto_val) if auto_on else "关",
        "缓存条目": len(_cache),
        "缓存的内容": sorted(os.path.basename(k) for k in _cache.keys()),
        "笔记加密": cfg.get("encrypt_notes"),
        "笔记密钥已装载": notes.key_set(),
        "加密库可用": notes.crypto_available(),
        "已设密码": bool(str(cfg.get("password_hash") or "").strip()),
        "错误日志": ERROR_LOG if os.path.isfile(ERROR_LOG) else "（没有）",
        "写锁被占用": _write_lock.locked(),
    }
    return info


def cache_clear(body=None):
    """清内存缓存（下次读会重新载入）。顺带把 Python 的垃圾回收跑一遍。"""
    n = len(_cache)
    with _cache_lock:
        _cache.clear()
    import gc
    gc.collect()
    return True, "已清掉 %d 个缓存（下次读会重新载入）" % n


def save_atomic(wb, path):
    """临时文件 + 原子替换；被 Excel 占用时抛 PermissionError"""
    auto_backup(path)
    wb.calculation.fullCalcOnLoad = True
    tmp = path + ".tmp"
    try:
        wb.save(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# ---------------- 快路径：直改 xlsx 内部 XML（单格写入，毫秒级） ----------------
# 整表重写（openpyxl 往返）是打卡点击卡顿的元凶；这里只对某个 <c> 做字符串手术。
# 字符串存储约定：文件里有没有 sharedStrings.xml 就用哪种写法（openpyxl 写的是
# inlineStr；物资清单有 sharedStrings 就跟随它）。失败抛异常 → 调用方回退 openpyxl。
_XML_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def _xesc(s):
    return "".join(_XML_ESC.get(c, c) for c in str(s))


def _col_idx(col):
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def _sheet_xml_name(wbxml, rels, sheet):
    rid = None
    for m in re.finditer(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="(rId\d+)"', wbxml):
        if m.group(1) == sheet:
            rid = m.group(2)
            break
    if not rid:
        raise ValueError("找不到工作表 %s" % sheet)
    rel = re.search(r'<Relationship[^>]*Id="%s"[^>]*' % rid, rels).group(0)
    tgt = re.search(r'Target="([^"]+)"', rel).group(1).lstrip("/")
    return tgt if tgt.startswith("xl/") else "xl/" + tgt


def _serial(dt):
    """datetime/date → Excel 日期序列号"""
    return (dt.date() - date(1899, 12, 30)).days if isinstance(dt, datetime) else dt


class _SharedStrings:
    """sharedStrings.xml 的读入 + 追加（去重返回索引）"""

    def __init__(self, z):
        self.items, self.index, self.changed = [], {}, False
        self.exists = "xl/sharedStrings.xml" in z.namelist()
        if self.exists:
            xml = z.read("xl/sharedStrings.xml").decode("utf-8")
            for m in re.finditer(r"<si>(.*?)</si>", xml, re.S):
                t = re.search(r"<t[^>]*>(.*?)</t>", m.group(1), re.S)
                text = t.group(1) if t else ""
                self.items.append(text)
                self.index.setdefault(text, len(self.items) - 1)

    def add(self, text):
        if text in self.index:
            return self.index[text]
        idx = len(self.items)
        self.items.append(text)
        self.index[text] = idx
        self.changed = True
        return idx

    def xml(self):
        body = "".join("<si><t>%s</t></si>" % _xesc(t) for t in self.items)
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
                ' count="%d" uniqueCount="%d">%s</sst>' % (len(self.items), len(self.items), body))


def _cell_xml(col, row, value, style, shared):
    """构造 <c> 元素；value 为 None/'' → None（表示删掉该格）"""
    if value is None or value == "":
        return None
    ref = "%s%d" % (col, row)
    s = ' s="%s"' % style if style else ""
    if isinstance(value, bool):
        return '<c r="%s"%s t="b"><v>%d</v></c>' % (ref, s, int(value))
    if isinstance(value, (int, float)):
        return '<c r="%s"%s><v>%s</v></c>' % (ref, s, repr(value))
    if isinstance(value, (datetime, date)):
        return '<c r="%s"%s><v>%d</v></c>' % (ref, s, _serial(value))
    if shared and shared.exists:      # 文件本来就有 sharedStrings 才用 t="s"
        return '<c r="%s"%s t="s"><v>%d</v></c>' % (ref, s, shared.add(str(value)))
    return '<c r="%s"%s t="inlineStr"><is><t>%s</t></is></c>' % (ref, s, _xesc(value))


def _patch_cell(xml, col, row, value, shared):
    ref = "%s%d" % (col, row)
    m = re.search(r'<c r="%s"(?: [^>]*?)?(?:/>|>.*?</c>)' % ref, xml, re.S)
    if m:                                     # 该格已存在 → 就地替换（或删除）
        style = (re.search(r's="(\d+)"', m.group(0)) or [None, None])[1]
        new = _cell_xml(col, row, value, style, shared)
        return xml.replace(m.group(0), new or "", 1)
    # 新格：样式取同列其他行的第一个 s
    style = None
    for mm in re.finditer(r'<c r="%s\d+"[^>]*s="(\d+)"' % col, xml):
        style = mm.group(1)
        break
    new = _cell_xml(col, row, value, style, shared)
    if new is None:
        return xml
    rm = re.search(r'(<row r="%d"[^>]*>)(.*?)(</row>)' % row, xml, re.S)
    if rm:                                    # 行已存在 → 按列序插入
        body = rm.group(2)
        pos, prev_end, placed = 0, 0, False
        for cm in re.finditer(r'<c r="([A-Z]+)\d+"[^>]*?(?:/>|>.*?</c>)', body, re.S):
            if _col_idx(cm.group(1)) < _col_idx(col):
                prev_end = cm.end()
            else:
                pos, placed = prev_end, True
                break
        if not placed:
            pos = len(body)
        return xml[:rm.start(2)] + body[:pos] + new + body[pos:] + xml[rm.end(2):]
    # 行不存在 → 插到下一个行号更大的 <row> 之前
    nr = None
    for rm2 in re.finditer(r'<row r="(\d+)"[^>]*>', xml):
        if int(rm2.group(1)) > row:
            nr = rm2
            break
    newrow = '<row r="%d">%s</row>' % (row, new)
    if nr:
        return xml[:nr.start()] + newrow + xml[nr.start():]
    return xml.replace("</sheetData>", newrow + "</sheetData>", 1)


def fast_cell_write(path, sheet, row, col, value):
    """直改 xlsx 内部 XML，只动一个单元格。异常上抛（调用方回退 openpyxl）。"""
    auto_backup(path)
    tmp = path + ".fsw"
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        wbxml = z.read("xl/workbook.xml").decode("utf-8")
        rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        sheetfile = _sheet_xml_name(wbxml, rels, sheet)
        xml = z.read(sheetfile).decode("utf-8")
        shared = _SharedStrings(z)
        newxml = _patch_cell(xml, col, row, value, shared)
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
            for n in names:
                if n == sheetfile:
                    zo.writestr(n, newxml.encode("utf-8"))
                elif n == "xl/sharedStrings.xml" and shared.changed:
                    zo.writestr(n, shared.xml().encode("utf-8"))
                else:
                    zo.writestr(n, z.read(n))
    os.replace(tmp, path)


def fast_set(path, sheet, row, col, value):
    """快路径单格写入；失败返回 False（调用方用 openpyxl 兜底）"""
    try:
        fast_cell_write(path, sheet, row, col, value)
        return True
    except Exception:
        return False


def _cell_has_value(path, sheet, col, row):
    """只读 XML 判断某格是否有内容（快路径写入前的行存在性校验）"""
    with zipfile.ZipFile(path) as z:
        wbxml = z.read("xl/workbook.xml").decode("utf-8")
        rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        xml = z.read(_sheet_xml_name(wbxml, rels, sheet)).decode("utf-8")
    m = re.search(r'<c r="%s%d"[^>]*?(?:/>|>(.*?)</c>)' % (col, row), xml, re.S)
    return bool(m and m.group(1) and m.group(1).strip())


# ================================================================
# ① 账单
# ================================================================
EXP_CATS = ["餐饮", "零食", "饮料", "服饰", "日用品", "购物", "交通", "通讯",
            "学习", "娱乐", "游戏", "周边", "医疗", "生活", "人情", "理财", "其他"]
INC_CATS = ["生活费", "兼职", "奖学金", "其他收入", "理财"]
# 资金/账户类型（微信、支付宝、校园卡…）。**用户可以自己增删改** ——
# 原来写死五个，有人的钱在别的卡里、或者用云闪付，就没法记。
# 这个常量只当兜底：真正用哪个看设置里的 pays。
PAYS = ["微信", "支付宝", "现金", "农业银行卡", "农商银行卡"]


def pays_of():
    """当前该用哪些资金类型：设置里有就用设置的，没有就退回出厂那五个。"""
    try:
        v = settings_load().get("pays")
        if isinstance(v, list) and v:
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        pass
    return list(PAYS)


def _account_list(conf, inc_map, exp_map):
    """配置里的账户 + 数据里真正用过的账户，按配置顺序排前面。"""
    seen = [a for a in conf]
    for m in (inc_map, exp_map):
        for k in m:
            k = (k or "").strip()
            if k and k not in seen:
                seen.append(k)
    # 空账户（一分钱没动过、也不在配置里的）不列
    return [a for a in seen if a in conf or inc_map.get(a) or exp_map.get(a)]
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ================================================================
# ① 账单
# ================================================================
# 换到 SQLite 之后这一节整体重写，但**对外的返回结构一字未动** ——
# 前端、AI 摘要、回忆书的 read_stats 全都按 load_bill 的老结构写的，
# 结构一变就得改一大片，不值当。唯一变的是 records 里那个 "row"：
# 以前是 Excel 行号（插一行就全乱），现在是数据库 id。名字还叫 row，
# 前端拿回来当 id 用，两边都不知情。

def _sem():
    """当前学期。以前是一整个文件路径，现在只是个字段值。"""
    return SEMESTER


def _cats_of(sem=None):
    """(支出类别, 收入类别)，按排序。对外那个 cats_get() 返回的是带上限、
    带保留字的完整 dict，两个别混。"""
    sem = sem or _sem()
    rows = store.q("SELECT kind,name FROM cat WHERE sem=? ORDER BY kind, ord", (sem,))
    return ([r["name"] for r in rows if r["kind"] == "exp"],
            [r["name"] for r in rows if r["kind"] == "inc"])


# 下面两个只给「导出成 Excel」用 —— 数据库是家了，Excel 降级成导出格式。
# 留着是因为导出时要按原来那张表的列序一格一格写回去。
def write_bill_row(ws, r, rec):
    """按记录 dict 写入第 r 行（含 B/H 静态星期月份）"""
    d = to_date(rec.get("date"))
    ws.cell(r, 1).value = d
    ws.cell(r, 2).value = WEEKDAYS[d.weekday()] if d else ""
    ws.cell(r, 3).value = rec.get("cat", "")
    ws.cell(r, 4).value = rec.get("note", "")
    ws.cell(r, 5).value = to_num(rec.get("inc")) or 0
    ws.cell(r, 6).value = to_num(rec.get("exp")) or 0
    ws.cell(r, 7).value = rec.get("pay", "")
    ws.cell(r, 8).value = "%d月" % d.month if d else ""
    ws.cell(r, 9).value = rec.get("grp", "")
    ws.cell(r, 10).value = rec.get("stat", "")


def tail_write(ws, r, t):
    ws.cell(r, 1).value = t.get("name", "")
    ws.cell(r, 2).value = t.get("cat", "")
    ws.cell(r, 3).value = to_num(t.get("dep"))
    ws.cell(r, 4).value = to_num(t.get("tail"))
    ws.cell(r, 5).value = to_date(t.get("pdate"))
    ws.cell(r, 6).value = t.get("stat", "待付")
    ws.cell(r, 7).value = t.get("note", "")


def load_bill(path=None, sem=None):
    """⚠ path 必须排在第一个：cached() 是 `loader(path)` 这么调的，
    签名写成 (sem, path) 的话，那个文件路径会被当成学期名收下，
    然后一声不吭地查出 0 条 —— 页面全空、还不报错。
    path 本身已经没用了，留着纯粹为了对上这个调用约定。"""
    sem = sem or _sem()
    records = []
    for r in store.q("SELECT id,date,cat,note,inc,exp,pay,grp,stat FROM bill"
                     " WHERE sem=? ORDER BY date, id", (sem,)):
        records.append({
            "row": r["id"], "date": r["date"] or "", "cat": r["cat"] or "",
            "note": r["note"] or "", "inc": float(r["inc"] or 0),
            "exp": float(r["exp"] or 0), "pay": r["pay"] or "",
            "grp": (r["grp"] or "").strip(), "stat": (r["stat"] or "").strip()})

    stats = [r for r in records if r["stat"] != "退回"]

    exp_cat, inc_cat, day_exp = {}, {}, {}
    month_inc, month_exp = {}, {}
    month_inc_real = {}          # 剔除「结余」（期初余额）后的真实收入，用于预估月结余
    opening_total = 0.0
    pay_inc, pay_exp = {}, {}
    groups = {"wait": 0, "done": 0, "back": 0, "rows": []}
    for r in stats:
        cat = r["cat"]
        if r["inc"] > 0:
            key = r["date"][:7]
            # 「结余」= **期初余额**（见使用说明的记账约定）：开学时手里本来就有的钱。
            #
            # 它算不算「收入」，2.3.1 和 2.3.7 给出了**相反**的答案 —— 不是谁改错了，
            # 是这件事本来就有两个都对的答案，取决于你在回答哪个问题：
            #   问「我这学期挣了多少」→ 不算（2.3.1 的答案）
            #   问「我这学期进账多少 / 和 Excel 对得上吗」→ 算（2.3.7，用户定的）
            # 最后按后者办：**账面上对得上**比**口径上纯粹**更重要，
            # 因为对不上的时候用户的第一反应是「数据丢了吧」。
            #
            # 代价是饼图里一块几乎占满（实测 2826.93 / 3427.44 = 82%）。
            # 所以下面必须让「结余」**独立成一类**，不能并进它原本的 cat ——
            # 那四笔的 cat 都是「其他收入」，并进去的话饼图就是一块 99% 的绿。
            #
            # 唯一还继续剔除它的地方是 month_inc_real（→ cashflow 的每月结余预估）：
            # 「我每月大概能剩多少」如果拿本金当收入，算出来是个永远达不到的数，
            # 那笔钱会一路撑着后面六个月的预估，比"少算一次收入"危险得多。
            is_open = str(r["note"]).strip() == "结余"
            if is_open:
                opening_total += r["inc"]
            else:
                month_inc_real[key] = month_inc_real.get(key, 0) + r["inc"]
            ic = "结余" if is_open else cat
            inc_cat[ic] = inc_cat.get(ic, 0) + r["inc"]
            month_inc[key] = month_inc.get(key, 0) + r["inc"]
            pay_inc[r["pay"]] = pay_inc.get(r["pay"], 0) + r["inc"]
        if r["exp"] > 0:
            exp_cat[cat] = exp_cat.get(cat, 0) + r["exp"]
            key = r["date"][:7]
            month_exp[key] = month_exp.get(key, 0) + r["exp"]
            pay_exp[r["pay"]] = pay_exp.get(r["pay"], 0) + r["exp"]
            day_exp[r["date"]] = day_exp.get(r["date"], 0) + r["exp"]
    # ⚠ 逐日金额**必须在这里收成 2 位小数**。
    #   上面是浮点累加（0.1 + 0.2 那种），同一天记三笔就能累出
    #   114.22999999999999 —— 账单日历的格子里直接把原值打印出来，
    #   屏幕上就是一串 33.75000000000001。前端 money() 有 toFixed 挡着，
    #   但凡是不走 money() 的地方（日历格子、图表 tooltip 的原始值）全会漏。
    #   在**源头**收掉，比在每个显示点各修一遍可靠。
    day_exp = {k: round(v, 2) for k, v in day_exp.items()}
    # 团购单独扫一遍 records（不能用 stats：stats 已剔除「退回」，
    # 会导致退回的团购行不显示、已退回合计恒为 0）
    for r in records:
        if r["grp"] == "是":
            groups["rows"].append({"row": r["row"], "name": r["note"] or r["cat"] or "团购",
                                   "date": r["date"], "amt": r["exp"],
                                   "stat": r["stat"] or "待核销"})
    for g in groups["rows"]:
        groups[{"待核销": "wait", "核销": "done", "退回": "back"}.get(g["stat"], "wait")] += g["amt"]

    # 周边尾款
    tails = []
    for t in store.q("SELECT id,name,cat,dep,tail,pdate,stat,note FROM tail"
                     " WHERE sem=? ORDER BY id", (sem,)):
        pd = to_date(t["pdate"]) if t["pdate"] else None
        days = (pd.date() - date.today()).days if pd else None
        tails.append({"row": t["id"], "name": t["name"], "cat": t["cat"] or "",
                      "dep": float(t["dep"] or 0), "tail": float(t["tail"] or 0),
                      "pdate": t["pdate"] or "", "days": days,
                      "stat": (t["stat"] or "").strip() or "待付",
                      "note": t["note"] or ""})
    pending = sum(t["tail"] for t in tails if t["stat"] == "待付")

    # 预算
    budget = {r["month"]: float(r["amount"] or 0) for r in
              store.q("SELECT month,amount FROM budget WHERE sem=?", (sem,))}
    cats_exp, cats_inc = _cats_of(sem)

    # ⚠ 2.3.7 起 inc_cat 里**已经含**「结余」这一类了，所以这里不能再 +opening_total。
    #   2.3.1~2.3.6 的写法是 `sum(inc_cat.values()) + opening_total`，
    #   合并口径之后那会把这笔钱算两遍 —— 总收入变成 6254，比 Excel 多出一倍，
    #   而且因为是个"变大"的错误，看起来不像坏了，最难发现。
    total_inc = sum(inc_cat.values())
    total_exp = sum(exp_cat.values())
    balance = total_inc - total_exp
    # 把中间断掉的月份补齐。只有一两个月数据时图上是孤零零两根柱子，
    # 看着像坏了；而且真断了月（比如寒假整月没记），缺口会被悄悄抹平，
    # 柱状图连"这个月是空的"这件事都表达不出来。
    months = sorted(set(list(month_inc) + list(month_exp)))
    _cur = date.today().strftime("%Y-%m")
    if months:
        _a, _b = months[0], max(months[-1], _cur)
        y, m2 = int(_a[:4]), int(_a[5:])
        filled = []
        while "%04d-%02d" % (y, m2) <= _b and len(filled) < 60:
            filled.append("%04d-%02d" % (y, m2))
            m2 += 1
            if m2 > 12:
                y, m2 = y + 1, 1
        months = filled
    return {
        # ⚠ 这里有两个「收入」，必须分清楚，否则用户一定会问「我明明有三千多，
        #   怎么收入只有六百」—— 2.3.1 修的是口径，2.3.7 修的是**没把话说明白**。
        #     earned   本期收入   真正挣到的（不含期初）—— 饼图 / 月柱状图 / AI 都用它
        #     inc      进账总额   期初 ＋ 本期收入 —— **这才是 Excel「收入合计」那一格**，
        #                         用户拿计算器加出来的是这个数
        #   两个都发出去，界面上两个都写清楚名字；只发一个，另一个就永远像丢了钱。
        "kpi": {"inc": round(total_inc, 2), "exp": round(total_exp, 2),
                "bal": round(balance, 2), "pending": round(pending, 2),
                "avail": round(balance - pending, 2),
                "opening": round(opening_total, 2),
                "earned": round(total_inc - opening_total, 2),
                "void": len(records) - len(stats)},
        "exp_cat": {k: round(v, 2) for k, v in sorted(exp_cat.items(), key=lambda x: -x[1])},
        "inc_cat": {k: round(v, 2) for k, v in sorted(inc_cat.items(), key=lambda x: -x[1])},
        # ⚠ ym 是给图表的横轴用的：只写「9月」的话，下学期也有 9 月，
        #   两个 9 月在一张图上就撞了。月份标签必须带年份。
        "months": _months_with_budget(months, month_inc, month_exp, budget),
        "day_exp": day_exp,
        # ⚠ 账户列表 = **配置里的** ∪ **数据里出现过的**。
        #   只按配置列的话，用户删掉一个资金类型，历史上用它的那些钱
        #   就从「账户结余」里凭空消失 —— 账面上少一块，却看不出去哪了。
        #   所以见过的账户一律留着，哪怕已经从配置里删了。
        "accounts": [{"name": a, "inc": round(pay_inc.get(a, 0), 2),
                      "exp": round(pay_exp.get(a, 0), 2),
                      "bal": round(pay_inc.get(a, 0) - pay_exp.get(a, 0), 2)}
                     for a in _account_list(pays_of(), pay_inc, pay_exp)],
        "groups": {"wait": round(groups["wait"], 2), "done": round(groups["done"], 2),
                   "back": round(groups["back"], 2), "rows": groups["rows"]},
        "tails": tails,
        "cashflow": _cashflow(tails, month_inc_real, month_exp, balance, opening_total),
        "cats": {"exp": cats_exp, "inc": cats_inc},
        "records": sorted(records, key=lambda r: r["date"], reverse=True),
    }


# ---- 写 ----
def _bill_fields(body):
    d = to_date(body.get("date"))
    grp = str(body.get("grp") or "")
    stat = str(body.get("stat") or "")
    # 「只有团购才有核销状态」这条**由服务端把住**。
    # 起因：表单里那个下拉是 待核销/核销/退回，第一个默认就被选中，
    # 于是每一笔普通支出都被打上「待核销」，记录列表看着像全是团购。
    # 前端已经加了空选项并置灰，但客户端不该有权力违反这条不变量 ——
    # 换个入口（接口直调、以后新加的界面）就又漏了。
    if grp != "是":
        stat = ""
    return (dstr(d) if d else "", str(body.get("cat") or ""),
            str(body.get("note") or ""), to_num(body.get("inc")) or 0,
            to_num(body.get("exp")) or 0, str(body.get("pay") or ""), grp, stat)


def bill_add(body):
    f = _bill_fields(body)
    with store.tx("bill") as c:
        c.execute("INSERT INTO bill(sem,date,cat,note,inc,exp,pay,grp,stat)"
                  " VALUES(?,?,?,?,?,?,?,?,?)", (_sem(),) + f)
    drop_cache(BILL)
    return "已记下：%s %s%.2f 元" % (f[0], "收" if f[3] else "支", f[3] or f[4])


def bill_edit(body):
    rid = int(body["row"])
    f = _bill_fields(body)
    with store.tx("bill") as c:
        cur = c.execute("UPDATE bill SET date=?,cat=?,note=?,inc=?,exp=?,pay=?,"
                        "grp=?,stat=? WHERE id=? AND sem=?",
                        f + (rid, _sem()))
        if not cur.rowcount:
            return False, "找不到这条记录（可能已经被删了）"
    drop_cache(BILL)
    return True, "已更新"


def bill_del(body):
    rid = int(body["row"])
    r = store.q1("SELECT date,cat,note,inc,exp,pay,grp,stat FROM bill"
                 " WHERE id=? AND sem=?", (rid, _sem()))
    if not r:
        return False, "找不到这条记录（可能已经被删了）"
    payload = {"date": r["date"], "cat": r["cat"], "note": r["note"],
               "inc": r["inc"], "exp": r["exp"], "pay": r["pay"],
               "grp": r["grp"], "stat": r["stat"]}
    try:                       # 先记档再删：记档失败就中止，不让删除变成不可逆
        _recycle_put("bill", _bill_label(payload), "bill/add", payload)
    except OSError as e:
        return False, "回收站写入失败，已中止删除：%s" % e
    with store.tx("bill") as c:
        c.execute("DELETE FROM bill WHERE id=? AND sem=?", (rid, _sem()))
    drop_cache(BILL)
    return True, "已删除（可在设置页的回收站恢复）"


def bill_stat(body):
    """只改核销状态 —— 团购看板上直接切换用"""
    rid = int(body.get("row") or 0)
    stat = str(body.get("stat") or "").strip()
    if stat not in ("待核销", "核销", "退回"):
        return False, "核销状态只能是 待核销 / 核销 / 退回"
    with store.tx("bill") as c:
        cur = c.execute("UPDATE bill SET stat=? WHERE id=? AND sem=?",
                        (stat, rid, _sem()))
        if not cur.rowcount:
            return False, "找不到这条记录"
    drop_cache(BILL)
    return True, "核销状态已改为「%s」" % stat


def tail_pay(body):
    """付清尾款：尾款行标已付 + 在账单里记一笔支出。

    以前这两处写在同一个 xlsx 里，靠「一次 save_atomic」当事务；
    现在直接就是一个 SQLite 事务，语义更硬 —— 要么都成，要么都不成。"""
    rid = int(body.get("row") or 0)
    pay = str(body.get("pay") or "微信").strip()
    when = to_date(str(body.get("date") or "")) or datetime.now()
    with store.tx("bill") as c:
        t = c.execute("SELECT name,cat,tail,stat FROM tail WHERE id=? AND sem=?",
                      (rid, _sem())).fetchone()
        if not t:
            return False, "找不到这笔尾款"
        if (t["stat"] or "").strip() == "已付":
            return False, "这一笔已经标过已付了"
        name = t["name"] or "周边尾款"
        amount = _f(t["tail"])
        if body.get("amount") not in (None, ""):       # 允许按实际付款金额覆盖
            amount = _f(body.get("amount"))
        if amount <= 0:
            return False, "这一笔尾款金额是 0，先把金额填上"
        # 记账类别：优先用该尾款行的类别（若它确实是账单类别），否则落「周边」
        cats_exp, _inc = _cats_of(_sem())
        cat = str(t["cat"] or "").strip()
        if cat not in cats_exp:
            cat = "周边" if "周边" in cats_exp else (cats_exp[-1] if cats_exp else "其他")
        c.execute("UPDATE tail SET stat='已付', tail=? WHERE id=? AND sem=?",
                  (amount, rid, _sem()))
        c.execute("INSERT INTO bill(sem,date,cat,note,inc,exp,pay,grp,stat)"
                  " VALUES(?,?,?,?,0,?,?,'','')",
                  (_sem(), dstr(when), cat, "%s 尾款" % name, amount, pay))
    drop_cache(BILL)
    return True, "已付清「%s」%.2f 元，并记了一笔支出" % (name, amount)


def _tail_fields(body):
    d = to_date(body.get("pdate"))
    return (str(body.get("name") or ""), str(body.get("cat") or ""),
            to_num(body.get("dep")) or 0, to_num(body.get("tail")) or 0,
            dstr(d) if d else "", str(body.get("stat") or "待付"),
            str(body.get("note") or ""))


def tail_add(body):
    f = _tail_fields(body)
    with store.tx("bill") as c:
        c.execute("INSERT INTO tail(sem,name,cat,dep,tail,pdate,stat,note)"
                  " VALUES(?,?,?,?,?,?,?,?)", (_sem(),) + f)
    drop_cache(BILL)
    return "已添加尾款「%s」" % f[0]


def tail_edit(body):
    rid = int(body["row"])
    f = _tail_fields(body)
    with store.tx("bill") as c:
        cur = c.execute("UPDATE tail SET name=?,cat=?,dep=?,tail=?,pdate=?,stat=?,"
                        "note=? WHERE id=? AND sem=?", f + (rid, _sem()))
        if not cur.rowcount:
            return False, "找不到这笔尾款"
    drop_cache(BILL)
    return True, "已更新"


def tail_del(body):
    rid = int(body["row"])
    t = store.q1("SELECT name,cat,dep,tail,pdate,stat,note FROM tail"
                 " WHERE id=? AND sem=?", (rid, _sem()))
    if not t:
        return False, "找不到这笔尾款"
    payload = {"name": t["name"], "cat": t["cat"], "dep": t["dep"],
               "tail": t["tail"], "pdate": t["pdate"], "stat": t["stat"],
               "note": t["note"]}
    try:
        _recycle_put("tail", _tail_label(payload), "tail/add", payload)
    except OSError as e:
        return False, "回收站写入失败，已中止删除：%s" % e
    with store.tx("bill") as c:
        c.execute("DELETE FROM tail WHERE id=? AND sem=?", (rid, _sem()))
    drop_cache(BILL)
    return True, "已删除（可在设置页的回收站恢复）"




# ================================================================
# ② 打卡
# ================================================================
CHECK_COLS = {"C", "D", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R",
              "T", "U", "V", "W", "X", "Y", "Z", "AA", "AB", "AC", "AD",
              "AE", "AF", "AG", "AH"}   # 手动输入列（S/AI/AJ 等公式列不在此列）
CHECK_ITEMS = [  # (列, 中文名, 类型)  type: tick 打勾 / time 时间 / num 数字 / sel 下拉 / text 文本
    ("C", "入睡时间", "time"), ("D", "起床时间", "time"),
    ("I", "睡眠质量", "sel1"), ("J", "夜醒次数", "num"), ("K", "睡前手机", "yn"),
    ("L", "小睡(min)", "num"),
    ("M", "记得梦", "sel"), ("N", "梦的类型", "sel"), ("O", "梦的情绪", "sel"),
    ("P", "梦境关键词", "text"),
    ("Q", "喝水1.5L", "tick"), ("R", "记账", "tick"), ("T", "按时吃药", "tick"),
    ("U", "少外卖奶茶", "tick"),
    ("V", "早起不赖床", "tick"), ("W", "吃早饭", "tick"), ("X", "学习/作业推进", "tick"),
    ("Y", "睡前洗漱", "tick"), ("Z", "运动类型", "sel"), ("AA", "运动时长(min)", "num"),
    ("AB", "屏幕时长(h)", "num"), ("AC", "收拾桌面/倒垃圾", "tick"),
    ("AD", "洗衣服/打水", "tick"), ("AE", "跟家人联系", "tick"),
    ("AF", "心情", "sel"), ("AG", "精力", "sel1"), ("AH", "备注", "text"),
]


def _months_with_budget(months, month_inc, month_exp, budget):
    """每个月的收支 + 预算。开了「预算结转」时，把上月结余并进下月的预算。

    ⚠ 结转**只在开关打开时算**，而且是**现算**、不改预算表里的数 ——
      用户关掉开关，看到的就是原本填的那个数；不然「我明明填的 1000，
      怎么变成 1150 了」根本查不出来。
    ⚠ 只结转**正结余**。上个月超支了不倒扣下个月：那会让一个月超支
      连着惩罚后面好几个月，越滚越绝望，不如让它过去。"""
    carry = bool(settings_load().get("budget_carry"))
    out = []
    prev_left = 0
    for m in months:
        label = "%s月" % m[5:].lstrip("0")
        base = budget.get(label)
        eff = base
        if carry and base is not None:
            eff = round(base + max(0, prev_left), 2)
        exp = round(month_exp.get(m, 0), 2)
        out.append({
            "m": label, "ym": m,
            "inc": round(month_inc.get(m, 0), 2),
            "exp": exp,
            # budget 是「本来填的」，eff_budget 是「算上结转实际能花的」
            "budget": base,
            "eff_budget": eff,
            "carry": round(eff - base, 2) if (carry and base is not None) else 0,
        })
        prev_left = (base - exp) if base is not None else 0
    return out


def load_check(path=None):
    """打卡数据。path 只为对上 cached() 的 loader(path) 调用约定，内容不看。

    「有哪些天」不是拿整月算的 —— check_month 里存着每张月表的第一天，
    因为 9 月表是从 12 号开始的（建表那天），拿整月算会凭空多出 11 个空格子。"""
    settings, opts = {}, {}
    for r in store.q("SELECT k,v FROM check_cfg"):
        k = r["k"]
        try:
            val = json.loads(r["v"])
        except Exception:
            val = r["v"]
        if k.startswith("set."):
            settings[k[4:]] = val
        elif k.startswith("opt."):
            opts[k[4:]] = val

    months = []
    for m in store.q("SELECT ym,d0 FROM check_month ORDER BY ym"):
        ym, d0s = m["ym"] or "", m["d0"] or ""
        # ⚠ to_date 返回的是 **datetime**，不是 date。拿它直接跟 date 比大小
        # 会抛「'<=' not supported between datetime.datetime and datetime.date」。
        # 这里一律降到 date，省得后面每处比较都要多想一次。
        d0 = to_date(d0s)
        if not d0:
            continue
        d0 = d0.date()
        last = date(d0.year, d0.month, monthrange(d0.year, d0.month)[1])
        vals = {}
        _items = _all_items()          # 含用户自建的项
        for r in store.q("SELECT date,col,v,s FROM check_val"
                         " WHERE date>=? AND date<=?", (dstr(d0), dstr(last))):
            vals.setdefault(r["date"], {})[r["col"]] = (
                r["v"] if r["v"] is not None else r["s"])
        days = []
        d = d0
        while d <= last:
            ds = dstr(d)
            got = vals.get(ds) or {}
            day = {"day": d.day, "date": ds, "row": 7 + d.day}   # row 保持 8~38 的形状
            for it in _items:
                day[it["col"]] = got.get(it["col"])
            days.append(day)
            d += timedelta(days=1)
        months.append({"name": ym, "ym": ym, "days": days})

    dreams = []
    for r in store.q("SELECT date,type,mood,clarity,content,read FROM dream"
                     " WHERE kind='archive' ORDER BY date DESC"):
        dreams.append({"date": r["date"], "type": r["type"] or "",
                       "mood": r["mood"] or "", "clarity": r["clarity"] or "",
                       "content": r["content"] or "", "read": r["read"] or ""})
    dream_detail = {}
    for r in store.q("SELECT date,seq,type,mood,clarity,content,read FROM dream"
                     " WHERE kind='detail' ORDER BY date, seq"):
        dream_detail.setdefault(r["date"], []).append({
            "date": r["date"], "seq": r["seq"], "type": r["type"] or "",
            "mood": r["mood"] or "", "clarity": r["clarity"] or "",
            "content": r["content"] or "", "read": r["read"] or ""})

    return {"settings": settings, "opts": opts, "months": months,
            "items": check_items(),
            "dreams": dreams, "dream_detail": dream_detail}



CHECK_ITEM_DEFAULTS = {
    "core": [("Q", "喝水1.5L ★"), ("R", "记账 ★"), ("S", "小睡≤30 ★"),
             ("T", "按时吃药 ★"), ("U", "少外卖奶茶 ★")],
    "bonus": [("V", "早起不赖床"), ("W", "吃早饭"), ("X", "学习/作业推进"), ("Y", "睡前洗漱"),
              ("AC", "收拾桌面/倒垃圾"), ("AD", "洗衣服/打水"), ("AE", "跟家人联系")],
}
CHECK_ITEM_GROUP_CN = {"core": "核心打卡（计入完成率）", "bonus": "加分打卡（做了白赚）"}


def _seed_check_items():
    """第一次跑时，把出厂那 28 项写进 check_item 表，并套用用户以前改过的名字/隐藏。

    为什么现在才能做「增删打卡项」：以前打卡数据在 Excel 月表里，
    每一项固定占一列，旁边的公式（完成率、睡眠时长）全是按列号引用的，
    插一列就把它们全带偏了，所以只敢让你改名和隐藏。
    换成 SQLite 的窄表之后，「一项」就是 check_val 里的一组行 ——
    加一项、删一项都不碰任何别的东西。
    """
    if store.one("SELECT COUNT(*) FROM check_item", (), 0):
        return False
    # 用户以前在设置里改过的（只存改过的），套在出厂值上
    saved = {}
    for it in (settings_load().get("check_items") or []):
        if isinstance(it, dict) and it.get("col"):
            saved[str(it["col"]).upper()] = it
    core = {c for c, _n in CHECK_ITEM_DEFAULTS["core"]}
    bonus = {c for c, _n in CHECK_ITEM_DEFAULTS["bonus"]}
    # ⚠ S（小睡≤30）**不在 CHECK_ITEMS 里** —— 它是由「小睡(min)」算出来的，
    # 在 Excel 里是公式列，没有数据列。但它是核心项之一，完成率要算它，
    # 设置里也列着它。所以单独补一条 kind='derived' 的进去：
    # 列表里有它（计数才对得上），但不给它建数据格子。
    all_items = list(CHECK_ITEMS) + [("S", "小睡≤30 ★", "derived")]
    with store.tx("check") as c:
        for i, (col, name, kind) in enumerate(all_items):
            s = saved.get(col) or {}
            grp = "core" if col in core else ("bonus" if col in bonus else "other")
            c.execute("INSERT OR REPLACE INTO check_item"
                      "(col,name,kind,grp,opts,ord,enabled,builtin)"
                      " VALUES(?,?,?,?,'',?,?,1)",
                      (col, str(s.get("name") or "").strip() or name, kind, grp, i,
                       1 if s.get("on", True) is not False else 0))
    return True


def check_items():
    """当前的打卡项定义，按分组给。

    数据在 `check_item` 表里（见 _seed_check_items 的说明）。
    表是空的（还没播种）就退回出厂值，保证任何情况下页面都有东西可渲染。
    """
    rows = store.q("SELECT col,name,kind,grp,opts,ord,enabled,builtin FROM check_item"
                   " ORDER BY ord, col")
    if not rows:
        out = {}
        for grp, defs in CHECK_ITEM_DEFAULTS.items():
            out[grp] = [{"col": c, "name": n, "kind": "tick", "opts": "",
                         "on": True, "builtin": True} for c, n in defs]
        return out
    out = {"core": [], "bonus": [], "other": []}
    for r in rows:
        g = r["grp"] if r["grp"] in out else "other"
        out[g].append({"col": r["col"], "name": r["name"], "kind": r["kind"],
                       "opts": r["opts"] or "", "on": bool(r["enabled"]),
                       "builtin": bool(r["builtin"])})
    return out


def _all_items():
    """所有项（含隐藏的）拍平，给 load_check / check_set 用"""
    it = check_items()
    return [x for g in ("core", "bonus", "other") for x in (it.get(g) or [])]


CK_KINDS = ("tick", "num", "time", "sel", "text", "derived")
# derived = 由别的项算出来的（目前只有 S「小睡≤30」），列表里有它、不能填
CK_GROUPS = ("core", "bonus", "other")


def check_items_save(items):
    """整表保存打卡项定义。

    **整体替换而不是逐条 diff** —— 这张表一共几十行，一次全写简单可靠，
    也不会留下「改了一半」的中间状态。删掉的项，它在 check_val 里的历史
    数据**不动**：万一以后想加回来，记录还在。
    """
    if not isinstance(items, dict):
        return False, "参数不对"
    have = {r["col"] for r in store.q("SELECT col FROM check_item")}
    used, rows, seen = set(), [], 0
    for grp in CK_GROUPS:
        for it in (items.get(grp) or []):
            if not isinstance(it, dict):
                continue
            col = str(it.get("col") or "").strip().upper()
            name = str(it.get("name") or "").strip()[:20]
            kind = str(it.get("kind") or "tick").strip()
            if not name:
                continue
            # ⚠ "derived" 必须在允许列表里 —— 不然 S（小睡≤30）保存一圈回来
            # 就被打成 tick，从「自动算的」变成「可以手填的」，
            # 而这个格子根本没有对应的数据列，填了也存不住。
            if kind not in CK_KINDS:
                kind = "tick"
            # 但**新造的项不许是 derived** —— 那是内置项的专属状态，
            # 客户端说自己是 derived 只是想绕过写入校验而已
            if kind == "derived" and col not in have:
                kind = "tick"
            # 自建项的列号由服务端发，不接受客户端指定 —— 客户端给了也可能是
            # 跟内置项撞车的（比如把新项叫成 "Q"），那会直接覆盖别人的数据
            if not col or col in used or (col not in have and not col.startswith("U")):
                while "U%d" % (seen + 1) in used or "U%d" % (seen + 1) in have:
                    seen += 1
                seen += 1
                col = "U%d" % seen
            used.add(col)
            rows.append((col, name, kind, grp,
                         str(it.get("opts") or "").strip()[:200],
                         len(rows),
                         1 if it.get("on") is not False else 0,
                         1 if (it.get("builtin") or col in have) else 0))
    if not rows:
        # 全空 = 前端点了「还原默认」：清掉重播一次出厂值。
        # 直接报错的话那个按钮就废了 —— 出厂定义在服务端，前端拿不到。
        with store.tx("check") as c:
            c.execute("DELETE FROM check_item")
        _seed_check_items()
        drop_cache(CHECK)
        return True, "已还原成出厂打卡项"
    if len(rows) > 60:
        return False, "打卡项太多了（%d 项），最多 60 项" % len(rows)
    with store.tx("check") as c:
        c.execute("DELETE FROM check_item")
        for r in rows:
            c.execute("INSERT INTO check_item"
                      "(col,name,kind,grp,opts,ord,enabled,builtin)"
                      " VALUES(?,?,?,?,?,?,?,?)", r)
    drop_cache(CHECK)
    return True, "打卡项已保存（共 %d 项）" % len(rows)





MONTH_RE = re.compile(r"^(\d{4})年(\d{2})月$")
MONTH_BACKFILL_MAX = 24          # 一次最多补几个月（两年）


def _ym_of(name):
    """'2026年09月' → (2026, 9)；不合法返回 None"""
    m = MONTH_RE.match(str(name or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _month_key(name):
    return _ym_of(name) or (9999, 0)


def _next_month_name(name):
    m = MONTH_RE.match(name)
    y, mo = int(m.group(1)), int(m.group(2)) + 1
    if mo > 12:
        y, mo = y + 1, 1
    return "%04d年%02d月" % (y, mo)


def _month_seq(last, upto, cap):
    """列出 (last, upto] 之间的月份。格式零填充，所以字符串比较就是时间比较。"""
    out, n = [], _next_month_name(last)
    while n <= upto and len(out) < cap:
        out.append(n)
        n = _next_month_name(n)
    return out


def _day_date(ym, day):
    """这一天在月表范围里吗？月表可能从月中才开始，超出的返回 None。"""
    r = store.q1("SELECT d0 FROM check_month WHERE ym=?", (ym,))
    d0 = to_date(r["d0"]) if r and r["d0"] else None
    if not d0:
        return None
    if day < d0.day or day > monthrange(d0.year, d0.month)[1]:
        return None
    return date(d0.year, d0.month, day)


def _cell_vs(col, val):
    """一个格子的值 → (v, s)。数字型进 v，文本型进 s，回读时 v 优先。
    时间统一成 'HH:MM' 再存，免得 '23:30' 和 0.979 两种写法混在库里。"""
    typ = store.one("SELECT kind FROM check_item WHERE col=?", (col,), "tick")
    if val is None or val == "":
        return None, None
    if typ == "time":
        val = frac_to_time(to_time_fraction(str(val)))
    if isinstance(val, bool):
        return (1.0 if val else 0.0), None
    if isinstance(val, (int, float)):
        return float(val), None
    return None, str(val)


def _put_cell(c, ds, col, val):
    """写一个格子。空值 = 删掉这行（不是存个空字符串）。"""
    v, s = _cell_vs(col, val)
    if v is None and s is None:
        c.execute("DELETE FROM check_val WHERE date=? AND col=?", (ds, col))
    else:
        c.execute("INSERT INTO check_val(date,col,v,s) VALUES(?,?,?,?)"
                  " ON CONFLICT(date,col) DO UPDATE SET v=excluded.v, s=excluded.s",
                  (ds, col, v, s))


def check_set(body):
    name = str(body.get("sheet"))
    try:
        day = int(body.get("day"))
    except (TypeError, ValueError):
        return False, "日期不合法"
    col = str(body.get("col")).upper()
    # 能写哪些格子**以 check_item 表为准** —— 用户自建的项也在里面。
    # 以前查的是写死的 CHECK_COLS，自建项一个都存不进去。
    if not store.one("SELECT COUNT(*) FROM check_item WHERE col=?", (col,), 0):
        return False, "没有「%s」这一项" % col
    if store.one("SELECT kind FROM check_item WHERE col=?", (col,), "") == "derived":
        return False, "「%s」是自动算出来的，不能直接填" % col
    d = _day_date(name, day)
    if not d:
        return False, "%s 没有 %d 号" % (name, day)
    with store.tx("check") as c:
        _put_cell(c, dstr(d), col, body.get("value"))
    drop_cache(CHECK)
    return True, "%s %d号 %s 已保存" % (name, day, col)


def check_ensure(body=None):
    """补齐月表登记。

    **换到 SQLite 之后这个函数瘦了一大圈**：以前它要新建工作表、复制 1520 个
    单元格的样式、滚「统计看板」的最近四个月引用、给梦境档案续年份、补梦境明细表……
    那些全是为了让 Excel 那张表自己算得对。库里「一个月」就是 check_month 里一行，
    正事只剩一件：该有的月份登记上了没有。
    """
    body = body or {}
    want = str(body.get("month") or "").strip()
    backfill = bool(body.get("backfill"))
    base = str(body.get("from") or "").strip()
    have = [r["ym"] for r in store.q("SELECT ym FROM check_month") if r["ym"]]
    cur = want if MONTH_RE.match(want) else \
        "%04d年%02d月" % (date.today().year, date.today().month)
    if not have and not backfill and not base:
        # 一份数据都还没有：先把这个月登记上，等于当年的「建第一张月表」
        todo = [cur]
    elif base and MONTH_RE.match(base):
        todo = _month_seq(base, cur, MONTH_BACKFILL_MAX)
    elif backfill and have:
        todo = _month_seq(sorted(have, key=_month_key)[-1], cur, MONTH_BACKFILL_MAX)
    else:
        todo = [] if cur in have else [cur]
    todo = [m for m in todo if m not in have]
    if not todo and cur not in have:
        todo = [cur]
    if not todo:
        return True, "结构已检查（无变化）"
    with store.tx("check") as c:
        for m in todo:
            y, mo = _ym_of(m)
            # 新建的月份从 1 号排满整月 —— 和当年 create_month_sheet 的行为一致
            c.execute("INSERT OR REPLACE INTO check_month(ym,d0) VALUES(?,?)",
                      (m, "%04d-%02d-01" % (y, mo)))
    drop_cache(CHECK)
    return True, "结构已检查（新增 %d 个月表：%s）" % (len(todo), "、".join(todo))


# 断月回填的进度，前端轮询 check/backfill 就能看到它跑到哪了
_check_fill_state = {"running": False, "total": 0, "done": 0,
                     "created": [], "error": ""}
_check_fill_lock = threading.Lock()
_check_fill_started = [False]


def check_backfill_start():
    """补齐断掉的月表登记。

    以前这个**必须**放后台线程：建一张月表要复制 1520 个单元格的样式，
    补 12 个月要好几秒，而 Electron 是等后端就绪才开窗的，同步跑会让用户
    盯着空屏。现在只是往 check_month 里插几行，几毫秒，直接同步做完。

    顺序仍然要紧：必须在同步的 check_ensure **之前**调用 —— 那一步会先把
    当月登记上，等这边再看，「最后一个月」已经是当月了，缺口就被从上面堵死。
    """
    if _check_fill_started[0]:
        return
    _check_fill_started[0] = True
    try:
        names = sorted([r["ym"] for r in store.q("SELECT ym FROM check_month")
                        if r["ym"]], key=_month_key)
        if not names:
            return
        cur = "%04d年%02d月" % (date.today().year, date.today().month)
        need = [m for m in _month_seq(names[-1], cur, MONTH_BACKFILL_MAX)
                if m not in names]
        if not need:
            return
        with _check_fill_lock:
            _check_fill_state.update({"running": True, "total": len(need),
                                      "done": 0, "created": [], "error": ""})
        with store.tx("check") as c:
            for m in need:
                y, mo = _ym_of(m)
                c.execute("INSERT OR REPLACE INTO check_month(ym,d0) VALUES(?,?)",
                          (m, "%04d-%02d-01" % (y, mo)))
        drop_cache(CHECK)
        with _check_fill_lock:
            _check_fill_state["created"] = list(need)
            _check_fill_state["done"] = len(need)
    except Exception as e:
        with _check_fill_lock:
            _check_fill_state["error"] = str(e)
    finally:
        with _check_fill_lock:
            _check_fill_state["running"] = False


def check_backfill_status(body=None):
    with _check_fill_lock:
        return dict(_check_fill_state)


def dream_save(body):
    """保存某天的梦境：先做没做梦(M)，做了则按次数逐条写入梦境明细，
    同时同步打卡月表的 M/N/O/P 速记列（N/O/P 取第一个梦）"""
    d = to_date(str(body.get("date")))
    if not d:
        return False, "日期无效"
    dreamed = bool(body.get("dreamed"))
    M = body.get("m") or ("模糊记得" if dreamed else "不记得")
    dreams = body.get("dreams") or []        # [{type,mood,clarity,content,read}]
    ym = "%04d年%02d月" % (d.year, d.month)
    ds = dstr(d)
    with store.tx("check") as c:
        # 1) 该日期的明细行先删后写（跟以前 delete_rows 再补的语义一致）
        c.execute("DELETE FROM dream WHERE kind='detail' AND date=?", (ds,))
        if dreamed:
            for i, g in enumerate(dreams, 1):
                c.execute("INSERT INTO dream(kind,date,seq,type,mood,clarity,"
                          "content,read) VALUES('detail',?,?,?,?,?,?,?)",
                          (ds, i, g.get("type", ""), g.get("mood", ""),
                           g.get("clarity", ""), g.get("content", ""),
                           g.get("read", "")))
        # 2) 同步月表速记列。这一天不在月表范围里就跳过（以前是找不到行就算了）
        if _day_date(ym, d.day):
            _put_cell(c, ds, "M", M)
            if dreamed and dreams:
                _put_cell(c, ds, "N", dreams[0].get("type", ""))
                _put_cell(c, ds, "O", dreams[0].get("mood", ""))
                _put_cell(c, ds, "P", "、".join(
                    (g.get("content") or "").strip() for g in dreams)[:50])
            else:
                for col in ("N", "O", "P"):
                    _put_cell(c, ds, col, None)
    drop_cache(CHECK)
    return True, ("已保存 %d 个梦" % len(dreams)) if dreamed else "已记为「没做梦」"




# ================================================================
# ③ 物资
# ================================================================
STOCK_COLS = {   # 各表可写列（公式列 / 统计列不可写）
    "药品":   {"A", "B", "C", "D", "E", "F", "J", "K", "L", "M", "N", "Q", "R"},
    "日用品": {"A", "B", "C", "D", "E", "F", "J", "K", "L", "N", "R"},
    # N = 有效期(直接填)：有些零食包装只印到期日，没有生产日期+保质期
    "零食":   {"A", "B", "C", "D", "H", "I", "J", "K", "M", "N", "Q", "R"},
}
DATE_COLS = {"药品": {"C", "Q"}, "日用品": {"C", "D", "F"}, "零食": {"B", "N", "Q"}}

# 「开封日期」在各表里落在哪一列。日用品原本就有（C），药品和零食是 2.2 新加的，
# 一律放 Q —— 字母不一样不要紧，代码只认这张表。
OPEN_COL = {"药品": "Q", "日用品": "C", "零食": "Q"}
# 「开封后建议用完」的月数。三张表统一放 R。
SHELF_COL = {"药品": "R", "日用品": "R", "零食": "R"}

# 2.2 新加的列。老库里的 stock_header 是搬 Excel 时按表头写进去的，
# 没有这两列 —— 启动时补一次，不然界面上根本没有这两个格子。
NEW_STOCK_COLS = [
    ("药品",   "Q", "开封日期"),
    ("药品",   "R", "开封后建议用完(月)"),
    ("日用品", "R", "开封后建议用完(月)"),
    ("零食",   "Q", "开封日期"),
    ("零食",   "R", "开封后建议用完(月)"),
]


def seed_stock_cols():
    """把 2.2 新加的物资列补进表头。幂等，每次启动都能调。

    **只补表头，不给任何行填值** —— 新列对老数据来说就是空的，
      跟「用户没填」是一回事，状态计算会自然跳过它们。"""
    n = 0
    with store.tx("stock") as c:
        for sheet, col, name in NEW_STOCK_COLS:
            cur = c.execute("INSERT OR IGNORE INTO stock_header(sheet,col,name)"
                            " VALUES(?,?,?)", (sheet, col, name))
            n += cur.rowcount or 0
    if n:
        print("[物资] 补了 %d 个新表头（开封日期 / 开封后建议用完）" % n)
    return n


def _add_months(d, n):
    """日期加 N 个月。**日对齐是特意处理的**：8月31日加一个月应该落到
    9月30日（而不是让 datetime 把 9月31日 顺延成 10月1日）——
    往后顺延会在边上莫名其妙多出一天，对「开封后三个月内用完」这种
    本来就是约数的事来说，宁可少算不能多算。"""
    y, m = d.year, d.month + int(n)
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    day = d.day
    while day > 1:
        try:
            return datetime(y, m, day)
        except ValueError:
            day -= 1
    return datetime(y, m, 1)


def _opened_deadline(sheet, row):
    """开封之后「建议用完」的那一天。没填开封日期或没填月数 → None。

    这条和「包装上的有效期」是**两回事**：眼药水开封一个月就不该用了，
    哪怕瓶子上印着 2028 年到期。哪个先到听哪个，所以取 min。"""
    od = row.get(OPEN_COL.get(sheet, ""))
    m = row.get(SHELF_COL.get(sheet, ""))
    if not isinstance(od, datetime) or m in (None, ""):
        return None
    try:
        m = float(m)
    except (TypeError, ValueError):
        return None
    if m <= 0 or m > 120:            # 离谱的值当没填：多半是手滑打进去的
        return None
    return _add_months(od, m)


def _stock_statuses(sheet, row):
    """在 Python 里复算各表公式列（供网页显示；Excel 内公式原样保留）"""
    today = date.today()
    def days_to(v):
        return (v.date() - today).days if isinstance(v, datetime) else None
    open_dl = _opened_deadline(sheet, row)     # 开封后建议用完的那天，可能没有
    if sheet == "药品":
        exp = row.get("C")
        if open_dl and (not exp or open_dl < exp):
            exp = open_dl
        days = days_to(exp) if exp else None
        if row.get("A") and exp:
            status = "已过期" if days < 0 else ("临期" if days <= 90 else "正常")
        elif row.get("A"):
            status = "长期有效"
        else:
            status = ""
        restock = "需补货" if row.get("F") is not None and (row.get("D") or 0) <= row["F"] else ""
        return status, days, restock
    if sheet == "日用品":
        # 失效日期 = EXP 优先，否则 生产日期 + 保质期(月)
        exp = row.get("F") or row.get("D")
        if row.get("F"):
            fail = row["F"]
        elif row.get("D") and row.get("E"):
            m = row.get("E")
            fail = datetime(row["D"].year + (row["D"].month - 1 + m) // 12,
                            (row["D"].month - 1 + m) % 12 + 1, 1)
        else:
            fail = None
        if open_dl and (not fail or open_dl < fail):
            fail = open_dl
        days = days_to(fail) if fail else None
        if row.get("A") and fail:
            status = "已过期" if days < 0 else ("临期" if days <= 30 else "正常")
        elif row.get("A"):
            status = ""
        else:
            status = ""
        restock = "需补货" if row.get("L") is not None and (row.get("J") or 0) <= row["L"] else ""
        return status, days, restock
    # 零食：N(直接填的有效期) 优先 —— 与日用品「包装到期日EXP」同一套优先级；
    # 没填 N 才回落到 生产日期 + 保质期 + 单位
    fail = row.get("N")
    if not fail:
        prod, shelf, unit = row.get("B"), row.get("C"), row.get("D")
        if prod and shelf:
            n, u = int(shelf), (unit or "月")
            if u == "天":
                fail = prod + timedelta(days=n)
            elif u == "周":
                fail = prod + timedelta(weeks=n)
            else:
                y, m = prod.year, prod.month + n
                fail = datetime(y + (m - 1) // 12, (m - 1) % 12 + 1, prod.day)
        else:
            fail = None
    if open_dl and (not fail or open_dl < fail):
        fail = open_dl
    days = days_to(fail) if fail else None
    if row.get("H") == "已食用":
        status = "已食用"
    elif row.get("A") and fail:
        status = "已过期" if days < 0 else ("临期" if days <= 30 else "正常")
    else:
        status = ""
    restock = "需补货" if row.get("K") is not None and (row.get("I") or 0) <= row["K"] else ""
    return status, days, restock


def load_stock(path=None):
    """物资。path 只为对上 cached() 的 loader(path) 调用约定。"""
    out = {"sheets": {}, "overview": [], "todo": [], "emergency": _em_cells()}
    total = {}
    for name in ("药品", "日用品", "零食"):
        header = {r["col"]: r["name"] for r in
                  store.q("SELECT col,name FROM stock_header WHERE sheet=?", (name,))}
        raw = {}
        for r in store.q("SELECT row_id,col,v,s FROM stock WHERE sheet=?"
                         " ORDER BY row_id", (name,)):
            raw.setdefault(r["row_id"], {})[r["col"]] = (
                r["v"] if r["v"] is not None else r["s"])
        rows = []
        for rid in sorted(raw):
            d = {"row": rid}
            d.update(raw[rid])
            # 日期列得还原成 datetime 再交给 _stock_statuses ——
            # 它内部到处 isinstance(v, datetime) 和 v.date()，
            # 喂字符串进去不会报错，只会**默默算出「长期有效」这类错结论**。
            for col in DATE_COLS.get(name, ()):
                if d.get(col):
                    d[col] = to_date(str(d[col]))
            status, days, restock = _stock_statuses(name, d)
            d["_status"], d["_days"], d["_restock"] = status, days, restock
            _od = _opened_deadline(name, d)
            d["_open_exp"] = _od.strftime("%Y-%m-%d") if _od else ""
            d["_open_days"] = (_od.date() - date.today()).days if _od else None
            rows.append(d)
        out["sheets"][name] = {"header": header, "rows": rows}
        t = {"total": len(rows), "expired": 0, "soon": 0, "normal": 0,
             "long": 0, "restock": 0}
        for r in rows:
            if r["_restock"]:
                t["restock"] += 1
            s = r["_status"]
            if s == "已过期":
                t["expired"] += 1
            elif s == "临期":
                t["soon"] += 1
            elif s in ("正常", "已食用"):
                t["normal"] += 1
            elif s == "长期有效":
                t["long"] += 1
        total[name] = t
    for name in ("药品", "日用品", "零食"):
        out["overview"].append({"cat": name, **total[name]})

    for r in store.q("SELECT id,stat,item,cat,due,pri,note FROM todo ORDER BY ord, id"):
        d = to_date(r["due"])
        days = (d.date() - date.today()).days if d else None
        out["todo"].append({"row": r["id"], "stat": r["stat"] or "",
                            "item": r["item"] or "", "cat": r["cat"] or "",
                            "due": r["due"] or "", "days": days,
                            "pri": r["pri"] or "", "note": r["note"] or ""})
    return out


# 应急信息每节一行放几组「标签/值」。这是**版面**不是数据，
# 所以留在代码里而不是库里 —— 库里只存「有哪些标签、值是什么」。
EM_COLS = {"基本信息": 3, "医疗警示": 1, "常用电话": 3, "就医与其他": 1}


def _em_cells():
    """应急信息 → 老的「一行一串词」形状。

    库里存的是结构化的（标签→值 + 联系人小表），因为老表那一坨是**排版**不是数据，
    拍平成一串字符串就没法编辑了。这里再还原回老形状，纯粹是为了让现有前端
    一行都不用改 —— 等应急信息的新界面做好，这个函数就可以退休。"""
    num = {"基本信息": "一", "医疗警示": "二", "紧急联系人": "三",
           "常用电话": "四", "就医与其他": "五"}
    out = []
    for sec in ("基本信息", "医疗警示", "紧急联系人", "常用电话", "就医与其他"):
        fields = list(store.q("SELECT label,value,ord FROM em_field WHERE sec=?"
                              " ORDER BY ord", (sec,)))
        if sec == "紧急联系人":
            contacts = list(store.q("SELECT name,rel,phone FROM em_contact"
                                    " ORDER BY ord, id"))
            if not fields and not contacts:
                continue                     # 一节都没填就不显示这节
            out.append(["%s、%s" % (num[sec], sec)])
            if contacts:
                out.append(["姓名", "关系", "联系电话"])
                for c in contacts:
                    cells = [c["name"], c["rel"], c["phone"]]
                    if any(cells):
                        out.append(cells)
            for f in fields:                 # 万一这节还挂了普通字段
                out.append([f["label"], f["value"]] if f["value"] else [f["label"]])
            continue
        if not fields:
            continue
        out.append(["%s、%s" % (num[sec], sec)])
        n = EM_COLS.get(sec, 1)              # 这节一行放几组标签值
        for i in range(0, len(fields), n):
            cells = []
            for f in fields[i:i + n]:
                cells.append(f["label"])
                if f["value"]:
                    cells.append(f["value"])
            if cells:
                out.append(cells)
    return out


def emergency_get(body=None):
    """给「应急信息」编辑界面的结构化数据"""
    out = []
    for sec in ("基本信息", "医疗警示", "紧急联系人", "常用电话", "就医与其他"):
        out.append({
            "sec": sec,
            "fields": [{"id": r["id"], "label": r["label"], "value": r["value"]}
                       for r in store.q("SELECT id,label,value FROM em_field"
                                        " WHERE sec=? ORDER BY ord, id", (sec,))],
            "contacts": ([{"id": r["id"], "name": r["name"], "rel": r["rel"],
                           "phone": r["phone"]}
                          for r in store.q("SELECT id,name,rel,phone FROM em_contact"
                                           " ORDER BY ord, id")]
                         if sec == "紧急联系人" else []),
        })
    return {"sections": out}


def emergency_save(body):
    """整块保存应急信息。**整体替换而不是逐条 diff** —— 这张卡统共就
    二三十个格子，一次全写简单可靠，也不会留下「改了一半」的中间状态。"""
    secs = body.get("sections")
    if not isinstance(secs, list):
        return False, "参数不对"
    with store.tx("stock") as c:
        c.execute("DELETE FROM em_field")
        c.execute("DELETE FROM em_contact")
        for s in secs:
            sec = str(s.get("sec") or "").strip()
            if not sec:
                continue
            for i, f in enumerate(s.get("fields") or []):
                label = str(f.get("label") or "").strip()
                if not label:
                    continue
                c.execute("INSERT INTO em_field(sec,label,value,ord) VALUES(?,?,?,?)",
                          (sec, label, str(f.get("value") or "").strip(), i))
            if sec == "紧急联系人":
                for i, p in enumerate(s.get("contacts") or []):
                    if not any(str(p.get(k) or "").strip()
                               for k in ("name", "rel", "phone")):
                        continue
                    c.execute("INSERT INTO em_contact(name,rel,phone,ord)"
                              " VALUES(?,?,?,?)",
                              (str(p.get("name") or "").strip(),
                               str(p.get("rel") or "").strip(),
                               str(p.get("phone") or "").strip(), i))
    drop_cache(STOCK)
    return True, "应急信息已保存"


# 哪些列是数字。**必须一列一列点名**，不能像以前那样「D/E/F/J/K/L 都当数字」——
# 药品的 E 是「单位」（颗/片）、J 是「备注」，一律 to_num 转过去，
# 备注里写「一日3次」就被当成数字了。
STOCK_NUM_COLS = {"药品": {"D", "F", "R"}, "日用品": {"E", "J", "L", "R"},
                  "零食": {"C", "I", "K", "R"}}


def _stock_vs(sheet, col, val):
    """一格物资的值 → (v, s)。日期统一成 'YYYY-MM-DD' 存字符串。"""
    if val is None or str(val).strip() == "":
        return None, None
    if col in DATE_COLS.get(sheet, ()):
        d = to_date(str(val))
        return None, (dstr(d) if d else "")
    if col in STOCK_NUM_COLS.get(sheet, ()):
        n = to_num(val)
        # to_num 解析不出来时**会把原字符串返回**，不是 None ——
        # 直接 float(n) 会当场抛异常。所以判类型，别判 None。
        if isinstance(n, (int, float)) and not isinstance(n, bool):
            return float(n), None
    return None, str(val)


def stock_set(body):
    sheet = str(body.get("sheet"))
    rid = int(body.get("row"))
    col = str(body.get("col")).upper()
    if sheet not in STOCK_COLS or col not in STOCK_COLS[sheet]:
        return False, "%s 表的 %s 列不可写（公式列）" % (sheet, col)
    if not store.one("SELECT COUNT(*) FROM stock WHERE sheet=? AND row_id=?",
                     (sheet, rid), 0):
        return False, "%s 第 %d 行没有数据" % (sheet, rid)
    # ⚠ 缺键**不等于**「清空这一格」，这两件事必须分开。
    #   写成 body.get("value") 的话，调用方把键名拼错（传 v 而不是 value）
    #   就会被解读成「用户清空了这个格子」，往下走那条 DELETE ——
    #   **静默删数据，还回一句「已保存」**。2.4.6 真栽过：一次手写探针
    #   把「药品 第2行 数量=10」删掉了，事前事后都没报任何错。
    #   前端清空格子发的是 value: ""，**键一定在**，所以这条拦不到正常操作。
    if "value" not in body:
        return False, "请求里少了 value 字段（清空请传 value: \"\"）"
    v, s = _stock_vs(sheet, col, body.get("value"))
    with store.tx("stock") as c:
        if v is None and s is None:
            c.execute("DELETE FROM stock WHERE sheet=? AND row_id=? AND col=?",
                      (sheet, rid, col))
        else:
            c.execute("INSERT INTO stock(sheet,row_id,col,v,s) VALUES(?,?,?,?,?)"
                      " ON CONFLICT(sheet,row_id,col) DO UPDATE SET"
                      " v=excluded.v, s=excluded.s", (sheet, rid, col, v, s))
    drop_cache(STOCK)
    return True, "%s 第 %d 行 %s 已保存" % (sheet, rid, col)


def stock_add(body):
    sheet = str(body.get("sheet"))
    if sheet not in STOCK_COLS:
        return False, "不支持的表 %s" % sheet
    name = str(body.get("name") or "").strip()
    if not name:
        return False, "名称不能为空"
    with store.tx("stock") as c:
        rid = int(c.execute("SELECT COALESCE(MAX(row_id),0)+1 FROM stock"
                            " WHERE sheet=?", (sheet,)).fetchone()[0])
        for col, val in body.items():
            if col in ("sheet", "name", "row"):
                continue
            cu = str(col).upper()
            if cu not in STOCK_COLS[sheet] or cu == "A":
                continue
            v, s = _stock_vs(sheet, cu, val)
            if v is None and s is None:
                continue
            c.execute("INSERT INTO stock(sheet,row_id,col,v,s) VALUES(?,?,?,?,?)",
                      (sheet, rid, cu, v, s))
        v, s = _stock_vs(sheet, "A", name)
        c.execute("INSERT INTO stock(sheet,row_id,col,v,s) VALUES(?,?,?,?,?)"
                  " ON CONFLICT(sheet,row_id,col) DO UPDATE SET"
                  " v=excluded.v, s=excluded.s", (sheet, rid, "A", v, s))
    drop_cache(STOCK)
    return True, "%s 已新增「%s」" % (sheet, name)


# ================================================================
# ③+ 待办 + 零食吃掉
# ================================================================
def _todo_fields(body):
    return (str(body.get("stat") or "未完成"),
            str(body.get("item") or "").strip(),
            str(body.get("cat") or "").strip(),
            dstr(to_date(str(body.get("due") or ""))) if body.get("due") else "",
            str(body.get("pri") or "中"),
            str(body.get("note") or "").strip())


def todo_add(body):
    f = _todo_fields(body)
    if not f[1]:
        return False, "事项不能为空"
    with store.tx("stock") as c:
        c.execute("INSERT INTO todo(stat,item,cat,due,pri,note,ord)"
                  " VALUES(?,?,?,?,?,?,"
                  "(SELECT COALESCE(MAX(ord),0)+1 FROM todo))", f)
    drop_cache(STOCK)
    return True, "待办已保存"


def todo_edit(body):
    rid = int(body.get("row"))
    f = _todo_fields(body)
    if not f[1]:
        return False, "事项不能为空"
    with store.tx("stock") as c:
        cur = c.execute("UPDATE todo SET stat=?,item=?,cat=?,due=?,pri=?,note=?"
                        " WHERE id=?", f + (rid,))
        if not cur.rowcount:
            return False, "找不到这条待办", None
    drop_cache(STOCK)
    return True, "待办已更新"


def todo_toggle(body):
    rid = int(body.get("row"))
    stat = str(body.get("stat") or "").strip()
    with store.tx("stock") as c:
        r = c.execute("SELECT stat FROM todo WHERE id=?", (rid,)).fetchone()
        if not r:
            return False, "找不到这条待办"
        if stat not in ("未完成", "已完成"):
            stat = "未完成" if (r["stat"] or "") == "已完成" else "已完成"
        c.execute("UPDATE todo SET stat=? WHERE id=?", (stat, rid))
    drop_cache(STOCK)
    return True, "已勾选/取消"


def todo_del(body):
    rid = int(body.get("row"))
    r = store.q1("SELECT stat,item,cat,due,pri,note FROM todo WHERE id=?", (rid,))
    if not r:
        return False, "找不到这条待办"
    payload = {"stat": r["stat"], "item": r["item"], "cat": r["cat"],
               "due": r["due"], "pri": r["pri"], "note": r["note"]}
    try:
        _recycle_put("todo", _todo_label(payload), "todo/add", payload)
    except OSError as e:
        return False, "回收站写入失败，已中止删除：%s" % e
    with store.tx("stock") as c:
        c.execute("DELETE FROM todo WHERE id=?", (rid,))
    drop_cache(STOCK)
    return True, "待办已删除（可在设置页的回收站恢复）"


def stock_eat(body):
    """吃掉 1 个：数量-1，减到 0 自动标「已食用」"""
    rid = int(body.get("row"))
    with store.tx("stock") as c:
        if not c.execute("SELECT 1 FROM stock WHERE sheet='零食' AND row_id=?"
                         " AND col='A'", (rid,)).fetchone():
            return False, "第 %d 行没有零食" % rid
        q = c.execute("SELECT v FROM stock WHERE sheet='零食' AND row_id=?"
                      " AND col='I'", (rid,)).fetchone()
        qty = max(0, int((q["v"] if q else 0) or 0) - 1)
        c.execute("INSERT INTO stock(sheet,row_id,col,v,s) VALUES('零食',?,'I',?,NULL)"
                  " ON CONFLICT(sheet,row_id,col) DO UPDATE SET v=excluded.v,s=NULL",
                  (rid, float(qty)))
        if qty == 0:
            c.execute("INSERT INTO stock(sheet,row_id,col,v,s)"
                      " VALUES('零食',?,'H',NULL,'已食用')"
                      " ON CONFLICT(sheet,row_id,col) DO UPDATE SET"
                      " v=NULL,s=excluded.s", (rid,))
    drop_cache(STOCK)
    if qty > 0:
        return True, "吃掉 1 个，剩 %d" % qty
    return True, "吃完了，已自动划掉"




# ================================================================
# ④ AI（DeepSeek）· 设置与药品信息生成
# ================================================================
DEFAULT_BASE = "https://api.deepseek.com"
# 2026-07-24 起 deepseek-chat / deepseek-reasoner 已停用，请求会直接 400/404。
# 保险起见前端还能「从 API 拉取模型列表」，不依赖这份写死的清单。
AI_MODELS = ["deepseek-flash", "deepseek-v4-pro"]
# 已停用的旧模型名 → 新名（读到旧配置时自动迁移，避免用户升级后直接报错）
AI_MODEL_MIGRATE = {"deepseek-chat": "deepseek-flash",
                    "deepseek-reasoner": "deepseek-flash",
                    "deepseek-v4-flash": "deepseek-flash",
                    "deepseek-v4-flash-vision-exp": "deepseek-flash"}

# 官方价目（元 / 百万 tokens，2026-08-17 起峰谷计价；[空闲, 高峰]，高峰=空闲的2倍）
# 高峰时段：北京时间 周一至周五 9:00-12:00、14:00-18:00
AI_PRICES = {
    "deepseek-flash":   {"cache_hit": (0.02, 0.04), "cache_miss": (1.0, 2.0), "out": (4.0, 8.0)},
    "deepseek-v4-pro":  {"cache_hit": (0.15, 0.30), "cache_miss": (4.5, 9.0), "out": (13.5, 27.0)},
}
AI_USAGE_FILE = os.path.join(CONF_DIR, "ai_usage.json")
AI_ANALYSIS_FILE = os.path.join(CONF_DIR, "ai_analysis.json")

# 注意：这是「整理个人备药清单」的辅助信息，不是医疗建议。
# 提示词里明确要求不确定就写"请核对说明书"，前端还会再挂免责提示。
DRUG_SYS_PROMPT = (
    "你在帮一个大学生整理寝室备药清单。根据药名，给出该药的常见参考信息。\n"
    "只输出一个 JSON 对象，不要任何解释或代码块标记，字段固定为：\n"
    '{"disease":"针对疾病/适应症","usage":"使用方法与用量","effect":"大致功效","side_effect":"常见副作用与注意事项"}\n'
    "要求：每项用简体中文，40 字以内，面向普通人；剂量写常见成人剂量；\n"
    "不确定或没有把握的内容不要编造，直接写「请核对说明书」；\n"
    "这些内容仅供参考，不能替代说明书或医嘱。"
)


SHELF_SYS_PROMPT = (
    "你在帮一个大学生估算「开封之后，这个东西还能用/吃多久」。\n"
    "判断依据是这一类物品开封后的通用常识（比如眼药水开封 4 周、"
    "糖浆开封 1~3 个月、维生素片开封 6 个月、薯片开封几天…），"
    "**不要去找生产日期或包装上的有效期** —— 那两回事。\n"
    "只输出一个 JSON 对象，不要解释、不要代码块标记，字段固定为：\n"
    '{"months":"数字（月，可以是小数，比如 0.25 表示一周）","why":"一句话说明理由，30 字以内"}\n'
    "要求：months 必须是纯数字的字符串；实在没有把握就返回 0 并在 why 里写"
    "「拿不准，请按包装说明」；宁可能用得更短也不要给一个危险的长数字。"
)


def ai_shelf(body):
    """问 AI「开封之后建议多久用完」。**只给建议，不写库** ——
    前端把它填进输入框，用户看着不对可以改，点保存才落盘。"""
    sheet = str(body.get("sheet") or "").strip()
    name = str(body.get("name") or "").strip()
    if not name:
        return False, "这一行还没有名称，先填上名字再问"
    cfg = ai_config_load()
    if not (cfg.get("api_key") or "").strip():
        return False, "还没配置 API Key，先到设置 → AI 里填一个"
    note = str(body.get("note") or "").strip()
    user = "物品：%s（在「%s」分类下）" % (name, sheet or "物资")
    if note:
        user += "\n备注：%s" % note
    ok, out, _ = _ai_chat(cfg, [
        {"role": "system", "content": SHELF_SYS_PROMPT + profile_hint()},
        {"role": "user", "content": user}], timeout=30, scope="shelf")
    if not ok:
        return False, out
    try:
        text = str(out).strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
        obj = json.loads(text)
    except Exception:
        return False, "模型返回的不是合法 JSON，请重试：%s" % str(out)[:120]
    try:
        months = float(str(obj.get("months") or 0))
    except (TypeError, ValueError):
        return False, "模型给的月数看不懂：%r" % obj.get("months")
    if months <= 0:
        return False, str(obj.get("why") or "模型拿不准这个能放多久，请按包装说明填")
    if months > 120:
        months = 120.0
    # 小数月对用户没意义（谁会去填「0.25 个月」），整数就写整数，不然留一位
    shown = int(months) if abs(months - round(months)) < 0.01 else round(months, 1)
    return True, "AI 建议：开封后 %s 个月（%s）" % (
        shown, str(obj.get("why") or "").strip()[:60]), {
        "months": shown, "why": str(obj.get("why") or "").strip()[:200]}


def bg_save(body):
    """存背景图。**前端先缩好再发过来** —— 服务端只有标准库，没有 PIL，
    没法自己缩放；而一张手机原图动辄五六兆，直接存下来每次开页面都要传一遍。

    收的是 data:image/...;base64,... 这种 dataURL，浏览器读本地文件最省事的写法。"""
    raw = str(body.get("data") or "")
    if not raw:
        return False, "没收到图片"
    m = re.match(r"^data:image/(\w+);base64,(.+)$", raw, re.S)
    if not m:
        return False, "图片格式不对"
    fmt, b64 = m.group(1).lower(), m.group(2)
    if fmt not in ("jpeg", "jpg", "png", "webp"):
        return False, "只支持 JPEG / PNG / WebP"
    try:
        blob = base64.b64decode(b64, validate=True)
    except Exception:
        return False, "图片数据解不开，可能传了一半"
    if not blob:
        return False, "图片是空的"
    if len(blob) > BG_MAX_BYTES:
        return False, ("缩完之后还有 %.1f MB，太大了（上限 %d MB）。"
                       "换一张小一点的，或者先用画图工具缩一下。"
                       % (len(blob) / 1048576.0, BG_MAX_BYTES // 1048576))
    os.makedirs(BG_DIR, exist_ok=True)
    ext = "jpg" if fmt in ("jpeg", "jpg") else fmt
    name = "%s.%s" % (BG_STEM, ext)
    dest = os.path.join(BG_DIR, name)
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, dest)             # 原子替换：写一半断电也不会留下半张图
    # 换了格式就把旧格式那份删掉，不然 _配置\背景\ 会越攒越多
    for other in ("jpg", "png", "webp"):
        if other != ext:
            try:
                old = os.path.join(BG_DIR, "%s.%s" % (BG_STEM, other))
                if os.path.isfile(old):
                    os.remove(old)
            except OSError:
                pass
    patch = {"bg_image": name}
    # 前端量过这张图的明暗之后会带一个建议的「压暗」值过来 ——
    # 照片亮不亮直接决定要压多少，让用户自己试是折磨。他照样可以再拖滑块。
    if body.get("dim") is not None:
        try:
            d = int(round(float(body["dim"])))
        except (TypeError, ValueError):
            d = None
        if d is not None:
            patch["bg_dim"] = max(0, min(90, d))
    # 记一个「这是第几版」的标记，**用一个只增不减的计数器**。
    # ⚠ 试过两个别的写法，都不行：
    #   · 拿文件名当版本号 —— 换图之后名字还是「背景.jpg」，URL 一模一样，
    #     浏览器就把缓存里那张旧的端出来了（用户报的「换不了背景」）
    #   · 拿文件改动时间 —— `int(getmtime())` 只精确到秒，连着换两张图
    #     落在同一秒里，版本号还是没变（实测撞过）
    #   计数器不会撞，而且「第几版」这个说法也比时间戳好懂。
    _n = int(store.kv_get("bg_rev", 0) or 0) + 1
    store.kv_set("bg_rev", _n)
    patch["bg_rev"] = str(_n)
    settings_save(patch)
    return True, "背景已更新", {"file": name, "kb": round(len(blob) / 1024.0, 1),
                                "rev": patch["bg_rev"], "dim": patch.get("bg_dim")}


def bg_clear(body=None):
    """删掉背景图。**文件和设置一起清** —— 只清一个的话，
    下次开页面会一直去要一个不存在的文件。"""
    try:
        p = bg_path()
        if p and os.path.isfile(p):
            os.remove(p)
    except OSError as e:
        return False, "图片被占用，删不掉：%s" % e
    settings_save({"bg_image": "", "bg_rev": ""})
    return True, "背景已去掉，回到纯色"


def mask_key(k):
    """只回显尾号，避免明文往返"""
    if not k:
        return ""
    return (k[:5] + "****" + k[-4:]) if len(k) > 12 else "****"


def is_peak_now(when=None):
    """DeepSeek 峰谷计价：高峰 = 北京时间 周一至周五 9:00-12:00、14:00-18:00"""
    t = when or datetime.now()
    if t.weekday() >= 5:
        return False
    hm = t.hour * 60 + t.minute
    return (9 * 60 <= hm < 12 * 60) or (14 * 60 <= hm < 18 * 60)


def _f(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def ai_cost(model, prompt_tokens, completion_tokens, cache_hit_tokens, peak):
    """估算一次调用的花费（元）"""
    p = AI_PRICES.get(model) or AI_PRICES[AI_MODELS[0]]
    i = 1 if peak else 0
    hit = min(_f(cache_hit_tokens), _f(prompt_tokens))
    miss = max(0.0, _f(prompt_tokens) - hit)
    return (hit / 1e6 * p["cache_hit"][i]
            + miss / 1e6 * p["cache_miss"][i]
            + _f(completion_tokens) / 1e6 * p["out"][i])


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def _save_json(path, obj):
    with _write_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def ai_usage_log(scope, model, usage):
    """把一次调用的 token 用量记到 ai_usage.json"""
    if not isinstance(usage, dict):
        return None
    peak = is_peak_now()
    rec = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "scope": scope,
           "model": model,
           "prompt": int(_f(usage.get("prompt_tokens"))),
           "completion": int(_f(usage.get("completion_tokens"))),
           "total": int(_f(usage.get("total_tokens"))),
           "cache_hit": int(_f(usage.get("prompt_cache_hit_tokens")
                               or usage.get("prompt_tokens_details", {}).get("cached_tokens"))),
           "peak": peak}
    rec["cost"] = round(ai_cost(model, rec["prompt"], rec["completion"], rec["cache_hit"], peak), 6)
    data = _load_json(AI_USAGE_FILE, {})
    calls = data.get("calls") or []
    calls.append(rec)
    data["calls"] = calls[-2000:]          # 只留最近 2000 条，防止无限增长
    _save_json(AI_USAGE_FILE, data)
    return rec


def ai_usage_get():
    """汇总用量：总计 + 分场景 + 分模型 + 最近 20 次"""
    data = _load_json(AI_USAGE_FILE, {})
    calls = data.get("calls") or []
    tot = {"calls": len(calls), "prompt": 0, "completion": 0, "total": 0, "cost": 0.0}
    by_scope, by_model = {}, {}
    for c in calls:
        for k in ("prompt", "completion", "total"):
            tot[k] += int(c.get(k) or 0)
        tot["cost"] += _f(c.get("cost"))
        for bucket, key in ((by_scope, c.get("scope") or "其他"),
                            (by_model, c.get("model") or "?")):
            b = bucket.setdefault(key, {"calls": 0, "total": 0, "cost": 0.0})
            b["calls"] += 1
            b["total"] += int(c.get("total") or 0)
            b["cost"] += _f(c.get("cost"))
    tot["cost"] = round(tot["cost"], 4)
    for b in list(by_scope.values()) + list(by_model.values()):
        b["cost"] = round(b["cost"], 4)
    return {"total": tot, "by_scope": by_scope, "by_model": by_model,
            "recent": list(reversed(calls[-20:])),
            "peak_now": is_peak_now(), "prices": AI_PRICES}


def ai_usage_clear(body=None):
    _save_json(AI_USAGE_FILE, {"calls": []})
    return True, "用量统计已清空"


def ai_config_load():
    try:
        with open(AI_CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def ai_config_get():
    """给前端看的配置（Key 脱敏）"""
    cfg = ai_config_load()
    model = cfg.get("model") or AI_MODELS[0]
    note = ""
    if model in AI_MODEL_MIGRATE:          # 旧模型名已停用，自动迁移
        note = "模型 %s 已停用，已自动切到 %s" % (model, AI_MODEL_MIGRATE[model])
        model = AI_MODEL_MIGRATE[model]
        cfg["model"] = model
        try:
            _save_json(AI_CONFIG, cfg)
        except Exception:
            pass
    # 回忆书可以单独选一个模型（整理日报用便宜的、问答用强的），没选就跟随上面
    mm = str(cfg.get("memory_model") or "").strip()
    if mm in AI_MODEL_MIGRATE:
        mm = AI_MODEL_MIGRATE[mm]
    # 看图模型也是单独一个：**不是所有模型都能读图**，主模型换了不影响它，
    # 它不支持图片时也只改这一个。没设就跟随主模型。
    vm = str(cfg.get("vision_model") or "").strip()
    if vm in AI_MODEL_MIGRATE:
        vm = AI_MODEL_MIGRATE[vm]
    models = list(AI_MODELS)
    for m in (model, mm, vm):
        if m and m not in models:
            models.insert(0, m)
    return {"api_key_masked": mask_key(cfg.get("api_key", "")),
            "has_key": bool(cfg.get("api_key")),
            "model": model,
            "memory_model": mm,
            "vision_model": vm,
            "base_url": cfg.get("base_url") or DEFAULT_BASE,
            "models": models,
            "model_note": note}


def ai_config_save(body):
    cfg = ai_config_load()
    key = str(body.get("api_key") or "").strip()
    # 回显的掩码值不能当成新 Key 存回去
    if key and "****" not in key:
        cfg["api_key"] = key
    if body.get("clear_key"):
        cfg["api_key"] = ""
    cfg["model"] = str(body.get("model") or cfg.get("model") or AI_MODELS[0]).strip()
    # 回忆书模型：留空 = 跟随上面的模型
    if "memory_model" in body:
        cfg["memory_model"] = str(body.get("memory_model") or "").strip()
    # 看图模型：留空 = 跟随主模型。单独留一个是因为主模型很可能看不了图
    if "vision_model" in body:
        cfg["vision_model"] = str(body.get("vision_model") or "").strip()
    cfg["base_url"] = str(body.get("base_url") or cfg.get("base_url") or DEFAULT_BASE).strip().rstrip("/")
    with _write_lock:
        os.makedirs(CONF_DIR, exist_ok=True)
        tmp = AI_CONFIG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, AI_CONFIG)
    return True, "设置已保存"


def _ai_chat(cfg, messages, timeout=30, json_mode=True, scope="other"):
    """调一次 chat/completions（OpenAI 兼容）。
    返回 (ok, 内容或错误信息, usage)。usage 会顺手记进 ai_usage.json。"""
    key = str(cfg.get("api_key") or "").strip()
    if not key:
        return False, "还没配置 API Key，请先到「⚙ 设置」里填", None
    base = str(cfg.get("base_url") or DEFAULT_BASE).rstrip("/")
    model = cfg.get("model") or AI_MODELS[0]
    payload = {"model": model, "messages": messages, "temperature": 0.3, "stream": False}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        hint = {401: "API Key 不对或已失效", 402: "账户余额不足",
                429: "请求太频繁或额度用尽",
                400: "请求被拒绝（模型名可能不对，去设置页点「刷新模型列表」试试）"}.get(e.code, "")
        return False, "调用失败（HTTP %d）%s %s" % (e.code, hint, detail[:120]), None
    except urllib.error.URLError as e:
        return False, "连不上 %s：%s（检查网络或 Base URL）" % (base, e.reason), None
    except Exception as e:
        return False, "调用出错：%s" % e, None
    usage = data.get("usage")
    try:
        ai_usage_log(scope, model, usage)
    except Exception:
        pass                       # 记用量失败绝不能影响主流程
    try:
        return True, data["choices"][0]["message"]["content"], usage
    except Exception:
        return False, "返回格式看不懂：%s" % json.dumps(data, ensure_ascii=False)[:150], usage


SUGGEST_KIND = {"drug": "药品", "daily": "日用品", "snack": "零食", "todo": "待办事项"}
SUGGEST_SYS = ('你在帮用户补全一个个人物品清单里的名称。根据用户输入的开头几个字，'
               '猜他可能想记录什么，给出 5 个候选名称。\n'
               '只输出 JSON：{"names":["候选1","候选2",...]}\n'
               '要求：名称简短具体（如"百事可乐 300ml""复方感冒灵颗粒"），'
               '不要解释、不要编号、不要重复用户已输入的部分。')


_SUG_CACHE = {}          # (kind, text) → names。进程内缓存，重启就清


def ai_suggest(body):
    """输入名称时的 AI 兜底补全。

    ⚠ 这是**全应用最烧钱的一处**：实测占全部 AI 花费的 76%。前端那三道闸
      （一个字不问 / 一次输入只问一次 / 问过的记下来）是主力，这里是第二道：
      **同一个词永远不付第二次钱**。进程内一个小字典就够 —— 重启后重问
      几次也就几分钱，不值得为它落盘。"""
    kind = str(body.get("kind") or "").strip()
    text = str(body.get("text") or "").strip()
    if not text:
        return False, "还没输入内容"
    if len(text) < 2:
        return False, "再多打一个字"          # 一个字猜出来的东西没参考价值
    ck = (kind, text)
    if ck in _SUG_CACHE:
        return True, "（缓存）%d 个" % len(_SUG_CACHE[ck]), {"names": _SUG_CACHE[ck]}
    label = SUGGEST_KIND.get(kind, "物品")
    ok, out, _ = _ai_chat(ai_config_load(), [
        {"role": "system", "content": SUGGEST_SYS},
        {"role": "user", "content": "类别：%s\n已输入：%s" % (label, text)}],
        timeout=20, scope="suggest")
    if not ok:
        return False, out
    try:
        t = str(out).strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t)
        obj = json.loads(t)
        names = [str(n).strip()[:40] for n in (obj.get("names") or []) if str(n).strip()]
        names = [n for n in names if n != text][:6]
    except Exception:
        return False, "模型返回格式不对，请重试"
    if not names:
        return False, "没猜到什么，换个字试试"
    if len(_SUG_CACHE) > 500:
        _SUG_CACHE.clear()                    # 别无限涨
    _SUG_CACHE[ck] = names
    return True, "AI 猜了 %d 个" % len(names), {"names": names}


# ---------------- 总览分析：把各模块汇总成一小段文字喂给模型 ----------------
def _hm(v):
    """时间 → 分钟数（跨夜口径：12:00 前算次日）。

    ⚠ 换了 SQLite 之后，时间列在窄表里存的是**字符串** 'HH:MM'
      （Excel 那边是 datetime.time，或者「一天的小数」）。
      这里原来只认后两种，字符串掉进 float() 抛异常、被吞成 None ——
      表现是**后端算出来的睡眠时间全是 0**，而前端同一份数据算出来是对的。
      AI 拿的是后端那份，于是它理直气壮地说「睡眠数据全是0，要么没填要么没睡」，
      用户明明填了。所以这个分支必须补上。"""
    if v is None:
        return None
    if isinstance(v, dtime):
        m = v.hour * 60 + v.minute
    elif isinstance(v, str) and ":" in v:
        p = v.strip().split(":")
        try:
            m = int(p[0]) * 60 + int(p[1])
        except (ValueError, IndexError):
            return None
        if not (0 <= m < 1440):
            return None
    else:
        try:
            m = round(float(v) * 24 * 60)
        except (TypeError, ValueError):
            return None
    return m + 1440 if m < 720 else m


def _core_col_list():
    """「核心」组有哪些列。**必须从 check_item 表里查**，不能写死。

    2.2 起打卡项可以自己增删改，写死列号的后果是：用户加的核心项永远不计分、
    删掉的项还一直在分母里拖着。表和前端都走同一份定义，才不会出现
    前端显示 80%、AI 那边说 57% 这种事。表空了就退回出厂那几项。"""
    try:
        cols = [x["col"] for x in (check_items().get("core") or [])]
    except Exception:
        cols = []
    return cols or ["Q", "R", "T", "U", "S"]


def _day_stat(day, st):
    """Python 版单日统计（与前端 dayStats 同口径）"""
    L = day.get("L")
    try:
        Lv = None if L in (None, "") else float(L)
    except (TypeError, ValueError):
        Lv = None
    # 小睡口径：空 = 还没记（不算数）；**0 = 「没小睡」，判不达标（扣分）**；
    # 1~30 = 达标；>30 = 睡太久。
    # ⚠ 这是刻意定的口径（见使用说明），0 不是"达标"，是要扣分的 ——
    #   别因为看着别扭就改成达标：前端 dayStats 和文档都按这个来，
    #   改一处不改另一处，AI 说的完成率就和人看到的不一样了。
    s_ok = None if Lv is None else (Lv > 0 and Lv <= 30)
    # ⚠ 核心项**从打卡项表里数**，不能写死 Q/R/T/U。
    #   2.2 起打卡项可以自己增删改，写死列号的后果是：用户加的核心项永远不计分，
    #   删掉的项还一直在分母里拖着。前端的 dayStats 已经改成查表了，这里必须跟。
    _core_cols = _core_col_list()
    core = 0
    for _c in _core_cols:
        if _c == "S":                        # 小睡是算出来的，不是打勾的
            core += 1 if s_ok else 0
        elif day.get(_c) == "√":
            core += 1
    sleep_h = None
    a, b = _hm(day.get("C")), _hm(day.get("D"))
    if a is not None and b is not None:
        sleep_h = ((b - a) / 60.0 + 24) % 24
    tmin, emin, lmin = _hm(day.get("C")), _hm(st.get("early")), _hm(st.get("late"))
    judge = "" if tmin is None else ("早睡" if tmin <= emin else ("偏晚" if tmin <= lmin else "熬夜"))
    return {"core": core, "sleep": sleep_h, "judge": judge,
            "sport": 1 if _f(day.get("AA")) > 0 else 0,
            "screen": _f(day.get("AB"))}


def _cashflow(tails, month_inc, month_exp, balance, opening_total=0.0):
    """未来几个月的尾款压力：每月要付多少、按近期水平估的结余、付完还剩多少。
    只想回答一个问题 ——「这批尾款我扛得住吗」。"""
    pend = [t for t in tails if t["stat"] == "待付" and t.get("pdate")]
    if not pend:
        return {"months": [], "est_surplus": 0.0, "surplus_src": 0, "tight": False}
    # 预估月结余 = 最近有数据的 3 个月的 (真实收入 - 支出) 平均值
    # 注意用 month_inc_real（已剔除期初「结余」），否则会把一次性余额当成每月挣的
    keys = sorted(set(list(month_inc) + list(month_exp)))[-3:]
    surpluses = [month_inc.get(k, 0) - month_exp.get(k, 0) for k in keys]
    est = (sum(surpluses) / len(surpluses)) if surpluses else 0.0

    by_month = {}
    for t in pend:
        by_month.setdefault(str(t["pdate"])[:7], 0.0)
        by_month[str(t["pdate"])[:7]] += t["tail"]
    left = balance - sum(t["tail"] for t in pend)      # 现在就全付掉还剩多少
    rows, tight = [], False
    for ym in sorted(by_month)[:6]:
        tail_amt = round(by_month[ym], 2)
        net = round(est - tail_amt, 2)
        if net < 0:
            tight = True
        rows.append({"month": ym[:4] + "年" + ym[5:].lstrip("0") + "月",
                     "tail": tail_amt, "est_surplus": round(est, 2),
                     "net": net, "warn": net < 0})
    return {"months": rows, "est_surplus": round(est, 2), "surplus_src": len(surpluses),
            "tight": tight, "left_after_all": round(left, 2),
            "opening_total": round(opening_total, 2)}


def _digest_bill():
    b = cached(BILL, load_bill)
    k = b["kpi"]
    # ⚠ 喂给 AI 的这份摘要里也有「收入」这个词，同样要说清楚是哪一种。
    #   以前只给一个数，AI 就会一本正经地分析「你赚了 3427 元」，
    #   而同一屏的饼图上写的是 600 —— 两个数在用户眼里就是「数据对不上」。
    #   现在口径统一成「总收入含期初」，但**要把期初是多少讲明白**，
    #   否则 AI 会把本金夸成赚钱能力，给出「你月入三千四，可以多花点」这种建议。
    out = ["累计：总收入 %.0f 元，支出 %.0f 元，结余 %.0f 元；"
           "待付周边尾款 %.0f 元，可动用 %.0f 元"
           % (k["inc"], k["exp"], k["bal"], k["pending"], k["avail"])]
    if k["opening"]:
        out.append("（口径说明：总收入 %.0f 元里，有 %.0f 元是**期初余额** —— "
                   "开学时手里本来就有的钱，不是这段时间挣的；真正挣到的是 %.0f 元。"
                   "涉及「赚钱能力 / 收入水平」的判断请用后者，"
                   "涉及「账面结构 / 钱够不够花」才用前者。）"
                   % (k["inc"], k["opening"], k["earned"]))
    if k["exp"]:
        out.append("支出构成：" + "、".join(
            "%s %.0f元(%.0f%%)" % (c, v, v / k["exp"] * 100)
            for c, v in list(b["exp_cat"].items())[:10]))
    if b["inc_cat"]:
        out.append("收入构成：" + "、".join(
            "%s %.0f元" % (c, v) for c, v in b["inc_cat"].items()))
    for m in b["months"][-6:]:
        bud = "预算%.0f元" % m["budget"] if m.get("budget") else "未设预算"
        out.append("  %s：收入 %.0f，支出 %.0f，%s" % (m["m"], m["inc"], m["exp"], bud))
    g = b["groups"]
    if g["rows"]:
        out.append("团购：待核销 %.0f 元、已核销 %.0f 元、已退回 %.0f 元"
                   % (g["wait"], g["done"], g["back"]))
    days = b.get("day_exp") or {}
    if days:
        vals = sorted(days.values(), reverse=True)
        out.append("单日最高支出 %.0f 元；有支出的天数 %d 天" % (vals[0], len(vals)))
    return "\n".join(out)


def _digest_check():
    c = cached(CHECK, load_check)
    st = c["settings"]
    out = []
    for m in c["months"]:
        days = [d for d in m["days"] if d.get("date", "") <= date.today().strftime("%Y-%m-%d")]
        if not days:
            continue
        stats = [_day_stat(d, st) for d in days]
        sl = [x["sleep"] for x in stats if x["sleep"] is not None]
        avg = sum(sl) / len(sl) if sl else 0
        # 分母从同一张表数（原来写死 5.0，用户改过打卡项之后这个数就是错的）
        _cn = max(1, len(_core_col_list()))
        core = sum(x["core"] for x in stats) / (len(stats) * float(_cn))
        out.append("%s：记了 %d 天；平均睡眠 %.1fh（目标 %s）；早睡 %d 天、熬夜 %d 天；"
                   "核心完成率 %.0f%%；运动 %d 天；超过屏幕目标的 %d 天"
                   % (m["ym"], len(days), avg, st.get("goal_sleep"),
                      sum(1 for x in stats if x["judge"] == "早睡"),
                      sum(1 for x in stats if x["judge"] == "熬夜"),
                      core * 100, sum(x["sport"] for x in stats),
                      sum(1 for x in stats if x["screen"] and x["screen"] > _f(st.get("screen")))))
    d = c.get("dreams") or []
    if d:
        out.append("梦境档案累计 %d 条" % len(d))
    return "\n".join(out) or "还没有打卡记录"


def _digest_stock():
    s = cached(STOCK, load_stock)
    out = []
    for o in s["overview"]:
        out.append("%s：共 %d 条，已过期 %d，临期 %d，待补货 %d"
                   % (o["cat"], o["total"], o["expired"], o["soon"], o["restock"]))
    soon = []
    for name in ("药品", "日用品", "零食"):
        for r in s["sheets"][name]["rows"]:
            if r.get("_days") is not None and 0 <= r["_days"] <= 30:
                soon.append("%s「%s」剩%d天" % (name, (r.get("A") or "?")[:18], r["_days"]))
    if soon:
        out.append("30 天内到期：" + "、".join(soon[:15]))
    for name in ("药品", "日用品", "零食"):
        names = [(r.get("A") or "").strip() for r in s["sheets"][name]["rows"] if r.get("A")]
        if names:
            out.append("现有%s %d 种：%s" % (name, len(names), "、".join(names[:25])))
    todo = [t for t in s["todo"] if (t.get("stat") or "") != "已完成"]
    out.append("未完成待办 %d 项%s" % (len(todo),
               ("：" + "、".join((t.get("item") or "")[:20] for t in todo[:8])) if todo else ""))
    return "\n".join(out)


ANALYZE_SCOPES = {
    "all": ("整体", "这是一个人（大学生，住校）的个人数据。请综合「钱、作息、物资」三条线做一次简短体检：\n"
                     "1) 各用一句话概括现状；2) 指出最值得改的一件事，并给一个能立刻执行的小动作。\n"
                     "语气像朋友，别喊口号，不要罗列数据。全文 200 字以内。"),
    "bill": ("账单", "分析这个人的花钱情况：结构是否健康、哪类占比过高、和预算的差距、"
                     "有没有明显可省的地方。给 2-3 条具体建议，每条一句话。150 字以内，别复述数字。"),
    "check": ("打卡", "分析这个人的生活习惯：作息规律性、早睡/熬夜趋势、运动和屏幕时长、"
                      "哪项坚持得最好/最差。给 2-3 条具体可执行的改进，每条一句话。150 字以内。"),
    "stock": ("物资管家", "这是寝室备药和日用品的库存。请分析：1) 还缺哪些常备药（感冒/退烧/肠胃/外伤/过敏等）；"
                          "2) 有没有明显重复囤积的；3) 哪些该优先用掉；4) 该补什么。"
                          "给一个简短的清单式建议，180 字以内。"),
}
ANALYZE_SYS = ("你在帮一个大学生看他的个人数据记录。{who}。要求：用简体中文、"
               "口语化、直接说结论；不要复述他已知的数字；不要用 markdown 标题；"
               "不要编造数据里没有的信息；不确定就不说。全文控制在要求字数内。")


def ai_analyze(body):
    """生成某个板块的分析。结果缓存到 ai_analysis.json，force=true 才重跑。"""
    scope = str(body.get("scope") or "all")
    if scope not in ANALYZE_SCOPES:
        return False, "未知的分析范围 %s" % scope
    cache = _load_json(AI_ANALYSIS_FILE, {})
    if not body.get("force") and cache.get(scope):
        return True, "已是最新分析", cache[scope]
    try:
        if scope == "all":
            digest = "【账单】\n%s\n\n【作息打卡】\n%s\n\n【物资】\n%s" % (
                _digest_bill(), _digest_check(), _digest_stock())
        else:
            digest = {"bill": _digest_bill, "check": _digest_check, "stock": _digest_stock}[scope]()
    except Exception as e:
        return False, "汇总数据失败：%s" % e
    label, ask = ANALYZE_SCOPES[scope]
    ok, out, usage = _ai_chat(ai_config_load(), [
        {"role": "system", "content": ANALYZE_SYS.replace("{who}", address_clause())},
        {"role": "user", "content": "【%s数据】\n%s\n%s%s\n【要求】\n%s" % (
            label, digest, profile_hint(), recent_notes(), ask)}],
        timeout=90, json_mode=False, scope="analyze")
    if not ok:
        return False, out
    rec = {"scope": scope, "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "model": (ai_config_load().get("model") or AI_MODELS[0]),
           "tokens": (usage or {}).get("total_tokens"),
           "text": str(out).strip()}
    cache[scope] = rec
    try:
        _save_json(AI_ANALYSIS_FILE, cache)
    except Exception:
        pass
    return True, "分析完成", rec


def ai_analysis_get():
    return _load_json(AI_ANALYSIS_FILE, {})


def ai_models_fetch(body=None):
    """从官方 /models 拉取当前可用的模型名（模型名改过两次了，别写死）"""
    cfg = ai_config_load()
    if body and body.get("api_key") and "****" not in str(body["api_key"]):
        cfg = dict(cfg, api_key=str(body["api_key"]).strip())
    key = str(cfg.get("api_key") or "").strip()
    if not key:
        return False, "还没配置 API Key，请先填再刷新"
    base = str(cfg.get("base_url") or DEFAULT_BASE).rstrip("/")
    req = urllib.request.Request(base + "/models",
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        ids = [i for i in ids if "vision" not in i and "exp" not in i]
    except urllib.error.HTTPError as e:
        return False, "拉取失败（HTTP %d）：Key 可能不对" % e.code
    except Exception as e:
        return False, "拉取失败：%s" % e
    if not ids:
        return False, "接口没返回任何模型"
    cur = cfg.get("model")
    # 当前选的模型已不在列表里 → 自动切到第一个
    if cur not in ids:
        cfg["model"] = ids[0]
        _save_json(AI_CONFIG, cfg)
    return True, "已从 API 拉到 %d 个模型：%s" % (len(ids), "、".join(ids)), {"models": ids}


def ai_test(body=None):
    """测试连接：发一句最小请求验证 Key 是否可用"""
    cfg = ai_config_load()
    if body and body.get("api_key") and "****" not in str(body["api_key"]):
        cfg = dict(cfg, api_key=str(body["api_key"]).strip())     # 用刚填还没保存的 Key 试
    ok, out, _ = _ai_chat(cfg, [{"role": "user", "content": "回复两个字：可用"}],
                          timeout=20, json_mode=False, scope="test")
    if not ok:
        return False, out
    return True, "连接正常（%s），模型回复：%s" % (cfg.get("model") or AI_MODELS[0],
                                                  str(out).strip()[:30])


def ai_drug(body):
    """生成药品的参考信息。只返回内容，不写 Excel —— 由前端预览确认后再写。"""
    name = str(body.get("name") or "").strip()
    if not name:
        return False, "缺少药名"
    note = str(body.get("note") or "").strip()
    user = "药名：%s" % name + ("\n备注：%s" % note if note else "")
    ok, out, _ = _ai_chat(ai_config_load(), [
        {"role": "system", "content": DRUG_SYS_PROMPT},
        {"role": "user", "content": user}], scope="drug")
    if not ok:
        return False, out
    try:
        text = str(out).strip()
        if text.startswith("```"):                    # 少数情况会带代码块围栏
            text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
        obj = json.loads(text)
    except Exception:
        return False, "模型返回的不是合法 JSON，请重试：%s" % str(out)[:120]
    fields = {"disease": "针对疾病", "usage": "使用方法", "effect": "大致功效", "side_effect": "副作用"}
    data = {k: str(obj.get(k) or "").strip()[:300] for k in fields}
    if not any(data.values()):
        return False, "模型没给出有效内容，请重试"
    return True, "已生成，请核对后保存", data


# ================================================================
# ④.5 日报 / 周报 / 月报（Markdown 笔记）
# ================================================================
# 提示词移植自 SpringNote（github.com/Radiant303/SpringNote），做了两处改动：
#   · 它是职场导向的（「开发者或职场人士」「遇到什么卡点」「用户所在行业」），
#     这里改成大学生记生活的口径，并去掉「所在行业」变量
#   · 多了一个 {day_data} —— 当天的打卡/账单数据。这是移植进本系统的核心理由：
#     日报不再是纯手写，而是有数据支撑的（详见 note_day_data）
# ---------- 个性化：AI 口吻与称呼 ----------
# 口吻只影响「写得详略如何」，不影响事实口径 —— 不要让它变成「可以让 AI 编」的开关
TONE_HINT = {
    "brief": "从简。短句为主，一件事一两句写完，能省的字都省掉，不铺陈、不总结升华。",
    "natural": "适中。该说清楚的说清楚，不刻意压缩也不刻意展开。",
    "rich": "舒展一些。把细节、感受和前后关联写充分，段落之间过渡自然，但仍不许添加没发生过的事。",
}


def ai_vision(body):
    """看图录入：**只识别，不写库**。

    这个函数一个字节都不会写进账目或打卡。它把识别结果连同图片一起还给前端，
    用户核对、改完、点确认之后，才走普通那条 bill/add、check/set 通路 ——
    跟手动输进去的完全一样。账目和睡眠是长期数据，模型看错一位数要翻半天账，
    这一步不能省；而且不走专线写入，出了问题也好排查。
    """
    kind = str(body.get("kind") or "")
    if kind not in ("bill", "sleep"):
        return False, "只支持 bill（账单截图）和 sleep（睡眠截图）"
    data_url = str(body.get("image") or "")
    cfg = ai_config_load()
    exp, _inc = _cats_of(_sem())
    try:
        moods = (load_check().get("opts") or {}).get("mood") or []
    except Exception:
        moods = []
    schema = {"cats": exp or ["其他"], "pays": pays_of(), "moods": moods or ["好", "一般", "差"]}
    # 配置不齐就先别存图 —— 存了也是孤儿，用户还得自己去找地方删
    _model, cerr = vision.check_config(cfg)
    if cerr:
        return False, cerr
    ok, info, _aid = vision.save_image(DATA_ROOT, store, data_url, kind + "_shot")
    if not ok:
        return False, info
    ok, got, _usage = vision.recognize(cfg, kind, data_url, schema)
    if not ok:
        return False, got
    tip = str(got.get("warn") or "").strip()
    if got.get("confidence") == "low":
        tip = (tip + " " if tip else "") + "模型对这张图把握不大，建议逐项核对。"
    out = {"kind": kind, "attach": info["file"], "attach_id": info["id"], "tip": tip}
    if kind == "bill":
        out["items"] = got.get("items") or []
        n = len(out["items"])
        return True, "认出 %d 条，逐条核对后再确认" % n, out
    out["fields"] = got
    return True, "认出来了，核对一下再确认", out


def tone_hint():
    try:
        t = str(settings_load().get("note_tone") or "natural")
    except Exception:
        t = "natural"
    return TONE_HINT.get(t, TONE_HINT["natural"])


def profile_hint():
    """把「个人基本情况」拼成一段给模型看的背景。

    没有就返回空串 —— 提示词里那一段会整块消失，不会留一个空标题
    让模型以为「这里本来该有内容」。"""
    try:
        p = str(settings_load().get("personal") or "").strip()
    except Exception:
        p = ""
    if not p:
        return ""
    return ("\n【关于这个人】以下是用户自己写的背景情况，"
            "分析时要把它考虑进去，用它来解释数据、给贴合他实际的建议，"
            "但**不要凭空补充这里没写的事**：\n%s\n" % p)


def recent_notes(n=3):
    """最近 n 天的日报正文（只要最近的），给分析当参考。
    开关没开、或者根本没写过日记，就返回空串。"""
    try:
        s = settings_load()
        if not s.get("ai_use_notes"):
            return ""
    except Exception:
        return ""
    try:
        # ⚠ 只取日报。周报月报是日报的汇总，一起喂进去等于同样的内容说三遍，
        # 又占 token 又容易让模型以为那是三件不同的事。
        names = [nm for (k, nm, _p) in _note_files() if k == "daily"]
        out = []
        for nm in sorted(names, reverse=True)[:n]:
            try:
                body = str(notes.read_note("daily", nm) or "").strip()
            except Exception:
                continue          # 上了锁、或者单篇坏了 —— 跳过就好，别拖垮分析
            if body:
                out.append("【%s】\n%s" % (nm, body[:1200]))
        if not out:
            return ""
        return ("\n【最近几天的日记（用户主动允许参考）】\n%s\n"
                "日记只用来理解他最近的状态和在意的事，**不要在里面找数据**，"
                "也不要复述日记内容。\n" % "\n\n".join(out))
    except Exception:
        return ""


def address_clause():
    """给模型看的一句「该怎么称呼用户」。设置里填了称呼就用它，没填就用「你」。
    只有 AI **对着用户说话**的地方才用它（回忆书、总览页分析）；
    日报周报月报是第一人称写的，塞称呼进去会很怪。"""
    try:
        who = str(settings_load().get("call_me") or "").strip()
    except Exception:
        who = ""
    return "称呼他「%s」" % (who or "你")


NOTE_DAILY_PROMPT = """你是「小煦拾简」的日报整理助手。
你的任务是根据已有日报和新增随手记录，整理生成一篇自然、真实、便于继续编辑的日报。

已知信息：
- 日期：{date}
- 已有日报：{existing_markdown}
- 新增随手记录：{raw_input}
- 当天系统记录到的数据：{day_data}

整理要求：
1. 综合利用所有已提供的信息进行整理，空变量自动忽略。
2. 如果已有日报存在，优先保留其中仍然有效的内容，并将新增记录自然融合进去；如果已有日报为空，则根据新增记录整理生成日报。
3. 严格保留事实，不得编造任何不存在的活动、时间、人物、原因、进展、结果、计划、评价或情绪。
4. 在不改变事实的前提下，可以自由整理语言，包括补充完整句子、调整语序、合并重复内容、优化表达，使内容更加自然流畅。
5. 当新增记录只是关键词、短语或简短描述时，应主动整理成符合正常书面表达的完整内容，而不是直接照抄原文。允许适度扩展描述，使表达更加自然，但扩展内容只能服务于表达已有事实，不得引入新的事实信息。
6. 将零散记录整理成连贯的生活记录，使全文具有连续阅读体验，读起来像用户亲自整理后的日记，而不是 AI 自动汇总的结果。
7. 内容较少时保持简洁，避免为了丰富内容而重复表达；内容较多时可自然分段或按主题组织，但不要为了分组而分组。
8. 表达应符合一个大学生记录日常生活的习惯，语言自然、克制、顺畅，避免机械、模板化或过于正式的总结语气。
9. 如果已有日报与新增记录存在重复，应保留表达更完整、更自然的一份，避免重复描述。
10. 保留已有日报的整体结构和可继续编辑性，不随意改变已有内容的组织方式。
11. 「当天系统记录到的数据」是自动采集的客观事实。要把它自然融进叙述里（例如「虽然只睡了六个多小时」「今天打卡基本没做」），不要另起一段罗列成数据清单；如果这些数据跟当天记录的内容没什么关系，就整段略去不写。不要据此推断用户的心情或想法。
12. 详略口吻：{tone}
13. 不输出变量名称，不解释整理过程，不添加任何说明，仅输出最终日报内容。"""

NOTE_WEEKLY_PROMPT = """你是「小煦拾简」的周报整理助手。请基于一周的日报 Markdown 生成一篇自然、有重点、可直接编辑的周报。

已知信息：
- 周期：{period_label}
- 本周日报内容：
{source_markdown}

写作原则：
1. 综合利用所有已提供的信息进行整理，空变量自动忽略。
2. 保留来源中的事实，不编造没有依据的事情、情绪、变化或计划。
3. 不需要固定套用「主要事情 / 关键进展 / 问题 / 下周计划」等模板，可以根据材料自由组织结构。
4. Markdown 要层次清楚、阅读舒服；可以使用标题、段落、列表、重点小结，但避免机械堆栏目。
5. 优先呈现这一周真正发生了什么、过得怎么样、遇到什么状况、接下来打算怎么走。
6. 语气自然，像一个认真回顾自己生活的人写的周记，不要像 AI 模板。
7. 全文第一行必须是一级标题，格式固定为 `# YYYY年M月 第NN周 周报`（例如 `# 2026年9月 第37周 周报`），不得自拟、追加或省略。日期区间不用写进正文，界面上会显示。
8. 详略口吻：{tone}
9. 只输出最终 Markdown，不要解释。"""

NOTE_MONTHLY_PROMPT = """你是「小煦拾简」的月报整理助手。请基于月度周报 Markdown 生成一篇自然、有回顾感、可继续编辑的月报。

已知信息：
- 周期：{period_label}
- 本月周报内容：
{source_markdown}

写作原则：
1. 保留来源中的事实，不编造事情、数据、评价或计划。
2. 不需要固定套用「核心成果 / 进展 / 问题复盘 / 个人成长 / 下月计划」等模板，可以根据材料自由组织结构。
3. Markdown 要美观、有呼吸感；可以使用标题、短段落、列表、总结和展望，但不要写成僵硬表格。
4. 重点体现这个月的主线、阶段性变化、值得保留的经验、还没解决的问题和自然的下一步。
5. 语气克制、真诚、有人的表达，不要过度包装，也不要像 AI 汇报模板。
6. 全文第一行必须是一级标题，格式固定为 `# YYYY年M月 月报`（例如 `# 2026年8月 月报`），不得自拟、追加或省略。日期区间不用写进正文，界面上会显示。
7. 详略口吻：{tone}
8. 只输出最终 Markdown，不要解释。"""


def _render(tpl, vars_):
    """占位符替换。空值统一填「（空）」而不是留空白 —— 留空白会让模型
    以为这里有内容却看不见，容易胡编。"""
    out = tpl
    for k, v in vars_.items():
        s = str(v or "").strip()
        out = out.replace("{%s}" % k, s if s else "（空）")
    return out


def _strip_fence(text):
    """模型偶尔会把 Markdown 包在 ``` 里，去掉围栏"""
    t = str(text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*[ \t]*\r?\n?", "", t)
        t = re.sub(r"\r?\n?```\s*$", "", t)
    return t.strip()


def note_day_data(d):
    """当天系统自动记录到的客观数据，喂给日报整理当背景。

    这是「把 SpringNote 搬进本系统」而不是「直接用 SpringNote」的核心理由 ——
    日报因此不是纯手写，而是有数据支撑的。
    取不到就返回空串，提示词里空变量会被忽略（不会让模型觉得"这儿有东西但看不见"）。
    """
    ds = notes.daily_name(d)
    bits = []
    try:
        dk = cached(CHECK, load_check)
        st = dk.get("settings") or {}
        day = None
        for m in dk.get("months", []):
            for x in m.get("days", []):
                if x.get("date") == ds:
                    day = x
                    break
            if day:
                break
        if day:
            s = _day_stat(day, st)          # 复用打卡页同口径的统计
            if s["sleep"] is not None:
                bits.append("睡眠 %.1f 小时%s" % (
                    s["sleep"], "（%s）" % s["judge"] if s["judge"] else ""))
            bits.append("核心打卡 %d/5" % s["core"])
            if s["sport"]:
                bits.append("运动 %s 分钟" % _f(day.get("AA")))
            elif str(day.get("Z") or "").strip() == "未运动":
                bits.append("未运动")
            if s["screen"]:
                bits.append("屏幕 %.1f 小时" % s["screen"])
            for col, label in (("L", "小睡"), ("AF", "心情"), ("AG", "精力")):
                v = day.get(col)
                if v not in (None, ""):
                    bits.append("%s%s" % (label, (" %s 分钟" % v) if col == "L" else " %s" % v))
            dd = (dk.get("dream_detail") or {}).get(ds)
            if dd:
                bits.append("记了 %d 个梦" % len(dd))
            if str(day.get("AH") or "").strip():
                bits.append("打卡备注：%s" % str(day["AH"]).strip()[:80])
    except Exception:
        pass
    try:
        bl = cached(BILL, load_bill)
        rows = [r for r in bl.get("records", [])
                if str(r.get("date") or "")[:10] == ds and r.get("stat") != "退回"]
        exp = sum(_f(r.get("exp")) for r in rows)
        inc = sum(_f(r.get("inc")) for r in rows)
        if exp:
            bits.append("支出 %.2f 元（%d 笔）" % (exp, len(rows)))
        if inc:
            bits.append("收入 %.2f 元" % inc)
    except Exception:
        pass
    return "；".join(bits)


def _local_merge(existing, raw, when):
    """AI 不可用时的兜底：把新内容按时间追加进去，先保证不丢东西"""
    title = "# %s 日报" % notes.daily_name(when)
    body = notes.strip_title(existing or "")
    line = "- %s %s" % (when.strftime("%H:%M"), " ".join(str(raw).split()))
    return "%s\n\n%s\n" % (title, (body + "\n" + line).strip() if body else line)


# ================= 2.3.6 新增的几份小数据 =================
# ⚠ 订阅、奖励、交易模板都放 kv 里的 JSON，**不建新表**。
#   理由：它们是「用户自己维护的一小串清单」，没有跟别的表做联查的需求。
#   建表要动 store.SCHEMA、结构守卫、迁移脚本，成本远大于收益。
#   （真正的领域数据还是走表 —— 这三样是清单，不是流水。）

def _kv_json(key, default):
    try:
        v = store.kv_get(key)
        return json.loads(v) if v else copy.deepcopy(default)
    except Exception:
        return copy.deepcopy(default)


def _kv_put(key, val):
    store.kv_set(key, json.dumps(val, ensure_ascii=False))


def check_series(body=None):
    """近 N 天的每日小结。

    **一个接口喂三样**：活跃热力图、连续天数（streak）、心情/精力/睡眠趋势图。
    本来该写三个接口 —— 可它们要的是同一份数据，只是切法不同。
    （ponytail：与其三次往返，不如一次给全。）"""
    try:
        days = int((body or {}).get("days") or 182)
    except (TypeError, ValueError):
        days = 182
    days = max(7, min(1095, days))
    core = _core_col_list()
    coreN = max(1, len(core))
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    by = {}
    for r in store.q("SELECT date,col,v FROM check_val WHERE date>=?", (start,)):
        by.setdefault(r["date"], {})[r["col"]] = r["v"]
    dreams = {}
    for r in store.q("SELECT date, COUNT(*) n FROM dream WHERE date>=? GROUP BY date",
                     (start,)):
        dreams[r["date"]] = r["n"]
    out = []
    for date in sorted(by):
        v = by[date]
        hit = sum(1 for c in core if v.get(c) == "√")
        sh = None
        if v.get("C") and v.get("D"):
            a, b = _hm(v.get("C")), _hm(v.get("D"))
            if a is not None and b is not None:
                sh = round(((b - a) / 60.0 + 24) % 24, 2)
        out.append({"d": date, "hit": hit, "n": coreN, "sleepH": sh,
                    "mood": v.get("AF") or "", "energy": v.get("AG") or "",
                    "dream": dreams.get(date, 0)})
    return True, "ok", {"days": out, "coreN": coreN}


def game_state(body=None):
    """积分 + 奖励。

    ⚠ **积分不存表**，每次从打卡现算。存下来就要处理「改了上个月的卡要不要
      补分」「删了记录分数怎么办」这一串同步问题 —— 而现算永远和打卡一致。"""
    ser = check_series({"days": 1095})[2]["days"]
    per_day, total = [], 0
    for x in ser:
        # 一天得分 = 核心项打√的个数；全打满额外 +5（有奖励才有劲）
        pt = x["hit"] + (5 if x["hit"] >= x["n"] and x["n"] > 1 else 0)
        per_day.append({"d": x["d"], "pt": pt})
        total += pt
    rewards = _kv_json("game.rewards", [])
    spent = sum(r.get("cost", 0) for r in rewards if r.get("got"))
    return True, "ok", {
        "total": total, "spent": spent, "left": total - spent,
        # 最近 30 天，给「最近攒了多少」用
        "recent": per_day[-30:],
        "rewards": rewards,
    }


def game_save(body):
    """整份替换奖励清单（和「打卡项保存」同一种语义）。"""
    body = body or {}
    items = body.get("rewards")
    if not isinstance(items, list):
        return False, "格式不对"
    clean = []
    for x in (items or [])[:60]:                  # 别让人塞几千条进来
        if not isinstance(x, dict):
            continue
        name = str(x.get("name") or "").strip()[:40]
        if not name:
            continue
        try:
            cost = max(0, min(99999, int(x.get("cost") or 0)))
        except (TypeError, ValueError):
            cost = 0
        clean.append({"id": str(x.get("id") or secrets.token_hex(4)), "name": name,
                      "cost": cost, "got": str(x.get("got") or "")})
    _kv_put("game.rewards", clean)
    return True, "奖励清单已更新", {"rewards": clean}


def game_redeem(body):
    """兑换：把某条奖励标记成已获得（花掉积分）。再点一次取消。"""
    rid = str((body or {}).get("id") or "")
    rewards = _kv_json("game.rewards", [])
    hit = None
    for r in rewards:
        if r.get("id") == rid:
            hit = r
            break
    if hit is None:
        return False, "没找到这条奖励"
    if hit.get("got"):
        hit["got"] = ""
        msg = "已取消兑换"
    else:
        st = game_state()[2]
        if hit.get("cost", 0) > st["left"]:
            return False, "积分不够（还差 %d）" % (hit["cost"] - st["left"])
        hit["got"] = date.today().strftime("%Y-%m-%d")
        msg = "兑换成功"
    _kv_put("game.rewards", rewards)
    return True, msg, {"rewards": rewards}


# ---- 订阅 / 定期扣款 ----
# 跟「尾款计划」不是一回事：尾款是一次性的，订阅是**每月循环**的。
def sub_save(body):
    """整份替换订阅清单。"""
    body = body or {}
    items = body.get("subs")
    if not isinstance(items, list):
        return False, "格式不对"
    clean = []
    for x in (items or [])[:120]:
        if not isinstance(x, dict):
            continue
        name = str(x.get("name") or "").strip()[:40]
        if not name:
            continue
        try:
            amt = round(float(x.get("amount") or 0), 2)
        except (TypeError, ValueError):
            amt = 0.0
        try:
            day = max(1, min(28, int(x.get("day") or 1)))   # 28 封顶，二月也有这一天
        except (TypeError, ValueError):
            day = 1
        cyc = str(x.get("cycle") or "月")
        if cyc not in ("月", "季", "年"):
            cyc = "月"
        clean.append({"id": str(x.get("id") or secrets.token_hex(4)), "name": name,
                      "amount": amt, "day": day, "cycle": cyc,
                      "note": str(x.get("note") or "")[:60]})
    _kv_put("subs", clean)
    return True, "订阅已更新", {"subs": clean}


def sub_list(body=None):
    """订阅清单 + 算出来的「每月合多少」「下次什么时候扣」。"""
    subs = _kv_json("subs", [])
    today = date.today()
    for s in subs:
        k = {"月": 1, "季": 3, "年": 12}[s["cycle"]]
        s["monthly"] = round(s["amount"] / k, 2)      # 摊到每个月
        # 下次扣款日：这个月还没到就是本月，过了就是下个周期
        try:
            nxt = date(today.year, today.month, s["day"])
        except ValueError:
            nxt = date(today.year, today.month, 28)   # 2 月 29 号的兜底
        while nxt < today:
            m = nxt.month + k
            y = nxt.year + (m - 1) // 12
            nxt = date(y, (m - 1) % 12 + 1, s["day"])
        s["next"] = nxt.strftime("%Y-%m-%d")
        s["days"] = (nxt - today).days
    subs.sort(key=lambda x: x["days"])
    return True, "ok", {"subs": subs,
                        "monthly": round(sum(s["monthly"] for s in subs), 2),
                        "yearly": round(sum(s["monthly"] for s in subs) * 12, 2)}


# ---- 笔记导出（2.3.6）----
def notes_export(body):
    """把某一类笔记导出成文档。

    ⚠ **后端没有 Markdown 解析器，也不打算为导出再写一个。** 正文的 HTML
      由前端用屏幕上那套 md2html 生成好再传上来 —— 这样导出的和看到的
      一定一致；两边各写一套迟早会对不上（屏幕上一个样、导出一个样）。

    fmt：
      md   → 原样复制 .md 文件（自己留底、进 VSCode 看）
      doc  → 单文件 HTML，扩展名 .doc。**Word 本来就能开 HTML**，
             这样不用手写 200 行 OOXML，图片也能内嵌进去
      html → 同样内容存成 .html，浏览器里 Ctrl+P 就能存成 PDF
    """
    body = body or {}
    kind = str(body.get("type") or "daily")
    fmt = str(body.get("fmt") or "doc")
    if kind not in notes.KINDS:
        return False, "未知的笔记类型"
    if fmt not in ("md", "doc", "html"):
        return False, "不支持的格式"
    dest = os.path.join(DATA_ROOT, "_导出")
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    cn = notes.KIND_CN[kind]
    try:
        os.makedirs(dest, exist_ok=True)
        if fmt == "md":
            # 一篇一个文件，原样复制（不解析、不重排 —— 留底就要原样）
            sub = os.path.join(dest, "%s_%s" % (cn, stamp))
            os.makedirs(sub, exist_ok=True)
            n = 0
            for it in (notes.list_notes(kind) or []):
                md = notes.read_note(kind, it["name"])
                if md is None:
                    continue
                with open(os.path.join(sub, "%s.md" % it["name"]), "w",
                          encoding="utf-8") as fh:
                    fh.write(md)
                n += 1
            return True, "导出 %d 篇到 %s" % (n, sub), {"path": sub, "kind": "dir", "n": n}
        # doc / html：单文件，正文由前端给
        html = str(body.get("html") or "")
        if not html.strip():
            return False, "没有内容可导出"
        title = "%s导出 %s" % (cn, stamp)
        page = (
            "<!DOCTYPE html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            "<title>%s</title><style>"
            "body{font-family:'Microsoft YaHei',sans-serif;line-height:1.8;"
            "max-width:820px;margin:0 auto;padding:32px 24px;color:#222}"
            "h1{font-size:1.6em;border-bottom:2px solid #ddd;padding-bottom:8px;"
            "margin-top:2em}h2{font-size:1.25em;margin-top:1.6em}"
            "h3{font-size:1.08em}img{max-width:100%%;border-radius:6px}"
            "blockquote{border-left:3px solid #ddd;margin-left:0;padding-left:14px;color:#666}"
            "table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:5px 9px}"
            "hr{border:0;border-top:1px solid #eee;margin:2.4em 0}"
            "@media print{body{max-width:none;padding:0}}"
            "</style></head><body><h1>%s</h1>%s</body></html>"
            % (title, title, html))
        path = os.path.join(dest, "%s_%s.%s" % (cn, stamp, fmt))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(page)
        return True, "已导出到 %s" % os.path.basename(path), {
            "path": path, "kind": "file", "n": body.get("count") or 0,
            "tip": "Word 版可以直接打开改；想存成 PDF 就打开 HTML 那个再按 Ctrl+P",
        }
    except OSError as e:
        log_error("notes_export", e)
        return False, "导出失败：%s（文件可能正被 Word 打开）" % e


# ---- 笔记插图（2.3.6）----
# ⚠ 放**文件**，不放数据库。塞 BLOB 进去会让备份、迁目录、导出全部变重，
#   而且图片本来就该「跟笔记一起走」—— 放在 笔记\_附件\ 下，搬目录时
#   是跟着 笔记\ 整个走的，一行额外代码都不用。
ATTACH_DIR = os.path.join(NOTES_ROOT, "_附件")
_ATT_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}\.(jpg|png|gif|webp)$")


def attach_path(name):
    """附件路径。名字必须完全匹配白名单正则 —— 它是直接拼进路径的，
    挡不住 ../ 就等于把整个磁盘暴露了。"""
    n = os.path.basename(str(name or ""))
    if not _ATT_RE.match(n):
        return None
    return os.path.join(ATTACH_DIR, n)


def attach_save(body):
    """存一张插图，返回它在正文里该用的写法。

    前端已经缩过图了（跟背景图同一套，canvas 缩到 1600px），
    这里只负责落盘 + 算个内容哈希当文件名 —— 同一张图传两次只存一份。"""
    data = str((body or {}).get("data") or "")
    m = re.match(r"^data:image/(\w+);base64,(.+)$", data, re.S)
    if not m:
        return False, "这不是图片"
    fmt = m.group(1).lower()
    if fmt not in ("jpeg", "jpg", "png", "gif", "webp"):
        return False, "这种格式不支持（用 jpg 或 png）"
    try:
        raw = base64.b64decode(m.group(2), validate=False)
    except Exception:
        return False, "图片数据坏了"
    if len(raw) > 8 * 1024 * 1024:
        return False, "图太大了（超过 8 MB）—— 先裁一下再传"
    ext = "jpg" if fmt in ("jpeg", "jpg") else fmt
    name = hashlib.sha1(raw).hexdigest()[:20] + "." + ext
    try:
        os.makedirs(ATTACH_DIR, exist_ok=True)
        p = os.path.join(ATTACH_DIR, name)
        if not os.path.isfile(p):           # 同一张图不重复写
            with open(p, "wb") as fh:
                fh.write(raw)
    except OSError as e:
        log_error("attach_save", e)
        return False, "存不下这张图：%s" % e
    return True, "图插进来了", {"name": name, "url": "/attach/" + name,
                                "md": "![](附件/%s)" % name, "kb": round(len(raw) / 1024, 1)}


# ---- 摘抄（2.3.6）----
# 一条 = 内容 + 出处 + 标签 + 我为什么记它。放 kv 的 JSON，跟订阅一个道理。
def quote_save(body):
    body = body or {}
    items = body.get("quotes")
    if not isinstance(items, list):
        return False, "格式不对"
    clean = []
    for x in (items or [])[:2000]:
        if not isinstance(x, dict):
            continue
        text = str(x.get("text") or "").strip()
        if not text:
            continue
        clean.append({
            "id": str(x.get("id") or secrets.token_hex(4)),
            "text": text[:2000],
            "from": str(x.get("from") or "")[:80],
            "tags": [str(t)[:12] for t in (x.get("tags") or [])][:8],
            "note": str(x.get("note") or "")[:500],
            "at": str(x.get("at") or datetime.now().strftime("%Y-%m-%d")),
        })
    _kv_put("essay.quotes", clean)
    return True, "摘抄已保存", {"quotes": clean}


def quote_list(body=None):
    items = _kv_json("essay.quotes", [])
    tags = {}
    for q in items:
        for t in q.get("tags") or []:
            tags[t] = tags.get(t, 0) + 1
    return True, "ok", {"quotes": items, "tags": tags, "n": len(items)}


# ---- 交易模板（记一笔的时候一键重填）----
def tpl_list(body=None):
    return True, "ok", {"tpls": _kv_json("bill.tpls", [])}


def tpl_save(body):
    body = body or {}
    items = body.get("tpls")
    if not isinstance(items, list):
        return False, "格式不对"
    clean = []
    for x in (items or [])[:40]:
        if not isinstance(x, dict):
            continue
        name = str(x.get("name") or "").strip()[:20]
        if not name:
            continue
        clean.append({"id": str(x.get("id") or secrets.token_hex(4)), "name": name,
                      "amount": str(x.get("amount") or ""),
                      "cat": str(x.get("cat") or ""), "who": str(x.get("who") or ""),
                      "pay": str(x.get("pay") or ""), "note": str(x.get("note") or "")[:60]})
    _kv_put("bill.tpls", clean)
    return True, "模板已保存", {"tpls": clean}


def note_append(body):
    """往某篇笔记**原样追加**一段，不过 AI。

    和 note_quick 的区别：那个会让 AI 把整篇重写一遍（随手记要的是通顺），
    而日记模板填出来的东西**本来就有结构**（「三件感恩的事」这种小标题
    是内容的一部分），再让 AI 整理一次会把结构揉平。
    所以这条路径就是「把这段字贴到文件末尾」，不做任何加工。

    ⚠ 字段名跟 notes 那套保持一致，是 **type**（不是 kind）。
      我第一版写成 kind，结果前端发 kind、notes/get 认 type，两边对不上 ——
       读到的是「未知的笔记类型：」，查了半天才发现是字段名的事。
       这里两个都收，免得以后再有人踩。"""
    kind = str(body.get("type") or body.get("kind") or "daily")
    text = str(body.get("text") or "").strip()
    if not text:
        return False, "还没写内容"
    if kind not in notes.KINDS:
        return False, "未知的笔记类型"
    name = str(body.get("name") or "")
    if not name:
        if kind == "daily":
            name = notes.daily_name(datetime.now())
        elif kind == "essay":
            name = notes.essay_name(datetime.now())
        else:
            return False, "这种笔记得指定是哪一篇"
    if not notes.valid_name(kind, name):
        return False, "笔记名不对"
    notes.ensure_note(kind, name)
    old = notes.read_note(kind, name) or ""
    notes.write_note(kind, name, old.rstrip() + "\n\n" + text + "\n")
    return True, "写进去了", {"kind": kind, "name": name,
                              "display": notes.display_name(kind, name)}


def note_new(body):
    """新建一篇笔记，返回它的名字。

    随笔按**时刻**命名（见 notes.essay_name 那段：一天可能写好几篇）。
    日报/周报/月报是按周期算出来的，直接回名字就行。"""
    body = body or {}
    kind = str(body.get("type") or body.get("kind") or "essay")
    if kind not in notes.KINDS:
        return False, "未知的笔记类型"
    now = datetime.now()
    if kind == "essay":
        name = notes.essay_name(now)
        # 同一分钟里连点两下会撞名 —— 往后顺延到不撞为止
        n = 1
        while os.path.isfile(notes.note_path(kind, name)) and n < 60:
            name = notes.essay_name(now + timedelta(minutes=n))
            n += 1
    elif kind == "daily":
        name = notes.daily_name(now)
    elif kind == "weekly":
        name = notes.weekly_name(now)
    else:
        name = notes.monthly_name(now)
    notes.ensure_note(kind, name)
    return True, "建好了", {"kind": kind, "name": name,
                            "display": notes.display_name(kind, name)}


def note_quick(body):
    """随手记：写进当天日报，并让 AI 把已有内容和新记录整理成一篇。

    并发保护：AI 调用要好几秒，期间用户可能又提交了一条。所以写回前比对
    内容有没有变过，变了就放弃 AI 结果、改用本地追加 —— 不能拿旧版本覆盖。
    """
    text = str(body.get("text") or "").strip()
    if not text:
        return False, "还没写内容"
    when = datetime.now()
    if body.get("date"):
        try:
            when = datetime.strptime(str(body["date"]), "%Y-%m-%d").replace(
                hour=when.hour, minute=when.minute)
        except ValueError:
            return False, "日期格式不对"
    name = notes.daily_name(when)
    notes.ensure_note("daily", name)
    existing = notes.read_note("daily", name) or ""

    cfg = ai_config_load()
    if not str(cfg.get("api_key") or "").strip():
        merged = _local_merge(existing, text, when)
        notes.write_note("daily", name, merged)
        _note_backup()
        return True, "已记下（没配 API Key，先按原文追加）", {
            "name": name, "content": merged, "ai": False}

    # json_mode 必须关掉：日报要的是 Markdown，开着 response_format=json_object
    # 会被 DeepSeek 直接拒掉（"Prompt must contain the word 'json'"）
    ok, out, _ = _ai_chat(cfg, [
        {"role": "system", "content": _render(prompt_override("daily", NOTE_DAILY_PROMPT), {
            "date": name,
            "existing_markdown": existing,
            "raw_input": text,
            "day_data": note_day_data(when.date()),
            "tone": tone_hint()})},
        {"role": "user", "content": "请整理今天的日报。"}],
        json_mode=False, scope="report")

    now_existing = notes.read_note("daily", name) or ""
    if now_existing != existing:
        # 整理期间又来了新内容，别覆盖
        merged = _local_merge(now_existing, text, when)
        notes.write_note("daily", name, merged)
        _note_backup()
        return True, "已记下（整理期间又有新内容，改用直接追加）", {
            "name": name, "content": merged, "ai": False}

    if not ok or not _strip_fence(out):
        merged = _local_merge(existing, text, when)
        notes.write_note("daily", name, merged)
        _note_backup()
        return True, "已记下（AI 整理失败，按原文追加）：%s" % str(out)[:80], {
            "name": name, "content": merged, "ai": False}

    merged = _strip_fence(out)
    if not merged.endswith("\n"):
        merged += "\n"
    notes.write_note("daily", name, merged)
    _note_backup()
    return True, "已整理进今天的日报", {"name": name, "content": merged, "ai": True}


def _note_backup():
    """每天头一次写笔记时留一份，跟 Excel 的自动备份一个思路"""
    try:
        stamp = date.today().strftime("%Y%m%d")
        root = backup_root()
        dest = os.path.join(root, "笔记_%s" % stamp)
        if not os.path.exists(dest):
            os.makedirs(root, exist_ok=True)
            notes.copy_tree(dest)
            _prune_note_backups()
    except Exception:
        pass          # 备份失败不能挡住写入


def _prune_note_backups(keep=7):
    for root in backup_roots():
        try:
            names = sorted(n for n in os.listdir(root) if n.startswith("笔记_"))
            for n in names[:-keep]:
                shutil.rmtree(os.path.join(root, n), ignore_errors=True)
        except Exception:
            pass
        pass


def _note_source(kind, name):
    """拼周报/月报的来源内容"""
    if kind == "weekly":
        parts = []
        for d in notes.week_days(name):
            nm = notes.daily_name(d)
            md = notes.read_note("daily", nm)
            if notes.has_content(md):
                parts.append("### %s\n\n%s" % (nm, notes.strip_title(md)))
        return "\n\n".join(parts)
    parts = []
    for w in notes.weeks_overlapping_month(name):
        md = notes.read_note("weekly", w)
        if notes.has_content(md):
            a, b = notes.iso_week_range(w)
            parts.append("### %s（%s ~ %s）\n\n%s" % (w, a, b, notes.strip_title(md)))
    return "\n\n".join(parts)


def _note_label(kind, name):
    if kind == "weekly":
        a, b = notes.iso_week_range(name)
        return "%s（%s ~ %s）" % (name, a, b)
    a, b = notes.month_range(name)
    return "%s（%s ~ %s）" % (name, a, b)


def note_generate(body):
    """生成/重新生成周报或月报。force=False 时已有内容就不动。"""
    kind = str(body.get("type") or "")
    name = str(body.get("name") or "").strip()
    force = bool(body.get("force"))
    if kind not in ("weekly", "monthly"):
        return False, "只能生成周报或月报"
    if not notes.valid_name(kind, name):
        return False, "名称格式不对：%s" % name

    existing = notes.read_note(kind, name) or ""
    if notes.has_content(existing) and not force:
        return True, "已经有内容了，跳过", {"skipped": True}

    src = _note_source(kind, name)
    if not src.strip():
        return False, "这段时间没有任何记录，先生成%s吧" % (
            "日报" if kind == "weekly" else "周报")

    cfg = ai_config_load()
    if not str(cfg.get("api_key") or "").strip():
        return False, "还没配 API Key，去「⚙ 设置」里填"

    # 提示词可以在设置里改（留空 = 用代码里这份，见 prompt_override）
    tpl = (prompt_override("weekly", NOTE_WEEKLY_PROMPT) if kind == "weekly"
           else prompt_override("monthly", NOTE_MONTHLY_PROMPT))
    ok, out, _ = _ai_chat(cfg, [
        {"role": "system", "content": _render(tpl, {
            "period_label": _note_label(kind, name),
            "source_markdown": src,
            "tone": tone_hint()})},
        {"role": "user", "content": "请生成%s。" % notes.KIND_CN[kind]}],
        timeout=180, json_mode=False, scope="report")
    if not ok:
        return False, out
    text = _strip_fence(out)
    if not notes.has_content(text):
        return False, "模型返回了空内容，已保留原文件不动"

    # 标题格式强制。标题不对会让后续「有效内容」判定和列表显示都错乱
    want = "# %s" % notes.title_of(kind, name)
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("# "):
        lines[0] = want
    else:
        lines.insert(0, want)
        lines.insert(1, "")
    text = "\n".join(lines).rstrip() + "\n"

    if not os.path.exists(notes.kind_dir(kind)):
        os.makedirs(notes.kind_dir(kind), exist_ok=True)
    notes.write_note(kind, name, text)
    _note_backup()
    return True, "%s已生成" % notes.KIND_CN[kind], {"name": name, "content": text}


def note_pending(body=None):
    """哪些周期缺报告（前端顶部提示条 + 启动后台补齐都用它）"""
    p = notes.pending()
    with _gen_lock:
        st = dict(_gen_state)
    return {"weekly": p["weekly"], "monthly": p["monthly"],
            "total": len(p["weekly"]) + len(p["monthly"]),
            "job": st}


# 启动后台补齐的进度。前端轮询 notes/pending 就能看到它跑到哪了。
_gen_state = {"running": False, "total": 0, "done": 0,
              "current": "", "finished": [], "error": ""}
_gen_lock = threading.Lock()
_gen_started = [False]


def note_autogen_start():
    """启动时在后台把缺的周报/月报补掉。

    必须放后台线程：Electron 是等 /api/bill 通了才开窗的，同步跑生成会让用户
    盯着十几秒空屏。这里还先 sleep 几秒，把开窗那几秒让出来。

    安全约束（跟 SpringNote 一致）：只补已结束的周期、只补有来源没内容的、
    note_generate 里 force=False，所以**永远不会覆盖已有内容**。
    """
    if _gen_started[0]:
        return
    _gen_started[0] = True

    def run():
        time.sleep(5)                       # 让窗口先开出来
        try:
            p = notes.pending()
            todo = [("weekly", n) for n in p["weekly"]] + \
                   [("monthly", n) for n in p["monthly"]]
        except Exception as e:
            with _gen_lock:
                _gen_state["error"] = "扫描失败：%s" % e
            return
        if not todo:
            return
        cfg = ai_config_load()
        if not str(cfg.get("api_key") or "").strip():
            return                          # 没配 Key 就别折腾了，前端会提示
        with _gen_lock:
            _gen_state.update({"running": True, "total": len(todo),
                               "done": 0, "current": "", "finished": [], "error": ""})
        for kind, name in todo:
            with _gen_lock:
                _gen_state["current"] = "%s %s" % (notes.KIND_CN[kind], name)
            try:
                ok, msg, _ = note_generate({"type": kind, "name": name})
            except Exception as e:
                ok, msg = False, str(e)
            with _gen_lock:
                _gen_state["done"] += 1
                _gen_state["finished"].append(
                    {"kind": kind, "name": name, "ok": ok, "msg": msg})
        with _gen_lock:
            _gen_state["running"] = False
            _gen_state["current"] = ""

    threading.Thread(target=run, daemon=True).start()


def note_list(body=None):
    """三种类型一次全返回 —— 前端切标签不用再请求"""
    return {k: notes.list_notes(k) for k in notes.KINDS}


# 从日报里挑待办。跟药品 AI 一个套路：**只返回候选，不写 Excel**，
# 由前端列出来让用户勾，确认后才调 todo/add。免得 AI 自作主张往待办表里塞东西。
TODO_EXTRACT_PROMPT = """你从一篇个人日记里挑出**还没做完、需要跟进**的事项。

只输出 JSON：{"todos":[{"item":"要做什么","cat":"类别","pri":"优先级","due":"YYYY-MM-DD"}]}

要求：
1. item 一句话说清要做什么，20 字以内，用日记里的原意，不要扩展或引申。
2. cat 只能从这几个里选：采购、事务、学习、生活、其他。
3. pri 只能从这几个里选：高、中、低。拿不准就填「中」。
4. due 只在日记里明确提到日期或时间点（比如「明天」「周五」「下周一」）时才填，
   按给定的今天日期换算成 YYYY-MM-DD；没提到就填空字符串。不要自己编日期。
5. 只挑**明确还没做**的事。已经做完的、纯感受和心情、对过去的描述，一律不要。
6. 一件事只出现一次，不要重复。
7. 一件都没有就返回 {"todos":[]}。
8. 只输出 JSON，不要解释、不要代码块标记。"""


def note_extract_todos(body):
    """从一篇笔记里提取待办候选（不落盘，等用户勾选）"""
    kind, name, err = _note_target(body)
    if err:
        return False, err
    md = notes.read_note(kind, name)
    if not notes.has_content(md):
        return False, "这篇还没有内容"
    cfg = ai_config_load()
    if not str(cfg.get("api_key") or "").strip():
        return False, "还没配 API Key，去「⚙ 设置」里填"
    # 参照日期必须用**这篇笔记的日期**，不是真实的今天。
    # 否则 9/16 写的日记里那句「明天要还书」会被算成 9/16（差一天）。
    try:
        ref = notes.parse_name(kind, name)
    except ValueError:
        ref = date.today()
    ok, out, _ = _ai_chat(cfg, [
        {"role": "system", "content": TODO_EXTRACT_PROMPT},
        {"role": "user", "content": "今天的日期：%s\n\n日记内容：\n%s" % (
            notes.daily_name(ref), notes.strip_title(md)[:6000])}],
        timeout=90, scope="todo")
    if not ok:
        return False, out
    try:
        text = str(out).strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
        obj = json.loads(text)
    except Exception:
        return False, "模型返回的不是合法 JSON，请重试：%s" % str(out)[:120]
    cats = ("采购", "事务", "学习", "生活", "其他")
    pris = ("高", "中", "低")
    items = []
    for t in (obj.get("todos") or [])[:20]:
        it = str(t.get("item") or "").strip()
        if not it:
            continue
        due = str(t.get("due") or "").strip()
        if not re.match(r"^20\d{2}-\d{2}-\d{2}$", due):
            due = ""
        items.append({"item": it[:60],
                      "cat": t.get("cat") if t.get("cat") in cats else "事务",
                      "pri": t.get("pri") if t.get("pri") in pris else "中",
                      "due": due, "note": "来自 %s %s" % (name, notes.KIND_CN[kind])})
    msg = ("找到 %d 条待办，勾选后才会写进待办表" % len(items)) if items \
        else "这篇里没找到还没做的事"
    return True, msg, {"todos": items}


def _note_target(body):
    kind = str(body.get("type") or "")
    name = str(body.get("name") or "").strip()
    if kind not in notes.KINDS:
        return None, None, "未知的笔记类型：%s" % kind
    if not notes.valid_name(kind, name):
        return None, None, "名称格式不对：%s" % name
    return kind, name, None


def note_get(body):
    kind, name, err = _note_target(body)
    if err:
        return False, err
    md = notes.read_note(kind, name)
    if md is None:
        return False, "这篇还没写"
    return True, "ok", {"name": name, "content": md}


def note_save(body):
    """前端编辑器手改后保存。这里不做 AI 整理，存什么就是什么。"""
    kind, name, err = _note_target(body)
    if err:
        return False, err
    content = str(body.get("content") or "")
    if not content.strip():
        return False, "内容不能为空"
    notes.write_note(kind, name, content if content.endswith("\n") else content + "\n")
    _note_backup()
    return True, "已保存", {"name": name}


def note_del(body):
    kind, name, err = _note_target(body)
    if err:
        return False, err
    # 存**原样**（加密开着时就是密文）—— 回收站是个 JSON 文件，
    # 往里塞明文等于把笔记加密白做了。write_note 认得密文，恢复时不会再套一层。
    raw = notes.read_raw(kind, name)
    if raw is None:
        return False, "这篇本来就不存在"
    try:
        _recycle_put("note", "%s %s" % (name, notes.KIND_CN[kind]), "note/write",
                     {"type": kind, "name": name, "content": raw})
    except OSError as e:
        return False, "回收站写入失败，已中止删除：%s" % e
    if not notes.delete_note(kind, name):
        return False, "这篇本来就不存在"
    return True, "已删除（可在设置页的回收站恢复）"


# ================================================================
# ④.6 回忆书（带工具调用的问答）
# ================================================================
# 移植自 SpringNote 的 Memories：本地检索 → 读取记录 → AI 归纳。
# 工具名和语义照搬它的（keyword_search / read_daily_note / ...），只删掉了
# run_tool_sequence / run_tool_batch 两个编排工具 —— DeepSeek 原生支持一轮返回
# 多个 tool_calls，直接并发跑就行，少两个工具、少一层间接。
# 另外多了一个 read_stats：读打卡/账单的统计数字，这是本系统独有的。
MEMORY_SYS_PROMPT = """你是「小煦拾简」的回忆书问答助手。你必须基于用户的历史日报、周报、月报回答问题。
你可以自主调用工具检索或读取记录；需要信息时先调用工具，不要让应用预先替你检索。
连续追问时结合完整消息历史理解省略指代，例如“什么时候”“那次”“刚才说的”等。
每条用户消息末尾附有发送时间（如 [发送时间：2026-08-11 20:04 星期二]），解析“今天”“昨天”“这周”等相对时间时以最新用户消息的发送时间为准，无需调用 get_current_date。
工具结果中 truncated 为 true 表示该条内容按字符上限被截断（截断处以“…”标记），totalCharacters 为原文总长度；没有工具能取回被截断的部分，重复调用同一工具只会得到相同的片段，此时基于已有内容回答并向用户说明不完整之处。
回答必须只依据工具返回和对话上下文；材料不足时明确说明缺少依据，不要编造事实。
用户问的是他自己的生活记录。{who}，不要用“用户”这种第三人称。
最终回答使用自然中文和清晰 Markdown，不要输出工具调用 JSON。"""

# 单条工具结果的字符上限。超了就截断并标 truncated —— 模型能据此判断"还有没看到的"
MEM_SEARCH_LIMIT = 20          # 一次搜索最多返回几条
MEM_SNIPPET_CHARS = 420        # 搜索片段长度
MEM_READ_CHARS = 6000          # 单篇读取上限
MEM_TOTAL_CHARS = 40000        # 一次工具调用的总预算，防止把上下文撑爆


def mem_limits():
    """回忆书检索的几个上限。**设置里能调**（2.3.6）。

    上面那几个常量是默认值。调小 = 更快更省 token 但 AI 看到的材料少；
    调大 = 看得更多但更慢更贵。范围都夹住了，免得有人填 0 或者 100000
    把一次问答变成几块钱。"""
    s = settings_load()

    def g(key, d, lo, hi):
        try:
            return max(lo, min(hi, int(s.get(key) or d)))
        except (TypeError, ValueError):
            return d

    return {
        "search": g("mem_search_limit", MEM_SEARCH_LIMIT, 3, 60),
        "snippet": g("mem_snippet_chars", MEM_SNIPPET_CHARS, 120, 2000),
        "read": g("mem_read_chars", MEM_READ_CHARS, 500, 30000),
        "total": g("mem_total_chars", MEM_TOTAL_CHARS, 4000, 200000),
        "turns": g("mem_max_turns", MEM_MAX_TURNS, 1, 20),
    }


def prompt_override(key, default):
    """取提示词：设置里改过就用改过的，没改过用代码里那份（2.3.6）。

    ⚠ **空字符串 = 用默认**。不这么定的话，用户把输入框清空保存
      就等于"把提示词删了"，AI 当场变成没有指令的裸模型 —— 那种错
      查起来毫无头绪（症状是"AI 突然变笨了"）。想恢复默认就是清空。"""
    try:
        v = str(settings_load().get("prompt_" + key) or "").strip()
    except Exception:
        return default
    return v or default

_DATE_PAT = r"^20\d{2}-(0[1-9]|1[0-2])-([0-2][0-9]|3[0-1])$"
_WEEK_PAT = r"^20\d{2}-W(0[1-9]|[1-4]\d|5[0-3])$"
_MONTH_PAT = r"^20\d{2}-(0[1-9]|1[0-2])$"


def _kw_params(scope):
    return {"type": "object", "properties": {"keywords": {
        "type": "array",
        "description": "本次 %s 检索要用的全部关键词或短语，按重要性排序。" % scope,
        "items": {"type": "string", "description": "一个关键词或短语，至少两个字。"}}},
        "required": ["keywords"], "additionalProperties": False}


def _one_of(prop, desc, pat):
    return {"type": "object", "properties": {prop: {
        "type": "string", "description": desc, "pattern": pat}},
        "required": [prop], "additionalProperties": False}


MEMORY_TOOLS = [
    {"type": "function", "function": {
        "name": "get_current_date",
        "description": "获取当前本地日期、ISO 周标签和周数。需要解析今天、昨天、这周这类相对日期时先用它。",
        "parameters": {"type": "object", "properties": {},
                       "required": [], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "keyword_search",
        "description": "在日报、周报、月报里做一次全局关键词检索。只在不知道记录属于哪一类、"
                       "或答案可能跨类型时才用它；用户明确说了日报/周报/月报时用对应的限定检索。"
                       "把这次检索要用的关键词一次性全部提交。每个关键词至少两个字。",
        "parameters": _kw_params("全局")}},
    {"type": "function", "function": {
        "name": "search_daily_notes",
        "description": "只检索日报。问题只涉及某天或日常记录时用它。关键词一次性全部提交，每个至少两个字。",
        "parameters": _kw_params("日报")}},
    {"type": "function", "function": {
        "name": "search_weekly_notes",
        "description": "只检索周报。问题只涉及周报时用它。关键词一次性全部提交，每个至少两个字。",
        "parameters": _kw_params("周报")}},
    {"type": "function", "function": {
        "name": "search_monthly_notes",
        "description": "只检索月报。问题只涉及月报时用它。关键词一次性全部提交，每个至少两个字。",
        "parameters": _kw_params("月报")}},
    {"type": "function", "function": {
        "name": "read_daily_note",
        "description": "读取某一天的日报全文。",
        "parameters": _one_of("date", "日期，格式 YYYY-MM-DD。", _DATE_PAT)}},
    {"type": "function", "function": {
        "name": "read_week_daily_notes",
        "description": "读取一个日期区间内的所有日报，通常是一周（周一至周日）。",
        "parameters": {"type": "object", "properties": {
            "startDate": {"type": "string", "description": "起始日期 YYYY-MM-DD。", "pattern": _DATE_PAT},
            "endDate": {"type": "string", "description": "结束日期 YYYY-MM-DD。", "pattern": _DATE_PAT}},
            "required": ["startDate", "endDate"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "read_weekly_note",
        "description": "读取某一 ISO 周的周报全文。不要用它读日报。",
        "parameters": _one_of("week", "ISO 周，格式 YYYY-Www，例如 2026-W28。", _WEEK_PAT)}},
    {"type": "function", "function": {
        "name": "read_month_weekly_notes",
        "description": "读取覆盖某个自然月的所有周报（跨月周会同时属于相邻两个月）。只返回周报。",
        "parameters": _one_of("month", "自然月，格式 YYYY-MM。", _MONTH_PAT)}},
    {"type": "function", "function": {
        "name": "read_month_report",
        "description": "读取某个月的月报全文。不要用它读日报。",
        "parameters": _one_of("month", "自然月，格式 YYYY-MM。", _MONTH_PAT)}},
    {"type": "function", "function": {
        "name": "resolve_iso_week",
        "description": "把 ISO 周标签换算成具体的起止日期（周一至周日）。需要知道某一周覆盖哪些日期时用它，别自己算。",
        "parameters": _one_of("week", "ISO 周，格式 YYYY-Www，例如 2026-W28。", _WEEK_PAT)}},
    {"type": "function", "function": {
        "name": "read_stats",
        "description": "读取打卡或账单的统计数字（本系统独有，日记正文里没有这些）。"
                       "打卡给睡眠时长、核心完成度、运动、心情精力的区间汇总；"
                       "账单给收支和分类花销。想用客观数据佐证或对比时用它。",
        "parameters": {"type": "object", "properties": {
            "module": {"type": "string", "description": "统计哪个模块。",
                       "enum": ["check", "bill"]},
            "from": {"type": "string", "description": "起始日期 YYYY-MM-DD。", "pattern": _DATE_PAT},
            "to": {"type": "string", "description": "结束日期 YYYY-MM-DD。", "pattern": _DATE_PAT}},
            "required": ["module", "from", "to"], "additionalProperties": False}}},
]


def _clip(text, limit):
    t = str(text or "")
    return (t[:limit], True, len(t)) if len(t) > limit else (t, False, len(t))


def _tool_get_current_date(_):
    t = date.today()
    y, w, _d = t.isocalendar()
    return {"date": notes.daily_name(t), "isoWeek": "%04d-W%02d" % (y, w), "weekNumber": w}


def _tool_search(args, kind=None):
    _ML = mem_limits()
    kws = args.get("keywords") or []
    if isinstance(kws, str):
        kws = [kws]
    hits = notes.search(kws, kind=kind, limit=_ML["search"],
                        snippet_width=_ML["snippet"])
    out, used = [], 0
    for h in hits:
        if used + len(h["snippet"]) > _ML["total"]:
            break
        used += len(h["snippet"])
        out.append({"kind": h["kind"], "name": h["name"], "title": h["title"],
                    "snippet": h["snippet"],
                    "truncated": h["totalCharacters"] > len(h["snippet"]),
                    "totalCharacters": h["totalCharacters"]})
    return {"results": out, "count": len(out)}


def _read_one(kind, name):
    _ML = mem_limits()
    md = notes.read_note(kind, name)
    if md is None:
        return {"name": name, "kind": kind, "error": "这篇还没有内容"}
    body, trunc, total = _clip(md, _ML["read"])
    return {"kind": kind, "name": name, "title": "%s %s" % (name, notes.KIND_CN[kind]),
            "content": body, "truncated": trunc, "totalCharacters": total}


def _tool_read_daily(a):
    return _read_one("daily", str(a.get("date") or ""))


def _tool_read_week_daily(a):
    _ML = mem_limits()
    try:
        d0 = datetime.strptime(str(a.get("startDate")), "%Y-%m-%d").date()
        d1 = datetime.strptime(str(a.get("endDate")), "%Y-%m-%d").date()
    except ValueError:
        return {"error": "日期格式不对，要 YYYY-MM-DD"}
    if (d1 - d0).days > 62:
        return {"error": "区间太长（最多 62 天），拆成几次读"}
    items, used = [], 0
    cur = d0
    while cur <= d1:
        md = notes.read_note("daily", notes.daily_name(cur))
        if notes.has_content(md):
            body, trunc, total = _clip(md, _ML["read"])
            if used + len(body) > _ML["total"]:
                items.append({"name": notes.daily_name(cur), "error": "超出本次读取预算，未读"})
            else:
                used += len(body)
                items.append({"kind": "daily", "name": notes.daily_name(cur),
                              "title": "%s 日报" % notes.daily_name(cur),
                              "content": body, "truncated": trunc, "totalCharacters": total})
        cur += timedelta(days=1)
    return {"results": items, "count": len(items),
            "range": [str(d0), str(d1)]}


def _tool_read_weekly(a):
    return _read_one("weekly", str(a.get("week") or ""))


def _tool_read_month_weekly(a):
    _ML = mem_limits()
    mo = str(a.get("month") or "")
    if not notes.valid_name("monthly", mo):
        return {"error": "月份格式不对，要 YYYY-MM"}
    items, used = [], 0
    for w in notes.weeks_overlapping_month(mo):
        md = notes.read_note("weekly", w)
        if not notes.has_content(md):
            continue
        body, trunc, total = _clip(md, _ML["read"])
        if used + len(body) > _ML["total"]:
            break
        used += len(body)
        items.append({"kind": "weekly", "name": w, "title": "%s 周报" % w,
                      "content": body, "truncated": trunc, "totalCharacters": total})
    return {"results": items, "count": len(items), "month": mo}


def _tool_read_month_report(a):
    return _read_one("monthly", str(a.get("month") or ""))


def _tool_resolve_iso_week(a):
    w = str(a.get("week") or "")
    try:
        d0, d1 = notes.iso_week_range(w)
    except ValueError as e:
        return {"week": w, "error": str(e)}
    return {"week": w, "startDate": str(d0), "endDate": str(d1)}


def _tool_read_stats(a):
    """本系统独有：把打卡/账单的客观数字给模型，让它能拿数据佐证"""
    mod = str(a.get("module") or "")
    try:
        d0 = datetime.strptime(str(a.get("from")), "%Y-%m-%d").date()
        d1 = datetime.strptime(str(a.get("to")), "%Y-%m-%d").date()
    except ValueError:
        return {"error": "日期格式不对，要 YYYY-MM-DD"}
    if mod == "check":
        try:
            dk = cached(CHECK, load_check)
            st = dk.get("settings") or {}
            rows = []
            for m in dk.get("months", []):
                for day in m.get("days", []):
                    ds = day.get("date") or ""
                    if ds and str(d0) <= ds <= str(d1):
                        s = _day_stat(day, st)
                        rows.append({"date": ds, "core": s["core"],
                                     "sleep": None if s["sleep"] is None else round(s["sleep"], 2),
                                     "judge": s["judge"], "sport": s["sport"],
                                     "screen": s["screen"]})
            if not rows:
                return {"module": "check", "range": [str(d0), str(d1)], "days": 0,
                        "note": "这段时间没有打卡记录"}
            ok_core = sum(1 for r in rows if r["core"] >= 4)
            sl = [r["sleep"] for r in rows if r["sleep"] is not None]
            return {"module": "check", "range": [str(d0), str(d1)], "days": len(rows),
                    "核心打卡满分天数": ok_core,
                    "平均核心完成": round(sum(r["core"] for r in rows) / len(rows), 2),
                    "有睡眠记录天数": len(sl),
                    "平均睡眠小时": round(sum(sl) / len(sl), 2) if sl else None,
                    "运动天数": sum(r["sport"] for r in rows),
                    "平均屏幕小时": round(sum(r["screen"] for r in rows) / len(rows), 1),
                    "明细": rows}
        except Exception as e:
            return {"error": "读取打卡数据失败：%s" % e}
    if mod == "bill":
        try:
            bl = cached(BILL, load_bill)
            rows = [r for r in bl.get("records", [])
                    if str(r.get("date") or "")[:10] and
                    str(d0) <= str(r["date"])[:10] <= str(d1) and r.get("stat") != "退回"]
            exp = sum(_f(r.get("exp")) for r in rows)
            inc = sum(_f(r.get("inc")) for r in rows)
            by = {}
            for r in rows:
                if _f(r.get("exp")) > 0:
                    by[r.get("cat") or "其他"] = by.get(r.get("cat") or "其他", 0) + _f(r["exp"])
            top = sorted(by.items(), key=lambda kv: -kv[1])[:8]
            return {"module": "bill", "range": [str(d0), str(d1)], "笔数": len(rows),
                    "支出": round(exp, 2), "收入": round(inc, 2),
                    "结余": round(inc - exp, 2),
                    "分类支出": [{"类别": k, "金额": round(v, 2)} for k, v in top]}
        except Exception as e:
            return {"error": "读取账单数据失败：%s" % e}
    return {"error": "module 只能是 check 或 bill"}


MEMORY_DISPATCH = {
    "get_current_date": _tool_get_current_date,
    "keyword_search": lambda a: _tool_search(a),
    "search_daily_notes": lambda a: _tool_search(a, "daily"),
    "search_weekly_notes": lambda a: _tool_search(a, "weekly"),
    "search_monthly_notes": lambda a: _tool_search(a, "monthly"),
    "read_daily_note": _tool_read_daily,
    "read_week_daily_notes": _tool_read_week_daily,
    "read_weekly_note": _tool_read_weekly,
    "read_month_weekly_notes": _tool_read_month_weekly,
    "read_month_report": _tool_read_month_report,
    "resolve_iso_week": _tool_resolve_iso_week,
    "read_stats": _tool_read_stats,
}


def _ai_tool_chat(cfg, messages, tools=None, timeout=180, scope="memory"):
    """带工具的一轮调用。返回 (ok, message 字典或错误信息, usage)。

    单独一个函数、不去改 _ai_chat：那个被药品/补全/分析/建议四处用着，
    json_mode 之类的默认值一改就会连累它们。
    """
    key = str(cfg.get("api_key") or "").strip()
    if not key:
        return False, "还没配置 API Key", None
    base = str(cfg.get("base_url") or DEFAULT_BASE).rstrip("/")
    # 回忆书单独选的模型优先；没选就跟「整理/生成」用同一个
    model = str(cfg.get("memory_model") or "").strip() or cfg.get("model") or AI_MODELS[0]
    payload = {"model": model, "messages": messages, "temperature": 0.3, "stream": False}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        hint = {401: "API Key 不对或已失效", 402: "账户余额不足",
                429: "请求太频繁或额度用尽"}.get(e.code, "")
        return False, "调用失败（HTTP %d）%s %s" % (e.code, hint, detail[:160]), None
    except urllib.error.URLError as e:
        return False, "连不上 %s：%s" % (base, e.reason), None
    except Exception as e:
        return False, "调用出错：%s" % e, None
    usage = data.get("usage")
    try:
        ai_usage_log(scope, model, usage)
    except Exception:
        pass
    try:
        return True, data["choices"][0]["message"], usage
    except Exception:
        return False, "返回格式看不懂：%s" % json.dumps(data, ensure_ascii=False)[:150], None


MEM_MAX_TURNS = 8


# ---------------- 回忆书：对话落盘（2.4.1） ----------------
#
# 起因：原来那版把消息只放在前端的 `MEM.messages` 里 —— 一刷新、一切标签页
# 就全没了。用户的原话是「回忆书没有对话历史吗，这个需要存下来」。
#
# ⚠ 建表没有另开「会话表」：会话列表要的东西（标题、最后一句、时间、几条）
#   全都能从消息里 group by 出来，而一个消息都没有的会话本来也不该存在。
#   多一张表就多一处要同步的状态。见 store.py 里 mem_msg 那段注释。

def _mem_new_chat():
    """新会话号。带时间戳是为了**排序稳定**；同一秒开两个就往后加一位。"""
    base = "c" + time.strftime("%Y%m%d-%H%M%S")
    cid, n = base, 1
    while store.q1("SELECT 1 FROM mem_msg WHERE chat=? LIMIT 1", (cid,)):
        cid = "%s-%d" % (base, n)
        n += 1
    return cid


def _mem_save(chat, role, content, trace=None):
    with store.tx("memory") as c:
        c.execute("INSERT INTO mem_msg(chat,ts,role,content,trace)"
                  " VALUES(?,?,?,?,?)",
                  (chat, time.strftime("%Y-%m-%d %H:%M:%S"), role, content or "",
                   json.dumps(trace or [], ensure_ascii=False)))


def mem_chats():
    """会话列表，最近说过的排最前。

    标题取**第一句用户提问**的前 28 个字 —— 不是取最后一句，因为
    「那再帮我看看上周的」这种追问当标题毫无信息量。"""
    rows = store.q("SELECT chat, COUNT(*) AS n, MAX(id) AS last_id,"
                   " MAX(ts) AS ts FROM mem_msg GROUP BY chat ORDER BY last_id DESC")
    out = []
    for r in rows:
        first = store.q1("SELECT content FROM mem_msg WHERE chat=? AND role='user'"
                         " ORDER BY id LIMIT 1", (r["chat"],))
        title = "（没有提问）"
        if first and first["content"]:
            # 提问里带着「[发送时间：…]」那段，标题里要去掉
            t = re.sub(r"\s*\[发送时间：.*?\]\s*$", "", first["content"], flags=re.S)
            t = " ".join(t.split())
            title = t[:28] + ("…" if len(t) > 28 else "")
        out.append({"chat": r["chat"], "n": r["n"], "title": title,
                    "ts": r["ts"] or ""})
    return out


def mem_history(body):
    """某个会话的全部消息。不传 chat 就给最近那个。"""
    chat = str((body or {}).get("chat") or "")
    if not chat:
        r = store.q1("SELECT chat FROM mem_msg ORDER BY id DESC LIMIT 1")
        chat = r["chat"] if r else ""
    if not chat:
        return True, "还没有对话", {"chat": "", "messages": []}
    rows = store.q("SELECT ts,role,content,trace FROM mem_msg WHERE chat=? ORDER BY id",
                   (chat,))
    msgs = []
    for r in rows:
        try:
            tr = json.loads(r["trace"] or "[]")
        except Exception:
            tr = []
        msgs.append({"ts": r["ts"], "role": r["role"], "content": r["content"],
                     "trace": tr})
    return True, "%d 条" % len(msgs), {"chat": chat, "messages": msgs}


def mem_clear(body):
    """清掉一个会话。⚠ 只删对话，**不碰任何笔记** —— 界面上要说清楚。"""
    chat = str((body or {}).get("chat") or "")
    if not chat:
        return False, "没说清要清哪个会话"
    with store.tx("memory") as c:
        n = c.execute("DELETE FROM mem_msg WHERE chat=?", (chat,)).rowcount
    return True, "清掉了 %d 条" % n, {"chat": chat, "n": n}


def mem_clear_all():
    """所有会话一起清（设置里的「清空回忆书对话」用）。"""
    with store.tx("memory") as c:
        n = c.execute("DELETE FROM mem_msg").rowcount
    return True, "清掉了 %d 条对话" % n, {"n": n}


# ---------------- 待办 → 日历（.ics）（2.4.5） ----------------
#
# 用户挑的做法：**每个待办一个「加到日历」按钮**，只同步未完成的，
# 日程带**当天和前一天各一次提醒**。
#
# 为什么是 .ics 文件而不是订阅地址：这台机器上的程序不一定一直开着，
# 而 Windows 自带的日历**不支持**本地 webcal 订阅地址。生成一个文件、
# 双击导入，是唯一"不依赖程序在跑"的做法。
#
# ⚠ UID 必须**跟着待办走**（`xiaoxu-todo-<row>@...`），而且每次生成都一模一样。
#   用户改了待办重新加一次时，日历认得出"是同一条"，会更新而不是
#   再插一条重复的。UID 里放时间戳就没有这个效果了。

BACKSLASH = chr(92)


def _ics_esc(v):
    """TEXT 值里的 逗号 / 分号 / 反斜杠 / 换行 都要转义（RFC 5545 §3.3.11）。

    ⚠ 不转义的话，备注里打一个逗号就能把这条日程拆坏 ——
      而"买牙膏,顺便买洗发水"这种写法太常见了。"""
    s2 = str(v or "")
    s2 = s2.replace(BACKSLASH, BACKSLASH * 2)
    s2 = s2.replace(";", BACKSLASH + ";").replace(",", BACKSLASH + ",")
    return s2.replace("\r\n", BACKSLASH + "n").replace("\n", BACKSLASH + "n") \
             .replace("\r", BACKSLASH + "n")


def _ics_fold(line):
    """按 75 **字节**折行。

    ⚠ 是字节不是字符 —— 中文一个字在 UTF-8 里占 3 字节，按"75 个字符"折
      会折出 200 多字节的行，严格的日历程序直接拒收整个文件。
      续行以**一个空格**开头（这是规范，不是缩进）。"""
    b = line.encode("utf-8")
    if len(b) <= 73:
        return line
    out, cur = [], b""
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > 73:
            out.append(cur.decode("utf-8"))
            cur = b" " + cb               # 续行那一个空格正好占掉一个字节
        else:
            cur += cb
    if cur.strip():
        out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def todo_ics(body):
    """把一条待办写成 .ics，返回文件路径。

    ⚠ 只写文件，**不碰待办本身** —— 加不加日历是"提醒方式"，
      不是"这件事的状态"。导出了一次就被标成干完了，那是灾难。

    ⚠ 失败时也要回 **3 元组**（`False, msg, None`）。路由那边其实兼容 2 元组，
      但项目自己的规矩是"一律 3 元组"，破例的下场当场就看到了：
      直接调这个函数做单测时 `ok, msg, _ = todo_ics(...)` 直接
      ValueError: not enough values to unpack。"""
    row = body.get("row")
    # ⚠ 待办表里**没有 done 列**，完成状态是 `stat`（'已完成' / '未完成'）。
    #   第一版按 done 查，SQLite 直接报 no such column —— 而且因为路由那边
    #   把异常吞成了 500，前端只看到"服务器错误"，看不到真正的原因。
    t = store.q1("SELECT id,stat,item,cat,due,pri,note FROM todo WHERE id=?", (row,))
    if not t:
        return False, "找不到这条待办"
    if str(t["stat"] or "").strip() == "已完成":
        return False, "这条已经做完了。日历是拿来提醒「还要做什么」的，做完的就不往里放了。", None
    due = str(t["due"] or "").strip()
    if not due:
        return False, ("这条还没填截止日期 —— 日历里没法安放一个不知道哪天做的事。"
                       "先在「截止日期」里填一个，再点这个按钮。"), None
    d = to_date(due)
    if not d:
        return False, "截止日期看不懂：%s" % due, None
    d0 = d.strftime("%Y%m%d")
    d1 = (d + timedelta(days=1)).strftime("%Y%m%d")   # 全天事件的 DTEND 是**次日**
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    title = t["item"] or "待办"
    desc = "来自小煦拾简的待办。\n类别：%s　优先级：%s" % (t["cat"] or "", t["pri"] or "")
    if str(t["note"] or "").strip():
        desc += "\n备注：" + str(t["note"])

    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//小煦拾简//待办//CN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        "UID:xiaoxu-todo-%s@xiaoxu.local" % row,
        "DTSTAMP:" + stamp,
        "DTSTART;VALUE=DATE:" + d0,
        "DTEND;VALUE=DATE:" + d1,
        "SUMMARY:" + _ics_esc(title),
        "DESCRIPTION:" + _ics_esc(desc),
        "TRANSP:TRANSPARENT",              # 全天事件不该把日历显示成"忙碌"
    ]
    # 两次提醒。全天事件的 DTSTART 是当天 00:00，所以：
    #   PT9H   → 当天 09:00
    #   -PT15H → 前一天 09:00（当天 0 点往前 15 小时）
    for trig, label in (("-PT15H", "明天到期，今天先准备"),
                        ("PT9H", "今天到期")):
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:" + trig,
                  "DESCRIPTION:" + _ics_esc("%s：%s" % (label, title)),
                  "END:VALARM"]
    lines += ["END:VEVENT", "END:VCALENDAR"]

    text = "\r\n".join(_ics_fold(x) for x in lines) + "\r\n"
    # 文件名：日期 + 事项。文件名里不能有的字符换成下划线；太长就截断
    safe = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", title).strip(" .")[:24] or "待办"
    name = "待办-%s-%s.ics" % (d0, safe)
    out = os.path.join(DATA_ROOT, "_导出", "日历")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return True, "写好了", {"path": path, "name": name, "dir": out,
                            "title": title, "due": due}


# ---------------- 牛马时钟（2.4.1） ----------------
#
# 用户要的是 SpringNote 桌面小组件那种：进度条 + 大数字 + 速率 + 计时。
# 我们这边对应的是「日薪 ÷ 每天几小时 = 时薪」，实时算今天赚了多少。
#
# ⚠ 必须有「几点上班」这个设置项。原来的算法是拿"从今天 0 点到现在"
#   当已工作时长，早上七点打开会显示已经赚了七个小时的钱。
#   加上班时间之后：早于上班时间 = 0，超时下班 = 封顶在每天工时。

def _hhmm(s, dflt=(9, 0)):
    m = re.match(r"^\s*(\d{1,2})\s*[:：]\s*(\d{1,2})", str(s or ""))
    if not m:
        return dflt
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return dflt
    return h, mi


# 等级表（2.4.1）：按**累计工作小时**划分。
# ⚠ 名字是自嘲用的，跟用户要的"牛马"一个调子 —— 但阶梯得是真的：
#   每一级的门槛都在下面这张表里，改这里就够了，别在别处再写一份。
CLOCK_LEVELS = [
    (0,    "实习生"),      # 0 小时起步
    (20,   "试用期"),
    (60,   "正式工"),
    (140,  "熟练工"),
    (300,  "老员工"),
    (600,  "骨干"),
    (1000, "卷王"),
    (2000, "牛马之王"),
]


def clock_level(total_min):
    """累计分钟 → (等级序号, 名字, 本级进度 0~1, 下一级还差几分钟)。"""
    h = total_min / 60.0
    idx = 0
    for i, (need, _n) in enumerate(CLOCK_LEVELS):
        if h >= need:
            idx = i
        else:
            break
    name = CLOCK_LEVELS[idx][1]
    if idx + 1 >= len(CLOCK_LEVELS):
        return idx + 1, name, 1.0, 0          # 到顶了
    lo, hi = CLOCK_LEVELS[idx][0], CLOCK_LEVELS[idx + 1][0]
    pct = (h - lo) / (hi - lo) if hi > lo else 1.0
    return idx + 1, name, max(0.0, min(1.0, pct)), int(round((hi - h) * 60))


def clock_state():
    st = settings_load()
    wage = float(st.get("clock_wage") or 0)
    hours = float(st.get("clock_hours") or 8) or 8.0
    if hours <= 0:
        hours = 8.0
    sh, sm = _hhmm(st.get("clock_start"), (9, 0))
    now = datetime.now()
    start_min = sh * 60 + sm
    now_min = now.hour * 60 + now.minute
    total_min = hours * 60
    done = max(0.0, min(float(now_min - start_min), total_min))
    hourly = wage / hours if wage > 0 else 0.0
    earned = hourly * done / 60.0
    before = now_min < start_min
    over = now_min - start_min >= total_min
    # 记一笔今天干到哪儿了（取当天最大值 —— 下午干得多，晚上再问不该退回早上）
    if wage > 0:
        day = now.strftime("%Y-%m-%d")
        try:
            with store.tx("clock") as c:
                c.execute("INSERT INTO clock_log(day,minutes) VALUES(?,?)"
                          " ON CONFLICT(day) DO UPDATE SET minutes=MAX(minutes,excluded.minutes)",
                          (day, int(done)))
        except Exception as e:
            print("[时钟] 记工时报错（不影响使用）：%s" % e)
    try:
        total_min = int(store.q1("SELECT COALESCE(SUM(minutes),0) AS m FROM clock_log")["m"] or 0)
    except Exception:
        total_min = int(done)
    lv, lvname, lvpct, lv_left = clock_level(total_min)
    return {
        "level": lv, "level_name": lvname, "level_pct": round(lvpct, 4),
        "level_left_min": lv_left, "total_min": total_min,
        "total_hours": round(total_min / 60.0, 1),
        "on": wage > 0,                       # 没填日薪就整块不显示
        "wage": round(wage, 2), "hours": hours,
        "start": "%02d:%02d" % (sh, sm),
        "hourly": round(hourly, 2),
        "earned": round(earned, 2),
        "done_min": int(done),
        # 「今天第几个小时」—— 进度条上面那行字用
        "hour_no": min(int(hours), int(done // 60) + 1) if done < total_min else int(hours),
        "pct": round(done / total_min, 4) if total_min else 0.0,
        "before": before,                     # 还没上班
        "over": over,                         # 已经到点了
        "day": now.strftime("%Y-%m-%d"),
        # 顺手把主题带上：桌面小时钟是个独立窗口，它没法读主窗口的设置，
        # 而 /api/settings 是要令牌的。这里一起给，省一次调用、也省一个坑。
        "theme": st.get("theme") or "auto",
        "palette": st.get("palette") or "素纸",
    }


def memory_chat(body):
    """回忆书一轮对话。

    没有配 Key 时不报错、也不假装能回答 —— 退回纯本地检索，把命中的原文摆出来。
    SpringNote 也是这个行为：搜索和读取在没有模型时照样可用。
    """
    _ML = mem_limits()

    # ⚠ 2.4.1 起：**历史从库里读**，前端只发一个会话号 + 这一句问题。
    #   以前是前端把整个 messages 数组发上来 —— 那样刷新一次上下文就没了，
    #   而且每问一句都要把前面全部重传一遍。
    #   留一条 `messages` 的后路：万一还连着旧版前端，别直接坏掉。
    chat = str(body.get("chat") or "")
    q = str(body.get("question") or "").strip()
    msgs = body.get("messages")
    if not q and isinstance(msgs, list) and msgs:
        for m in reversed(msgs):
            if m.get("role") == "user":
                q = str(m.get("content") or "")
                break
        msgs = None
    if not q:
        return False, "没收到问题"
    if not chat:
        chat = _mem_new_chat()
    # 有了会话号就从库里把前面的对话捞出来当上下文
    if msgs is None:
        msgs = mem_history({"chat": chat})[2]["messages"]
    cfg = ai_config_load()

    if not str(cfg.get("api_key") or "").strip():
        kws = [s for s in re.split(r"[\s，。？！、,.\?!；;：:]+", q) if len(s) >= 2][:6]
        hits = notes.search(kws) if kws else []
        txt = "**还没配置 API Key**，现在只能做本地检索，不能生成分析。\n\n去「⚙ 设置」里填上就能问答了。\n"
        if hits:
            txt += "\n按关键词 %s 找到这些记录：\n\n" % "、".join("`%s`" % k for k in kws)
            for h in hits[:10]:
                txt += "- **%s** — %s\n" % (h["title"], h["snippet"][:120].replace("\n", " "))
        else:
            txt += "\n（也没检索到相关记录）"
        _mem_save(chat, "user", q)
        _mem_save(chat, "ai", txt)
        return True, "本地检索", {"chat": chat, "answer": txt, "trace": [],
                                  "local_only": True}

    convo = [{"role": "system", "content": prompt_override("memory", MEMORY_SYS_PROMPT).replace("{who}", address_clause())
              + profile_hint()}]
    for m in msgs:
        role = m.get("role")
        if role in ("user", "assistant") and m.get("content"):
            convo.append({"role": role, "content": str(m["content"])})

    trace = []
    for _turn in range(_ML["turns"]):
        ok, msg, _u = _ai_tool_chat(cfg, convo, MEMORY_TOOLS)
        if not ok:
            return False, msg
        calls = msg.get("tool_calls") or []
        if not calls:
            ans = msg.get("content") or ""
            _mem_save(chat, "user", q)
            _mem_save(chat, "ai", ans, trace)
            return True, "ok", {"chat": chat, "answer": ans, "trace": trace}
        # 把 assistant 那轮原样带回消息历史，否则 tool 消息没有对应的 tool_call_id
        convo.append({"role": "assistant", "content": msg.get("content") or "",
                      "tool_calls": calls})
        for tc in calls:
            fn = (tc.get("function") or {})
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except (ValueError, TypeError):
                args = {}
            fnimpl = MEMORY_DISPATCH.get(name)
            try:
                result = fnimpl(args) if fnimpl else {"error": "没有这个工具：%s" % name}
            except Exception as e:
                result = {"error": "工具执行失败：%s" % e}
            trace.append({"tool": name, "args": args, "result": result})
            convo.append({"role": "tool", "tool_call_id": tc.get("id") or name,
                          "content": json.dumps(result, ensure_ascii=False)})

    # 轮数用完了：最后再来一次不带工具的，逼它用手上的材料作答
    ok, msg, _u = _ai_tool_chat(cfg, convo + [
        {"role": "user", "content": "（检索轮数已达上限，请直接根据上面已有的材料回答，"
                                    "并说明哪些部分可能不完整。）"}], tools=None)
    if not ok:
        return False, msg
    ans2 = msg.get("content") or ""
    _mem_save(chat, "user", q)
    _mem_save(chat, "ai", ans2, trace)
    return True, "ok", {"chat": chat, "answer": ans2,
                        "trace": trace, "hit_turn_limit": True}


def memory_tools_list(body=None):
    """给前端展示「回忆书能查什么」用的"""
    _ML = mem_limits()          # ⚠ 这个函数也要 —— 漏了就是 NameError，
    #                             而它只在「点了回忆书的问号」时才炸，
    #                             平时完全看不出来（自测抓到的）
    return {"tools": [{"name": t["function"]["name"],
                       "desc": t["function"]["description"]} for t in MEMORY_TOOLS],
            "maxTurns": _ML["turns"]}


# ================================================================
# ⑤ 账单类别管理
# ================================================================
# 「汇总」表里类别区是固定行，下面各区块又按绝对地址互相引用，
# 所以类别数一变、行号一动，公式/图表/预算全得跟着挪。
# 解法：一次性迁移到「固定容量」骨架（支出 30 行、收入 10 行），
# 空位行隐藏（图表 plotVisOnly=1，隐藏行不参与绘图），此后行号永不再动。
CAP_EXP, CAP_INC = 30, 10
CAT_RESERVED = {"合计", "支出合计", "收入合计", "月份", "项目", "类别", "账户"}
PAYS_DEFAULT = ["支付宝", "微信", "农业银行卡", "农商银行卡", "现金"]


def summary_layout(n_exp=CAP_EXP, n_inc=CAP_INC, n_mon=6, n_acc=5):
    """推导「汇总」表各区块行号（已用 17/5/6/5 对真实文件做过黄金校验）"""
    L = {"title": 1, "sub": 2, "kpi": 3, "exp_sec": 5, "exp_hdr": 6, "exp0": 7}
    L["exp1"] = 6 + n_exp
    L["exp_tot"] = 7 + n_exp
    L["inc_sec"] = L["exp_tot"] + 2
    L["inc_hdr"] = L["inc_sec"] + 1
    L["inc0"] = L["inc_sec"] + 2
    L["inc1"] = L["inc0"] + n_inc - 1
    L["inc_tot"] = L["inc1"] + 1
    L["grp_sec"] = L["inc_tot"] + 2
    L["grp_hdr"] = L["grp_sec"] + 1
    L["grp0"] = L["grp_sec"] + 2
    L["grp1"] = L["grp0"] + 3
    L["mon_sec"] = L["grp1"] + 2
    L["mon_hdr"] = L["mon_sec"] + 1
    L["mon0"] = L["mon_sec"] + 2
    L["mon1"] = L["mon0"] + n_mon - 1
    L["mon_tot"] = L["mon1"] + 1
    L["acc_sec"] = L["mon_tot"] + 2
    L["acc_hdr"] = L["acc_sec"] + 1
    L["acc0"] = L["acc_hdr"] + 1
    L["acc1"] = L["acc0"] + n_acc - 1
    L["acc_tot"] = L["acc1"] + 1
    L["av_sec"] = L["acc_tot"] + 2
    L["av_hdr"] = L["av_sec"] + 1
    L["av0"] = L["av_hdr"] + 1
    L["av1"] = L["av0"] + 2
    L["last"] = L["av1"]
    return L


def summary_read_cats(ws):
    """读回类别：支出区 = 从第 7 行到「支出合计」上一行；收入区同理"""
    exp, inc = [], []
    exp_tot = inc_tot = None
    for r in range(1, ws.max_row + 3):
        v = str(ws.cell(r, 1).value or "").strip()
        if v == "支出合计":
            exp_tot = r
        elif v == "收入合计":
            inc_tot = r
    if exp_tot:
        for r in range(7, exp_tot):
            v = str(ws.cell(r, 1).value or "").strip()
            if v:
                exp.append(v)
    if inc_tot:
        # 收入数据行从「支出合计」往下数第 4 行开始（+2 标题、+3 表头、+4 首数据）
        start = (exp_tot + 4) if exp_tot else 28
        for r in range(start, inc_tot):
            v = str(ws.cell(r, 1).value or "").strip()
            if v:
                inc.append(v)
    return exp, inc


def _snap_styles(ws, L):
    """按角色抓样式模板（都取自非合并格）"""
    T = {}
    role_rows = {
        "title": L["title"], "sub": L["sub"], "kpi": L["kpi"],
        "exp_sec": L["exp_sec"], "exp_hdr": L["exp_hdr"],
        "data_a": L["exp0"], "data_b": L["exp0"] + 1,
        "total": L["exp_tot"], "inc_sec": L["inc_sec"], "inc_hdr": L["inc_hdr"],
        "grp_sec": L["grp_sec"], "grp_hdr": L["grp_hdr"],
        "mon_sec": L["mon_sec"], "mon_hdr": L["mon_hdr"], "mon": L["mon0"],
        "acc_sec": L["acc_sec"], "acc_hdr": L["acc_hdr"], "acc": L["acc0"],
        "av_sec": L["av_sec"], "av_hdr": L["av_hdr"], "av": L["av0"],
        "blank": 4,
    }
    for role, r in role_rows.items():
        T[role] = [copy.copy(ws.cell(r, c)._style) for c in range(1, 7)]
    T["grp"] = [[copy.copy(ws.cell(r, c)._style) for c in range(1, 7)]
                for r in range(L["grp0"], L["grp1"] + 1)]
    T["height"] = {r: ws.row_dimensions[r].height for r in
                   (1, 2, 3, L["exp_sec"], L["exp_hdr"], L["mon_hdr"],
                    L["grp_hdr"], L["acc_hdr"], L["av_hdr"])}
    return T


def _put(ws, r, c, val, style):
    cell = ws.cell(r, c)
    cell.value = val
    if style is not None:
        cell._style = copy.copy(style)


def build_summary(wb, exp_cats, inc_cats, budget=None, months=None, accounts=None):
    """按类别清单重建「汇总」表。只用于首次迁移到固定容量（以及将来扩容）。
    调用方负责先备份、再断言、最后 save_atomic。"""
    ws = wb["汇总"]
    old_exp, old_inc = summary_read_cats(ws)
    old_L = summary_layout(len(old_exp), len(old_inc))
    T = _snap_styles(ws, old_L)
    if months is None:
        months = [str(ws.cell(r, 1).value) for r in range(old_L["mon0"], old_L["mon1"] + 1)
                  if ws.cell(r, 1).value]
    if accounts is None:
        accounts = [str(ws.cell(r, 1).value) for r in range(old_L["acc0"], old_L["acc1"] + 1)
                    if ws.cell(r, 1).value]
    if budget is None:
        budget = {}
    L = summary_layout(CAP_EXP, CAP_INC, len(months), len(accounts))

    for rng in list(ws.merged_cells.ranges):        # ① 先拆合并，否则 MergedCell 只读
        ws.unmerge_cells(str(rng))
    for r in range(1, old_L["last"] + 1):           # ② 清空
        ws.row_dimensions[r].height = None
        ws.row_dimensions[r].hidden = False
        for c in range(1, 7):
            _put(ws, r, c, None, T["blank"][c - 1])

    def row(r, role, vals):
        for i, v in enumerate(vals):
            _put(ws, r, i + 1, v, T[role][i])

    # 顶部
    row(L["title"], "title", ["%s · 记账汇总" % SEMESTER])
    row(L["sub"], "sub", ["全部数字由公式自动统计，只需在「记录」表记账；"
                          "核销状态填「退回」的行不计入任何统计"])
    row(L["kpi"], "kpi", ["总收入", "=B%d" % L["inc_tot"], "总支出", "=B%d" % L["exp_tot"],
                          "结余", "=B%d-B%d" % (L["inc_tot"], L["exp_tot"])])

    # ① 支出类别
    row(L["exp_sec"], "exp_sec", ["  ① 各支出类别汇总"])
    row(L["exp_hdr"], "exp_hdr", ["类别", "总支出", "占比", "笔数", "笔均"])
    bt = L["exp_tot"]
    for i in range(CAP_EXP):
        r = L["exp0"] + i
        name = exp_cats[i] if i < len(exp_cats) else ""
        role = "data_a" if i % 2 == 0 else "data_b"
        row(r, role, [name,
                      '=SUMIFS(记录!$F:$F,记录!$C:$C,$A%d,记录!$J:$J,"<>退回")' % r,
                      '=IF($B$%d=0,"",B%d/$B$%d)' % (bt, r, bt),
                      '=COUNTIFS(记录!$C:$C,$A%d,记录!$F:$F,">0",记录!$J:$J,"<>退回")' % r,
                      '=IF(D%d=0,"",B%d/D%d)' % (r, r, r)])
    row(L["exp_tot"], "total", ["支出合计",
                                "=SUM(B%d:B%d)" % (L["exp0"], L["exp1"]),
                                '=IF($B$%d=0,"",1)' % bt,
                                "=SUM(D%d:D%d)" % (L["exp0"], L["exp1"]),
                                '=IF(D%d=0,"",B%d/D%d)' % (bt, bt, bt)])

    # ② 收入类别
    row(L["inc_sec"], "inc_sec", ["  ② 各收入类别汇总"])
    row(L["inc_hdr"], "inc_hdr", ["类别", "总收入", "占比", "笔数", "笔均"])
    it = L["inc_tot"]
    for i in range(CAP_INC):
        r = L["inc0"] + i
        name = inc_cats[i] if i < len(inc_cats) else ""
        role = "data_a" if i % 2 == 0 else "data_b"
        row(r, role, [name,
                      '=SUMIFS(记录!$E:$E,记录!$C:$C,$A%d,记录!$J:$J,"<>退回")' % r,
                      '=IF($B$%d=0,"",B%d/$B$%d)' % (it, r, it),
                      '=COUNTIFS(记录!$C:$C,$A%d,记录!$E:$E,">0",记录!$J:$J,"<>退回")' % r,
                      '=IF(D%d=0,"",B%d/D%d)' % (r, r, r)])
    row(L["inc_tot"], "total", ["收入合计",
                                "=SUM(B%d:B%d)" % (L["inc0"], L["inc1"]),
                                '=IF($B$%d=0,"",1)' % it,
                                "=SUM(D%d:D%d)" % (L["inc0"], L["inc1"]),
                                '=IF(D%d=0,"",B%d/D%d)' % (it, it, it)])

    # ③ 团购
    row(L["grp_sec"], "grp_sec", ["  ③ 团购 / 核销情况（退回不计入支出）"])
    row(L["grp_hdr"], "grp_hdr", ["项目", "金额", "说明"])
    g0 = L["grp0"]
    grp = [("待核销团购", '=SUMIFS(记录!$F:$F,记录!$I:$I,"是",记录!$J:$J,"待核销")',
            "钱已付、券还没用 → 先计入支出"),
           ("已核销团购", '=SUMIFS(记录!$F:$F,记录!$I:$I,"是",记录!$J:$J,"核销")',
            "已经用掉了 → 计入支出"),
           ("计入支出的团购合计", "=B%d+B%d" % (g0, g0 + 1), "上面两项之和"),
           ("已退回（不计入统计）", '=SUMIFS(记录!$F:$F,记录!$I:$I,"是",记录!$J:$J,"退回")',
            "退款到账，整行从所有统计里剔除")]
    for i, (a, b, c) in enumerate(grp):
        for j, v in enumerate((a, b, c)):
            _put(ws, g0 + i, j + 1, v, T["grp"][i][j])

    # ④ 每月
    row(L["mon_sec"], "mon_sec", ["  ④ 每月收支汇总（预算可自行修改）"])
    row(L["mon_hdr"], "mon_hdr", ["月份", "总收入", "总支出", "结余", "预算", "超支提醒"])
    for i, m in enumerate(months):
        r = L["mon0"] + i
        row(r, "mon", [m,
                       '=SUMIFS(记录!$E:$E,记录!$H:$H,$A%d,记录!$J:$J,"<>退回")' % r,
                       '=SUMIFS(记录!$F:$F,记录!$H:$H,$A%d,记录!$J:$J,"<>退回")' % r,
                       "=B%d-C%d" % (r, r),
                       budget.get(m),                       # 预算原样搬过来，没有就留空
                       '=IF(E%d="","",IF(C%d>E%d,"超支","正常"))' % (r, r, r)])
    row(L["mon_tot"], "total", ["合计",
                                "=SUM(B%d:B%d)" % (L["mon0"], L["mon1"]),
                                "=SUM(C%d:C%d)" % (L["mon0"], L["mon1"]),
                                "=SUM(D%d:D%d)" % (L["mon0"], L["mon1"]),
                                "=SUM(E%d:E%d)" % (L["mon0"], L["mon1"]), None])

    # ⑤ 账户
    row(L["acc_sec"], "acc_sec", ["  ⑤ 各资金账户结余"])
    row(L["acc_hdr"], "acc_hdr", ["账户", "总收入", "总支出", "结余"])
    for i, a in enumerate(accounts):
        r = L["acc0"] + i
        row(r, "acc", [a,
                       '=SUMIFS(记录!$E:$E,记录!$G:$G,$A%d,记录!$J:$J,"<>退回")' % r,
                       '=SUMIFS(记录!$F:$F,记录!$G:$G,$A%d,记录!$J:$J,"<>退回")' % r,
                       "=B%d-C%d" % (r, r)])
    row(L["acc_tot"], "total", ["合计",
                                "=SUM(B%d:B%d)" % (L["acc0"], L["acc1"]),
                                "=SUM(C%d:C%d)" % (L["acc0"], L["acc1"]),
                                "=SUM(D%d:D%d)" % (L["acc0"], L["acc1"])])

    # ⑥ 可动用
    row(L["av_sec"], "av_sec", ["  ⑥ 可动用资金"])
    row(L["av_hdr"], "av_hdr", ["项目", "金额"])
    row(L["av0"], "av", ["当前账上结余（总）", "=D%d" % L["acc_tot"]])
    row(L["av0"] + 1, "av", ["待付周边尾款（将扣）", "=周边尾款!$H$2"])
    row(L["av1"], "av", ["除去周边尾款可动用资金", "=B%d-B%d" % (L["av0"], L["av0"] + 1)])

    # 合并区
    for rng in ("A1:E1", "A2:E2", "A%d:E%d" % (L["exp_sec"], L["exp_sec"]),
                "A%d:E%d" % (L["inc_sec"], L["inc_sec"]),
                "A%d:E%d" % (L["grp_sec"], L["grp_sec"]),
                "A%d:F%d" % (L["mon_sec"], L["mon_sec"]),
                "A%d:E%d" % (L["acc_sec"], L["acc_sec"]),
                "A%d:E%d" % (L["av_sec"], L["av_sec"])):
        ws.merge_cells(rng)
    for i in range(4):
        ws.merge_cells("C%d:E%d" % (g0 + i, g0 + i))

    # 行高
    for r, h in T["height"].items():
        if h:
            ws.row_dimensions[r].height = h

    # 空位行隐藏（图表 plotVisOnly=1，隐藏行不会出现在图上）
    for i in range(len(exp_cats), CAP_EXP):
        ws.row_dimensions[L["exp0"] + i].hidden = True
    for i in range(len(inc_cats), CAP_INC):
        ws.row_dimensions[L["inc0"] + i].hidden = True

    # 条件格式：超支提醒 + 账户/可动用负数标红
    ws.conditional_formatting = ConditionalFormattingList()
    for i in range(len(months)):
        r = L["mon0"] + i
        for op, val, fill, fg in (("equal", '"超支"', "FFC7CE", "9C0006"),
                                  ("equal", '"正常"', "C6EFCE", "1E7145")):
            ws.conditional_formatting.add("F%d" % r, CellIsRule(
                operator=op, formula=[val], font=Font(color=fg),
                fill=PatternFill("solid", start_color=fill)))
    for i in range(len(accounts)):
        ws.conditional_formatting.add("D%d" % (L["acc0"] + i), CellIsRule(
            operator="lessThan", formula=["0"], font=Font(bold=True, color="9C0006")))
    ws.conditional_formatting.add("B%d" % L["av1"], CellIsRule(
        operator="lessThan", formula=["0"], font=Font(bold=True, size=14, color="C00000")))

    _rebuild_charts(wb, L)
    return L


def _rebuild_charts(wb, L):
    """「图表」sheet 的辅助列与三个图表的引用跟着新行号走"""
    ws = wb["图表"]
    last = L["exp0"] + CAP_EXP - 1
    for i in range(CAP_EXP):
        r, src = 3 + i, L["exp0"] + i
        ws.cell(r, 19).value = '=IF(汇总!$A%d="",0,汇总!$B%d+ROW()/1000000)' % (src, src)
    for i in range(8):
        r = 3 + i
        ws.cell(r, 16).value = ('=IF(Q%d<=0,"",INDEX(汇总!$A$%d:$A$%d,'
                                'MATCH(LARGE($S$3:$S$%d,ROW()-2),$S$3:$S$%d,0)))'
                                % (r, L["exp0"], last, last, last))
        ws.cell(r, 17).value = "=LARGE($S$3:$S$%d,ROW()-2)" % last
    ws.cell(11, 16).value = "其他小额"
    ws.cell(11, 17).value = "=SUM(汇总!$B$%d:$B$%d)-SUM(Q3:Q10)" % (L["exp0"], last)

    def set_ref(ch, i, val=None, cat=None, tx=None):
        s = ch.series[i]
        if val:
            s.val.numRef.f = val
        if cat:
            if s.cat.numRef is not None:
                s.cat.numRef.f = cat
            elif s.cat.strRef is not None:
                s.cat.strRef.f = cat
        if tx and s.tx and s.tx.strRef:
            s.tx.strRef.f = tx

    ch = ws._charts
    if len(ch) >= 3:
        set_ref(ch[1], 0, val="汇总!$B$%d:$B$%d" % (L["inc0"], L["inc1"]),
                cat="汇总!$A$%d:$A$%d" % (L["inc0"], L["inc1"]),
                tx="汇总!$B$%d" % (L["inc_hdr"]))
        for i, col in enumerate("BC"):
            set_ref(ch[2], i, val="汇总!$%s$%d:$%s$%d" % (col, L["mon0"], col, L["mon1"]),
                    cat="汇总!$A$%d:$A$%d" % (L["mon0"], L["mon1"]),
                    tx="汇总!$%s$%d" % (col, L["mon_hdr"]))


def migrate_cats(ws_rec, mapping, fallback_exp="其他", fallback_inc="其他收入"):
    """把「记录」C 列的历史类别改名/归并。mapping: {旧名: 新名 或 None(删除)}"""
    n = 0
    for r in range(2, 1004):            # 不 break：表里可能有空行空洞
        c = ws_rec.cell(r, 3)
        v = c.value
        if v in mapping:
            c.value = mapping[v] or fallback_exp
            n += 1
    return n


def set_cat_dv(ws_rec, cats):
    """同步「记录」C 列的下拉列表"""
    s = '"' + ",".join(cats) + '"'
    if len(s) > 250:
        raise ValueError("类别太多，下拉放不下（%d 字符）" % len(s))
    hit = 0
    for dv in ws_rec.data_validations.dataValidation:
        if dv.type == "list" and str(dv.sqref).split(":")[0] == "C2":
            dv.formula1 = s
            hit += 1
    return hit


def cats_get(body=None, sem=None):
    exp, inc = _cats_of(sem)
    return {"exp": exp, "inc": inc, "cap_exp": CAP_EXP, "cap_inc": CAP_INC,
            "reserved": sorted(CAT_RESERVED)}


def _validate_cats(exp, inc, renames):
    if not exp or not inc:
        return "支出和收入类别都不能为空"
    if exp[-1] != "其他":
        return "支出类别必须保留「其他」作为兜底（放在最后）"
    if "其他收入" not in inc:
        return "收入类别必须保留「其他收入」作为兜底"
    for c in list(exp) + list(inc):
        if not c or not c.strip():
            return "类别名不能为空"
        if any(ch in c for ch in ',"，'):
            return "类别名不能包含逗号或引号：%s" % c
        if c in CAT_RESERVED:
            return "「%s」是保留名，不能用作类别" % c
    if len(set(exp)) != len(exp):
        return "支出类别有重复"
    if len(set(inc)) != len(inc):
        return "收入类别有重复"
    if len(exp) > CAP_EXP or len(inc) > CAP_INC:
        return "类别数超出上限（支出 %d / 收入 %d）" % (CAP_EXP, CAP_INC)
    for old, new in (renames or {}).items():
        if old in ("其他", "其他收入"):
            return "「%s」不能改名或删除（兜底类别）" % old
        if new and new in CAT_RESERVED:
            return "「%s」是保留名" % new
    return None


def cats_save(body):
    """保存类别：校验 → 改历史记录里的旧名字 → 写库。

    以前这里要重建「汇总」表、重排下拉、重建图表引用，然后一口气断言
    图表没少、预算搬对了、没有 #REF! —— 整整一页。那些事的**唯一目的是
    让 Excel 那张表自己还算得对**。类别搬到库里就只是 cat 表里几行，
    正事只剩一件：历史流水里引用过旧名字的，得跟着改。
    """
    exp = [str(x).strip() for x in (body.get("exp") or []) if str(x).strip()]
    inc = [str(x).strip() for x in (body.get("inc") or []) if str(x).strip()]
    renames = body.get("renames") or {}
    err = _validate_cats(exp, inc, renames)
    if err:
        return False, err
    sem = _sem()
    old_exp, old_inc = _cats_of(sem)
    # 改名 / 删除：没在 renames 里声明又不在新列表里的，算删除，落到兜底类
    mapping = {}
    for old in old_exp + old_inc:
        if old in renames:
            mapping[old] = str(renames[old]).strip()
        elif old not in exp + inc:
            mapping[old] = ""
    n_exp = n_inc = 0
    with store.tx("bill") as c:
        for old, new in mapping.items():
            is_exp = old in old_exp
            fallback = "其他" if is_exp else "其他收入"
            if not new or (is_exp and new not in exp) or (not is_exp and new not in inc):
                new = fallback
            cur = c.execute("UPDATE bill SET cat=? WHERE sem=? AND cat=?",
                            (new, sem, old))
            if is_exp:
                n_exp += cur.rowcount
            else:
                n_inc += cur.rowcount
        # 尾款行的类别跟着改，不然「付清并记账」会落进一个不存在的类别
        for old, new in mapping.items():
            if new:
                c.execute("UPDATE tail SET cat=? WHERE sem=? AND cat=?", (new, sem, old))
        c.execute("DELETE FROM cat WHERE sem=?", (sem,))
        for i, n in enumerate(exp):
            c.execute("INSERT INTO cat(sem,kind,name,ord) VALUES(?,?,?,?)",
                      (sem, "exp", n, i))
        for i, n in enumerate(inc):
            c.execute("INSERT INTO cat(sem,kind,name,ord) VALUES(?,?,?,?)",
                      (sem, "inc", n, i))
    drop_cache(BILL)
    return True, "类别已保存（改了 %d 处支出、%d 处收入的历史记录）" % (n_exp, n_inc)




# ================================================================
# HTTP 服务
# ================================================================
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".svg": "image/svg+xml", ".ico": "image/x-icon"}

# 回收站的恢复靠重放这几个「新增」函数（它们定义在上面了，这里才绑得进来）
RECYCLE_ADD.update({"bill/add": bill_add, "tail/add": tail_add, "todo/add": todo_add})

API = {
    "bill": lambda: cached(BILL, load_bill),
    "check": lambda: cached(CHECK, load_check),
    "stock": lambda: cached(STOCK, load_stock),
    "ai/config": ai_config_get,          # 不走缓存：Key 改动要立刻生效
    "ai/usage": ai_usage_get,
    "ai/analysis": ai_analysis_get,
    "bill/cats": cats_get,
    "backup/list": backup_list,
    "semesters": lambda: list_semesters(),
    "semesters/compare": semesters_compare,
    "notes/list": note_list,
    "notes/pending": note_pending,
    "memory/tools": memory_tools_list,
    "recycle/list": recycle_list,
    "check/backfill": check_backfill_status,
    "settings": settings_get,
    "auth/state": lambda: auth_state(),
    "auth/autostart": lambda: {"on": autostart_state()[0], "value": autostart_state()[1]},
    "about": app_about,
    "debug": debug_info,
    "stamp": data_stamp,
    "notice": notice_take,
    "emergency": emergency_get,
    "fonts": list_fonts,
    "error/log": error_log_read,
}
WRITERS = {
    "bill/add": bill_add, "bill/edit": bill_edit, "bill/del": bill_del,
    "emergency/save": emergency_save,
    "export/excel": export_excel,
    "data/inspect": data_inspect,        # 换目录前先看看要搬什么（只读）
    "data/move": data_move,              # 真搬：复制 → 校验 →（可选）删源
    "ai/vision": ai_vision,
    "bill/stat": bill_stat,
    "tail/add": tail_add, "tail/edit": tail_edit, "tail/del": tail_del,
    "tail/pay": tail_pay,
    "check/set": check_set, "check/ensure": check_ensure,
    "dream/save": dream_save,
    "stock/set": stock_set, "stock/add": stock_add, "stock/eat": stock_eat,
    "todo/add": todo_add, "todo/edit": todo_edit,
    "todo/toggle": todo_toggle, "todo/del": todo_del,
    "todo/ics": todo_ics,           # 把一条待办写成 .ics（2.4.5）
    "ai/config/save": ai_config_save, "ai/test": ai_test, "ai/drug": ai_drug,
    "ai/shelf": ai_shelf,
    "settings/bg": bg_save, "settings/bg/clear": bg_clear,
    "ai/models": ai_models_fetch, "ai/usage/clear": ai_usage_clear,
    "ai/suggest": ai_suggest, "ai/analyze": ai_analyze,
    "bill/cats/save": cats_save,
    "backup/now": backup_now, "backup/restore": backup_restore,
    "semester/switch": semester_switch, "semester/create": semester_create,
    "notes/get": note_get, "notes/save": note_save, "notes/del": note_del,
    "notes/quick": note_quick, "notes/generate": note_generate,
    "notes/append": note_append,         # 原样追加，不过 AI（日记模板走这条）
    "notes/new": note_new,               # 新建一篇（随笔按时刻命名）
    # ---- 2.3.6 ----
    "check/series": check_series,        # 近 N 天的每日小结（热力图/连续/趋势共用）
    "game/state": game_state, "game/save": game_save, "game/redeem": game_redeem,
    "sub/list": sub_list, "sub/save": sub_save,
    "tpl/list": tpl_list, "tpl/save": tpl_save,
    "quote/list": quote_list, "quote/save": quote_save,
    "notes/attach": attach_save,         # 存一张插图，返回它在正文里怎么写
    "notes/export": notes_export,        # 导出成 Word / Markdown / HTML
    "memory/chat": memory_chat,
    # ---- 2.4.1：对话落盘 ----
    "memory/chats": lambda b: (True, "ok", {"chats": mem_chats()}),
    "memory/history": mem_history,
    "memory/clear": mem_clear,
    "memory/clear_all": mem_clear_all,
    "notes/todo": note_extract_todos,
    "recycle/restore": recycle_restore, "recycle/purge": recycle_purge,
    "recycle/clear": recycle_clear,
    "settings/save": settings_save, "check/items/save": lambda b: check_items_save(b.get("items")),
    # ⚠ 必须回 3 元组。写成 `lambda b: {"items": ...}` 的话，路由会把那个 dict
    # 当 msg，前端从 r.data 拿就是 undefined —— 「点了没反应还不报错」的老毛病。
    "check/items": lambda b: (True, "打卡项", {"items": check_items()}),
    "auth/unlock": auth_unlock, "auth/set": auth_set, "auth/clear": auth_clear,
    "error/clear": error_log_clear, "cache/clear": cache_clear,
}


# 允许出现在 /static/ 下的**子目录**白名单（2.4.8 加的）。
# ⚠ 为什么要白名单：静态服务原来一律走 `os.path.basename(path)` ——
#   那确实挡住了 `../` 穿越，但代价是**子目录彻底访问不了**。
#   2.4.8 加自带字体（`static/fonts/shoujinti.ttf`）时就撞上了：字体 404，
#   而源码版和桌面版都"看着正常"（只是字静默回退成了别的字体）。
STATIC_SUBDIRS = ("fonts",)


def _static_rel(path):
    """/static/xxx 里的 xxx → 可以安全拼进 WEB 的相对路径。

    ⚠ 安全底线跟原来一样严：**只接受白名单里的第一层子目录 + 一个纯文件名**。
      不做"拼接后检查前缀"那套 —— 那要处理符号链接、大小写、`..` 归一化，
      容易漏；白名单是"只有这几个形状能过"，漏不了。
      没命中白名单就退回 basename（跟 2.4.8 之前的行为完全一致）。
    """
    rel = path[len("/static/"):].split("?", 1)[0].split("#", 1)[0]
    rel = rel.replace("\\", "/").lstrip("/")
    if "/" in rel:
        parts = [p for p in rel.split("/") if p not in ("", ".")]
        # 只允许「白名单目录 / 纯文件名」两层，多一层都不要
        if len(parts) == 2 and parts[0] in STATIC_SUBDIRS and parts[1] not in ("", ".."):
            return os.path.join(parts[0], os.path.basename(parts[1]))
    return os.path.basename(rel)


class Handler(BaseHTTPRequestHandler):

    def finish(self):
        """一条 HTTP 连接处理完了，把它那条 SQLite 连接也关掉。
        每个请求一个线程、一个连接，不还回去的话句柄会一直涨。"""
        try:
            store.close()
        finally:
            super().finish()

    server_version = "StatsSys/2.0"

    def log_message(self, fmt, *args):   # 静默访问日志
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # ⚠ 所有接口一律不许缓存（2.3.7 补）。
        #   原来这条响应**一个缓存头都没有** —— 静态文件那边是写了的
        #   （ETag + no-cache），接口这边漏了。实测踩到：同一个 Chrome
        #   profile 里改了主题设置，页面死活还是旧主题，换一个干净 profile
        #   立刻就对；同一份代码同一个库，两个 profile 出两种结果。
        #   没有 Cache-Control / Expires / Last-Modified 时浏览器会走
        #   启发式缓存，具体行为随版本变，不能靠它。
        #   接口数据全部来自本地库，no-store 的成本是零。
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._file(os.path.join(WEB, "index.html"))
        if path.startswith("/static/"):
            return self._file(os.path.join(WEB, _static_rel(path)))
        # 背景图走静态这条路（不查令牌），理由和静态页一样：
        # 锁屏界面也应该有背景，拦了就得先解锁才看得见自己的桌面。
        # 而且服务只监听 127.0.0.1，本来也出不了这台机器。
        # 桌面那个小时钟（2.4.1）。**不查令牌** —— 它是个独立的窗口，
        # 没有登录这一步；服务只监听 127.0.0.1，出不了这台机器。
        # 跟 /bg 同一个理由。
        if path == "/api/clock":
            return self._json({"ok": True, "data": clock_state()})
        if path == "/bg":
            p = bg_path()
            if not p or not os.path.isfile(p):
                return self._json({"ok": False, "msg": "还没设背景图"}, 404)
            # 背景图是「换了就得立刻看到」的东西 —— 一律不缓存。
            # 光靠 URL 上加版本号不够：换图之后文件名还是「背景.jpg」，
            # URL 一模一样，浏览器照样端旧图出来（实测过）。
            return self._file(p, no_store=True)
        # 笔记里的插图。跟 /bg 一个道理：不查令牌，服务只监听 127.0.0.1，
        # 而且正文里的 ![](附件/x.jpg) 得能在锁屏前就渲染出来。
        if path.startswith("/attach/"):
            p = attach_path(path[8:])
            if not p or not os.path.isfile(p):
                return self._json({"ok": False, "msg": "没有这张图"}, 404)
            # 文件名是**内容哈希**，同一张图永远是同一个名字 → 可以长缓存
            return self._file(p)
        if path.startswith("/api/"):
            name = path[5:]
            if name in API:
                if not self._authed(name):
                    return self._json({"ok": False, "need_password": True,
                                       "msg": "需要先解锁"}, 401)
                try:
                    return self._json({"ok": True, "data": API[name]()})
                except Exception as e:
                    log_error("GET /api/%s" % name, e)
                    return self._json({"ok": False, "msg": "读取失败: %s" % e}, 500)
        self._json({"ok": False, "msg": "404 %s" % path}, 404)

    def _authed(self, name):
        """设了密码的话，除了解锁接口本身，其他都要带对令牌。
        静态文件不拦 —— 锁屏界面自己就是静态页，拦了就没法输了。"""
        if name.startswith("auth/"):
            return True
        return auth_check(self.headers.get("X-Auth-Token"))

    def do_POST(self):
        name = self.path[5:]
        if name not in WRITERS:
            return self._json({"ok": False, "msg": "未知操作 %s" % name}, 404)
        if not self._authed(name):
            return self._json({"ok": False, "need_password": True,
                               "msg": "需要先解锁"}, 401)
        # 每天第一次改动之前先给数据库留一份快照。
        # 放在**所有写操作的入口**，而不是某个具体的写函数里 ——
        # 以前挂在 save_atomic 上，换存储之后那个钩子再也不触发了，
        # 自动备份就这么悄没声地停了。入口只此一处，以后加新接口也不会漏。
        auto_backup_db()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, ValueError):
                # 请求体不是合法 UTF-8 JSON。这**不是保存失败**，是请求本身坏了，
                # 回 500「保存失败」会让人以为是数据出了问题，白查半天。
                return self._json({"ok": False,
                                   "msg": "请求格式不对（要 UTF-8 的 JSON）"}, 400)
            res = WRITERS[name](body)
            extra = None
            if isinstance(res, tuple) and len(res) == 3:      # (ok, msg, data)
                ok, msg, extra = res
            elif isinstance(res, tuple):
                ok, msg = res
            else:
                ok, msg = True, res
            out = {"ok": ok, "msg": msg}
            if extra is not None:
                out["data"] = extra
            return self._json(out, 200 if ok else 400)
        except PermissionError:
            return self._json({"ok": False, "msg":
                               "Excel 文件被占用（可能正被 WPS/Excel 打开），请先关闭再保存"}, 409)
        except Exception as e:
            log_error("POST /api/%s" % name, e)
            return self._json({"ok": False, "msg": "保存失败: %s" % e}, 500)

    def _file(self, path, no_store=False):
        """发一个文件。

        ⚠ **缓存头不能省。** 这里原来只发 Content-Type 和 Content-Length ——
          Cache-Control、ETag、Last-Modified 一个都没有。后果不是"慢"，
          而是**东西换了浏览器还给你旧的**：
            · `/bg?v=背景.jpg` 那个版本号是**文件名**，换图之后名字没变，
              URL 一模一样 → 一直显示第一张图（用户报的「换不了背景」）
            · `/static/app.js` 在 index.html 里**没有版本号** →
              升级完可能还在跑上一个版本的代码，界面看着像没更新
          所以现在：static 走 ETag + no-cache（每次问一句，没变就 304，
          又新又快）；/bg 那种会变的直接 no-store，别缓存。

        判断「变没变」用**内容哈希**，不用 mtime：mtime 在同一秒内的两次改动
        会撞车，而内容哈希不会。"""
        if not os.path.isfile(path):
            return self._json({"ok": False, "msg": "404"}, 404)
        data = open(path, "rb").read()
        etag = '"%s"' % hashlib.md5(data).hexdigest()[:20]
        if no_store:
            cc = "no-store, max-age=0"
        else:
            cc = "no-cache"
        # 浏览器说"我这儿有这版" → 回一个空 304，省掉整包传输
        if not no_store and self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cc)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(os.path.splitext(path)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", cc)
        self.end_headers()
        self.wfile.write(data)


def port_in_use(port):
    """端口是否已有服务在监听。
    必须自己先查：http.server 默认开 SO_REUSEADDR，在 Windows 上它意味着
    "允许绑定到已占用的端口" —— 新进程会静默绑定成功，但连接仍被老进程接走，
    表现为「系统看着启动了，数据却一直不更新」。"""
    import socket
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


# 全新安装时的默认类别。**必须给一套**，不然第一次记账时类别下拉是空的，
# 记什么都落不了地。之后在设置页随便增删改。
FRESH_EXP_CATS = ["餐饮", "零食", "饮料", "服饰", "日用品", "购物", "交通", "通讯",
                  "学习", "娱乐", "游戏", "周边", "医疗", "生活", "人情", "理财", "其他"]
# 收入侧原来只有 4 项，结果「其他收入」一项就占了九成多 ——
# 报销、返现、红包、卖闲置全挤在里面，饼图看着就是一大块加两根细丝。
# 拆细之后记账时好归类，将来也看得出钱从哪来。
# ⚠ 顺序只影响下拉里的排列，用户随时能在设置里改。
FRESH_INC_CATS = ["生活费", "兼职", "奖学金", "报销", "返现", "红包",
                  "二手", "退款", "理财", "其他收入"]


def seed_fresh():
    """头一次跑、库里什么都没有、也没有旧 Excel 可搬时，铺一层默认数据。"""
    if not store.is_empty():
        return False
    with store.tx("bill") as c:
        for i, n in enumerate(FRESH_EXP_CATS):
            c.execute("INSERT OR REPLACE INTO cat(sem,kind,name,ord) VALUES(?,?,?,?)",
                      (SEMESTER, "exp", n, i))
        for i, n in enumerate(FRESH_INC_CATS):
            c.execute("INSERT OR REPLACE INTO cat(sem,kind,name,ord) VALUES(?,?,?,?)",
                      (SEMESTER, "inc", n, i))
    with store.tx("check") as c:
        c.execute("INSERT OR REPLACE INTO check_month(ym,d0) VALUES(?,?)",
                  ("%04d年%02d月" % (date.today().year, date.today().month),
                   date.today().replace(day=1).strftime("%Y-%m-%d")))
    drop_cache(BILL)
    drop_cache(CHECK)
    return True


def apply_fixes():
    """一次性的数据修补。每条只跑一次，跑过就记在 kv 里。

    **只修「明确的 bug 产物」，绝不碰用户真正填进去的东西。**
    所以下面这条只清「待核销」——那是表单默认值误存进去的，没有含义。
    「核销」和「退回」一律不碰：「退回」会让那一行剔除统计，
    清掉等于凭空多出一笔钱。"""
    if _seed_check_items():
        print("[打卡] 已把出厂打卡项写进数据库（以后可以在设置里增删改）")
    seed_stock_cols()
    _add_new_income_cats()
    _thin_bg_dim()
    _flatten_bg()
    if store.kv_get("fix.bill_stat_group"):
        return
    n = 0
    with store.tx("bill") as c:
        n = c.execute("UPDATE bill SET stat=''"
                      " WHERE grp<>'是' AND stat='待核销'").rowcount
    store.kv_set("fix.bill_stat_group", "1")
    if n:
        print("[修补] 清掉了 %d 条非团购记录上多余的「待核销」" % n)


def _thin_bg_dim():
    """把「还是老默认值」的背景遮罩浓度逐版调薄。跑过哪一档就记在 kv 里。

    遮罩用的是**主题底色**：深色主题下它是压暗照片，浅色主题下它是给照片垫一层
    浅底 —— 而浅色主题的底色本身就是浅色，浓了就等于往照片上蒙白纱。
    用户的原话是「浅色怎么感觉全屏都雾蒙蒙的」。

      · 2.3.5：35% → 20%
      · 2.3.6：20% → 10%（「调得很薄，只压照片」）

    估算公式（前端 suggestDim）每次都跟着改，但**已经存下来的值不会自己变**，
    所以这里替老用户挪。

    ⚠ 只认「正好等于上一版的默认」：别的值一律不碰，那是用户自己拖出来的。
      记的是「已经挪到过哪一档」，不是简单的跑没跑过 —— 所以同一个人
      跨版本能连挪两次（35→20→10），但手动拖回 20 之后就不会再被降下去。"""
    done = set((store.kv_get("fix.bg_dim") or "").split(",")) - {""}
    for old, new in (("35", 20), ("20", 10), ("10", 0)):
        if str(new) in done:
            continue
        if int(settings_load().get("bg_dim") or 0) == int(old):
            settings_save({"bg_dim": new})
            print("[修补] 背景遮罩 %s%% → %s%%（照片被那层纱洗白了）" % (old, new))
        done.add(str(new))
    store.kv_set("fix.bg_dim", ",".join(sorted(done)))


def _flatten_bg():
    """2.3.8：把「全屏遮罩」和「卡片透出照片」一次性清零。

    ⚠ 和 `_thin_bg_dim` 不是一回事，别合并：

      · `_thin_bg_dim` 的规矩是**只认「正好等于上一版的默认值」** —— 别的值
        一律不碰，那是用户自己拖出来的。它挪的是「默认值的演化」。
      · 这里挪的是**含义已经作废的值**：
          - bg_dim  以前的前提是"必须有薄薄一层，不然字看不清"，
                    现在这个前提被推翻了（用户要的是"不要那层图层"）
          - bg_glass 的映射分母 2.3.7 从 55% 提到了 86%，同一个 75
                    在两个版本里指的是**完全不同的两种效果**
        老值留着没有任何意义，只会让用户开机看到一屏他没要过的样子。

      重不重置都只是两个滑块的位置，用户拖回来就是 —— 所以这里可以果断清零，
      不像 `_thin_bg_dim` 那样需要小心翼翼地只认默认值。

    跑一次记一次（`fix.bg_flat`），之后用户自己拖的就再也不会被动了。"""
    if store.kv_get("fix.bg_flat"):
        return
    s = settings_load()
    if int(s.get("bg_dim") or 0) or int(s.get("bg_glass") or 0):
        settings_save({"bg_dim": 0, "bg_glass": 0})
        print("[修补] 背景：全屏遮罩与卡片透出都归零（2.3.8 起默认不蒙任何东西）")
    store.kv_set("fix.bg_flat", "1")


def _add_new_income_cats():
    """把新加的几个收入类别补进已有的库。一条只跑一次，跑过就记在 kv 里。

    **只 INSERT 缺的那几个，不删不改任何现有类别，也不碰任何一条账单记录。**
    用户自己删过的类别不会被它加回来 —— 只补这一批新名字。"""
    NEW = ["报销", "返现", "红包", "二手", "退款"]
    if store.kv_get("fix.income_cats"):
        return
    added = []
    with store.tx("bill") as c:
        for sem in [r[0] for r in c.execute(
                "SELECT DISTINCT sem FROM cat WHERE kind='inc'")]:
            have = {r[0] for r in c.execute(
                "SELECT name FROM cat WHERE sem=? AND kind='inc'", (sem,))}
            n = c.execute("SELECT COALESCE(MAX(ord),0) FROM cat"
                          " WHERE sem=? AND kind='inc'", (sem,)).fetchone()[0]
            for nm in NEW:
                if nm in have:
                    continue
                n += 1
                c.execute("INSERT OR IGNORE INTO cat(sem,kind,name,ord)"
                          " VALUES(?,?,?,?)", (sem, "inc", nm, n))
                added.append(nm)
    store.kv_set("fix.income_cats", "1")
    if added:
        print("[修补] 收入类别补了 %d 个：%s" % (len(added), "、".join(added)))


def _pause():
    """出错时停一下让人看清提示。**但只在真终端里停** ——
    被自测脚本/服务方式拉起来时 stdin 不是终端，input() 会直接抛
    EOFError 把整个回溯糊在屏幕上，比原来的错误信息还吓人。"""
    try:
        if sys.stdin and sys.stdin.isatty():
            input("按回车退出...")
    except Exception:
        pass


def main():
    load_data_config()               # 恢复上次用的学期
    global MISSING
    MISSING = missing_files()
    # ⚠ 这里以前是「找不到三本 Excel 就不许开机」。
    # 存储换成 SQLite 之后这条**已经不成立了**：数据在数据库里，
    # 三本 Excel 只是导出目标，没有它们应用照样该能跑。
    # 而且安装版会装到 %LOCALAPPDATA%\Programs\ 去，往上找三层永远找不到
    # 用户放在 D 盘的数据 —— 要是还拦着，装完就是一扇打不开的门。
    # 现在只提示，不拦。
    if MISSING and store.is_empty():
        print("! 还没找到数据，也没搬过旧数据 —— 先按全新开始。")
        print("  数据目录：%s" % DATA_ROOT)
        print("  如果你原来有数据，把「个人信息统计」文件夹指到这儿再启动一次就行。")
    elif MISSING:
        print("[数据] 数据库里已经有数据；下面这些 Excel 不在，只影响导出，不影响使用：")
        for p in MISSING:
            print("   -", p)
    if port_in_use(PORT):
        print("!! 端口 %d 已被占用，可能已经有一个系统实例在运行。" % PORT)
        print("   请先关掉那个窗口，或设置环境变量 STATS_PORT 换一个端口，例如：")
        print("     set STATS_PORT=8766 && python server.py")
        _pause()
        return
    # 第一次跑 2.0：把三本 Excel 搬进 SQLite。
    # 核对不过就抛异常、直接不开机 —— 宁可起不来，也不能让人对着半吊子数据用。
    try:
        import _migrate
        did, msg = _migrate.ensure(DATA_ROOT, sys.modules[__name__])
        if did:
            print("[数据] " + msg)

            # 打包版没有控制台，这些字用户一个字也看不见。
            # 留一条一次性通知，开机后由界面告诉他「发生了什么、东西还在不在」。
            store.kv_set("notice", "已把原来的三本 Excel 搬进数据库。\n" + msg)
        elif store.is_empty():
            # 没搬过、库里也空的 = 全新安装，铺一层默认类别，
            # 不然第一次记账时类别下拉是空的，记什么都落不了地
            if seed_fresh():
                print("[数据] 全新开始，已铺好默认类别。")
        # 一次性的数据修补，跑在迁移/播种之后
        apply_fixes()
        # 上次「换数据目录」欠下的删除。放这儿是因为要等库都开完了再说 ——
        # 见 _purge_pending() 上面那段：Windows 上删不掉自己开着的库文件。
        _purge_pending()
    except Exception as e:
        print("!! 数据迁移失败：%s" % e)
        print("   你的 Excel 一个字节都没改，可以用旧版本继续。")
        _pause()
        return
    # 把老格式的周报/月报标题换成新的（只动第一行，且只动长得像老格式的）
    try:
        ch = notes.migrate_titles()
        if ch:
            print("[笔记] 标题已更新：%s" % "、".join(ch))
    except Exception as e:
        print("[笔记] 标题迁移失败（不影响使用）: %s" % e)
    # 断月回填要在下面那次同步 check_ensure **之前**登记基准月，否则缺口会被堵死
    check_backfill_start()
    # 启动时补齐打卡表结构（缺当月表自动建 / 看板滚动 / 梦境年份续期）
    try:
        ok, msg = check_ensure()
        print("[打卡表]", msg)
    except Exception as e:
        print("[打卡表] 结构检查失败（文件可能被占用）: %s" % e)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%d" % PORT
    if not os.environ.get("STATS_NOBROWSER"):
        threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(url)),
                         daemon=True).start()
    print("小煦拾简已启动：%s" % url)
    print("数据根目录：%s" % DATA_ROOT)
    print("关闭此窗口（Ctrl+C）即停止系统。")
    # 后台补缺的周报/月报。先 sleep 再干活，不挡开窗
    note_autogen_start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("已停止。")


if __name__ == "__main__":
    main()
