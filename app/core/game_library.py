"""FrameBoost 极帧加速 — 已安装游戏检测 + 自定义游戏管理.

- 扫描 Steam 库 common 目录、Epic Games 等常见安装位置，找出其他已安装游戏；
- 自定义游戏持久化到 %LOCALAPPDATA%\\FrameBoost\\custom_games.json；
- 供「游戏专属」页检测、添加、删除并对添加的游戏做优化。
"""

from __future__ import annotations

import json
import os

from . import games

CUSTOM_GAMES_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", ".")),
    "FrameBoost", "custom_games.json",
)

_COMMON_ROOTS = [
    r"C:\Program Files\Epic Games",
    r"C:\Program Files (x86)\Epic Games",
    r"D:\Epic Games",
    r"D:\Program Files\Epic Games",
    r"E:\Epic Games",
    r"E:\Program Files\Epic Games",
    r"C:\Games",
    r"D:\Games",
    r"E:\Games",
]

_BLACKLIST_KW = ("steam", "redist", "directx", "vcredist", "_commonredist",
                 "launcher", "uninstall", "runtime", "engine", "online services",
                 "services", "workshop", "tools", "dedicated server")

# 常见工具/安装类 exe（非游戏主程序），检测时应排除
_BAD_EXE_KW = ("crashhandler", "crash", "unins", "uninstall", "setup", "install",
               "redist", "vcredist", "vc_redist", "anticheat", "easyanticheat",
               "eac", "battleye", "launcher", "helper", "update", "updater",
               "vconsole", "dxsetup", "dotnet", "eos", "steam", "unrealpak",
               "protected", "shipping-launcher")


def _is_blacklisted(name: str) -> bool:
    lower = name.lower()
    return any(k in lower for k in _BLACKLIST_KW)


def _is_bad_exe(name: str) -> bool:
    lower = name.lower()
    return any(k in lower for k in _BAD_EXE_KW)


def _find_main_exe(folder: str, max_depth: int = 4) -> str | None:
    """在目录内找主 exe：优先最浅层级里最大的 exe（主程序通常在根目录）。"""
    candidates: list[tuple[int, int, str]] = []  # (depth, size, path)
    base = folder.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(folder):
        depth = dirpath.count(os.sep) - base
        if depth > max_depth:
            dirnames[:] = []
            continue
        dl = dirpath.lower()
        if any(k in dl for k in ("redist", "_commonredist", "vcredist", "uninstall")):
            dirnames[:] = []
            continue
        for f in filenames:
            if not f.lower().endswith(".exe") or _is_bad_exe(f):
                continue
            fp = os.path.join(dirpath, f)
            try:
                sz = os.path.getsize(fp)
            except OSError:
                continue
            candidates.append((depth, sz, fp))
    if not candidates:
        return None
    min_depth = min(c[0] for c in candidates)
    best = max((c for c in candidates if c[0] == min_depth), key=lambda c: c[1])
    return best[2]


def scan_steam_games() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for lib in games.get_steam_libraries():
        common = os.path.join(lib, "common")
        if not os.path.isdir(common):
            continue
        try:
            entries = os.listdir(common)
        except OSError:
            continue
        for d in entries:
            folder = os.path.join(common, d)
            if not os.path.isdir(folder) or _is_blacklisted(d):
                continue
            exe = _find_main_exe(folder)
            if exe:
                found.append((d, exe))
    return found


def scan_other_games() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for root in _COMMON_ROOTS:
        if not os.path.isdir(root):
            continue
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for d in entries:
            folder = os.path.join(root, d)
            if not os.path.isdir(folder) or _is_blacklisted(d):
                continue
            exe = _find_main_exe(folder)
            if exe:
                found.append((d, exe))
    return found


def scan_installed_games() -> list[tuple[str, str]]:
    """检测其他已安装游戏，排除内置四款与已添加的自定义游戏。"""
    builtin_exes = set()
    builtin_folders = set()
    for g in games.GAMES:
        builtin_exes.update(e.lower() for e in g.exe_names)
        builtin_folders.update(k.lower() for k in g.search_keywords)
    custom = {os.path.normcase(c.get("exe_path", "")) for c in load_custom_games()}

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for name, exe in scan_steam_games() + scan_other_games():
        key = os.path.normcase(os.path.normpath(exe))
        base = os.path.basename(exe).lower()
        if key in seen or key in custom or base in builtin_exes:
            continue
        if any(kw in name.lower() for kw in builtin_folders):
            continue
        seen.add(key)
        result.append((name, exe))
    result.sort(key=lambda x: x[0].lower())
    return result


def load_custom_games() -> list[dict]:
    try:
        with open(CUSTOM_GAMES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [g for g in data if isinstance(g, dict) and g.get("exe_path")]
    except Exception:
        pass
    return []


def save_custom_games(games_list: list[dict]) -> bool:
    try:
        os.makedirs(os.path.dirname(CUSTOM_GAMES_FILE), exist_ok=True)
        with open(CUSTOM_GAMES_FILE, "w", encoding="utf-8") as f:
            json.dump(games_list, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def add_custom_game(name: str, exe_path: str) -> bool:
    """添加自定义游戏；返回是否成功写入（已存在或保存失败返回 False）。"""
    games_list = load_custom_games()
    if any(g.get("exe_path", "").lower() == exe_path.lower() for g in games_list):
        return False
    games_list.append({"name": name, "exe_path": exe_path})
    return save_custom_games(games_list)


def remove_custom_game(exe_path: str) -> None:
    games_list = [g for g in load_custom_games()
                  if g.get("exe_path", "").lower() != exe_path.lower()]
    save_custom_games(games_list)
