# -*- coding: utf-8 -*-
"""把用户给的那张 1024×1024 插画做成多尺寸 .ico。

为什么要分档：一张图缩到 16px，四字标题会糊成一团墨点。所以
  · 256 / 128：完整构图（纸简 + 月亮 + 「小煦拾简」）
  · 64 / 48 / 32：去掉文字，只留纸简和月亮 —— 文字在这个尺寸只会变成噪点
  · 16：只剩三根竖线，单独再放大一档
每档单独裁切、单独缩放，而不是把一张图丢给 ICO 编码器让它一刀切。

跑法：python electron/做图标2.py
产出：electron/build/icon.ico、icon_预览.png（每个尺寸按真实像素画一遍，方便看效果）
"""
import os
import struct
import io as _io
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_NAME = "01033094-miora_text_to_image-1789479508928-0-485fbe2cfdca.jpg"


def _find_src():
    """插画是用户随手放进来的，位置不固定 —— 就近找几个地方"""
    up1 = os.path.dirname(HERE)                     # 统计系统\
    up2 = os.path.dirname(up1)                      # 个人信息统计\
    for c in (os.path.join(up2, "个人统计系统", ICON_NAME),
              os.path.join(up2, ICON_NAME),
              os.path.join(up1, ICON_NAME),
              os.path.join(HERE, ICON_NAME)):
        if os.path.isfile(c):
            return c
    raise SystemExit("找不到插画 %s，把它放到 %s 下再跑" % (ICON_NAME, up2))


SRC = _find_src()
OUT_DIR = os.path.join(HERE, "build")
ICO = os.path.join(OUT_DIR, "icon.ico")
PREVIEW = os.path.join(OUT_DIR, "icon_预览.png")

# 量出来的内容边界（见脚本里的量法：以背景色为基准算色差）
SLIPS = (259, 493, 336, 705)          # 三张纸简
TEXT = (241, 736, 480, 815)           # 「小煦拾简」
MOON = (721, 242, 782, 303)           # 右上那轮淡月


def square(box, side=None, margin=0.0):
    """把矩形扩成以它为中心的方形，方便等比缩放不 deformation"""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    s = side or max(x1 - x0, y1 - y0) * (1 + margin)
    return (int(cx - s / 2), int(cy - s / 2), int(cx + s / 2), int(cy + s / 2))


def union(*boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


# 三根纸简的相对高度（量自原图，底对齐）；金色也取自原图的纸简描边
SLIP_RATIOS = (0.76, 0.87, 1.00)
GOLD = (204, 166, 122)
CREAM = (249, 241, 218)
_BIG = 1024          # 先在大画布上画再缩下去，边缘才不会有锯齿


def mark_tile(size, radius_ratio=0.2):
    """小尺寸专用：金底 + 三根米色纸简。按真实像素画，不缩原图。"""
    from PIL import ImageDraw
    img = Image.new("RGB", (_BIG, _BIG), GOLD)
    d = ImageDraw.Draw(img)
    u = _BIG / 32.0                       # 以 32 格为设计单位
    d.rounded_rectangle([0, 0, _BIG - 1, _BIG - 1], radius=_BIG * radius_ratio, fill=GOLD)
    w, gap, h = 4.6, 3.4, 18.0
    x = (32 - (w * 3 + gap * 2)) / 2
    base = (32 + h) / 2
    for r in SLIP_RATIOS:
        bh = h * r
        d.rounded_rectangle([x * u, (base - bh) * u, (x + w) * u, base * u],
                            radius=w * u / 2, fill=CREAM)
        x += w + gap
    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    im = Image.open(SRC).convert("RGB")
    W, H = im.size

    # ① 完整构图：纸简 + 月亮 + 文字，方形裁切，四周留一点空
    full = square(union(SLIPS, TEXT, MOON), side=700)
    # ② 无字构图：纸简 + 月亮（文字在这档只会糊）
    nolabel = square(union(SLIPS, MOON), side=600)
    # ③ 极小档：只留三根纸简，再放大一档留点呼吸
    tiny = square(SLIPS, side=260)

    def crop(box, size):
        x0, y0, x1, y1 = box
        # 裁切区域必须落在图里，越界就把整块平移回来
        if x0 < 0: x1 -= x0; x0 = 0
        if y0 < 0: y1 -= y0; y0 = 0
        if x1 > W: x0 -= (x1 - W); x1 = W
        if y1 > H: y0 -= (y1 - H); y1 = H
        return im.crop((x0, y0, x1, y1)).resize((size, size), Image.LANCZOS)

    # 小尺寸不再用「缩小的插画」：原图线条只有 8~14px 宽（1024 底），缩到 32px 以下
    # 每根线不足 1 像素，会糊成一团灰雾（对比图在 build\_小图对比.png）。
    # 所以 64 及以下改成**按量出来的比例重画**的加粗版：金底 + 三根米色纸简。
    # 这跟开屏那枚「金底白字」的图标是同一个视觉，反而更统一。
    plan = [(256, full), (128, full), (64, None), (48, None), (32, None), (16, None)]
    frames = []
    for s, box in plan:
        frames.append((s, mark_tile(s, radius_ratio=0.20) if box is None else crop(box, s)))

    # ---- 手写 ICO 容器：每个尺寸塞一张 PNG。这样每档可以用不同的裁切 ----
    pngs = []
    for size, img in frames:
        buf = _io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        pngs.append((size, buf.getvalue()))
    header = struct.pack("<HHH", 0, 1, len(pngs))
    entries, offset = b"", 6 + 16 * len(pngs)
    for size, data in pngs:
        d = 0 if size >= 256 else size            # ICO 里 256 记作 0
        entries += struct.pack("<BBBBHHII", d, d, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(ICO, "wb") as f:
        f.write(header + entries + b"".join(d for _, d in pngs))
    print("写好 %s（%d 个尺寸，%d 字节）" % (ICO, len(pngs), os.path.getsize(ICO)))

    # ---- 预览图：每个尺寸按真实像素贴出来，旁边标尺寸 ----
    pad, x = 18, 16
    total_w = sum(s for s, _ in frames) + pad * (len(frames) + 1)
    maxh = max(s for s, _ in frames)
    sheet = Image.new("RGB", (total_w, maxh + 46), (250, 247, 240))
    for size, img in frames:
        sheet.paste(img, (x, 16 + (maxh - size) // 2))
        x += size + pad
    sheet.save(PREVIEW)
    print("写好 %s" % PREVIEW)
    print("  256/128px：完整插画（纸简 + 月亮 + 小煦拾简）")
    print("  64 及以下：金底 + 三根纸简（按原图比例重画的加粗版）")

    # 浏览器版要一枚 favicon（多个尺寸塞进一个 .png 不行，给 32px 就够）
    fav = os.path.join(os.path.dirname(HERE), "static", "favicon.png")
    mark_tile(64, radius_ratio=0.22).save(fav)
    print("写好 %s" % fav)


if __name__ == "__main__":
    main()
