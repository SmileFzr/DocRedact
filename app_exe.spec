# -*- mode: python ; coding: utf-8 -*-
# DocRedact v3.3 打包配置（桌面版：原生窗口，不跳浏览器）
#
# 产出：dist/DocRedact/DocRedact.exe（单目录版，启动比 onefile 快很多）
# 说明：app.py / redact_engine.py 通过 import 链自动分析，无需手写。
#      RapidOCR 的 config.yaml 与 onnx 模型必须显式打进包内，
#      否则 exe 在无网络的机器上会因找不到模型而无法 OCR。
#      pywebview 依赖 pythonnet（.NET）+ EdgeWebView2 运行时，两者都有
#      官方提供的 PyInstaller hook，需把 hookspath 显式指过去。

import os
import sysconfig
from PyInstaller.utils.hooks import collect_data_files

spec_dir = globals().get('SPECPATH') or os.getcwd()

# ── 第三方 hook 目录（pywebview / pythonnet 都自带）─────────────
# spec 文件里不能用 __file__，统一用 sysconfig 定位站点包
_site = sysconfig.get_paths()['purelib']
hook_dirs = [
    _p for _p in (
        os.path.join(_site, 'webview', '__pyinstaller'),
        os.path.join(_site, 'pythonnet', '_pyinstaller'),
    ) if os.path.isdir(_p)
]
print(f'[info] 额外 hook 目录: {hook_dirs}')

# 前端页面 + 窗口图标（运行时用 WM_SETICON 补到标题栏）
datas = [
    (os.path.join(spec_dir, 'web_ui', 'index.html'), 'web_ui'),
    (os.path.join(spec_dir, 'icon.ico'), '.'),
]

# OCR 配置 + 模型
# 只剔除 *_infer 冗余副本（与 mobile 版权重等价，纯占体积）。
# 保留 v4 mobile 是因为 redact_engine._new_rapidocr() 里有 v5 失败回退到 v4 的
# 兜底逻辑，删掉模型等于拆掉安全网，不值得为了 15MB 冒 OCR 全废的风险。
try:
    rr_files = collect_data_files('rapidocr')
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
    # 原生窗口
    'webview',
    'webview.platforms.edgechromium',
    'clr',
    'pythonnet',
    'clr_loader',
]

excludes = [
    'torch', 'paddle', 'openvino', 'mnn', 'tensorrt',
    'matplotlib', 'scipy', 'pandas',
    'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'IPython', 'notebook',
    # 只走 EdgeChromium 后端，其它平台的 GUI 后端全部排除
    'webview.platforms.qt',
    'webview.platforms.gtk',
    'webview.platforms.cocoa',
    'webview.platforms.android',
    'webview.platforms.mshtml',
]

a = Analysis(
    ['app_exe.py'],
    pathex=[spec_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=hook_dirs,
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
    name='DocRedact',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                 # 桌面程序：不弹控制台，错误写日志文件
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesigning_identity=None,
    entitlements_file=None,
    icon=os.path.join(spec_dir, 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DocRedact',
)

# ── WebView2 原生加载器补位 ─────────────────────────────
# Microsoft.Web.WebView2.Core.dll 放在 _internal/webview/lib/，但它 P/Invoke 的
# WebView2Loader.dll 被 PyInstaller 归到了 runtimes/win-x64/native/ 子目录。
# 冻结环境下 .NET 只在程序集同目录找原生依赖，找不到就初始化失败 ——
# 表现是「窗口能打开但一片空白」，且不报任何错（曾经踩过）。
# 这里在构建收尾时把它拷到 Core.dll 旁边。
import shutil as _shutil

_lib = os.path.join(DISTPATH, 'DocRedact', '_internal', 'webview', 'lib')
_loader = os.path.join(_lib, 'runtimes', 'win-x64', 'native', 'WebView2Loader.dll')
_loader_dst = os.path.join(_lib, 'WebView2Loader.dll')
if os.path.exists(_loader) and not os.path.exists(_loader_dst):
    _shutil.copy2(_loader, _loader_dst)
    print(f'[info] 已补位 WebView2Loader.dll → {_loader_dst}')
elif not os.path.exists(_loader):
    print('[warn] 未找到 WebView2Loader.dll，原生窗口可能白屏')

# ── 使用说明放到 exe 同级 ───────────────────────────────
# datas 会被塞进 _internal\，用户看不到；这个文件必须躺在 exe 旁边，
# 安装包里 [Icons] 也会引用它做「使用说明」快捷方式。
_readme_src = os.path.join(spec_dir, '使用说明.txt')
_readme_dst = os.path.join(DISTPATH, 'DocRedact', '使用说明.txt')
if os.path.exists(_readme_src):
    _shutil.copy2(_readme_src, _readme_dst)
    print(f'[info] 已放置使用说明 → {_readme_dst}')
