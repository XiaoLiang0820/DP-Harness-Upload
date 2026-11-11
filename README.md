# FrameBoost · 极帧加速

一款轻量、安全的 **Windows 游戏加速 + 垃圾清理** 桌面工具，专为
**三角洲行动 / CS2 / 我的世界 / PUBG** 调校。界面简洁、高级、中英双语。

A lightweight, safe **Windows game booster + junk cleaner** tailored for
**Delta Force / CS2 / Minecraft / PUBG**, with a clean, premium, bilingual UI.

---

## ✨ 功能 Features

| 模块 Module | 说明 Description |
| --- | --- |
| 🧹 垃圾清理 Junk Cleaner | 扫描并安全清理 14 类目标：用户/系统临时文件、Windows 更新缓存、缩略图缓存、DirectX 着色器缓存、崩溃转储、浏览器缓存、回收站等；支持「移入回收站」安全模式 |
| 🚀 游戏加速 Game Booster | 切换高性能/终极性能电源计划、清理内存待机列表、压缩后台进程工作集、结束 OneDrive/Teams 等后台进程、开启 Windows 游戏模式、提升游戏进程优先级、定时器分辨率 0.5ms、关闭 Game DVR、硬件加速 GPU 调度 |
| 🧠 智能加速 Smart Boost | 自动识别设备形态（台式机/游戏本/轻薄本）与供电状态，推荐「激进/均衡/温和」档位并一键应用 |
| 🎮 游戏专属 Game Profiles | 三角洲行动 / CS2 / 我的世界 / PUBG 四款游戏的安装检测、运行状态、推荐启动参数与画面设置建议；支持全盘检测 Steam/Epic 其他游戏与手动添加自定义游戏 |
| ⚡ 网络优化 Network Boost | 关闭 Nagle 算法与多媒体网络节流，降低 CS2/PUBG 延迟；改前自动备份，可一键还原 |
| 🧠 低内存设备优化 Low-Memory Optimization | 核显笔记本专属（见下文）：低内存守护、轻量特效模式、硬件建议 |
| 🚦 启动项管理 Startup Manager | 枚举注册表 Run 键与启动文件夹；禁用 = 备份 + 移除，可一键恢复 |
| 💽 磁盘分析 Disk Analysis | 各盘符顶层文件夹占用排行 + 200MB 以上大文件 Top 40 |
| 🤖 自动清理 Auto Clean | 开机自启静默清理 + 每天定时清理（Windows 计划任务），结果记入日志供查看 |
| 📌 性能悬浮窗 Perf Overlay | 无边框可拖动悬浮窗，实时显示 CPU / 内存 / 显存，三种样式、可缩放、可置顶 |
| 🌡️ CPU 频率调节 CPU Tuning | 最大/最小处理器状态、性能提升模式（Windows 电源管理，无需第三方工具） |

## 🧠 低内存设备优化（核显笔记本）

针对**仅核显 + 小内存（≤16G，重点 ≤8G）**的笔记本：核显没有独立显存，
与系统共用同一条内存，内存压力会直接拖累游戏帧数。程序检测到这类设备后，
「游戏加速」页会自动出现「低内存设备优化」卡片：

- **低内存守护 Memory Guard** — 内存占用超过阈值（80% / 85% / 90% 可调）时，
  自动清理待机列表并压缩后台进程工作集；跳过正在运行的游戏进程，
  60 秒冷却防止频繁触发，小内存设备默认开启
- **轻量特效模式 Lite Effects** — 一键关闭窗口动画、任务栏动画与透明效果，
  为游戏腾出内存与 GPU 资源；改注册表前自动备份，可一键还原
- **立即释放内存** — 手动触发一次完整内存释放（同样跳过游戏进程）
- **硬件建议** — 双通道内存对核显帧数的收益、BIOS 中 UMA Frame Buffer 显存分配、
  虚拟内存保持「系统管理」、游戏前关闭浏览器等

独显笔记本与台式机不会看到该卡片，功能只对核显笔记本生效。

For laptops with **integrated GPU only and small RAM**: Memory Guard auto-frees
standby memory above a set threshold (never touching game processes), Lite
Effects mode turns off animations/transparency (backed up, revertible), plus
practical iGPU tips. The card appears only on iGPU laptops.

## 🖥️ 界面预览 UI

- 深色高级主题（科技蓝 + 青绿渐变），左侧导航 + 7 个页面 + 卡片式布局
- 中 / 英 一键切换，全部文案走统一翻译表
- 所有耗时操作均在子线程中执行，不卡界面

## 📦 安装与运行 Install & Run

需要 Windows 10/11 + Python 3.10+（推荐 3.11/3.12），依赖只有 `PySide6` 和 `psutil`。

```powershell
# 1) 进入项目目录
cd "D:\DP工作区\FrameBoost"

# 2) 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3) 安装依赖
pip install -r requirements.txt

# 4) 运行
python run.py
```

