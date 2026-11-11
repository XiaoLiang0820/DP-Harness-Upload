"""FrameBoost 极帧加速 — 游戏专属优化页（内置四款 + 自定义游戏检测/添加）."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout,
    QScrollArea, QDialog, QFileDialog, QInputDialog,
)

from ..core import booster, device, game_library, gpu
from ..core.games import (
    GAME_ORDER, GAMES, TIPS_EN, get_game, find_game_install, is_game_running, is_exe_running,
)
from ..i18n import Translator
from ..widgets import Card, CheckBox, TaskThread
from . import Page, show_info


class GameCard(Card):
    """通用游戏卡片：内置游戏与自定义游戏共用."""

    def __init__(self, translator: Translator, exe_names: list[str], title: str = "",
                 launch_options: str = "", tips: list[str] | None = None,
                 title_resolver=None, tips_resolver=None, removable: bool = False,
                 on_remove=None, parent: QWidget | None = None) -> None:
        super().__init__(parent, hover=True)
        self.translator = translator
        self.tr = translator.tr
        self.exe_names = exe_names
        self.launch_options = launch_options
        self.title = title
        self.tips = tips or []
        self._title_resolver = title_resolver
        self._tips_resolver = tips_resolver
        self.removable = removable
        self.on_remove = on_remove
        self.install_path: str | None = None
        self.running: bool = False
        self._fso_disabled: bool = False
        self._build()
        self.retranslate()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        top = QHBoxLayout()
        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet("font-size: 17px; font-weight: 700;")
        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 9px;"
            "background: #1F2A37; color: #8B9AA9;")
        top.addWidget(self.title_lbl)
        top.addStretch(1)
        top.addWidget(self.status_lbl)
        lay.addLayout(top)

        self.path_lbl = QLabel()
        self.path_lbl.setObjectName("muted")
        self.path_lbl.setWordWrap(True)
        lay.addWidget(self.path_lbl)

        self.launch_title = QLabel()
        self.launch_title.setObjectName("statLabel")
        lay.addWidget(self.launch_title)
        self.launch_lbl = QLabel()
        self.launch_lbl.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px;"
            "color: #2DD4BF; background: #0B1017; border: 1px solid #243241;"
            "border-radius: 8px; padding: 8px 10px;")
        self.launch_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.launch_lbl.setWordWrap(True)
        lay.addWidget(self.launch_lbl)

        self.tips_title = QLabel()
        self.tips_title.setObjectName("statLabel")
        lay.addWidget(self.tips_title)
        self.tips_lbl = QLabel()
        self.tips_lbl.setObjectName("muted")
        self.tips_lbl.setWordWrap(True)
        lay.addWidget(self.tips_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.opt_btn = QPushButton()
        self.opt_btn.setObjectName("primary")
        self.opt_btn.setCursor(Qt.PointingHandCursor)
        self.opt_btn.clicked.connect(self._optimize)
        btn_row.addWidget(self.opt_btn, 1)
        self.fso_btn = QPushButton()
        self.fso_btn.setObjectName("ghost")
        self.fso_btn.setCursor(Qt.PointingHandCursor)
        self.fso_btn.clicked.connect(self._disable_fso)
        btn_row.addWidget(self.fso_btn)
        self.remove_btn = QPushButton()
        self.remove_btn.setObjectName("ghost")
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.clicked.connect(self._remove)
        btn_row.addWidget(self.remove_btn)
        lay.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    def set_status(self, install_path: str | None, running: bool) -> None:
        self.install_path = install_path
        self.running = running
        if running:
            self.status_lbl.setText(self.tr("game_running"))
            self.status_lbl.setStyleSheet(
                "font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 9px;"
                "background: rgba(34,197,94,0.18); color: #22C55E;")
        elif install_path:
            self.status_lbl.setText(self.tr("game_installed"))
            self.status_lbl.setStyleSheet(
                "font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 9px;"
                "background: rgba(61,139,255,0.18); color: #6BA8FF;")
        else:
            self.status_lbl.setText(self.tr("game_not_found"))
            self.status_lbl.setStyleSheet(
                "font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 9px;"
                "background: #1F2A37; color: #8B9AA9;")
        self.path_lbl.setText(install_path or "")

    def _optimize(self) -> None:
        self.opt_btn.setEnabled(False)
        self.opt_btn.setText(self.tr("game_optimizing"))

        def work() -> int:
            booster.free_memory()
            return booster.raise_process_priority(self.exe_names)

        self._thread = TaskThread(work, self)
        self._thread.result.connect(self._on_opt_done)
        self._thread.error.connect(self._on_opt_error)
        self._thread.start()

    def _on_opt_done(self, count: int) -> None:
        self.opt_btn.setEnabled(True)
        if count > 0:
            self.opt_btn.setText(self.tr("game_priority_hint"))
        else:
            self.opt_btn.setText(self.tr("game_not_running_hint"))

    def _on_opt_error(self, _msg: str) -> None:
        self.opt_btn.setEnabled(True)
        self.opt_btn.setText(self.tr("game_optimize"))

    def _remove(self) -> None:
        if self.on_remove:
            self.on_remove(self)

    def _disable_fso(self) -> None:
        exe = (self.install_path or "").strip()
        if not exe.lower().endswith(".exe"):
            return
        if booster.set_fullscreen_optimizations(exe, True):
            self._fso_disabled = True
            self.fso_btn.setText(self.tr("game_fso_done"))
            self.fso_btn.setEnabled(False)

    def retranslate(self) -> None:
        if self._title_resolver:
            self.title = self._title_resolver()
        if self._tips_resolver:
            self.tips = self._tips_resolver()
        self.title_lbl.setText(self.title)
        self.tips_lbl.setText("\n".join("• " + t for t in self.tips))
        self.launch_title.setText(self.tr("game_launch"))
        self.tips_title.setText(self.tr("game_tips"))
        self.opt_btn.setText(self.tr("game_optimize"))
        self.fso_btn.setText(self.tr("game_fso_done") if self._fso_disabled else self.tr("game_fso_disable"))
        self.remove_btn.setText(self.tr("games_remove"))
        if self.launch_options:
            self.launch_title.setVisible(True)
            self.launch_lbl.setVisible(True)
            self.launch_lbl.setText(self.launch_options)
        else:
            self.launch_title.setVisible(False)
            self.launch_lbl.setVisible(False)
        self.remove_btn.setVisible(self.removable)
        self.set_status(self.install_path, self.running)


class AddGamesDialog(QDialog):
    """展示检测到的游戏，勾选后添加."""

    def __init__(self, detected: list[tuple[str, str]], translator: Translator,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tr = translator.tr
        self.detected = detected
        self._checks: list[tuple[str, str, QCheckBox]] = []
        self.setWindowTitle(self.tr("games_detect_dialog_title"))
        self.resize(540, 560)
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)
        title = QLabel(self.tr("games_detect_dialog_title"))
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 8, 0)
        content_lay.setSpacing(6)
        for name, exe in self.detected:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(2, 2, 2, 2)
            h.setSpacing(10)
            cb = CheckBox()
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-size: 13px;")
            h.addWidget(cb)
            h.addWidget(name_lbl, 1)
            path_lbl = QLabel(exe)
            path_lbl.setObjectName("muted")
            path_lbl.setWordWrap(True)
            path_lbl.setStyleSheet("font-size: 11px; padding-left: 34px;")
            content_lay.addWidget(row)
            content_lay.addWidget(path_lbl)
            self._checks.append((name, exe, cb))
        content_lay.addStretch(1)
        scroll.setWidget(content)
        lay.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        add_btn = QPushButton(self.tr("games_add_selected"))
        add_btn.setObjectName("primary")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton(self.tr("common_cancel"))
        cancel_btn.setObjectName("ghost")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    def _accept(self) -> None:
        if any(cb.isChecked() for _n, _e, cb in self._checks):
            self.accept()
        else:
            self.reject()

    def selected(self) -> list[tuple[str, str]]:
        return [(n, e) for n, e, cb in self._checks if cb.isChecked()]


class GamesPage(Page):
    def __init__(self, translator: Translator, main_window, parent: QWidget | None = None) -> None:
        super().__init__(translator, parent)
        self.main_window = main_window
        self._cards: dict[str, GameCard] = {}
        self._build()
        self.retranslate()
        self._detect_all()
        self._reload_custom()
        self._load_device_hint()

        # 每 5 秒刷新「运行中」状态（只查进程，不重扫安装路径）
        self._run_timer = QTimer(self)
        self._run_timer.setInterval(5000)
        self._run_timer.timeout.connect(self._refresh_running)
        self._run_timer.start()

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

        self.device_hint = QLabel()
        self.device_hint.setObjectName("hint")
        self.device_hint.setWordWrap(True)
        root.addWidget(self.device_hint)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.detect_btn = QPushButton()
        self.detect_btn.setObjectName("primary")
        self.detect_btn.setCursor(Qt.PointingHandCursor)
        self.detect_btn.clicked.connect(self._start_detect)
        self.add_btn = QPushButton()
        self.add_btn.setObjectName("ghost")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._manual_add)
        btn_row.addWidget(self.detect_btn)
        btn_row.addWidget(self.add_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.content_lay = QVBoxLayout(scroll_content)
        self.content_lay.setContentsMargins(0, 0, 8, 0)
        self.content_lay.setSpacing(16)

        self.builtin_grid = QGridLayout()
        self.builtin_grid.setSpacing(16)
        for idx, gid in enumerate(GAME_ORDER):
            game = get_game(gid)
            card = self._make_builtin_card(game)
            self._cards[gid] = card
            self.builtin_grid.addWidget(card, idx // 2, idx % 2)
        self.content_lay.addLayout(self.builtin_grid)

        self.custom_title = QLabel()
        self.custom_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.content_lay.addWidget(self.custom_title)
        self.custom_grid = QGridLayout()
        self.custom_grid.setSpacing(16)
        self.content_lay.addLayout(self.custom_grid)
        self.content_lay.addStretch(1)

        self.scroll.setWidget(scroll_content)
        root.addWidget(self.scroll, 1)

    def _make_builtin_card(self, game) -> GameCard:
        gid = game.id

        def title_resolver(gid=gid):
            return self.tr(f"game_{gid}")

        def tips_resolver(game=game):
            lang = self.translator.lang
            return TIPS_EN.get(game.id) if lang == "en" else game.tips

        lang = self.translator.lang
        return GameCard(
            self.translator, list(game.exe_names),
            title=self.tr(f"game_{gid}"),
            launch_options=game.launch_options,
            tips=(TIPS_EN.get(game.id) if lang == "en" else game.tips),
            title_resolver=title_resolver,
            tips_resolver=tips_resolver,
        )

    def _make_custom_card(self, name: str, exe_path: str) -> GameCard:
        exe_names = [os.path.basename(exe_path)]

        def tips_resolver():
            return [self.tr("custom_tip_1"), self.tr("custom_tip_2")]

        card = GameCard(
            self.translator, exe_names,
            title=name,
            launch_options="",
            tips=[self.tr("custom_tip_1"), self.tr("custom_tip_2")],
            tips_resolver=tips_resolver,
            removable=True,
            on_remove=lambda _c: self._remove_custom(exe_path),
        )
        card.set_status(exe_path, is_exe_running(exe_names))
        return card

    # ------------------------------------------------------------------ #
    def _load_device_hint(self) -> None:
        def work():
            dev = device.detect_device()
            return {
                "dev": dev,
                "mux": device.mux_hint(dev),
                "app": device.oem_hint(dev),
                "refresh": gpu.get_refresh_rate(),
            }
        th = TaskThread(work, self)
        th.result.connect(self._on_device_hint)
        th.start()

    def _on_device_hint(self, data) -> None:
        if not data:
            return
        dev = data.get("dev") or {}
        hints = []
        if data.get("mux"):
            hints.append(self.tr("hint_mux"))
        app = data.get("app")
        oem = dev.get("oem") or ""
        if app and oem:
            hints.append(self.tr("hint_oem", oem=oem, app=app))
        hz = data.get("refresh")
        if hz and hz >= 120:
            hints.append(self.tr("hint_refresh", hz=hz))
        self.device_hint.setText("\n".join(hints))

    # ------------------------------------------------------------------ #
    def _detect_all(self) -> None:
        def work() -> dict:
            result = {}
            for gid, card in self._cards.items():
                game = get_game(gid)
                result[gid] = (find_game_install(game), is_game_running(game))
            return result

        self._thread = TaskThread(work, self)
        self._thread.result.connect(self._on_detected)
        self._thread.start()

    def _on_detected(self, result: dict) -> None:
        for gid, (path, running) in result.items():
            if gid in self._cards:
                self._cards[gid].set_status(path, running)

    def _reload_custom(self) -> None:
        while self.custom_grid.count():
            item = self.custom_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        custom = game_library.load_custom_games()
        self.custom_title.setVisible(bool(custom))
        if custom:
            for idx, g in enumerate(custom):
                card = self._make_custom_card(g.get("name", ""), g.get("exe_path", ""))
                self.custom_grid.addWidget(card, idx // 2, idx % 2)

    def _remove_custom(self, exe_path: str) -> None:
        game_library.remove_custom_game(exe_path)
        self._reload_custom()

    def _scroll_to_custom(self) -> None:
        """添加游戏后滚动到「已添加的游戏」区，给出可见反馈."""
        def _do():
            if self.custom_title.isVisible():
                self.scroll.ensureWidgetVisible(self.custom_title, 0, 50)
        QTimer.singleShot(80, _do)

    def _refresh_running(self) -> None:
        """定时刷新各游戏「运行中」状态（只查进程，不重扫安装路径）."""
        for card in self._cards.values():
            if card.install_path:
                card.set_status(card.install_path, is_exe_running(card.exe_names))
        for i in range(self.custom_grid.count()):
            w = self.custom_grid.itemAt(i).widget()
            if isinstance(w, GameCard) and w.install_path:
                w.set_status(w.install_path, is_exe_running(w.exe_names))

    def _start_detect(self) -> None:
        self.detect_btn.setEnabled(False)
        self.detect_btn.setText(self.tr("games_detecting"))

        def work():
            return game_library.scan_installed_games()

        self._thread = TaskThread(work, self)
        self._thread.result.connect(self._on_detect_done)
        self._thread.error.connect(self._on_detect_error)
        self._thread.start()

    def _on_detect_done(self, detected) -> None:
        self.detect_btn.setEnabled(True)
        self.detect_btn.setText(self.tr("games_detect"))
        if not detected:
            show_info(self, self.tr("games_detect_dialog_title"),
                      self.tr("games_no_detected"), self.tr)
            return
        dlg = AddGamesDialog(detected, self.translator, self)
        if dlg.exec() == QDialog.Accepted:
            for name, exe in dlg.selected():
                game_library.add_custom_game(name, exe)
            self._reload_custom()
            self._scroll_to_custom()

    def _on_detect_error(self, _msg: str) -> None:
        self.detect_btn.setEnabled(True)
        self.detect_btn.setText(self.tr("games_detect"))

    def _manual_add(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("games_pick_exe"), "", self.tr("games_exe_filter"))
        if not path:
            return
        base = os.path.splitext(os.path.basename(path))[0]
        name, ok = QInputDialog.getText(
            self, self.tr("games_name_title"), self.tr("games_name_label"), text=base)
        if not ok or not name.strip():
            return
        if not game_library.add_custom_game(name.strip(), path):
            show_info(self, self.tr("common_info"), self.tr("games_exists"), self.tr)
        self._reload_custom()
        self._scroll_to_custom()

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.title.setText(self.tr("games_title"))
        self.subtitle.setText(self.tr("games_subtitle"))
        self.detect_btn.setText(self.tr("games_detect"))
        self.add_btn.setText(self.tr("games_add"))
        self.custom_title.setText(self.tr("games_custom_title"))
        for card in self._cards.values():
            card.retranslate()
        # 自定义卡片也刷新文案
        for i in range(self.custom_grid.count()):
            w = self.custom_grid.itemAt(i).widget()
            if isinstance(w, GameCard):
                w.retranslate()
