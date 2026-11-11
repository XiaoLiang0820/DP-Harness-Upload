"""FrameBoost 极帧加速 — 主窗口."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QStackedWidget, QButtonGroup,
)

from . import version, theme
from .core import admin
from .i18n import Translator
from .ui.boost import BoostPage
from .ui.clean import CleanPage
from .ui.disk import DiskPage
from .ui.games import GamesPage
from .ui.home import HomePage
from .ui.settings import SettingsPage
from .ui.startup import StartupPage
from .ui.overlay import OverlayWindow
from .widgets import fade_in

# 导航项：key, 图标, i18n 键
NAV = [
    ("home", "🏠", "nav_home"),
    ("clean", "🧹", "nav_clean"),
    ("boost", "🚀", "nav_boost"),
    ("games", "🎮", "nav_games"),
    ("startup", "🔌", "nav_startup"),
    ("disk", "💽", "nav_disk"),
    ("settings", "⚙️", "nav_settings"),
]
_NAV_ICON = {k: ic for k, ic, _ in NAV}
_PAGE_INDEX = {k: i for i, (k, _, _) in enumerate(NAV)}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.translator = Translator("zh")
        self.is_admin = admin.is_admin()

        self.setWindowTitle(f"{version.APP_NAME_ZH} · {version.APP_NAME} v{version.VERSION}")
        self.resize(1120, 740)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(theme.stylesheet())

        self._build()
        self.translator.changed.connect(self.on_lang_changed)

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- 侧边栏 ----
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(212)
        side_lay = QVBoxLayout(sidebar)
        side_lay.setContentsMargins(16, 24, 16, 18)
        side_lay.setSpacing(4)

        self._logo = QLabel("⚡ " + self.translator.tr("app_name"))
        self._logo.setObjectName("logo")
        self._logo.setContentsMargins(6, 0, 0, 0)
        self._tagline = QLabel(version.APP_NAME + " v" + version.VERSION)
        self._tagline.setObjectName("muted")
        self._tagline.setContentsMargins(6, 0, 0, 0)
        side_lay.addWidget(self._logo)
        side_lay.addWidget(self._tagline)
        side_lay.addSpacing(20)

        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        self._stack = QStackedWidget()

        for key, icon, _label in NAV:
            btn = QPushButton()
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, k=key: self.goto_page(k))
            self._nav_group.addButton(btn)
            self._nav_buttons[key] = btn
            side_lay.addWidget(btn)

        side_lay.addSpacing(12)
        self.side_boost_btn = QPushButton("⚡ " + self.translator.tr("home_quick_boost"))
        self.side_boost_btn.setObjectName("primary")
        self.side_boost_btn.setCursor(Qt.PointingHandCursor)
        self.side_boost_btn.clicked.connect(self._side_boost)
        side_lay.addWidget(self.side_boost_btn)
        self.side_clean_btn = QPushButton("🧹 " + self.translator.tr("home_quick_clean"))
        self.side_clean_btn.setObjectName("ghost")
        self.side_clean_btn.setCursor(Qt.PointingHandCursor)
        self.side_clean_btn.clicked.connect(lambda: self.goto_page("clean"))
        side_lay.addWidget(self.side_clean_btn)

        side_lay.addStretch(1)

        self.admin_badge = QLabel()
        self.admin_badge.setAlignment(Qt.AlignCenter)
        self.admin_badge.setWordWrap(True)
        side_lay.addWidget(self.admin_badge)

        layout.addWidget(sidebar)

        # ---- 页面容器 ----
        self.home_page = HomePage(self.translator, self)
        self.clean_page = CleanPage(self.translator, self)
        self.boost_page = BoostPage(self.translator, self)
        self.games_page = GamesPage(self.translator, self)
        self.startup_page = StartupPage(self.translator, self)
        self.disk_page = DiskPage(self.translator, self)
        self.settings_page = SettingsPage(self.translator, self)
        self.overlay = OverlayWindow(self.translator)

        for page in (self.home_page, self.clean_page, self.boost_page, self.games_page,
                     self.startup_page, self.disk_page, self.settings_page):
            self._stack.addWidget(page)
        layout.addWidget(self._stack, 1)

        self._nav_buttons["home"].setChecked(True)
        self.retranslate()

    # ------------------------------------------------------------------ #
    def goto_page(self, key: str) -> None:
        index = _PAGE_INDEX.get(key, 0)
        self._stack.setCurrentIndex(index)
        btn = self._nav_buttons.get(key)
        if btn:
            btn.setChecked(True)
        if key == "boost":
            self.boost_page.refresh_on_show()
        elif key == "settings":
            self.settings_page.refresh_on_show()
        fade_in(self._stack.currentWidget(), 220)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, "_faded", False):
            self._faded = True
            fade_in(self.centralWidget(), 340)

    def _side_boost(self) -> None:
        """侧边栏「一键加速」：切到加速页并执行加速."""
        self.goto_page("boost")
        self.boost_page.start_boost()

    def toggle_overlay(self) -> None:
        """显示/隐藏性能悬浮窗."""
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()
            self.overlay.raise_()

    def retranslate(self) -> None:
        self._logo.setText("⚡ " + self.translator.tr("app_name"))
        for key, btn in self._nav_buttons.items():
            btn.setText(f"{_NAV_ICON.get(key, '')}  {self.translator.tr(f'nav_{key}')}")
        self.side_boost_btn.setText("⚡ " + self.translator.tr("home_quick_boost"))
        self.side_clean_btn.setText("🧹 " + self.translator.tr("home_quick_clean"))
        if self.is_admin:
            self.admin_badge.setText("🛡 " + self.translator.tr("state_on"))
            self.admin_badge.setStyleSheet(
                "font-size: 11px; color: #22C55E; background: rgba(34,197,94,0.12);"
                "border-radius: 9px; padding: 6px;")
        else:
            self.admin_badge.setText("⚡ " + self.translator.tr("state_off") + " · " + self.translator.tr("settings_admin"))
            self.admin_badge.setStyleSheet(
                "font-size: 11px; color: #F59E0B; background: rgba(245,158,11,0.12);"
                "border-radius: 9px; padding: 6px;")

    def on_lang_changed(self, _lang: str) -> None:
        self.retranslate()