> 系统级清理与部分优化（系统临时文件、Windows 更新缓存、电源计划、HAGS、网络优化）
> 需要**管理员权限**。可在程序内「设置」页点击「以管理员身份重启」。
> System-level cleaning and some tweaks require **admin rights**; use the
> 「Restart as Administrator」 button in Settings.

## 🧰 打包为 exe Build to exe

打包使用 PyInstaller **目录模式（onedir）**：产物为 `dist\FrameBoost\`
（`FrameBoost.exe` + `_internal` 运行时目录），比单文件模式启动更快、更稳定。

```powershell
pyinstaller --noconfirm --clean --windowed --onedir --name FrameBoost --icon assets/icon.ico run.py
# 产物：dist\FrameBoost\FrameBoost.exe
```

## 🚀 一键发布 Release

`tools/release.py` 纯 GitHub REST API 实现（不依赖 git 协议），一条命令完成
打包 → 压缩 zip → 创建 Release → 上传附件；`--sync-source` 可同时把源码提交进仓库：

```powershell
python tools/release.py --check          # 查看远端状态
python tools/release.py --dry-run        # 演练：打包+算差异，不写远端
python tools/release.py                  # 完整发布
python tools/release.py --version 1.6.0 --notes "…" --sync-source
```

认证优先读环境变量 `GH_TOKEN`，否则读 Windows 凭据管理器中的 GitHub 凭据。
二进制 zip 一律走 Release 附件（GitHub API 拒收 >50MB 请求体，不进仓库）。

## 🛡️ 安全说明 Safety

- 只清理明确的临时文件 / 缓存 / 系统残留，**绝不删除系统关键文件**。
- 清理前默认弹出确认；可开启「移入回收站」以获得可恢复保护。
- 修改注册表（游戏模式 / HAGS / 网络优化 / 轻量特效）前会自动备份旧值到 `%TEMP%\FrameBoost_backup`。
- **不影响日常使用**：自动清理只处理临时/缓存等「可自动重建」的文件，不碰浏览器登录态与回收站；
  网络优化为「游戏会话级」，提供「恢复日常模式」一键还原并切回平衡电源。
- 低内存守护跳过正在运行的游戏进程，避免把游戏工作集换出造成卡顿。
- 所有操作均为本地执行，**不上传任何数据**。

## 📁 项目结构 Structure

```
FrameBoost/
├── run.py                 # 启动入口（--autoclean 为静默清理模式）
├── requirements.txt       # PySide6 + psutil
├── tools/
│   └── release.py         # 一键发布（打包 / 仓库同步 / GitHub Release）
├── app/
│   ├── __main__.py        # python -m app 入口
│   ├── main_window.py     # 主窗口（侧边栏 + 7 页面）
│   ├── theme.py           # 深色主题 QSS
│   ├── i18n.py            # 中英双语翻译表
│   ├── widgets.py         # 可复用组件（Card / ToggleSwitch / TaskThread…）
│   ├── version.py
│   ├── core/
│   │   ├── admin.py       # 权限检测 / 提权 / GBK 解码
│   │   ├── cleaner.py     # 垃圾扫描清理
│   │   ├── booster.py     # 加速核心（电源 / 内存 / 进程 / 游戏模式）
│   │   ├── memopt.py      # 低内存设备优化（核显笔记本）
│   │   ├── network.py     # 网络优化（快照 / 还原）
│   │   ├── startup.py     # 启动项管理
│   │   ├── games.py       # 游戏专属配置与检测
│   │   ├── game_library.py# 自定义游戏库 / 全盘扫描
│   │   ├── device.py      # 设备识别（形态 / OEM / 电池 / 内存）
│   │   ├── hardware.py    # 硬件信息
│   │   ├── gpu.py         # 显卡状态 / 温度 / 刷新率
│   │   ├── disk.py        # 磁盘空间分析
│   │   ├── automation.py  # 开机自启 / 计划任务自动清理
│   │   └── diagnostics.py # 诊断报告导出
│   └── ui/                # 7 个页面 + 性能悬浮窗
└── assets/
```

## 🔗 参考 References

借鉴了以下开源项目的成熟思路（清理、内存优化、电源计划）：

- [WinMemoryOpt](https://github.com/chienhaoc/WinMemoryOpt) — Windows 内存优化
- [OpenGameBoost](https://github.com/bensheed/OpenGameBoost) — 开源游戏加速
- [c_cleaner_plus](https://github.com/Kiowx/c_cleaner_plus) — Windows 清理工具
- [ngxsmk-gamenet-optimizer](https://github.com/NGXSMK/ngxsmk-gamenet-optimizer) — 游戏网络优化

## ⚠️ 免责声明 Disclaimer

本工具仅供学习与个人优化使用。系统优化与清理存在一定风险，使用前请自行备份重要数据。
Use at your own risk; back up important data before use.
