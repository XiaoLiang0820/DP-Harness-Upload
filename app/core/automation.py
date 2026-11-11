"""FrameBoost 极帧加速 — 开机自启清理 & 定时清理.

- 开机自启：写入 HKCU\\...\\Run，登录后以 --autoclean 静默清理安全目标；
- 定时清理：注册 Windows 计划任务 FrameBoostAutoClean，每天定时静默清理；
- 静默清理：只清理「默认勾选且无需管理员」的安全目标，结果追加写入日志，
  供设置页「上次自动清理」展示。
"""

from __future__ import annotations

import datetime
import os
import sys
import winreg

from . import admin

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
ENTRY_NAME = "FrameBoostAutoClean"
TASK_NAME = "FrameBoostAutoClean"
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", ".")), "FrameBoost")
LOG_FILE = os.path.join(LOG_DIR, "autoclean.log")


def _run_script() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "run.py"))


def _run_command() -> str:
    """返回启动本程序的命令行（打包后为 exe，开发态为 python run.py）。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{_run_script()}"'


def _app_command(extra: str = "") -> str:
    return f"{_run_command()} {extra}".strip()


# --------------------------------------------------------------------------- #
# 开机自启
# --------------------------------------------------------------------------- #

def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, ENTRY_NAME)
            return True
    except OSError:
        return False


def set_autostart(enable: bool) -> bool:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enable:
                winreg.SetValueEx(key, ENTRY_NAME, 0, winreg.REG_SZ, _app_command("--autoclean"))
            else:
                try:
                    winreg.DeleteValue(key, ENTRY_NAME)
                except OSError:
                    pass
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# 定时清理（计划任务）
# --------------------------------------------------------------------------- #

def is_scheduled() -> bool:
    code, _ = admin.run_elevated_command(["schtasks", "/query", "/tn", TASK_NAME])
    return code == 0


def set_schedule(enable: bool, hour: int = 12, minute: int = 0) -> bool:
    if enable:
        cmd = ["schtasks", "/create", "/tn", TASK_NAME,
               "/tr", _app_command("--autoclean"),
               "/sc", "daily", "/st", f"{int(hour):02d}:{int(minute):02d}", "/f"]
        code, _ = admin.run_elevated_command(cmd)
        return code == 0
    code, _ = admin.run_elevated_command(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])
    return code == 0


# --------------------------------------------------------------------------- #
# 静默清理 + 日志
# --------------------------------------------------------------------------- #

# 自动清理只处理「绝对安全、可自动重建」的目标，避免影响日常使用：
# 不含浏览器缓存（会清空登录态）、不含回收站（可能误删可恢复文件）、不含需管理员项。
AUTO_SAFE_KEYS = {"target_user_temp", "target_thumb_cache", "target_shader_cache"}


def _auto_targets() -> list:
    from . import cleaner
    return [t for t in cleaner.build_targets() if t.key in AUTO_SAFE_KEYS]


def run_autoclean_silent() -> tuple[int, int, int]:
    """静默清理绝对安全的目标，返回 (释放字节, 删除数, 跳过数)。"""
    from . import cleaner
    targets = _auto_targets()
    freed, deleted, skipped = cleaner.clean_targets(targets, to_recycle=False)
    _append_log(freed, deleted, skipped)
    return freed, deleted, skipped


def safe_targets_preview() -> list:
    """返回静默清理将覆盖的目标（只读，用于展示效果，不删除）。"""
    return _auto_targets()


def _append_log(freed: int, deleted: int, skipped: int) -> None:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}\t{freed}\t{deleted}\t{skipped}\n")
    except OSError:
        pass


def read_last_autoclean() -> tuple[str, int] | None:
    """返回 (时间字符串, 释放字节)，无记录返回 None。"""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        if not lines:
            return None
        parts = lines[-1].strip().split("\t")
        if len(parts) >= 2:
            ts = parts[0]
            freed = int(parts[1]) if parts[1].isdigit() else 0
            return ts, freed
    except Exception:
        pass
    return None
