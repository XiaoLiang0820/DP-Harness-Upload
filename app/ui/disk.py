"""FrameBoost 极帧加速 — 磁盘空间分析页."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QProgressBar, QScrollArea, QFrame,
)

from ..core import disk
from ..core.cleaner import format_bytes
from ..i18n import Translator
from ..widgets import TaskThread, fade_in
from . import Page


class DiskPage(Page):
    def __init__(self, translator: Translator, main_window, parent: QWidget | None = None) -> None:
        super().__init__(translator, parent)
        self.main_window = main_window
        self._build()
        self.retranslate()
        self._populate_drives()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 34, 40, 30)
        root.setSpacing(16)

        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(12)
        self.drive_combo = QComboBox()
        self.drive_combo.setFixedWidth(120)
        self.drive_combo.setCursor(Qt.PointingHandCursor)
        self.scan_btn = QPushButton()
        self.scan_btn.setObjectName("primary")
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        self.scan_btn.clicked.connect(self._start_scan)
        ctrl.addWidget(self.drive_combo)
        ctrl.addWidget(self.scan_btn)
        ctrl.addStretch(1)
        root.addLayout(ctrl)

        self.summary = QLabel()
        self.summary.setObjectName("statLabel")
        root.addWidget(self.summary)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content_lay = QVBoxLayout(self.content)
        self.content_lay.setContentsMargins(0, 0, 8, 0)
        self.content_lay.setSpacing(8)
        self.placeholder = QLabel()
        self.placeholder.setObjectName("hint")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.content_lay.addWidget(self.placeholder)
        self.content_lay.addStretch(1)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

    def _populate_drives(self) -> None:
        self.drive_combo.clear()
        for letter in "CDEFGHIJ":
            p = f"{letter}:\\"
            if os.path.isdir(p):
                self.drive_combo.addItem(f"{letter}:", p)

    def _start_scan(self) -> None:
        root = self.drive_combo.currentData()
        if not root:
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText(self.tr("disk_scanning"))
        self.progress.setVisible(True)
        self.progress.setValue(0)

        def work():
            def cb(cur, total):
                self._thread.progress.emit(cur, total)
            return disk.analyze_disk(root, cb)

        self._thread = TaskThread(work, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.result.connect(self._on_result)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_progress(self, cur: int, total: int) -> None:
        if total:
            self.progress.setValue(int(cur / total * 100))

    def _clear(self) -> None:
        while self.content_lay.count():
            item = self.content_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _on_result(self, data: dict) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText(self.tr("disk_scan"))
        self.progress.setVisible(False)
        self._clear()

        self.summary.setText(
            f"{self.tr('disk_free')}: {format_bytes(data.get('free', 0))}   "
            f"{self.tr('disk_used')}: {format_bytes(data.get('used', 0))}")

        h1 = QLabel(self.tr("disk_folders"))
        h1.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 6px;")
        self.content_lay.addWidget(h1)

        folders = data.get("folders", [])
        maxsz = max((f[2] for f in folders), default=1) or 1
        for name, path, size in folders[:24]:
            self.content_lay.addWidget(self._bar_row(name, size, maxsz))

        h2 = QLabel(self.tr("disk_large"))
        h2.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 12px;")
        self.content_lay.addWidget(h2)

        large = data.get("large_files", [])
        if not large:
            lbl = QLabel(self.tr("disk_no_data"))
            lbl.setObjectName("hint")
            self.content_lay.addWidget(lbl)
        for path, size in large[:24]:
            self.content_lay.addWidget(self._file_row(path, size))

        self.content_lay.addStretch(1)
        fade_in(self.content, 300)

    def _bar_row(self, name: str, size: int, maxsz: int) -> QFrame:
        row = QFrame()
        row.setObjectName("card")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(10)
        nl = QLabel(name)
        nl.setStyleSheet("font-size: 13px;")
        nl.setMinimumWidth(150)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(size / maxsz * 100) if maxsz else 0)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        sl = QLabel(format_bytes(size))
        sl.setObjectName("statLabel")
        sl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sl.setMinimumWidth(80)
        lay.addWidget(nl, 0)
        lay.addWidget(bar, 1)
        lay.addWidget(sl, 0)
        return row

    def _file_row(self, path: str, size: int) -> QFrame:
        row = QFrame()
        row.setObjectName("card")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(10)
        nl = QLabel(path)
        nl.setObjectName("muted")
        nl.setStyleSheet("font-size: 12px;")
        nl.setToolTip(path)
        sl = QLabel(format_bytes(size))
        sl.setObjectName("statLabel")
        sl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sl.setMinimumWidth(80)
        lay.addWidget(nl, 1)
        lay.addWidget(sl, 0)
        return row

    def _on_error(self, _msg: str) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText(self.tr("disk_scan"))
        self.progress.setVisible(False)

    def retranslate(self) -> None:
        self.title.setText(self.tr("disk_title"))
        self.subtitle.setText(self.tr("disk_subtitle"))
        self.scan_btn.setText(self.tr("disk_scan"))
        self.placeholder.setText(self.tr("disk_placeholder"))
