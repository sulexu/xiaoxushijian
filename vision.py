# -*- coding: utf-8 -*-
r"""看图录入：账单截图 → 一笔账；睡眠截图 → 打卡

**整个流程是「识别 → 核对 → 确认才写库」，中间那步不能省。**
模型看错一个数字是常事，而账目和睡眠记录是长期数据，错一笔要翻半天。
所以这个模块**只负责认**，一个字都不往库里写；写库永远是用户点了确认之后，
走的是普通那条 bill/add、check/set 通路 —— 跟手动输的完全一样，
出错也好排查（不会出现「AI 专线写坏了没人知道」这种事）。

图片存文件、不存数据库：`附件\YYYYMM\`。库里只记元信息 ——
图进数据库会让备份和应用体积一起膨胀，不值当。

模型必须自己会看图，**不是所有模型都行**。所以单独留一个「看图模型」设置，
默认跟着主模型走；哪天主模型不支持图片，改这一个就行，不用动别的。
"""
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime

# 单张图上限。手机截图两三兆很正常，base64 之后还要再涨三分之一，
# 太大就直接挡下来并告诉用户 —— 让接口去报「请求体过大」的错，更难看懂。
MAX_BYTES = 5 * 1024 * 1024
EXT_OF = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
          "image/webp": ".webp", "image/gif": ".gif", "image/bmp": ".bmp"}


