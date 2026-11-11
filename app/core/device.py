"""FrameBoost 极帧加速 — 设备识别（台式机 / 游戏本 / 轻薄本、OEM、电池）."""

from __future__ import annotations

import winreg

from . import gpu


def _bios_field(name: str) -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\BIOS") as k:
            v, _ = winreg.QueryValueEx(k, name)
            return str(v).strip()
    except OSError:
        return ""


def oem_name() -> str:
    man = _bios_field("SystemManufacturer")
    m = (man or "").lower()
    for key, label in (
        ("asus", "ASUS"), ("lenovo", "Lenovo"), ("dell", "Dell"),
        ("hp", "HP"), ("hewlett", "HP"), ("acer", "Acer"),
        ("msi", "MSI"), ("micro-star", "MSI"), ("gigabyte", "Gigabyte"),
        ("razer", "Razer"), ("microsoft", "Microsoft"), ("samsung", "Samsung"),
        ("huawei", "Huawei"), ("honor", "Honor"), ("xiaomi", "Xiaomi"),
    ):
        if key in m:
            return label
    return man or "Unknown"


def model_name() -> str:
    return _bios_field("SystemProductName")


def battery_state() -> dict:
    try:
        import psutil
        b = psutil.sensors_battery()
        if b is None:
            return {"present": False, "percent": None, "plugged": True}
        return {"present": True, "percent": int(b.percent), "plugged": bool(b.power_plugged)}
    except Exception:
        return {"present": False, "percent": None, "plugged": True}


def ram_size_gb() -> int:
    """物理内存大小（GB，四舍五入）；不可用时返回 0."""
    try:
        import psutil
        return int(round(psutil.virtual_memory().total / 1024 ** 3))
    except Exception:
        return 0


_CACHE: dict | None = None


def detect_device(force: bool = False) -> dict:
    """返回设备类型、OEM、显卡、电池等信息（带缓存）."""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    gs = gpu.get_gpu_stats()
    gpu_name = gs[0] if gs else ""
    bat = battery_state()
    is_laptop = bat["present"]
    vendor = gpu.gpu_vendor(gpu_name)
    discrete = gpu.is_discrete(gpu_name)

    if not is_laptop:
        kind = "desktop"
    elif discrete:
        kind = "gaming_laptop"
    else:
        kind = "thin_light"

    _CACHE = {
        "kind": kind,
        "is_laptop": is_laptop,
        "oem": oem_name(),
        "model": model_name(),
        "gpu_name": gpu_name,
        "gpu_vendor": vendor,
        "discrete_gpu": discrete,
        "battery": bat,
        "ram_gb": ram_size_gb(),
    }
    return _CACHE


def suggest_tier(device: dict) -> str:
    """根据设备类型/供电状态推荐加速档位：aggressive / balanced / gentle."""
    bat = device.get("battery") or {}
    if bat.get("present") and not bat.get("plugged"):
        return "gentle"
    kind = device.get("kind")
    if kind == "desktop":
        return "aggressive"
    if kind == "gaming_laptop":
        return "balanced"
    return "gentle"


def mux_hint(device: dict) -> bool:
    """是否有独显直连（MUX）提示价值."""
    return bool(device.get("discrete_gpu") and device.get("is_laptop"))


def oem_hint(device: dict) -> str | None:
    """返回 OEM 对应的官方性能软件名（用于提示），无则 None."""
    return {
        "ASUS": "MyASUS / Armoury Crate",
        "Lenovo": "Lenovo Vantage / Legion Space",
        "Dell": "Dell G Series / Alienware Command Center",
        "HP": "OMEN Gaming Hub",
        "MSI": "MSI Center",
        "Acer": "PredatorSense / NitroSense",
        "Razer": "Razer Synapse",
    }.get(device.get("oem") or "", None)
