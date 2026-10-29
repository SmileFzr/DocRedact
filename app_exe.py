#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档隐私遮罩工具 - exe 启动器（PyInstaller 打包入口）
只做一件事：设置好环境后调用 app.main()
所有业务逻辑都在 app.py / redact_engine.py 中
"""

import sys
import os

# 确保能 import 同目录的模块（开发环境和打包环境都适用）
if getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(sys.executable))
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import main

if __name__ == '__main__':
    main()
