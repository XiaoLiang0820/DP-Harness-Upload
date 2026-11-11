"""FrameBoost 极帧加速 — 高级设置面板.

默认锁定：只有用户在设置页主动解锁后才会构建并显示内部选项，
避免不懂的用户误触。

面板内容（每张卡片都会按平台能力自动显示/隐藏）：
  · 平台能力报告（CPU / 设备 / 权限 / 温度源 / 降压可行性）
  · CPU 频率上下限与睿频模式
  · 软件温度墙
  · 启动处理器数量（numproc）
  · NVIDIA 显卡功耗墙（仅 N 卡）
  · CPU 电压的事实说明
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSlider,
)

from ..core import admin, hwtune, prefs
from ..i18n import Translator
from ..widgets import Card, ToggleSwitch, TaskThread
from . import ask_confirm, show_error, show_info


class AdvancedPanel(QWidget):
    """高级设置容器：解锁卡片 +（解锁后可见的）全部调校卡片."""

    def __init__(self, translator: Translator, main_window,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        self.tr = translator.tr
        self.main_window = main_window
        self._probe: dict | None = None
        self._threads: list[TaskThread] = []
        self._texts: list[tuple[QLabel, str]] = []
        self._pending_status: list[tuple[str, QLabel]] = []
        self._unlocked = False
        self._build()
        self.retranslate()
        translator.changed.connect(self._on_lang_changed)
        self.set_unlocked(bool(prefs.get("advanced_unlocked", False)), silent=True)

    # ------------------------------------------------------------------ #
    # 构建
    # ------------------------------------------------------------------ #
    def _label(self, key: str, obj: str | None = None, wrap: bool = True) -> QLabel:
        lb = QLabel()
        if obj:
            lb.setObjectName(obj)
        lb.setWordWrap(wrap)
        self._texts.append((lb, key))
        return lb

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # ---- 解锁卡片 ----
        self.unlock_card = Card()
        unlock_lay = QHBoxLayout(self.unlock_card)
        unlock_lay.setContentsMargins(18, 14, 18, 14)
        unlock_lay.setSpacing(12)
        unlock_col = QVBoxLayout()
        unlock_col.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.adv_title = self._label("advs_title", "advTitle", wrap=False)
        self.adv_badge = QLabel()
        self.adv_badge.setObjectName("advBadge")
        head.addWidget(self.adv_title)
        head.addWidget(self.adv_badge)
        head.addStretch(1)
        self.adv_desc = self._label("advs_desc", "muted")
        unlock_col.addLayout(head)
        unlock_col.addWidget(self.adv_desc)
        self.adv_switch = ToggleSwitch(False)
        self.adv_switch.toggled.connect(self._on_toggle)
        unlock_lay.addLayout(unlock_col, 1)
        unlock_lay.addWidget(self.adv_switch)
        root.addWidget(self.unlock_card)

        # ---- 解锁后可见的主体 ----
        self.body = QWidget()
        body_lay = QVBoxLayout(self.body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(14)

        body_lay.addWidget(self._build_status_card())
        body_lay.addWidget(self._build_cpu_card())
        body_lay.addWidget(self._build_thermal_card())
        body_lay.addWidget(self._build_cores_card())
        self.gpu_card = self._build_gpu_card()
        body_lay.addWidget(self.gpu_card)
        body_lay.addWidget(self._build_voltage_card())
        root.addWidget(self.body)

    # ---- 平台能力 ----
    def _build_status_card(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        self.status_title = self._label("advs_status_title", "advTitle", wrap=False)
        lay.addWidget(self.status_title)

        self.status_grid = QVBoxLayout()
        self.status_grid.setSpacing(5)
        self.status_rows: dict[str, QLabel] = {}
        for key in ("cpu", "device", "perm", "temp", "numproc", "uv"):
            row = QHBoxLayout()
            row.setSpacing(10)
            name = QLabel()
            name.setFixedWidth(76)
            name.setObjectName("advKey")
            val = QLabel()
            val.setWordWrap(True)
            val.setObjectName("advVal")
            row.addWidget(name)
            row.addWidget(val, 1)
            self.status_grid.addLayout(row)
            self.status_rows[key] = name
            self._texts.append((name, f"advs_k_{key}"))
            self._pending_status.append((key, val))
        lay.addLayout(self.status_grid)
        self.status_hint = self._label("advs_status_hint", "hint")
        lay.addWidget(self.status_hint)
        self.status_refresh_btn = QPushButton()
        self.status_refresh_btn.setObjectName("ghost")
        self.status_refresh_btn.setCursor(Qt.PointingHandCursor)
        self.status_refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(self.status_refresh_btn, 0, Qt.AlignLeft)
        return card

    # ---- CPU 频率 ----
    def _build_cpu_card(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        self.cpu_title = self._label("advs_cpu_title", "advTitle", wrap=False)
        lay.addWidget(self.cpu_title)

        self.max_state = self._slider_row(
            lay, "advs_max_state", 25, 100, 100, "advs_pct")
        self.min_state = self._slider_row(
            lay, "advs_min_state", 0, 100, 5, "advs_pct")

        boost_row = QHBoxLayout()
        boost_row.setSpacing(10)
        self.boost_name = self._label("advs_boost_mode", wrap=False)
        self.boost_name.setMinimumWidth(150)
        self.boost_combo = QComboBox()
        self.boost_combo.setMinimumWidth(200)
        boost_row.addWidget(self.boost_name)
        boost_row.addWidget(self.boost_combo, 1)
        lay.addLayout(boost_row)

        self.cpu_note = self._label("advs_cpu_note", "hint")
        lay.addWidget(self.cpu_note)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.cpu_apply_btn = QPushButton()
        self.cpu_apply_btn.setObjectName("primary")
        self.cpu_apply_btn.setCursor(Qt.PointingHandCursor)
        self.cpu_apply_btn.clicked.connect(self._apply_cpu)
        self.cpu_reset_btn = QPushButton()
        self.cpu_reset_btn.setObjectName("ghost")
        self.cpu_reset_btn.setCursor(Qt.PointingHandCursor)
        self.cpu_reset_btn.clicked.connect(self._reset_cpu)
        btn_row.addWidget(self.cpu_apply_btn)
        btn_row.addWidget(self.cpu_reset_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.cpu_status = QLabel()
        self.cpu_status.setObjectName("hint")
        self.cpu_status.setWordWrap(True)
        lay.addWidget(self.cpu_status)
        return card

    def _slider_row(self, lay: QVBoxLayout, key: str, lo: int, hi: int,
                    val: int, unit_key: str) -> QSlider:
        row = QHBoxLayout()
        row.setSpacing(10)
        name = self._label(key, wrap=False)
        name.setMinimumWidth(150)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(val)
        slider.setMinimumWidth(200)
        value_label = QLabel()
        value_label.setObjectName("advVal")
        value_label.setFixedWidth(52)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider.valueChanged.connect(
            lambda v, lb=value_label: lb.setText(f"{v}%"))
        value_label.setText(f"{val}%")
        row.addWidget(name)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        lay.addLayout(row)
        return slider

    # ---- 温度墙 ----
    def _build_thermal_card(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        self.thermal_title = self._label("advs_thermal_title", "advTitle", wrap=False)
        lay.addWidget(self.thermal_title)
        self.thermal_desc = self._label("advs_thermal_desc", "hint")
        lay.addWidget(self.thermal_desc)

        self.thermal_temp = QLabel()
        self.thermal_temp.setObjectName("advBig")
        lay.addWidget(self.thermal_temp)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(10)
        self.thermal_switch_name = self._label("advs_thermal_on", wrap=False)
        self.thermal_switch = ToggleSwitch(bool(prefs.get("thermal_guard", False)))
        self.thermal_switch.toggled.connect(self._on_thermal_toggled)
        toggle_row.addWidget(self.thermal_switch_name, 1)
        toggle_row.addWidget(self.thermal_switch)
        lay.addLayout(toggle_row)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(10)
        self.thermal_th_name = self._label("advs_thermal_threshold", wrap=False)
        self.thermal_th_combo = QComboBox()
        self.thermal_th_combo.setFixedWidth(96)
        self.thermal_th_combo.currentIndexChanged.connect(self._on_thermal_values)
        self.thermal_floor_name = self._label("advs_thermal_floor", wrap=False)
        self.thermal_floor_combo = QComboBox()
        self.thermal_floor_combo.setFixedWidth(96)
        self.thermal_floor_combo.currentIndexChanged.connect(self._on_thermal_values)
        pick_row.addWidget(self.thermal_th_name)
        pick_row.addWidget(self.thermal_th_combo)
        pick_row.addSpacing(12)
        pick_row.addWidget(self.thermal_floor_name)
        pick_row.addWidget(self.thermal_floor_combo)
        pick_row.addStretch(1)
        lay.addLayout(pick_row)

        self.thermal_status = QLabel()
        self.thermal_status.setObjectName("hint")
        self.thermal_status.setWordWrap(True)
        lay.addWidget(self.thermal_status)
        return card

    # ---- 核心与线程 ----
    def _build_cores_card(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        self.cores_title = self._label("advs_cores_title", "advTitle", wrap=False)
        lay.addWidget(self.cores_title)

        self.cores_info = QLabel()
        self.cores_info.setObjectName("advVal")
        lay.addWidget(self.cores_info)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.cores_limit_name = self._label("advs_cores_limit", wrap=False)
        self.cores_combo = QComboBox()
        self.cores_combo.setMinimumWidth(180)
        self.cores_apply_btn = QPushButton()
        self.cores_apply_btn.setObjectName("primary")
        self.cores_apply_btn.setCursor(Qt.PointingHandCursor)
        self.cores_apply_btn.clicked.connect(self._apply_cores)
        row.addWidget(self.cores_limit_name)
        row.addWidget(self.cores_combo, 1)
        row.addWidget(self.cores_apply_btn)
        lay.addLayout(row)

        self.cores_note = self._label("advs_cores_reboot", "hint")
        lay.addWidget(self.cores_note)
        self.cores_status = QLabel()
        self.cores_status.setObjectName("hint")
        self.cores_status.setWordWrap(True)
        lay.addWidget(self.cores_status)
        return card

    # ---- 显卡功耗墙 ----
    def _build_gpu_card(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        self.gpu_title = self._label("advs_gpu_title", "advTitle", wrap=False)
        lay.addWidget(self.gpu_title)
        self.gpu_name = QLabel()
        self.gpu_name.setObjectName("advVal")
        lay.addWidget(self.gpu_name)

        slider_row = QHBoxLayout()
        slider_row.setSpacing(10)
        self.gpu_slider = QSlider(Qt.Horizontal)
        self.gpu_slider.setRange(0, 100)
        self.gpu_slider.setMinimumWidth(200)
        self.gpu_value = QLabel("--")
        self.gpu_value.setObjectName("advVal")
        self.gpu_value.setFixedWidth(64)
        self.gpu_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.gpu_slider.valueChanged.connect(
            lambda v: self.gpu_value.setText(f"{v} W"))
        slider_row.addWidget(self.gpu_slider, 1)
        slider_row.addWidget(self.gpu_value)
        lay.addLayout(slider_row)

        self.gpu_note = self._label("advs_gpu_note", "hint")
        lay.addWidget(self.gpu_note)

        self.gpu_apply_btn = QPushButton()
        self.gpu_apply_btn.setObjectName("primary")
        self.gpu_apply_btn.setCursor(Qt.PointingHandCursor)
        self.gpu_apply_btn.clicked.connect(self._apply_gpu)
        lay.addWidget(self.gpu_apply_btn, 0, Qt.AlignLeft)
        self.gpu_status = QLabel()
        self.gpu_status.setObjectName("hint")
        self.gpu_status.setWordWrap(True)
        lay.addWidget(self.gpu_status)
        card.setVisible(False)
        return card

    # ---- 电压说明 ----
    def _build_voltage_card(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        self.voltage_title = self._label("advs_voltage_title", "advTitle", wrap=False)
        lay.addWidget(self.voltage_title)
        self.voltage_verdict = QLabel()
        self.voltage_verdict.setObjectName("advWarn")
        self.voltage_verdict.setWordWrap(True)
        lay.addWidget(self.voltage_verdict)
        self.voltage_body = self._label("advs_voltage_body", "hint")
        lay.addWidget(self.voltage_body)
        return card

    # ------------------------------------------------------------------ #
    # 解锁 / 锁定
    # ------------------------------------------------------------------ #
    def set_unlocked(self, unlocked: bool, silent: bool = False) -> None:
        self._unlocked = bool(unlocked)
        self.adv_switch.blockSignals(True)
        self.adv_switch.setChecked(self._unlocked)
        self.adv_switch.blockSignals(False)
        self.body.setVisible(self._unlocked)
        if self._unlocked:
            self.refresh()
        else:
            self._probe = None
        if not silent:
            prefs.set_value("advanced_unlocked", self._unlocked)

    def _on_toggle(self, checked: bool) -> None:
        if checked:
            if not ask_confirm(self, self.tr("advs_confirm_title"),
                               self.tr("advs_confirm_text"), self.tr):
                self.adv_switch.blockSignals(True)
                self.adv_switch.setChecked(False)
                self.adv_switch.blockSignals(False)
                return
        self.set_unlocked(checked)

    def is_unlocked(self) -> bool:
        return self._unlocked

    # ------------------------------------------------------------------ #
    # 探测 / 刷新
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        if not self._unlocked:
            return
        self._set_status_values({k: self.tr("common_loading") for k in self.status_rows})
        self._run(hwtune.probe, self._on_probe_done)

    def _on_probe_done(self, data: dict) -> None:
        self._probe = data
        self._fill_from_probe(data)

    def _fill_from_probe(self, data: dict) -> None:
        cpu = data.get("cpu") or {}
        dev = data.get("device") or {}
        power = data.get("power") or {}
        temp = data.get("temp") or {}
        av = power.get("available") or {}

        kind_key = {"desktop": "advs_dev_desktop", "gaming_laptop": "advs_dev_gaming",
                    "thin_light": "advs_dev_thin"}.get(dev.get("kind") or "", "advs_dev_unknown")
        gen = cpu.get("gen")
        cpu_text = cpu.get("name") or "?"
        if gen:
            cpu_text = f"{cpu_text}  ({gen}{self.tr('advs_gen_suffix')})"
        self._set_status_values({
            "cpu": cpu_text,
            "device": f"{dev.get('oem') or '?'} · {self.tr(kind_key)}",
            "perm": self.tr("advs_admin_yes") if data.get("is_admin")
                    else self.tr("advs_admin_no"),
            "temp": self._temp_text(temp),
            "numproc": (f"{data['numproc']}" if data.get("numproc")
                        else self.tr("advs_cores_none_short")),
            "uv": self.tr(f"advs_uv_{data.get('undervolt', {}).get('level', 'unknown')}"),
        })

        # CPU 卡片
        for key, slider in (("max_state", self.max_state), ("min_state", self.min_state)):
            rng = av.get(key)
            if rng:
                slider.setRange(max(0, int(rng["min"])), int(rng["max"]))
            if key in power:
                slider.blockSignals(True)
                slider.setValue(int(power[key]))
                slider.blockSignals(False)
        self.boost_combo.blockSignals(True)
        self.boost_combo.clear()
        for mode in (power.get("boost_options") or []):
            self.boost_combo.addItem(self.tr(f"advs_boost_{mode}"), mode)
        if power.get("boost_mode") is not None:
            idx = self.boost_combo.findData(int(power["boost_mode"]))
            if idx >= 0:
                self.boost_combo.setCurrentIndex(idx)
        self.boost_combo.blockSignals(False)

        # 显卡
        nv = data.get("nvidia")
        if nv:
            self.gpu_card.setVisible(True)
            lo, hi = float(nv["min"]), float(nv["max"])
            self.gpu_name.setText(
                "{} · {:.0f} W  ({})".format(
                    nv["name"], float(nv["limit"]),
                    self.tr("advs_gpu_range", min=f"{lo:.0f}", max=f"{hi:.0f}")))
            self.gpu_slider.blockSignals(True)
            self.gpu_slider.setRange(int(lo), int(hi))
            self.gpu_slider.setValue(int(float(nv["limit"])))
            self.gpu_slider.blockSignals(False)
            self.gpu_value.setText(f"{float(nv['limit']):.0f} W")
        else:
            self.gpu_card.setVisible(False)

        # 核心
        self.cores_info.setText(self.tr("advs_cores_info", p=data.get("physical", 0),
                                        l=data.get("logical", 0)))
        self._fill_numproc_combo(data.get("logical", 0), data.get("numproc"))
        self.cores_status.setText(
            self.tr("advs_cores_current",
                    n=data["numproc"]) if data.get("numproc")
            else self.tr("advs_cores_none"))

        # 电压结论
        level = (data.get("undervolt") or {}).get("level", "unknown")
        self.voltage_verdict.setText(self.tr(f"advs_uv_{level}"))

        # 温度显示
        self._update_temp_label(temp)

    def _temp_text(self, temp: dict) -> str:
        if temp.get("c") is None:
            return self.tr("advs_temp_none")
        return f"{temp['c']:.0f} °C · {self.tr('advs_src_' + (temp.get('source') or 'acpi'))}"

    def _update_temp_label(self, temp: dict) -> None:
        if temp.get("c") is None:
            self.thermal_temp.setText(self.tr("advs_thermal_no_sensor"))
            self.thermal_temp.setStyleSheet("color:#8B9AA9; font-size:13px;")
        else:
            engaged = bool(prefs.get("thermal_engaged", False))
            color = "#F59E0B" if engaged else "#E8EEF5"
            self.thermal_temp.setText(
                f"{temp['c']:.0f} °C  ·  "
                + (self.tr("advs_thermal_state_engaged") if engaged
                   else self.tr("advs_thermal_state_idle")))
            self.thermal_temp.setStyleSheet(
                f"color:{color}; font-size:18px; font-weight:700;")

    def _set_status_values(self, mapping: dict) -> None:
        for key, label in self._pending_status:
            if key in mapping:
                label.setText(mapping[key])

    def _fill_numproc_combo(self, logical: int, current: int | None) -> None:
        self.cores_combo.blockSignals(True)
        self.cores_combo.clear()
        self.cores_combo.addItem(self.tr("advs_cores_all"), 0)
        for n in range(1, max(1, logical) + 1):
            self.cores_combo.addItem(str(n), n)
        self.cores_combo.setCurrentIndex(self.cores_combo.findData(current or 0))
        if self.cores_combo.currentIndex() < 0:
            self.cores_combo.setCurrentIndex(0)
        self.cores_combo.blockSignals(False)

    # ------------------------------------------------------------------ #
    # 应用动作
    # ------------------------------------------------------------------ #
    def _run(self, fn, on_done) -> None:
        thread = TaskThread(fn, self)
        thread.result.connect(on_done)
        thread.error.connect(lambda msg: self._show_error(str(msg)))
        # 防止线程对象被 GC
        self._threads.append(thread)
        thread.finished.connect(lambda: self._threads.remove(thread)
                                if thread in self._threads else None)
        thread.start()

    def _show_error(self, msg: str) -> None:
        show_error(self, self.tr("common_error"), msg, self.tr)

    def _also_dc(self) -> bool:
        return bool(prefs.get("also_dc", True))

    def _apply_cpu(self) -> None:
        values = {
            "max_state": self.max_state.value(),
            "min_state": self.min_state.value(),
            "boost_mode": self.boost_combo.currentData(),
        }
        self.cpu_status.setText(self.tr("common_loading"))
        self._run(lambda: hwtune.apply_power_batch(values, also_dc=self._also_dc()),
                  self._on_cpu_applied)

    def _on_cpu_applied(self, results: dict) -> None:
        bad = {k: v for k, v in results.items() if not v.get("ok")}
        if not bad:
            detail = " · ".join(f"{self.tr('advs_k_' + k)}={v['applied']}"
                                for k, v in results.items())
            self.cpu_status.setText(self.tr("advs_applied", detail=detail))
            return
        parts = []
        for key, res in bad.items():
            reason = res.get("reason")
            if reason == "no_admin":
                parts.append(self.tr("advs_need_admin"))
            elif reason == "overridden":
                parts.append(self.tr("advs_override", cur=res.get("applied")))
            elif reason == "out_of_range":
                parts.append(self.tr("advs_out_of_range"))
            else:
                parts.append(self.tr("advs_write_failed"))
        self.cpu_status.setText("  ".join(dict.fromkeys(parts)))

    def _reset_cpu(self) -> None:
        self.cpu_status.setText(self.tr("common_loading"))
        self._run(lambda: hwtune.reset_power_defaults(self._also_dc()),
                  lambda res: (self._on_cpu_applied(res), self.refresh()))

    def _on_thermal_toggled(self, checked: bool) -> None:
        if not checked:
            prefs.set_value("thermal_guard", False)
            self._sync_guard()
            return

        # 开启前一次性校验，避免连弹多个提示框
        reason = ""
        if not admin.is_admin():
            reason = "advs_need_admin"
        elif self._probe is not None and (self._probe.get("temp") or {}).get("c") is None:
            reason = "advs_thermal_sensor_hint"

        if reason:
            # 条件不满足 → 开关回弹，不写入配置
            self.thermal_switch.blockSignals(True)
            self.thermal_switch.setChecked(False)
            self.thermal_switch.blockSignals(False)
            show_info(self, self.tr("common_info"), self.tr(reason), self.tr)
            return

        prefs.set_value("thermal_guard", True)
        self._sync_guard()

    def _sync_guard(self) -> None:
        sync = getattr(self.main_window, "sync_thermal_guard", None)
        if callable(sync):
            sync()

    def _on_thermal_values(self, *_args) -> None:
        prefs.save({
            "thermal_threshold": int(self.thermal_th_combo.currentData() or 90),
            "thermal_floor": int(self.thermal_floor_combo.currentData() or 70),
        })

    def _apply_cores(self) -> None:
        value = int(self.cores_combo.currentData() or 0)
        self.cores_status.setText(self.tr("common_loading"))
        target = None if value == 0 else value
        self._run(lambda: hwtune.set_boot_numproc(target),
                  lambda ok: self.cores_status.setText(
                      self.tr("advs_cores_applied") if ok else self.tr("advs_need_admin")))

    def _apply_gpu(self) -> None:
        watts = self.gpu_slider.value()
        self.gpu_status.setText(self.tr("common_loading"))
        self._run(lambda: hwtune.set_nvidia_power_limit(watts), self._on_gpu_applied)

    def _on_gpu_applied(self, res: dict) -> None:
        if res.get("ok"):
            self.gpu_status.setText(self.tr("advs_applied", detail=f"{res['applied']:.0f} W"))
        elif res.get("reason") == "no_admin":
            self.gpu_status.setText(self.tr("advs_need_admin"))
        elif res.get("reason") == "overridden":
            self.gpu_status.setText(self.tr("advs_override", cur=f"{res.get('applied'):.0f} W"))
        else:
            self.gpu_status.setText(self.tr("advs_write_failed"))

    # ------------------------------------------------------------------ #
    # 文案
    # ------------------------------------------------------------------ #
    def _on_lang_changed(self, _lang: str) -> None:
        self.retranslate()

    def retranslate(self) -> None:
        for label, key in self._texts:
            label.setText(self.tr(key))
        self.adv_badge.setText(self.tr("advs_badge"))
        self.status_refresh_btn.setText(self.tr("common_refresh"))
        self.cpu_apply_btn.setText(self.tr("advs_apply"))
        self.cpu_reset_btn.setText(self.tr("advs_reset"))
        self.cores_apply_btn.setText(self.tr("advs_apply"))
        self.gpu_apply_btn.setText(self.tr("advs_apply"))

        # 温度阈值 / 降频幅度下拉
        self._fill_combo(self.thermal_th_combo,
                         [(75, "75 °C"), (80, "80 °C"), (85, "85 °C"),
                          (90, "90 °C"), (95, "95 °C"), (100, "100 °C")],
                         int(prefs.get("thermal_threshold", 90)))
        self._fill_combo(self.thermal_floor_combo,
                         [(40, "40%"), (50, "50%"), (60, "60%"),
                          (70, "70%"), (80, "80%")],
                         int(prefs.get("thermal_floor", 70)))

        if self._probe:
            self._fill_from_probe(self._probe)
        else:
            self._set_status_values({k: "--" for k in self.status_rows})
            self.thermal_temp.setText(self.tr("advs_thermal_idle_hint"))
            self.cores_info.setText(self.tr("advs_cores_info", p="--", l="--"))

    @staticmethod
    def _fill_combo(combo: QComboBox, items: list[tuple[int, str]], current: int) -> None:
        combo.blockSignals(True)
        combo.clear()
        for value, label in items:
            combo.addItem(label, value)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
