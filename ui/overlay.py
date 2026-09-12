import sys
import os
import time
import datetime
import math
import random
import psutil

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
except Exception:
    HAS_NVML = False

from PySide6.QtCore import Qt, Signal, Slot, QObject, QPoint, QThread, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QLinearGradient, QMouseEvent, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QGraphicsDropShadowEffect,
    QSizeGrip,
    QSizePolicy,
    QStackedWidget,
)

from ui.orb_view import OrbView


class TelemetryWorker(QThread):
    """
    Background worker thread fetching live system stats & power metrics using psutil, pynvml, and WMI every second.
    """
    telemetry_updated = Signal(dict)

    def __init__(self, interval: float = 1.0):
        super().__init__()
        self.interval = interval
        self.running = True
        try:
            self._last_net_io = psutil.net_io_counters()
        except Exception:
            self._last_net_io = None
        self._last_time = time.time()

    def _get_power_draw(self, cpu_pct: float, is_plugged: bool) -> tuple[float, str]:
        """
        Delegates to tools.os_tools.get_power_draw_watts() -- the single shared
        implementation also used by the get_power_draw() LLM tool -- so the HUD
        display and the tool can never silently drift out of sync with each other.
        """
        from tools.os_tools import get_power_draw_watts
        total_watts, label, _gpu_watts = get_power_draw_watts(cpu_pct, is_plugged)
        return total_watts, label

    def run(self):
        while self.running:
            try:
                now = time.time()
                dt = max(now - self._last_time, 0.1)

                cpu_pct = psutil.cpu_percent(interval=None)

                gpu_pct = 0.0
                if HAS_NVML:
                    try:
                        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                        gpu_pct = float(util.gpu)
                    except Exception:
                        gpu_pct = 0.0

                ram = psutil.virtual_memory()
                ram_pct = ram.percent
                ram_used_gb = ram.used / (1024 ** 3)
                ram_total_gb = ram.total / (1024 ** 3)

                try:
                    disk = psutil.disk_usage("/")
                    disk_pct = disk.percent
                except Exception:
                    disk_pct = 0.0

                net_up = 0.0
                net_down = 0.0
                if self._last_net_io:
                    try:
                        net_io = psutil.net_io_counters()
                        net_up = (net_io.bytes_sent - self._last_net_io.bytes_sent) / (1024 * 1024 * dt)
                        net_down = (net_io.bytes_recv - self._last_net_io.bytes_recv) / (1024 * 1024 * dt)
                        self._last_net_io = net_io
                    except Exception:
                        pass
                self._last_time = now

                bat_pct = 100.0
                is_plugged = True
                try:
                    battery = psutil.sensors_battery()
                    if battery:
                        bat_pct = battery.percent
                        is_plugged = battery.power_plugged
                except Exception:
                    pass

                pwr_watts, pwr_str = self._get_power_draw(cpu_pct, is_plugged)

                data = {
                    "cpu_pct": max(0.0, min(100.0, cpu_pct)),
                    "gpu_pct": max(0.0, min(100.0, gpu_pct)),
                    "ram_pct": max(0.0, min(100.0, ram_pct)),
                    "ram_used_gb": ram_used_gb,
                    "ram_total_gb": ram_total_gb,
                    "disk_pct": max(0.0, min(100.0, disk_pct)),
                    "net_up": max(0.0, net_up),
                    "net_down": max(0.0, net_down),
                    "bat_pct": max(0.0, min(100.0, bat_pct)),
                    "is_plugged": is_plugged,
                    "pwr_watts": pwr_watts,
                    "pwr_str": pwr_str,
                }
                self.telemetry_updated.emit(data)
            except Exception:
                pass

            self.msleep(int(self.interval * 1000))

    def stop(self):
        self.running = False
        self.wait(1000)


