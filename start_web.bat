@echo off
chcp 65001 > nul
echo ========================================
echo   文档隐私遮罩工具 - 网页端启动脚本
echo ========================================
echo.

REM 查找 Python
set PYTHON_EXE=
for %%i in (python.exe py.exe) do (
    where %%i >nul 2>&1 && set PYTHON_EXE=%%i && goto :found
)
:found
if not defined PYTHON_EXE (
    echo ❌ 未找到 Python，请先安装 Python 并添加到 PATH
    pause
    exit /b 1
)

echo ✅ 使用 Python: %PYTHON_EXE%
echo.

REM 检查依赖
%PYTHON_EXE% -c "import flask, fitz, PIL" 2>nul
if errorlevel 1 (
    echo ⚠️ 依赖不完整，正在安装...
    %PYTHON_EXE% -m pip install -r requirements.txt
)

echo 🚀 启动服务器...
echo 📝 日志窗口将显示服务器状态
echo 🌐 浏览器将自动打开 http://localhost:5000
echo.
echo ⚠️ 关闭此窗口即可停止服务器
echo ========================================
echo.

%PYTHON_EXE% app.py
pause
