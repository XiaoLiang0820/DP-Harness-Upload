"""FrameBoost 极帧加速 — 深色高级主题 (QSS)."""

from __future__ import annotations

# 配色
BG = "#0B1017"          # 窗口背景
SURFACE = "#121A24"     # 卡片
SURFACE_2 = "#1A2430"   # 悬浮/次级
BORDER = "#243241"
TEXT = "#E8EEF5"
MUTED = "#8B9AA9"
ACCENT = "#3D8BFF"      # 主色（科技蓝）
ACCENT_2 = "#2DD4BF"    # 辅色（青绿）
GOOD = "#22C55E"
WARN = "#F59E0B"
BAD = "#EF4444"

FONT_FAMILY = '"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif'

_QSS = f"""
* {{
    font-family: {FONT_FAMILY};
    outline: none;
}}

QMainWindow, QDialog, QWidget#root {{
    background: {BG};
    color: {TEXT};
}}

QLabel {{
    background: transparent;
    color: {TEXT};
}}

QLabel#muted {{ color: {MUTED}; }}
QLabel#pageTitle {{
    font-size: 23px; font-weight: 800; color: {TEXT};
    border-left: 3px solid {ACCENT}; padding-left: 12px;
}}
QLabel#pageSubtitle {{ font-size: 13px; color: {MUTED}; }}
QLabel#bigTitle {{ font-size: 26px; font-weight: 800; color: {TEXT}; }}
QLabel#statValue {{ font-size: 20px; font-weight: 700; color: {TEXT}; }}
QLabel#statLabel {{ font-size: 12px; color: {MUTED}; }}
QLabel#hint {{ font-size: 12px; color: {MUTED}; }}

/* ---------- 侧边栏 ---------- */
QWidget#sidebar {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
}}

QLabel#logo {{
    font-size: 17px; font-weight: 800; color: {TEXT};
}}
QLabel#logoAccent {{ color: {ACCENT}; }}

QPushButton#navBtn {{
    text-align: left;
    padding: 11px 18px;
    border: none;
    border-radius: 10px;
    background: transparent;
    color: {MUTED};
    font-size: 14px;
    font-weight: 600;
}}
QPushButton#navBtn:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#navBtn:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4A97FF, stop:1 #2DD4BF);
    color: #FFFFFF;
}}

/* ---------- 卡片 ---------- */
QFrame#card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #151E2A, stop:1 #101720);
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QFrame#cardHover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2430, stop:1 #121A24);
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    border: none;
    border-radius: 10px;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 600;
    background: {SURFACE_2};
    color: {TEXT};
}}
QPushButton:hover {{ background: #22303F; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {MUTED}; background: {SURFACE}; }}

QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {ACCENT}, stop:1 {ACCENT_2});
    color: #FFFFFF;
    font-size: 14px;
    font-weight: 700;
    padding: 12px 26px;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #4A97FF, stop:1 #36E0C9);
}}
QPushButton#primary:pressed {{ opacity: 0.9; }}
QPushButton#primary:disabled {{ background: {SURFACE_2}; color: {MUTED}; }}

QPushButton#danger {{
    background: transparent;
    border: 1px solid {BAD};
    color: {BAD};
}}
QPushButton#danger:hover {{ background: rgba(239,68,68,0.12); }}

QPushButton#ghost {{
    background: transparent;
    border: 1px solid {BORDER};
    color: {TEXT};
}}
QPushButton#ghost:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}

/* ---------- 复选框 ---------- */
QCheckBox {{ color: {TEXT}; font-size: 13px; spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border-radius: 5px;
    border: 1px solid {BORDER};
    background: {SURFACE};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ---------- 进度条 ---------- */
QProgressBar {{
    border: none;
    border-radius: 6px;
    background: {SURFACE_2};
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:1 {ACCENT_2});
}}

/* ---------- 滚动区 ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 7px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2C3A4A; border-radius: 3px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 7px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #2C3A4A; border-radius: 3px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---------- 滑块/开关 ---------- */
QSlider::groove:horizontal {{
    height: 6px; border-radius: 3px; background: {SURFACE_2};
}}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -5px 0;
    border-radius: 8px; background: {ACCENT};
}}

/* ---------- 输入框 ---------- */
QLineEdit, QTextEdit {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    color: {TEXT};
    font-size: 13px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QComboBox {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 5px 10px;
    color: {TEXT};
    font-size: 13px;
    min-width: 80px;
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    outline: none;
}}

/* ---------- 提示框 ---------- */
QToolTip {{
    background: {SURFACE_2}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 6px; padding: 6px;
}}
"""


def stylesheet() -> str:
    return _QSS
