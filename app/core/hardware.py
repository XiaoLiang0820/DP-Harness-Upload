"""FrameBoost 极帧加速 — 硬件信息（CPU / 内存 / 显卡 / 磁盘 / 系统）.

CPU 名称从注册表读取，显卡优先用 nvidia-smi（更准），否则从显示适配器注册表读取，
避免依赖 WMI（部分环境会「拒绝访问」）。
"""

from __future__ import annotations

import platform
import winreg

from . import gpu


def _cpu_name() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            v, _ = winreg.QueryValueEx(k, "ProcessorNameString")
            return str(v).strip()
    except OSError:
        return ""


def _gpu_names_registry() -> list[str]:
    names: list[str] = []
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                    i += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base + "\\" + sub) as sk:
                        v, _ = winreg.QueryValueEx(sk, "DriverDesc")
                        if v:
                            names.append(str(v))
                except OSError:
                    pass
    except OSError:
        pass
    return names


def get_hardware() -> dict:
    """返回 {cpu, ram_total, gpu, disks:[{mount,total,used,free}], os}."""
    info = {"cpu": "", "ram_total": 0, "gpu": "", "disks": [], "os": ""}
    try:
        info["os"] = platform.platform()
    except Exception:
        pass

    info["cpu"] = _cpu_name()

    gs = gpu.get_gpu_stats()
    if gs:
        info["gpu"] = gs[0]
    else:
        names = _gpu_names_registry()
        if names:
            info["gpu"] = names[0]
    info["gpu_vendor"] = gpu.gpu_vendor(info["gpu"])
    info["discrete_gpu"] = gpu.is_discrete(info["gpu"])

    try:
        import psutil
        info["ram_total"] = psutil.virtual_memory().total
        for p in psutil.disk_partitions():
            if p.fstype == "":
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
            except Exception:
                continue
            info["disks"].append({"mount": p.mountpoint, "total": u.total,
                                  "used": u.used, "free": u.free})
    except Exception:
        pass
    return info
