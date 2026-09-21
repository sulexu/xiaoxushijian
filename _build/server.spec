# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配置：把 server.py 打成自带 Python 的 server.exe

要点：
  · static/ 一起打进去（后端要发网页文件），运行时解包到 sys._MEIPASS
  · 配置文件（ai_config.json 等）**不**打进去 —— 它们要写在 exe 旁边，
    server.py 里已经区分了 _app_dir()（可写）和 _res_dir()（只读资源）
  · onedir 而不是 onefile：onefile 每次启动都要把整个运行时解压到临时目录，
    启动会慢好几秒；onedir 快得多，反正最终是跟 Electron 一起打包成文件夹
"""
import os

BASE = os.path.dirname(os.path.abspath(SPEC))          # noqa: F821  _build/
ROOT = os.path.dirname(BASE)                            # 统计系统/

a = Analysis(
    [os.path.join(ROOT, "server.py")],
    pathex=[ROOT],
    binaries=[],
    # ⚠ static 下的 `_` 开头文件是**开发时用的**（回归测试 _test.html、
    # 各种界面原型 _i2/_ic/... ），一律不进安装包。两个理由：
    #   ① 难看 —— 用户翻到 resources\static 会看见一堆半成品；
    #   ② **_test.html 是会写数据的**：它跑起来会存笔记、改打卡项、
    #      动设置。它又恰好挂在 /static/ 下谁都能打开，等于在成品里
    #      留了一个「点一下就把数据改乱」的按钮。
    # 这里用 glob 逐个列，而不是整个目录拷进去 —— 就是为了把这件事写死在构建里。
    # ⚠ 这里原来用 `os.listdir(static)` + `os.path.isfile`，**只取顶层文件** ——
    #   子目录会被静默漏掉。2.4.8 加了 `static/fonts/shoujinti.ttf`（瘦金体）
    #   才发现：打完包字体不在，而源码版一切正常（典型的"只有安装版才犯病"）。
    #   现在改成 os.walk 递归，同时保留「`_` 开头的开发文件不进包」那条规矩。
    datas=[(os.path.join(dp, f),
            os.path.join("static", os.path.relpath(dp, os.path.join(ROOT, "static"))))
           for dp, _dn, fn in os.walk(os.path.join(ROOT, "static"))
           for f in sorted(fn)
           if not f.startswith("_")
           and not os.path.basename(dp).startswith("_")],
    # cryptography 是「笔记加密」要用的（AES-GCM）。它是 Rust 扩展，
    # 静态分析不一定能把 _rust 那块捞全，所以显式列出来 —— 漏了的话
    # 打包版会「加密开关点不动」，而源码版一切正常，最容易漏测。
    # ⚠ 有一批模块是**在函数体里 import 的**（为了避开循环导入、或者只在
    # 那一件事发生时才需要）。PyInstaller 只做静态分析，看不见函数里的 import，
    # 不显式列出来的话，打包版跑到那一步会当场 ModuleNotFoundError，
    # 而源码版一切正常 —— 这种「只有安装版才犯的病」最难查。
    #   _migrate / _excel_legacy  启动时把 Excel 搬进数据库要用（循环导入，只能懒加载）
    #   export                    点「导出 Excel」要用
    #   vision                    看图录入要用
    #   store / notes             正常 import，列着保险
    hiddenimports=["openpyxl", "openpyxl.styles", "openpyxl.chart", "openpyxl.utils",
                   "cryptography",
                   "cryptography.hazmat.primitives.ciphers.aead",
                   "cryptography.hazmat.bindings._rust",
                   "store", "notes", "export", "vision",
                   "_migrate", "_excel_legacy"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "PyQt5", "PySide2"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # 不弹黑窗口（Electron 会隐藏它，这里再保险一层）
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="server",
)
