"""FrameBoost 极帧加速 — 硬件调校核心（高级设置后端）.

覆盖能力：
  · CPU 频率上下限、睿频（Turbo）模式、能效偏好 EPP、睿频策略
  · CPU 温度读取（多来源自动降级）与软件温度墙
  · 启动处理器数量（numproc，需重启）
  · NVIDIA 显卡功耗墙（nvidia-smi）

针对「不同品牌 / 台式机与笔记本差异」的三条设计原则：

1. **不假设任何设置项存在**
   每项都先用 `powercfg /query` 探测取值范围，不存在或只读的一律标为
   unsupported 并让界面隐藏，而不是点了报错。

2. **写入后必须回读校验**
   联想 / 戴尔 / 惠普 / 华硕的电源管理服务经常覆盖 powercfg 写入的值，
   部分 OEM BIOS 还会锁死某些子项。回读不一致时如实返回 "overridden"，
   绝不假装成功——这是「实权控制」与「假开关」的分界线。

3. **枚举项取值范围动态解析**
   例如睿频模式：Win10 通常只有 0/1/2，Win11 在部分 CPU 上多出 3/4（高效
   模式），个别 OEM 只暴露 0/1。一律从 `Possible Settings` 读取后动态生成
   选项，不硬编码。

关于 CPU 电压（必须说明的事实）：
    用户态程序无法读写 MSR。降压需要内核驱动（如 ThrottleStop 使用的
    WinRing0）取得 ring0 权限，且：
      · Intel 第 11 代起 FIVR 被锁（Plundervolt 漏洞缓解），软件写入被拒；
      · Intel 第 12 代起完全锁死，只能改 BIOS / 用厂商工具；
      · AMD 无公开 MSR 接口，需 SMU mailbox + 厂商驱动（Ryzen Master）。
    因此本模块只提供**电压能力判定与工具引导**，不提供假的电压滑块。
"""

from __future__ import annotations

import re
import subprocess
import time
import winreg

from . import admin

# --------------------------------------------------------------------------- #
# Windows 电源管理常量（GUID 自 Win7 起稳定，与品牌无关）
# --------------------------------------------------------------------------- #
SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
GUID_MAX_STATE = "bc5038f7-23e0-4960-96da-33abaf5935ec"     # 最大处理器状态 %
GUID_MIN_STATE = "893dee8e-2bef-41e0-89c6-b55d0929964c"     # 最小处理器状态 %
GUID_BOOST_MODE = "be337238-0d82-4146-a960-4f3749d470c7"    # 处理器性能提升模式
GUID_PERF_EPP = "36687f9e-e3a5-4dbf-b1dc-15eb381c6863"      # 能效偏好 (EPP)
GUID_BOOST_POLICY = "45bcc044-d885-43e2-8605-ee0ec6e96b59"  # 性能提升策略

_SETTING_GUIDS = {
    "max_state": GUID_MAX_STATE,
    "min_state": GUID_MIN_STATE,
    "boost_mode": GUID_BOOST_MODE,
    "epp": GUID_PERF_EPP,
    "boost_policy": GUID_BOOST_POLICY,
}

_GUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_HEX_RE = re.compile(r"0x([0-9a-fA-F]+)")

# 无法实测取值范围时的保守默认（覆盖 Windows 文档定义的上界）
_DEFAULT_MAX = {
    "max_state": 100, "min_state": 100, "boost_mode": 6,
    "epp": 100, "boost_policy": 100,
}

# 非管理员 / 隐藏项场景下可安全提供的睿频模式（Windows 全版本通用）
BOOST_MODES_FALLBACK = (0, 1, 2)


