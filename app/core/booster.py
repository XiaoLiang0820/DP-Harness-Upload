"""FrameBoost 极帧加速 — 游戏加速核心.

包含：电源计划切换、内存释放/待机列表清理、后台进程结束、
Windows 游戏模式开关、游戏进程优先级提升、硬件加速 GPU 调度检测。
所有系统级修改均带异常保护与注册表备份。
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import winreg
from dataclasses import dataclass

try:
    import psutil
    HAS_PSUTIL = True
except Exception:  # pragma: no cover
    psutil = None
    HAS_PSUTIL = False

from . import admin

# 常见电源计划 GUID
GUID_HIGH_PERF = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
GUID_ULTIMATE = "e9a42b02-d5df-448d-aa00-03f14749eb61"
GUID_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"

# 默认的「安全可结束」后台进程（不影响系统稳定）
DEFAULT_KILL_LIST = [
    "OneDrive.exe",
    "ms-teams.exe",
    "Teams.exe",
    "YourPhone.exe",
    "PhoneExperienceHost.exe",
    "Widgets.exe",
    "GameBar.exe",
    "GameBarFTServer.exe",
    "SkypeApp.exe",
    "Cortana.exe",
]

_POWER_PLAN_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


@dataclass
class SystemStats:
    memory_percent: float = 0.0
    memory_used: int = 0
    memory_total: int = 0
    cpu_percent: float = 0.0
    process_count: int = 0
    logical_cpus: int = 0
    power_plan_name: str = ""
    power_plan_guid: str = ""
    game_mode: bool = False
    hags: bool = False


def get_system_stats() -> SystemStats:
    """采集首页 / 加速页所需的系统状态."""
    stats = SystemStats()
    if HAS_PSUTIL:
        try:
            vm = psutil.virtual_memory()
            stats.memory_percent = vm.percent
            stats.memory_used = vm.used
            stats.memory_total = vm.total
        except Exception:
            pass
        try:
            stats.cpu_percent = psutil.cpu_percent(interval=0.2)
        except Exception:
            pass
        try:
            stats.process_count = len(psutil.pids())
        except Exception:
            pass
        try:
            stats.logical_cpus = psutil.cpu_count(logical=True) or 0
        except Exception:
            pass
    stats.power_plan_name = get_active_power_plan_name()
    stats.power_plan_guid = get_active_power_plan()
    stats.game_mode = is_game_mode_on()
    stats.hags = is_hags_on()
    return stats


# --------------------------------------------------------------------------- #
# 电源计划
# --------------------------------------------------------------------------- #

def list_power_plans() -> list[tuple[str, str]]:
    """返回 [(GUID, 名称), ...]."""
    code, out = admin.run_elevated_command(["powercfg", "/list"])
    if code != 0:
        return []
    plans: list[tuple[str, str]] = []
    for line in out.splitlines():
        m = _POWER_PLAN_RE.search(line)
        if m:
            guid = m.group(1)
            name_m = re.search(r"\(([^)]*)\)", line)
            name = name_m.group(1).strip() if name_m else guid
            name = name.lstrip("*").strip()
            plans.append((guid, name))
    return plans


def get_active_power_plan() -> str:
    code, out = admin.run_elevated_command(["powercfg", "/getactivescheme"])
    if code == 0:
        m = _POWER_PLAN_RE.search(out)
        if m:
            return m.group(1)
    # 注册表兜底：直接读取当前激活的电源方案 GUID（无需管理员）
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes",
        ) as key:
            v, _ = winreg.QueryValueEx(key, "ActivePowerScheme")
            return str(v)
    except OSError:
        pass
    return ""


def get_active_power_plan_name() -> str:
    active = get_active_power_plan()
    for guid, name in list_power_plans():
        if guid.lower() == active.lower():
            return name
    return active or ""


def set_power_plan(guid: str) -> bool:
    code, _ = admin.run_elevated_command(["powercfg", "/setactive", guid])
    return code == 0


def ensure_high_performance() -> str:
    """切换到高性能（若不存在则尝试创建终极性能方案），返回最终方案名."""
    # 优先终极性能
    for guid in (GUID_ULTIMATE, GUID_HIGH_PERF):
        if any(g.lower() == guid.lower() for g, _ in list_power_plans()):
            if set_power_plan(guid):
                return get_active_power_plan_name()
    # 尝试创建终极性能方案
    admin.run_elevated_command(["powercfg", "-duplicatescheme", GUID_ULTIMATE])
    if set_power_plan(GUID_ULTIMATE):
        return get_active_power_plan_name()
    # 兜底：高性能
    if set_power_plan(GUID_HIGH_PERF):
        return get_active_power_plan_name()
    return ""


def restore_balanced_power_plan() -> bool:
    """切回平衡电源计划（用于游戏结束后的「恢复日常模式」）。"""
    if any(g.lower() == GUID_BALANCED.lower() for g, _ in list_power_plans()):
        return set_power_plan(GUID_BALANCED)
    return False


# --------------------------------------------------------------------------- #
# 内存释放
# --------------------------------------------------------------------------- #

def trim_working_set(pid: int) -> bool:
    """压缩单个进程的工作集，释放其物理内存."""
    try:
        PROCESS_SET_QUOTA = 0x0100
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        h = kernel32.OpenProcess(PROCESS_SET_QUOTA, False, pid)
        if not h:
            return False
        try:
            kernel32.SetProcessWorkingSetSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
            kernel32.SetProcessWorkingSetSize.restype = ctypes.c_int
            return bool(kernel32.SetProcessWorkingSetSize(h, ctypes.c_size_t(-1), ctypes.c_size_t(-1)))
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return False


def purge_standby_list() -> bool:
    """清理内存待机列表（需管理员，失败返回 False）."""
    if not admin.is_admin():
        return False
    try:
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        SystemMemoryListInformation = 80
        MemoryPurgeStandbyList = 4

        class Cmd(ctypes.Structure):
            _fields_ = [("command", ctypes.c_ulong)]

        cmd = Cmd()
        cmd.command = MemoryPurgeStandbyList
        ntdll.NtSetSystemInformation.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        ntdll.NtSetSystemInformation.restype = ctypes.c_long
        status = ntdll.NtSetSystemInformation(SystemMemoryListInformation, ctypes.byref(cmd), ctypes.sizeof(cmd))
        return status == 0
    except Exception:
        return False


def free_memory() -> int:
    """综合内存释放：先清理待机列表，再压缩所有用户进程工作集。返回估算释放字节."""
    before = after = 0
    if HAS_PSUTIL:
        try:
            before = psutil.virtual_memory().available
        except Exception:
            pass
    purge_standby_list()
    if HAS_PSUTIL:
        for p in psutil.process_iter(["pid"]):
            try:
                trim_working_set(p.info["pid"])
            except Exception:
                continue
        try:
            after = psutil.virtual_memory().available
        except Exception:
            pass
    return max(0, after - before)


# --------------------------------------------------------------------------- #
# 后台进程
# --------------------------------------------------------------------------- #

def kill_background_processes(kill_list: list[str] | None = None) -> int:
    """结束指定的后台进程，返回成功结束的数量（默认使用用户自定义名单）."""
    names = kill_list if kill_list is not None else load_kill_list()
    if not HAS_PSUTIL:
        return 0
    lower = {n.lower() for n in names}
    killed = 0
    for p in psutil.process_iter(["name", "pid"]):
        try:
            if (p.info["name"] or "").lower() in lower:
                p.kill()
                killed += 1
        except Exception:
            continue
    return killed


# --------------------------------------------------------------------------- #
# 游戏模式 / HAGS / 优先级
# --------------------------------------------------------------------------- #

def _read_reg(root, path: str, value: str):
    try:
        with winreg.OpenKey(root, path) as key:
            v, _ = winreg.QueryValueEx(key, value)
            return v
    except OSError:
        return None


def _write_reg(root, path: str, value: str, data: int, backup: bool = True) -> bool:
    try:
        if backup:
            _backup_reg_value(root, path, value)
        with winreg.CreateKey(root, path) as key:
            winreg.SetValueEx(key, value, 0, winreg.REG_DWORD, data)
        return True
    except OSError:
        return False


def _backup_reg_value(root, path: str, value: str) -> None:
    """导出注册表键到用户临时目录作为备份."""
    try:
        keyname = path.replace("\\", "_").replace("/", "_")
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(os.environ.get("TEMP", "."), "FrameBoost_backup")
        os.makedirs(backup_dir, exist_ok=True)
        out_file = os.path.join(backup_dir, f"{keyname}__{value}__{stamp}.reg")
        code, _ = admin.run_elevated_command(
            ["reg", "export", _reg_path_str(root, path), out_file, "/y"]
        )
        # reg export 的路径需为注册表路径
        if code != 0:
            # 退而求其次：只记录旧值
            old = _read_reg(root, path, value)
            if old is not None:
                with open(out_file + ".txt", "w", encoding="utf-8") as f:
                    f.write(f"{_reg_path_str(root, path)}\\{value} = {old}\n")
    except Exception:
        pass


def _reg_path_str(root, path: str) -> str:
    hive = "HKCU" if root == winreg.HKEY_CURRENT_USER else "HKLM"
    return f"{hive}\\{path}"


def is_game_mode_on() -> bool:
    return bool(_read_reg(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AutoGameModeEnabled"))


def set_game_mode(enable: bool = True) -> bool:
    ok1 = _write_reg(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1 if enable else 0)
    ok2 = _write_reg(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1 if enable else 0)
    return ok1 and ok2


def is_hags_on() -> bool:
    """硬件加速 GPU 调度（HwSchMode: 2=开启）。"""
    v = _read_reg(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode")
    return bool(v and int(v) == 2)


def set_hags(enable: bool = True) -> bool:
    if not admin.is_admin():
        return False
    return _write_reg(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
                      "HwSchMode", 2 if enable else 0)


def raise_process_priority(process_names: list[str], priority_class: int = 0x80) -> int:
    """将匹配名称的进程优先级设为高（0x80=HIGH_PRIORITY_CLASS），返回成功数量."""
    if not HAS_PSUTIL:
        return 0
    lower = {n.lower() for n in process_names if n}
    PROCESS_SET_INFORMATION = 0x0200
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.SetPriorityClass.restype = ctypes.c_int
    count = 0
    for p in psutil.process_iter(["name", "pid"]):
        try:
            if (p.info["name"] or "").lower() in lower:
                h = kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, p.info["pid"])
                if h:
                    kernel32.SetPriorityClass(h, priority_class)
                    kernel32.CloseHandle(h)
                    count += 1
        except Exception:
            continue
    return count


# --------------------------------------------------------------------------- #
# 进阶优化：定时器分辨率 / 电源细化 / Game DVR / 全屏优化 / 自定义进程名单
# --------------------------------------------------------------------------- #

def set_timer_resolution(enable: bool = True, resolution_100ns: int = 5000) -> bool:
    """设置系统定时器分辨率（默认 0.5ms = 5000 × 100ns），降低输入延迟."""
    try:
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        ntdll.NtSetTimerResolution.argtypes = [
            ctypes.c_ulong, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ulong)
        ]
        ntdll.NtSetTimerResolution.restype = ctypes.c_long
        cur = ctypes.c_ulong()
        ret = ntdll.NtSetTimerResolution(resolution_100ns, 1 if enable else 0, ctypes.byref(cur))
        return ret == 0
    except Exception:
        return False


# 电源子项：(子组 GUID, 设置 GUID, 值)
_POWER_TWEAKS = [
    ("54533251-82be-4824-96c1-47b60b740d00", "893dee8e-2bef-41e0-89c6-b55d0929964c", "100"),  # 最低处理器状态
    ("54533251-82be-4824-96c1-47b60b740d00", "0cc5b647-c1df-4637-891a-dec35c318583", "100"),  # 核心停放最小核心 100%
    ("501a4d13-42af-4429-9fd1-a8218c268e20", "ee12f906-d277-404b-b6da-e5fa1a576df5", "0"),    # PCIe 链接电源管理 关
    ("2a737441-1930-4402-8d77-b2bebba308a3", "48e6b7a6-50f5-4782-a5d4-53bb8f07e226", "0"),    # USB 选择性暂停 关
    ("0012ee47-9041-4b5d-9b77-535fba8b1442", "6738e2c4-e8a5-4a42-b16a-e040e769756e", "0"),    # 硬盘 从不关闭
]


def apply_power_tweaks() -> bool:
    """细化当前电源方案（需管理员）：最低处理器状态/核心停放/PCIe/USB/硬盘."""
    ok = True
    for sub_guid, setting_guid, value in _POWER_TWEAKS:
        code, _ = admin.run_elevated_command([
            "powercfg", "/setacvalueindex", "SCHEME_CURRENT", sub_guid, setting_guid, value
        ])
        if code != 0:
            ok = False
    admin.run_elevated_command(["powercfg", "/setactive", "SCHEME_CURRENT"])
    return ok


def set_game_dvr(enable: bool = False) -> bool:
    """开关 Xbox Game DVR 后台录制."""
    v = 1 if enable else 0
    a = _write_reg(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", "GameDVR_Enabled", v)
    b = _write_reg(winreg.HKEY_CURRENT_USER,
                   r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", v)
    c = _write_reg(winreg.HKEY_CURRENT_USER,
                   r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "HistoricalCaptureEnabled", v)
    return a and b and c


def set_fullscreen_optimizations(exe_path: str, disable: bool = True) -> bool:
    """对指定 exe 开关「禁用全屏优化」."""
    key = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            if disable:
                winreg.SetValueEx(k, exe_path, 0, winreg.REG_SZ, "~ DISABLEDXMAXIMIZEDWINDOWEDMODE")
            else:
                try:
                    winreg.DeleteValue(k, exe_path)
                except OSError:
                    pass
        return True
    except OSError:
        return False


KILL_LIST_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", ".")),
    "FrameBoost", "kill_list.json",
)


def load_kill_list() -> list[str]:
    try:
        with open(KILL_LIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            names = [str(x).strip() for x in data if str(x).strip()]
            if names:
                return names
    except Exception:
        pass
    return list(DEFAULT_KILL_LIST)


def save_kill_list(names: list[str]) -> None:
    try:
        os.makedirs(os.path.dirname(KILL_LIST_FILE), exist_ok=True)
        with open(KILL_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump([n for n in names if n.strip()], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 设备自适应加速档位
# --------------------------------------------------------------------------- #

def apply_profile(tier: str) -> dict:
    """按档位应用加速：aggressive（台式）/ balanced（游戏本）/ gentle（轻薄本/电池）."""
    result = {"tier": tier, "mem": 0, "procs": 0, "power": ""}
    if tier == "gentle":
        # 轻薄本 / 电池供电：不动高性能电源，只做温和优化
        result["mem"] = free_memory()
        result["procs"] = kill_background_processes()
        set_game_mode(True)
        return result
    # aggressive / balanced：切高性能 + 常规优化
    result["power"] = ensure_high_performance()
    result["mem"] = free_memory()
    result["procs"] = kill_background_processes()
    set_game_mode(True)
    set_timer_resolution(True)
    set_game_dvr(False)
    if tier == "aggressive":
        apply_power_tweaks()
    return result


def revert_profile() -> None:
    """还原到日常状态."""
    set_timer_resolution(False)
    set_game_dvr(True)
    restore_balanced_power_plan()


# --------------------------------------------------------------------------- #
# 高级：CPU 频率上限 / 性能提升模式（Windows 电源管理，无需第三方驱动）
# 说明：Windows 无法在用户态直接调 CPU 电压，电压调节需 ThrottleStop / Intel XTU /
# AMD Ryzen Master 等厂商工具；这里提供频率相关的可控项。
# --------------------------------------------------------------------------- #

_SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
_PROCTHROTTLEMAX = "bc5038f7-23e0-4960-96da-33abaf5935ec"   # 最大处理器状态 %
_PROCTHROTTLEMIN = "893dee8e-2bef-41e0-89c6-b55d0929964c"   # 最小处理器状态 %
_PERFBOOSTMODE = "be337238-0d82-4146-a960-4f3749d470c7"     # 性能提升模式


def set_cpu_limit(max_percent: int | None = None,
                  min_percent: int | None = None,
                  boost_mode: int | None = None) -> bool:
    """调整 CPU 频率相关设置（需管理员）.

    max_percent: 最大处理器状态 0-100（越低越省电/低温，但也降性能）
    min_percent: 最小处理器状态 0-100
    boost_mode : 0=禁用 / 1=启用 / 2=激进
    """
    ok = True
    if max_percent is not None:
        code, _ = admin.run_elevated_command([
            "powercfg", "/setacvalueindex", "SCHEME_CURRENT",
            _SUB_PROCESSOR, _PROCTHROTTLEMAX, str(int(max_percent))])
        ok = ok and code == 0
    if min_percent is not None:
        code, _ = admin.run_elevated_command([
            "powercfg", "/setacvalueindex", "SCHEME_CURRENT",
            _SUB_PROCESSOR, _PROCTHROTTLEMIN, str(int(min_percent))])
        ok = ok and code == 0
    if boost_mode is not None:
        admin.run_elevated_command([
            "powercfg", "/attributes", _SUB_PROCESSOR, _PERFBOOSTMODE, "-ATTRIB_HIDE"])
        code, _ = admin.run_elevated_command([
            "powercfg", "/setacvalueindex", "SCHEME_CURRENT",
            _SUB_PROCESSOR, _PERFBOOSTMODE, str(int(boost_mode))])
        ok = ok and code == 0
    admin.run_elevated_command(["powercfg", "/setactive", "SCHEME_CURRENT"])
    return ok


def get_cpu_freq_mhz() -> int | None:
    """当前 CPU 频率（MHz），部分平台可能不可用."""
    try:
        if not HAS_PSUTIL:
            return None
        f = psutil.cpu_freq()
        if f and f.current:
            return int(f.current)
    except Exception:
        pass
    return None
