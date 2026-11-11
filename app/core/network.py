"""FrameBoost 极帧加速 — 激进网络优化（降低 CS2/PUBG 延迟）.

原理：
- 关闭多媒体网络节流（NetworkThrottlingIndex=0xFFFFFFFF, SystemResponsiveness=0），
  让游戏/下载不再被 Windows 多媒体调度降速；
- 关闭 Nagle 算法（TCPNoDelay=1 / TcpAckFrequency=1 / TcpDelAckTicks=0），
  减少小包确认延迟，改善 CS2/PUBG 这类对延迟敏感的联机游戏。

所有修改前会快照旧值到 %TEMP%\\FrameBoost_backup\\network_backup.json，可一键还原。
多数改动需管理员权限；接口级改动通常重启后生效。
"""

from __future__ import annotations

import json
import os
import winreg

BACKUP_DIR = os.path.join(os.environ.get("TEMP", "."), "FrameBoost_backup")
SNAPSHOT_FILE = os.path.join(BACKUP_DIR, "network_backup.json")

_MMS_PROFILE = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
_TCP_INTERFACES = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"


def _root_str(root) -> str:
    return "HKCU" if root == winreg.HKEY_CURRENT_USER else "HKLM"


def _root_from_str(s: str):
    return winreg.HKEY_CURRENT_USER if s == "HKCU" else winreg.HKEY_LOCAL_MACHINE


def _read_dword(root, path: str, value: str):
    try:
        with winreg.OpenKey(root, path) as key:
            v, t = winreg.QueryValueEx(key, value)
            return int(v), t
    except OSError:
        return None, None


def _write_dword(root, path: str, value: str, data: int, snap: dict, key: str) -> bool:
    """写入 DWORD，并把旧值记录进 snap（用于还原）。"""
    old, _oldtype = _read_dword(root, path, value)
    snap[key] = {"root": _root_str(root), "path": path, "value": value, "old": old}
    try:
        with winreg.CreateKey(root, path) as k:
            winreg.SetValueEx(k, value, 0, winreg.REG_DWORD, data)
        return True
    except OSError:
        return False


def _tcp_interface_subkeys() -> list[str]:
    out: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _TCP_INTERFACES) as key:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(key, i))
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


def apply_network_tweaks() -> dict:
    """应用延迟优化，返回 {ok, throttling, responsiveness, interfaces}。"""
    snap: dict = {}
    result = {"ok": False, "throttling": False, "responsiveness": False, "interfaces": 0}

    result["throttling"] = _write_dword(
        winreg.HKEY_LOCAL_MACHINE, _MMS_PROFILE, "NetworkThrottlingIndex", 0xFFFFFFFF,
        snap, "throttling")
    result["responsiveness"] = _write_dword(
        winreg.HKEY_LOCAL_MACHINE, _MMS_PROFILE, "SystemResponsiveness", 0,
        snap, "responsiveness")

    ifaces_ok = 0
    for iface in _tcp_interface_subkeys():
        path = rf"{_TCP_INTERFACES}\{iface}"
        w = 0
        w += _write_dword(winreg.HKEY_LOCAL_MACHINE, path, "TcpAckFrequency", 1,
                          snap, f"iface_{iface}_ack")
        w += _write_dword(winreg.HKEY_LOCAL_MACHINE, path, "TCPNoDelay", 1,
                          snap, f"iface_{iface}_nodelay")
        w += _write_dword(winreg.HKEY_LOCAL_MACHINE, path, "TcpDelAckTicks", 0,
                          snap, f"iface_{iface}_delack")
        if w:
            ifaces_ok += 1
    result["interfaces"] = ifaces_ok

    result["ok"] = bool(result["throttling"] or result["responsiveness"] or ifaces_ok)
    if result["ok"]:
        _save_snapshot(snap)
    return result


def revert_network_tweaks() -> bool:
    """按快照还原网络设置，返回是否成功。"""
    snap = _load_snapshot()
    if not snap:
        return False
    restored = 0
    for entry in snap.values():
        root = _root_from_str(entry["root"])
        try:
            if entry["old"] is None:
                with winreg.OpenKey(root, entry["path"], 0, winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, entry["value"])
            else:
                with winreg.CreateKey(root, entry["path"]) as k:
                    winreg.SetValueEx(k, entry["value"], 0, winreg.REG_DWORD, int(entry["old"]))
            restored += 1
        except OSError:
            continue
    return restored > 0


def is_network_optimized() -> bool:
    v, _ = _read_dword(winreg.HKEY_LOCAL_MACHINE, _MMS_PROFILE, "NetworkThrottlingIndex")
    return bool(v is not None and v == 0xFFFFFFFF)


def _save_snapshot(snap: dict) -> None:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)


def _load_snapshot() -> dict | None:
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
