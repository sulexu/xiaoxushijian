# -*- coding: utf-8 -*-
"""SQLite 存储层 —— 数据不再住在 Excel 里

为什么换掉 Excel 当数据库：

  写一次要 load_workbook 整本 + save_atomic 整本。账单那本 972 行、打卡那本
  8 张表 40 列，改一个格也要把整本重排一遍再落盘，写完还要 drop_cache，
  于是每点一下都卡。SQLite 是**标准库自带**的（「零第三方依赖」这条底线没破），
  单行写是微秒级，而且天然带事务 —— 尾款「付清并记账」那种一次改两处的操作
  再也不用自己拼。」

  更要紧的是：图片没地方放。截图识别出来的东西总得有个落点，
  往 Excel 里塞图是自找麻烦。

Excel **没有被抛弃**，只是从「数据库」降级成「导出格式」：报告用、存档用、
想用 Excel 自己再算算的时候用。导出是一等功能，随时能把全部数据吐回成
跟原来一模一样的三本表。

并发：ThreadingHTTPServer 一个请求一个线程，所以连接放 threading.local，
一人一个，别跨线程共用（sqlite3 的连接默认就不许这么干）。
开 WAL，读不挡写。
"""
import os
import sqlite3
import threading
import time

# 数据库就放在数据根下，跟三本 Excel 并排 —— 一眼能看见，备份也好带
DB_NAME = "小煦拾简.db"

# ⚠ 库文件路径必须是**进程级**的，不能塞进 threading.local。
# ThreadingHTTPServer 一个请求一个线程，主线程里 use() 设的路径，
# 工作线程里根本看不见 —— 表现就是主线程好好的，一收到请求就报
# 「还没指定数据库文件」。threading.local 里只放那个线程自己的连接。
_path = None
_local = threading.local()
_write_lock = threading.RLock()

SCHEMA_VER = 1


def db_path(root):
    return os.path.join(root, DB_NAME)


# ================================================================
# 连接
# ================================================================
def connect(path):
    """开一个连接。调用方一般不用直接用它，用 conn() 拿线程内那个。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    c = sqlite3.connect(path, timeout=15, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")     # 读不挡写
    c.execute("PRAGMA synchronous=NORMAL")   # WAL 下够安全，比 FULL 快得多
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=15000")
    return c


def conn():
    """当前线程的连接。没建过就现建一个（懒建，线程用完就关）。"""
    c = getattr(_local, "c", None)
    if c is None:
        if not _path:
            raise RuntimeError("还没指定数据库文件，先调 store.use(路径)")
        c = connect(_path)
        _local.c = c
    return c


def use(path):
    """指定数据库文件（进程启动时调一次；测试里用来指到隔离目录）"""
    global _path
    path = os.path.abspath(path)
    if _path == path:
        return
    _path = path
    close()          # 只关当前线程那条；别的线程的连着，反正它们下次会重新开


def close():
    """关掉**当前线程**的连接。HTTP 那边每处理完一条连接就调一次 ——
    ThreadingHTTPServer 是一请求一线程，不主动关的话每条请求都漏一个
    SQLite 连接（还压着 WAL 读锁），跑一会儿就打不开了。"""
    c = getattr(_local, "c", None)
    if c is not None:
        try:
            c.close()
        except Exception:
            pass
        _local.c = None


# ================================================================
# 查询小工具
# ================================================================
def q(sql, args=()):
    return conn().execute(sql, args).fetchall()


def q1(sql, args=()):
    return conn().execute(sql, args).fetchone()


def one(sql, args=(), default=None):
    """取一个标量"""
    r = q1(sql, args)
    return r[0] if r is not None and r[0] is not None else default


def x(sql, args=()):
    """执行。返回 lastrowid（INSERT）或受影响行数（UPDATE/DELETE）。"""
    with _write_lock:
        cur = conn().execute(sql, args)
        return cur.lastrowid if cur.lastrowid else cur.rowcount


def xmany(sql, seq):
    with _write_lock:
        conn().executemany(sql, seq)


def script(sql):
    with _write_lock:
        conn().executescript(sql)


class _Tx:
    """一次事务。里面**不能**再调 x()/xmany()（它们自己会去抢同一把锁，
    RLock 虽然可重入，但内层 COMMIT 会把外层的事务提前结束掉）。
    事务里一律直接用 c.execute()。

    domain 是「这块改动属于哪个领域」（bill / check / stock …）。
    前端每几秒问一次 /api/stamp，靠它分辨到底是哪块变了 ——
    不分域的话，记一笔账会让打卡页也弹出「数据在别处被改过」，纯属吓人。"""

    def __init__(self, domain=None):
        self.domain = domain

    def __enter__(self):
        self.c = conn()
        self.c.execute("BEGIN IMMEDIATE")
        return self.c

    def __exit__(self, et, ev, tb):
        if et is None:
            self.c.execute("COMMIT")
            bump(self.domain)      # 模块级函数，不是 self 上的
        else:
            self.c.execute("ROLLBACK")
        return False


def tx(domain=None):
    return _Tx(domain)


def bump(domain=None):
    """版本号 +1。**全局那个给缓存用**（任何改动都让缓存失效），
    分域的那个给前端判断「是哪块变了」。"""
    with _write_lock:
        c = conn()
        keys = ["rev"] + (["rev." + domain] if domain else [])
        for k in keys:
            c.execute("INSERT INTO kv(k,v) VALUES(?, '1') "
                      "ON CONFLICT(k) DO UPDATE SET v=CAST(CAST(v AS INTEGER)+1 AS TEXT)",
                      (k,))


def rev(domain=None):
    """domain=None → 全局版本号（缓存失效用）
    给了 domain → 只数那块（前端提示条用）"""
    if domain is None:
        return int(one("SELECT v FROM kv WHERE k='rev'", (), 0) or 0)
    return int(one("SELECT v FROM kv WHERE k=?", ("rev." + domain,), 0) or 0)


def kv_get(k, d=None):
    r = q1("SELECT v FROM kv WHERE k=?", (k,))
    return r[0] if r else d


def kv_set(k, v):
    with _write_lock:
        conn().execute("INSERT INTO kv(k,v) VALUES(?,?) "
                       "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def kv_del(k):
    x("DELETE FROM kv WHERE k=?", (k,))


# ================================================================
# 建表
# ================================================================
SCHEMA = r"""
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);

