"""FrameBoost 极帧加速 — 显卡信息检测（NVIDIA / AMD / Intel 核显）.

优先级：
1. nvidia-smi（NVIDIA 独显，最准确）；
2. WMI GPU 性能计数器：独显读 Dedicated，核显读 Shared（共享内存）；
3. Win32_VideoController（仅名称 + 总显存，兜底）。
"""

from __future__ import annotations

import json

from . import admin


def _query(args: list[str]) -> tuple[int, str]:
    return admin.run_elevated_command(args)


def gpu_vendor(name: str) -> str:
    """从显卡名称判断厂商."""
    n = (name or "").lower()
    if any(k in n for k in ("nvidia", "geforce", "rtx", "gtx", "quadro")):
        return "NVIDIA"
    if "radeon" in n or "amd" in n:
        return "AMD"
    if "intel" in n or "iris" in n or "uhd" in n or "arc" in n:
        return "Intel"
    return "Unknown"


def is_discrete(name: str) -> bool:
    """粗略判断是否独显（用于区分游戏本 / 轻薄本）."""
    n = (name or "").lower()
    if any(k in n for k in ("nvidia", "geforce", "rtx", "gtx", "quadro")):
        return True
    if "radeon" in n and any(k in n for k in ("rx", "pro w", "pro ")):
        # Radeon 780M / 680M 等核显不含 RX
        return True
    if "arc" in n and "graphics" not in n:
        return True
    return False


def get_gpu_stats() -> tuple[str, int, int] | None:
    """返回 (显卡名称, 已用字节, 总字节)；无法检测返回 None."""
    # 1) NVIDIA 独显
    try:
        code, out = _query(["nvidia-smi", "--query-gpu=name,memory.used,memory.total",
                            "--format=csv,noheader,nounits"])
        if code == 0 and out.strip():
            line = out.strip().splitlines()[0].strip()
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                name = parts[0]
                used_mb = int(float(parts[1]))
                total_mb = int(float(parts[2]))
                if total_mb > 0:
                    return name, used_mb * 1024 * 1024, total_mb * 1024 * 1024
    except Exception:
        pass

    # 2) WMI GPU 性能计数器（NVIDIA / AMD / Intel 核显通用）
    try:
        ps = (
            "$c = Get-CimInstance -Namespace root/cimv2 "
            "-ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory "
            "-ErrorAction SilentlyContinue | Select-Object -First 1;"
            "$v = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | "
            "Where-Object { $_.Name -notmatch 'Microsoft' } | Select-Object -First 1;"
            "@{name=($v.Name); ded=$c.DedicatedUsage; dedlim=$c.DedicatedLimit; "
            "shared=$c.SharedUsage; sharedlim=$c.SharedLimit} | ConvertTo-Json -Compress"
        )
        code, out = _query(["powershell", "-NoProfile", "-Command", ps])
        if code == 0 and out.strip():
            data = json.loads(out.strip())
            name = data.get("name") or "GPU"
            ded = int(data.get("ded", 0) or 0)
            dedlim = int(data.get("dedlim", 0) or 0)
            shared = int(data.get("shared", 0) or 0)
            sharedlim = int(data.get("sharedlim", 0) or 0)
            if dedlim > 0:
                return name, ded, dedlim
            if sharedlim > 0:
                return name, shared, sharedlim
    except Exception:
        pass

    # 3) 仅名称 + 总显存（兜底）
    try:
        ps = ("Get-CimInstance Win32_VideoController | "
              "Select-Object -First 1 Name, AdapterRAM | ConvertTo-Json -Compress")
        code, out = _query(["powershell", "-NoProfile", "-Command", ps])
        if code == 0 and out.strip():
            data = json.loads(out.strip())
            name = data.get("Name", "GPU")
            total = int(data.get("AdapterRAM", 0) or 0)
            if total > 0:
                return name, 0, total
    except Exception:
        pass

    return None


def get_refresh_rate() -> int | None:
    """获取主显示器当前刷新率 (Hz)；失败返回 None."""
    try:
        ps = ("(Get-CimInstance Win32_VideoController | "
              "Select-Object -First 1).CurrentRefreshRate")
        code, out = _query(["powershell", "-NoProfile", "-Command", ps])
        if code == 0 and out.strip():
            return int(float(out.strip()))
    except Exception:
        pass
    return None


def get_temperature() -> float | None:
    """尽力获取 CPU/主板温度 (℃)；多数机器不可用，返回 None."""
    try:
        ps = ("$t = Get-CimInstance -Namespace root/wmi "
              "-ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | "
              "Select-Object -First 1 -ExpandProperty CurrentTemperature; "
              "if ($t) { [math]::Round($t/10.0 - 273.15, 1) }")
        code, out = _query(["powershell", "-NoProfile", "-Command", ps])
        if code == 0 and out.strip():
            return float(out.strip())
    except Exception:
        pass
    return None
