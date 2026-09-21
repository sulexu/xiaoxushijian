# -*- coding: utf-8 -*-
"""Markdown → Word（.docx）。给 项目历程.md / 项目交接.md 用。

跑：python _md转word.py 项目历程.md
    python _md转word.py            # 不带参数就把两份都转一遍

为什么不直接把 .md 甩给 Word：Word 打开 .md 是一片带井号和竖线的原文，
而这两份文档都有**表格**（版本索引表、坑表），手画一遍不现实。

支持的范围就是这两份文档真用到的那几样：
    # ## ###      标题
    | a | b |     表格（含表头分隔行）
    -  / 1.       列表
    > 引用
    ---           分隔线
    ``` 代码块
    **加粗**  `行内代码`（可以套着写）

不追求完整 Markdown —— 用不上的语法不写，省得下次有人以为这能当通用转换器使。

━━━ 两个已经栽过的坑，别拆 ━━━

① **硬换行必须合并成一段。** 这两份 .md 是手工折行的，一行就是一句半。
   第一版按「一行 = 一段」渲染，结果 项目历程 出了 607 个段落、平均 26 字，
   读起来像被人掐着脖子说话；更要命的是 `**它没有问，直接在` /
   `「文档\\小煦拾简」新建了一个空库**` 这种**跨行的加粗**，
   行内解析器看不到配对的星号，直接把 `**` 原样打进了 Word（8 处）。
   现在用 _blocks() 先做一遍块级归并，行内解析只处理合并后的整段。

② **加粗里面嵌反引号要递归。** 源里写的是
   `**必须同时登记进 \\`SETTINGS_DEFAULTS\\`**` —— 先按 `**` 切，
   拿到 chunck 后**还得再按反引号切一遍**。不递归的话那个内层反引号
   会跟着进 Word（项目交接 里 46 处）。修在 _emit() 里。
"""
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from docx import Document                                    # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH                # noqa: E402
from docx.oxml.ns import qn                                  # noqa: E402
from docx.shared import Pt, RGBColor                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CN = "微软雅黑"
MONO = "Consolas"
ACCENT = RGBColor(0x6B, 0x5B, 0x3E)
GREY = RGBColor(0x8C, 0x81, 0x71)

RE_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")      # 表头下的 |---|---|
RE_LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
RE_HEAD = re.compile(r"^(#{1,4})\s+(.*)$")
RE_RULE = re.compile(r"^-{3,}$")
RE_FENCE = re.compile(r"^\s*```")


def set_font(run, name=CN, size=None, bold=None, mono=False, color=None):
    run.font.name = MONO if mono else name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def _emit(p, text, size, bold, color):
    """只管反引号这一层 —— 加粗已经在上面剥掉了。"""
    for chunk in re.split(r"(`[^`]+`)", text):
        if not chunk:
            continue
        if len(chunk) > 2 and chunk.startswith("`") and chunk.endswith("`"):
            set_font(p.add_run(chunk[1:-1]), size=size, bold=bold,
                     mono=True, color=color)
        else:
            set_font(p.add_run(chunk), size=size, bold=bold, color=color)


def add_rich(p, text, size, bold_all=False, color=None):
    """渲染 `**加粗**` 和 `` `行内代码` ``，两者可以嵌套。

    ⚠ 不处理的话星号和反引号会**原样打进 Word** —— 这两份文档里到处都是
      `` **必须同时登记进 `SETTINGS_DEFAULTS`** ``，直接贴过去就是满屏符号。"""
    for chunk in re.split(r"(\*\*.+?\*\*)", text):
        if not chunk:
            continue
        if len(chunk) > 4 and chunk.startswith("**") and chunk.endswith("**"):
            _emit(p, chunk[2:-2], size, True, color)      # ← 内层再切一次反引号
        else:
            _emit(p, chunk, size, bold_all, color)


def split_row(line):
    """`| a | b |` → ['a', 'b']。⚠ 两头的空段要丢掉，否则每张表都多一列。"""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _join(prev, nxt):
    """折行的两截怎么接。中文直接贴（接缝在句子中间），英文补个空格。"""
    if not prev:
        return nxt
    if prev[-1].isascii() and prev[-1].isalnum() and nxt[:1].isascii() and nxt[:1].isalnum():
        return prev + " " + nxt
    return prev + nxt


