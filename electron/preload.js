// 小煦拾简 · preload
//
// 只干一件事：把「主题变了」这件事从网页报给主进程。
//
// 为什么需要它：窗口按钮的颜色是**主进程**画的，而深浅色是用户在**网页**里选的。
// 主进程开着 contextIsolation，渲染进程够不着它 —— 中间必须有一条窄缝。
// 这条缝就是这里：contextBridge 只暴露一个函数，别的什么都不给。
"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("xrShell", {
  /** 网页切了深浅色时调一下，窗口按钮和启动底色跟着变 */
  setTheme: mode => {
    try { ipcRenderer.send("theme-changed", mode === "dark" ? "dark" : "light"); }
    catch (e) { /* 在浏览器里跑（不是 Electron 壳）时没有这条通道，忽略就好 */ }
  },
  /** 是不是跑在桌面壳里。网页据此决定要不要显示「窗口按钮占位」 */
  isShell: true,

  /* ---- 打开文件 / 选文件夹（2.3.6）----
     ⚠ 这三样在浏览器里**根本没有**，网页必须自己判断有没有再调 ——
       所以每个函数返回 Promise，浏览器里那些调用点得先看 window.xrShell 在不在。
       网页那边统一走 app.js 的 openDir() / showItem() / pickFolder() 三个包装，
       不在各处散着写 `window.xrShell && ...`。 */

  /** 用资源管理器打开一个文件夹；p 也可以是文件，那就打开它所在的文件夹 */
  openPath: p => ipcRenderer.invoke("shell:open-path", String(p || "")),
  /** 打开文件夹并**选中**这个文件 */
  showItem: p => ipcRenderer.invoke("shell:show-item", String(p || "")),
  /** 弹文件夹选择框，返回选中的路径；取消返回空串 */
  pickFolder: () => ipcRenderer.invoke("dialog:pick-folder"),
  /** 重启应用（换完数据目录要重启才生效） */
  relaunch: () => ipcRenderer.invoke("app:relaunch"),
  /** 把新的数据目录记下来（下次启动读它）；返回空串 = 成功 */
  setDataRoot: dir => ipcRenderer.invoke("app:set-data-root", String(dir || "")),
  /** 安装目录（exe 所在目录）—— 用户想「数据就放安装目录」时的快捷项 */
  installDir: () => ipcRenderer.invoke("app:install-dir"),

  /* ---- 桌面小时钟（2.4.1）----
     ⚠ 浏览器里没有这三个，网页必须先看 window.xrShell 在不在 ——
       跟上面那批一样，统一走 app.js 的包装函数，别各处散着写。 */
  clockOpen: () => ipcRenderer.invoke("clock:open"),
  clockClose: () => ipcRenderer.invoke("clock:close"),
  clockToggle: () => ipcRenderer.invoke("clock:toggle"),
  clockIsOpen: () => ipcRenderer.invoke("clock:is-open"),
});
