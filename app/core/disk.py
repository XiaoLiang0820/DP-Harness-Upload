"""FrameBoost 极帧加速 — 磁盘空间分析.

统计指定盘符下各顶层文件夹的占用大小，并列出大文件 Top N，
帮助找出「空间大户」。
"""

from __future__ import annotations

import os

LARGE_FILE_MB = 200  # 大文件阈值（MB）


def _folder_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                continue
    return total


def analyze_disk(root: str, progress=None, max_large_files: int = 40) -> dict:
    """分析磁盘：返回 {total, used, free, folders:[(name,path,size)], large_files:[(path,size)]}.

    progress(current, total) 用于上报进度。
    """
    result = {"total": 0, "used": 0, "free": 0, "folders": [], "large_files": []}
    try:
        usage = __import__("shutil").disk_usage(root)
        result["total"] = usage.total
        result["used"] = usage.used
        result["free"] = usage.free
    except Exception:
        pass

    try:
        entries = [d for d in os.listdir(root)
                   if os.path.isdir(os.path.join(root, d))]
    except OSError:
        entries = []

    folders = []
    large = []
    total_folders = len(entries) or 1
    for idx, d in enumerate(sorted(entries, key=str.lower)):
        full = os.path.join(root, d)
        size = 0
        try:
            for dirpath, _dirs, files in os.walk(full, onerror=lambda _e: None):
                for f in files:
                    fp = os.path.join(dirpath, f)
                    try:
                        sz = os.path.getsize(fp)
                    except OSError:
                        continue
                    size += sz
                    if sz >= LARGE_FILE_MB * 1024 * 1024:
                        large.append((fp, sz))
        except OSError:
            pass
        folders.append((d, full, size))
        if progress:
            progress(idx + 1, total_folders)

    folders.sort(key=lambda x: x[2], reverse=True)
    large.sort(key=lambda x: x[1], reverse=True)
    result["folders"] = folders
    result["large_files"] = large[:max_large_files]
    return result
