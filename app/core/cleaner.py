"""FrameBoost 极帧加速 — 垃圾扫描与清理.

只清理明确的临时文件 / 缓存 / 系统残留，绝不触碰系统关键文件。
扫描与清理都在子线程中执行，通过回调上报进度，避免阻塞界面。
"""

from __future__ import annotations

import ctypes
import os
import tempfile
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Callable

ProgressFn = Callable[[int, int], None]


@dataclass
class CleanTarget:
    """一个可清理目标。paths 为已解析的绝对路径列表；special 为特殊处理类型."""

    key: str
    name: str = ""
    desc: str = ""
    paths: list[str] = field(default_factory=list)
    need_admin: bool = False
    default_on: bool = True
    special: str = ""  # "" | "recycle"

    size: int = 0
    count: int = 0


def _env(parts: list[str]) -> str:
    return os.path.join(*parts)


def build_targets() -> list[CleanTarget]:
    """构造全部扫描目标（路径已展开环境变量）."""
    local = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    windir = os.environ.get("WINDIR", r"C:\Windows")

    targets: list[CleanTarget] = [
        CleanTarget(
            key="target_user_temp",
            paths=[tempfile.gettempdir()],
            need_admin=False,
            default_on=True,
        ),
        CleanTarget(
            key="target_system_temp",
            paths=[os.path.join(windir, "Temp")],
            need_admin=True,
            default_on=False,
        ),
        CleanTarget(
            key="target_win_update",
            paths=[os.path.join(windir, "SoftwareDistribution", "Download")],
            need_admin=True,
            default_on=False,
        ),
        CleanTarget(
            key="target_thumb_cache",
            paths=[os.path.join(local, "Microsoft", "Windows", "Explorer")],
            need_admin=False,
            default_on=True,
        ),
        CleanTarget(
            key="target_shader_cache",
            paths=[os.path.join(local, "D3DSCache"), os.path.join(local, "NVIDIA", "DXCache"),
                   os.path.join(local, "AMD", "DxCache")],
            need_admin=False,
            default_on=True,
        ),
        CleanTarget(
            key="target_crash_dumps",
            paths=[os.path.join(local, "CrashDumps"), os.path.join(windir, "Minidump"),
                   os.path.join(windir, "MEMORY.DMP")],
            need_admin=True,
            default_on=False,
        ),
        CleanTarget(
            key="target_prefetch",
            paths=[os.path.join(windir, "Prefetch")],
            need_admin=True,
            default_on=False,
        ),
        CleanTarget(
            key="target_windows_old",
            paths=[os.path.join(windir, ".old")],
            need_admin=True,
            default_on=False,
        ),
        CleanTarget(
            key="target_wer",
            paths=[os.path.join(local, "Microsoft", "Windows", "WER"),
                   os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                                "Microsoft", "Windows", "WER")],
            need_admin=True,
            default_on=False,
        ),
        CleanTarget(
            key="target_delivery_opt",
            paths=[os.path.join(windir, "SoftwareDistribution", "DeliveryOptimization"),
                   os.path.join(windir, "ServiceProfiles", "NetworkService", "AppData", "Local",
                                "Microsoft", "Windows", "DeliveryOptimization")],
            need_admin=True,
            default_on=False,
        ),
        CleanTarget(
            key="target_font_cache",
            paths=[os.path.join(local, "Microsoft", "Windows", "FontCache"),
                   os.path.join(windir, "ServiceProfiles", "LocalService", "AppData", "Local",
                                "FontCache")],
            need_admin=False,
            default_on=True,
        ),
        CleanTarget(
            key="target_dns_cache",
            special="dns",
            need_admin=False,
            default_on=True,
        ),
        CleanTarget(
            key="target_recycle_bin",
            special="recycle",
            need_admin=False,
            default_on=True,
        ),
    ]

    # 浏览器缓存（各浏览器路径不同，存在才加入）
    browsers = [
        (os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cache"),
         os.path.join(local, "Google", "Chrome", "User Data", "Default", "Code Cache")),
        (os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cache"),
         os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Code Cache")),
        (os.path.join(appdata, "Mozilla", "Firefox", "Profiles"),),
        (os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Cache"),),
        (os.path.join(appdata, "Opera Software", "Opera Stable", "Cache"),),
        (os.path.join(local, "Vivaldi", "User Data", "Default", "Cache"),),
    ]
    browser_paths: list[str] = []
    for group in browsers:
        for p in group:
            if os.path.isdir(p):
                browser_paths.append(p)
    if browser_paths:
        targets.insert(6, CleanTarget(
            key="target_browser_cache", paths=browser_paths, need_admin=False, default_on=True,
        ))

    return targets


def _scan_size(path: str) -> tuple[int, int]:
    """返回 (总字节数, 文件数)。失败返回 (0,0)。"""
    total, count = 0, 0
    try:
        if os.path.isfile(path):
            try:
                return os.path.getsize(path), 1
            except OSError:
                return 0, 0
        for _root, _dirs, files in os.walk(path, onerror=lambda _e: None):
            for f in files:
                fp = os.path.join(_root, f)
                try:
                    total += os.path.getsize(fp)
                    count += 1
                except OSError:
                    continue
    except OSError:
        pass
    return total, count


def scan_all(targets: list[CleanTarget], progress: ProgressFn | None = None) -> list[CleanTarget]:
    """扫描所有目标，填充 size/count 并返回。"""
    total_targets = len(targets)
    for idx, tgt in enumerate(targets):
        if tgt.special == "recycle":
            tgt.size, tgt.count = recycle_bin_stats()
        else:
            size = count = 0
            for p in tgt.paths:
                if os.path.exists(p):
                    s, c = _scan_size(p)
                    size += s
                    count += c
            tgt.size, tgt.count = size, count
        if progress:
            progress(idx + 1, total_targets)
    return targets


# --------------------------------------------------------------------------- #
# 删除 / 回收站
# --------------------------------------------------------------------------- #

def _recycle(path: str) -> None:
    """使用 Shell 将文件/目录移入回收站."""
    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x40
    FOF_NOCONFIRMATION = 0x10
    FOF_SILENT = 0x4
    FOF_NOERRORUI = 0x400

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_uint),
            ("fAnyOperationsAborted", ctypes.c_int),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    buf = ctypes.create_unicode_buffer(path + "\0")
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = ctypes.cast(buf, ctypes.c_wchar_p)
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    ret = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if ret != 0:
        raise OSError(f"SHFileOperationW failed ({ret})")


def _remove(path: str, to_recycle: bool) -> None:
    if to_recycle:
        _recycle(path)
    else:
        if os.path.isdir(path) and not os.path.islink(path):
            os.rmdir(path)
        else:
            os.remove(path)


def _clean_path(path: str, to_recycle: bool) -> tuple[int, int, int]:
    """清理单个路径，返回 (释放字节, 删除数, 跳过数)。仅删除文件，不删除目录本身."""
    freed = deleted = skipped = 0
    try:
        if os.path.isfile(path):
            try:
                sz = os.path.getsize(path)
                _remove(path, to_recycle)
                freed += sz
                deleted += 1
            except OSError:
                skipped += 1
            return freed, deleted, skipped

        for _root, _dirs, files in os.walk(path, onerror=lambda _e: None):
            for f in files:
                fp = os.path.join(_root, f)
                try:
                    sz = os.path.getsize(fp)
                    _remove(fp, to_recycle)
                    freed += sz
                    deleted += 1
                except OSError:
                    skipped += 1
    except OSError:
        skipped += 1
    return freed, deleted, skipped


def clean_targets(targets: list[CleanTarget], to_recycle: bool = False,
                  progress: ProgressFn | None = None) -> tuple[int, int, int]:
    """清理选中的目标，返回 (释放字节, 删除数, 跳过数)。"""
    freed = deleted = skipped = 0
    for idx, tgt in enumerate(targets):
        if tgt.special == "recycle":
            try:
                if empty_recycle_bin():
                    deleted += 1
            except Exception:
                skipped += 1
        elif tgt.special == "dns":
            try:
                if flush_dns():
                    deleted += 1
            except Exception:
                skipped += 1
        else:
            for p in tgt.paths:
                if os.path.exists(p):
                    f, d, s = _clean_path(p, to_recycle)
                    freed += f
                    deleted += d
                    skipped += s
        if progress:
            progress(idx + 1, len(targets))
    return freed, deleted, skipped


def flush_dns() -> bool:
    """刷新 DNS 解析缓存."""
    try:
        import subprocess
        proc = subprocess.run(["ipconfig", "/flushdns"], capture_output=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return proc.returncode == 0
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# 回收站
# --------------------------------------------------------------------------- #

def recycle_bin_stats() -> tuple[int, int]:
    """估算回收站占用大小（返回 (字节, 文件数)，失败返回 (0,0)）。"""
    try:
        import ctypes.wintypes as wt

        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("i64Size", ctypes.c_longlong),
                        ("i64NumItems", ctypes.c_longlong)]

        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        ret = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if ret == 0:  # S_OK
            return int(info.i64Size), int(info.i64NumItems)
    except Exception:
        pass
    return 0, 0


def empty_recycle_bin() -> bool:
    """清空回收站（不弹确认、不显示进度、静音）。"""
    try:
        SHERB_NOCONFIRMATION = 0x1
        SHERB_NOPROGRESSUI = 0x2
        SHERB_NOSOUND = 0x4
        ret = ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND,
        )
        return ret == 0
    except Exception:
        return False


def format_bytes(num: float) -> str:
    """把字节数格式化为易读字符串."""
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(num)} {unit}"
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"
