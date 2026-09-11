import os
import math
import time
import random
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QLinearGradient, QRadialGradient, QMovie, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy, QGraphicsOpacityEffect


class HolographicOrbWidget(QWidget):
    """
    Renders an animated holographic orb using QMovie (GIF) when asset files exist,
    or a rich procedural QPainter fallback with glowing rings when assets are missing.
    """

    COLOR_PALETTES = {
        "STANDBY": (QColor(0, 240, 255), QColor(56, 189, 248), QColor(15, 23, 42)),
        "LISTENING": (QColor(16, 185, 129), QColor(0, 240, 255), QColor(6, 78, 59)),
        "THINKING": (QColor(168, 85, 247), QColor(192, 132, 252), QColor(88, 28, 135)),
        "SPEAKING": (QColor(245, 158, 11), QColor(251, 191, 36), QColor(120, 53, 15)),
        "EXECUTING": (QColor(245, 158, 11), QColor(239, 68, 68), QColor(127, 29, 29)),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "STANDBY"
        self.angle = 0.0
        self.audio_level = 0.15
        self.current_movie = None

        # Container label for QMovie
        self.movie_label = QLabel(self)
        self.movie_label.setAlignment(Qt.AlignCenter)
        self.movie_label.setAttribute(Qt.WA_TranslucentBackground, True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_animate)
        self.timer.start(40)  # 25 FPS

    def set_state(self, state: str, movie_path: str = None):
        self.state = state.upper().strip()
        if movie_path and os.path.exists(movie_path):
            if self.current_movie:
                self.current_movie.stop()
            self.current_movie = QMovie(movie_path)
            self.movie_label.setMovie(self.current_movie)
            self.current_movie.start()
            self.movie_label.show()
        else:
            if self.current_movie:
                self.current_movie.stop()
                self.current_movie = None
            self.movie_label.hide()

        self.update()

    def set_audio_level(self, level: float):
        self.audio_level = max(0.1, min(1.0, level))

    def _on_animate(self):
        self.angle += 0.04
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.movie_label.setGeometry(self.rect())

    def paintEvent(self, event):
        # Render procedural holographic orb & scanning rings if no QMovie active
        if self.current_movie and self.movie_label.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        base_radius = min(w, h) * 0.24

        c1, c2, c3 = self.COLOR_PALETTES.get(self.state, self.COLOR_PALETTES["STANDBY"])

        is_active = self.state in ("LISTENING", "SPEAKING", "EXECUTING")
        pulse_speed = 3.5 if is_active else 1.5
        pulse = 1.0 + (0.06 * math.sin(self.angle * pulse_speed)) + (self.audio_level * 0.15)
        radius = base_radius * pulse

        # 1. Outer Scanning Ring 1 (Rotating dashed arc)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle * 30)
        pen_outer = QPen(c1, 1.5, Qt.DashLine)
        painter.setPen(pen_outer)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(-radius * 1.35, -radius * 1.35, radius * 2.7, radius * 2.7))
        painter.restore()

        # 2. Outer Scanning Ring 2 (Counter-rotating tick ring)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self.angle * 45)
        pen_ring2 = QPen(c2, 1.2)
        painter.setPen(pen_ring2)
        painter.drawArc(QRectF(-radius * 1.2, -radius * 1.2, radius * 2.4, radius * 2.4), 0, 120 * 16)
        painter.drawArc(QRectF(-radius * 1.2, -radius * 1.2, radius * 2.4, radius * 2.4), 180 * 16, 100 * 16)
        painter.restore()

        # 3. Radial Glow Core
        radial = QRadialGradient(cx, cy, radius)
        c1_glow = QColor(c1)
        c1_glow.setAlpha(220)
        c2_glow = QColor(c2)
        c2_glow.setAlpha(160)
        c3_glow = QColor(c3)
        c3_glow.setAlpha(80)

        radial.setColorAt(0.0, c1_glow)
        radial.setColorAt(0.5, c2_glow)
        radial.setColorAt(0.85, c3_glow)
        radial.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setBrush(QBrush(radial))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        # 4. HUD Crosshairs and Degree Ticks
        pen_hud = QPen(QColor(0, 240, 255, 140), 1.0)
        painter.setPen(pen_hud)
        ch_len = 12
        painter.drawLine(int(cx - radius * 1.4), int(cy), int(cx - radius * 1.4 + ch_len), int(cy))
        painter.drawLine(int(cx + radius * 1.4 - ch_len), int(cy), int(cx + radius * 1.4), int(cy))
        painter.drawLine(int(cx), int(cy - radius * 1.4), int(cx), int(cy - radius * 1.4 + ch_len))
        painter.drawLine(int(cx), int(cy + radius * 1.4 - ch_len), int(cx), int(cy + radius * 1.4))


