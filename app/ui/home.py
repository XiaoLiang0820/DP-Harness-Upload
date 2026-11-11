"""FrameBoost 极帧加速 — 首页（信息看板 + 交互控制）."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QComboBox,
)

from ..core import booster, cleaner, gpu, hardware
from ..i18n import Translator
from ..theme import ACCENT, ACCENT_2, GOOD
from ..widgets import Card, RingChart, StatCard, TaskThread, ToggleSwitch
from . import Page, show_info

_GUID_HIGH = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
_GUID_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"
_GUID_SAVER = "a1841308-3541-4fab-bc81-f71556f20b4a"


class HomePage(Page):
    def __init__(self, translator: Translator, main_window, parent: QWidget | None = None) -> None:
        super().__init__(translator, parent)
        self.main_window = main_window
        self._stats_busy = False
        self._syncing = False
        self._last_power_guid = ""
        self._admin_notified = False
        self._build()
        self.retranslate()

        self._load_hardware()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh_stats_async)
        self._timer.start()
        self._refresh_stats_async()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 34, 40, 30)
        root.setSpacing(24)

        self.title = QLabel()
        self.title.setObjectName("bigTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        self.device_lbl = QLabel()
        self.device_lbl.setObjectName("muted")
        self.device_lbl.setWordWrap(True)
        root.addWidget(self.device_lbl)

        # 三个环形图卡片：内存 / CPU / 显存
        charts = QHBoxLayout()
        charts.setSpacing(14)
        self.mem_card, self.mem_title, self.mem_ring, self.mem_detail = self._chart_card(ACCENT)
        self.cpu_card, self.cpu_title, self.cpu_ring, self.cpu_detail = self._chart_card(ACCENT_2)
        self.gpu_card, self.gpu_title, self.gpu_ring, self.gpu_detail = self._chart_card(GOOD)
        charts.addWidget(self.mem_card)
        charts.addWidget(self.cpu_card)
        charts.addWidget(self.gpu_card)
        root.addLayout(charts, 1)

        # 信息卡片：进程 / 电源计划（下拉）/ 游戏模式（开关）/ GPU 加速（开关）
        grid = QGridLayout()
        grid.setSpacing(14)
        self.stat_processes = StatCard("")
        self.power_card, self.power_combo, self.power_label = self._combo_card()
        self.gm_card, self.gm_toggle, self.gm_state, self.gm_label = self._toggle_card()
        self.hags_card, self.hags_toggle, self.hags_state, self.hags_label = self._toggle_card()
        for col, card in enumerate([self.stat_processes, self.power_card,
                                    self.gm_card, self.hags_card]):
            grid.addWidget(card, 0, col)
        root.addLayout(grid)

        # 连接开关（_on_stats 同步时用 blockSignals 避免误触发）
        self.gm_toggle.toggled.connect(self._on_gamemode_toggled)
        self.hags_toggle.toggled.connect(self._on_hags_toggled)

        # 硬件信息（一行四列）
        hw = Card()
        hw_lay = QHBoxLayout(hw)
        hw_lay.setContentsMargins(18, 12, 18, 12)
        hw_lay.setSpacing(24)
        self.hw_cpu = self._hw_block(hw_lay)
        self.hw_gpu = self._hw_block(hw_lay)
        self.hw_ram = self._hw_block(hw_lay)
        self.hw_disk = self._hw_block(hw_lay)
        self.hw_temp = self._hw_block(hw_lay)
        root.addWidget(hw)

        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        self._populate_power_combo()

    def _chart_card(self, color: str):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        title = QLabel()
        title.setObjectName("statLabel")
        title.setAlignment(Qt.AlignCenter)
        ring = RingChart(color=color, size=132)
        detail = QLabel()
        detail.setObjectName("muted")
        detail.setAlignment(Qt.AlignCenter)
        detail.setWordWrap(True)
        lay.addWidget(title, 0, Qt.AlignHCenter)
        lay.addWidget(ring, 1)
        lay.addWidget(detail, 0, Qt.AlignHCenter)
        return card, title, ring, detail

    def _hw_block(self, parent_lay):
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel()
        title.setObjectName("statLabel")
        value = QLabel("--")
        value.setStyleSheet("font-size: 12px; color: #E8EEF5;")
        col.addWidget(title)
        col.addWidget(value)
        parent_lay.addLayout(col, 1)
        return title, value

    def _load_hardware(self) -> None:
        def work():
            from ..core import device
            dev = device.detect_device()
            return {
                "hw": hardware.get_hardware(),
                "dev": dev,
                "temp": gpu.get_temperature(),
                "refresh": gpu.get_refresh_rate(),
            }
        th = TaskThread(work, self)
        th.result.connect(self._on_hardware)
        th.start()

    def _on_hardware(self, data) -> None:
        if not data:
            return
        hw = data.get("hw") or {}
        dev = data.get("dev") or {}
        self._device = dev

        def short(s, n=26):
            s = (s or "--").strip()
            return s if len(s) <= n else s[:n - 1] + "…"

        cpu = hw.get("cpu") or ""
        gpu_name = hw.get("gpu") or ""
        self.hw_cpu[1].setText(short(cpu))
        self.hw_cpu[1].setToolTip(cpu)
        self.hw_gpu[1].setText(short(gpu_name))
        self.hw_gpu[1].setToolTip(gpu_name)
        self.hw_ram[1].setText(cleaner.format_bytes(hw.get("ram_total", 0)))
        disks = hw.get("disks") or []
        if disks:
            d = disks[0]
            self.hw_disk[1].setText(f"{d['mount']} {cleaner.format_bytes(d['free'])}")
        else:
            self.hw_disk[1].setText("--")
        t = data.get("temp")
        self.hw_temp[1].setText(f"{t:.0f} ℃" if t is not None else "--")
        self._render_device()

    def _render_device(self) -> None:
        dev = getattr(self, "_device", None)
        if not dev:
            self.device_lbl.setText("")
            return
        kind_label = self.tr("device_kind_" + str(dev.get("kind", "desktop")))
        parts = [kind_label]
        oem = dev.get("oem") or ""
        model = dev.get("model") or ""
        if oem and oem != "Unknown":
            parts.append(f"{oem} {model}".strip())
        if dev.get("gpu_vendor") and dev["gpu_vendor"] != "Unknown":
            parts.append(dev["gpu_vendor"])
        bat = dev.get("battery") or {}
        if bat.get("present"):
            if bat.get("plugged"):
                parts.append(self.tr("device_ac"))
            else:
                parts.append(self.tr("device_battery") + f" {bat.get('percent')}%")
        self.device_lbl.setText(" · ".join(parts))

    def _combo_card(self):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        combo = QComboBox()
        combo.setCursor(Qt.PointingHandCursor)
        combo.currentIndexChanged.connect(self._on_power_changed)
        lay.addWidget(combo)
        lbl = QLabel()
        lbl.setObjectName("statLabel")
        lay.addWidget(lbl)
        return card, combo, lbl

    def _toggle_card(self):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(10)
        sw = ToggleSwitch(False)
        state = QLabel()
        state.setObjectName("statValue")
        row.addWidget(sw)
        row.addWidget(state)
        row.addStretch(1)
        lay.addLayout(row)
        lbl = QLabel()
        lbl.setObjectName("statLabel")
        lay.addWidget(lbl)
        return card, sw, state, lbl

    def _populate_power_combo(self) -> None:
        plans = booster.list_power_plans()
        if not plans:
            plans = [(_GUID_HIGH, self.tr("state_high_perf")),
                     (_GUID_BALANCED, self.tr("state_balanced")),
                     (_GUID_SAVER, self.tr("state_power_saver"))]
        pref = [_GUID_HIGH[:8], _GUID_BALANCED[:8], _GUID_SAVER[:8]]

        def rank(p):
            g = p[0].lower()
            for i, gg in enumerate(pref):
                if g.startswith(gg):
                    return i
            return len(pref)

        plans = sorted(plans, key=rank)
        self.power_combo.blockSignals(True)
        for guid, name in plans:
            self.power_combo.addItem(name or guid, guid)
        self.power_combo.blockSignals(False)

    # ------------------------------------------------------------------ #
    def _refresh_stats_async(self) -> None:
        if self._stats_busy:
            return
        self._stats_busy = True

        def work():
            return booster.get_system_stats(), gpu.get_gpu_stats()

        th = TaskThread(work, self)
        th.result.connect(self._on_stats)
        th.error.connect(lambda _e: self._on_stats(None))
        th.finished.connect(lambda: setattr(self, "_stats_busy", False))
        th.start()

    def _on_stats(self, data) -> None:
        if data is None:
            return
        stats, gpu_stats = data

        self.mem_ring.setValue(stats.memory_percent)
        self.mem_detail.setText(
            f"{cleaner.format_bytes(stats.memory_used)} / {cleaner.format_bytes(stats.memory_total)}")

        self.cpu_ring.setValue(stats.cpu_percent)
        self.cpu_detail.setText(f"{stats.logical_cpus} " + self.tr("stat_cpu_threads"))

        if gpu_stats:
            name, used, total = gpu_stats
            pct = (used / total * 100.0) if total else 0.0
            self.gpu_ring.setValue(pct)
            short = name.replace("NVIDIA GeForce ", "").replace("AMD Radeon ", "")
            self.gpu_detail.setText(
                f"{short} · {cleaner.format_bytes(used)} / {cleaner.format_bytes(total)}")
        else:
            self.gpu_ring.setValue(0)
            self.gpu_detail.setText(self.tr("stat_gpu_unknown"))

        self.stat_processes.value_label.setText(str(stats.process_count))

        self._syncing = True
        try:
            idx = self.power_combo.findData(stats.power_plan_guid)
            if idx >= 0:
                self.power_combo.blockSignals(True)
                self.power_combo.setCurrentIndex(idx)
                self.power_combo.blockSignals(False)
            self._last_power_guid = stats.power_plan_guid

            self._set_toggle(self.gm_toggle, stats.game_mode)
            self.gm_state.setText(self.tr("state_on") if stats.game_mode else self.tr("state_off"))
            self._set_toggle(self.hags_toggle, stats.hags)
            self.hags_state.setText(self.tr("state_on") if stats.hags else self.tr("state_off"))
        finally:
            self._syncing = False

    def _set_toggle(self, sw: ToggleSwitch, value: bool) -> None:
        sw.blockSignals(True)
        sw.setChecked(value)
        sw.blockSignals(False)

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
    def _on_power_changed(self, _index: int) -> None:
        if self._syncing:
            return
        guid = self.power_combo.currentData()
        if not guid:
            return
        if booster.set_power_plan(guid):
            self._last_power_guid = guid
            self.power_combo.setToolTip("")
            self._refresh_stats_async()
        else:
            self._revert_power()
            self._need_admin(self.power_combo)

    def _revert_power(self) -> None:
        idx = self.power_combo.findData(self._last_power_guid)
        if idx >= 0:
            self.power_combo.blockSignals(True)
            self.power_combo.setCurrentIndex(idx)
            self.power_combo.blockSignals(False)

    def _on_gamemode_toggled(self, checked: bool) -> None:
        if self._syncing:
            return
        if booster.set_game_mode(checked):
            self.gm_state.setText(self.tr("state_on") if checked else self.tr("state_off"))
            self.gm_toggle.setToolTip("")
            self._refresh_stats_async()
        else:
            self._set_toggle(self.gm_toggle, not checked)
            self._need_admin(self.gm_toggle)

    def _on_hags_toggled(self, checked: bool) -> None:
        if self._syncing:
            return
        if booster.set_hags(checked):
            self.hags_state.setText(self.tr("state_on") if checked else self.tr("state_off"))
            self.hags_toggle.setToolTip("")
            self._refresh_stats_async()
        else:
            self._set_toggle(self.hags_toggle, not checked)
            self._need_admin(self.hags_toggle)

    def _need_admin(self, control) -> None:
        control.setToolTip(self.tr("settings_admin"))
        if not self._admin_notified and not self.main_window.is_admin:
            self._admin_notified = True
            show_info(self, self.tr("common_info"),
                      self.tr("admin_needed_msg"), self.tr)

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.title.setText(self.tr("home_title"))
        self.subtitle.setText(self.tr("home_subtitle"))
        self.mem_title.setText(self.tr("stat_memory"))
        self.cpu_title.setText(self.tr("stat_cpu"))
        self.gpu_title.setText(self.tr("stat_gpu"))
        self.stat_processes.label_label.setText(self.tr("stat_processes"))
        self.power_label.setText(self.tr("stat_power"))
        self.gm_label.setText(self.tr("stat_gamemode"))
        self.hags_label.setText(self.tr("stat_hags"))
        self.hw_cpu[0].setText(self.tr("hw_cpu"))
        self.hw_gpu[0].setText(self.tr("hw_gpu"))
        self.hw_ram[0].setText(self.tr("hw_ram"))
        self.hw_disk[0].setText(self.tr("hw_disk"))
        self.hw_temp[0].setText(self.tr("hw_temp"))
        self._render_device()
        self.gm_state.setText(self.tr("state_on") if self.gm_toggle.isChecked() else self.tr("state_off"))
        self.hags_state.setText(self.tr("state_on") if self.hags_toggle.isChecked() else self.tr("state_off"))
        self._populate_power_combo()
        self.hint.setText(
            self.tr("settings_admin_hint") if not self.main_window.is_admin else "")
