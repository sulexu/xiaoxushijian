@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 用 pythonw 跑，不弹黑框；出错写进 _原型_错误.txt
start "" /b pythonw _原型_窗口.py 2> _原型_错误.txt
