"""FrameBoost 极帧加速 — 轻量偏好存储.

存放在 %LOCALAPPDATA%\\FrameBoost\\prefs.json，与 kill_list.json 同目录。
用来记住「高级设置是否已解锁」「温度墙开关」等跨会话状态。

设计：读写都做异常兜底，任何情况下都不能因为配置损坏而让主程序起不来。
"""

from __future__ import annotations

import json
import os

_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", ".")), "FrameBoost")
_FILE = os.path.join(_DIR, "prefs.json")

# 默认值：新增键一律给默认值，老版本配置文件缺失新键时也能正常工作
DEFAULTS: dict = {
    "advanced_unlocked": False,   # 高级设置总开关（持久化，避免每次重开）
    "thermal_guard": False,       # 温度墙守护
    "thermal_threshold": 90,      # 触发温度（°C）
    "thermal_floor": 70,          # 触发后最大处理器状态（%）
    "thermal_engaged": False,     # 当前是否已因超温而降频
    "thermal_saved_max": 100,     # 降频前保存的最大处理器状态，用于恢复
    "also_dc": True,              # 同时应用到电池供电（笔记本）
}

_CACHE: dict | None = None


def load() -> dict:
    """读取全部配置（带内存缓存与默认值合并）."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    data: dict = {}
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data = raw
    except Exception:
        data = {}
    merged = dict(DEFAULTS)
    merged.update(data)
    _CACHE = merged
    return merged


def save(patch: dict) -> bool:
    """把 patch 合并写入磁盘，返回是否成功."""
    global _CACHE
    try:
        data = dict(load())
        data.update(patch)
        os.makedirs(_DIR, exist_ok=True)
        tmp = _FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _FILE)
        _CACHE = data
        return True
    except Exception:
        return False


def get(key: str, default=None):
    return load().get(key, DEFAULTS.get(key, default))


def set_value(key: str, value) -> bool:
    return save({key: value})
