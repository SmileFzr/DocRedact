# -*- mode: python ; coding: utf-8 -*-
# DocRedact v3.2 打包配置
#
# 产出：dist/DocRedactWeb/DocRedactWeb.exe（单目录版，启动比 onefile 快）
# 说明：app.py / redact_engine.py 通过 import 链自动分析，无需手写。
#      RapidOCR 的 config.yaml 与 onnx 模型必须显式打进包内，
#      否则 exe 在无网络的机器上会因找不到模型而无法 OCR。

import os
from PyInstaller.utils.hooks import collect_data_files

spec_dir = globals().get('SPECPATH') or os.getcwd()

# 前端页面
datas = [
    (os.path.join(spec_dir, 'web_ui', 'index.html'), 'web_ui'),
]

# OCR 配置 + 模型（PP-OCRv5 为主，保留 v4 mobile 作为回退）
try:
    rr_files = collect_data_files('rapidocr')
    # 去掉 v4 的 *_infer 冗余副本（与 mobile 版内容一致，纯占体积）
    rr_files = [f for f in rr_files if '_infer.onnx' not in f[0]]
    datas += rr_files
except Exception as e:
    print(f'[warn] 收集 rapidocr 数据失败: {e}')

hiddenimports = [
    'flask',
    'fitz',
    'PIL',
    'numpy',
    'docx',
    'openpyxl',
    'pptx',
    'rapidocr',
    'rapidocr_onnxruntime',
    'onnxruntime',
    'cv2',
    'yaml',
    'requests',
]

excludes = [
    'torch', 'paddle', 'openvino', 'mnn', 'tensorrt',
    'matplotlib', 'scipy', 'pandas',
    'tkinter', 'PyQt5', 'PySide6', 'IPython', 'notebook',
]

a = Analysis(
    ['app_exe.py'],
    pathex=[spec_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

# OpenCV 的视频解码 DLL 约 28MB，本项目完全不处理视频，剔除
a.binaries = [b for b in a.binaries if 'opencv_videoio_ffmpeg' not in b[0].lower()]

# ── MSVC 运行时对齐 ─────────────────────────────────────
# 依赖里混进了很旧的 msvcp140.dll（14.26），而 onnxruntime 1.26 需要新版运行时，
# 直接打包会在 import 时报「DLL 初始化例程失败」→ OCR 静默失效。
# 解决：统一换成系统里最新的同族 DLL（14.5x），保证 onnxruntime 能正常加载。
_MSVC_DLLS = (
    'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll',
    'vcruntime140.dll', 'vcruntime140_1.dll', 'concrt140.dll',
)
_sys32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
a.binaries = [b for b in a.binaries
              if os.path.basename(b[0]).lower() not in _MSVC_DLLS]
for _name in _MSVC_DLLS:
    _src = os.path.join(_sys32, _name)
    if os.path.exists(_src):
        a.binaries.append((_name, _src, 'BINARY'))
    else:
        print(f'[warn] 系统缺少 {_name}，依赖目标机器自带的 VC++ 运行时')

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DocRedactWeb',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # 保留控制台，方便查看日志与端口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesigning_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DocRedactWeb',
)