# ================================================================
# 存图
# ================================================================
def save_image(root, store, data_url, kind):
    """把 data URL 落成文件，并在 attach 表里记一笔。返回 (ok, msg/信息, 附件id)"""
    m = re.match(r"^data:([\w/+.-]+);base64,(.*)$", data_url or "", re.S)
    if not m:
        return False, "图片格式认不出来（要 data:image/...;base64, 开头的）", None
    mime, b64 = m.group(1).lower(), m.group(2)
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:
        return False, "图片数据坏了，解不开", None
    if not raw:
        return False, "图片是空的", None
    if len(raw) > MAX_BYTES:
        return False, "图片太大了（%.1fMB，上限 %dMB）。裁一下再传，或者用手机自带的「编辑」压一下。" % (
            len(raw) / 1048576.0, MAX_BYTES // 1048576), None

    ext = EXT_OF.get(mime, ".png")
    digest = hashlib.sha1(raw).hexdigest()[:16]
    sub = datetime.now().strftime("%Y%m")
    folder = os.path.join(root, "附件", sub)
    os.makedirs(folder, exist_ok=True)
    name = "%s%s" % (digest, ext)
    full = os.path.join(folder, name)
    if not os.path.exists(full):          # 同一张图传两次就复用，不重复占地方
        with open(full, "wb") as f:
            f.write(raw)
    rel = "%s/%s" % (sub, name)
    with store.tx("stock") as c:
        c.execute("INSERT INTO attach(kind,ref,file,mime,bytes,made)"
                  " VALUES(?,?,?,?,?,?)",
                  (kind, "", rel, mime, len(raw), store.now_str()))
        aid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    return True, {"file": rel, "bytes": len(raw), "id": aid}, aid


# ================================================================
# 提示词
# ================================================================
BILL_SYS = """你在帮用户把一张支付截图（微信/支付宝账单列表、外卖订单、银行流水等）里的
**每一笔交易**逐条读出来。用户要把它们一条条记进账本。

只输出 JSON，不要解释、不要客套、不要 markdown 代码块：
{"items":[{"date":"YYYY-MM-DD","amount":0.00,"direction":"支出","cat":"","note":"","pay":""}],
 "confidence":"high","warn":""}

⚠ **最重要的一条：把截图里所有交易都列出来，一条都不能漏。**
一屏有 8 条就输出 8 个，有 15 条就输出 15 个。只输出一条是最严重的错误。

哪些**不是**交易，不要输出：
- 表头那一行（「日期 / 金额 / 商户」之类的列名）
- 「合计」「小计」「总计」「本页共 N 笔」这类汇总行
- 筛选条件、搜索框、按钮上的字

同一次付款拆成多行商品明细时（比如外卖里「米饭 2.00 + 宫保鸡丁 18.00」），
**截图显示成几行就输出几条**；只有截图明确合成一笔（只给一个总金额）时才输出一条。

每条的字段：
- date     交易日期。截图里没有就留空字符串（**不要编今天的日期**）
- amount   金额，正数，只留数字
- direction 只能是「支出」或「收入」。付款/消费/转出是支出；收款/退款/红包到账是收入
- cat      花在哪一类，**只能从这个清单里挑一个**：%s
- note     项目或商家名，尽量短（如「食堂」「打车」「买书」）
- pay      付款方式，只能从这几种里挑：%s

顶层：
- confidence  你对整张图识别结果的把握："high" / "medium" / "low"
- warn        有哪条看不清、拿不准，用一句话说明；没问题就留空

⚠ 看不清的字段一律留空，**绝对不要猜**。某一条金额看不清就把那条的 amount 填 0
并在 warn 里说明；但**不要因为看不清就把它整条丢掉** —— 漏一条比差一个数更难发现。"""

SLEEP_SYS = """你在帮用户从一张睡眠记录截图（手环/手表/手机健康 App）里，
读出「每日打卡」需要的作息信息。

只输出 JSON，不要解释、不要客套、不要 markdown 代码块：
{"date":"YYYY-MM-DD","sleep":"","wake":"","hours":0,"quality":"","wake_count":null,
 "screen":null,"confidence":"high","warn":""}

字段说明：
- date        这一晚对应的日期（一般填**起床那天**）
- sleep       入睡时间，24 小时制 "HH:MM"
- wake        起床时间，24 小时制 "HH:MM"
- hours       睡了几个小时，可以带小数
- quality     睡眠质量，只能填：%s
- wake_count  夜里醒了几次，整数；截图没写就填 null
- screen      睡前看手机/屏幕的时长（小时），截图里没有就填 null
- confidence  把握程度："high" / "medium" / "low"
- warn        哪一项看不清就说明一下；没问题留空

⚠ 时间一律 24 小时制补零成 "HH:MM"。看不清的留空或 null，**不要猜**。"""


def _prompt(kind, schema):
    if kind == "bill":
        return BILL_SYS % ("、".join(schema.get("cats") or ["其他"]),
                           "、".join(schema.get("pays") or ["微信"]))
    return SLEEP_SYS % "、".join(schema.get("moods") or ["好", "一般", "差"])


# ================================================================
# 调模型
# ================================================================
def _post(cfg, model, messages, timeout=90):
    key = str(cfg.get("api_key") or "").strip()
    if not key:
        return False, "还没配置 API Key，先去「⚙ 设置 → AI」填上", None
    base = str(cfg.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
    payload = {"model": model, "messages": messages, "temperature": 0.1,
               "stream": False, "response_format": {"type": "json_object"}}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        if e.code == 400 and ("image" in detail.lower() or "multimodal" in detail.lower()
                              or "content" in detail.lower()):
            return False, ("这个模型看不了图。到「设置 → AI → 看图模型」换一个"
                           "能看图的（比如带 vision 字样的）。接口原话：%s" % detail[:100]), None
        hint = {401: "API Key 不对或已失效", 402: "账户余额不足",
                429: "请求太频繁或额度用尽"}.get(e.code, "")
        return False, "调用失败（HTTP %d）%s %s" % (e.code, hint, detail[:120]), None
    except urllib.error.URLError as e:
        return False, "连不上 %s：%s" % (base, e.reason), None
    except Exception as e:
        return False, "调用出错：%s" % e, None


def check_config(cfg):
    """动手之前先看配置齐不齐。返回 (model, 错误信息)。

    **要在存图之前调**：不然每次没配好就白落一张图在附件目录里，
    攒一堆孤儿，用户还得自己找地方删。
    顺序也有讲究 —— 先问 Key 再问模型：头一回用的人多半是 Key 还没填，
    这时候回一句「没设模型」会把人指到错的地方去。"""
    if not str(cfg.get("api_key") or "").strip():
        return "", "还没配置 API Key。去「⚙ 设置 → AI」填上，再回来看图录入。"
    model = (cfg.get("vision_model") or cfg.get("model") or "").strip()
    if not model:
        return "", "还没选模型。去「⚙ 设置 → AI」选一个能看图的模型。"
    return model, ""


MAX_ITEMS = 60          # 一张图最多认这么多条，多了多半是模型在胡说


def _norm_item(it, schema):
    """把模型给的一条整成我们认识的样子。认不出来的返回 None。

    **宁可留空也不要编**：这里只做规整和过滤，一个字的猜测都不加。"""
    if not isinstance(it, dict):
        return None
    amount = it.get("amount")
    if isinstance(amount, str):
        m = re.search(r"-?[\d.]+", amount.replace(",", ""))
        amount = float(m.group()) if m else 0.0
    try:
        amount = abs(float(amount or 0))
    except (TypeError, ValueError):
        amount = 0.0
    note = str(it.get("note") or it.get("merchant") or "").strip()[:60]
    date = str(it.get("date") or "").strip()[:10]
    if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        date = ""
    direction = "收入" if str(it.get("direction") or "").strip() == "收入" else "支出"
    cat = str(it.get("cat") or "").strip()
    print_ = str(it.get("pay") or "").strip()
    if cat not in (schema.get("cats") or []):
        cat = ""                       # 不在清单里就当没认出来，别硬塞
    if print_ not in (schema.get("pays") or []):
        print_ = ""
    # 既没金额又没说明的，基本是表头/合计那种噪声行
    if amount <= 0 and not note:
        return None
    return {"date": date, "amount": round(amount, 2), "direction": direction,
            "cat": cat, "note": note, "pay": print_}


def recognize(cfg, kind, data_url, schema, timeout=120):
    """认一张图。返回 (ok, 结果dict 或 错误, usage)

    账单返回 {"items": [...], "confidence":…, "warn":…}；睡眠返回单条字段。"""
    model, err = check_config(cfg)
    if err:
        return False, err, None
    messages = [{"role": "user", "content": [
        {"type": "text", "text": _prompt(kind, schema)},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]}]
    ok, data, err = _post(cfg, model, messages, timeout)
    if not ok:
        return False, data, None
    usage = data.get("usage")
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return False, "返回格式看不懂：%s" % json.dumps(data, ensure_ascii=False)[:150], usage
    txt = re.sub(r"^```(?:json)?|```$", "", (content or "").strip(),
                 flags=re.M).strip()
    try:
        got = json.loads(txt)
    except Exception:
        return False, "模型没按格式回（应该是一段 JSON）：%s" % txt[:150], usage
    if not isinstance(got, dict):
        return False, "模型回的不是一个对象", usage

    if kind != "bill":
        return True, got, usage

    # ---- 账单：规整成条目列表 ----
    raw = got.get("items")
    if raw is None:
        # 容错：万一模型还是按老格式回了单个对象，包成一条，别让用户白跑一趟
        raw = [got] if (got.get("amount") or got.get("note")) else []
    if not isinstance(raw, list):
        raw = []
    items, dropped = [], 0
    for it in raw[:MAX_ITEMS]:
        one = _norm_item(it, schema)
        if one:
            items.append(one)
        else:
            dropped += 1
    if not items:
        return False, ("这张图里没认出交易。可能截图太糊、或者截的不是账单列表。"
                       "换一张清楚点的试试。"), usage
    warn = str(got.get("warn") or "").strip()
    if dropped:
        # 把「过滤掉几行」明说出来 —— 悄悄丢掉才是最难发现的
        warn = (warn + " " if warn else "") + "有 %d 行看不出是交易，已跳过。" % dropped
    if len(raw) > MAX_ITEMS:
        warn = (warn + " " if warn else "") + "图里有 %d 条，只取了前 %d 条。" % (
            len(raw), MAX_ITEMS)
    return True, {"items": items, "confidence": got.get("confidence") or "",
                  "warn": warn}, usage


def cleanup_orphans(root, store, days=30):
    """清掉没被任何记录引用、又放够久的图。

    识别完用户没点确认（或者干脆关了页面），那张图就成了孤儿。
    留着占地方，删了又不影响任何东西 —— 但**必须留足天数**：
    万一用户今天认完、过两天才想起来去确认，图不能先没了。"""
    import time as _t
    cutoff = _t.time() - days * 86400
    n = 0
    for r in store.q("SELECT id,file FROM attach WHERE ref=''"):
        full = os.path.join(root, "附件", r["file"].replace("/", os.sep))
        try:
            if os.path.isfile(full) and os.path.getmtime(full) < cutoff:
                os.remove(full)
                store.x("DELETE FROM attach WHERE id=?", (r["id"],))
                n += 1
        except OSError:
            pass
    return n
