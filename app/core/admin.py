"""FrameBoost 极帧加速 — 管理员权限检测与提权重启."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys


def is_admin() -> bool:
    """检测当前进程是否以管理员权限运行."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """请求以管理员身份重新启动本程序（UAC 弹窗）."""
    try:
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        exe = sys.executable
        script = os.path.abspath(sys.argv[0])
        if script.endswith((".py", ".pyw")):
            cmd = f'"{exe}" "{script}" {params}'
        else:
            cmd = f'"{script}" {params}'
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable if script.endswith((".py", ".pyw")) else script,
            f'"{script}" {params}' if script.endswith((".py", ".pyw")) else params,
            None, 1,
        )
        # ShellExecuteW 返回值 > 32 表示成功
        return int(ret) > 32
    except Exception:
        return False


def _decode(raw: bytes) -> str:
    """解码命令输出：优先 UTF-8，失败再用中文 Windows 常用的 GBK/ANSI."""
    if not raw:
        return ""
    for enc in ("utf-8", "gbk", "mbcs"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="ignore")


def run_elevated_command(args: list[str]) -> tuple[int, str]:
    """运行一条系统命令（如 powercfg），返回 (returncode, 文本输出).

    注意：中文 Windows 的 powercfg/schtasks 输出为 GBK 编码，所以按字节读取后
    再自动解码，避免中文方案名被丢弃。
    """
    try:
        proc = subprocess.run(
            args, capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = proc.stdout or b""
        if not out:
            out = proc.stderr or b""
        return proc.returncode, _decode(out)
    except Exception as exc:  # pragma: no cover
        return -1, str(exc)
