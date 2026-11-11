"""FrameBoost 极帧加速 — 启动项管理.

枚举注册表 Run（HKCU / HKLM / WOW6432）与「启动」文件夹中的自启项，
支持启用 / 禁用。禁用时把项移入 FrameBoost 自己的备份（可一键恢复），
不破坏系统其它设置。
"""

from __future__ import annotations

import json
import os
import shutil
import winreg

BACKUP_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", ".")),
    "FrameBoost", "startup_backup.json",
)
BACKUP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", ".")),
    "FrameBoost", "startup_disabled",
)

RUN_KEYS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "HKLM(32)"),
]


def _startup_folders() -> list[tuple[str, str]]:
    folders = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("ProgramData", r"C:\ProgramData")
    if appdata:
        p = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")
        if os.path.isdir(p):
            folders.append((p, "用户启动"))
    p2 = os.path.join(programdata, r"Microsoft\Windows\Start Menu\Programs\Startup")
    if os.path.isdir(p2):
        folders.append((p2, "公共启动"))
    return folders


def load_backup() -> dict:
    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_backup(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def list_startup_items() -> list[dict]:
    """返回所有启动项：{name, command, source, kind, path, enabled}."""
    items: list[dict] = []
    backup = load_backup()
    seen: set[str] = set()

    for root, path, label in RUN_KEYS:
        try:
            with winreg.OpenKey(root, path) as k:
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(k, i)
                        i += 1
                    except OSError:
                        break
                    key = f"reg:{label}:{path}:{name}"
                    seen.add(key)
                    items.append({"name": name, "command": str(val), "source": label,
                                  "kind": "reg", "path": path, "enabled": True, "key": key})
        except OSError:
            continue

    for folder, label in _startup_folders():
        try:
            for fn in os.listdir(folder):
                if not fn.lower().endswith((".lnk", ".exe", ".bat", ".cmd", ".py")):
                    continue
                key = f"folder:{label}:{os.path.join(folder, fn)}"
                seen.add(key)
                items.append({"name": fn, "command": os.path.join(folder, fn), "source": label,
                              "kind": "folder", "path": folder, "enabled": True, "key": key})
        except OSError:
            continue

    # 已禁用（在备份里）的项
    for key, it in backup.items():
        if key in seen:
            continue
        d = dict(it)
        d["enabled"] = False
        d["key"] = key
        items.append(d)

    items.sort(key=lambda x: (not x["enabled"], x["name"].lower()))
    return items


def disable_item(item: dict) -> bool:
    """禁用启动项：注册表项删除并备份；文件夹项移动到备份目录."""
    backup = load_backup()
    try:
        if item["kind"] == "reg":
            root = next(r for r, p, l in RUN_KEYS if l == item["source"] and p == item["path"])
            with winreg.OpenKey(root, item["path"], 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, item["name"])
            backup[item["key"]] = {k: item[k] for k in ("name", "command", "source", "kind", "path")}
            save_backup(backup)
            return True
        if item["kind"] == "folder":
            src = os.path.join(item["path"], item["name"])
            if not os.path.exists(src):
                return False
            os.makedirs(BACKUP_DIR, exist_ok=True)
            dst = os.path.join(BACKUP_DIR, item["name"])
            shutil.move(src, dst)
            backup[item["key"]] = {**{k: item[k] for k in ("name", "command", "source", "kind", "path")},
                                   "disabled_as": dst}
            save_backup(backup)
            return True
    except Exception:
        return False
    return False


def enable_item(item: dict) -> bool:
    """重新启用：从备份恢复到原位置."""
    backup = load_backup()
    it = backup.get(item["key"])
    if not it:
        return False
    try:
        if it["kind"] == "reg":
            root = next(r for r, p, l in RUN_KEYS if l == it["source"] and p == it["path"])
            with winreg.CreateKey(root, it["path"]) as k:
                winreg.SetValueEx(k, it["name"], 0, winreg.REG_SZ, it["command"])
        elif it["kind"] == "folder":
            src = it.get("disabled_as") or os.path.join(BACKUP_DIR, it["name"])
            dst = os.path.join(it["path"], it["name"])
            if not os.path.exists(src):
                return False
            os.makedirs(it["path"], exist_ok=True)
            shutil.move(src, dst)
        backup.pop(item["key"], None)
        save_backup(backup)
        return True
    except Exception:
        return False
