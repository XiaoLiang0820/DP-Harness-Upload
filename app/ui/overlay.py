"""FrameBoost 极帧加速 — 性能悬浮窗（多风格 / 可缩放 / 可置顶）."""

from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt, QTimer, QPoint, QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QProgressBar, QPushButton,
    QGraphicsDropShadowEffect,
)

from ..core import booster, gpu
from ..i18n import Translator
from ..widgets import TaskThread

BASE_W, BASE_H = 250, 260
MIN_W, MIN_H = 170, 150

_STYLES = ("card", "minimal", "glass")

_CARD_QSS = {
    "card": ("QFrame#ovCard { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
             "stop:0 #141D28, stop:1 #0C131B); border: 1px solid #263445; border-radius: 14px; }"),
    "minimal": ("QFrame#ovCard { background: rgba(10, 15, 22, 0.55); "
                "border: none; border-radius: 10px; }"),
    "glass": ("QFrame#ovCard { background: rgba(8, 14, 22, 0.72); "
              "border: 1px solid rgba(74, 151, 255, 0.45); border-radius: 16px; }"),
}

_COLORS = {"cpu": "#4A97FF", "ram": "#2DD4BF", "gpu": "#22C55E"}

_CURSORS = {
    "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
    "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
    "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
    "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
}

_STATE_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ".",
    "FrameBoost", "overlay.json")