def _blocks(lines):
    """预处理：把「一行一段」归并成真正的块。

    ⚠ 这是整个转换器的地基。_render 只认这里吐出来的东西 ——
      要加新语法（比如嵌套列表）在这里加，别去后面打补丁。"""
    out, i, n = [], 0, len(lines)
    buf = []                                   # 攒着的普通正文行
    # ⚠ 空字典是「没有列表项」的哨兵，不是 None —— flush() 里对它调的是
    #   .clear()。写成 None 会在第一个列表项上炸 AttributeError（已经炸过）。
    lst = {}                                   # 攒着的列表项 {"txt":..,"ind":..}

    def flush():
        if buf:
            out.append(("p", "".join(buf)))
            del buf[:]
        if lst:
            out.append(("li", lst["txt"], lst["ind"]))
            lst.clear()

    while i < n:
        raw = lines[i].rstrip()
        s = raw.strip()
        if not s:
            flush()
            i += 1
            continue
        if RE_FENCE.match(s):
            flush()
            i += 1
            code = []
            while i < n and not RE_FENCE.match(lines[i]):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(("code", "\n".join(code)))
            continue
        if s.startswith("|") and i + 1 < n and RE_SEP.match(lines[i + 1]):
            flush()
            head = split_row(s)
            i += 2
            body = []
            while i < n and lines[i].strip().startswith("|"):
                body.append(split_row(lines[i]))
                i += 1
            out.append(("table", head, body))
            continue
        if RE_RULE.match(s):
            flush()
            out.append(("rule",))
            i += 1
            continue
        m = RE_HEAD.match(s)
        if m:
            flush()
            out.append(("h", len(m.group(1)), m.group(2)))
            i += 1
            continue
        if s.startswith(">"):
            flush()
            q = []
            while i < n and lines[i].strip().startswith(">"):
                q.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(("quote", " ".join(x for x in q if x)))
            continue
        m = RE_LIST.match(raw)
        if m:
            flush()
            lst.update(txt=m.group(3), ind=len(m.group(1)))
            i += 1
            continue
        # 剩下两种：普通正文；以及「缩进且不是列表标记」= 上一项的折行续写
        if lst and raw[:1] in (" ", "\t") and not m:
            lst["txt"] = _join(lst["txt"], s)
            i += 1
            continue
        if lst:
            flush()
        # ⚠ 必须**就地接在 buf[0] 上**，不能 append 一个已合并的新串 ——
        #   写成 buf.append(_join(buf[-1], s)) 会让 buf 变成
        #   [行1, 行1+行2, 行1+行2+行3, …]，最后 join 出来整段是平方级重复
        #   （2.4.5 这一版真炸过：一段 70 字印成 140 字）。
        if buf:
            buf[0] = _join(buf[0], s)
        else:
            buf.append(s)
        i += 1
    flush()
    return out


def _render(doc, blocks, cover_title=None):
    for b in blocks:
        kind = b[0]
        if kind == "h":
            lv, txt = b[1], b[2]
            if lv == 1 and cover_title:
                continue                       # 标题已经在封面上，正文里不再重复
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(14 if lv <= 2 else 9)
            p.paragraph_format.space_after = Pt(4)
            add_rich(p, txt, {1: 20, 2: 15.5, 3: 12.5, 4: 11.5}[lv],
                     bold_all=(lv <= 3), color=ACCENT if lv <= 2 else None)
        elif kind == "code":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(20)
            p.paragraph_format.space_after = Pt(6)
            for k, ln in enumerate(b[1].split("\n")):
                if k:
                    p.add_run("\n")
                set_font(p.add_run(ln), size=9, mono=True)
        elif kind == "table":
            head, body = b[1], b[2]
            t = doc.add_table(rows=1, cols=len(head))
            t.style = "Table Grid"
            for c, txt in enumerate(head):
                cell = t.rows[0].cells[c]
                cell.text = ""
                add_rich(cell.paragraphs[0], txt, 10, bold_all=True)
            for row in body:
                cells = t.add_row().cells
                for c in range(len(head)):
                    cells[c].text = ""
                    add_rich(cells[c].paragraphs[0], row[c] if c < len(row) else "", 9.5)
            doc.add_paragraph()
        elif kind == "rule":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            set_font(p.add_run("─" * 30), size=8, color=GREY)
        elif kind == "li":
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.left_indent = Pt(18 + b[2] * 10)
            p.paragraph_format.space_after = Pt(2)
            add_rich(p, b[1], 10)
        elif kind == "quote":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(20)
            p.paragraph_format.space_after = Pt(6)
            add_rich(p, b[1], 9.5, color=GREY)
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            add_rich(p, b[1], 10.5)


def md_to_doc(md_path, docx_path, cover_title=None, sub=""):
    lines = io.open(md_path, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = CN
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), CN)

    if cover_title:
        for _ in range(4):
            doc.add_paragraph()
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_font(p.add_run(cover_title), size=30, bold=True, color=ACCENT)
        if sub:
            doc.add_paragraph()
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_font(p.add_run(sub), size=12, color=GREY)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_font(p.add_run("拾寸简以记，沐小煦而行"), size=12, color=GREY)
        doc.add_page_break()

    blocks = _blocks(lines)
    _render(doc, blocks, cover_title)
    doc.save(docx_path)
    return blocks


JOBS = [("项目历程.md", "项目历程.docx", "项目历程",
         "从 1.0 到 2.4.6：每个版本改了什么、修过什么问题"),
        ("项目交接.md", "项目交接.docx", "项目交接",
         "改代码之前要读什么"),
        ("用户需求和决策习惯.md", "用户需求和决策习惯.docx", "用户需求与决策习惯",
         "跟这个人怎么配合 —— 四份文档里唯一一份讲「人」的")]


def main():
    args = sys.argv[1:]
    jobs = [j for j in JOBS if not args or j[0] in args]
    if args and not jobs:
        jobs = [(a, os.path.splitext(a)[0] + ".docx", os.path.splitext(a)[0], "") for a in args]
    for src, dst, title, sub in jobs:
        sp, dp = os.path.join(HERE, src), os.path.join(HERE, dst)
        if not os.path.isfile(sp):
            print("没有这个文件：%s" % src)
            continue
        blocks = md_to_doc(sp, dp, title, sub)
        kinds = {}
        for b in blocks:
            kinds[b[0]] = kinds.get(b[0], 0) + 1
        print("写好了：%s" % dp)
        print("  段落 %d，明细：%s" % (
            len([b for b in blocks if b[0] == "p"]),
            "、".join("%s×%d" % (k, v) for k, v in sorted(kinds.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
