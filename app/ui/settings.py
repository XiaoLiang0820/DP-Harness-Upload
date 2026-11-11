"""FrameBoost 极帧加速 — 设置页."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QScrollArea,
)

from .. import version
from ..core import admin, automation, cleaner
from ..i18n import Translator
from ..widgets import Card, ToggleSwitch
from . import Page
from .adv_panel import AdvancedPanel


class SettingsPage(Page):
    def __init__(self, translator: Translator, main_window, parent: QWidget | None = None) -> None:
        super().__init__(translator, parent)
        self.main_window = main_window
        self._build()
        self.retranslate()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 34, 40, 30)
        root.setSpacing(18)

        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        content_lay = QVBoxLayout(scroll_content)
        content_lay.setContentsMargins(0, 0, 8, 0)
        content_lay.setSpacing(14)

        # 语言
        lang_card = Card()
        lang_lay = QHBoxLayout(lang_card)
        lang_lay.setContentsMargins(18, 14, 18, 14)
        lang_lay.setSpacing(12)
        self.lang_title = QLabel()
        self.lang_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        lang_lay.addWidget(self.lang_title)
        lang_lay.addStretch(1)
        self.lang_zh_btn = QPushButton("中文")
        self.lang_en_btn = QPushButton("English")
        for b in (self.lang_zh_btn, self.lang_en_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setObjectName("ghost")
            b.setCheckable(False)
        self.lang_zh_btn.clicked.connect(lambda: self._set_lang("zh"))
        self.lang_en_btn.clicked.connect(lambda: self._set_lang("en"))
        lang_lay.addWidget(self.lang_zh_btn)
        lang_lay.addWidget(self.lang_en_btn)
        content_lay.addWidget(lang_card)

        # 安全
        safe_card = Card()
        safe_lay = QHBoxLayout(safe_card)
        safe_lay.setContentsMargins(18, 14, 18, 14)
        safe_lay.setSpacing(12)
        safe_col = QVBoxLayout()
        safe_col.setSpacing(2)
        self.safe_title = QLabel()
        self.safe_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.safe_desc = QLabel()
        self.safe_desc.setObjectName("muted")
        self.safe_desc.setWordWrap(True)
        safe_col.addWidget(self.safe_title)
        safe_col.addWidget(self.safe_desc)
        self.safe_switch = ToggleSwitch(True)
        safe_lay.addLayout(safe_col, 1)
        safe_lay.addWidget(self.safe_switch)
        content_lay.addWidget(safe_card)

        # 高级设置（默认锁定，解锁后才显示内部选项）
        self.adv_panel = AdvancedPanel(self.translator, self.main_window)
        content_lay.addWidget(self.adv_panel)

        # 自动清理（开机自启 / 定时）
        auto_card = Card()
        auto_lay = QVBoxLayout(auto_card)
        auto_lay.setContentsMargins(18, 14, 18, 14)
        auto_lay.setSpacing(10)
        self.auto_title = QLabel()
        self.auto_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        auto_lay.addWidget(self.auto_title)

        startup_row = QHBoxLayout()
        startup_row.setSpacing(12)
        startup_col = QVBoxLayout()
        startup_col.setSpacing(2)
        self.auto_startup_name = QLabel()
        self.auto_startup_name.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.auto_startup_desc = QLabel()
        self.auto_startup_desc.setObjectName("muted")
        self.auto_startup_desc.setWordWrap(True)
        startup_col.addWidget(self.auto_startup_name)
        startup_col.addWidget(self.auto_startup_desc)
        self.auto_startup_switch = ToggleSwitch(False)
        self.auto_startup_switch.toggled.connect(self._on_startup_toggled)
        startup_row.addLayout(startup_col, 1)
        startup_row.addWidget(self.auto_startup_switch)
        auto_lay.addLayout(startup_row)

        sched_row = QHBoxLayout()
        sched_row.setSpacing(12)
        sched_col = QVBoxLayout()
        sched_col.setSpacing(2)
        self.auto_sched_name = QLabel()
        self.auto_sched_name.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.auto_sched_desc = QLabel()
        self.auto_sched_desc.setObjectName("muted")
        self.auto_sched_desc.setWordWrap(True)
        sched_col.addWidget(self.auto_sched_name)
        sched_col.addWidget(self.auto_sched_desc)
        self.auto_time_label = QLabel()
        self.auto_time_label.setObjectName("muted")
        self.auto_time = QComboBox()
        self.auto_time.addItems(["00:00", "06:00", "08:00", "12:00", "18:00", "22:00"])
        self.auto_time.setCurrentText("12:00")
        self.auto_time.setFixedWidth(96)
        self.auto_sched_switch = ToggleSwitch(False)
        self.auto_sched_switch.toggled.connect(self._on_schedule_toggled)
        self.auto_time.currentTextChanged.connect(self._on_schedule_time_changed)
        sched_row.addLayout(sched_col, 1)
        sched_row.addWidget(self.auto_time_label)
        sched_row.addWidget(self.auto_time)
        sched_row.addWidget(self.auto_sched_switch)
        auto_lay.addLayout(sched_row)

        self.auto_last_label = QLabel()
        self.auto_last_label.setObjectName("muted")
        auto_lay.addWidget(self.auto_last_label)

        content_lay.addWidget(auto_card)

        # 管理员
        self.admin_card = Card()
        admin_lay = QVBoxLayout(self.admin_card)
        admin_lay.setContentsMargins(18, 14, 18, 14)
        admin_lay.setSpacing(8)
        self.admin_title = QLabel()
        self.admin_title.setStyleSheet("font-weight: 600; font-size: 14px; color: #F59E0B;")
        self.admin_hint = QLabel()
        self.admin_hint.setObjectName("muted")
        self.admin_hint.setWordWrap(True)
        self.admin_btn = QPushButton()
        self.admin_btn.setObjectName("danger")
        self.admin_btn.setCursor(Qt.PointingHandCursor)
        self.admin_btn.clicked.connect(self._relaunch_admin)
        admin_lay.addWidget(self.admin_title)
        admin_lay.addWidget(self.admin_hint)
        admin_lay.addWidget(self.admin_btn, 0, Qt.AlignLeft)
        content_lay.addWidget(self.admin_card)
        self.admin_card.setVisible(not self.main_window.is_admin)

        # 工具：性能悬浮窗 / 诊断报告
        self.tool_card = Card()
        tool_lay = QVBoxLayout(self.tool_card)
        tool_lay.setContentsMargins(18, 14, 18, 14)
        tool_lay.setSpacing(8)
        self.tool_title = QLabel()
        self.tool_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        tool_row = QHBoxLayout()
        tool_row.setSpacing(10)
        self.overlay_btn = QPushButton()
        self.overlay_btn.setObjectName("ghost")
        self.overlay_btn.setCursor(Qt.PointingHandCursor)
        self.overlay_btn.clicked.connect(self.main_window.toggle_overlay)
        self.diag_btn = QPushButton()
        self.diag_btn.setObjectName("ghost")
        self.diag_btn.setCursor(Qt.PointingHandCursor)
        self.diag_btn.clicked.connect(self._export_diag)
        tool_row.addWidget(self.overlay_btn)
        tool_row.addWidget(self.diag_btn)
        tool_row.addStretch(1)
        tool_lay.addWidget(self.tool_title)
        tool_lay.addLayout(tool_row)
        content_lay.addWidget(self.tool_card)

        # 关于
        about_card = Card()
        about_lay = QVBoxLayout(about_card)
        about_lay.setContentsMargins(18, 14, 18, 14)
        self.about_title = QLabel()
        self.about_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.about_text = QLabel()
        self.about_text.setObjectName("muted")
        self.about_text.setWordWrap(True)
        about_lay.addWidget(self.about_title)
        about_lay.addWidget(self.about_text)
        content_lay.addWidget(about_card)

        content_lay.addStretch(1)
        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

    def _set_lang(self, lang: str) -> None:
        self.translator.set_lang(lang)
        self._update_lang_buttons()

    def _update_lang_buttons(self) -> None:
        active = self.translator.lang
        style_active = (
            "QPushButton { background: #3D8BFF; color: white; border-radius: 10px;"
            " padding: 10px 18px; font-weight: 700; }")
        style_idle = (
            "QPushButton { background: #1A2430; color: #8B9AA9; border-radius: 10px;"
            " padding: 10px 18px; font-weight: 600; }"
            "QPushButton:hover { background: #22303F; color: #E8EEF5; }")
        self.lang_zh_btn.setStyleSheet(style_active if active == "zh" else style_idle)
        self.lang_en_btn.setStyleSheet(style_active if active == "en" else style_idle)

    def _relaunch_admin(self) -> None:
        if admin.relaunch_as_admin():
            # UAC 通过、新管理员实例已启动 → 关闭当前旧实例
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.quit()
        else:
            from . import show_info
            show_info(self, self.tr("common_info"), self.tr("admin_cancelled"), self.tr)

    # ------------------------------------------------------------------ #
    # 自动清理
    # ------------------------------------------------------------------ #
    def refresh_on_show(self) -> None:
        self._load_automation_state()
        # 重新探测温度与当前电源设置（进入设置页时刷新一次）
        if self.adv_panel.is_unlocked():
            self.adv_panel.refresh()

    def _load_automation_state(self) -> None:
        self.auto_startup_switch.blockSignals(True)
        self.auto_startup_switch.setChecked(automation.is_autostart_enabled())
        self.auto_startup_switch.blockSignals(False)
        self.auto_sched_switch.blockSignals(True)
        self.auto_sched_switch.setChecked(automation.is_scheduled())
        self.auto_sched_switch.blockSignals(False)
        self._update_last_label()

    def _on_startup_toggled(self, checked: bool) -> None:
        if not automation.set_autostart(checked):
            self.auto_startup_switch.blockSignals(True)
            self.auto_startup_switch.setChecked(not checked)
            self.auto_startup_switch.blockSignals(False)

    def _schedule_hm(self) -> tuple[int, int]:
        try:
            h, m = self.auto_time.currentText().split(":")
            return int(h), int(m)
        except (ValueError, AttributeError):
            return 12, 0

    def _on_schedule_toggled(self, checked: bool) -> None:
        h, m = self._schedule_hm()
        if not automation.set_schedule(checked, h, m):
            self.auto_sched_switch.blockSignals(True)
            self.auto_sched_switch.setChecked(not checked)
            self.auto_sched_switch.blockSignals(False)

    def _on_schedule_time_changed(self, _text: str) -> None:
        if self.auto_sched_switch.isChecked():
            h, m = self._schedule_hm()
            automation.set_schedule(True, h, m)

    def _update_last_label(self) -> None:
        res = automation.read_last_autoclean()
        if res:
            ts, freed = res
            text = self.tr("auto_last_result", time=ts, size=cleaner.format_bytes(freed))
        else:
            text = self.tr("auto_never")
        self.auto_last_label.setText(self.tr("auto_last") + ": " + text)

    def _export_diag(self) -> None:
        from ..core import diagnostics
        try:
            path = diagnostics.save_report()
            from . import show_info
            show_info(self, self.tr("common_info"), self.tr("diag_done", path=path), self.tr)
        except Exception:
            # 兜底：直接展示报告内容，方便手动复制
            try:
                text = diagnostics.build_report()
            except Exception as exc:
                text = str(exc)
            self._show_report_text(text)

    def _show_report_text(self, text: str) -> None:
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("diag_btn"))
        dlg.resize(560, 460)
        lay = QVBoxLayout(dlg)
        tip = QLabel(self.tr("diag_copy_tip"))
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(text)
        lay.addWidget(edit, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(self.tr("common_close"))
        close.clicked.connect(dlg.accept)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec()

    def retranslate(self) -> None:
        self.title.setText(self.tr("settings_title"))
        self.tool_title.setText(self.tr("tool_title"))
        self.overlay_btn.setText(self.tr("overlay_btn"))
        self.diag_btn.setText(self.tr("diag_btn"))
        self.subtitle.setText(self.tr("settings_subtitle"))
        self.lang_title.setText(self.tr("settings_language"))
        self.safe_title.setText(self.tr("settings_safety"))
        self.safe_desc.setText(self.tr("settings_safety_desc"))
        self.admin_title.setText(self.tr("settings_admin"))
        self.admin_hint.setText(self.tr("settings_admin_hint"))
        self.admin_btn.setText(self.tr("settings_admin_btn"))
        self.about_title.setText(self.tr("settings_about"))
        self.about_text.setText(self.tr("settings_about_text", ver=version.VERSION))
        self.auto_title.setText(self.tr("auto_clean_title"))
        self.auto_startup_name.setText(self.tr("auto_startup"))
        self.auto_startup_desc.setText(self.tr("auto_startup_desc"))
        self.auto_sched_name.setText(self.tr("auto_schedule"))
        self.auto_sched_desc.setText(self.tr("auto_schedule_desc"))
        self.auto_time_label.setText(self.tr("auto_time"))
        self._update_last_label()
        self._update_lang_buttons()
