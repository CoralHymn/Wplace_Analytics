@echo off
chcp 65001 >nul
title WPlace Analytics - 启动器

echo ==========================================
echo   WPlace Analytics 一键启动
echo ==========================================
echo.

:: 进入脚本所在目录
cd /d "%~dp0"

:: --- 1. 启动本地 Web 服务器 ---
echo [1/3] 正在启动本地 Web 服务器 (端口 8080)...
start "WPlace-Web-Server" /MIN python -m http.server 8080
echo        ✅ 本地 Web 服务器已启动: http://localhost:8080
echo.

:: 等待服务器就绪
echo        ⏳ 等待服务器启动...
timeout /t 2 /nobreak >nul

:: --- 2. 打开浏览器 ---
echo [2/3] 正在打开浏览器访问本地页面...
start "" http://localhost:8080
echo        ✅ 浏览器已打开
echo.

:: --- 3. 启动账号分析器 ---
echo [3/3] 正在启动账号分析器...
start "" python "%~dp0account_analyzer.py"
echo        ✅ 账号分析器已启动
echo.

echo ==========================================
echo   所有服务已启动！
echo   - 网页分析: http://localhost:8080
echo   - 账号分析: GUI 程序窗口
echo   关闭此窗口不会停止服务
echo ==========================================

:: 短暂显示后关闭自己
timeout /t 3 /nobreak >nul
exit
