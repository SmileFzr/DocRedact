#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成用于真实测试的 PDF：文本层 / 纯图片 / 图文混排 / 小字密集 四种页面。"""

# --- 统一入口：无论从哪个目录执行，都以仓库根目录为工作目录 ---
import os as _os, sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
_os.chdir(_ROOT)
_sys.path.insert(0, str(_ROOT))
_ROOT.joinpath("outputs").mkdir(exist_ok=True)

import fitz

FONT = r"C:\Windows\Fonts\simhei.ttf"
OUT = "outputs/_TEST_sample.pdf"

TEXT_P1 = [
    ("品牌分析报告 2026 Q3", 20),
    ("NICETOWN 品牌在美站窗帘类目的表现优于 MIULEE。", 12),
    ("本章重点分析遮光面料的竞争格局，遮光性能是核心卖点。", 12),
    ("同一行出现两次遮光遮光，用于测试同行多次命中。", 12),
    ("非遮光款客单价更低，遮光率 99% 是主要卖点。", 12),
    ("联系人：张伟  手机 13812345678  邮箱 zhangwei@example.com", 12),
    ("订单号：SN-2026-0042  金额：$1,234.56  折扣 15%", 12),
    ("备注：以上数据仅内部使用，请勿外传。", 12),
]


def draw_lines(page, lines, x=56, y=80, gap=30):
    cur = y
    for text, size in lines:
        page.insert_text((x, cur), text, fontsize=size,
                         fontname="F0", fontfile=FONT)
        cur += gap
    return cur


def render_page_png(lines, width=595, height=842):
    """把文字画到临时页 → 渲染成 PNG 字节（模拟扫描件/截图）。"""
    tmp = fitz.open()
    p = tmp.new_page(width=width, height=height)
    draw_lines(p, lines)
    png = p.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
    tmp.close()
    return png


def main():
    doc = fitz.open()

    # ── 第 1 页：纯文本层，中英混排 ──────────────────────
    p1 = doc.new_page(width=595, height=842)
    draw_lines(p1, TEXT_P1)

    # ── 第 2 页：纯图片（无文本层），模拟扫描件 ──────────
    p2 = doc.new_page(width=595, height=842)
    png = render_page_png(TEXT_P1[1:7])
    p2.insert_image(fitz.Rect(40, 60, 555, 780), stream=png)

    # ── 第 3 页：图文混排，正文有文本层 + 图表截图里也有字 ──
    p3 = doc.new_page(width=595, height=842)
    draw_lines(p3, [
        ("三、图文混排页（正文可选中，图表是图片）", 15),
        ("正文段落：NICETOWN 遮光窗帘在天猫渠道增长 23%。", 12),
        ("下图是竞品价格分布图表，图里也写了品牌名。", 12),
    ])
    chart = fitz.open()
    cp = chart.new_page(width=520, height=300)
    cp.draw_rect(fitz.Rect(0, 0, 520, 300), color=(0.9, 0.9, 0.9),
                 fill=(1, 1, 1), width=1)
    cp.insert_text((16, 26), "Price Distribution - Curtain Category", fontsize=13,
                   fontname="helv")
    bars = [(40, 220, 70), (110, 160, 90), (180, 120, 120), (250, 180, 100),
            (320, 90, 150), (390, 200, 80)]
    for i, (bx, bh, bw) in enumerate(bars):
        cp.draw_rect(fitz.Rect(bx, 270 - bh, bx + bw, 270),
                     color=None, fill=(0.55, 0.45, 0.35))
        cp.insert_text((bx, 288), f"Brand{i+1}", fontsize=8, fontname="helv")
        cp.insert_text((bx, 270 - bh - 6), f"${18 + i * 4}", fontsize=8,
                       fontname="helv")
    cp.insert_text((16, 60), "Source: NICETOWN internal data, 遮光 line", fontsize=11,
                   fontname="F0", fontfile=FONT)
    cpng = cp.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
    chart.close()
    p3.insert_image(fitz.Rect(40, 150, 555, 447), stream=cpng)

    # ── 第 4 页：小字号密集文本 ──────────────────────────
    p4 = doc.new_page(width=595, height=842)
    p4.insert_text((56, 70), "四、小字号密集条款（8pt）", fontsize=15,
                   fontname="F0", fontfile=FONT)
    y = 100
    for i in range(14):
        p4.insert_text(
            (56, y),
            f"{i+1:02d}. 用户 张伟 于 2026-03-{i+1:02d} 申请遮光配件售后，"
            f"电话 1381234567{i%10}，处理人 NICETOWN-CS。",
            fontsize=8, fontname="F0", fontfile=FONT)
        y += 18

    doc.save(OUT)
    doc.close()

    # 报告结构，便于核对
    d = fitz.open(OUT)
    print("生成:", OUT, "页数:", len(d))
    for i, page in enumerate(d):
        t = page.get_text().strip()
        print(f"  第{i+1}页 文本层 {len(t)} 字 | 图片数 {len(page.get_images())}")
    d.close()

    # ── 额外生成一张图片（模拟手机截图），用于测试图片格式遮罩 ──
    shot = fitz.open()
    sp = shot.new_page(width=420, height=260)
    sp.draw_rect(fitz.Rect(0, 0, 420, 260), color=None, fill=(1, 1, 1))
    draw_lines(sp, [
        ("聊天记录截图", 16),
        ("张伟：这批遮光窗帘的 NICETOWN 报价是多少？", 11),
        ("客服：13812345678，邮箱 service@nicetown.com", 11),
        ("张伟：收到，遮光率 99% 那款先来 200 套。", 11),
    ], x=20, y=40, gap=34)
    png_img = sp.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
    shot.close()
    with open("outputs/_TEST_shot.png", "wb") as f:
        f.write(png_img)
    print("生成: outputs/_TEST_shot.png")


if __name__ == "__main__":
    main()