-- 账单流水。原来靠 Excel 行号定位（插一行全乱），现在给自增主键，
-- 行号只在对 Excel 导出时才临时算。
--
-- sem = 学期。**这是换到 SQLite 顺带解决的一件事**：以前一个学期一个 xlsx
-- 文件，切学期要重绑路径、重算 MISSING、清 AI 缓存；现在只是一个字段，
-- 切学期就是换个 where 条件，跨学期对比就是 group by。
CREATE TABLE IF NOT EXISTS bill (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  sem  TEXT NOT NULL DEFAULT '',
  date TEXT NOT NULL DEFAULT '',
  cat  TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  inc  REAL NOT NULL DEFAULT 0,
  exp  REAL NOT NULL DEFAULT 0,
  pay  TEXT NOT NULL DEFAULT '',
  grp  TEXT NOT NULL DEFAULT '',
  stat TEXT NOT NULL DEFAULT '',
  src  TEXT NOT NULL DEFAULT ''      -- 'shot' = 截图识别录进来的，便于日后追溯
);
CREATE INDEX IF NOT EXISTS bill_date ON bill(sem, date);

CREATE TABLE IF NOT EXISTS tail (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  sem   TEXT NOT NULL DEFAULT '',
  name  TEXT NOT NULL DEFAULT '',
  cat   TEXT NOT NULL DEFAULT '',
  dep   REAL NOT NULL DEFAULT 0,
  tail  REAL NOT NULL DEFAULT 0,
  pdate TEXT NOT NULL DEFAULT '',
  stat  TEXT NOT NULL DEFAULT '待付',
  note  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS budget (
  sem    TEXT NOT NULL DEFAULT '',
  month  TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (sem, month)
);

-- 类别。kind = exp(支出) / inc(收入)
CREATE TABLE IF NOT EXISTS cat (
  sem  TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  ord  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (sem, kind, name)
);

-- 打卡。用「一格一行」而不是「一天一行 28 列」：
-- 打卡项的列是刻死的（CHECK_ITEMS），但万一以后要加项，
-- 窄表只要多几行，宽表得改表结构 + 迁移。
CREATE TABLE IF NOT EXISTS check_val (
  date TEXT NOT NULL,               -- YYYY-MM-DD
  col  TEXT NOT NULL,               -- Excel 列号，如 'C' 'AA'
  v    REAL,                        -- 数字型（时间/数字/勾）
  s    TEXT,                        -- 文本型（下拉/备注）
  PRIMARY KEY (date, col)
);
CREATE INDEX IF NOT EXISTS check_val_date ON check_val(date);

-- 打卡「设置」表那几项（作息时间、目标、下拉选项）
CREATE TABLE IF NOT EXISTS check_cfg (k TEXT PRIMARY KEY, v TEXT);

-- 打卡项定义。**这张表是「打卡项可自定义」的地基。**
-- 以前打卡数据在 Excel 月表里，每项固定占一列，旁边的公式（完成率、
-- 睡眠时长）全按列号引用，插一列就把它们全带偏，所以只敢让用户改名和隐藏。
-- 换成窄表之后，「一项」就是 check_val 里的一组行，加删都不影响别的。
--   col   内置项是原来的列字母；自建项是 U1/U2…
--   kind  tick 打勾 / num 数字 / time 时间 / sel 下拉 / text 文本
--   grp   core 计入完成率 / bonus 加分 / other 只在单日页显示
CREATE TABLE IF NOT EXISTS check_item (
  col     TEXT PRIMARY KEY,
  name    TEXT NOT NULL DEFAULT '',
  kind    TEXT NOT NULL DEFAULT 'tick',
  grp     TEXT NOT NULL DEFAULT 'other',
  opts    TEXT NOT NULL DEFAULT '',      -- 下拉选项，逗号分隔
  ord     INTEGER NOT NULL DEFAULT 0,
  -- ⚠ 列名不能叫 on —— **那是 SQLite 的保留字**（JOIN ... ON），
  -- 建表时会直接报 near "on": syntax error
  enabled INTEGER NOT NULL DEFAULT 1,
  builtin INTEGER NOT NULL DEFAULT 0     -- 内置项只能隐藏，自建项才能真删
);

-- 有哪些月表、每个月表从哪天开始。
-- **必须存 d0**：9 月表是从 12 号开始的（系统建表那天），不是 1 号。
-- 要是拿「整月」当答案，网页上会凭空多出 1~11 号十一个空格子。
CREATE TABLE IF NOT EXISTS check_month (
  ym TEXT PRIMARY KEY,          -- '2026年09月'
  d0 TEXT NOT NULL DEFAULT ''   -- 这个月表的第一天 'YYYY-MM-DD'
);

-- 梦境。kind = detail(梦境明细，网页录入) / archive(梦境档案，旧的长文版)
CREATE TABLE IF NOT EXISTS dream (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  kind    TEXT NOT NULL,
  date    TEXT NOT NULL,
  seq     INTEGER NOT NULL DEFAULT 1,
  type    TEXT NOT NULL DEFAULT '',
  mood    TEXT NOT NULL DEFAULT '',
  clarity TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  read    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS dream_k ON dream(kind, date);

-- 物资。同样是窄表：sheet=药品/日用品/零食，col=Excel 列号。
-- row_id 是每张分表内部稳定的序号（1,2,3...），不是 Excel 行号。
CREATE TABLE IF NOT EXISTS stock (
  sheet  TEXT NOT NULL,
  row_id INTEGER NOT NULL,
  col    TEXT NOT NULL,
  v      REAL,
  s      TEXT,
  PRIMARY KEY (sheet, row_id, col)
);

-- 物资表头（第 4 行那些中文名）。存下来是为了不打开 Excel 也能渲染表头。
CREATE TABLE IF NOT EXISTS stock_header (
  sheet TEXT NOT NULL,
  col   TEXT NOT NULL,
  name  TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (sheet, col)
);

-- 手动待办
CREATE TABLE IF NOT EXISTS todo (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  stat TEXT NOT NULL DEFAULT '未完成',
  item TEXT NOT NULL DEFAULT '',
  cat  TEXT NOT NULL DEFAULT '',
  due  TEXT NOT NULL DEFAULT '',
  pri  TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  ord  INTEGER NOT NULL DEFAULT 0
);

-- 应急信息。分成「字段」和「联系人」两张：
-- 前者是 标签→值（基本信息 / 医疗警示 / 常用电话 / 就医与其他），
-- 后者是表格（姓名 / 关系 / 电话），塞进 kv 里没法编辑。
CREATE TABLE IF NOT EXISTS em_field (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  sec   TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  value TEXT NOT NULL DEFAULT '',
  ord   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS em_contact (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  name  TEXT NOT NULL DEFAULT '',
  rel   TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  ord   INTEGER NOT NULL DEFAULT 0
);

-- 附件（截图）。文件本体放 附件\ 目录，这里只记元信息 ——
-- 图进数据库会让备份和应用体积一起膨胀，不值当。
CREATE TABLE IF NOT EXISTS attach (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  kind    TEXT NOT NULL,            -- bill_shot / sleep_shot / other
  ref     TEXT NOT NULL DEFAULT '', -- 关联对象（如账单 id），可空
  file    TEXT NOT NULL DEFAULT '', -- 附件目录下的文件名
  mime    TEXT NOT NULL DEFAULT '',
  bytes   INTEGER NOT NULL DEFAULT 0,
  ai      TEXT NOT NULL DEFAULT '', -- 识别出的原始 JSON，留档好回溯
  made    TEXT NOT NULL DEFAULT ''  -- 创建时间 YYYY-MM-DD HH:MM:SS
);
CREATE INDEX IF NOT EXISTS attach_ref ON attach(kind, ref);

-- 回忆书的对话（2.4.1）。
-- ⚠ 一张表搞定，**不另开一张「会话表」**：会话列表要的东西
--   （标题、最后一句、时间、几条）全都能从消息里 group by 出来，
--   而一个消息都没有的会话本来也没必要存在。多一张表就多一处
--   要同步的状态（删消息忘了删会话、改标题要更新两处…）。
-- `chat` 就是会话号，形如 c20260918-213045 —— 带时间戳是为了
-- **排序稳定**，同一秒开两个也不会撞（撞了就多加一位）。
CREATE TABLE IF NOT EXISTS mem_msg (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  chat    TEXT NOT NULL,            -- 会话号
  ts      TEXT NOT NULL DEFAULT '', -- YYYY-MM-DD HH:MM:SS
  role    TEXT NOT NULL,            -- user / ai
  content TEXT NOT NULL DEFAULT '',
  -- 这一轮 AI 翻了哪些材料（工具调用的痕迹）。存下来是为了**回看**：
  -- 用户过两天回来看到一句结论，能点开看它当时查了什么，
  -- 不然就只是一句没有出处的断言。
  trace   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS mem_msg_chat ON mem_msg(chat, id);

-- 每天实际干了多久（2.4.1）。牛马时钟的等级就是按这张表的**累计分钟**分的。
-- ⚠ 为什么不是「从装的那天算起 × 每天工时」：那是编的。
--   这张表是**实的** —— 程序每天问你一次现在干到哪儿了，记下当天的最大值。
--   没开机的日子就是 0，等级涨得慢，但那才是真的。
CREATE TABLE IF NOT EXISTS clock_log (
  day     TEXT PRIMARY KEY,          -- YYYY-MM-DD
  minutes INTEGER NOT NULL DEFAULT 0 -- 这天干到过的最大值
);
"""


def init(path=None):
    """建表。幂等，每次启动都可以调。"""
    if path:
        use(path)
    # ① 先给**已有的表**补上缺的列。
    #    这一步必须排在 script(SCHEMA) 前面：SCHEMA 里有
    #    `CREATE INDEX ... ON bill(sem, date)` 这种句子，旧库的 bill 要是没有 sem，
    #    跑到那儿会抛一句「no such column: sem」，那句话看不出真正的问题。
    added, stuck = _add_missing_columns()
    if added:
        print("[数据库] 给旧库补了 %d 个新列：%s" % (len(added), "、".join(added)))
    if stuck:
        raise RuntimeError(
            "数据库有几列补不上：%s。\n"
            "把「小煦拾简.db」改名或删掉，重开一次就会重新建库。" % "、".join(stuck[:8]))
    # ② 再跑建表脚本。**缺的整张表由它建**（CREATE TABLE IF NOT EXISTS 就是干这个的），
    #    索引也在这里建。
    script(SCHEMA)
    if not q1("SELECT 1 FROM kv WHERE k='schema'"):
        kv_set("schema", SCHEMA_VER)
        kv_set("rev", 0)
    elif int(kv_get("schema", 0) or 0) < SCHEMA_VER:
        kv_set("schema", SCHEMA_VER)


def want_tables():
    """从 SCHEMA 里解析出「表 → [(列名, 列定义), …]」。

    列定义原样留着，补列的时候直接拿它去 ALTER TABLE。

    ⚠ 不能用 `\\n\\);` 当结尾 —— kv、check_cfg 这些是**单行**定义的，
    那样写会把它们和后面几张表连成一坨，解析出来的列全是错的（还看不出来）。
    用 `\\);` 收尾，单行多行都能吃。"""
    import re as _re
    want = {}
    for m in _re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\);",
                          SCHEMA, _re.S):
        name, body = m.group(1), m.group(2)
        cols = []
        for line in body.split("\n"):
            line = line.strip()
            if not line or line.startswith("--"):
                continue
            # 行尾可能挂着 `-- 说明`。去掉它 —— ALTER 时带着注释虽然也能跑，
            # 但注释里万一有个逗号就把定义截断了，没必要冒这个险。
            line = _re.sub(r"\s--.*$", "", line).strip().rstrip(",")
            if not line:
                continue
            head = line.split()[0].upper()
            if head in ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"):
                continue          # 表级约束，不是列
            cols.append((line.split()[0], line))
        want[name] = cols
    return want


def _add_missing_columns():
    """给**已经存在**的表补上这一版新加的列。返回 (补好的, 补不上的)。

    ⚠ 这件事 `CREATE TABLE IF NOT EXISTS` 不管：它只建新表，
    **不会往旧表里加列**。所以升级之后旧库不会自己长出新列，
    然后代码去 INSERT 一个不存在的列，报的是一句「no such column」——
    翻半天才知道是怎么回事。这里替它做了。

    **整张表都没有的话，这里什么都不做** —— 那种情况交给 CREATE TABLE
    去建就行。以前把这两种情况混在一起，结果 2.2 一上来就拒绝启动：
    旧的库里没有 check_item 这张新表，却报成「缺 check_item.col、
    check_item.name…」，看着像库坏了，其实只差一张还没建的表。"""
    have_tables = {r[0] for r in q("SELECT name FROM sqlite_master WHERE type='table'")}
    added, stuck = [], []
    for t, cols in want_tables().items():
        if t not in have_tables:
            continue                      # 整张表都没有 → 交给 CREATE TABLE
        have = {r[1] for r in q("PRAGMA table_info(%s)" % t)}
        for cname, decl in cols:
            if cname in have:
                continue
            if "PRIMARY KEY" in decl.upper():
                # SQLite 不许 ALTER 出来一个主键列。真碰上说明这张表被换过血，
                # 那就不是「补一列」能解决的，别硬撑着改。
                stuck.append("%s.%s（是主键列，ALTER 加不了）" % (t, cname))
                continue
            try:
                x("ALTER TABLE %s ADD COLUMN %s" % (t, decl))
                added.append("%s.%s" % (t, cname))
            except sqlite3.Error as e:
                stuck.append("%s.%s（%s）" % (t, cname, e))
    return added, stuck


def check_schema():
    """库里现有的表结构和代码期望的对不上吗？
    返回 {"缺表": [...], "缺列": [...]}，都对得上就两个空列表。

    这是给**诊断**用的（自测、排查），启动流程走的是 _add_missing_columns()
    那条路 —— 它会真的把缺的列补上，而不是拦在门口。"""
    have_tables = {r[0] for r in q("SELECT name FROM sqlite_master WHERE type='table'")}
    no_table, no_col = [], []
    for t, cols in want_tables().items():
        if t not in have_tables:
            no_table.append(t)
            continue
        have = {r[1] for r in q("PRAGMA table_info(%s)" % t)}
        for cname, _decl in cols:
            if cname not in have:
                no_col.append("%s.%s" % (t, cname))
    return {"缺表": no_table, "缺列": no_col}


def is_empty():
    """还没迁过数据（四张主表全空）"""
    return (one("SELECT COUNT(*) FROM bill", (), 0) == 0
            and one("SELECT COUNT(*) FROM check_val", (), 0) == 0
            and one("SELECT COUNT(*) FROM stock", (), 0) == 0
            and one("SELECT COUNT(*) FROM tail", (), 0) == 0)


# 表名 → 中文名（备份列表、调试信息里显示用）
TABLES = {
    "bill": "账单流水", "tail": "周边尾款", "budget": "月度预算",
    "cat": "类别", "check_val": "打卡记录", "check_cfg": "打卡设置",
    "dream": "梦境", "stock": "物资", "stock_header": "物资表头",
    "todo": "待办", "em_field": "应急信息", "em_contact": "紧急联系人",
    "attach": "附件", "kv": "杂项",
}


def counts():
    return {t: one("SELECT COUNT(*) FROM %s" % t, (), 0) for t in TABLES}


def vacuum():
    with _write_lock:
        conn().execute("VACUUM")


def snapshot(dest):
    """把数据库完整拷到 dest（用 SQLite 自己的备份接口，写到一半也不怕）"""
    d = os.path.dirname(dest)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = dest + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    tgt = sqlite3.connect(tmp)
    try:
        conn().backup(tgt)
    finally:
        tgt.close()
    os.replace(tmp, dest)
    return dest


def restore_from(path):
    """把另一个库的内容整体灌回当前库。

    **为什么不直接换文件**：Windows 上只要还有别的线程握着这个库的句柄，
    替换就会被拒；而且就算换成了，那些连接手里还是旧文件，之后写进去的数据
    会凭空消失。用 SQLite 自己的备份接口**反向写进去**就没这些事 ——
    不换文件、不关连接、别的线程完全不知情。
    调用方负责先备份当前状态（这个操作不可逆）。"""
    src = sqlite3.connect(path)
    try:
        src.backup(conn())
    finally:
        src.close()
    bump()


def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")
