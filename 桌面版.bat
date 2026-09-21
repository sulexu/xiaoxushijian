@echo off
chcp 65001 >nul
rem 本机环境变量里带 ELECTRON_RUN_AS_NODE=1（其他软件加的），
rem 不清掉的话 Electron 会以纯 Node 模式启动、直接报错
set ELECTRON_RUN_AS_NODE=
cd /d "%~dp0electron"
npm start
