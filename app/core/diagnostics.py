"""FrameBoost 极帧加速 — 诊断报告导出."""

from __future__ import annotations

import os

from . import admin, booster, device, gpu, hardware


def build_report() -> str:
    hw = hardware.get_hardware()
    dev = device.detect_device()
    stats = booster.get_system_stats()
    ram_gb = (hw.get("ram_total") or 0) / 1024 ** 3
    disks = hw.get("disks") or []
    disk_txt = ", ".join(
        f"{d['mount']} {d['free'] / 1024 ** 3:.0f}G free/{d['total'] / 1024 ** 3:.0f}G"
        for d in disks) or "-"
    lines = [
        "FrameBoost 诊断报告",
        "=" * 46,
        f"系统          : {hw.get('os') or '-'}",
        f"设备类型      : {dev.get('kind')}",
        f"厂商 / 型号   : {dev.get('oem')} {dev.get('model')}",
        f"CPU           : {hw.get('cpu') or '-'}",
        f"显卡          : {hw.get('gpu') or '-'}  (厂商: {dev.get('gpu_vendor')})",
        f"内存          : {ram_gb:.1f} GB",
        f"磁盘          : {disk_txt}",
        f"电池          : {dev.get('battery')}",
        f"当前电源计划  : {stats.power_plan_name or '-'}",
        f"游戏模式      : {stats.game_mode}",
        f"HAGS          : {stats.hags}",
        f"温度          : {gpu.get_temperature()}",
        f"屏幕刷新率    : {gpu.get_refresh_rate()}",
        f"管理员权限    : {admin.is_admin()}",
    ]
    return "\n".join(lines)


def save_report() -> str:
    """把诊断报告写入文件；依次尝试多个可写位置，全部失败才抛错."""
    text = build_report()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    candidates = [
        os.path.join(base, "FrameBoost", "diagnostics.txt"),
        os.path.join(os.path.expanduser("~"), "Desktop", "FrameBoost_diagnostics.txt"),
        os.path.join(os.environ.get("TEMP", "."), "FrameBoost_diagnostics.txt"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostics.txt"),
    ]
    last_exc: Exception | None = None
    for path in candidates:
        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return path
        except Exception as exc:  # 尝试下一个位置
            last_exc = exc
            continue
    raise last_exc or OSError("无法写入诊断报告")
