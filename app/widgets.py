"""FrameBoost 极帧加速 — 可复用 UI 组件."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    QThread, Signal, Qt, QSize, QRectF, Property, QPropertyAnimation, QEasingCurve,
)
from PySide6.QtGui import QColor, QPainter, QFont, QPen, QPainterPath, QLinearGradient, QBrush
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QGraphicsDropShadowEffect, QSizePolicy,
)


class Card(QFrame):
    """圆角卡片容器（带柔和阴影）."""

    def __init__(self, parent: QWidget | None = None, hover: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("cardHover" if hover else "card")
        eff = QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(22)
        eff.setOffset(0, 5)
        eff.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(eff)


class StatCard(Card):
    """首页状态卡片：数值 + 标签."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)
        self.value_label = QLabel("--")
        self.value_label.setObjectName("statValue")
        self.label_label = QLabel(label)
        self.label_label.setObjectName("statLabel")
        layout.addWidget(self.value_label)
        layout.addWidget(self.label_label)


class ToggleSwitch(QWidget):
    """自定义开关：模拟 iOS 风格的切换按钮（滑块滑动动画）."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = checked
        self._pos = 1.0 if checked else 0.0
        self.setFixedSize(44, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, v: float) -> None:
        self._pos = float(v)
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        if checked == self._checked:
            return
        self._checked = checked
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()
        self.toggled.emit(checked)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        track = QRectF(0, 0, 44, 24)
        p.setBrush(QColor("#2DD4BF") if self._checked else QColor("#2A3644"))
        p.drawRoundedRect(track, 12, 12)
        x = 2 + 20 * self._pos
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, 2, 20, 20))

    def mouseReleaseEvent(self, _event) -> None:
        if self.isEnabled():
            self.setChecked(not self._checked)


class TaskThread(QThread):
    """在后台线程运行一个函数，通过信号回传结果/进度，避免界面卡顿."""

    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, fn: Callable, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.result.emit(self._fn())
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


def make_progress_callback(thread: TaskThread) -> Callable[[int, int], None]:
    """构造一个把 (current, total) 转发到线程 progress 信号的回调."""
    def _cb(cur: int, total: int) -> None:
        thread.progress.emit(cur, total)
    return _cb


class CheckBox(QWidget):
    """自绘复选框：选中时显示对勾（替代 QCheckBox 只有纯色块的问题）."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, size: int = 20, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = checked
        self._size = size
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        if checked != self._checked:
            self._checked = checked
            self.update()
            self.toggled.emit(checked)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = h = float(self._size)
        rect = QRectF(1, 1, w - 2, h - 2)
        enabled = self.isEnabled()

        if self._checked:
            bg = QColor("#3D8BFF")
            if not enabled:
                bg.setAlpha(120)
            p.setBrush(bg)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, 5, 5)
            pen = QPen(QColor("#FFFFFF" if enabled else "#B9C6D6"),
                       max(2.0, h * 0.11), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            path = QPainterPath()
            path.moveTo(w * 0.27, h * 0.52)
            path.lineTo(w * 0.44, h * 0.69)
            path.lineTo(w * 0.75, h * 0.33)
            p.drawPath(path)
        else:
            p.setBrush(QColor("#1A2430"))
            p.setPen(QPen(QColor("#2A3A4C" if enabled else "#1E2833"), 1.2))
            p.drawRoundedRect(rect, 5, 5)
        p.end()

    def mouseReleaseEvent(self, _event) -> None:
        if self.isEnabled():
            self.setChecked(not self._checked)


class RingChart(QWidget):
    """环形（甜甜圈）占比图：中心显示百分比文字，环平滑动画填充。"""

    def __init__(self, parent: QWidget | None = None, color: str = "#3D8BFF",
                 size: int = 128) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._color = QColor(color)
        self.setMinimumSize(size, size)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._anim = QPropertyAnimation(self, b"chartValue", self)
        self._anim.setDuration(650)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_val(self) -> float:
        return self._value

    def _set_val(self, v: float) -> None:
        self._value = float(v)
        self.update()

    chartValue = Property(float, _get_val, _set_val)

    def setValue(self, value: float) -> None:
        target = max(0.0, min(100.0, float(value)))
        if abs(target - self._value) < 0.05:
            return
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(target)
        self._anim.start()

    def value(self) -> float:
        return self._value

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        d = min(self.width(), self.height())
        if d <= 0:
            p.end()
            return
        thickness = max(8, d // 10)
        margin = thickness / 2.0 + 1
        rect = QRectF((self.width() - d) / 2 + margin, (self.height() - d) / 2 + margin,
                      d - 2 * margin, d - 2 * margin)

        # 背景环
        pen = QPen(QColor("#1F2A37"), thickness)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)

        # 数值环（从 12 点方向顺时针，渐变）
        if self._value > 0:
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, self._color)
            grad.setColorAt(1.0, self._color.lighter(145))
            pen2 = QPen(QBrush(grad), thickness)
            pen2.setCapStyle(Qt.RoundCap)
            p.setPen(pen2)
            p.drawArc(rect, 90 * 16, -int(self._value * 360 * 16 / 100.0))

        # 中心百分比文字
        p.setPen(QColor("#E8EEF5"))
        font = QFont(self.font())
        font.setPixelSize(max(16, int(d * 0.2)))
        font.setBold(True)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignCenter, f"{self._value:.0f}%")
        p.end()


def fade_in(widget: QWidget, duration: int = 250) -> None:
    """给组件加淡入动画；结束后移除效果，避免影响其子控件渲染."""
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def _done():
        try:
            widget.setGraphicsEffect(None)
        except Exception:
            pass

    anim.finished.connect(_done)
    widget._fade_anim = anim
    anim.start()