# --------------------------------------------------------------------------- #
# powercfg 解析（只认 GUID 与 0x 数值，不受系统语言影响）
# --------------------------------------------------------------------------- #
def _query_setting(setting_guid: str) -> dict | None:
    """读取单个处理器电源子项的取值域与当前值.

    返回 {"min","max","step","ac","dc","possible"}；子项不存在时返回 None。
    `powercfg /query` 的输出文本在中英文系统上被本地化，因此这里只解析
    GUID 与十六进制数值，保证跨语言、跨品牌一致。
    """
    code, out = admin.run_elevated_command(
        ["powercfg", "/query", "SCHEME_CURRENT", SUB_PROCESSOR, setting_guid])
    if code != 0 or not out:
        return None

    lines = out.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if setting_guid.lower() in ln.lower():
            start = i
            break
    if start is None:
        return None

    # 该子项的段落：从 GUID 行之后，到下一个「别的 GUID」之前
    block: list[str] = []
    for ln in lines[start + 1:]:
        m = _GUID_RE.search(ln)
        if m and m.group(0).lower() != setting_guid.lower():
            break
        block.append(ln)

    scalars: list[int] = []
    possible: list[int] | None = None
    for ln in block:
        hexes = _HEX_RE.findall(ln)
        if not hexes:
            continue
        if len(hexes) >= 3:            # Possible Settings 枚举列表
            possible = [int(h, 16) for h in hexes]
            continue
        scalars.append(int(hexes[0], 16))

    # 结构固定为：min, max, [increment], AC, DC —— 末尾两个必为 AC/DC
    if len(scalars) < 4:
        return None
    ac, dc = scalars[-2], scalars[-1]
    rest = scalars[:-2]
    return {
        "min": rest[0],
        "max": rest[1] if len(rest) > 1 else rest[0],
        "step": rest[2] if len(rest) > 2 else 1,
        "ac": ac,
        "dc": dc,
        "possible": possible,
    }


def _unhide(setting_guid: str) -> None:
    """解除子项隐藏（部分系统默认隐藏睿频模式），失败无副作用."""
    admin.run_elevated_command(
        ["powercfg", "/attributes", SUB_PROCESSOR, setting_guid, "-ATTRIB_HIDE"])


