"""FrameBoost 极帧加速 — 高级 CPU 频率调节对话框."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QWidget,
)

from ..core import booster
from ..i18n import Translator
from .. import theme
from . import show_error, show_info


class CpuTuningDialog(QDialog):
    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        self.tr = translator.tr
        self.setWindowTitle(self.tr("adv_title"))
        self.resize(460, 340)
        self.setStyleSheet(theme.stylesheet())
        self._build()
        self.retranslate()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        self.desc = QLabel()
        self.desc.setObjectName("muted")
        self.desc.setWordWrap(True)
        lay.addWidget(self.desc)

        self.max_label, self.max_combo = self._row(lay, [100, 90, 80, 70, 60])
        self.min_label, self.min_combo = self._row(lay, [5, 50, 100])
        self.boost_label, self.boost_combo = self._row(lay, [1, 0, 2], data=True)

        self.note = QLabel()
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

        lay.addStretch(1)

        row = QHBoxLayout()
        self.apply_btn = QPushButton()
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        self.apply_btn.clicked.connect(self._apply)
        self.reset_btn = QPushButton()
        self.reset_btn.setObjectName("ghost")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.clicked.connect(self._reset)
        self.close_btn = QPushButton()
        self.close_btn.setObjectName("ghost")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.reject)
        row.addWidget(self.apply_btn)
        row.addWidget(self.reset_btn)
        row.addStretch(1)
        row.addWidget(self.close_btn)
        lay.addLayout(row)

    def _row(self, lay: QVBoxLayout, values: list[int], data: bool = False):
        label = QLabel()
        combo = QComboBox()
        combo.setMinimumWidth(180)
        for v in values:
            combo.addItem(str(v), v)
        h = QHBoxLayout()
        h.addWidget(label, 1)
        h.addWidget(combo)
        lay.addLayout(h)
        return label, combo

    def _apply(self) -> None:
        ok = booster.set_cpu_limit(
            max_percent=int(self.max_combo.currentData()),
            min_percent=int(self.min_combo.currentData()),
            boost_mode=int(self.boost_combo.currentData()),
        )
        if ok:
            show_info(self, self.tr("common_info"), self.tr("adv_done"), self.tr)
            self.accept()
        else:
            show_error(self, self.tr("common_error"), self.tr("settings_admin"), self.tr)

    def _reset(self) -> None:
        self.max_combo.setCurrentIndex(0)   # 100
        self.min_combo.setCurrentIndex(0)   # 5
        self.boost_combo.setCurrentIndex(0)  # 启用(1)
        self._apply()

    def retranslate(self) -> None:
        self.desc.setText(self.tr("adv_desc"))
        self.note.setText(self.tr("adv_note"))
        self.apply_btn.setText(self.tr("adv_apply"))
        self.reset_btn.setText(self.tr("adv_reset"))
        self.close_btn.setText(self.tr("common_close"))
        self.max_label.setText(self.tr("adv_max"))
        self.min_label.setText(self.tr("adv_min"))
        self.boost_label.setText(self.tr("adv_boost"))
        # 重新填充下拉项（带单位/文案）
        self._fill(self.max_combo, [100, 90, 80, 70, 60],
                   [f"{v}%" for v in (100, 90, 80, 70, 60)])
        self._fill(self.min_combo, [5, 50, 100],
                   [f"{v}%" for v in (5, 50, 100)])
        self._fill(self.boost_combo, [1, 0, 2],
                   [self.tr("adv_boost_on"), self.tr("adv_boost_off"),
                    self.tr("adv_boost_aggressive")])

    @staticmethod
    def _fill(combo: QComboBox, values: list[int], labels: list[str]) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for v, lab in zip(values, labels):
            combo.addItem(lab, v)
        idx = combo.findData(current) if current is not None else 0
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
