#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DocRedact 桌面版启动器（PyInstaller 打包入口）。

与源码运行（app.py）的区别：
  · 不再打开浏览器标签页，改用 pywebview 在**原生窗口**里载入同一套界面
  · Flask 仍跑在后台线程，只监听 127.0.0.1 的可用端口，不对外暴露
  · WebView2 内核缺失时自动降级回浏览器，不让用户面对白屏
  · 打包为无控制台程序，崩溃信息写入 exe 同级的错误日志

所有业务逻辑都在 app.py / redact_engine.py，这里只负责"怎么把窗口弄出来"。
"""

import os
import sys
import time
import socket
import threading
import traceback
from pathlib import Path

APP_TITLE = 'DocRedact · 文档隐私遮罩工具'
WIN_W, WIN_H = 1320, 880
WIN_MIN = (1040, 700)

# ── 路径基准：打包后是 exe 所在目录，源码运行时是脚本所在目录 ──
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

LOG_FILE = BASE_DIR / 'DocRedact_错误日志.txt'
DATA_DIR = BASE_DIR / 'ui_data'

# 无控制台模式下 sys.stdout / sys.stderr 是 None，
# 任何 print 或库内写 stderr 都会抛 AttributeError，先兜住。
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')


def log_crash(detail):
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'\n===== {time.strftime("%Y-%m-%d %H:%M:%S")} =====\n{detail}\n')
    except Exception:
        pass


def show_error(msg):
    """无控制台时用系统弹窗告知用户，否则用户只会看到"双击没反应"。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, 'DocRedact 启动失败', 0x10)
    except Exception:
        pass


def wait_port(port, timeout=40.0):
    """等服务真正能接受连接，避免窗口打开时页面 404。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def start_backend():
    """在后台线程拉起 Flask，返回访问地址。"""
    import app as A

    port = A.find_free_port()
    url = f'http://127.0.0.1:{port}'

    def serve():
        try:
            A.app.run(host='127.0.0.1', port=port, debug=False,
                      threaded=True, use_reloader=False)
        except Exception:
            log_crash('本地服务异常退出:\n' + traceback.format_exc())

    threading.Thread(target=serve, daemon=True, name='flask').start()

    if not wait_port(port):
        raise RuntimeError(f'本地服务未能在 40 秒内就绪（端口 {port}）')

    # 提前预热 OCR：用户拖入文件时就不用再等模型加载
    def warm():
        try:
            A.engine.ocr_available()
        except Exception:
            pass

    threading.Thread(target=warm, daemon=True, name='ocr-warmup').start()
    return url


def open_in_browser(url):
    """降级路径：没有 pywebview 或 WebView2 时退回浏览器。"""
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        log_crash('无法打开浏览器:\n' + traceback.format_exc())
    threading.Event().wait()       # 保持主线程存活，后台服务继续跑


def _resource(name):
    """取打包资源：冻结后从 _MEIPASS，源码运行从脚本目录。"""
    if getattr(sys, 'frozen', False):
        p = Path(getattr(sys, '_MEIPASS', BASE_DIR)) / name
    else:
        p = BASE_DIR / name
    return p if p.exists() else None


def _apply_window_icon():
    """给原生窗口设标题栏图标。

    pywebview 6.x 的 create_window 没有 icon 参数，WinForms 窗口默认显示
    系统的通用图标。这里用 WM_SETICON 消息在窗口就绪后补上。
    """
    ico = _resource('icon.ico')
    if not ico:
        return
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1

        small = u32.LoadImageW(None, str(ico), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        big = u32.LoadImageW(None, str(ico), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if not (small or big):
            return

        pid = os.getpid()
        targets = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _):
            wpid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value == pid and u32.IsWindowVisible(hwnd):
                targets.append(hwnd)
            return True

        # 窗口与 WebView2 初始化有延迟，最多等 8 秒
        for _ in range(80):
            targets.clear()
            u32.EnumWindows(_cb, 0)
            if targets:
                break
            time.sleep(0.1)

        for hwnd in targets:
            if big:
                u32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, ctypes.c_void_p(big))
            if small:
                u32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, ctypes.c_void_p(small))
    except Exception:
        log_crash('设置窗口图标失败:\n' + traceback.format_exc())


def run_native(url):
    """用原生窗口打开界面；返回 False 表示需要降级。"""
    try:
        import webview
    except Exception:
        log_crash('pywebview 导入失败:\n' + traceback.format_exc())
        return False

    try:
        webview.create_window(
            APP_TITLE,
            url=url,
            width=WIN_W,
            height=WIN_H,
            min_size=WIN_MIN,
            confirm_close=False,
            text_select=True,
        )
        # private_mode=False 才会保留 localStorage（关键词、正则开关等设置）
        webview.start(
            _apply_window_icon,
            gui='edgechromium',
            private_mode=False,
            storage_path=str(DATA_DIR),
            debug=False,
        )
        return True
    except Exception:
        log_crash('原生窗口启动失败:\n' + traceback.format_exc())
        return False


def main():
    url = start_backend()

    if run_native(url):
        return

    # 走到这里说明 WebView2 不可用（常见于 Win7 或精简版系统）
    log_crash('已降级为浏览器模式')
    open_in_browser(url)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        detail = traceback.format_exc()
        log_crash(detail)
        show_error(
            'DocRedact 启动失败。\n\n'
            f'错误信息已写入：\n{LOG_FILE}\n\n'
            f'{(detail.strip().splitlines() or ["未知错误"])[-1]}'
        )
    finally:
        # 窗口关闭即退出进程，避免后台 Flask 线程把 exe 吊在任务管理器里
        os._exit(0)