class WaveformWidget(QWidget):
    """
    Real-time cyan vertical bar waveform visualizer reacting to audio energy / state.
    """

    def __init__(self, bar_count: int = 24, parent=None):
        super().__init__(parent)
        self.bar_count = bar_count
        self.levels = [0.15] * bar_count
        self.target_levels = [0.15] * bar_count
        self.is_active = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate_bars)
        self.timer.start(40)  # 25 FPS smoothness

    def set_active(self, active: bool):
        self.is_active = active

    def set_audio_level(self, level: float):
        base = max(0.1, min(1.0, level))
        for i in range(self.bar_count):
            factor = math.sin((i / self.bar_count) * math.pi)
            self.target_levels[i] = max(0.1, base * factor * random.uniform(0.7, 1.2))

    def _animate_bars(self):
        for i in range(self.bar_count):
            if self.is_active:
                if random.random() < 0.3:
                    factor = math.sin((i / self.bar_count) * math.pi)
                    self.target_levels[i] = max(0.12, random.uniform(0.2, 0.95) * factor)
            else:
                self.target_levels[i] = 0.12 + 0.08 * math.sin(time.time() * 3 + i * 0.4)

            self.levels[i] += (self.target_levels[i] - self.levels[i]) * 0.25

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        gap = 4
        total_gaps = (self.bar_count - 1) * gap
        bar_w = max(3.0, (w - total_gaps) / self.bar_count)

        gradient = QLinearGradient(0, h, 0, 0)
        gradient.setColorAt(0.0, QColor(0, 240, 255, 160))
        gradient.setColorAt(0.7, QColor(56, 189, 248, 220))
        gradient.setColorAt(1.0, QColor(168, 85, 247, 255))

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)

        for i in range(self.bar_count):
            bar_h = max(6.0, self.levels[i] * h * 0.85)
            x = i * (bar_w + gap)
            y = (h - bar_h) / 2.0
            painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), bar_w / 2.0, bar_w / 2.0)


