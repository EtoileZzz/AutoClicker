# 自动点击器 AutoClicker

一个 Windows 图形化自动点击 / 滚轮 / OCR 辅助确认工具。

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Windows](https://img.shields.io/badge/Windows-10%2F11-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

## 功能特性

- 图形化界面，支持 1~6 套普通预设 + 特殊“触发预设 7”
- 任务类型：单击 / 右键 / 双击、滚轮滚动
- 坐标模式：固定坐标、拾取坐标、实时“当前鼠标位置”
- 全局热键：F8 进入监听，数字 1~7 选择/触发预设
- 触发预设 7：等待鼠标左键或自定义按键后执行，并保持监听
- 循环执行：按次数或按时间循环，可设置循环间隔
- 长按数字键或 Ctrl+数字键触发循环，Esc/单击同数字取消
- OCR 点击确认：Windows 自带 OCR、图形化框选区域、失败策略可选
- 每个任务独立间隔与 OCR 开关
- 任务流程图：线性展示、拖拽排序、双击编辑
- 配置自动保存 / 导入导出 JSON

## 运行环境

- Windows 10 / 11
- Python 3.12（使用 Tkinter，官方 Windows 安装包自带）
- OCR 使用 Windows.Media.Ocr，需要系统已安装中文（zh-CN）OCR 语言包

## 快速开始（源码运行）

```powershell
git clone https://github.com/<你的用户名>/<仓库名>.git
cd <仓库名>

# 安装依赖（OCR + PyInstaller 可选；主程序核心为 Python 标准库）
python -m pip install -r requirements.txt

# 直接运行
python auto_clicker.py
```

> 若未安装 OCR 依赖，程序仍可正常点击/滚轮；只有启用 OCR 校验时才需要。

## 打包 exe

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name AutoClicker `
  --hidden-import winrt.runtime `
  --hidden-import winrt.windows.media.ocr `
  --hidden-import winrt.windows.globalization `
  --hidden-import winrt.windows.graphics.imaging `
  --hidden-import winrt.windows.storage.streams `
  --hidden-import winrt.windows.foundation `
  auto_clicker.py
```

也可以直接执行仓库中的 `build_exe.ps1`。

## 快捷键

| 按键 | 说明 |
| --- | --- |
| F8 | 进入监听 / 退出运行 |
| Esc | 暂停监听或取消循环 |
| 数字 1~6 | 短按执行一次；长按或 Ctrl+数字按循环设置运行 |
| 数字 7 | 进入“触发预设”（等待鼠标/按键触发） |
| 循环中 Esc 或单击同一数字 | 取消循环并回到监听 |

## 运行状态机

```text
编辑界面
   │ 按 F8
   ▼
监听状态 ── 按 1~6 ──► 普通执行 ── 完成 ──► 回到监听
   │                        │ 长按/Ctrl ──► 循环执行（可取消）
   └── 按 7 ──► 触发等待 ── 触发 ──► 执行触发预设任务 ──► 回到触发等待
```

## OCR 速度说明

本项目使用 Windows 系统自带 OCR + GDI 直读截图。小范围实测约 30ms 上下，
完整 OCR 难以稳定做到 20ms 以内；OCR 仅用于每个任务执行前的一次确认。

## 配置保存位置

程序会在 exe / 源码同目录生成 `auto_clicker_presets.json` 自动保存全部预设。
仓库提供空配置示例：`auto_clicker_presets.example.json`，首次运行未生成配置时
会自动创建 7 个空预设。

## 安全与合规说明

- 自动模拟输入可能违反部分软件的用户协议，请只在你有权限的软件/环境使用。
- 作者不对因使用本工具导致的封号、数据丢失等后果负责。

## 项目结构

```text
auto_clicker.py         主程序（单文件实现）
requirements.txt        OCR 可选依赖
requirements-build.txt  exe 打包依赖
build_exe.ps1           Windows exe 打包脚本
.github/workflows/build.yml  GitHub Actions 自动打包
```

## 开源协议

[MIT License](LICENSE)
