"""FrameBoost 极帧加速 — 程序入口 (python -m app)."""

from __future__ import annotations

import sys


def main() -> int:
    # 静默清理模式：开机自启 / 定时任务调用，不加载 GUI，清理后直接退出
    if "--autoclean" in sys.argv:
        from .core.automation import run_autoclean_silent
        try:
            run_autoclean_silent()
        except Exception:
            pass
        return 0

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow
    from .theme import stylesheet

    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except AttributeError:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("FrameBoost")
    app.setStyleSheet(stylesheet())

    from .icon_data import load_icon
    app.setWindowIcon(load_icon())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