class TelemetryCard(QFrame):
    """
    Futuristic minimalist vertical card for telemetry stats (CPU, GPU, RAM, Disk, Net, Battery, Power).
    No progress bars. Muted top label & large bold white value display.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("TelemetryCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setObjectName("CardTitle")
        self.title_lbl.setAlignment(Qt.AlignCenter)

        self.val_lbl = QLabel("—")
        self.val_lbl.setObjectName("CardVal")
        self.val_lbl.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.val_lbl)

    def set_value(self, val_str: str, pct: float = 0.0):
        self.val_lbl.setText(val_str)


class DashboardView(QWidget):
    """
    Main Dashboard layout containing waveform visualizer, telemetry stats row,
    action-only Recent Commands log, and collapsible Chat History.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 1. Central Waveform & Activation Prompt Frame
        center_frame = QFrame()
        center_frame.setObjectName("CenterFrame")
        center_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        center_layout = QVBoxLayout(center_frame)
        center_layout.setContentsMargins(12, 12, 12, 12)
        center_layout.setSpacing(8)

        self.waveform = WaveformWidget(bar_count=24)
        self.waveform.setFixedHeight(70)
        self.waveform.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        center_layout.addWidget(self.waveform)

        self.activation_prompt = QLabel("Say 'Jarvis' to activate")
        self.activation_prompt.setObjectName("ActivationPrompt")
        self.activation_prompt.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.activation_prompt)

        layout.addWidget(center_frame)

        # 2. Telemetry Minimalist Cards Row
        telemetry_layout = QHBoxLayout()
        telemetry_layout.setSpacing(6)

        self.card_cpu = TelemetryCard("CPU")
        self.card_gpu = TelemetryCard("GPU")
        self.card_ram = TelemetryCard("MEMORY")
        self.card_disk = TelemetryCard("DISK")
        self.card_net = TelemetryCard("NET")
        self.card_bat = TelemetryCard("BATTERY")
        self.card_pwr = TelemetryCard("POWER")
        self.card_claw = TelemetryCard("GATEWAY")

        telemetry_layout.addWidget(self.card_cpu)
        telemetry_layout.addWidget(self.card_gpu)
        telemetry_layout.addWidget(self.card_ram)
        telemetry_layout.addWidget(self.card_disk)
        telemetry_layout.addWidget(self.card_net)
        telemetry_layout.addWidget(self.card_bat)
        telemetry_layout.addWidget(self.card_pwr)
        telemetry_layout.addWidget(self.card_claw)

        self.card_claw.set_value("OFFLINE")

        layout.addLayout(telemetry_layout)

        # 3. Recent Commands Panel (Action-Only Log)
        recent_frame = QFrame()
        recent_frame.setObjectName("RecentFrame")
        recent_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        recent_layout = QVBoxLayout(recent_frame)
        recent_layout.setContentsMargins(12, 10, 12, 10)
        recent_layout.setSpacing(6)

        recent_header = QLabel("Recent commands")
        recent_header.setObjectName("RecentHeader")
        recent_layout.addWidget(recent_header)

        self.recent_list = QListWidget()
        self.recent_list.setObjectName("RecentList")
        self.recent_list.setFixedHeight(65)
        self.recent_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        recent_layout.addWidget(self.recent_list)

        layout.addWidget(recent_frame)

        # 4. Collapsible Chat History Panel
        self.btn_toggle_chat = QPushButton("▼ Show Chat History")
        self.btn_toggle_chat.setObjectName("ToggleChatBtn")
        self.btn_toggle_chat.setCheckable(True)
        self.btn_toggle_chat.toggled.connect(self._on_chat_toggled)
        layout.addWidget(self.btn_toggle_chat)

        self.chat_history_frame = QFrame()
        self.chat_history_frame.setObjectName("ChatFrame")
        self.chat_history_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        chat_layout = QVBoxLayout(self.chat_history_frame)
        chat_layout.setContentsMargins(10, 10, 10, 10)

        self.conversation_log = QTextEdit()
        self.conversation_log.setObjectName("ConversationLog")
        self.conversation_log.setReadOnly(True)
        self.conversation_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        chat_layout.addWidget(self.conversation_log)

        self.chat_history_frame.setVisible(False)
        layout.addWidget(self.chat_history_frame, stretch=1)

    def _on_chat_toggled(self, checked: bool):
        self.chat_history_frame.setVisible(checked)
        self.btn_toggle_chat.setText("▲ Hide Chat History" if checked else "▼ Show Chat History")

    def set_status(self, is_active: bool):
        self.waveform.set_active(is_active)

    def update_telemetry(self, data: dict):
        cpu_pct = data.get("cpu_pct", 0.0)
        gpu_pct = data.get("gpu_pct", 0.0)
        ram_used = data.get("ram_used_gb", 0.0)
        ram_total = data.get("ram_total_gb", 0.0)
        disk_pct = data.get("disk_pct", 0.0)
        net_up = data.get("net_up", 0.0)
        net_down = data.get("net_down", 0.0)
        bat_pct = data.get("bat_pct", 100.0)
        is_plugged = data.get("is_plugged", True)
        pwr_str = data.get("pwr_str", "0W")

        self.card_cpu.set_value(f"{cpu_pct:.0f}%")
        self.card_gpu.set_value(f"{gpu_pct:.0f}%")
        self.card_ram.set_value(f"{ram_used:.1f}/{ram_total:.0f}G")
        self.card_disk.set_value(f"{disk_pct:.0f}%")
        self.card_net.set_value(f"{net_up:.1f}↑ {net_down:.1f}↓")
        self.card_bat.set_value(f"{bat_pct:.0f}%{'⚡' if is_plugged else ''}")
        self.card_pwr.set_value(pwr_str)

    def add_recent_command(self, action_text: str):
        if not action_text or not action_text.strip():
            return
        time_str = datetime.datetime.now().strftime("%H:%M")
        item = QListWidgetItem(f"[{time_str}] {action_text.strip()}")
        self.recent_list.insertItem(0, item)
        if self.recent_list.count() > 8:
            self.recent_list.takeItem(self.recent_list.count() - 1)

    def add_message(self, sender: str, text: str):
        time_str = datetime.datetime.now().strftime("%H:%M:%S")
        sender_upper = sender.upper().strip()

        if sender_upper in ("YOU", "USER"):
            color = "#00F0FF"
            prefix = f"<span style='color: {color}; font-weight: bold;'>[{time_str}] YOU:</span>"
        else:
            color = "#A855F7"
            prefix = f"<span style='color: {color}; font-weight: bold;'>[{time_str}] J.A.R.V.I.S.:</span>"

        formatted_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        html_line = f"<div>{prefix} <span style='color: #F8FAFC;'>{formatted_text}</span></div><br>"
        self.conversation_log.append(html_line)


