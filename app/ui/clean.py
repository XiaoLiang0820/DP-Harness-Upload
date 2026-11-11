"""FrameBoost 极帧加速 — 垃圾清理页."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QProgressBar,
)

from ..core import cleaner
from ..i18n import Translator
from ..widgets import Card, CheckBox, TaskThread, ToggleSwitch
from . import Page, ask_confirm, show_info

_ICONS = {
    "target_user_temp": "🗂️",
    "target_system_temp": "🗂️",
    "target_win_update": "🔄",
    "target_thumb_cache": "🖼️",
    "target_shader_cache": "🎨",
    "target_crash_dumps": "💥",
    "target_prefetch": "⚡",
    "target_browser_cache": "🌐",
    "target_recycle_bin": "♻️",
    "target_windows_old": "📦",
    "target_wer": "🛠️",
    "target_delivery_opt": "📡",
    "target_font_cache": "🔤",
    "target_dns_cache": "📶",
}


class CleanPage(Page):
    def __init__(self, translator: Translator, main_window, parent: QWidget | None = None) -> None:
        super().__init__(translator, parent)
        self.main_window = main_window
        self.is_admin = main_window.is_admin
        self._targets = cleaner.build_targets()
        self._rows: list[tuple] = []  # (target, checkbox, name_lbl, desc_lbl, size_lbl)
        self._status_after_scan: str | None = None
        self._build()
        self.retranslate()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 34, 40, 30)
        root.setSpacing(18)

        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        # 操作栏
        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.scan_btn = QPushButton()
        self.scan_btn.setObjectName("primary")
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        self.scan_btn.clicked.connect(self._start_scan)
        self.select_all_btn = QPushButton()
        self.select_all_btn.setObjectName("ghost")
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_btn.clicked.connect(self._toggle_all)
        bar.addWidget(self.scan_btn)
        bar.addWidget(self.select_all_btn)
        bar.addStretch(1)
        self.recycle_switch = ToggleSwitch(False)
        self.recycle_switch.setChecked(False)
        self.recycle_label = QLabel()
        self.recycle_label.setObjectName("hint")
        bar.addWidget(self.recycle_label)
        bar.addWidget(self.recycle_switch)
        root.addLayout(bar)

        # 进度
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        self.status_label = QLabel()
        self.status_label.setObjectName("hint")
        root.addWidget(self.status_label)

        # 目标列表
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 8, 0)
        self.scroll_layout.setSpacing(10)
        for tgt in self._targets:
            row = self._make_row(tgt)
            self.scroll_layout.addWidget(row)
        self.scroll_layout.addStretch(1)
        self.scroll.setWidget(self.scroll_content)
        root.addWidget(self.scroll, 1)

        # 底部汇总 + 清理按钮
        footer = QHBoxLayout()
        footer.setSpacing(12)
        self.total_found = QLabel()
        self.total_found.setObjectName("statLabel")
        self.total_selected = QLabel()
        self.total_selected.setObjectName("statLabel")
        footer.addWidget(self.total_found)
        footer.addWidget(self.total_selected)
        footer.addStretch(1)
        self.clean_btn = QPushButton()
        self.clean_btn.setObjectName("primary")
        self.clean_btn.setCursor(Qt.PointingHandCursor)
        self.clean_btn.setEnabled(False)
        self.clean_btn.clicked.connect(self._start_clean)
        footer.addWidget(self.clean_btn)
        root.addLayout(footer)

    def _make_row(self, tgt) -> QFrame:
        row = Card()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        cb = CheckBox()
        usable = not tgt.need_admin or self.is_admin
        cb.setChecked(tgt.default_on and usable)
        cb.setEnabled(usable)
        cb.toggled.connect(lambda _v, t=tgt: self._update_totals())

        name_lbl = QLabel()
        name_lbl.setStyleSheet("font-weight: 600; font-size: 14px;")
        desc_lbl = QLabel()
        desc_lbl.setObjectName("muted")
        desc_lbl.setWordWrap(True)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(name_lbl)
        text_col.addWidget(desc_lbl)

        size_lbl = QLabel("—")
        size_lbl.setObjectName("statValue")
        size_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        size_lbl.setMinimumWidth(90)

        lay.addWidget(cb)
        lay.addLayout(text_col, 1)
        lay.addWidget(size_lbl)

        self._rows.append((tgt, cb, name_lbl, desc_lbl, size_lbl))
        return row

    # ------------------------------------------------------------------ #
    def _start_scan(self) -> None:
        self.scan_btn.setEnabled(False)
        self.clean_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status_label.setText(self.tr("clean_scanning"))

        self._thread = TaskThread(self._do_scan, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.result.connect(self._on_scan_done)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _do_scan(self):
        def cb(cur, total):
            self._thread.progress.emit(cur, total)
        return cleaner.scan_all(self._targets, cb)

    def _on_progress(self, cur: int, total: int) -> None:
        if total:
            self.progress.setValue(int(cur / total * 100))

    def _on_scan_done(self, _result) -> None:
        self.scan_btn.setEnabled(True)
        self.progress.setVisible(False)
        total_size = 0
        for tgt, _cb, _nl, _dl, size_lbl in self._rows:
            total_size += tgt.size
            size_lbl.setText(
                cleaner.format_bytes(tgt.size)
                + " · " + self.tr("clean_item_files", count=tgt.count)
            )
        self._total_all = total_size
        if self._status_after_scan is not None:
            self.status_label.setText(self._status_after_scan)
            self._status_after_scan = None
        else:
            self.status_label.setText(self.tr("clean_empty") if total_size == 0 else "")
        self._update_totals()
        if total_size > 0:
            self.clean_btn.setEnabled(True)

    def _update_totals(self) -> None:
        found = getattr(self, "_total_all", 0)
        selected = sum(
            t.size for t, cb, *_ in self._rows if cb.isEnabled() and cb.isChecked()
        )
        self.total_found.setText(self.tr("clean_total_found") + ": " + cleaner.format_bytes(found))
        self.total_selected.setText(
            self.tr("clean_total_selected") + ": " + cleaner.format_bytes(selected))
        self._selected_size = selected

    def _toggle_all(self) -> None:
        # 如果当前全部选中则取消，否则全选（仅启用的项）
        enabled = [cb for _t, cb, *_ in self._rows if cb.isEnabled()]
        all_checked = all(cb.isChecked() for cb in enabled)
        target = not all_checked
        for cb in enabled:
            cb.setChecked(target)
        self._update_totals()

    # ------------------------------------------------------------------ #
    def _start_clean(self) -> None:
        selected = [t for t, cb, *_ in self._rows if cb.isEnabled() and cb.isChecked()]
        if not selected:
            show_info(self, self.tr("common_info"), self.tr("clean_no_selection"), self.tr)
            return
        size = sum(t.size for t in selected)
        if not ask_confirm(
            self,
            self.tr("clean_confirm_title"),
            self.tr("clean_confirm_text", count=len(selected), size=cleaner.format_bytes(size)),
            self.tr,
        ):
            return

        to_recycle = self.recycle_switch.isChecked()
        self.clean_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status_label.setText(self.tr("clean_cleaning"))

        self._thread = TaskThread(lambda: self._do_clean(selected, to_recycle), self)
        self._thread.progress.connect(self._on_progress)
        self._thread.result.connect(self._on_clean_done)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _do_clean(self, selected, to_recycle):
        def cb(cur, total):
            self._thread.progress.emit(cur, total)
        return cleaner.clean_targets(selected, to_recycle, cb)

    def _on_clean_done(self, result) -> None:
        freed, deleted, skipped = result
        self.progress.setVisible(False)
        self.clean_btn.setEnabled(True)
        self._status_after_scan = self.tr(
            "clean_done", freed=cleaner.format_bytes(freed), skipped=skipped)
        # 清理后自动重扫，刷新剩余大小
        self._start_scan()

    def _on_error(self, msg: str) -> None:
        self.scan_btn.setEnabled(True)
        self.clean_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status_label.setText(self.tr("common_error") + ": " + msg)

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.title.setText(self.tr("clean_title"))
        self.subtitle.setText(self.tr("clean_subtitle"))
        self.scan_btn.setText(self.tr("clean_scan"))
        self.select_all_btn.setText(self.tr("clean_select_all"))
        self.clean_btn.setText(self.tr("clean_clean"))
        self.recycle_label.setText(self.tr("clean_safe_recycle"))
        for tgt, _cb, name_lbl, desc_lbl, _size_lbl in self._rows:
            name_lbl.setText(f"{_ICONS.get(tgt.key, '')}  {self.tr(tgt.key)}")
            desc = self.tr(tgt.key + "_desc")
            if tgt.need_admin and not self.is_admin:
                desc += "  ⚠ " + self.tr("settings_admin")
            desc_lbl.setText(desc)
        self._update_totals()
