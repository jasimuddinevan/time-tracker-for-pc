import csv
import json
import os
import sys
import threading
import time
from datetime import datetime, date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QTimer, QPoint, QRectF, Signal, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap, QRegion,
    QRadialGradient, QShortcut, QFont,
)
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCalendarWidget, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGraphicsDropShadowEffect,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QSizePolicy, QSpinBox, QStackedWidget,
    QRadioButton, QTableWidget, QTableWidgetItem, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from focusflow import APP_NAME, DB_PATH, Database

try:
    import winsound
except ImportError:
    winsound = None

try:
    from win11toast import toast as windows_toast
except ImportError:
    windows_toast = None


APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
LOGO_PATH = APP_DIR / "focusflow_logo.svg"
ICON_PATH = APP_DIR / "focusflow.ico"


THEMES = {
    "light": {
        "window": "#E8ECF7",
        "shell": "rgba(255,255,255,218)",
        "sidebar": "rgba(247,244,255,226)",
        "card": "rgba(255,255,255,202)",
        "card_alt": "rgba(249,248,255,214)",
        "input": "rgba(246,247,251,224)",
        "border": "rgba(255,255,255,180)",
        "text": "#172033",
        "muted": "#718096",
        "accent": "#7C3AED",
        "accent_dark": "#5B21B6",
        "accent_soft": "#EEE9FF",
        "cyan": "#0EA5E9",
        "green": "#10B981",
        "red": "#E11D48",
        "yellow": "#D97706",
        "glow": "#C4B5FD",
        "shadow": "#C9D0E1",
    },
    "dark": {
        "window": "#080C18",
        "shell": "rgba(16,23,42,232)",
        "sidebar": "rgba(18,26,49,238)",
        "card": "rgba(21,30,52,224)",
        "card_alt": "rgba(27,39,66,232)",
        "input": "rgba(14,21,40,236)",
        "border": "rgba(130,150,200,88)",
        "text": "#F8FAFC",
        "muted": "#98A9C3",
        "accent": "#A78BFA",
        "accent_dark": "#7C3AED",
        "accent_soft": "#302158",
        "cyan": "#38BDF8",
        "green": "#34D399",
        "red": "#FB7185",
        "yellow": "#FBBF24",
        "glow": "#8B5CF6",
        "shadow": "#050711",
    },
}


def palette_color(value):
    """Convert hex or rgba(...) theme values into a reliable QColor for custom painting."""
    if isinstance(value, QColor):
        return value
    if isinstance(value, str) and value.startswith("rgba(") and value.endswith(")"):
        try:
            parts = [int(part.strip()) for part in value[5:-1].split(",")]
            if len(parts) == 4:
                return QColor(*parts)
        except (TypeError, ValueError):
            pass
    return QColor(value)


class GradientBackground(QWidget):
    def __init__(self, theme="light", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_theme(self, theme):
        self.theme = theme
        self.update()

    def paintEvent(self, _event):
        colors = THEMES[self.theme]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        gradient = QLinearGradient(0, 0, rect.width(), rect.height())
        gradient.setColorAt(0.0, palette_color(colors["window"]))
        gradient.setColorAt(0.55, palette_color(colors["shell"]))
        gradient.setColorAt(1.0, palette_color(colors["window"]))
        painter.fillRect(rect, gradient)
        for x, y, radius, alpha in ((rect.width() - 180, 90, 220, 34), (120, rect.height() - 120, 260, 24)):
            glow = QRadialGradient(x, y, radius)
            glow.setColorAt(0.0, QColor(124, 58, 237, alpha))
            glow.setColorAt(1.0, QColor(124, 58, 237, 0))
            painter.fillRect(rect, glow)
        painter.end()


class ChartCanvas(QWidget):
    def __init__(self, theme="light", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.values = []
        self.labels = []
        self.color_key = "accent"
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, values, labels, color_key="accent"):
        self.values = list(values)
        self.labels = list(labels)
        self.color_key = color_key
        self.update()

    def set_theme(self, theme):
        self.theme = theme
        self.update()

    def paintEvent(self, _event):
        colors = THEMES[self.theme]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), palette_color(colors["card_alt"]))
        if not self.values:
            painter.setPen(palette_color(colors["muted"]))
            painter.drawText(self.rect(), Qt.AlignCenter, "Complete a session to start your trend")
            painter.end()
            return
        margin = 28
        chart = QRectF(margin, 16, max(1, self.width() - margin * 2), max(1, self.height() - 48))
        maximum = max(max(self.values), 1)
        grid_pen = QPen(palette_color(colors["border"]), 1)
        for index in range(4):
            y = chart.bottom() - chart.height() * index / 3
            painter.setPen(grid_pen)
            painter.drawLine(chart.left(), y, chart.right(), y)
        count = len(self.values)
        slot = chart.width() / max(count, 1)
        bar_width = min(38, max(10, slot * 0.48))
        bar_color = palette_color(colors.get(self.color_key, colors["accent"]))
        for index, value in enumerate(self.values):
            height = chart.height() * value / maximum if maximum else 0
            x = chart.left() + slot * index + (slot - bar_width) / 2
            y = chart.bottom() - height
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, bar_width, max(4, height)), 8, 8)
            painter.fillPath(path, bar_color)
            painter.setPen(palette_color(colors["muted"]))
            label = self.labels[index] if index < len(self.labels) else ""
            painter.drawText(QRectF(x - 14, chart.bottom() + 8, bar_width + 28, 22), Qt.AlignCenter, label)
        painter.end()


