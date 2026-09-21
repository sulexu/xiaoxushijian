@echo off
cd /d "%~dp0"
title 小煦拾简（浏览器版）
echo.
echo   正在启动，稍等几秒会自动打开浏览器...
echo   如果没打开，手动访问 http://127.0.0.1:8765
echo.
echo   ★ 关掉这个黑色窗口 = 停止系统 ★
echo.
"%~dp0resources\server.exe"
echo.
echo   系统已停止。按任意键关闭。
pause >nul
