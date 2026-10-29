#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 DocRedact 程序图标（icon.ico，多尺寸）。

设计语言与 web_ui 的亚麻棉配色一致：
  亚麻深底 + 米白纸面 + 一道墨色遮罩条
16px 下仍可辨认：纸面占满画面，遮罩条足够粗。

用法：python tools/make_icon.py
产出：icon.ico（16/24/32/48/64/128/256）、docs/icon-preview.png
"""

import os as _os, sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parent.parent
_os.chdir(_ROOT)
_sys.path.insert(0, str(_ROOT))

from PIL import Image, ImageDraw

S = 1024                      # 绘制用的高清画布
LINEN = (110, 95, 73)         # 亚麻深棕（底）
PAPER = (248, 245, 237)       # 米白（纸面）
RULE = (206, 193, 168)        # 纸上的横线
INK = (31, 28, 23)            # 遮罩条（墨色）
ACCENT = (186, 117, 23)       # 琥珀点缀


def draw_icon(bg_radius=S // 5) -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角底
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=bg_radius, fill=LINEN)

    # 纸面（略微内缩，带一点透视感）
    px0, py0, px1, py1 = 214, 150, 810, 890
    d.rounded_rectangle([px0, py0, px1, py1], radius=34, fill=PAPER)

    # 纸面上的三行文字：中间那行被遮罩条盖住
    # 所有内容都内缩在纸面以内（纸面 214~810），避免任何元素探出边缘
    lines = [(300, 270, 754), (438, 270, 754), (576, 270, 700)]
    for i, (y, x0, x1) in enumerate(lines):
        if i == 1:
            continue                      # 留给遮罩条
        d.rounded_rectangle([x0, y, x1, y + 52], radius=26, fill=RULE)

    # 遮罩条：比上下两行更粗，左右对称地略宽一点 —— 「盖住」的语义
    d.rounded_rectangle([246, 410, 778, 518], radius=16, fill=INK)

    # 纸面右下角一枚琥珀色小方块，呼应 UI 的主题色
    d.rounded_rectangle([640, 700, 782, 842], radius=20, fill=ACCENT)
    d.rounded_rectangle([672, 742, 750, 772], radius=14, fill=PAPER)

    return img


def main():
    base = draw_icon()

    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [base.resize((n, n), Image.LANCZOS) for n in sizes]

    out = _ROOT / "icon.ico"
    frames[-1].save(out, format="ICO", sizes=[(n, n) for n in sizes])
    print(f"已生成 {out}  尺寸: {sizes}")

    # 预览图：把各尺寸并排画出来，方便肉眼检查小尺寸是否糊
    pad, gap = 24, 28
    total_w = pad * 2 + sum(sizes) + gap * (len(sizes) - 1)
    total_h = pad * 2 + max(sizes)
    sheet = Image.new("RGBA", (total_w, total_h), (247, 243, 234, 255))
    x = pad
    for n, fr in zip(sizes, frames):
        sheet.paste(fr, (x, total_h - pad - n), fr)
        x += n + gap

    prev = _ROOT / "docs" / "icon-preview.png"
    prev.parent.mkdir(exist_ok=True)
    sheet.save(prev)
    print(f"已生成 {prev}")


if __name__ == "__main__":
    main()