class GlassCard(QFrame):
    def __init__(self, theme="light", object_name="card", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName(object_name)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(22)
        self._shadow.setOffset(0, 7)
        self._shadow.setColor(self._shadow_color(theme))
        self.setGraphicsEffect(self._shadow)

    def _shadow_color(self, theme):
        return QColor(93, 72, 160, 34) if theme == "light" else QColor(0, 0, 0, 120)

    def set_theme(self, theme):
        self.theme = theme
        self._shadow.setColor(self._shadow_color(theme))


class EditTaskDialog(QDialog):
    def __init__(self, app, task, parent=None):
        super().__init__(parent)
        self.app = app
        self.task = task
        self.setWindowTitle("Edit task")
        self.setMinimumWidth(440)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        title = QLabel("Edit task")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        subtitle = QLabel("Keep the plan clear so every session has a purpose.")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        form = QFormLayout()
        form.setSpacing(12)
        self.title_edit = QLineEdit(str(task["title"]))
        self.planned = QSpinBox(); self.planned.setRange(1, 99); self.planned.setValue(int(task["planned_sessions"]))
        self.focus = QSpinBox(); self.focus.setRange(1, 180); self.focus.setValue(int(task["focus_minutes"]))
        self.priority = QComboBox(); self.priority.addItems(["Low", "Normal", "High"]); self.priority.setCurrentText(task["priority"] or "Normal")
        self.status = QComboBox(); self.status.addItems(["Not started", "In progress", "Paused", "Completed", "Archived"]); self.status.setCurrentText(task["status"] or "Not started")
        self.due = QLineEdit(str(task["due_date"] or "")); self.due.setPlaceholderText("YYYY-MM-DD")
        form.addRow("Task name", self.title_edit)
        form.addRow("Planned sessions", self.planned)
        form.addRow("Focus minutes", self.focus)
        form.addRow("Priority", self.priority)
        form.addRow("Status", self.status)
        form.addRow("Due date", self.due)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Check task", "A task name is required.")
            return
        due = self.due.text().strip()
        if due:
            try:
                datetime.strptime(due, "%Y-%m-%d")
            except ValueError:
                QMessageBox.warning(self, "Check due date", "Use YYYY-MM-DD or leave the field blank.")
                return
        self.app.db.update_task(int(self.task["id"]), title, self.planned.value(), self.focus.value(), self.priority.currentText(), self.status.currentText(), due)
        self.accept()


class NewTaskDialog(QDialog):
    def __init__(self, default_minutes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plan this task")
        self.setMinimumWidth(430)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        title = QLabel("Ready to focus?")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        subtitle = QLabel("Choose the task rhythm, then start now or save it for later.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        form = QFormLayout()
        form.setSpacing(12)
        self.focus = QSpinBox()
        self.focus.setRange(1, 180)
        self.focus.setValue(max(1, min(180, int(default_minutes))))
        self.focus.setSuffix(" min")
        form.addRow("Focus time", self.focus)
        layout.addLayout(form)
        option_title = QLabel("When should it begin?")
        option_title.setObjectName("muted")
        layout.addWidget(option_title)
        self.run_now = QRadioButton("Run now")
        self.run_now.setChecked(True)
        self.later = QRadioButton("Later")
        layout.addWidget(self.run_now)
        layout.addWidget(self.later)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        self.save_button = buttons.button(QDialogButtonBox.Save)
        self.save_button.setDefault(True)
        self.run_now.toggled.connect(self._update_save_label)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_save_label(True)

    def _update_save_label(self, run_now):
        if hasattr(self, "save_button"):
            self.save_button.setText("Start task" if run_now else "Save for later")


class WelcomeDialog(QDialog):
    def __init__(self, logo_icon=None, parent=None):
        super().__init__(parent)
        self.user_name = ""
        self.setWindowTitle("Welcome to FocusFlow")
        self.setMinimumSize(620, 500)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        colors = parent.colors() if parent is not None else {"text": "#172033", "muted": "#667085", "border": "#E4E7F0", "accent": "#7C3AED", "card": "#FFFFFF"}
        if parent is not None:
            self.setStyleSheet(parent.styleSheet() + f"""
            QLabel#onboardingTitle {{ color: {colors['text']}; font-size: 30pt; font-weight: 800; }}
            QLabel#onboardingSubtitle {{ color: {colors['muted']}; font-size: 12pt; }}
            QLabel#onboardingPrompt {{ color: {colors['text']}; font-size: 16pt; font-weight: 700; }}
            QLineEdit#onboardingName {{ background: transparent; color: {colors['text']}; border: none; border-radius: 0px; padding: 9px 3px; font-size: 20pt; selection-background-color: {colors['accent']}; }}
            QLineEdit#onboardingName:focus {{ border: none; }}
            QPushButton#onboardingContinue {{ font-size: 12pt; padding: 13px 26px; min-width: 150px; }}
            """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(58, 46, 58, 42)
        layout.setSpacing(18)
        if logo_icon and not logo_icon.isNull():
            logo = QLabel()
            logo.setAlignment(Qt.AlignCenter)
            logo.setPixmap(logo_icon.pixmap(84, 84))
            layout.addWidget(logo)
        self.title_label = QLabel("Hi there, welcome!")
        self.title_label.setObjectName("onboardingTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        self.subtitle_label = QLabel("Let’s make your focus time feel personal.")
        self.subtitle_label.setObjectName("onboardingSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)
        layout.addSpacing(12)
        self.prompt_label = QLabel("What should we call you?")
        self.prompt_label.setObjectName("onboardingPrompt")
        self.prompt_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.prompt_label)
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("onboardingName")
        self.name_edit.setPlaceholderText("Your name")
        self.name_edit.setAlignment(Qt.AlignCenter)
        self.name_edit.returnPressed.connect(self.save_name)
        layout.addWidget(self.name_edit)
        layout.addStretch(1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        self.continue_button = self.buttons.button(QDialogButtonBox.Ok)
        self.continue_button.setObjectName("onboardingContinue")
        self.continue_button.setText("Continue")
        self.continue_button.setDefault(True)
        self.buttons.accepted.connect(self.save_name)
        layout.addWidget(self.buttons)
        self.name_edit.setFocus()

    def save_name(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Add your name", "Please enter your name so FocusFlow can welcome you personally.")
            self.name_edit.setFocus()
            return
        self.user_name = name
        self.title_label.setText(f"Thank you, {name}!")
        self.subtitle_label.setText("Your focused workspace is ready. Let’s begin.")
        self.prompt_label.setVisible(False)
        self.name_edit.setVisible(False)
        self.buttons.setVisible(False)
        QTimer.singleShot(950, self.accept)


class FocusFlowQt(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database(DB_PATH)
        self.settings = self.db.get_settings()
        self.theme = self.settings.get("theme", "light") if self.settings.get("theme", "light") in THEMES else "light"
        self.current_view = "dashboard"
        self.selected_task_id = None
        self.mode = "focus"
        self.total_seconds = 25 * 60
        self.remaining_seconds = self.total_seconds
        self.running = False
        self.session_started_at = None
        self.session_deadline = None
        self._drag_pos = None
        self.user_name = self.settings.get("user_name", "").strip()
        self.setWindowTitle("FocusFlow — Pomodoro Timer")
        self.logo_icon = QIcon(str(ICON_PATH if ICON_PATH.exists() else LOGO_PATH))
        if not self.logo_icon.isNull():
            self.setWindowIcon(self.logo_icon)
        self.setMinimumSize(1180, 760)
        self.resize(1400, 880)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.background = GradientBackground(self.theme)
        self.setCentralWidget(self.background)
        self._apply_qss()
        self._build_shell()
        self._setup_shortcuts()
        self._setup_tray()
        self._reset_timer()
        self._restore_session()
        self._apply_window_mask()

    def start_first_run(self):
        if self.settings.get("onboarding_complete", "0") == "1" and self.user_name:
            return
        dialog = WelcomeDialog(self.logo_icon, self)
        if dialog.exec() == QDialog.Accepted and dialog.user_name:
            self.user_name = dialog.user_name
            self.db.save_settings({"user_name": self.user_name, "onboarding_complete": "1"})
            self.settings = self.db.get_settings()
            self.refresh_settings_summary()
            self.show_view("dashboard")

    def colors(self):
        return THEMES[self.theme]

    def _apply_window_mask(self):
        if self.width() <= 0 or self.height() <= 0:
            return
        self.clearMask()

    def resizeEvent(self, event):
        self._apply_window_mask()
        super().resizeEvent(event)

    def _apply_qss(self):
        c = self.colors()
        self.setStyleSheet(f"""
        QWidget {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 10pt; }}
        QMainWindow {{ background: transparent; }}
        QFrame#shell {{ background: {c['shell']}; border: 1px solid {c['border']}; border-radius: 0px; }}
        QFrame#sidebar {{ background: {c['sidebar']}; border: 1px solid {c['border']}; border-radius: 24px; }}
        QFrame#card, QFrame#heroCard, QFrame#glassPanel {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 20px; }}
        QFrame#heroCard {{ background: {c['card_alt']}; border: 1px solid {c['accent']}66; }}
        QLabel#brand {{ color: {c['text']}; font-size: 23pt; font-weight: 800; letter-spacing: 1px; }}
        QLabel#eyebrow {{ color: {c['accent']}; font-size: 8pt; font-weight: 800; letter-spacing: 2px; }}
        QLabel#pageTitle {{ color: {c['text']}; font-size: 24pt; font-weight: 800; }}
        QLabel#pageSubtitle, QLabel#muted {{ color: {c['muted']}; }}
        QLabel#metric {{ color: {c['text']}; font-size: 21pt; font-weight: 800; }}
        QLabel#metricCaption {{ color: {c['muted']}; font-size: 8pt; }}
        QLabel#timerMode {{ color: {c['accent']}; font-size: 10pt; font-weight: 800; letter-spacing: 2px; }}
        QLabel#timerTask {{ color: {c['text']}; font-size: 14pt; font-weight: 700; }}
        QLabel#timer {{ color: {c['text']}; font-size: 66pt; font-weight: 800; letter-spacing: 3px; }}
        QLabel#pill {{ background: {c['accent_soft']}; color: {c['accent_dark']}; border-radius: 12px; padding: 6px 10px; font-weight: 700; }}
        QPushButton {{ background: {c['card_alt']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 14px; padding: 11px 16px; font-weight: 700; }}
        QPushButton:hover {{ background: {c['accent_soft']}; border-color: {c['accent']}88; }}
        QPushButton:pressed {{ background: {c['accent_soft']}; }}
        QPushButton#primary {{ background: {c['accent']}; color: white; border: none; padding: 13px 20px; border-radius: 13px; }}
        QPushButton#primary:hover {{ background: {c['accent_dark']}; }}
        QPushButton#navButton {{ background: transparent; color: {c['muted']}; text-align: left; border: none; padding: 13px 15px; border-radius: 14px; }}
        QPushButton#navButton:hover {{ background: {c['accent_soft']}; color: {c['text']}; }}
        QPushButton#navButton:checked {{ background: {c['accent']}; color: white; }}
        QPushButton#closeButton {{ background: transparent; border: none; color: {c['muted']}; font-size: 14pt; padding: 3px 8px; }}
        QPushButton#closeButton:hover {{ background: {c['red']}22; color: {c['red']}; }}
        QLineEdit, QSpinBox, QComboBox {{ background: {c['input']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 12px; padding: 10px 12px; selection-background-color: {c['accent']}; }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
        QTableWidget {{ background: {c['input']}; alternate-background-color: {c['card_alt']}; color: {c['text']}; border: 1px solid {c['border']}; gridline-color: {c['border']}; border-radius: 16px; padding: 4px; }}
        QHeaderView::section {{ background: {c['accent_soft']}; color: {c['muted']}; border: none; padding: 10px; font-weight: 800; }}
        QTableWidget::item {{ padding: 8px; border-bottom: 1px solid {c['border']}; }}
        QTableWidget::item:focus, QAbstractItemView::item:focus {{ outline: none; border: none; }}
        QTableWidget::item:selected {{ background: {c['accent']}; color: white; }}
        QProgressBar {{ background: {c['accent_soft']}; border: none; border-radius: 7px; height: 10px; }}
        QProgressBar::chunk {{ background: {c['accent']}; border-radius: 7px; }}
        QCheckBox {{ color: {c['text']}; spacing: 8px; }}
        QCalendarWidget QWidget {{ background: transparent; color: {c['text']}; }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {c['card_alt']}; border: 1px solid {c['border']}; border-radius: 14px; padding: 6px; }}
        QCalendarWidget QToolButton {{ background: transparent; color: {c['text']}; border: none; border-radius: 10px; padding: 6px 10px; font-weight: 700; }}
        QCalendarWidget QToolButton:hover {{ background: {c['accent_soft']}; color: {c['accent_dark']}; }}
        QCalendarWidget QAbstractItemView {{ color: {c['text']}; selection-background-color: {c['accent']}; selection-color: white; background: {c['input']}; alternate-background-color: {c['card_alt']}; border: 1px solid {c['border']}; border-radius: 14px; }}
        QCalendarWidget QTableView {{ color: {c['text']}; background: {c['input']}; alternate-background-color: {c['card_alt']}; selection-background-color: {c['accent']}; selection-color: white; border: 1px solid {c['border']}; border-radius: 14px; }}
        QCalendarWidget QTableView QHeaderView::section {{ background: {c['accent_soft']}; color: {c['muted']}; border: none; padding: 6px; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
        """)

    def _apply_calendar_palette(self):
        if not hasattr(self, "calendar"):
            return
        c = self.colors()
        palette = self.calendar.palette()
        if self.theme == "light":
            base = QColor("#FFFFFF")
            text = QColor(c["text"])
            muted = QColor("#98A2B3")
        else:
            base = QColor(c["input"])
            text = QColor(c["text"])
            muted = QColor(c["muted"])
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
            palette.setColor(group, QPalette.ColorRole.Base, base)
            palette.setColor(group, QPalette.ColorRole.Window, base)
            palette.setColor(group, QPalette.ColorRole.AlternateBase, base)
            palette.setColor(group, QPalette.ColorRole.Text, muted if group == QPalette.ColorGroup.Disabled else text)
            palette.setColor(group, QPalette.ColorRole.WindowText, muted if group == QPalette.ColorGroup.Disabled else text)
            palette.setColor(group, QPalette.ColorRole.ButtonText, muted if group == QPalette.ColorGroup.Disabled else text)
            palette.setColor(group, QPalette.ColorRole.Highlight, QColor(c["accent"]))
            palette.setColor(group, QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        self.calendar.setPalette(palette)
        surface = base.name()
        self.calendar.setStyleSheet(f"""
        QCalendarWidget QWidget {{ background: {c['card']}; color: {c['text']}; }}
        QCalendarWidget QAbstractItemView, QCalendarWidget QTableView {{ background: {surface}; color: {c['text']}; alternate-background-color: {surface}; selection-background-color: {c['accent']}; selection-color: #FFFFFF; }}
        QCalendarWidget QHeaderView::section {{ background: {c['accent_soft']}; color: {c['muted']}; border: none; padding: 6px; }}
        QCalendarWidget QToolButton {{ background: transparent; color: {c['text']}; border: none; border-radius: 10px; padding: 6px 10px; font-weight: 700; }}
        """)
        for view in self.calendar.findChildren(QAbstractItemView):
            view.setPalette(palette)
            view.setAutoFillBackground(True)
            viewport = view.viewport()
            viewport_palette = viewport.palette()
            viewport_palette.setColor(QPalette.ColorRole.Base, base)
            viewport_palette.setColor(QPalette.ColorRole.Window, base)
            viewport_palette.setColor(QPalette.ColorRole.AlternateBase, base)
            viewport_palette.setColor(QPalette.ColorRole.Text, text)
            viewport_palette.setColor(QPalette.ColorRole.WindowText, text)
            viewport.setPalette(viewport_palette)
            viewport.setAutoFillBackground(True)

    def _build_shell(self):
        outer = QVBoxLayout(self.background)
        outer.setContentsMargins(0, 0, 0, 0)
        self.shell = QFrame(objectName="shell")
        self.shell_shadow = None
        self.shell.setGraphicsEffect(None)
        outer.addWidget(self.shell)
        shell_layout = QVBoxLayout(self.shell); shell_layout.setContentsMargins(18, 18, 18, 18); shell_layout.setSpacing(12)
        topbar = QHBoxLayout(); topbar.setContentsMargins(8, 0, 4, 0)
        brand_row = QHBoxLayout(); brand_row.setSpacing(10)
        brand_icon = QLabel(); brand_icon.setFixedSize(46, 46); brand_icon.setAlignment(Qt.AlignCenter)
        if not self.logo_icon.isNull():
            brand_icon.setPixmap(self.logo_icon.pixmap(42, 42))
        brand_row.addWidget(brand_icon)
        brand_box = QVBoxLayout(); brand_box.setSpacing(0)
        eyebrow = QLabel("PERSONAL PRODUCTIVITY"); eyebrow.setObjectName("eyebrow"); brand_box.addWidget(eyebrow)
        brand = QLabel("FocusFlow"); brand.setObjectName("brand"); brand_box.addWidget(brand)
        brand_row.addLayout(brand_box)
        topbar.addLayout(brand_row); topbar.addStretch()
        self.date_label = QLabel(datetime.now().strftime("%A, %B %d, %Y")); self.date_label.setObjectName("muted"); topbar.addWidget(self.date_label)
        topbar.addSpacing(18)
        self.theme_btn = QPushButton("◐  Dark mode" if self.theme == "light" else "◑  Light mode"); self.theme_btn.clicked.connect(self.toggle_theme); topbar.addWidget(self.theme_btn)
        minimize = QPushButton("—"); minimize.setObjectName("closeButton"); minimize.clicked.connect(self.showMinimized); topbar.addWidget(minimize)
        close = QPushButton("×"); close.setObjectName("closeButton"); close.clicked.connect(self.close); topbar.addWidget(close)
        shell_layout.addLayout(topbar)
        body = QHBoxLayout(); body.setSpacing(14); shell_layout.addLayout(body, 1)
        self.sidebar = QFrame(objectName="sidebar"); self.sidebar.setFixedWidth(205); body.addWidget(self.sidebar)
        side_layout = QVBoxLayout(self.sidebar); side_layout.setContentsMargins(12, 16, 12, 14); side_layout.setSpacing(6)
        nav_label = QLabel("WORKSPACE"); nav_label.setObjectName("eyebrow"); nav_label.setContentsMargins(10, 8, 0, 8); side_layout.addWidget(nav_label)
        self.nav_buttons = {}
        for key, label in (("dashboard", "Dashboard"), ("tasks", "Tasks"), ("history", "History"), ("analytics", "Analytics"), ("calendar", "Calendar"), ("settings", "Settings"), ("about", "About & Support")):
            button = QPushButton(label); button.setObjectName("navButton"); button.setCheckable(True); button.clicked.connect(lambda _checked=False, page=key: self.show_view(page)); side_layout.addWidget(button); self.nav_buttons[key] = button
        side_layout.addStretch()
        side_note = QLabel("One focused session at a time.\nSmall steps, clear progress."); side_note.setObjectName("muted"); side_note.setWordWrap(True); side_note.setContentsMargins(10, 0, 10, 0); side_layout.addWidget(side_note)
        self.content = QStackedWidget(); body.addWidget(self.content, 1)
        self.pages = {}
        for key, builder in (("dashboard", self.build_dashboard), ("tasks", self.build_tasks), ("history", self.build_history), ("analytics", self.build_analytics), ("calendar", self.build_calendar), ("settings", self.build_settings), ("about", self.build_about)):
            page = builder(); self.pages[key] = page; self.content.addWidget(page)
        self.show_view("dashboard")

    def _setup_shortcuts(self):
        self._shortcut_objects = []
        for key, sequence in (("dashboard", "Ctrl+1"), ("tasks", "Ctrl+2"), ("history", "Ctrl+3"), ("settings", "Ctrl+4"), ("analytics", "Ctrl+5"), ("calendar", "Ctrl+6"), ("about", "Ctrl+7")):
            shortcut = QShortcut(sequence, self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(lambda page=key: self.show_view(page))
            self._shortcut_objects.append(shortcut)
        guarded = (
            ("Space", self.toggle_timer),
            ("R", self.reset_timer),
            ("S", self.skip_timer),
            ("Ctrl+E", self.edit_current_task),
            ("Ctrl+Shift+S", self.start_current_task),
        )
        direct = (
            ("Ctrl+N", self.focus_new_task),
            ("Ctrl+Shift+T", self.toggle_theme),
            ("Ctrl+Shift+M", self.showMinimized),
            ("Ctrl+,", self.open_settings_dialog),
            ("F1", self.show_shortcut_reference),
            ("F5", self.refresh_all),
        )
        for sequence, callback in guarded:
            shortcut = QShortcut(sequence, self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(lambda callback=callback: self._run_guarded_shortcut(callback))
            self._shortcut_objects.append(shortcut)
        for sequence, callback in direct:
            shortcut = QShortcut(sequence, self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(callback)
            self._shortcut_objects.append(shortcut)

    def _run_guarded_shortcut(self, callback):
        """Keep single-key timer commands from hijacking text and numeric inputs."""
        if QApplication.activePopupWidget() is not None:
            return
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QSpinBox, QComboBox)):
            return
        callback()

    def _shortcut_rows(self):
        return (
            ("Space", "Start or pause the current timer"),
            ("R", "Reset the current timer"),
            ("S", "Skip the current focus or break mode"),
            ("Ctrl+N", "Open Tasks and focus the new-task field"),
            ("Ctrl+E", "Edit the selected task"),
            ("Ctrl+Shift+S", "Start the selected task"),
            ("Ctrl+Shift+T", "Toggle light and dark mode"),
            ("Ctrl+Shift+M", "Minimize FocusFlow"),
            ("Ctrl+,", "Open timer settings"),
            ("F1", "Open this shortcut reference"),
            ("F5", "Refresh tasks, history, analytics, and calendar"),
            ("Ctrl+1 … Ctrl+7", "Switch between Dashboard, Tasks, History, Settings, Analytics, Calendar, and About & Support"),
        )

    def focus_new_task(self):
        self.show_view("tasks")
        if hasattr(self, "tasks_entry"):
            self.tasks_entry.setFocus()
            self.tasks_entry.selectAll()

    def _current_task_id(self):
        return self._selected_from_table(getattr(self, "tasks_table", None)) or self._selected_from_table(getattr(self, "task_table", None))

    def edit_current_task(self):
        task_id = self._current_task_id()
        if task_id:
            self._edit_task_id(task_id)

    def start_current_task(self):
        task_id = self._current_task_id()
        if task_id:
            self.selected_task_id = task_id
            self.mode = "focus"
            self._reset_timer()
            self.show_view("dashboard")
            self.start_timer()

    def show_shortcut_reference(self):
        self.show_view("settings")

    def _tray_icon(self):
        if not self.logo_icon.isNull():
            return self.logo_icon
        pixmap = QPixmap(64, 64); pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing); painter.setBrush(QColor(self.colors()["accent"])); painter.setPen(Qt.NoPen); painter.drawRoundedRect(4, 4, 56, 56, 16, 16); painter.setBrush(Qt.NoBrush); painter.setPen(QPen(Qt.white, 4)); painter.drawEllipse(18, 18, 28, 28); painter.drawLine(32, 32, 32, 23); painter.drawLine(32, 32, 41, 37); painter.end()
        return QIcon(pixmap)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip("FocusFlow")
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("Open FocusFlow", self.show_from_tray)
        menu.addAction("Start / Resume", self.start_timer)
        menu.addAction("Pause", self.pause_timer)
        menu.addSeparator(); menu.addAction("Exit", self.close)
        self.tray.setContextMenu(menu)
        if self.settings.get("tray_enabled", "1") == "1": self.tray.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 84:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft(); event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos); event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None; super().mouseReleaseEvent(event)

    def _card(self, object_name="card"):
        card = GlassCard(self.theme, object_name); layout = QVBoxLayout(card); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(10); return card, layout

    def _heading(self, title, subtitle):
        box = QVBoxLayout(); box.setSpacing(3); label = QLabel(title); label.setObjectName("pageTitle"); box.addWidget(label); sub = QLabel(subtitle); sub.setObjectName("pageSubtitle"); box.addWidget(sub); return box

    def _time_greeting(self):
        hour = datetime.now().hour
        if hour < 12:
            moment = "Good morning"
        elif hour < 18:
            moment = "Good afternoon"
        else:
            moment = "Good evening"
        name = getattr(self, "user_name", "").strip()
        return f"{moment}, {name}!" if name else "Good focus starts here."

    def refresh_dashboard_greeting(self):
        if hasattr(self, "dashboard_greeting"):
            self.dashboard_greeting.setText(self._time_greeting())

    def _metric_card(self, value, caption):
        card, layout = self._card("card"); value_label = QLabel(value); value_label.setObjectName("metric"); cap = QLabel(caption); cap.setObjectName("metricCaption"); layout.addWidget(value_label); layout.addWidget(cap); return card, value_label

    def build_dashboard(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(10, 8, 10, 10); layout.setSpacing(16)
        heading = QVBoxLayout(); heading.setSpacing(3); self.dashboard_greeting = QLabel(); self.dashboard_greeting.setObjectName("pageTitle"); heading.addWidget(self.dashboard_greeting); subtitle = QLabel("A calm workspace for choosing one task and finishing the next small step."); subtitle.setObjectName("pageSubtitle"); heading.addWidget(subtitle); layout.addLayout(heading)
        columns = QHBoxLayout(); columns.setSpacing(14); layout.addLayout(columns, 1)
        left, left_l = self._card(); left.setMinimumWidth(250); columns.addWidget(left, 3)
        left_l.addWidget(QLabel("Today’s tasks")); hint = QLabel("Add a task, then choose its own rhythm."); hint.setObjectName("muted"); left_l.addWidget(hint)
        add_row = QHBoxLayout(); self.task_entry = QLineEdit(); self.task_entry.setPlaceholderText("What will you focus on?"); self.task_entry.returnPressed.connect(self.add_task); add_row.addWidget(self.task_entry, 1); add = QPushButton("+"); add.setObjectName("primary"); add.setFixedWidth(44); add.clicked.connect(self.add_task); add_row.addWidget(add); left_l.addLayout(add_row)
        self.task_table = self.make_task_table(); left_l.addWidget(self.task_table, 1)
        task_actions = QHBoxLayout(); self.start_selected_btn = QPushButton("Start selected"); self.start_selected_btn.setObjectName("primary"); self.start_selected_btn.clicked.connect(self.start_selected); task_actions.addWidget(self.start_selected_btn); edit = QPushButton("Edit"); edit.clicked.connect(self.edit_selected); task_actions.addWidget(edit); delete = QPushButton("Delete"); delete.clicked.connect(self.delete_selected); task_actions.addWidget(delete); left_l.addLayout(task_actions)
        hero, hero_l = self._card("heroCard"); columns.addWidget(hero, 5)
        self.mode_label = QLabel("FOCUS SESSION"); self.mode_label.setObjectName("timerMode"); self.mode_label.setAlignment(Qt.AlignCenter); hero_l.addWidget(self.mode_label)
        self.active_task = QLabel("Select a task to begin"); self.active_task.setObjectName("timerTask"); self.active_task.setAlignment(Qt.AlignCenter); hero_l.addWidget(self.active_task)
        self.timer_label = QLabel("25:00"); self.timer_label.setObjectName("timer"); self.timer_label.setAlignment(Qt.AlignCenter); hero_l.addWidget(self.timer_label, 1)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setTextVisible(False); hero_l.addWidget(self.progress)
        self.timer_status = QLabel("Ready when you are."); self.timer_status.setObjectName("muted"); self.timer_status.setAlignment(Qt.AlignCenter); hero_l.addWidget(self.timer_status)
        timer_buttons = QHBoxLayout(); self.start_btn = QPushButton("Start"); self.start_btn.setObjectName("primary"); self.start_btn.clicked.connect(self.toggle_timer); timer_buttons.addWidget(self.start_btn); pause = QPushButton("Pause"); pause.clicked.connect(self.pause_timer); timer_buttons.addWidget(pause); reset = QPushButton("Reset"); reset.clicked.connect(self.reset_timer); timer_buttons.addWidget(reset); skip = QPushButton("Skip"); skip.clicked.connect(self.skip_timer); timer_buttons.addWidget(skip); hero_l.addLayout(timer_buttons)
        right, right_l = self._card(); right.setMinimumWidth(220); columns.addWidget(right, 3)
        right_l.addWidget(QLabel("Today’s progress")); sub = QLabel("A quiet view of what you accomplished."); sub.setObjectName("muted"); right_l.addWidget(sub)
        metrics = QGridLayout(); self.metric_labels = {}
        for index, (key, caption) in enumerate((("sessions", "sessions"), ("minutes", "focused minutes"), ("remaining", "planned left"), ("rate", "completion rate"))):
            card, value_label = self._metric_card("0%" if key == "rate" else "0", caption); metrics.addWidget(card, index // 2, index % 2); self.metric_labels[key] = value_label
        right_l.addLayout(metrics)
        right_l.addWidget(QLabel("Recent activity")); self.activity_table = self.make_table(["Type", "Task", "Time"]); right_l.addWidget(self.activity_table, 1)
        self.refresh_all(); return page

    def make_task_table(self):
        table = QTableWidget(0, 5); table.setHorizontalHeaderLabels(["Task", "Done", "Focus", "Priority", "Due"]); table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setSelectionMode(QAbstractItemView.SingleSelection); table.setFocusPolicy(Qt.NoFocus); table.setAlternatingRowColors(True); table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch); table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents); table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents); table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents); table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents); table.itemSelectionChanged.connect(self.on_task_selected); table.cellDoubleClicked.connect(lambda _r, _c: self.start_selected()); return table

    def make_table(self, headers):
        table = QTableWidget(0, len(headers)); table.setHorizontalHeaderLabels(headers); table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setFocusPolicy(Qt.NoFocus); table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setAlternatingRowColors(True); table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        if len(headers) > 1: table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for index in range(2, len(headers)): table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeToContents)
        return table

    def build_tasks(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(10, 8, 10, 10); layout.addLayout(self._heading("Task library", "Plan the work before you start the clock."))
        card, card_l = self._card(); layout.addWidget(card, 1); row = QHBoxLayout(); self.tasks_entry = QLineEdit(); self.tasks_entry.setPlaceholderText("Add a focused task"); self.tasks_entry.returnPressed.connect(self.add_task_from_tasks); row.addWidget(self.tasks_entry, 1); planned = QSpinBox(); planned.setRange(1, 99); planned.setValue(4); self.tasks_planned = planned; row.addWidget(planned); focus = QSpinBox(); focus.setRange(1, 180); focus.setValue(int(self.settings.get("focus_minutes", "25"))); self.tasks_focus = focus; row.addWidget(focus); add = QPushButton("Add task"); add.setObjectName("primary"); add.clicked.connect(self.add_task_from_tasks); row.addWidget(add); card_l.addLayout(row)
        self.tasks_table = self.make_task_table(); card_l.addWidget(self.tasks_table, 1); actions = QHBoxLayout(); start = QPushButton("Start selected"); start.setObjectName("primary"); start.clicked.connect(self.start_selected_from_tasks); actions.addWidget(start); edit = QPushButton("Edit task"); edit.clicked.connect(self.edit_selected_from_tasks); actions.addWidget(edit); delete = QPushButton("Archive task"); delete.clicked.connect(self.delete_selected_from_tasks); actions.addWidget(delete); actions.addStretch(); card_l.addLayout(actions); return page

    def build_history(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(10, 8, 10, 10); header = QHBoxLayout(); header.addLayout(self._heading("Focus history", "A clear record of the sessions that moved your work forward."), 1); export = QPushButton("Export CSV"); export.clicked.connect(self.export_history); header.addWidget(export); layout.addLayout(header); card, card_l = self._card(); layout.addWidget(card, 1); self.history_table = self.make_table(["Completed", "Type", "Task", "Minutes", "Actual"]); card_l.addWidget(self.history_table, 1); return page

    def build_analytics(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(10, 8, 10, 10); header = QHBoxLayout(); header.addLayout(self._heading("Analytics", "See where your focus time is going and build a rhythm that lasts."), 1); self.analytics_range = QComboBox(); self.analytics_range.addItems(["Last 7 days", "Last 14 days", "Last 30 days"]); self.analytics_range.currentIndexChanged.connect(self.refresh_analytics); header.addWidget(self.analytics_range); layout.addLayout(header)
        metrics = QGridLayout(); self.analytics_labels = {}
        for index, (key, caption) in enumerate((("minutes", "focused minutes"), ("sessions", "focus sessions"), ("average", "average minutes"), ("best", "best day"))):
            card, value = self._metric_card("0", caption); metrics.addWidget(card, 0, index); self.analytics_labels[key] = value
        layout.addLayout(metrics); chart_card, chart_l = self._card(); chart_l.addWidget(QLabel("Daily focus trend")); self.chart = ChartCanvas(self.theme); chart_l.addWidget(self.chart, 1); layout.addWidget(chart_card, 2)
        task_card, task_l = self._card(); task_l.addWidget(QLabel("Focus by task")); self.task_chart = ChartCanvas(self.theme); self.task_chart.color_key = "cyan"; task_l.addWidget(self.task_chart, 1); layout.addWidget(task_card, 1); return page

    def build_calendar(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(10, 8, 10, 10); layout.addLayout(self._heading("Calendar history", "Browse your focus rhythm day by day.")); row = QHBoxLayout(); calendar_card, calendar_l = self._card(); self.calendar = QCalendarWidget(); self.calendar.setGridVisible(False); self.calendar.selectionChanged.connect(self.refresh_calendar_day); self._apply_calendar_palette(); calendar_l.addWidget(self.calendar); row.addWidget(calendar_card, 1); day_card, day_l = self._card(); self.calendar_day_title = QLabel("Select a date"); self.calendar_day_title.setObjectName("timerTask"); day_l.addWidget(self.calendar_day_title); self.calendar_day_summary = QLabel(""); self.calendar_day_summary.setObjectName("muted"); day_l.addWidget(self.calendar_day_summary); self.calendar_filter = QComboBox(); self.calendar_filter.addItems(["All sessions", "Focus only", "Breaks only"]); self.calendar_filter.currentIndexChanged.connect(self.refresh_calendar_day); day_l.addWidget(self.calendar_filter); self.calendar_table = self.make_table(["Time", "Type", "Task", "Minutes"]); day_l.addWidget(self.calendar_table, 1); row.addWidget(day_card, 2); layout.addLayout(row, 1); return page

    def build_settings(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(10, 8, 10, 10); layout.setSpacing(14); layout.addLayout(self._heading("Settings", "Tune your timer, notifications, sounds, appearance, and shortcuts.")); card, card_l = self._card(); layout.addWidget(card); self.settings_summary = QLabel(""); self.settings_summary.setObjectName("muted"); self.settings_summary.setWordWrap(True); card_l.addWidget(self.settings_summary); button_row = QHBoxLayout(); edit = QPushButton("Open timer settings"); edit.setObjectName("primary"); edit.clicked.connect(self.open_settings_dialog); button_row.addWidget(edit); toggle = QPushButton("Toggle theme"); toggle.clicked.connect(self.toggle_theme); button_row.addWidget(toggle); button_row.addStretch(); card_l.addLayout(button_row)
        shortcut_card, shortcut_l = self._card(); layout.addWidget(shortcut_card, 1); shortcut_l.addWidget(QLabel("Keyboard shortcuts")); shortcut_hint = QLabel("Use these commands anywhere in the app. Timer keys pause while you are typing in a field."); shortcut_hint.setObjectName("muted"); shortcut_hint.setWordWrap(True); shortcut_l.addWidget(shortcut_hint); self.shortcut_table = self.make_table(["Shortcut", "Action"]); self.shortcut_table.setSelectionMode(QAbstractItemView.NoSelection); self.shortcut_table.setFocusPolicy(Qt.NoFocus); self.shortcut_table.setRowCount(len(self._shortcut_rows()))
        for row_index, (shortcut, action) in enumerate(self._shortcut_rows()):
            self.shortcut_table.setItem(row_index, 0, QTableWidgetItem(shortcut)); self.shortcut_table.setItem(row_index, 1, QTableWidgetItem(action))
        self.shortcut_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents); self.shortcut_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); self.shortcut_table.setMinimumHeight(250); shortcut_l.addWidget(self.shortcut_table, 1); return page

    def build_about(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(10, 8, 10, 10); layout.setSpacing(14)
        layout.addLayout(self._heading("About & Support", "FocusFlow is made for calm, consistent progress."))
        intro, intro_l = self._card("heroCard"); layout.addWidget(intro)
        brand_row = QHBoxLayout(); brand_row.setSpacing(14)
        icon = QLabel(); icon.setFixedSize(64, 64); icon.setAlignment(Qt.AlignCenter)
        if not self.logo_icon.isNull(): icon.setPixmap(self.logo_icon.pixmap(58, 58))
        brand_row.addWidget(icon)
        copy = QVBoxLayout(); copy.setSpacing(3)
        title = QLabel("FocusFlow"); title.setObjectName("pageTitle"); copy.addWidget(title)
        tagline = QLabel("Personal productivity, designed for focused work."); tagline.setObjectName("pageSubtitle"); copy.addWidget(tagline)
        brand_row.addLayout(copy, 1); intro_l.addLayout(brand_row)
        intro_l.addSpacing(6)
        developer = QLabel("Developed by Jasim Uddin"); developer.setObjectName("timerTask"); intro_l.addWidget(developer)
        bio = QLabel("Web designer, Meta ad expert, and philosopher. Thank you for using FocusFlow and supporting independent software."); bio.setObjectName("muted"); bio.setWordWrap(True); intro_l.addWidget(bio)

        support, support_l = self._card(); layout.addWidget(support)
        support_l.addWidget(QLabel("Support the project"))
        support_copy = QLabel("If FocusFlow helps you protect your attention, you can support its continued development or find all of my links here."); support_copy.setObjectName("muted"); support_copy.setWordWrap(True); support_l.addWidget(support_copy)
        links = QHBoxLayout(); links.setSpacing(10)
        coffee = QPushButton("Support my work"); coffee.setObjectName("primary"); coffee.clicked.connect(lambda: self.open_external_url("https://buymeacoffee.com/jasimuddin")); links.addWidget(coffee)
        bio_button = QPushButton("Visit my links"); bio_button.clicked.connect(lambda: self.open_external_url("https://bio.link/jasimuddin")); links.addWidget(bio_button); links.addStretch(); support_l.addLayout(links)
        coffee_url = QLabel("buymeacoffee.com/jasimuddin"); coffee_url.setObjectName("muted"); support_l.addWidget(coffee_url)
        bio_url = QLabel("bio.link/jasimuddin"); bio_url.setObjectName("muted"); support_l.addWidget(bio_url)
        layout.addStretch(); return page

    def open_external_url(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def show_view(self, key):
        if key not in self.pages: return
        self.current_view = key; self.content.setCurrentWidget(self.pages[key])
        for name, button in self.nav_buttons.items(): button.setChecked(name == key)
        self.refresh_all()

    def task_rows(self):
        return self.db.conn.execute("SELECT * FROM tasks WHERE archived = 0 ORDER BY completed_sessions >= planned_sessions, created_at DESC").fetchall()

    def session_rows(self, since=None, until=None):
        query = "SELECT sessions.*, COALESCE(tasks.title, 'Unassigned') AS task_title FROM sessions LEFT JOIN tasks ON tasks.id = sessions.task_id"
        clauses = []; params = []
        if since: clauses.append("datetime(sessions.completed_at) >= datetime(?)"); params.append(since)
        if until: clauses.append("datetime(sessions.completed_at) < datetime(?)"); params.append(until)
        if clauses: query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY datetime(sessions.completed_at) DESC"
        return self.db.conn.execute(query, params).fetchall()

    def refresh_all(self):
        self.date_label.setText(datetime.now().strftime("%A, %B %d, %Y")); self.refresh_dashboard_greeting()
        self.refresh_tasks(); self.refresh_timer_ui(); self.refresh_summary(); self.refresh_history_table(); self.refresh_analytics(); self.refresh_calendar_day(); self.refresh_settings_summary()

    def refresh_tasks(self):
        rows = self.task_rows()
        for table_name in ("task_table", "tasks_table"):
            table = getattr(self, table_name, None)
            if table is None: continue
            table.setRowCount(0)
            for row in rows:
                index = table.rowCount(); table.insertRow(index)
                values = (row["title"], f"{row['completed_sessions']}/{row['planned_sessions']}", f"{row['focus_minutes']} min", row["priority"], row["due_date"] or "—")
                for col, value in enumerate(values): table.setItem(index, col, QTableWidgetItem(str(value)))
                table.item(index, 0).setData(Qt.UserRole, int(row["id"]))
        if self.selected_task_id:
            self.refresh_active_task()

    def on_task_selected(self):
        table = self.sender()
        if not table or not table.selectedItems(): return
        self.selected_task_id = table.item(table.currentRow(), 0).data(Qt.UserRole); self.refresh_active_task()

    def refresh_active_task(self):
        task = self.db.get_task(self.selected_task_id) if self.selected_task_id else None
        self.active_task.setText(task["title"] if task else ("Rest and come back refreshed" if self.mode != "focus" else "Select a task to begin"))

    def _create_task_from_prompt(self, title, planned_sessions, default_minutes):
        dialog = NewTaskDialog(default_minutes, self)
        if dialog.exec() != QDialog.Accepted:
            return False
        focus_minutes = dialog.focus.value()
        task_id = self.db.add_task(title, planned_sessions, focus_minutes)
        self.selected_task_id = task_id
        self.mode = "focus"
        self.reset_timer()
        self.refresh_all()
        if dialog.run_now.isChecked():
            self.show_view("dashboard")
            self.start_timer()
        return True

    def add_task(self):
        title = self.task_entry.text().strip()
        if not title: return
        if self._create_task_from_prompt(title, 4, int(self.settings.get("focus_minutes", "25"))):
            self.task_entry.clear()

    def add_task_from_tasks(self):
        title = self.tasks_entry.text().strip()
        if not title: return
        if self._create_task_from_prompt(title, self.tasks_planned.value(), self.tasks_focus.value()):
            self.tasks_entry.clear()

    def _selected_from_table(self, table):
        if table and table.selectedItems(): return int(table.item(table.currentRow(), 0).data(Qt.UserRole))
        return self.selected_task_id

    def start_selected(self):
        task_id = self._selected_from_table(getattr(self, "task_table", None));
        if task_id: self.selected_task_id = task_id; self.mode = "focus"; self.reset_timer(); self.start_timer()

    def start_selected_from_tasks(self):
        task_id = self._selected_from_table(getattr(self, "tasks_table", None));
        if task_id: self.selected_task_id = task_id; self.mode = "focus"; self.reset_timer(); self.show_view("dashboard"); self.start_timer()

    def edit_selected(self):
        task_id = self._selected_from_table(getattr(self, "task_table", None)); self._edit_task_id(task_id)

    def edit_selected_from_tasks(self):
        task_id = self._selected_from_table(getattr(self, "tasks_table", None)); self._edit_task_id(task_id)

    def _edit_task_id(self, task_id):
        if not task_id: return
        task = self.db.get_task(task_id); dialog = EditTaskDialog(self, task, self); dialog.exec(); self.refresh_all()

    def delete_selected(self): self._delete_task_id(self._selected_from_table(getattr(self, "task_table", None)))
    def delete_selected_from_tasks(self): self._delete_task_id(self._selected_from_table(getattr(self, "tasks_table", None)))

    def _delete_task_id(self, task_id):
        if not task_id: return
        task = self.db.get_task(task_id)
        if task and QMessageBox.question(self, "Archive task", f"Archive ‘{task['title']}’?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.db.archive_task(task_id); self.selected_task_id = None; self.reset_timer(); self.refresh_all()

    def _duration_for_mode(self):
        if self.mode == "focus":
            task = self.db.get_task(self.selected_task_id) if self.selected_task_id else None
            return int(task["focus_minutes"]) * 60 if task else int(self.settings.get("focus_minutes", "25")) * 60
        return int(self.settings.get("short_break_minutes" if self.mode == "short_break" else "long_break_minutes", "5")) * 60

    def _persist_active(self):
        if self.session_started_at and (self.running or self.remaining_seconds < self.total_seconds):
            payload = {"task_id": self.selected_task_id, "mode": self.mode, "total_seconds": self.total_seconds, "remaining_seconds": self.remaining_seconds, "session_started_at": self.session_started_at, "deadline": self.session_deadline, "running": self.running, "saved_at": time.time()}
            self.db.save_settings({"active_session": json.dumps(payload)})
        else: self.db.save_settings({"active_session": ""})

    def _restore_session(self):
        raw = self.settings.get("active_session", "")
        if not raw: return
        try:
            data = json.loads(raw); remaining = int(data.get("remaining_seconds", 0));
            if data.get("running") and data.get("deadline"): remaining = max(0, int(float(data["deadline"]) - time.time()))
            if remaining <= 0: return
            if QMessageBox.question(self, "Resume session?", f"FocusFlow found an unfinished {data.get('mode', 'focus')} session. Resume {self._fmt(remaining)}?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                self.db.save_settings({"active_session": ""}); return
            self.selected_task_id = data.get("task_id"); self.mode = data.get("mode", "focus"); self.total_seconds = int(data.get("total_seconds", self._duration_for_mode())); self.remaining_seconds = remaining; self.session_started_at = data.get("session_started_at")
            if data.get("running"): self.start_timer()
        except (ValueError, TypeError, json.JSONDecodeError): self.db.save_settings({"active_session": ""})

    def _fmt(self, seconds): return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"

    def _reset_timer(self):
        self.running = False; self.session_deadline = None; self.session_started_at = None; self.total_seconds = max(1, self._duration_for_mode()); self.remaining_seconds = self.total_seconds; self._persist_active(); self.refresh_timer_ui()

    def reset_timer(self): self._reset_timer()

    def start_timer(self):
        if self.mode == "focus" and not self.selected_task_id:
            QMessageBox.information(self, "Choose a task", "Select or add a task before starting a focus session."); return
        if self.running: return
        if not self.session_started_at: self.session_started_at = datetime.now().isoformat(timespec="seconds")
        self.session_deadline = time.time() + self.remaining_seconds; self.running = True; self.db.set_task_status(self.selected_task_id, "In progress") if self.mode == "focus" and self.selected_task_id else None; self.timer.start(250); self._persist_active(); self.refresh_tasks()

    def pause_timer(self):
        if not self.running: return
        self._update_remaining(); self.running = False; self.session_deadline = None; self.timer.stop();
        if self.mode == "focus" and self.selected_task_id: self.db.set_task_status(self.selected_task_id, "Paused")
        self._persist_active(); self.refresh_all()

    def toggle_timer(self): self.pause_timer() if self.running else self.start_timer()

    def _update_remaining(self):
        if self.running and self.session_deadline: self.remaining_seconds = max(0, int(self.session_deadline - time.time()))

    def _tick(self):
        self._update_remaining(); self.refresh_timer_ui(); self._persist_active()
        if self.remaining_seconds <= 0: self.complete_timer()

    def complete_timer(self):
        if hasattr(self, "timer"): self.timer.stop()
        self.running = False; actual = self.total_seconds
        self.db.conn.execute("INSERT INTO sessions(task_id, session_type, duration_minutes, actual_seconds, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?)", (self.selected_task_id, self.mode, max(1, self.total_seconds // 60), actual, self.session_started_at or datetime.now().isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds")))
        if self.mode == "focus" and self.selected_task_id:
            self.db.increment_task(self.selected_task_id)
            task = self.db.get_task(self.selected_task_id)
            if task and int(task["completed_sessions"]) >= int(task["planned_sessions"]): self.db.set_task_status(self.selected_task_id, "Completed")
        self.db.conn.commit(); self._play_completion(); self._send_toast("FocusFlow", "Focus session complete" if self.mode == "focus" else "Break complete")
        if self.mode == "focus":
            today_focus = sum(1 for row in self.session_rows(since=datetime.now().strftime("%Y-%m-%d")) if row["session_type"] == "focus")
            self.mode = "long_break" if today_focus and today_focus % int(self.settings.get("sessions_before_long_break", "4")) == 0 else "short_break"
        else: self.mode = "focus"
        self.session_started_at = None; self.session_deadline = None; self.total_seconds = self._duration_for_mode(); self.remaining_seconds = self.total_seconds; self._persist_active(); self.refresh_all()

    def skip_timer(self):
        if self.running and QMessageBox.question(self, "Skip session", "Skip the current timer? It will not be recorded.", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        if hasattr(self, "timer"): self.timer.stop()
        self.running = False; self.mode = "short_break" if self.mode == "focus" else "focus"; self._reset_timer(); self.refresh_all()

    def refresh_timer_ui(self):
        if not hasattr(self, "timer_label"): return
        self._update_remaining(); self.timer_label.setText(self._fmt(self.remaining_seconds)); progress = int(100 * (1 - self.remaining_seconds / max(1, self.total_seconds))); self.progress.setValue(progress); self.mode_label.setText({"focus": "FOCUS SESSION", "short_break": "SHORT BREAK", "long_break": "LONG BREAK"}.get(self.mode, "FOCUS SESSION")); self.timer_status.setText("Stay with one thing until the bell." if self.mode == "focus" else "Step away and come back refreshed."); self.start_btn.setText("Running…" if self.running else ("Resume" if self.remaining_seconds < self.total_seconds else "Start")); self.refresh_active_task()

    def refresh_summary(self):
        sessions = [row for row in self.session_rows(since=datetime.now().strftime("%Y-%m-%d")) if row["session_type"] == "focus"]
        minutes = sum(int(row["actual_seconds"] or row["duration_minutes"] * 60) for row in sessions) // 60; tasks = self.task_rows(); planned = sum(int(row["planned_sessions"]) for row in tasks); complete = len(sessions); remaining = max(0, planned - complete); rate = int(complete / planned * 100) if planned else 0
        for key, value in (("sessions", str(complete)), ("minutes", str(minutes)), ("remaining", str(remaining)), ("rate", f"{rate}%")):
            if key in self.metric_labels: self.metric_labels[key].setText(value)
        if hasattr(self, "activity_table"):
            self.activity_table.setRowCount(0)
            for row in self.session_rows(since=datetime.now().strftime("%Y-%m-%d"))[:12]:
                index = self.activity_table.rowCount(); self.activity_table.insertRow(index); values = ("Focus" if row["session_type"] == "focus" else "Break", row["task_title"], datetime.fromisoformat(row["completed_at"]).strftime("%I:%M %p").lstrip("0"))
                for col, value in enumerate(values): self.activity_table.setItem(index, col, QTableWidgetItem(str(value)))

    def refresh_history_table(self):
        if not hasattr(self, "history_table"): return
        rows = self.session_rows(); self.history_table.setRowCount(0)
        for row in rows:
            index = self.history_table.rowCount(); self.history_table.insertRow(index); values = (datetime.fromisoformat(row["completed_at"]).strftime("%b %d, %Y  %I:%M %p").replace(" 0", " "), "Focus" if row["session_type"] == "focus" else "Break", row["task_title"], str(row["duration_minutes"]), self._fmt(int(row["actual_seconds"])))
            for col, value in enumerate(values): self.history_table.setItem(index, col, QTableWidgetItem(value))

    def _range_days(self): return (7, 14, 30)[self.analytics_range.currentIndex()] if hasattr(self, "analytics_range") else 7

    def refresh_analytics(self):
        if not hasattr(self, "chart"): return
        end = date.today() + timedelta(days=1); start = date.today() - timedelta(days=self._range_days() - 1); rows = [row for row in self.session_rows(start.isoformat(), end.isoformat()) if row["session_type"] == "focus"]; daily = {}; by_task = {}
        for row in rows:
            day = row["completed_at"][:10]; minutes = max(1, int((row["actual_seconds"] or row["duration_minutes"] * 60) / 60)); daily[day] = daily.get(day, 0) + minutes; by_task[row["task_title"]] = by_task.get(row["task_title"], 0) + minutes
        days = [start + timedelta(days=i) for i in range(self._range_days())]; values = [daily.get(day.isoformat(), 0) for day in days]; labels = [day.strftime("%b %d") if self._range_days() <= 14 else day.strftime("%d") for day in days]; self.chart.set_data(values, labels, "accent"); task_items = sorted(by_task.items(), key=lambda item: item[1], reverse=True)[:8]; self.task_chart.set_data([value for _, value in task_items], [name[:9] for name, _ in task_items], "cyan")
        total = sum(values); best = max(daily.items(), key=lambda item: item[1])[0] if daily else "—"; avg = int(total / len(rows)) if rows else 0
        self.analytics_labels["minutes"].setText(str(total)); self.analytics_labels["sessions"].setText(str(len(rows))); self.analytics_labels["average"].setText(str(avg)); self.analytics_labels["best"].setText(datetime.strptime(best, "%Y-%m-%d").strftime("%b %d") if best != "—" else "—")

    def refresh_calendar_day(self):
        if not hasattr(self, "calendar"): return
        selected = self.calendar.selectedDate().toPython(); day = selected.isoformat(); rows = self.session_rows(day, (selected + timedelta(days=1)).isoformat()); mode = self.calendar_filter.currentIndex() if hasattr(self, "calendar_filter") else 0
        if mode == 1: rows = [row for row in rows if row["session_type"] == "focus"]
        elif mode == 2: rows = [row for row in rows if row["session_type"] != "focus"]
        self.calendar_day_title.setText(selected.strftime("%A, %B %d")); focus_minutes = sum(int((row["actual_seconds"] or row["duration_minutes"] * 60) / 60) for row in rows if row["session_type"] == "focus"); self.calendar_day_summary.setText(f"{focus_minutes} focused minutes  •  {len(rows)} recorded sessions"); self.calendar_table.setRowCount(0)
        for row in rows:
            index = self.calendar_table.rowCount(); self.calendar_table.insertRow(index); values = (datetime.fromisoformat(row["completed_at"]).strftime("%I:%M %p").lstrip("0"), "Focus" if row["session_type"] == "focus" else "Break", row["task_title"], str(row["duration_minutes"]))
            for col, value in enumerate(values): self.calendar_table.setItem(index, col, QTableWidgetItem(value))

    def refresh_settings_summary(self):
        if not hasattr(self, "settings_summary"): return
        self.settings_summary.setText(f"Theme: {'Light' if self.theme == 'light' else 'Dark'}\nFocus: {self.settings.get('focus_minutes', '25')} min  •  Short break: {self.settings.get('short_break_minutes', '5')} min  •  Long break: {self.settings.get('long_break_minutes', '15')} min\nToast: {'On' if self.settings.get('toast_notifications', '1') == '1' else 'Off'}  •  System tray: {'On' if self.settings.get('tray_enabled', '1') == '1' else 'Off'}")

    def open_settings_dialog(self):
        dialog = QDialog(self); dialog.setWindowTitle("FocusFlow Settings"); dialog.setMinimumWidth(460); layout = QVBoxLayout(dialog); layout.setContentsMargins(26, 24, 26, 22); title = QLabel("Timer settings"); title.setObjectName("dialogTitle"); layout.addWidget(title); form = QFormLayout(); values = {}
        for label, key, default in (("Focus minutes", "focus_minutes", 25), ("Short break minutes", "short_break_minutes", 5), ("Long break minutes", "long_break_minutes", 15), ("Sessions before long break", "sessions_before_long_break", 4)):
            spin = QSpinBox(); spin.setRange(1, 180); spin.setValue(int(self.settings.get(key, str(default)))); form.addRow(label, spin); values[key] = spin
        layout.addLayout(form); sound = QCheckBox("Play completion music"); sound.setChecked(self.settings.get("sound_enabled", "1") == "1"); layout.addWidget(sound); notify = QCheckBox("Use Windows completion alert sound"); notify.setChecked(self.settings.get("notifications_enabled", "1") == "1"); layout.addWidget(notify); toast = QCheckBox("Show Windows corner toast notification"); toast.setChecked(self.settings.get("toast_notifications", "1") == "1"); layout.addWidget(toast); tray = QCheckBox("Enable system-tray controls"); tray.setChecked(self.settings.get("tray_enabled", "1") == "1"); layout.addWidget(tray); buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save); buttons.rejected.connect(dialog.reject)
        def save():
            self.db.save_settings({**{key: str(spin.value()) for key, spin in values.items()}, "sound_enabled": "1" if sound.isChecked() else "0", "notifications_enabled": "1" if notify.isChecked() else "0", "toast_notifications": "1" if toast.isChecked() else "0", "tray_enabled": "1" if tray.isChecked() else "0"}); self.settings = self.db.get_settings(); self.tray.setVisible(self.settings.get("tray_enabled", "1") == "1"); self.refresh_settings_summary(); dialog.accept()
        buttons.accepted.connect(save); layout.addWidget(buttons); dialog.exec()

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"; self.db.save_settings({"theme": self.theme}); self.settings = self.db.get_settings(); self._apply_qss(); self._apply_calendar_palette(); self.background.set_theme(self.theme); self._apply_window_mask(); self.theme_btn.setText("◐  Dark mode" if self.theme == "light" else "◑  Light mode"); self.tray.setIcon(self._tray_icon()); self.chart.set_theme(self.theme) if hasattr(self, "chart") else None; self.task_chart.set_theme(self.theme) if hasattr(self, "task_chart") else None; self.refresh_all()

    def _play_completion(self):
        if self.settings.get("sound_enabled", "1") != "1": return
        path = self.settings.get("custom_sound", "").strip()
        def play():
            try:
                if path and winsound:
                    for _ in range(3): winsound.PlaySound(path, winsound.SND_FILENAME); time.sleep(0.18)
                elif winsound:
                    for frequency in (660, 790, 940): winsound.Beep(frequency, 180); time.sleep(0.13)
            except Exception: pass
        threading.Thread(target=play, daemon=True).start()

    def _send_toast(self, title, message):
        if self.settings.get("toast_notifications", "1") != "1": return
        def send():
            try:
                if windows_toast: windows_toast(title, message, duration="short")
                else: QApplication.beep()
            except Exception: QApplication.beep()
        threading.Thread(target=send, daemon=True).start()

    def export_history(self):
        rows = self.session_rows()
        if not rows: QMessageBox.information(self, "Export history", "There are no sessions to export yet."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export focus history", "focusflow-history.csv", "CSV files (*.csv)")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle); writer.writerow(["Completed", "Type", "Task", "Planned minutes", "Actual seconds"])
            for row in rows: writer.writerow([row["completed_at"], row["session_type"], row["task_title"], row["duration_minutes"], row["actual_seconds"]])
        QMessageBox.information(self, "Export complete", f"History exported to:\n{path}")

    def show_from_tray(self): self.showNormal(); self.raise_(); self.activateWindow()

    def closeEvent(self, event):
        self._update_remaining(); self._persist_active(); self.db.close(); self.tray.hide(); event.accept()


def main():
    app = QApplication(sys.argv); app.setApplicationName(APP_NAME); window = FocusFlowQt(); window.show(); QTimer.singleShot(250, window.start_first_run); sys.exit(app.exec())


if __name__ == "__main__":
    main()
