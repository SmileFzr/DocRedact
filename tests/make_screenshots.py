#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 README 生成界面截图（用真实 UI 代码 + 演示数据渲染）。"""

# --- 统一入口：无论从哪个目录执行，都以仓库根目录为工作目录 ---
import os as _os, sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
_os.chdir(_ROOT)
_sys.path.insert(0, str(_ROOT))
_ROOT.joinpath("outputs").mkdir(exist_ok=True)

import base64
import subprocess
from pathlib import Path

import fitz

DOCS = Path("docs")
DOCS.mkdir(exist_ok=True)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

FONT = r"C:\Windows\Fonts\simhei.ttf"


def make_page_png():
    """造一张「遮罩后」的报告页示意图。"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 64
    lines = [
        ("Listing 数据分析报告", 17),
        ("NICETOWN 品牌在美站窗帘类目的表现", 12),
        ("", 8),
        ("一、市场概况", 13),
        ("美国窗帘市场年增速约 8%，遮光款占比持续提升。", 11),
        ("二、竞品对比", 13),
        ("价格带集中在 $18 - $35，材质以聚酯纤维为主。", 11),
        ("三、评论分析", 13),
        ("用户最关注遮光性与尺寸准确性，退货原因多为色差。", 11),
        ("四、结论与建议", 13),
        ("建议强化遮光卖点，优化尺寸标注与详情页文案。", 11),
    ]
    for text, size in lines:
        if text:
            page.insert_text((56, y), text, fontsize=size,
                             fontname="F0", fontfile=FONT)
        y += 28

    # 用文本搜索精确定位，模拟真实遮罩效果
    for kw in ("NICETOWN", "遮光", "MIULEE"):
        for rect in page.search_for(kw):
            page.draw_rect(rect + (-1, -1, 1, 1), color=None, fill=(0, 0, 0))

    png = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8)).tobytes("png")
    doc.close()
    return base64.b64encode(png).decode()


def build_demo(html, b64, tab):
    inject = f"""
<script>
S.files = [
 {{filename:'US(B09TT6C82J) 口碑评价分析 _ Listing数据深度解析报告.pdf',
   size:3738622, pages:4, kind:'pdf', filepath:'a'}},
 {{filename:'NICETOWN 竞品对比 2026Q3.docx', size:284000, pages:0, kind:'docx', filepath:'b'}}
];
S.keywords = [
 {{value:'遮光', regex:false}},
 {{value:'1[3-9]\\\\d{{9}}', regex:true, label:'手机号'}},
 {{value:'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{{2,}}', regex:true, label:'邮箱'}}
];
renderFiles(); renderKws();
log('遮罩完成，共遮挡 78 处', 'success');
log('查找完成，共 78 处' + '（文本层 68 · OCR 10）');
renderFind({{total:78, items:[
 {{name:'US(B09TT6C82J) 口碑评价分析 _ Listing数据深度解析报告.pdf', total:70,
  details:{{'遮光':{{text:21,ocr:7,pages:{{1:{{text:6,ocr:0}},2:{{text:0,ocr:5}},3:{{text:1,ocr:1}},4:{{text:14,ocr:1}}}}}},
           '手机号':{{text:15,ocr:1,pages:{{1:{{text:1,ocr:0}},2:{{text:0,ocr:1}},4:{{text:14,ocr:0}}}}}},
           '邮箱':{{text:1,ocr:0,pages:{{1:{{text:1,ocr:0}}}}}}}}}},
 {{name:'NICETOWN 竞品对比 2026Q3.docx', total:8,
  details:{{'遮光':{{text:8,ocr:0,pages:{{1:{{text:8,ocr:0}}}}}},
           '手机号':{{text:0,ocr:0,pages:{{}}}},
           '邮箱':{{text:0,ocr:0,pages:{{}}}}}}}}
]}});
S.preview = {{out:'', orig:'', name:'US(B09TT6C82J)_redacted.pdf', page:1, pages:4, mode:'output'}};
renderPreviewPanel();
document.getElementById('pageInfo').textContent = '1 / 4';
const st = document.getElementById('previewStage');
st.innerHTML = '';
const im = document.createElement('img');
im.src = 'data:image/png;base64,{b64}';
st.appendChild(im);
switchTab('{tab}');
</script>
"""
    return html.replace("</body>", inject + "\n</body>")


def shot(url, out):
    subprocess.run([
        EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--window-size=1440,900", "--force-device-scale-factor=1.5",
        f"--screenshot={str(Path(out).resolve())}",
        "--virtual-time-budget=3000", url,
    ], capture_output=True)
    print("截图:", out, Path(out).stat().st_size // 1024, "KB")


def main():
    b64 = make_page_png()
    # 截图走真实服务：优先用 exe 内的页面，其次用开发目录
    candidates = [
        Path("dist/DocRedactWeb/_internal/web_ui/index.html"),
        Path("web_ui/index.html"),
    ]
    orig = next(p for p in candidates if p.exists())
    backup = orig.read_text(encoding="utf-8")
    try:
        for tab, out in [("find", "docs/screenshot-find.png"),
                         ("preview", "docs/screenshot-preview.png")]:
            orig.write_text(build_demo(backup, b64, tab), encoding="utf-8")
            shot("http://127.0.0.1:5000/", out)
    finally:
        orig.write_text(backup, encoding="utf-8")
        print(f"{orig} 已还原")


if __name__ == "__main__":
    main()