class OverlaySignals(QObject):
    """
    Thread-safe signals for updating the J.A.R.V.I.S. overlay UI from background threads.
    """
    update_status = Signal(str)
    append_message = Signal(str, str)
    add_recent_command = Signal(str)
    command_submitted = Signal(str)
    voice_toggle_clicked = Signal(bool)
    system_online_toggled = Signal(bool)
    audio_rms_updated = Signal(float)
    display_card_requested = Signal(str, str)


class JarvisOverlay(QMainWindow):
    """
    Advanced Resizable Frosted Dark Glass HUD overlay interface for J.A.R.V.I.S.
    Supports dynamic switching between Dashboard (HUD) mode and Orb Mode.
    """

    STATUS_STYLES = {
        "STANDBY": ("#94A3B8", "#1E293B", "Standby"),
        "LISTENING": ("#10B981", "#064E3B", "Listening..."),
        "LISTENING (FOLLOW-UP)": ("#10B981", "#064E3B", "Listening (Follow-Up)..."),
        "THINKING": ("#00F0FF", "#0C4A6E", "Thinking..."),
        "SPEAKING": ("#A855F7", "#581C87", "Speaking..."),
        "EXECUTING": ("#F59E0B", "#78350F", "Executing..."),
    }

    BORDER_MARGIN = 8

    def __init__(self):
        super().__init__()
        self.signals = OverlaySignals()
        self.voice_enabled = True
        self.system_online = True
        self._drag_pos = QPoint()

        self.setMouseTracking(True)

        self._init_ui()
        self._connect_signals()

        # Telemetry worker thread
        self.telemetry_worker = TelemetryWorker(interval=1.0)
        self.telemetry_worker.telemetry_updated.connect(self.update_telemetry)
        self.telemetry_worker.start()

    def _init_ui(self):
        self.setWindowTitle("J.A.R.V.I.S. HUD Interface")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(560, 780)
        self.setMinimumSize(460, 600)

        # Container Frame with frosted dark glass styling
        self.container = QFrame(self)
        self.container.setObjectName("Container")
        self.container.setMouseTracking(True)
        self.setCentralWidget(self.container)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 240, 255, 70))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        # ----------------------------------------------------
        # 1. TOP LAYOUT
        # ----------------------------------------------------
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        # Mic / Profile Icon
        self.profile_icon = QLabel("🎙️")
        self.profile_icon.setObjectName("ProfileIcon")
        self.profile_icon.setAlignment(Qt.AlignCenter)
        self.profile_icon.setFixedSize(36, 36)
        top_layout.addWidget(self.profile_icon)

        # Title & Status Subtext
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.title_lbl = QLabel("J.A.R.V.I.S.")
        self.title_lbl.setObjectName("TitleLabel")

        self.status_subtext = QLabel("Listening...")
        self.status_subtext.setObjectName("StatusSubtext")
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.status_subtext)
        top_layout.addLayout(title_box)

        top_layout.addStretch()

        # Dashboard / Orb Mode Switch Button
        self.btn_mode_toggle = QPushButton("🌐 HUD")
        self.btn_mode_toggle.setObjectName("ModeToggleBtn")
        top_layout.addWidget(self.btn_mode_toggle)

        # Interactive Online/Offline Toggle Button
        self.btn_online_toggle = QPushButton("● Online")
        self.btn_online_toggle.setObjectName("OnlineToggleBtn")
        self.btn_online_toggle.setCheckable(True)
        self.btn_online_toggle.setChecked(True)
        top_layout.addWidget(self.btn_online_toggle)

        # Window Controls
        self.btn_min = QPushButton("—")
        self.btn_min.setObjectName("WinBtn")
        self.btn_min.setFixedSize(28, 28)
        self.btn_min.clicked.connect(self.showMinimized)
        top_layout.addWidget(self.btn_min)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("CloseBtn")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.clicked.connect(self.close)
        top_layout.addWidget(self.btn_close)

        main_layout.addLayout(top_layout)

        # ----------------------------------------------------
        # 2. CENTRAL QSTACKEDWIDGET (Dashboard vs Orb Mode)
        # ----------------------------------------------------
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("CentralStackedWidget")
        self.stacked_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.dashboard_view = DashboardView(self)
        self.orb_view = OrbView(self)

        from ui.memory_manager import MemoryManagerWidget
        self.memory_view = MemoryManagerWidget(self)

        self.stacked_widget.addWidget(self.dashboard_view)  # Index 0
        self.stacked_widget.addWidget(self.orb_view)        # Index 1
        self.stacked_widget.addWidget(self.memory_view)     # Index 2

        main_layout.addWidget(self.stacked_widget, stretch=1)

        # ----------------------------------------------------
        # 3. HYBRID INPUT BAR & SIZE GRIP
        # ----------------------------------------------------
        input_box = QHBoxLayout()
        input_box.setSpacing(8)

        self.btn_voice_toggle = QPushButton("Voice: ON")
        self.btn_voice_toggle.setObjectName("VoiceToggleBtn")
        self.btn_voice_toggle.setCheckable(True)
        self.btn_voice_toggle.setChecked(True)
        input_box.addWidget(self.btn_voice_toggle)

        self.input_field = QLineEdit()
        self.input_field.setObjectName("InputField")
        self.input_field.setPlaceholderText("Type a command or message...")
        input_box.addWidget(self.input_field, stretch=1)

        self.btn_send = QPushButton("Send")
        self.btn_send.setObjectName("SendBtn")
        input_box.addWidget(self.btn_send)

        # Native Window Size Grip at bottom right
        self.size_grip = QSizeGrip(self.container)
        self.size_grip.setObjectName("SizeGrip")
        self.size_grip.setFixedSize(16, 16)
        input_box.addWidget(self.size_grip, alignment=Qt.AlignBottom | Qt.AlignRight)

        main_layout.addLayout(input_box)

        # Apply QSS
        self.setStyleSheet(self._get_stylesheet())
        self.set_status("STANDBY")

    def _get_stylesheet(self) -> str:
        return """
            QFrame#Container {
                background-color: rgba(15, 23, 42, 0.93);
                border: 1px solid rgba(0, 240, 255, 0.35);
                border-radius: 18px;
            }
            QLabel#ProfileIcon {
                background-color: rgba(0, 240, 255, 0.15);
                border: 1px solid #00F0FF;
                border-radius: 18px;
                font-size: 16px;
            }
            QLabel#TitleLabel {
                color: #00F0FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 16px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QLabel#StatusSubtext {
                color: #94A3B8;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QPushButton#ModeToggleBtn {
                background-color: rgba(0, 240, 255, 0.12);
                color: #00F0FF;
                border: 1px solid rgba(0, 240, 255, 0.4);
                border-radius: 10px;
                padding: 4px 10px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#ModeToggleBtn:hover {
                background-color: rgba(0, 240, 255, 0.25);
            }
            QPushButton#OnlineToggleBtn {
                background-color: rgba(16, 185, 129, 0.2);
                color: #10B981;
                border: 1px solid #10B981;
                border-radius: 10px;
                padding: 4px 12px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#OnlineToggleBtn:checked {
                background-color: rgba(16, 185, 129, 0.22);
                color: #10B981;
                border: 1px solid #10B981;
            }
            QPushButton#OnlineToggleBtn:not(:checked) {
                background-color: rgba(239, 68, 68, 0.2);
                color: #EF4444;
                border: 1px solid #EF4444;
            }
            QPushButton#WinBtn, QPushButton#CloseBtn {
                background-color: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton#WinBtn:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
            }
            QPushButton#CloseBtn:hover {
                background-color: #EF4444;
                color: #FFFFFF;
                border: none;
            }
            QFrame#CenterFrame {
                background-color: rgba(30, 41, 59, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QLabel#ActivationPrompt {
                color: #38BDF8;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }
            QFrame#TelemetryCard {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QLabel#CardTitle {
                color: #9CA3AF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.8px;
                text-transform: uppercase;
            }
            QLabel#CardVal {
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
            QFrame#RecentFrame {
                background-color: rgba(30, 41, 59, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QLabel#RecentHeader {
                color: #94A3B8;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QListWidget#RecentList {
                background: transparent;
                border: none;
                color: #CBD5E1;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QListWidget#RecentList::item {
                padding: 2px 0;
            }
            QPushButton#ToggleChatBtn {
                background-color: rgba(255, 255, 255, 0.05);
                color: #38BDF8;
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 8px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
                padding: 6px;
            }
            QPushButton#ToggleChatBtn:hover {
                background-color: rgba(56, 189, 248, 0.15);
            }
            QFrame#ChatFrame {
                background-color: rgba(30, 41, 59, 0.65);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QTextEdit#ConversationLog {
                background: transparent;
                border: none;
                color: #F8FAFC;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 12px;
            }
            QLineEdit#InputField {
                background-color: rgba(30, 41, 59, 0.85);
                border: 1px solid rgba(0, 240, 255, 0.3);
                border-radius: 8px;
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                padding: 8px 12px;
            }
            QLineEdit#InputField:focus {
                border: 1px solid #00F0FF;
                background-color: rgba(30, 41, 59, 0.95);
            }
            QPushButton#SendBtn {
                background-color: #00F0FF;
                color: #0F172A;
                border: none;
                border-radius: 8px;
                font-family: 'Segoe UI', sans-serif;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 16px;
            }
            QPushButton#SendBtn:hover {
                background-color: #38BDF8;
            }
            QPushButton#VoiceToggleBtn {
                background-color: rgba(16, 185, 129, 0.2);
                color: #10B981;
                border: 1px solid #10B981;
                border-radius: 8px;
                font-family: 'Segoe UI', sans-serif;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 12px;
            }
            QPushButton#VoiceToggleBtn:checked {
                background-color: rgba(16, 185, 129, 0.25);
                color: #10B981;
                border: 1px solid #10B981;
            }
            QPushButton#VoiceToggleBtn:not(:checked) {
                background-color: rgba(239, 68, 68, 0.2);
                color: #EF4444;
                border: 1px solid #EF4444;
            }
            QSizeGrip#SizeGrip {
                background: transparent;
                width: 16px;
                height: 16px;
            }
        """

    def _connect_signals(self):
        self.btn_send.clicked.connect(self._on_send_clicked)
        self.input_field.returnPressed.connect(self._on_send_clicked)
        self.btn_voice_toggle.toggled.connect(self._on_voice_toggled)
        self.btn_online_toggle.toggled.connect(self._on_online_toggled)
        self.btn_mode_toggle.clicked.connect(self.toggle_ui_mode)

        self.signals.update_status.connect(self.set_status)
        self.signals.append_message.connect(self.add_message)
        self.signals.add_recent_command.connect(self.add_recent_command)
        self.signals.audio_rms_updated.connect(self._on_audio_rms_updated)
        self.signals.display_card_requested.connect(self.show_display_card)

    def _on_audio_rms_updated(self, rms: float):
        self.dashboard_view.waveform.set_audio_level(rms)
        self.orb_view.orb_widget.set_audio_level(rms)

    @Slot(str, str)
    def show_display_card(self, title: str, markdown_content: str):
        from ui.display_card import DisplayCardModal
        modal = DisplayCardModal(title=title, markdown_content=markdown_content, parent=self)
        modal.exec()

    def toggle_ui_mode(self):
        """Switches UI layout between Dashboard HUD (0), Orb View (1), and Memory Vault (2)."""
        current_idx = self.stacked_widget.currentIndex()
        new_idx = (current_idx + 1) % 3
        self.stacked_widget.setCurrentIndex(new_idx)
        if new_idx == 0:
            self.btn_mode_toggle.setText("🌐 HUD")
        elif new_idx == 1:
            self.btn_mode_toggle.setText("🔮 Orb")
        else:
            self.btn_mode_toggle.setText("🧠 Vault")
            self.memory_view.refresh_memories()

    def _on_send_clicked(self):
        text = self.input_field.text().strip()
        if text:
            self.input_field.clear()
            self.signals.command_submitted.emit(text)

    def _on_voice_toggled(self, checked: bool):
        self.voice_enabled = checked
        text = "Voice: ON" if checked else "Voice: OFF"
        self.btn_voice_toggle.setText(text)
        self.signals.voice_toggle_clicked.emit(checked)

    def _on_online_toggled(self, checked: bool):
        self.system_online = checked
        if checked:
            self.btn_online_toggle.setText("● Online")
        else:
            self.btn_online_toggle.setText("○ Offline")
        self.signals.system_online_toggled.emit(checked)

    @Slot(dict)
    def update_telemetry(self, data: dict):
        self.dashboard_view.update_telemetry(data)
        self.orb_view.update_telemetry(data)

    @Slot(str)
    def update_openclaw_status(self, status: str):
        val = "ONLINE" if status == "CONNECTED" else ("RECONNECTING" if status == "RECONNECTING" else "OFFLINE")
        if hasattr(self.dashboard_view, "card_claw"):
            self.dashboard_view.card_claw.set_value(val)

    def set_status(self, status: str):
        clean_status = status.upper().strip()
        text_color, bg_color, subtext = self.STATUS_STYLES.get(clean_status, ("#FFFFFF", "#1E293B", status))

        self.status_subtext.setText(subtext)
        self.status_subtext.setStyleSheet(f"color: {text_color};")
        self.profile_icon.setStyleSheet(
            f"background-color: {bg_color}; border: 1px solid {text_color}; border-radius: 18px; font-size: 16px;"
        )

        is_active = clean_status in ("LISTENING", "SPEAKING", "EXECUTING")
        self.dashboard_view.set_status(is_active)
        self.orb_view.set_status(clean_status)
        self.orb_view.set_active(is_active)

    def add_recent_command(self, action_text: str):
        self.dashboard_view.add_recent_command(action_text)

    def add_message(self, sender: str, text: str):
        self.dashboard_view.add_message(sender, text)

    def closeEvent(self, event):
        if hasattr(self, 'telemetry_worker') and self.telemetry_worker:
            self.telemetry_worker.stop()
        event.accept()

    # --- Resizable & Draggable Frameless Window Handlers ---
    def _get_hit_edges(self, pos: QPoint) -> Qt.Edges:
        edges = Qt.Edge(0)
        w = self.width()
        h = self.height()
        m = self.BORDER_MARGIN

        if pos.x() <= m:
            edges |= Qt.LeftEdge
        elif pos.x() >= w - m:
            edges |= Qt.RightEdge

        if pos.y() <= m:
            edges |= Qt.TopEdge
        elif pos.y() >= h - m:
            edges |= Qt.BottomEdge

        return edges

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            edges = self._get_hit_edges(event.position().toPoint())
            if edges:
                self.windowHandle().startSystemResize(edges)
            else:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        edges = self._get_hit_edges(event.position().toPoint())
        if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            self.setCursor(QCursor(Qt.SizeFDiagCursor))
        elif edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            self.setCursor(QCursor(Qt.SizeBDiagCursor))
        elif edges in (Qt.LeftEdge, Qt.RightEdge):
            self.setCursor(QCursor(Qt.SizeHorCursor))
        elif edges in (Qt.TopEdge, Qt.BottomEdge):
            self.setCursor(QCursor(Qt.SizeVerCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))

        if event.buttons() == Qt.LeftButton and not self._drag_pos.isNull() and not edges:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = QPoint()
        self.setCursor(QCursor(Qt.ArrowCursor))
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = JarvisOverlay()
    overlay.show()
    overlay.add_message("J.A.R.V.I.S.", "HUD System Online, sir.")
    overlay.add_recent_command("Opened Notepad")
    overlay.set_status("LISTENING")
    sys.exit(app.exec())
