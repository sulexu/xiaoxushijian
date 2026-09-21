@echo off
cd /d "%~dp0"
rem 有些电脑上装了 Node 开发环境，会带一个 ELECTRON_RUN_AS_NODE 变量，
rem 它会让窗口程序退化成命令行模式、双击没反应。这里先清掉再启动。
set "ELECTRON_RUN_AS_NODE="
start "" "小煦拾简.exe"