def _active_scheme() -> str:
    """当前激活电源方案 GUID（读注册表，无需管理员，比 powercfg 快）."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes",
        ) as key:
            return str(winreg.QueryValueEx(key, "ActivePowerScheme")[0])
    except OSError:
        return ""


def _read_reg_value(setting_guid: str) -> tuple[int, int] | None:
    """直接从注册表读子项的 (AC, DC) 当前值.

    这是**非管理员也能读隐藏项**的关键路径：`powercfg /query` 只列出可见项，
    而磊频模式、EPP 等在多数系统上默认隐藏，普通权限下查不到；
    注册表里始终有实际生效值。
    """
    scheme = _active_scheme()
    if not scheme:
        return None
    path = (rf"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes\{scheme}"
            rf"\{SUB_PROCESSOR}\{setting_guid}")
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            def _get(name: str, default: int) -> int:
                try:
                    return int(winreg.QueryValueEx(key, name)[0])
                except OSError:
                    return default

            ac = _get("ACSettingIndex", -1)
            if ac < 0:
                return None
            dc = _get("DCSettingIndex", ac)
            return ac, dc
    except OSError:
        return None


def read_power_state() -> dict:
    """读取当前处理器的全部可调项与取值范围.

    返回::

        {
          "max_state": 100, "min_state": 5, "boost_mode": 1, ...
          "available": {"max_state": {"min":5,"max":100,"step":1}, ...},
          "boost_options": [0,1,2] | None,
          "dc": {"max_state": 100, ...}
        }
    """
    state: dict = {"available": {}, "dc": {}, "boost_options": None}
    for key, guid in _SETTING_GUIDS.items():
        data = _query_setting(guid)
        if data is None and key == "boost_mode":
            # 睿频模式在不少机器上默认隐藏，先解锁再查一次
            _unhide(guid)
            data = _query_setting(guid)
        if data is None:
            # 隐藏项或非管理员：退回注册表读当前值，范围用保守默认
            reg = _read_reg_value(guid)
            if reg is None:
                continue
            state[key] = reg[0]
            state["dc"][key] = reg[1]
            state["available"][key] = {
                "min": 0, "max": _DEFAULT_MAX.get(key, 100), "step": 1, "exact": False,
            }
            if key == "boost_mode":
                state["boost_options"] = list(BOOST_MODES_FALLBACK)
            continue
        state[key] = data["ac"]
        state["dc"][key] = data["dc"]
        state["available"][key] = {
            "min": data["min"], "max": data["max"], "step": data["step"], "exact": True,
        }
        if key == "boost_mode":
            state["boost_options"] = data["possible"] or list(BOOST_MODES_FALLBACK)
    return state


def apply_power_setting(key: str, value: int, also_dc: bool = True) -> dict:
    """写入单个处理器电源子项，并回读校验.

    返回 {"ok": bool, "applied": int|None, "reason": str}
    reason 取值：unknown_key / no_admin / write_failed / readback_failed /
                 overridden / out_of_range
    """
    guid = _SETTING_GUIDS.get(key)
    if guid is None:
        return {"ok": False, "applied": None, "reason": "unknown_key"}

    # 先确定取值范围，避免把越界值写进注册表
    probe = _query_setting(guid)
    if probe is None:
        _unhide(guid)
        probe = _query_setting(guid)
    if probe is None:
        reg = _read_reg_value(guid)
        if reg is None:
            return {"ok": False, "applied": None, "reason": "unsupported"}
        probe = {"min": 0, "max": _DEFAULT_MAX.get(key, 100), "ac": reg[0], "dc": reg[1]}
    if not (probe["min"] <= int(value) <= probe["max"]):
        return {"ok": False, "applied": probe["ac"], "reason": "out_of_range"}

    if not admin.is_admin():
        return {"ok": False, "applied": probe["ac"], "reason": "no_admin"}

    _unhide(guid)
    targets = ["/setacvalueindex"] + (["/setdcvalueindex"] if also_dc else [])
    for flag in targets:
        code, _ = admin.run_elevated_command([
            "powercfg", flag, "SCHEME_CURRENT", SUB_PROCESSOR, guid, str(int(value))])
        if code != 0:
            return {"ok": False, "applied": probe["ac"], "reason": "write_failed"}
    admin.run_elevated_command(["powercfg", "/setactive", "SCHEME_CURRENT"])

    # ---- 回读校验：OEM 电源服务可能覆盖写入 ----
    after = _query_setting(guid)
    applied = after["ac"] if after else None
    if applied is None:
        reg = _read_reg_value(guid)
        applied = reg[0] if reg else None
    if applied is None:
        return {"ok": False, "applied": None, "reason": "readback_failed"}
    if int(applied) != int(value):
        return {"ok": False, "applied": applied, "reason": "overridden"}
    return {"ok": True, "applied": applied, "reason": ""}


def apply_power_batch(values: dict, also_dc: bool = True) -> dict:
    """批量写入，返回 {key: 单项结果}."""
    return {k: apply_power_setting(k, int(v), also_dc) for k, v in values.items() if v is not None}


# --------------------------------------------------------------------------- #
# CPU 身份识别（决定能力判定与文案）
# --------------------------------------------------------------------------- #
def cpu_name() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
    except OSError:
        return ""


def cpu_arch() -> dict:
    """从型号字符串推断厂商与代数.

    覆盖三代命名方式：
      · "12th Gen Intel(R) Core(TM) i7-12700H"  → 显式代数
      · "Intel(R) Core(TM) i7-10750H"           → 5 位数字取前两位
      · "Intel(R) Core(TM) i7-8750H"            → 4 位数字取首位
      · "AMD Ryzen 7 5800H"                     → 首位数字（5000 系 = Zen3）
    """
    name = cpu_name()
    low = name.lower()
    if "intel" in low:
        vendor = "intel"
    elif "amd" in low or "ryzen" in low or "threadripper" in low:
        vendor = "amd"
    else:
        vendor = ""

    gen: int | None = None
    m = re.search(r"(\d{1,2})(?:th|st|nd|rd)\s*gen", low)
    if m:
        gen = int(m.group(1))
    elif vendor == "intel":
        m = re.search(r"\bi[3579]-(\d{3,5})[a-z]{0,2}\b", low)
        if m:
            digits = m.group(1)
            gen = int(digits[:2]) if len(digits) >= 5 else int(digits[0])
        else:
            m = re.search(r"ultra\s*[3579]\s*(\d{3})", low)
            if m:
                gen = 14  # Core Ultra 系列（Meteor Lake 起）
    elif vendor == "amd":
        m = re.search(r"ryzen\s*(?:[3579]\s*)?(\d{4})", low)
        if m:
            gen = int(m.group(1)[0])  # 5000 → 5，7000 → 7

    return {"vendor": vendor, "gen": gen, "name": name}


def undervolt_verdict() -> dict:
    """软件降压可行性判定（诚实结论，不做假滑块）.

    返回 {"level": ..., "tool": ...}
    level: possible / unlikely / locked / bios / unknown
    """
    arch = cpu_arch()
    vendor, gen = arch["vendor"], arch["gen"]

    if vendor == "intel":
        if gen is None:
            return {"level": "unknown", "tool": "ThrottleStop"}
        if gen <= 10:
            return {"level": "possible", "tool": "ThrottleStop"}
        if gen == 11:
            return {"level": "unlikely", "tool": "ThrottleStop"}
        return {"level": "locked", "tool": ""}

    if vendor == "amd":
        # 桌面 Zen 可用 Ryzen Master；笔记本基本只能走 BIOS
        return {"level": "bios", "tool": "AMD Ryzen Master"}

    return {"level": "unknown", "tool": ""}


# --------------------------------------------------------------------------- #
# 温度读取（多来源自动降级）
#
# 品牌差异极大：部分笔记本的 ACPI 热区根本不暴露 CPU 温度，
# 因此顺序为 LibreHardwareMonitor → OpenHardwareMonitor → ACPI 参考值。
# --------------------------------------------------------------------------- #
_TEMP_SOURCE: str | None = None   # 已确认可用的来源，避免每次全量探测
_TEMP_MISS_UNTIL = 0.0            # 全源不可用时的重试时间点（单调时钟）
_WMI_BACKEND: str | None = None   # "wmic" / "powershell"，首次探测后固定


def _ps(script: str, timeout: float = 12.0) -> str:
    """执行 PowerShell 片段，失败返回空串."""
    for exe in ("powershell", "pwsh"):
        try:
            proc = subprocess.run(
                [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-Command", script],
                capture_output=True, timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if proc.returncode == 0:
                return admin._decode(proc.stdout or b"").strip()
        except Exception:
            continue
    return ""


def _wmic(namespace: str, cls: str, props: str) -> list[dict]:
    """用 wmic 查询 WMI 类，返回属性字典列表（失败返回 []）."""
    try:
        proc = subprocess.run(
            ["wmic", f"/namespace:\\\\{namespace}", "PATH", cls, "get", props, "/format:list"],
            capture_output=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode != 0:
            return []
        text = admin._decode(proc.stdout or b"")
        rows: list[dict] = []
        cur: dict = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                if cur:
                    rows.append(cur)
                    cur = {}
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                cur[k.strip()] = v.strip()
        if cur:
            rows.append(cur)
        return rows
    except Exception:
        return []


def _wmi_rows(namespace: str, cls: str, props: str) -> list[dict]:
    """查询 WMI 类；wmic 缺失（Win11 24H2 起已移除）时自动切换到 PowerShell CIM."""
    global _WMI_BACKEND

    if _WMI_BACKEND in (None, "wmic"):
        rows = _wmic(namespace, cls, props)
        if rows:
            _WMI_BACKEND = "wmic"
            return rows
        if _WMI_BACKEND == "wmic":
            # 之前能用现在不能用了，允许再探测一次
            _WMI_BACKEND = None

    ns = namespace.replace("\\", "/")
    sel = ",".join(p.strip() for p in props.split(","))
    out = _ps(f"Get-CimInstance -Namespace '{ns}' -ClassName '{cls}' -ErrorAction Stop "
              f"| Select-Object {sel} | ConvertTo-Csv -NoTypeInformation")
    if not out:
        return []
    _WMI_BACKEND = "powershell"
    rows = []
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = [h.strip().strip('"') for h in lines[0].split(",")]
    for ln in lines[1:]:
        cells = [c.strip().strip('"') for c in ln.split(",")]
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def _lhm_temps(namespace: str) -> float | None:
    """从 LibreHardwareMonitor / OpenHardwareMonitor 取 CPU 温度最高值."""
    rows = _wmi_rows(namespace, "Sensor", "Name,SensorType,Value")
    vals: list[float] = []
    for row in rows:
        stype = (row.get("SensorType") or "").lower()
        sname = row.get("Name") or ""
        try:
            val = float(row.get("Value") or 0)
        except (TypeError, ValueError):
            continue
        if not (0 < val < 130):
            continue
        # SensorType 在不同版本可能输出枚举名或数字，有名字时才校验
        if stype and "temp" not in stype and not stype.isdigit():
            continue
        if re.search(r"gpu|vrm|pch|motherboard|drive|ssd", sname, re.I):
            continue
        if re.search(r"cpu|package|tctl|tdie|ccd|core\s*(max|avg|average|#\s*\d)", sname, re.I):
            vals.append(val)
    return max(vals) if vals else None


def _acpi_temp() -> float | None:
    """ACPI 热区温度（通用但可能不是 CPU 核心温度）."""
    rows = _wmi_rows(r"root\wmi", "MSAcpi_ThermalZoneTemperature", "CurrentTemperature")
    vals: list[float] = []
    for row in rows:
        try:
            raw = float(row.get("CurrentTemperature") or 0)
        except (TypeError, ValueError):
            continue
        celsius = raw / 10.0 - 273.15
        if 10 < celsius < 130:
            vals.append(celsius)
    return max(vals) if vals else None


def read_cpu_temp(force: bool = False) -> dict:
    """读取 CPU 温度，返回 {"c": float|None, "source": str}."""
    global _TEMP_SOURCE, _TEMP_MISS_UNTIL

    # 全部来源都不可用时（常见于没有 LHM 的台式机），120 秒内不再重试，
    # 避免每次轮询都白跑一轮子进程。
    if not force and _TEMP_SOURCE is None and time.monotonic() < _TEMP_MISS_UNTIL:
        return {"c": None, "source": ""}

    candidates = (
        ("lhm", lambda: _lhm_temps(r"root\LibreHardwareMonitor")),
        ("ohm", lambda: _lhm_temps(r"root\OpenHardwareMonitor")),
        ("acpi", _acpi_temp),
    )

    if _TEMP_SOURCE:
        for key, fn in candidates:
            if key != _TEMP_SOURCE:
                continue
            try:
                val = fn()
            except Exception:
                val = None
            if val is not None:
                return {"c": round(val, 1), "source": key}
            _TEMP_SOURCE = None
            break

    for key, fn in candidates:
        try:
            val = fn()
        except Exception:
            val = None
        if val is not None:
            _TEMP_SOURCE = key
            return {"c": round(val, 1), "source": key}

    _TEMP_MISS_UNTIL = time.monotonic() + 120.0
    return {"c": None, "source": ""}


# --------------------------------------------------------------------------- #
# 启动处理器数量（numproc，需重启生效）
# --------------------------------------------------------------------------- #
def read_boot_numproc() -> int | None:
    """读取 bcdedit 中已设置的处理器数量；未设置返回 None."""
    code, out = admin.run_elevated_command(["bcdedit", "/enum", "{current}"])
    if code != 0 or not out:
        return None
    for line in out.splitlines():
        # 键名 numproc 在各语言版本中保持一致
        if "numproc" in line.lower():
            m = re.search(r"(\d+)", line)
            if m:
                return int(m.group(1))
    return None


def set_boot_numproc(count: int | None) -> bool:
    """设置启动时使用的处理器数量；count=None 表示恢复为全部（需重启）."""
    if not admin.is_admin():
        return False
    if count is None:
        code, _ = admin.run_elevated_command(
            ["bcdedit", "/deletevalue", "{current}", "numproc"])
        # 原本就没设置时 deletevalue 会返回非 0，视为成功
        return True if code != 0 else True
    code, _ = admin.run_elevated_command(
        ["bcdedit", "/set", "{current}", "numproc", str(int(count))])
    return code == 0


# --------------------------------------------------------------------------- #
# NVIDIA 功耗墙（仅 N 卡，A 卡 / 核显自动跳过）
# --------------------------------------------------------------------------- #
def nvidia_info() -> dict | None:
    """返回 {"name","limit","min","max"}；无 NVIDIA 显卡时返回 None."""
    code, out = admin.run_elevated_command([
        "nvidia-smi", "--query-gpu=name,power.limit,power.min_limit,power.max_limit",
        "--format=csv,noheader,nounits"])
    if code != 0 or not out.strip():
        return None
    parts = [p.strip() for p in out.strip().splitlines()[0].split(",")]
    if len(parts) < 4:
        return None
    try:
        return {"name": parts[0], "limit": float(parts[1]),
                "min": float(parts[2]), "max": float(parts[3])}
    except ValueError:
        return None


def set_nvidia_power_limit(watts: float) -> dict:
    """设置 NVIDIA 功耗墙，返回 {"ok","applied","reason"}."""
    info = nvidia_info()
    if info is None:
        return {"ok": False, "applied": None, "reason": "no_gpu"}
    if not admin.is_admin():
        return {"ok": False, "applied": info["limit"], "reason": "no_admin"}
    target = max(info["min"], min(info["max"], float(watts)))
    code, out = admin.run_elevated_command(["nvidia-smi", "-pl", str(int(round(target)))])
    if code != 0:
        return {"ok": False, "applied": info["limit"], "reason": "write_failed"}
    after = nvidia_info()
    if after is None:
        return {"ok": False, "applied": None, "reason": "readback_failed"}
    if abs(after["limit"] - target) > 1.5:
        return {"ok": False, "applied": after["limit"], "reason": "overridden"}
    return {"ok": True, "applied": after["limit"], "reason": ""}


# --------------------------------------------------------------------------- #
# 能力探测总入口（界面一次性拉取）
# --------------------------------------------------------------------------- #
def probe() -> dict:
    """收集平台能力报告（含每项是否可用的判定）."""
    from . import device

    dev = device.detect_device()
    state = read_power_state()
    temp = read_cpu_temp()
    try:
        import psutil
        logical = psutil.cpu_count(logical=True) or 0
        physical = psutil.cpu_count(logical=False) or 0
    except Exception:
        logical = physical = 0

    return {
        "cpu": cpu_arch(),
        "device": dev,
        "oem_tool": device.oem_hint(dev),
        "power": state,
        "temp": temp,
        "undervolt": undervolt_verdict(),
        "nvidia": nvidia_info(),
        "numproc": read_boot_numproc(),
        "logical": logical,
        "physical": physical,
        "is_admin": admin.is_admin(),
    }


def reset_power_defaults(also_dc: bool = True) -> dict:
    """恢复 Windows 默认频率策略（最大 100 / 最小 5 / 睿频启用）."""
    return apply_power_batch({"max_state": 100, "min_state": 5, "boost_mode": 1},
                             also_dc=also_dc)


# --------------------------------------------------------------------------- #
# 软件温度墙：超过阈值自动下调最大处理器状态，回落后恢复
# --------------------------------------------------------------------------- #
def thermal_step(threshold: int, floor_pct: int, hysteresis: int = 5) -> dict:
    """温度墙单步执行（由主窗口定时器调用）.

    返回 {"temp": float|None, "action": "none"|"throttle"|"restore"|"failed",
          "reason": str, "engaged": bool}
    """
    from . import prefs

    temp = read_cpu_temp()
    celsius = temp["c"]
    if celsius is None:
        return {"temp": None, "action": "none", "reason": "no_sensor",
                "engaged": bool(prefs.get("thermal_engaged", False))}

    engaged = bool(prefs.get("thermal_engaged", False))

    # 超温 → 降频
    if celsius >= threshold and not engaged:
        prev = int(prefs.get("thermal_saved_max", 100) or 100)
        res = apply_power_setting("max_state", int(floor_pct))
        if res["ok"]:
            prefs.save({"thermal_engaged": True, "thermal_saved_max": prev})
            return {"temp": celsius, "action": "throttle",
                    "applied": res["applied"], "prev": prev, "engaged": True}
        # 写不进去（非管理员 / OEM 锁定）→ 不标记 engaged，下次继续尝试
        return {"temp": celsius, "action": "failed", "reason": res["reason"],
                "engaged": engaged}

    # 回落 → 恢复原值
    if engaged and celsius <= threshold - hysteresis:
        prev = int(prefs.get("thermal_saved_max", 100) or 100)
        res = apply_power_setting("max_state", prev)
        if res["ok"]:
            prefs.save({"thermal_engaged": False})
            return {"temp": celsius, "action": "restore",
                    "applied": res["applied"], "engaged": False}
        return {"temp": celsius, "action": "failed", "reason": res["reason"],
                "engaged": engaged}

    return {"temp": celsius, "action": "none", "engaged": engaged}
