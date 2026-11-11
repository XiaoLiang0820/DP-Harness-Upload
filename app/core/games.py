"""FrameBoost 极帧加速 — 游戏专属配置.

为三角洲行动 / CS2 / 我的世界 / PUBG 提供：
进程名识别、Steam 安装检测、运行状态、推荐启动参数与优化建议。
"""

from __future__ import annotations

import os
import re
import winreg
from dataclasses import dataclass, field

try:
    import psutil
    HAS_PSUTIL = True
except Exception:  # pragma: no cover
    psutil = None
    HAS_PSUTIL = False


@dataclass
class GameProfile:
    id: str
    exe_names: list[str]          # 进程/可执行文件名（小写）
    search_keywords: list[str]    # Steam common 目录关键词
    launch_options: str           # 推荐启动参数
    tips: list[str]               # 优化建议（i18n 键或纯文本）


GAMES: list[GameProfile] = [
    GameProfile(
        id="deltaforce",
        exe_names=["deltaforceclient-win64-shipping.exe", "deltaforce.exe", "deltaforceclient.exe"],
        search_keywords=["delta force", "deltaforce"],
        launch_options="-dx12 -USEALLAVAILABLECORES -high",
        tips=[
            "分辨率：优先使用原生分辨率，关闭动态分辨率。",
            "画面：开启 DLSS/FSR 并设为“性能/均衡”，阴影与体积光调到中。",
            "网络：三角洲对网络敏感，关闭后台下载与直播软件。",
        ],
    ),
    GameProfile(
        id="cs2",
        exe_names=["cs2.exe"],
        search_keywords=["counter-strike", "cs2"],
        launch_options="-high -novid -nojoy +fps_max 0",
        tips=[
            "分辨率：4:3 拉伸可提升观感与帧数，16:9 更清晰。",
            "画面：阴影质量中、纹理高、其余低，关闭垂直同步。",
            "启动项：-high 提升进程优先级，+fps_max 0 解锁帧率上限。",
        ],
    ),
    GameProfile(
        id="minecraft",
        exe_names=["javaw.exe", "java.exe", "minecraft.exe"],
        search_keywords=["minecraft"],
        launch_options="-Xmx4G -XX:+UseG1GC -XX:+ParallelRefProcEnabled",
        tips=[
            "内存：给 JVM 分配 4–8G（-Xmx4G），视物理内存调整。",
            "模组：大量模组时增大 -Xmx 并开启 G1GC 垃圾回收。",
            "渲染：OptiFine / Sodium 可大幅提升帧数。",
        ],
    ),
    GameProfile(
        id="pubg",
        exe_names=["tslgame.exe", "tslgame_be.exe", "pubg.exe"],
        search_keywords=["pubg", "battlegrounds"],
        launch_options="-high -USEALLAVAILABLECORES -malloc=system -refresh 144",
        tips=[
            "画面：抗锯齿中、后期处理低、阴影低、纹理高。",
            "帧数：关闭垂直同步，开启动态模糊以外的特效。",
            "内存：确保至少 16G 物理内存，关闭浏览器与直播。",
        ],
    ),
]

GAME_ORDER = ["deltaforce", "cs2", "minecraft", "pubg"]

# 各游戏的英文优化建议（中文版保存在 GameProfile.tips 中）
TIPS_EN: dict[str, list[str]] = {
    "deltaforce": [
        "Resolution: keep native, disable dynamic resolution.",
        "Graphics: enable DLSS/FSR at Performance/Balanced; set shadows & volumetrics to Medium.",
        "Network: Delta Force is latency-sensitive — close background downloads & streaming apps.",
    ],
    "cs2": [
        "Resolution: 4:3 stretched boosts visibility & FPS; 16:9 is sharper.",
        "Graphics: Medium shadows, High textures, Low everything else, disable V-Sync.",
        "Launch: -high raises process priority; +fps_max 0 unlocks the frame cap.",
    ],
    "minecraft": [
        "Memory: allocate 4–8G to the JVM (-Xmx4G), adjust to your physical RAM.",
        "Mods: raise -Xmx and enable G1GC for heavy modpacks.",
        "Rendering: OptiFine / Sodium greatly improves FPS.",
    ],
    "pubg": [
        "Graphics: Medium AA, Low post-processing, Low shadows, High textures.",
        "FPS: disable V-Sync; keep effects (except motion blur) on.",
        "Memory: ensure 16G+ RAM, close browsers & streaming.",
    ],
}


