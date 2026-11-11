# -*- coding: utf-8 -*-
"""FrameBoost 图标生成：暗色圆角底 + 蓝青渐变闪电 + 能量光晕 + 细边框."""
import base64
import io

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 512
R = 108  # 圆角半径

# ---- 背景：垂直渐变（深海军蓝 -> 近黑）----
c_top = np.array([30, 42, 58], float)   # #1E2A3A
c_bot = np.array([10, 15, 23], float)   # #0A0F17
lin = np.linspace(0, 1, S).reshape(S, 1, 1)
bg = (c_top * (1 - lin) + c_bot * lin).astype(np.uint8)
bg = np.repeat(bg, S, axis=1)

rm = Image.new("L", (S, S), 0)
ImageDraw.Draw(rm).rounded_rectangle([0, 0, S - 1, S - 1], radius=R, fill=255)
rmask = (np.array(rm) / 255.0).astype(np.float32)

img = np.zeros((S, S, 4), dtype=np.uint8)
img[..., :3] = bg
img[..., 3] = (rmask * 255).astype(np.uint8)
icon = Image.fromarray(img, "RGBA")

# ---- 中心能量光晕 ----
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
cx = cy = S // 2
for r in range(150, 0, -2):
    a = int(50 * (1 - r / 150))
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(70, 150, 255, a))
glow = glow.filter(ImageFilter.GaussianBlur(24))
icon = Image.alpha_composite(icon, glow)

# ---- 闪电（对角渐变：左上蓝 -> 右下青绿）----
bolt = [(256, 36), (104, 304), (200, 304), (156, 476), (360, 176), (272, 176)]
bmask = Image.new("L", (S, S), 0)
ImageDraw.Draw(bmask).polygon(bolt, fill=255)
bmask = bmask.filter(ImageFilter.GaussianBlur(1.2))
bm = np.array(bmask, dtype=np.float32) / 255.0

xx, yy = np.meshgrid(np.linspace(0, 1, S), np.linspace(0, 1, S))
diag = (xx + yy) / 2.0
c1 = np.array([80, 160, 255], float)   # #50A0FF
c2 = np.array([45, 212, 191], float)   # #2DD4BF
bolt_grad = (c1 * (1 - diag[..., None]) + c2 * diag[..., None]).astype(np.uint8)

bolt_img = np.zeros((S, S, 4), dtype=np.uint8)
bolt_img[..., :3] = bolt_grad
bolt_img[..., 3] = (bm * 255).astype(np.uint8)
bolt_pil = Image.fromarray(bolt_img, "RGBA")
icon = Image.alpha_composite(icon, bolt_pil)

# ---- 细边框 ----
bd = ImageDraw.Draw(icon)
bd.rounded_rectangle([5, 5, S - 6, S - 6], radius=R - 6, outline=(120, 170, 240, 140), width=5)

# ---- 保存 ----
icon256 = icon.resize((256, 256), Image.LANCZOS)
icon256.save("assets/icon.png")
icon256.save("assets/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                       (64, 64), (128, 128), (256, 256)])

# 嵌入 128px 图标为 base64，供运行时窗口图标使用（无需外部文件）
icon128 = icon.resize((128, 128), Image.LANCZOS)
buf = io.BytesIO()
icon128.save(buf, "PNG")
b64 = base64.b64encode(buf.getvalue()).decode("ascii")
code = f'''"""FrameBoost 极帧加速 — 内嵌应用图标（自动生成，请勿手改）."""

from __future__ import annotations

import base64

from PySide6.QtGui import QIcon, QPixmap

_ICON_PNG_B64 = "{b64}"


def load_icon() -> QIcon:
    """加载内嵌图标为 QIcon."""
    data = base64.b64decode(_ICON_PNG_B64)
    pm = QPixmap()
    pm.loadFromData(data, "PNG")
    return QIcon(pm)
'''
with open("app/icon_data.py", "w", encoding="utf-8") as f:
    f.write(code)

print("icon generated: assets/icon.ico, assets/icon.png, app/icon_data.py")