class OrbView(QWidget):
    """
    Minimalist Holographic HUD Orb View containing centered orb visualizer and fighter-jet HUD telemetry text overlays.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.asset_dir = os.path.join(os.path.dirname(__file__), "assets")
        self.orb_assets = {
            "STANDBY": os.path.join(self.asset_dir, "orb_cyan_idle.gif"),
            "LISTENING": os.path.join(self.asset_dir, "orb_cyan_listening.gif"),
            "THINKING": os.path.join(self.asset_dir, "orb_purple_thinking.gif"),
            "SPEAKING": os.path.join(self.asset_dir, "orb_orange_speaking.gif"),
            "EXECUTING": os.path.join(self.asset_dir, "orb_orange_speaking.gif"),
        }

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # 1. Central Holographic Orb Container
        self.orb_widget = HolographicOrbWidget(self)
        self.orb_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.orb_widget, stretch=1)

        # 2. Fighter-Jet Style Minimalist HUD Telemetry Overlay Bar
        hud_bar = QHBoxLayout()
        hud_bar.setContentsMargins(4, 4, 4, 4)

        self.hud_left = QLabel("CPU: --%   GPU: --%   MEM: --/--G")
        self.hud_left.setObjectName("HudTextLeft")

        self.hud_right = QLabel("PWR: --W   BAT: 100%⚡   NET: 0.0 MB/s")
        self.hud_right.setObjectName("HudTextRight")

        hud_bar.addWidget(self.hud_left)
        hud_bar.addStretch()
        hud_bar.addWidget(self.hud_right)

        layout.addLayout(hud_bar)

        self.setStyleSheet("""
            QLabel#HudTextLeft, QLabel#HudTextRight {
                color: #00FFFF;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.8px;
                background: rgba(0, 240, 255, 0.05);
                border: 1px solid rgba(0, 240, 255, 0.2);
                border-radius: 6px;
                padding: 4px 8px;
            }
        """)

    def set_active(self, active: bool):
        self.orb_widget.set_audio_level(0.6 if active else 0.15)

    def set_status(self, status: str):
        clean_status = status.upper().strip()
        movie_file = self.orb_assets.get(clean_status, self.orb_assets.get("STANDBY"))
        self.orb_widget.set_state(clean_status, movie_path=movie_file)

    def update_telemetry(self, data: dict):
        cpu_pct = data.get("cpu_pct", 0.0)
        gpu_pct = data.get("gpu_pct", 0.0)
        ram_used = data.get("ram_used_gb", 0.0)
        ram_total = data.get("ram_total_gb", 0.0)
        net_up = data.get("net_up", 0.0)
        net_down = data.get("net_down", 0.0)
        bat_pct = data.get("bat_pct", 100.0)
        is_plugged = data.get("is_plugged", True)
        pwr_str = data.get("pwr_str", "0W")

        self.hud_left.setText(f"SYS // CPU: {cpu_pct:.0f}%   GPU: {gpu_pct:.0f}%   RAM: {ram_used:.1f}/{ram_total:.0f}G")
        self.hud_right.setText(f"PWR: {pwr_str}   BAT: {bat_pct:.0f}%{'⚡' if is_plugged else ''}   NET: {net_up + net_down:.1f}M/s")
