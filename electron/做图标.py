# -*- coding: utf-8 -*-
"""生成应用图标 build/icon.ico —— 不依赖任何图像库。

为什么要自己画：装 Pillow 只为了生成一张图标不值当，而这个图标本身很简单
（圆角方块 + 三根柱子），用有符号距离场（SDF）逐像素算一下就能得到带抗锯齿的
边缘，比先渲染大图再缩小还干净。

图形：蓝色圆角方块（#2563eb，跟界面主色一致）+ 三根白色圆角柱子（柱状图意象）
输出：16/24/32/48/64/128/256 七个尺寸打包成一个 .ico
      （Vista 以后 ICO 允许直接内嵌 PNG，比老的 BMP 格式小很多）

跑：python 做图标.py
"""
import math
import os
import struct
import zlib

BG = (37, 99, 235)          # #2563eb
FG = (255, 255, 255)
MASTER = 1024               # 先按 1024 渲染，再降采样到各尺寸
SIZES = [16, 24, 32, 48, 64, 128, 256]


def rounded_rect(x, y, x0, y0, x1, y1, r):
    """圆角矩形的有符号距离：负数在内部，绝对值约等于到边缘的距离"""
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hw, hh = (x1 - x0) / 2.0 - r, (y1 - y0) / 2.0 - r
    dx = abs(x - cx) - hw
    dy = abs(y - cy) - hh
    ax, ay = (dx if dx > 0 else 0.0), (dy if dy > 0 else 0.0)
    return math.hypot(ax, ay) + (min(max(dx, dy), 0.0)) - r


def render_master():
    """按 1024×1024 渲染，返回 RGBA 字节。SDF 直接给出覆盖率，所以边缘天然抗锯齿。"""
    S = MASTER
    u = S / 256.0                     # 以 256 为设计尺寸，换算到实际像素
    # 背景：留 6 单位边距的圆角方块
    bg = (6 * u, 6 * u, 250 * u, 250 * u, 54 * u)
    # 三根柱子：宽 34、间距 20，底边对齐，高度递增
    bar_w, gap, bottom = 34 * u, 20 * u, 196 * u
    total = 3 * bar_w + 2 * gap
    x = (S - total) / 2.0
    bars = []
    for top in (142 * u, 108 * u, 74 * u):
        bars.append((x, top, x + bar_w, bottom, 11 * u))
        x += bar_w + gap

    out = bytearray(S * S * 4)
    i = 0
    for py in range(S):
        y = py + 0.5
        for px in range(S):
            xx = px + 0.5
            cov = 0.5 - rounded_rect(xx, y, *bg)      # 覆盖率先按背景算
            if cov <= 0:
                out[i:i + 4] = b"\x00\x00\x00\x00"
                i += 4
                continue
            a = 1.0 if cov >= 1 else cov
            r, g, b = BG
            for bar in bars:                          # 柱子叠在背景上
                c = 0.5 - rounded_rect(xx, y, *bar)
                if c > 0:
                    w = 1.0 if c >= 1 else c
                    r = int(r + (FG[0] - r) * w)
                    g = int(g + (FG[1] - g) * w)
                    b = int(b + (FG[2] - b) * w)
            out[i] = r
            out[i + 1] = g
            out[i + 2] = b
            out[i + 3] = int(255 * a)
            i += 4
    return bytes(out), S


def downscale(rgba, src, dst):
    """盒式降采样。预乘 alpha 再平均，否则透明边缘会发黑"""
    out = bytearray(dst * dst * 4)
    block = src / float(dst)
    for dy in range(dst):
        y0, y1 = int(dy * block), int((dy + 1) * block)
        for dx in range(dst):
            x0, x1 = int(dx * block), int((dx + 1) * block)
            sa = sr = sg = sb = 0
            n = 0
            for yy in range(y0, y1):
                base = yy * src * 4
                for xx in range(x0, x1):
                    j = base + xx * 4
                    a = rgba[j + 3]
                    sr += rgba[j] * a
                    sg += rgba[j + 1] * a
                    sb += rgba[j + 2] * a
                    sa += a
                    n += 1
            if not n:
                continue
            k = dy * dst * 4 + dx * 4
            if sa:
                out[k] = min(255, sr // sa)
                out[k + 1] = min(255, sg // sa)
                out[k + 2] = min(255, sb // sa)
                out[k + 3] = sa // n
    return bytes(out)


def png_bytes(w, h, rgba):
    raw = bytearray()
    for y in range(h):
        raw.append(0)                       # 每行前面一个 filter 字节
        raw += rgba[y * w * 4:(y + 1) * w * 4]

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def ico_bytes(images):
    """images = [(尺寸, png 字节)]。Vista+ 支持 ICO 里直接放 PNG"""
    n = len(images)
    head = struct.pack("<HHH", 0, 1, n)
    offset = 6 + 16 * n
    entries, blobs = b"", b""
    for size, png in images:
        entries += struct.pack("<BBBBHHII",
                               0 if size >= 256 else size,     # 256 要写 0
                               0 if size >= 256 else size,
                               0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    return head + entries + blobs


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "build")
    os.makedirs(out_dir, exist_ok=True)
    print("渲染 %d×%d 母图…" % (MASTER, MASTER))
    master, S = render_master()
    images = []
    for s in SIZES:
        rgba = downscale(master, S, s) if s != S else master
        images.append((s, png_bytes(s, s, rgba)))
        print("   %3d×%-3d  %6d 字节" % (s, s, len(images[-1][1])))
    ico = ico_bytes(images)
    path = os.path.join(out_dir, "icon.ico")
    with open(path, "wb") as f:
        f.write(ico)
    print("已写出 %s（%d 字节）" % (path, len(ico)))

    # 顺手存一张 256 的 PNG，方便预览
    with open(os.path.join(out_dir, "icon_preview.png"), "wb") as f:
        f.write(dict(images)[256])
    print("已写出 build/icon_preview.png（预览用）")


if __name__ == "__main__":
    main()
