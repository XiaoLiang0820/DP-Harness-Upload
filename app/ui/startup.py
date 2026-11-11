"""FrameBoost 极帧加速 — 启动项管理页."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
)

from ..core import startup
from ..i18n import Translator
from ..widgets import Card, ToggleSwitch, fade_in
from . import Page, show_info


class StartupPage(Page):
    # 启动项来源标签的 i18n 映射（core 返回的中文标签同时用作备份键，保持稳定；
    # 这里仅在显示层翻译，不改动持久化数据）
    _SOURCE_KEYS = {"用户启动": "startup_src_user", "公共启动": "startup_src_common"}

    def __init__(self, translator: Translator, main_window, parent: QWidget | None = None) -> None:
        super().__init__(translator, parent)
        self.main_window = main_window
        self._build()
        self.retranslate()
        self._load_items()

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

        self.refresh_btn = QPushButton()
        self.refresh_btn.setObjectName("ghost")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._load_items)
        root.addWidget(self.refresh_btn, 0, Qt.AlignLeft)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content_lay = QVBoxLayout(self.content)
        self.content_lay.setContentsMargins(0, 0, 8, 0)
        self.content_lay.setSpacing(10)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

    def _load_items(self) -> None:
        while self.content_lay.count():
            item = self.content_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        items = startup.list_startup_items()
        if not items:
            lbl = QLabel(self.tr("startup_empty"))
            lbl.setObjectName("hint")
            self.content_lay.addWidget(lbl)
        for it in items:
            self.content_lay.addWidget(self._make_card(it))
        self.content_lay.addStretch(1)
        fade_in(self.content, 220)

    def _make_card(self, item: dict) -> Card:
        card = Card()
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(12)

        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(item["name"])
        name.setStyleSheet("font-size: 14px; font-weight: 600;")
        cmd = QLabel(item["command"])
        cmd.setObjectName("muted")
        cmd.setWordWrap(True)
        cmd.setStyleSheet("font-size: 11px;")
        col.addWidget(name)
        col.addWidget(cmd)

        src_text = self._source_text(item.get("source", ""))
        src = QLabel(src_text)
        src.setStyleSheet(
            "font-size: 11px; color: #8B9AA9; background: #1F2A37;"
            "border-radius: 7px; padding: 2px 8px;")
        lay.addLayout(col, 1)
        lay.addWidget(src, 0, Qt.AlignVCenter)

        sw = ToggleSwitch(bool(item.get("enabled", True)))
        state = QLabel()
        state.setObjectName("statLabel")
        sw.toggled.connect(lambda checked, it=item: self._on_toggle(it, checked))
        lay.addWidget(sw, 0, Qt.AlignVCenter)
        lay.addWidget(state, 0, Qt.AlignVCenter)
        self._set_state_label(state, bool(item.get("enabled", True)))
        return card

    def _set_state_label(self, label: QLabel, enabled: bool) -> None:
        if enabled:
            label.setText(self.tr("startup_enabled"))
            label.setStyleSheet("font-size: 11px; color: #22C55E;")
        else:
            label.setText(self.tr("startup_disabled"))
            label.setStyleSheet("font-size: 11px; color: #8B9AA9;")

    def _source_text(self, source: str) -> str:
        key = self._SOURCE_KEYS.get(source)
        return self.tr(key) if key else source

    def _on_toggle(self, item: dict, checked: bool) -> None:
        ok = startup.enable_item(item) if checked else startup.disable_item(item)
        if ok:
            self._load_items()
        else:
            show_info(self, self.tr("common_info"), self.tr("startup_fail"), self.tr)
            self._load_items()

    def retranslate(self) -> None:
        self.title.setText(self.tr("startup_title"))
        self.subtitle.setText(self.tr("startup_subtitle"))
        self.refresh_btn.setText(self.tr("common_refresh"))
        self._load_items()
