"""FrameBoost 极帧加速 — UI 包：页面基类与对话框辅助."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QMessageBox

from ..i18n import Translator


class Page(QWidget):
    """所有页面基类：持有翻译器，并在语言切换时自动调用 retranslate()."""

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        self.tr = translator.tr
        translator.changed.connect(self.retranslate)

    def retranslate(self) -> None:
        """子类覆盖此方法以刷新全部文案."""


def ask_confirm(parent: QWidget, title: str, text: str, tr) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Warning)
    yes = box.addButton(tr("common_ok"), QMessageBox.AcceptRole)
    box.addButton(tr("common_cancel"), QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is yes


def show_info(parent: QWidget, title: str, text: str, tr) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Information)
    box.addButton(tr("common_close"), QMessageBox.AcceptRole)
    box.exec()


def show_error(parent: QWidget, title: str, text: str, tr) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Critical)
    box.addButton(tr("common_close"), QMessageBox.AcceptRole)
    box.exec()