class OverlayWindow(QWidget):
    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        self._style = "card"
        self._pinned = True
        self._scale = 1.0
        self._drag_pos: QPoint | None = None
        self._resizing: str | None = None
        self._resize_start = QPoint()
        self._start_geo = QRect()
        self._gpu_name = ""

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setMinimumSize(MIN_W, MIN_H)
        self.resize(BASE_W, BASE_H)

        self._build()
        self.retranslate()
        self._apply_style()
        self._apply_scale()
        self._load_state()

        self._fast = QTimer(self)
        self._fast.setInterval(1200)
        self._fast.timeout.connect(self._update_fast)
        self._fast.start()
        self._slow = QTimer(self)
        self._slow.setInterval(6000)
        self._slow.timeout.connect(self._update_gpu_async)
        self._slow.start()
        self._update_fast()
        self._update_gpu_async()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        self._outer = outer

        self.card = QFrame()
        self.card.setObjectName("ovCard")
        self._shadow = QGraphicsDropShadowEffect(self.card)
        self._shadow.setBlurRadius(22)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(0, 0, 0, 120))
        self.card.setGraphicsEffect(self._shadow)

        self._inner = QVBoxLayout(self.card)
        self._inner.setContentsMargins(14, 10, 14, 12)
        self._inner.setSpacing(8)

        head = QHBoxLayout()
        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #E8EEF5;")
        self.pin_btn = self._icon_btn("📌", self._toggle_pin)
        self.style_btn = self._icon_btn("🎨", self._cycle_style)
        self.close_btn = self._icon_btn("×", self.hide)
        head.addWidget(self.title_lbl, 1)
        head.addWidget(self.pin_btn)
        head.addWidget(self.style_btn)
        head.addWidget(self.close_btn)
        self._inner.addLayout(head)

        self.cpu_val, self.cpu_sub, self.cpu_bar = self._row("cpu")
        self.ram_val, self.ram_sub, self.ram_bar = self._row("ram")
        self.gpu_val, self.gpu_sub, self.gpu_bar = self._row("gpu")
        self.proc_lbl = QLabel()
        self.proc_lbl.setStyleSheet("font-size: 12px; color: #C9D6E3;")
        self._inner.addWidget(self.proc_lbl)

        outer.addWidget(self.card)

    def _icon_btn(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(20, 20)
        btn.clicked.connect(slot)
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #8B9AA9;"
            " font-size: 12px; font-weight: 700; padding: 0; }"
            "QPushButton:hover { color: #4A97FF; }")
        return btn

    def _row(self, key: str):
        row = QHBoxLayout()
        name = QLabel(key.upper())
        name.setStyleSheet("font-size: 11px; font-weight: 700; color: #8B9AA9;")
        row.addWidget(name)
        row.addStretch(1)
        val = QLabel("--")
        val.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {_COLORS[key]};")
        row.addWidget(val)
        self._inner.addLayout(row)

        sub = QLabel("")
        sub.setStyleSheet("font-size: 10px; color: #7C8A99;")
        self._inner.addWidget(sub)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(5)
        bar.setStyleSheet(
            "QProgressBar { background: #1B2735; border: none; border-radius: 3px; }"
            f"QProgressBar::chunk {{ background: {_COLORS[key]}; border-radius: 3px; }}")
        self._inner.addWidget(bar)
        return val, sub, bar

    # ------------------------------------------------------------------ #
    # 样式 / 置顶 / 缩放
    # ------------------------------------------------------------------ #
    def _cycle_style(self) -> None:
        i = _STYLES.index(self._style) if self._style in _STYLES else 0
        self._style = _STYLES[(i + 1) % len(_STYLES)]
        self._apply_style()
        self._save_state()

    def _apply_style(self) -> None:
        self.card.setStyleSheet(_CARD_QSS.get(self._style, _CARD_QSS["card"]))
        show_bars = self._style != "minimal"
        for bar in (self.cpu_bar, self.ram_bar, self.gpu_bar):
            bar.setVisible(show_bars)
        self._shadow.setEnabled(self._style != "minimal")
        name = self.translator.tr("overlay_style_" + self._style)
        self.style_btn.setToolTip(self.translator.tr("overlay_style_tip", name=name))

    def _toggle_pin(self) -> None:
        self._pinned = not self._pinned
        self._apply_pin()
        self._save_state()

    def _apply_pin(self) -> None:
        pos = self.pos()
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self._pinned:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self.move(pos)
        self._update_pin_style()

    def _update_pin_style(self) -> None:
        color = "#4A97FF" if self._pinned else "#5A6775"
        self.pin_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {color}; font-size: 12px; font-weight: 700; padding: 0; }}"
            "QPushButton:hover { color: #4A97FF; }")
        self.pin_btn.setToolTip(self.translator.tr(
            "overlay_pin_on" if self._pinned else "overlay_pin_off"))

    def _apply_scale(self) -> None:
        s = min(self.width() / BASE_W, self.height() / BASE_H)
        s = max(0.65, min(2.6, s))
        self._scale = s
        self.title_lbl.setStyleSheet(
            f"font-size: {max(10, int(12 * s))}px; font-weight: 700; color: #E8EEF5;")
        for val in (self.cpu_val, self.ram_val, self.gpu_val):
            val.setStyleSheet(f"font-size: {max(10, int(13 * s))}px; font-weight: 700;")
        self.proc_lbl.setStyleSheet(f"font-size: {max(9, int(12 * s))}px; color: #C9D6E3;")
        self._inner.setContentsMargins(max(8, int(14 * s)), max(6, int(10 * s)),
                                       max(8, int(14 * s)), max(6, int(12 * s)))
        self._inner.setSpacing(max(2, int(8 * s)))
        for bar in (self.cpu_bar, self.ram_bar, self.gpu_bar):
            bar.setFixedHeight(max(3, int(5 * s)))
        for sub in (self.cpu_sub, self.ram_sub, self.gpu_sub):
            sub.setStyleSheet(f"font-size: {max(8, int(10 * s))}px; color: #7C8A99;")
        for btn in (self.pin_btn, self.style_btn, self.close_btn):
            btn.setFixedSize(max(16, int(20 * s)), max(16, int(20 * s)))
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; color: #8B9AA9;"
                f" font-size: {max(10, int(12 * s))}px; font-weight: 700; padding: 0; }}"
                "QPushButton:hover { color: #4A97FF; }")
        self._update_pin_style()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_scale()

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.title_lbl.setText("⚡ " + self.translator.tr("overlay_title"))
        self._apply_style()
        self._update_pin_style()

    def _update_fast(self) -> None:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            procs = len(psutil.pids())
            freq = booster.get_cpu_freq_mhz()
            self.cpu_val.setText(f"{cpu:.0f}%")
            self.cpu_bar.setValue(int(cpu))
            self.cpu_sub.setText(f"{freq / 1000:.2f} GHz" if freq else "")
            self.ram_val.setText(f"{vm.percent:.0f}%")
            self.ram_bar.setValue(int(vm.percent))
            self.ram_sub.setText(f"{vm.used / 1024**3:.1f} / {vm.total / 1024**3:.1f} GB")
            self.proc_lbl.setText(self.translator.tr("overlay_processes", n=procs))
        except Exception:
            pass

    def _update_gpu_async(self) -> None:
        def work():
            return gpu.get_gpu_stats()
        th = TaskThread(work, self)
        th.result.connect(self._on_gpu)
        th.start()

    def _on_gpu(self, data) -> None:
        if not data:
            self.gpu_val.setText("--")
            self.gpu_bar.setValue(0)
            self.gpu_sub.setText("")
            return
        name, used, total = data
        self._gpu_name = name or ""
        if total > 0:
            pct = int(used / total * 100)
            self.gpu_val.setText(f"{pct}%")
            self.gpu_bar.setValue(pct)
            self.gpu_sub.setText(f"{used / 1024**3:.1f} / {total / 1024**3:.1f} GB")
        else:
            self.gpu_val.setText("--")
            self.gpu_bar.setValue(0)
            self.gpu_sub.setText(self._gpu_name[:28])

    # ------------------------------------------------------------------ #
    # 拖动 / 缩放
    # ------------------------------------------------------------------ #
    def _edge_at(self, pos: QPoint) -> str | None:
        m = 8
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        left, right = x <= m, x >= w - m
        top, bottom = y <= m, y >= h - m
        if left and top:
            return "tl"
        if right and top:
            return "tr"
        if left and bottom:
            return "bl"
        if right and bottom:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        edge = self._edge_at(event.position().toPoint())
        if edge:
            self._resizing = edge
            self._resize_start = event.globalPosition().toPoint()
            self._start_geo = self.geometry()
            return
        self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._resizing:
            self._do_resize(event.globalPosition().toPoint())
            return
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            return
        edge = self._edge_at(event.position().toPoint())
        self.setCursor(_CURSORS.get(edge, Qt.ArrowCursor))

    def _do_resize(self, global_pos: QPoint) -> None:
        d = global_pos - self._resize_start
        g = QRect(self._start_geo)
        edge = self._resizing or ""
        if "l" in edge:
            g.setLeft(min(g.left() + d.x(), g.right() - MIN_W))
        if "r" in edge:
            g.setRight(max(g.right() + d.x(), g.left() + MIN_W))
        if "t" in edge:
            g.setTop(min(g.top() + d.y(), g.bottom() - MIN_H))
        if "b" in edge:
            g.setBottom(max(g.bottom() + d.y(), g.top() + MIN_H))
        self.setGeometry(g)

    def mouseReleaseEvent(self, _event) -> None:
        if self._resizing or self._drag_pos is not None:
            self._save_state()
        self._resizing = None
        self._drag_pos = None
        self.setCursor(Qt.ArrowCursor)

    # ------------------------------------------------------------------ #
    def _load_state(self) -> None:
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        try:
            w = int(data.get("w", BASE_W))
            h = int(data.get("h", BASE_H))
            self.resize(max(MIN_W, w), max(MIN_H, h))
            x = data.get("x")
            y = data.get("y")
            if isinstance(x, int) and isinstance(y, int):
                self.move(x, y)
            style = data.get("style")
            if style in _STYLES:
                self._style = style
                self._apply_style()
            if "pinned" in data:
                self._pinned = bool(data.get("pinned"))
                self._apply_pin()
        except Exception:
            pass

    def _save_state(self) -> None:
        try:
            folder = os.path.dirname(_STATE_FILE)
            os.makedirs(folder, exist_ok=True)
            data = {
                "w": self.width(), "h": self.height(),
                "x": self.x(), "y": self.y(),
                "style": self._style, "pinned": self._pinned,
            }
            with open(_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._fast.stop()
        self._slow.stop()
        self._save_state()
        super().closeEvent(event)