def get_game(game_id: str) -> GameProfile | None:
    for g in GAMES:
        if g.id == game_id:
            return g
    return None


# --------------------------------------------------------------------------- #
# Steam 检测
# --------------------------------------------------------------------------- #

def get_steam_path() -> str | None:
    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
    ]
    for root, path in keys:
        try:
            with winreg.OpenKey(root, path) as key:
                v, _ = winreg.QueryValueEx(key, "SteamPath")
                if v:
                    return v
        except OSError:
            continue
    return None


def get_steam_libraries() -> list[str]:
    steam = get_steam_path()
    libs: list[str] = []
    if not steam:
        return libs
    libs.append(os.path.join(steam, "steamapps"))
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    try:
        if os.path.exists(vdf):
            with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                p = m.group(1).replace("\\\\", "\\")
                libs.append(os.path.join(p, "steamapps"))
    except Exception:
        pass
    # 按规范化路径去重（大小写 / 斜杠差异）
    seen: set[str] = set()
    result: list[str] = []
    for l in libs:
        key = os.path.normcase(os.path.normpath(l))
        if key in seen:
            continue
        seen.add(key)
        if os.path.isdir(l):
            result.append(l)
    return result


def _find_exe_limited(root: str, names: set[str], max_depth: int = 5) -> str | None:
    """在目录内限深度搜索目标可执行文件，找到即返回."""
    base = root.rstrip(os.sep).count(os.sep)
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath.count(os.sep) - base
            if depth > max_depth:
                dirnames[:] = []
                continue
            for f in filenames:
                if f.lower() in names:
                    return os.path.join(dirpath, f)
    except OSError:
        pass
    return None


def _drive_roots() -> list[str]:
    roots: list[str] = []
    for letter in "CDEFGHIJ":
        p = f"{letter}:\\"
        if os.path.isdir(p):
            roots.append(p)
    return roots


def _match_folders(root: str, keywords: list[str], max_depth: int = 2) -> list[str]:
    """在 root 下按文件夹名匹配关键词，返回匹配的文件夹路径（限深度，避免全盘遍历）."""
    found: list[str] = []
    try:
        top = os.listdir(root)
    except OSError:
        return found
    for d in top:
        full = os.path.join(root, d)
        if not os.path.isdir(full):
            continue
        if any(k in d.lower() for k in keywords):
            found.append(full)
        elif max_depth > 1:
            try:
                subs = os.listdir(full)
            except OSError:
                continue
            for s in subs:
                subfull = os.path.join(full, s)
                if os.path.isdir(subfull) and any(k in s.lower() for k in keywords):
                    found.append(subfull)
    return found


def find_game_install(game: GameProfile) -> str | None:
    """定位游戏安装：先扫 Steam 库，再扫各盘符/常见目录（WeGame、独立安装等）.

    对 Minecraft（Java 版无独立 exe）额外用 %APPDATA%\\.minecraft 数据目录判断。
    """
    names = {n.lower() for n in game.exe_names}
    keywords = [k.lower() for k in game.search_keywords]

    # 1) Steam 库
    for lib in get_steam_libraries():
        common = os.path.join(lib, "common")
        if not os.path.isdir(common):
            continue
        try:
            entries = os.listdir(common)
        except OSError:
            continue
        for d in entries:
            if any(k in d.lower() for k in keywords):
                hit = _find_exe_limited(os.path.join(common, d), names)
                if hit:
                    return hit

    # 2) 各盘符 + 常见安装目录（匹配文件夹名后只在匹配目录内找 exe）
    search_roots = _drive_roots() + [
        r"C:\Program Files", r"C:\Program Files (x86)",
        r"D:\Program Files", r"E:\Program Files", r"F:\Program Files",
    ]
    for root in search_roots:
        for folder in _match_folders(root, keywords, max_depth=2):
            hit = _find_exe_limited(folder, names)
            if hit:
                return hit

    # 3) Minecraft 特殊：Java 版用 .minecraft 数据目录判断
    if game.id == "minecraft":
        for base in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):
            if base:
                mc = os.path.join(base, ".minecraft")
                if os.path.isdir(mc):
                    return mc

    return None


def is_exe_running(exe_names: list[str]) -> bool:
    """判断指定进程名是否有正在运行。"""
    if not HAS_PSUTIL:
        return False
    names = {n.lower() for n in exe_names if n}
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info["name"] or "").lower() in names:
                return True
        except Exception:
            continue
    return False


def is_game_running(game: GameProfile) -> bool:
    return is_exe_running(game.exe_names)
