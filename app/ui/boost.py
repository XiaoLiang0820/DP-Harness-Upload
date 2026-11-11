"""FrameBoost 极帧加速 — 游戏加速页（含进阶优化与游戏自动加速）."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QScrollArea,
    QDialog, QTextEdit, QComboBox,
)

from ..core import booster, device, game_library, gpu, memopt, network
from ..core.games import GAMES, is_exe_running
from ..i18n import Translator
from ..widgets import Card, TaskThread, ToggleSwitch
from . import Page

_OPTION_KEYS = {
    "powerplan": "boost_powerplan", "memory": "boost_memory",
    "killproc": "boost_killproc", "gamemode": "boost_gamemode",
    "priority": "boost_priority", "hags": "boost_hags",
    "network": "boost_network", "timer": "boost_timer",
    "powertweaks": "boost_powertweaks", "dvr": "boost_dvr",
    "autoboost": "boost_autoboost",
}


class BoostPage(Page):
    def __init__(self, translator: Translator, main_window, parent: QWidget | None = None) -> None:
        super().__init__(translator, parent)
        self.main_window = main_window
        self._toggles: dict[str, ToggleSwitch] = {}
        self._auto_was_running = False
        self._build()
        self.retranslate()

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(5000)
        self._auto_timer.timeout.connect(self._auto_check)
        self._guard_timer = QTimer(self)
        self._guard_timer.setInterval(10000)
        self._guard_timer.timeout.connect(self._guard_tick)
        self._guard_busy = False
        self._load_smart()

    # ------------------------------------------------------------------ #
    # 智能加速（按设备类型推荐档位）
    # ------------------------------------------------------------------ #
    def _load_smart(self) -> None:
        def work():
            dev = device.detect_device()
            return {
                "dev": dev,
                "tier": device.suggest_tier(dev),
                "oem_app": device.oem_hint(dev),
                "mux": device.mux_hint(dev),
                "refresh": gpu.get_refresh_rate(),
            }
        th = TaskThread(work, self)
        th.result.connect(self._on_smart)
        th.start()

    def _on_smart(self, data) -> None:
        if not data:
            return
        dev = data.get("dev") or {}
        self._device = dev
        self._tier = data.get("tier") or "balanced"
        kind_label = self.tr("device_kind_" + str(dev.get("kind", "desktop")))
        tier_label = self.tr("boost_tier_" + self._tier)
        oem = dev.get("oem") or ""
        vendor = dev.get("gpu_vendor") or ""
        info = f"{kind_label}"
        if oem and oem != "Unknown":
            info += f" · {oem}"
        if vendor and vendor != "Unknown":
            info += f" · {vendor}"
        info += f"\n{self.tr('boost_smart_title')}: {tier_label}"
        bat = dev.get("battery") or {}
        if self._tier == "aggressive":
            reason_key = "boost_tier_reason_desktop"
        elif self._tier == "balanced":
            reason_key = "boost_tier_reason_gaming_laptop"
        elif bat.get("present") and not bat.get("plugged"):
            reason_key = "boost_tier_reason_battery"
        else:
            reason_key = "boost_tier_reason_thin_light"
        info += f" — {self.tr(reason_key)}"
        self.smart_info.setText(info)

        hints = []
        if data.get("mux"):
            hints.append(self.tr("hint_mux"))
        app = data.get("oem_app")
        if app and oem:
            hints.append(self.tr("hint_oem", oem=oem, app=app))
        hz = data.get("refresh")
        if hz and hz >= 120:
            hints.append(self.tr("hint_refresh", hz=hz))
        bat = dev.get("battery") or {}
        if bat.get("present") and not bat.get("plugged"):
            hints.append(self.tr("hint_battery"))
        self.smart_hint.setText("\n".join(hints))

        self._update_lowmem(dev)

    # ------------------------------------------------------------------ #
    # 低内存设备优化（仅核显笔记本）
    # ------------------------------------------------------------------ #
    def _update_lowmem(self, dev: dict) -> None:
        if not memopt.is_target_device(dev):
            self._lowmem_card.setVisible(False)
            self._guard_timer.stop()
            return
        self._lowmem_card.setVisible(True)
        self._lowmem_dev = dev
        self._lowmem_ram = int(dev.get("ram_gb") or 0)
        self.lowmem_profile.setText(self._lowmem_profile_text())
        self.lowmem_hint.setText(
            "\n".join("• " + self.tr(k) for k in memopt.low_mem_hints(dev)))
        # 小内存设备默认开启守护（≤16G）；开关变化时由 _set_guard 启停定时器
        if not self.lowmem_guard_switch.isChecked():
            self.lowmem_guard_switch.setChecked(self._lowmem_ram <= 16)

    def _lowmem_profile_text(self) -> str:
        ram = getattr(self, "_lowmem_ram", 0)
        key = "lowmem_profile_low" if 0 < ram <= 8 else "lowmem_profile"
        return self.tr(key, ram=ram)

    def _guard_threshold(self) -> float:
        try:
            return float(self.lowmem_threshold.currentText().strip("%"))
        except ValueError:
            return 85.0

    def _set_guard(self, checked: bool) -> None:
        if checked:
            self._guard_timer.start()
        else:
            self._guard_timer.stop()

    def _guard_tick(self) -> None:
        if self._guard_busy or not self._lowmem_card.isVisible():
            return
        self._guard_busy = True

        def work():
            return memopt.maybe_release_memory(self._guard_threshold(),
                                               self._all_game_exe_names())

        th = TaskThread(work, self)
        th.result.connect(self._on_guard_done)
        th.finished.connect(lambda: setattr(self, "_guard_busy", False))
        th.start()

    def _on_guard_done(self, res) -> None:
        if not res:
            return
        self.lowmem_status.setText(self.tr(
            "lowmem_guard_freed", pct=f"{res.get('pct', 0):.0f}",
            mem=self._fmt(int(res.get("freed", 0)))))

    def _apply_lite(self) -> None:
        self.lowmem_apply_btn.setEnabled(False)

        def work():
            return memopt.apply_lite_effects()

        th = TaskThread(work, self)
        th.result.connect(self._on_lite_done)
        th.finished.connect(lambda: self.lowmem_apply_btn.setEnabled(True))
        th.start()

    def _on_lite_done(self, ok: bool) -> None:
        self.lowmem_status.setText(
            self.tr("lowmem_apply_done") if ok else self.tr("common_error"))

    def _revert_lite(self) -> None:
        self.lowmem_revert_btn.setEnabled(False)

        def work():
            return memopt.revert_lite_effects()

        th = TaskThread(work, self)
        th.result.connect(self._on_revert_done)
        th.finished.connect(lambda: self.lowmem_revert_btn.setEnabled(True))
        th.start()

    def _on_revert_done(self, ok: bool) -> None:
        self.lowmem_status.setText(
            self.tr("lowmem_revert_done") if ok else self.tr("common_error"))

    def _free_now(self) -> None:
        self.lowmem_free_btn.setEnabled(False)
        self.lowmem_free_btn.setText(self.tr("boost_boosting"))

        def work():
            return memopt.release_memory(self._all_game_exe_names())

        th = TaskThread(work, self)
        th.result.connect(self._on_free_done)
        th.start()

    def _on_free_done(self, freed: int) -> None:
        self.lowmem_free_btn.setEnabled(True)
        self.lowmem_free_btn.setText(self.tr("lowmem_freenow"))
        self.lowmem_status.setText(self.tr("lowmem_freed", mem=self._fmt(int(freed or 0))))
        self._refresh_mem()

    # ------------------------------------------------------------------ #
    def _smart_boost(self) -> None:
        self.smart_btn.setEnabled(False)
        tier = self._tier or "balanced"

        def work():
            return booster.apply_profile(tier)

        self._thread = TaskThread(work, self)
        self._thread.result.connect(lambda _r: self._on_smart_done(tier))
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_smart_done(self, tier: str) -> None:
        self.smart_btn.setEnabled(True)
        tier_label = self.tr("boost_tier_" + tier)
        self.result_label.setText(self.tr("boost_smart_done", tier=tier_label))
        self._refresh_mem()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 34, 40, 30)
        root.setSpacing(14)

        # 整页滚动：标题 / 智能卡片 / 内存条 / 选项一起滚动，往上划时自动卷走
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(14)
        self.scroll_layout = col

        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        col.addWidget(self.title)
        col.addWidget(self.subtitle)

        # 智能加速卡片（自动识别设备并推荐档位）
        self._device = None
        self._tier = "balanced"
        smart = Card()
        smart_lay = QVBoxLayout(smart)
        smart_lay.setContentsMargins(18, 12, 18, 12)
        smart_lay.setSpacing(4)
        head = QHBoxLayout()
        self.smart_title = QLabel()
        self.smart_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        self.smart_btn = QPushButton()
        self.smart_btn.setObjectName("primary")
        self.smart_btn.setCursor(Qt.PointingHandCursor)
        self.smart_btn.clicked.connect(self._smart_boost)
        head.addWidget(self.smart_title, 1)
        head.addWidget(self.smart_btn)
        smart_lay.addLayout(head)
        self.smart_info = QLabel()
        self.smart_info.setObjectName("muted")
        self.smart_info.setWordWrap(True)
        self.smart_hint = QLabel()
        self.smart_hint.setObjectName("hint")
        self.smart_hint.setWordWrap(True)
        smart_lay.addWidget(self.smart_info)
        smart_lay.addWidget(self.smart_hint)
        col.addWidget(smart)

        # 低内存设备优化卡片（仅「核显笔记本」显示，设备识别完成后决定可见性）
        self._lowmem_card = Card()
        lm = QVBoxLayout(self._lowmem_card)
        lm.setContentsMargins(18, 12, 18, 12)
        lm.setSpacing(4)
        lm_head = QHBoxLayout()
        self.lowmem_title = QLabel()
        self.lowmem_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        self.lowmem_profile = QLabel()
        self.lowmem_profile.setObjectName("muted")
        lm_head.addWidget(self.lowmem_title, 1)
        lm_head.addWidget(self.lowmem_profile)
        lm.addLayout(lm_head)
        self.lowmem_desc = QLabel()
        self.lowmem_desc.setObjectName("muted")
        self.lowmem_desc.setWordWrap(True)
        lm.addWidget(self.lowmem_desc)
        self.lowmem_hint = QLabel()
        self.lowmem_hint.setObjectName("hint")
        self.lowmem_hint.setWordWrap(True)
        lm.addWidget(self.lowmem_hint)

        guard_row = QHBoxLayout()
        guard_col = QVBoxLayout()
        guard_col.setSpacing(2)
        self.lowmem_guard_name = QLabel()
        self.lowmem_guard_name.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.lowmem_guard_desc = QLabel()
        self.lowmem_guard_desc.setObjectName("muted")
        self.lowmem_guard_desc.setWordWrap(True)
        guard_col.addWidget(self.lowmem_guard_name)
        guard_col.addWidget(self.lowmem_guard_desc)
        guard_row.addLayout(guard_col, 1)
        self.lowmem_threshold_label = QLabel()
        self.lowmem_threshold_label.setObjectName("muted")
        self.lowmem_threshold = QComboBox()
        self.lowmem_threshold.addItems(["80%", "85%", "90%"])
        self.lowmem_threshold.setCurrentText("85%")
        self.lowmem_threshold.setFixedWidth(76)
        self.lowmem_guard_switch = ToggleSwitch(False)
        self.lowmem_guard_switch.toggled.connect(self._set_guard)
        guard_row.addWidget(self.lowmem_threshold_label)
        guard_row.addWidget(self.lowmem_threshold)
        guard_row.addWidget(self.lowmem_guard_switch)
        lm.addSpacing(8)
        lm.addLayout(guard_row)

        act_row = QHBoxLayout()
        act_row.setSpacing(10)
        self.lowmem_free_btn = QPushButton()
        self.lowmem_free_btn.setObjectName("primary")
        self.lowmem_free_btn.setCursor(Qt.PointingHandCursor)
        self.lowmem_free_btn.clicked.connect(self._free_now)
        self.lowmem_apply_btn = QPushButton()
        self.lowmem_apply_btn.setObjectName("ghost")
        self.lowmem_apply_btn.setCursor(Qt.PointingHandCursor)
        self.lowmem_apply_btn.clicked.connect(self._apply_lite)
        self.lowmem_revert_btn = QPushButton()
        self.lowmem_revert_btn.setObjectName("ghost")
        self.lowmem_revert_btn.setCursor(Qt.PointingHandCursor)
        self.lowmem_revert_btn.clicked.connect(self._revert_lite)
        act_row.addWidget(self.lowmem_free_btn)
        act_row.addWidget(self.lowmem_apply_btn)
        act_row.addWidget(self.lowmem_revert_btn)
        act_row.addStretch(1)
        lm.addLayout(act_row)
        self.lowmem_status = QLabel()
        self.lowmem_status.setObjectName("hint")
        self.lowmem_status.setWordWrap(True)
        lm.addWidget(self.lowmem_status)
        self._lowmem_card.setVisible(False)
        col.addWidget(self._lowmem_card)

        # 内存占用条
        self.mem_bar_label = QLabel()
        self.mem_bar_label.setObjectName("statLabel")
        self.mem_bar = QProgressBar()
        self.mem_bar.setRange(0, 100)
        self.mem_bar.setValue(0)
        self.mem_bar.setTextVisible(False)
        col.addWidget(self.mem_bar_label)
        col.addWidget(self.mem_bar)

        # 优化开关卡片
        self.options: list[tuple[str, Card, QLabel, QLabel]] = []
        option_defs = [
            ("powerplan", True), ("memory", True), ("killproc", True),
            ("gamemode", True), ("priority", True), ("hags", True),
            ("network", False), ("timer", True), ("powertweaks", False),
            ("dvr", True), ("autoboost", False),
        ]
        for key, default_on in option_defs:
            card = Card()
            lay = QHBoxLayout(card)
            lay.setContentsMargins(18, 14, 18, 14)
            lay.setSpacing(12)
            name_lbl = QLabel()
            name_lbl.setStyleSheet("font-weight: 600; font-size: 14px;")
            desc_lbl = QLabel()
            desc_lbl.setObjectName("muted")
            desc_lbl.setWordWrap(True)
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            text_col.addWidget(name_lbl)
            text_col.addWidget(desc_lbl)
            sw = ToggleSwitch(default_on)
            self._toggles[key] = sw
            if key == "autoboost":
                sw.toggled.connect(self._set_autoboost)
            lay.addLayout(text_col, 1)
            lay.addWidget(sw)
            col.addWidget(card)
            self.options.append((key, card, name_lbl, desc_lbl))
        col.addStretch(1)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        # 底部按钮固定（不随内容滚动）
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.boost_btn = QPushButton()
        self.boost_btn.setObjectName("primary")
        self.boost_btn.setCursor(Qt.PointingHandCursor)
        self.boost_btn.clicked.connect(self._start_boost)
        self.restore_btn = QPushButton()
        self.restore_btn.setObjectName("ghost")
        self.restore_btn.setCursor(Qt.PointingHandCursor)
        self.restore_btn.clicked.connect(self._restore_daily)
        self.killlist_btn = QPushButton()
        self.killlist_btn.setObjectName("ghost")
        self.killlist_btn.setCursor(Qt.PointingHandCursor)
        self.killlist_btn.clicked.connect(self._edit_kill_list)
        self.adv_btn = QPushButton()
        self.adv_btn.setObjectName("ghost")
        self.adv_btn.setCursor(Qt.PointingHandCursor)
        self.adv_btn.clicked.connect(self._open_advanced)
        btn_row.addWidget(self.boost_btn)
        btn_row.addWidget(self.restore_btn)
        btn_row.addWidget(self.killlist_btn)
        btn_row.addWidget(self.adv_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)
        self.result_label = QLabel()
        self.result_label.setObjectName("hint")
        self.result_label.setWordWrap(True)
        root.addWidget(self.result_label)

    # ------------------------------------------------------------------ #
    def start_boost(self) -> None:
        """供侧边栏「一键加速」按钮调用."""
        self._start_boost()

    def _start_boost(self) -> None:
        self.boost_btn.setEnabled(False)
        self.boost_btn.setText(self.tr("boost_boosting"))
        self.result_label.setText("")

        chosen = {k: sw.isChecked() for k, sw in self._toggles.items()}

        def work() -> dict:
            mem = booster.free_memory() if chosen.get("memory") else 0
            procs = booster.kill_background_processes() if chosen.get("killproc") else 0
            power = booster.ensure_high_performance() if chosen.get("powerplan") else ""
            if chosen.get("gamemode"):
                booster.set_game_mode(True)
            if chosen.get("priority"):
                names = []
                for g in GAMES:
                    names.extend(g.exe_names)
                booster.raise_process_priority(names)
            if chosen.get("hags") and self.main_window.is_admin:
                booster.set_hags(True)
            if chosen.get("timer"):
                booster.set_timer_resolution(True)
            if chosen.get("powertweaks") and self.main_window.is_admin:
                booster.apply_power_tweaks()
            if chosen.get("dvr"):
                booster.set_game_dvr(False)
            network_ok = False
            if chosen.get("network") and self.main_window.is_admin:
                network_ok = network.apply_network_tweaks().get("ok", False)
            return {"mem": mem, "procs": procs, "power": power, "network": network_ok}

        self._thread = TaskThread(work, self)
        self._thread.result.connect(self._on_done)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_done(self, data: dict) -> None:
        self.boost_btn.setEnabled(True)
        self.boost_btn.setText(self.tr("boost_done"))
        msg = self.tr("boost_result",
                      mem=self._fmt(data.get("mem", 0)),
                      proc=data.get("procs", 0),
                      power=data.get("power") or self.tr("state_unknown"))
        if data.get("network"):
            msg += "\n" + self.tr("boost_network_done")
        self.result_label.setText(msg)
        self._refresh_mem()

    def _on_error(self, msg: str) -> None:
        self.boost_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)
        self.boost_btn.setText(self.tr("boost_start"))
        self.result_label.setText(self.tr("common_error") + ": " + msg)

    # ------------------------------------------------------------------ #
    def _restore_daily(self) -> None:
        self.restore_btn.setEnabled(False)
        self.restore_btn.setText(self.tr("boost_restoring"))

        def work() -> dict:
            net = network.revert_network_tweaks()
            power = booster.restore_balanced_power_plan()
            booster.set_timer_resolution(False)
            booster.set_game_dvr(True)
            return {"net": net, "power": power}

        self._thread = TaskThread(work, self)
        self._thread.result.connect(self._on_restore_done)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_restore_done(self, _data: dict) -> None:
        self.restore_btn.setEnabled(True)
        self.restore_btn.setText(self.tr("boost_restore"))
        self.result_label.setText(self.tr("boost_restore_done"))
        self._refresh_mem()

    # ------------------------------------------------------------------ #
    # 游戏自动加速：检测到游戏启动即加速，全部退出后还原
    # ------------------------------------------------------------------ #
    def _all_game_exe_names(self) -> list[str]:
        names: list[str] = []
        for g in GAMES:
            names.extend(g.exe_names)
        for c in game_library.load_custom_games():
            base = os.path.basename(c.get("exe_path", ""))
            if base:
                names.append(base)
        return names

    def _set_autoboost(self, checked: bool) -> None:
        if checked:
            self._auto_timer.start()
            self.result_label.setText(self.tr("boost_autoboost_on"))
        else:
            self._auto_timer.stop()
            self.result_label.setText(self.tr("boost_autoboost_off"))

    def _auto_check(self) -> None:
        running = is_exe_running(self._all_game_exe_names())
        if running and not self._auto_was_running:
            self._auto_was_running = True
            self.result_label.setText(self.tr("boost_autoboost_boosted"))
            self._auto_boost()
        elif not running and self._auto_was_running:
            self._auto_was_running = False
            self.result_label.setText(self.tr("boost_autoboost_reverted"))
            self._auto_revert()

    def _auto_boost(self) -> None:
        def work():
            booster.set_timer_resolution(True)
            booster.apply_power_tweaks()
            booster.free_memory()
            booster.set_game_mode(True)
            booster.set_game_dvr(False)
        self._thread = TaskThread(work, self)
        self._thread.start()

    def _auto_revert(self) -> None:
        def work():
            booster.set_timer_resolution(False)
            booster.restore_balanced_power_plan()
        self._thread = TaskThread(work, self)
        self._thread.start()

    # ------------------------------------------------------------------ #
    # 自定义结束后台进程名单
    # ------------------------------------------------------------------ #
    def _open_advanced(self) -> None:
        from .advanced import CpuTuningDialog
        CpuTuningDialog(self.translator, self).exec()

    def _edit_kill_list(self) -> None:
        names = booster.load_kill_list()
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("boost_killlist_title"))
        dlg.resize(440, 380)
        lay = QVBoxLayout(dlg)
        tip = QLabel(self.tr("boost_killlist_tip"))
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        edit = QTextEdit()
        edit.setPlainText("\n".join(names))
        lay.addWidget(edit, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok_btn = QPushButton(self.tr("common_ok"))
        ok_btn.setObjectName("primary")
        cancel_btn = QPushButton(self.tr("common_cancel"))
        cancel_btn.setObjectName("ghost")
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        row.addWidget(ok_btn)
        row.addWidget(cancel_btn)
        lay.addLayout(row)
        if dlg.exec() == QDialog.Accepted:
            booster.save_kill_list([ln.strip() for ln in edit.toPlainText().splitlines() if ln.strip()])

    # ------------------------------------------------------------------ #
    def _refresh_mem(self) -> None:
        stats = booster.get_system_stats()
        self.mem_bar.setValue(int(stats.memory_percent))
        self.mem_bar_label.setText(
            f"{self.tr('boost_mem_bar')}  {stats.memory_percent:.0f}%")

    @staticmethod
    def _fmt(n: int) -> str:
        from ..core.cleaner import format_bytes
        return format_bytes(n)

    def refresh_on_show(self) -> None:
        self._refresh_mem()

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.title.setText(self.tr("boost_title"))
        self.subtitle.setText(self.tr("boost_subtitle"))
        self.smart_title.setText(self.tr("boost_smart_title"))
        self.smart_btn.setText(self.tr("boost_smart_btn"))
        self.boost_btn.setText(self.tr("boost_start"))
        self.restore_btn.setText(self.tr("boost_restore"))
        self.killlist_btn.setText(self.tr("boost_killlist_btn"))
        self.adv_btn.setText(self.tr("adv_btn"))
        self.mem_bar_label.setText(self.tr("boost_mem_bar"))
        self.lowmem_title.setText(self.tr("lowmem_title"))
        self.lowmem_desc.setText(self.tr("lowmem_desc"))
        self.lowmem_guard_name.setText(self.tr("lowmem_guard"))
        self.lowmem_guard_desc.setText(self.tr("lowmem_guard_desc"))
        self.lowmem_threshold_label.setText(self.tr("lowmem_threshold"))
        self.lowmem_apply_btn.setText(self.tr("lowmem_apply"))
        self.lowmem_revert_btn.setText(self.tr("lowmem_revert"))
        self.lowmem_free_btn.setText(self.tr("lowmem_freenow"))
        if getattr(self, "_lowmem_ram", 0):
            self.lowmem_profile.setText(self._lowmem_profile_text())
        if getattr(self, "_lowmem_dev", None):
            self.lowmem_hint.setText("\n".join(
                "• " + self.tr(k) for k in memopt.low_mem_hints(self._lowmem_dev)))
        for key, _card, name_lbl, desc_lbl in self.options:
            base = _OPTION_KEYS[key]
            name_lbl.setText(self.tr(base))
            desc_lbl.setText(self.tr(base + "_desc"))
            if key in ("hags", "network", "powertweaks") and not self.main_window.is_admin:
                self._toggles[key].setEnabled(False)
                self._toggles[key].setChecked(False)
                desc_lbl.setText(desc_lbl.text() + "  ⚠ " + self.tr("settings_admin"))
