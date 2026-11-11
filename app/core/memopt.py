"""FrameBoost 极帧加速 — 低内存设备（核显笔记本）内存优化.

目标设备：仅核显 + 小内存（≤16G，重点 ≤8G）的笔记本。核显没有独立显存，
与系统共用同一条内存，内存压力会直接拖累游戏帧数。

提供三类能力：
1. 低内存守护：占用超阈值时自动清理待机列表 + 压缩后台进程工作集
   （跳过游戏进程与自身，60 秒冷却，避免频繁触发）；
2. 轻量特效模式：关闭窗口动画 / 任务栏动画 / 透明效果（改前备份，可一键还原）；
3. 硬件建议文案（双通道、UMA 显存分配、虚拟内存等）。

沿用项目安全约定：写注册表前先备份旧值；所有改动可还原；不碰系统关键项。
"""

from __future__ import annotations

import os
import time
import winreg

from . import booster

try:
    import psutil
    HAS_PSUTIL = True
except Exception:  # pragma: no cover
    psutil = None
    HAS_PSUTIL = False

# 轻量特效涉及的注册表项：
# (hive, path, value, reg_type, 还原时的默认值, 关闭特效时的值)
_EFFECTS = (
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
     "EnableTransparency", winreg.REG_DWORD, 1, 0),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
     "TaskbarAnimations", winreg.REG_DWORD, 1, 0),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
     "ListviewAlphaSelect", winreg.REG_DWORD, 1, 0),
    (winreg.HKEY_CURRENT_USER,
     r"Control Panel\Desktop\WindowMetrics",
     "MinAnimate", winreg.REG_SZ, "1", "0"),
)

GUARD_COOLDOWN = 60.0  # 低内存守护两次触发的最小间隔（秒）
_last_guard_run = 0.0


def ram_gb() -> int:
    """物理内存大小（GB，四舍五入）；不可用时返回 0."""
    if not HAS_PSUTIL:
        return 0
    try:
        return int(round(psutil.virtual_memory().total / 1024 ** 3))
    except Exception:
        return 0


def memory_percent() -> float:
    """当前内存占用百分比；不可用时返回 0."""
    if not HAS_PSUTIL:
        return 0.0
    try:
        return float(psutil.virtual_memory().percent)
    except Exception:
        return 0.0


def is_target_device(device: dict) -> bool:
    """是否为低内存优化目标：笔记本 + 无独显（仅核显）。"""
    return bool(device.get("is_laptop")) and not bool(device.get("discrete_gpu"))


def is_low_ram(ram: int | None = None) -> bool:
    """是否属于「小内存」（≤8G）。"""
    return 0 < (ram if ram is not None else ram_gb()) <= 8


# --------------------------------------------------------------------------- #
# 内存释放（带排除名单）
# --------------------------------------------------------------------------- #

def release_memory(exclude_names=None) -> int:
    """清理待机列表 + 压缩所有非排除进程的工作集，返回估算释放字节数.

    exclude_names: 需要跳过的进程名集合（如游戏进程），避免把正在运行的
    游戏工作集换出造成卡顿。
    """
    before = after = 0
    excl = {n.lower() for n in (exclude_names or []) if n}
    if HAS_PSUTIL:
        try:
            before = psutil.virtual_memory().available
        except Exception:
            pass
    booster.purge_standby_list()
    if HAS_PSUTIL:
        me = os.getpid()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["pid"] == me:
                    continue
                if (p.info["name"] or "").lower() in excl:
                    continue
                booster.trim_working_set(p.info["pid"])
            except Exception:
                continue
        try:
            after = psutil.virtual_memory().available
        except Exception:
            pass
    return max(0, after - before)


def maybe_release_memory(threshold_pct: float, exclude_names=None) -> dict | None:
    """低内存守护的单次检查（供 UI 定时器调用）.

    占用未超阈值或处于冷却期时返回 None；否则执行释放并返回
    {pct: 触发时占用%, freed: 释放字节}。
    """
    global _last_guard_run
    if not HAS_PSUTIL:
        return None
    try:
        pct = float(psutil.virtual_memory().percent)
    except Exception:
        return None
    now = time.monotonic()
    if pct < threshold_pct or now - _last_guard_run < GUARD_COOLDOWN:
        return None
    _last_guard_run = now
    freed = release_memory(exclude_names)
    return {"pct": pct, "freed": freed}


# --------------------------------------------------------------------------- #
# 轻量特效模式
# --------------------------------------------------------------------------- #

def _set_effect(spec: tuple, off: bool) -> bool:
    hive, path, value, rtype, default, off_value = spec
    booster._backup_reg_value(hive, path, value)
    try:
        with winreg.CreateKey(hive, path) as k:
            winreg.SetValueEx(k, value, 0, rtype, off_value if off else default)
        return True
    except OSError:
        return False


def apply_lite_effects() -> bool:
    """关闭窗口动画 / 任务栏动画 / 透明效果（改前自动备份）."""
    return all(_set_effect(s, off=True) for s in _EFFECTS)


def revert_lite_effects() -> bool:
    """还原轻量特效涉及的全部注册表项到默认值."""
    return all(_set_effect(s, off=False) for s in _EFFECTS)


# --------------------------------------------------------------------------- #
# 硬件建议
# --------------------------------------------------------------------------- #

def low_mem_hints(device: dict) -> list[str]:
    """返回适用于当前设备的 i18n 提示键列表（UI 层负责翻译）."""
    hints = ["memhint_dual_channel", "memhint_shared_vram", "memhint_close_browsers"]
    if 0 < (device.get("ram_gb") or ram_gb()) <= 16:
        hints.append("memhint_pagefile")
    return hints
