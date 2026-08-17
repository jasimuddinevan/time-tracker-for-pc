from __future__ import annotations

import calendar
import csv
import ctypes
import json
import os
import shutil
import sqlite3
import stat
import threading
import time
import tkinter as tk
from datetime import datetime, date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import winsound
except ImportError:  # pragma: no cover - Windows is the target platform.
    winsound = None

try:
    from win11toast import toast as windows_toast
except ImportError:  # Optional during source-only development.
    windows_toast = None

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:  # Optional fallback keeps the timer usable without a tray icon.
    pystray = None
    Image = None
    ImageDraw = None


APP_NAME = "FocusFlow"
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "focusflow.db"

THEMES = {
    "light": {
        "bg": "#F3F5FB",
        "panel": "#FFFFFF",
        "panel_alt": "#F8F7FF",
        "panel_deep": "#F8FAFC",
        "border": "#E4E7F0",
        "text": "#172033",
        "muted": "#667085",
        "accent": "#7C3AED",
        "accent_dark": "#5B21B6",
        "accent_soft": "#EDE9FE",
        "accent_glow": "#C4B5FD",
        "green": "#10B981",
        "blue": "#2563EB",
        "red": "#E11D48",
        "yellow": "#B45309",
        "shine": "#FFFFFF",
        "shadow": "#D9DEEA",
        "glass": "#FFFFFF",
        "glass_alt": "#FBFAFF",
        "nav": "#FFFFFF",
        "input": "#F8FAFC",
        "hero": "#FAF8FF",
        "hero_deep": "#F4F0FF",
        "success_soft": "#ECFDF5",
    },
    "dark": {
        "bg": "#0B1020",
        "panel": "#141B2D",
        "panel_alt": "#1D2740",
        "panel_deep": "#0E1424",
        "border": "#2B3854",
        "text": "#F8FAFC",
        "muted": "#93A4BE",
        "accent": "#A78BFA",
        "accent_dark": "#7C3AED",
        "accent_soft": "#30205F",
        "accent_glow": "#C4B5FD",
        "green": "#34D399",
        "blue": "#60A5FA",
        "red": "#FB7185",
        "yellow": "#FACC15",
        "shine": "#344363",
        "shadow": "#070A13",
        "glass": "#151D32",
        "glass_alt": "#1B2540",
        "nav": "#141B2D",
        "input": "#0F172A",
        "hero": "#171B35",
        "hero_deep": "#11172C",
        "success_soft": "#12372D",
    },
}
COLORS = THEMES["light"]


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._consume_data_reset_marker()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._setup()

    def _consume_data_reset_marker(self):
        """Finish a requested data wipe before the first-run state is loaded."""
        marker = self.path.parent.parent / "FocusFlow.remove-data"
        if not marker.exists():
            return
        data_dir = self.path.parent
        try:
            if data_dir.exists():
                def onerror(func, failed_path, _exc_info):
                    try:
                        os.chmod(failed_path, stat.S_IWRITE)
                    except OSError:
                        pass
                    try:
                        func(failed_path)
                    except OSError:
                        pass
                shutil.rmtree(data_dir, onerror=onerror)
            data_dir.mkdir(parents=True, exist_ok=True)
            marker.unlink(missing_ok=True)
        except OSError:
            # Leave the marker in place so a later launch retries the reset.
            pass

    def _setup(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                planned_sessions INTEGER NOT NULL DEFAULT 4,
                completed_sessions INTEGER NOT NULL DEFAULT 0,
                focus_minutes INTEGER NOT NULL DEFAULT 25,
                created_at TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Not started',
                priority TEXT NOT NULL DEFAULT 'Normal',
                due_date TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                session_type TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                actual_seconds INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE SET NULL
            );
            """
        )
        existing_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(tasks)").fetchall()}
        migrations = {
            "status": "TEXT NOT NULL DEFAULT 'Not started'",
            "priority": "TEXT NOT NULL DEFAULT 'Normal'",
            "due_date": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in migrations.items():
            if column not in existing_columns:
                self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {column} {definition}")

        defaults = {
            "focus_minutes": "25",
            "short_break_minutes": "5",
            "long_break_minutes": "15",
            "sessions_before_long_break": "4",
            "sound_enabled": "1",
            "custom_sound": "",
            "theme": "light",
            "active_session": "",
            "notifications_enabled": "1",
            "toast_notifications": "1",
            "tray_enabled": "1",
            "user_name": "",
            "onboarding_complete": "0",
        }
        for key, value in defaults.items():
            self.conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    def get_setting(self, key: str, fallback: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else fallback

    def get_settings(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def save_settings(self, values: dict[str, str]):
        self.conn.executemany(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            values.items(),
        )
        self.conn.commit()

    def add_task(self, title: str, planned: int, focus_minutes: int, priority: str = "Normal", due_date: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO tasks(title, planned_sessions, focus_minutes, priority, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (title, planned, focus_minutes, priority, due_date, datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_tasks(self):
        return self.conn.execute(
            "SELECT * FROM tasks WHERE archived = 0 ORDER BY completed_sessions >= planned_sessions, created_at DESC"
        ).fetchall()

    def get_task(self, task_id: int):
        return self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    def archive_task(self, task_id: int):
        self.conn.execute("UPDATE tasks SET archived = 1, status = 'Archived' WHERE id = ?", (task_id,))
        self.conn.commit()

    def update_task(self, task_id: int, title: str, planned: int, focus_minutes: int, priority: str, status: str, due_date: str):
        self.conn.execute(
            "UPDATE tasks SET title = ?, planned_sessions = ?, focus_minutes = ?, priority = ?, status = ?, due_date = ? WHERE id = ?",
            (title, planned, focus_minutes, priority, status, due_date, task_id),
        )
        self.conn.commit()

    def set_task_status(self, task_id: int, status: str):
        self.conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        self.conn.commit()

    def increment_task(self, task_id: int):
        self.conn.execute("UPDATE tasks SET completed_sessions = completed_sessions + 1 WHERE id = ?", (task_id,))
        self.conn.commit()

    def record_session(self, task_id: int | None, session_type: str, duration_minutes: int, actual_seconds: int, started_at: str):
        self.conn.execute(
            "INSERT INTO sessions(task_id, session_type, duration_minutes, actual_seconds, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, session_type, duration_minutes, actual_seconds, started_at, datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()

    def today_sessions(self):
        return self.conn.execute(
            """
            SELECT s.*, COALESCE(t.title, 'General focus') AS task_title
            FROM sessions s LEFT JOIN tasks t ON s.task_id = t.id
            WHERE date(s.completed_at, 'localtime') = date('now', 'localtime')
            ORDER BY s.completed_at DESC
            """
        ).fetchall()

    def today_task_counts(self) -> dict[int, int]:
        rows = self.conn.execute(
            "SELECT task_id, COUNT(*) AS count FROM sessions WHERE session_type='focus' AND date(completed_at, 'localtime') = date('now', 'localtime') GROUP BY task_id"
        ).fetchall()
        return {int(row["task_id"]): int(row["count"]) for row in rows if row["task_id"] is not None}

    def all_sessions(self):
        return self.conn.execute(
            """
            SELECT s.*, COALESCE(t.title, 'General focus') AS task_title
            FROM sessions s LEFT JOIN tasks t ON s.task_id = t.id
            ORDER BY s.completed_at DESC
            """
        ).fetchall()

    def sessions_for_date(self, day_text: str):
        return self.conn.execute(
            """
            SELECT s.*, COALESCE(t.title, 'General focus') AS task_title
            FROM sessions s LEFT JOIN tasks t ON s.task_id = t.id
            WHERE date(s.completed_at, 'localtime') = ?
            ORDER BY s.completed_at DESC
            """,
            (day_text,),
        ).fetchall()

    def daily_focus_totals(self, days: int = 14):
        days = max(1, min(365, int(days)))
        start = (date.today() - timedelta(days=days - 1)).isoformat()
        return self.conn.execute(
            """
            SELECT date(completed_at, 'localtime') AS day,
                   COUNT(*) AS sessions,
                   COALESCE(SUM(actual_seconds), SUM(duration_minutes * 60)) AS seconds
            FROM sessions
            WHERE session_type = 'focus' AND date(completed_at, 'localtime') >= ?
            GROUP BY date(completed_at, 'localtime')
            ORDER BY day
            """,
            (start,),
        ).fetchall()

    def task_focus_totals(self, days: int = 30):
        days = max(1, min(365, int(days)))
        start = (date.today() - timedelta(days=days - 1)).isoformat()
        return self.conn.execute(
            """
            SELECT COALESCE(t.title, 'General focus') AS task_title,
                   COUNT(*) AS sessions,
                   COALESCE(SUM(s.actual_seconds), SUM(s.duration_minutes * 60)) AS seconds
            FROM sessions s LEFT JOIN tasks t ON s.task_id = t.id
            WHERE s.session_type = 'focus' AND date(s.completed_at, 'localtime') >= ?
            GROUP BY s.task_id, task_title
            ORDER BY seconds DESC, task_title COLLATE NOCASE
            LIMIT 8
            """,
            (start,),
        ).fetchall()

    def summary_for_date(self, day_text: str):
        row = self.conn.execute(
            """
            SELECT COUNT(CASE WHEN session_type = 'focus' THEN 1 END) AS focus_sessions,
                   COUNT(CASE WHEN session_type <> 'focus' THEN 1 END) AS breaks,
                   COALESCE(SUM(CASE WHEN session_type = 'focus' THEN COALESCE(actual_seconds, duration_minutes * 60) ELSE 0 END), 0) AS focus_seconds
            FROM sessions
            WHERE date(completed_at, 'localtime') = ?
            """,
            (day_text,),
        ).fetchone()
        return row

    def close(self):
        self.conn.close()


class FocusFlowApp:
    def __init__(self, root: tk.Tk):
        global COLORS
        self.root = root
        self.root.title("FocusFlow — Pomodoro Timer")
        self.root.geometry("1180x760")
        self.root.minsize(980, 650)
        self.root.configure(bg=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.tray_icon = None
        self.tray_thread = None
        self._bind_shortcuts()

        self.db = Database(DB_PATH)
        self.settings = self.db.get_settings()
        self.theme = self.settings.get("theme", "light") if self.settings.get("theme", "light") in THEMES else "light"
        COLORS = THEMES[self.theme]
        self.root.configure(bg=COLORS["bg"])
        self.selected_task_id: int | None = None
        self.mode = "focus"
        self.running = False
        self.timer_job = None
        self.remaining_seconds = 0
        self.total_seconds = 0
        self.session_started_at: str | None = None
        self.session_deadline: float | None = None
        self.last_timer_persist_at = 0.0
        self.completed_focus_since_long_break = 0
        self.recovery_prompt_shown = False

        self._configure_styles()
        self._build_ui()
        self._refresh_all()
        self.total_seconds = max(1, self._duration_for_mode())
        self.remaining_seconds = self.total_seconds
        self._update_timer_display()
        self.refresh_active_task_label()
        self.root.after(180, self._restore_active_session)
        self.root.after(400, self._start_tray)

    def _bind_shortcuts(self):
        self.root.bind_all("<space>", lambda event: self._shortcut_action("toggle", event))
        self.root.bind_all("<KeyPress-r>", lambda event: self._shortcut_action("reset", event))
        self.root.bind_all("<KeyPress-s>", lambda event: self._shortcut_action("skip", event))
        self.root.bind_all("<Control-KeyPress-n>", lambda event: self._shortcut_action("new_task", event))
        self.root.bind_all("<Control-KeyPress-comma>", lambda event: self._shortcut_action("settings", event))
        self.root.bind_all("<Control-KeyPress-1>", lambda event: self._shortcut_action("dashboard", event))
        self.root.bind_all("<Control-KeyPress-2>", lambda event: self._shortcut_action("tasks", event))
        self.root.bind_all("<Control-KeyPress-3>", lambda event: self._shortcut_action("history", event))
        self.root.bind_all("<Control-KeyPress-4>", lambda event: self._shortcut_action("settings_page", event))
        self.root.bind_all("<Control-KeyPress-5>", lambda event: self._shortcut_action("analytics", event))
        self.root.bind_all("<Control-KeyPress-6>", lambda event: self._shortcut_action("calendar", event))

    def _shortcut_action(self, action, event):
        if isinstance(event.widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox)):
            return None
        actions = {
            "toggle": lambda: self.pause_timer() if self.running else self.start_timer(),
            "reset": self.reset_timer,
            "skip": self.skip_timer,
            "new_task": self._focus_new_task,
            "settings": self.open_settings,
            "dashboard": lambda: self.show_view("dashboard"),
            "tasks": lambda: self.show_view("tasks"),
            "history": lambda: self.show_view("history"),
            "settings_page": lambda: self.show_view("settings"),
            "analytics": lambda: self.show_view("analytics"),
            "calendar": lambda: self.show_view("calendar"),
        }
        callback = actions.get(action)
        if callback:
            callback()
        return "break"

    def _focus_new_task(self):
        self.show_view("tasks")
        if getattr(self, "task_entry", None):
            self.task_entry.focus_set()

    def _tray_image(self):
        if Image is None or ImageDraw is None:
            return None
        image = Image.new("RGBA", (64, 64), "#7C3AED")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=14, fill="#7C3AED", outline="#A78BFA", width=2)
        draw.ellipse((18, 18, 46, 46), outline="white", width=3)
        draw.line((32, 32, 32, 23), fill="white", width=3)
        draw.line((32, 32, 40, 37), fill="white", width=3)
        return image

    def _start_tray(self):
        if self.tray_icon or pystray is None or Image is None or self.settings.get("tray_enabled", "1") != "1":
            return
        image = self._tray_image()
        if image is None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Open FocusFlow", lambda icon, item: self.root.after(0, self.show_from_tray), default=True),
            pystray.MenuItem("Start / Resume", lambda icon, item: self.root.after(0, self.start_timer)),
            pystray.MenuItem("Pause", lambda icon, item: self.root.after(0, self.pause_timer)),
            pystray.MenuItem("Exit", lambda icon, item: self.root.after(0, self.close)),
        )
        self.tray_icon = pystray.Icon("FocusFlow", image, "FocusFlow", menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, name="FocusFlowTray", daemon=True)
        self.tray_thread.start()

    def hide_to_tray(self):
        if self.tray_icon is None:
            messagebox.showinfo("System tray", "System-tray support is unavailable in this build.")
            return
        self.root.withdraw()

    def show_from_tray(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(120, lambda: self.root.attributes("-topmost", False))

    def _configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background=COLORS["bg"])
        style.configure("Header.TFrame", background=COLORS["glass"], borderwidth=1, relief="solid")
        style.configure("Panel.TFrame", background=COLORS["glass"], borderwidth=1, relief="solid")
        style.configure("Deep.TFrame", background=COLORS["hero_deep"], borderwidth=1, relief="solid")
        style.configure("Hero.TFrame", background=COLORS["hero"], borderwidth=1, relief="solid")
        style.configure("Inset.TFrame", background=COLORS["panel_deep"], borderwidth=1, relief="solid")
        style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 27, "bold"))
        style.configure("HeaderTitle.TLabel", background=COLORS["glass"], foreground=COLORS["text"], font=("Segoe UI", 25, "bold"))
        style.configure("HeaderSubtitle.TLabel", background=COLORS["glass"], foreground=COLORS["muted"], font=("Segoe UI", 10))
        style.configure("Subtitle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Segoe UI", 10))
        style.configure("PanelTitle.TLabel", background=COLORS["glass"], foreground=COLORS["text"], font=("Segoe UI", 13, "bold"))
        style.configure("PanelText.TLabel", background=COLORS["glass"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=COLORS["glass"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("HeroTitle.TLabel", background=COLORS["hero"], foreground=COLORS["text"], font=("Segoe UI", 14, "bold"))
        style.configure("HeroMuted.TLabel", background=COLORS["hero"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Timer.TLabel", background=COLORS["hero"], foreground=COLORS["text"], font=("Segoe UI", 72, "bold"))
        style.configure("Mode.TLabel", background=COLORS["hero_deep"], foreground=COLORS["accent"], font=("Segoe UI", 10, "bold"))
        style.configure("SummaryNumber.TLabel", background=COLORS["panel_alt"], foreground=COLORS["text"], font=("Segoe UI", 21, "bold"))
        style.configure("SummaryCaption.TLabel", background=COLORS["panel_alt"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Accent.TButton", background=COLORS["accent"], foreground="white", borderwidth=0, padding=(16, 11), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", COLORS["accent_dark"]), ("pressed", COLORS["accent_dark"]), ("disabled", COLORS["border"])], foreground=[("disabled", COLORS["muted"])])
        style.configure("Secondary.TButton", background=COLORS["panel_alt"], foreground=COLORS["text"], borderwidth=0, padding=(13, 10), font=("Segoe UI", 9, "bold"))
        style.map("Secondary.TButton", background=[("active", COLORS["accent_soft"]), ("pressed", COLORS["border"])], foreground=[("active", COLORS["accent_dark"])])
        style.configure("Ghost.TButton", background=COLORS["glass"], foreground=COLORS["accent"], borderwidth=0, padding=(12, 9), font=("Segoe UI", 9, "bold"))
        style.map("Ghost.TButton", background=[("active", COLORS["accent_soft"]), ("pressed", COLORS["panel_alt"])], foreground=[("active", COLORS["accent_dark"])])
        style.configure("Nav.TButton", background=COLORS["nav"], foreground=COLORS["muted"], borderwidth=0, padding=(13, 9), font=("Segoe UI", 9, "bold"))
        style.map("Nav.TButton", background=[("active", COLORS["accent_soft"]), ("pressed", COLORS["panel_alt"])], foreground=[("active", COLORS["text"])])
        style.configure("NavActive.TButton", background=COLORS["accent"], foreground="white", borderwidth=0, padding=(14, 9), font=("Segoe UI", 9, "bold"))
        style.map("NavActive.TButton", background=[("active", COLORS["accent_dark"]), ("pressed", COLORS["accent_dark"])], foreground=[("active", "white")])
        style.configure("TEntry", fieldbackground=COLORS["input"], foreground=COLORS["text"], bordercolor=COLORS["border"], lightcolor=COLORS["border"], darkcolor=COLORS["border"], padding=(8, 7), font=("Segoe UI", 9))
        style.configure("TCombobox", fieldbackground=COLORS["input"], foreground=COLORS["text"], bordercolor=COLORS["border"], lightcolor=COLORS["border"], darkcolor=COLORS["border"], padding=(6, 5), font=("Segoe UI", 9))
        style.map("TCombobox", fieldbackground=[("readonly", COLORS["input"])], selectbackground=[("readonly", COLORS["accent_soft"])], selectforeground=[("readonly", COLORS["text"])])
        style.configure("Treeview", background=COLORS["panel_deep"], fieldbackground=COLORS["panel_deep"], foreground=COLORS["text"], rowheight=42, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=COLORS["panel_alt"], foreground=COLORS["muted"], relief="flat", padding=(10, 10), font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", COLORS["accent_dark"])], foreground=[("selected", "white")])
        style.configure("Horizontal.TProgressbar", troughcolor=COLORS["accent_soft"], background=COLORS["accent"], bordercolor=COLORS["accent_soft"], lightcolor=COLORS["accent_glow"], darkcolor=COLORS["accent"])
        style.configure("Glossy.TSeparator", background=COLORS["border"])

    def _theme_button_text(self):
        return "☾  Dark mode" if self.theme == "light" else "☀  Light mode"

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.db.save_settings({"theme": self.theme})
        self.settings = self.db.get_settings()
        self._rebuild_ui()

    def _rebuild_ui(self):
        global COLORS
        COLORS = THEMES[self.theme]
        self.root.configure(bg=COLORS["bg"])
        for child in self.root.winfo_children():
            child.destroy()
        self._configure_styles()
        self._build_ui()
        self._refresh_all()
        self._update_timer_display()

    def _build_ui(self):
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(28, 18, 28, 14))
        header.pack(fill="x")
        title_block = ttk.Frame(header, style="Header.TFrame")
        title_block.pack(side="left")
        ttk.Label(title_block, text="FocusFlow", style="HeaderTitle.TLabel").pack(anchor="w")
        self.date_label = ttk.Label(title_block, style="HeaderSubtitle.TLabel")
        self.date_label.pack(anchor="w", pady=(2, 0))
        actions = ttk.Frame(header, style="Header.TFrame")
        actions.pack(side="right", pady=8)
        self.theme_button = ttk.Button(actions, text=self._theme_button_text(), style="Ghost.TButton", command=self.toggle_theme)
        self.theme_button.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Minimize", style="Ghost.TButton", command=self.hide_to_tray).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Settings", style="Secondary.TButton", command=self.open_settings).pack(side="left")

        glow = tk.Frame(self.root, bg=COLORS["accent_glow"], height=3)
        glow.pack(fill="x", padx=28)
        self.nav_frame = ttk.Frame(self.root, style="Header.TFrame", padding=(28, 8, 28, 12))
        self.nav_frame.pack(fill="x")
        self.nav_buttons = {}
        for key, label in (("dashboard", "Dashboard"), ("tasks", "Tasks"), ("history", "History"), ("analytics", "Analytics"), ("calendar", "Calendar"), ("settings", "Settings")):
            button = ttk.Button(self.nav_frame, text=label, style="Nav.TButton", command=lambda page=key: self.show_view(page))
            button.pack(side="left", padx=(0, 8))
            self.nav_buttons[key] = button
        ttk.Separator(self.root, style="Glossy.TSeparator").pack(fill="x", padx=28)

        self.view_container = ttk.Frame(self.root, style="App.TFrame", padding=(28, 18, 28, 28))
        self.view_container.pack(fill="both", expand=True)
        self.view_container.columnconfigure(0, weight=1)
        self.view_container.rowconfigure(0, weight=1)
        self.show_view(getattr(self, "current_view", "dashboard"), refresh=False)

    def _clear_view(self):
        for child in self.view_container.winfo_children():
            child.destroy()
        self.left_panel = None
        self.center_panel = None
        self.right_panel = None
        for name in ("task_tree", "activity_tree", "history_tree", "start_button", "pause_button", "timer_label", "timer_progress", "timer_status", "mode_label", "active_task_label", "settings_theme_label", "settings_timer_label", "settings_sound_label", "analytics_days_combo", "analytics_total_label", "analytics_sessions_label", "analytics_average_label", "analytics_best_label", "analytics_daily_canvas", "analytics_task_canvas", "analytics_metric_vars", "calendar_month_label", "calendar_day_label", "calendar_focus_label", "calendar_sessions_label", "calendar_breaks_label", "calendar_grid", "calendar_tree", "calendar_filter_combo", "calendar_task_entry"):
            if hasattr(self, name):
                setattr(self, name, None)

    def show_view(self, view_name: str, refresh: bool = True):
        if view_name not in {"dashboard", "tasks", "history", "analytics", "calendar", "settings"}:
            view_name = "dashboard"
        self.current_view = view_name
        if not hasattr(self, "view_container"):
            return
        self._clear_view()
        builders = {"dashboard": self._build_dashboard_view, "tasks": self._build_tasks_view, "history": self._build_history_view, "analytics": self._build_analytics_view, "calendar": self._build_calendar_view, "settings": self._build_settings_view}
        builders[view_name]()
        self._update_nav_state()
        if refresh:
            self._refresh_all()
            if self.current_view == "dashboard":
                self._update_timer_display()

    def _update_nav_state(self):
        for key, button in getattr(self, "nav_buttons", {}).items():
            button.configure(style="NavActive.TButton" if key == getattr(self, "current_view", "dashboard") else "Nav.TButton")

    def _build_dashboard_view(self):
        content = ttk.Frame(self.view_container, style="App.TFrame")
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=5)
        content.columnconfigure(2, weight=3)
        content.rowconfigure(0, weight=1)
        self.left_panel = ttk.Frame(content, style="Panel.TFrame", padding=18)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.center_panel = ttk.Frame(content, style="Hero.TFrame", padding=25)
        self.center_panel.grid(row=0, column=1, sticky="nsew", padx=10)
        self.right_panel = ttk.Frame(content, style="Panel.TFrame", padding=18)
        self.right_panel.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        self._build_task_panel()
        self._build_timer_panel()
        self._build_summary_panel()

    def _page_heading(self, parent, title, subtitle):
        parent.columnconfigure(0, weight=1)
        block = ttk.Frame(parent, style="App.TFrame")
        block.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ttk.Label(block, text=title, style="PanelTitle.TLabel", background=COLORS["bg"]).pack(anchor="w")
        ttk.Label(block, text=subtitle, style="Subtitle.TLabel", background=COLORS["bg"]).pack(anchor="w", pady=(4, 0))

    def _build_tasks_view(self):
        page = ttk.Frame(self.view_container, style="App.TFrame")
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=4)
        page.columnconfigure(1, weight=2)
        page.rowconfigure(1, weight=1)
        self._page_heading(page, "Task library", "Plan the work before you start the clock.")
        self.left_panel = ttk.Frame(page, style="Panel.TFrame", padding=20)
        self.left_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self._build_task_panel()
        side = ttk.Frame(page, style="Panel.TFrame", padding=20)
        side.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(side, text="A focused plan", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(side, text="Turn a big goal into small, finishable sessions. Each task can have its own duration and planned session count.", style="Muted.TLabel", wraplength=260, justify="left").pack(anchor="w", pady=(8, 18))
        ttk.Button(side, text="Go to dashboard", style="Accent.TButton", command=lambda: self.show_view("dashboard")).pack(fill="x")
        ttk.Button(side, text="View history", style="Secondary.TButton", command=lambda: self.show_view("history")).pack(fill="x", pady=(8, 0))

    def _build_history_view(self):
        page = ttk.Frame(self.view_container, style="App.TFrame")
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(1, weight=1)
        page.columnconfigure(0, weight=1)
        heading = ttk.Frame(page, style="App.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Focus history", style="PanelTitle.TLabel", background=COLORS["bg"]).grid(row=0, column=0, sticky="w")
        ttk.Label(heading, text="Review your completed focus sessions and breaks.", style="Subtitle.TLabel", background=COLORS["bg"]).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(heading, text="Export CSV", style="Secondary.TButton", command=self.export_history).grid(row=0, column=1, rowspan=2, sticky="e")
        card = ttk.Frame(page, style="Panel.TFrame", padding=18)
        card.grid(row=1, column=0, sticky="nsew")
        card.rowconfigure(0, weight=1)
        card.columnconfigure(0, weight=1)
        self.history_tree = ttk.Treeview(card, columns=("date", "type", "task", "minutes", "completed"), show="headings")
        for key, label, width, anchor in (("date", "Date", 120, "w"), ("type", "Type", 90, "center"), ("task", "Task", 300, "w"), ("minutes", "Minutes", 90, "center"), ("completed", "Completed", 150, "center")):
            self.history_tree.heading(key, text=label)
            self.history_tree.column(key, width=width, anchor=anchor)
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(card, orient="vertical", command=self.history_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.history_tree.configure(yscrollcommand=scroll.set)

    def _build_analytics_view(self):
        page = ttk.Frame(self.view_container, style="App.TFrame")
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        heading = ttk.Frame(page, style="App.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Analytics", style="PanelTitle.TLabel", background=COLORS["bg"]).grid(row=0, column=0, sticky="w")
        ttk.Label(heading, text="See where your focus time is going and build a rhythm that lasts.", style="Subtitle.TLabel", background=COLORS["bg"]).grid(row=1, column=0, sticky="w", pady=(4, 0))
        controls = ttk.Frame(heading, style="App.TFrame")
        controls.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Label(controls, text="Window", style="Subtitle.TLabel", background=COLORS["bg"]).pack(side="left", padx=(0, 6))
        self.analytics_days_combo = ttk.Combobox(controls, values=("7 days", "14 days", "30 days"), state="readonly", width=10)
        self.analytics_days_combo.set("14 days")
        self.analytics_days_combo.pack(side="left", padx=(0, 8))
        self.analytics_days_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_analytics())
        ttk.Button(controls, text="Refresh", style="Secondary.TButton", command=self.refresh_analytics).pack(side="left")

        metrics = ttk.Frame(page, style="App.TFrame")
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        for column in range(4):
            metrics.columnconfigure(column, weight=1)
        self.analytics_metric_vars = {}
        metric_specs = (("analytics_total_label", "0", "focused minutes"), ("analytics_sessions_label", "0", "focus sessions"), ("analytics_average_label", "0 min", "average session"), ("analytics_best_label", "—", "best day"))
        for column, (name, value, caption) in enumerate(metric_specs):
            card = tk.Frame(metrics, bg=COLORS["panel_alt"], padx=16, pady=12, highlightbackground=COLORS["border"], highlightthickness=1)
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 5 if column < 3 else 0))
            variable = tk.StringVar(self.root, value=value)
            self.analytics_metric_vars[name] = variable
            setattr(self, name, ttk.Label(card, textvariable=variable, style="SummaryNumber.TLabel", background=COLORS["panel_alt"]))
            getattr(self, name).pack(anchor="w")
            ttk.Label(card, text=caption, style="SummaryCaption.TLabel", background=COLORS["panel_alt"]).pack(anchor="w", pady=(2, 0))

        charts = ttk.Frame(page, style="App.TFrame")
        charts.grid(row=2, column=0, sticky="nsew")
        charts.columnconfigure(0, weight=3)
        charts.columnconfigure(1, weight=2)
        charts.rowconfigure(0, weight=1)
        daily_card = ttk.Frame(charts, style="Panel.TFrame", padding=16)
        daily_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        task_card = ttk.Frame(charts, style="Panel.TFrame", padding=16)
        task_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(daily_card, text="Focus minutes by day", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(daily_card, text="Completed focus sessions in the selected window.", style="Muted.TLabel").pack(anchor="w", pady=(3, 8))
        self.analytics_daily_canvas = tk.Canvas(daily_card, height=260, bg=COLORS["panel_deep"], highlightthickness=0)
        self.analytics_daily_canvas.pack(fill="both", expand=True)
        ttk.Label(task_card, text="Focus by task", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(task_card, text="Your most focused tasks over the same period.", style="Muted.TLabel").pack(anchor="w", pady=(3, 8))
        self.analytics_task_canvas = tk.Canvas(task_card, height=260, bg=COLORS["panel_deep"], highlightthickness=0)
        self.analytics_task_canvas.pack(fill="both", expand=True)
        self.refresh_analytics()

    def _selected_analytics_days(self):
        try:
            return int(str(self.analytics_days_combo.get()).split()[0])
        except (ValueError, AttributeError):
            return 14

    def _draw_daily_chart(self, labels, values):
        canvas = self.analytics_daily_canvas
        canvas.delete("all")
        width = max(460, canvas.winfo_width())
        height = max(230, canvas.winfo_height())
        if not values or max(values, default=0) <= 0:
            canvas.create_text(width / 2, height / 2, text="Complete a focus session to see your trend.", fill=COLORS["muted"], font=("Segoe UI", 10))
            return
        left, right, top, bottom = 44, 16, 24, 42
        chart_width = width - left - right
        chart_height = height - top - bottom
        maximum = max(max(values), 1)
        canvas.create_text(left, 8, anchor="w", text="minutes", fill=COLORS["muted"], font=("Segoe UI", 8))
        canvas.create_line(left, top + chart_height, width - right, top + chart_height, fill=COLORS["border"])
        slot = chart_width / max(1, len(values))
        step = max(1, len(values) // 7)
        for index, value in enumerate(values):
            x_center = left + slot * index + slot / 2
            bar_width = max(8, slot * 0.58)
            bar_height = chart_height * (value / maximum)
            y_top = top + chart_height - bar_height
            canvas.create_rectangle(x_center - bar_width / 2, y_top, x_center + bar_width / 2, top + chart_height, fill=COLORS["accent"], outline="")
            if value > 0:
                canvas.create_text(x_center, y_top - 9, text=str(value), fill=COLORS["text"], font=("Segoe UI", 8, "bold"))
            if index % step == 0 or index == len(values) - 1:
                canvas.create_text(x_center, height - 18, text=labels[index], fill=COLORS["muted"], font=("Segoe UI", 8))

    def _draw_task_chart(self, rows):
        canvas = self.analytics_task_canvas
        canvas.delete("all")
        width = max(320, canvas.winfo_width())
        height = max(230, canvas.winfo_height())
        if not rows:
            canvas.create_text(width / 2, height / 2, text="No task data in this window yet.", fill=COLORS["muted"], font=("Segoe UI", 10))
            return
        left, right, top, bottom = 112, 42, 28, 18
        row_height = max(24, min(42, (height - top - bottom) / len(rows)))
        maximum = max(max(int(row["seconds"] or 0) // 60 for row in rows), 1)
        for index, row in enumerate(rows):
            minutes = int(row["seconds"] or 0) // 60
            y = top + index * row_height
            title = str(row["task_title"])
            if len(title) > 17:
                title = title[:16] + "…"
            canvas.create_text(left - 8, y + row_height / 2, text=title, anchor="e", fill=COLORS["text"], font=("Segoe UI", 8))
            bar_width = (width - left - right) * (minutes / maximum)
            canvas.create_rectangle(left, y + 6, left + max(3, bar_width), y + row_height - 6, fill=COLORS["blue"], outline="")
            canvas.create_text(min(width - 8, left + bar_width + 7), y + row_height / 2, text=f"{minutes}m", anchor="w", fill=COLORS["muted"], font=("Segoe UI", 8, "bold"))

    def refresh_analytics(self):
        if not getattr(self, "analytics_daily_canvas", None):
            return
        days = self._selected_analytics_days()
        rows = self.db.daily_focus_totals(days)
        totals = {row["day"]: {"minutes": int(row["seconds"] or 0) // 60, "sessions": int(row["sessions"] or 0)} for row in rows}
        today = date.today()
        dates = [today - timedelta(days=offset) for offset in reversed(range(days))]
        values = [totals.get(day.isoformat(), {}).get("minutes", 0) for day in dates]
        labels = [day.strftime("%b %d") for day in dates]
        total_minutes = sum(values)
        total_sessions = sum(totals.get(day.isoformat(), {}).get("sessions", 0) for day in dates)
        average = round(total_minutes / total_sessions) if total_sessions else 0
        best_index = max(range(len(values)), key=lambda index: values[index]) if values else 0
        best_text = dates[best_index].strftime("%b %d") if values and values[best_index] else "—"
        self.analytics_metric_vars["analytics_total_label"].set(str(total_minutes))
        self.analytics_metric_vars["analytics_sessions_label"].set(str(total_sessions))
        self.analytics_metric_vars["analytics_average_label"].set(f"{average} min")
        self.analytics_metric_vars["analytics_best_label"].set(best_text)
        self._draw_daily_chart(labels, values)
        self._draw_task_chart(self.db.task_focus_totals(days))

    def _build_calendar_view(self):
        page = ttk.Frame(self.view_container, style="App.TFrame")
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=3)
        page.columnconfigure(1, weight=2)
        page.rowconfigure(1, weight=1)
        if not hasattr(self, "calendar_month"):
            self.calendar_month = date.today().replace(day=1)
        if not hasattr(self, "calendar_selected_date"):
            self.calendar_selected_date = date.today()
        heading = ttk.Frame(page, style="App.TFrame")
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Calendar history", style="PanelTitle.TLabel", background=COLORS["bg"]).grid(row=0, column=0, sticky="w")
        ttk.Label(heading, text="Choose a day to inspect exactly what you completed.", style="Subtitle.TLabel", background=COLORS["bg"]).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(heading, text="Today", style="Secondary.TButton", command=self._calendar_today).grid(row=0, column=1, rowspan=2, sticky="e")

        calendar_card = ttk.Frame(page, style="Panel.TFrame", padding=16)
        calendar_card.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        calendar_card.columnconfigure(0, weight=1)
        calendar_card.rowconfigure(1, weight=1)
        month_bar = ttk.Frame(calendar_card, style="Panel.TFrame")
        month_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        month_bar.columnconfigure(1, weight=1)
        ttk.Button(month_bar, text="‹", style="Ghost.TButton", command=lambda: self._move_calendar_month(-1)).grid(row=0, column=0, sticky="w")
        self.calendar_month_label = ttk.Label(month_bar, text="", style="PanelTitle.TLabel")
        self.calendar_month_label.grid(row=0, column=1)
        ttk.Button(month_bar, text="›", style="Ghost.TButton", command=lambda: self._move_calendar_month(1)).grid(row=0, column=2, sticky="e")
        self.calendar_grid = tk.Frame(calendar_card, bg=COLORS["glass"], highlightthickness=0)
        self.calendar_grid.grid(row=1, column=0, sticky="nsew")
        for column in range(7):
            self.calendar_grid.columnconfigure(column, weight=1)
        for row_index in range(7):
            self.calendar_grid.rowconfigure(row_index, weight=1)

        detail_card = ttk.Frame(page, style="Panel.TFrame", padding=16)
        detail_card.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        detail_card.rowconfigure(4, weight=1)
        detail_card.columnconfigure(0, weight=1)
        self.calendar_day_label = ttk.Label(detail_card, text="", style="PanelTitle.TLabel")
        self.calendar_day_label.grid(row=0, column=0, sticky="w")
        self.calendar_focus_label = ttk.Label(detail_card, text="0 focused minutes", style="PanelText.TLabel")
        self.calendar_focus_label.grid(row=1, column=0, sticky="w", pady=(10, 2))
        self.calendar_sessions_label = ttk.Label(detail_card, text="0 focus sessions", style="Muted.TLabel")
        self.calendar_sessions_label.grid(row=2, column=0, sticky="w")
        self.calendar_breaks_label = ttk.Label(detail_card, text="0 breaks", style="Muted.TLabel")
        self.calendar_breaks_label.grid(row=3, column=0, sticky="w")
        filter_row = ttk.Frame(detail_card, style="Panel.TFrame")
        filter_row.grid(row=4, column=0, sticky="new", pady=(16, 8))
        filter_row.columnconfigure(1, weight=1)
        ttk.Label(filter_row, text="Show", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.calendar_filter_combo = ttk.Combobox(filter_row, values=("All sessions", "Focus only", "Breaks only"), state="readonly", width=15)
        self.calendar_filter_combo.set("All sessions")
        self.calendar_filter_combo.grid(row=0, column=1, sticky="ew")
        self.calendar_filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_calendar_detail())
        ttk.Label(filter_row, text="Task", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(8, 0))
        self.calendar_task_entry = ttk.Entry(filter_row)
        self.calendar_task_entry.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.calendar_task_entry.bind("<KeyRelease>", lambda _event: self.refresh_calendar_detail())
        self.calendar_tree = ttk.Treeview(detail_card, columns=("time", "type", "task", "minutes"), show="headings")
        for key, label, width, anchor in (("time", "Time", 72, "w"), ("type", "Type", 70, "center"), ("task", "Task", 150, "w"), ("minutes", "Min", 48, "center")):
            self.calendar_tree.heading(key, text=label)
            self.calendar_tree.column(key, width=width, anchor=anchor)
        self.calendar_tree.grid(row=5, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(detail_card, orient="vertical", command=self.calendar_tree.yview)
        scroll.grid(row=5, column=1, sticky="ns")
        self.calendar_tree.configure(yscrollcommand=scroll.set)
        self.refresh_calendar()

    def _move_calendar_month(self, offset):
        month_index = self.calendar_month.month - 1 + offset
        year = self.calendar_month.year + month_index // 12
        month = month_index % 12 + 1
        self.calendar_month = date(year, month, 1)
        self.refresh_calendar()

    def _calendar_today(self):
        self.calendar_selected_date = date.today()
        self.calendar_month = self.calendar_selected_date.replace(day=1)
        self.refresh_calendar()

    def _select_calendar_date(self, selected):
        self.calendar_selected_date = selected
        self.refresh_calendar()

    def refresh_calendar(self):
        if not getattr(self, "calendar_grid", None):
            return
        self.calendar_month_label.configure(text=self.calendar_month.strftime("%B %Y"))
        for child in self.calendar_grid.winfo_children():
            child.destroy()
        weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        for column, name in enumerate(weekdays):
            tk.Label(self.calendar_grid, text=name, bg=COLORS["glass"], fg=COLORS["muted"], font=("Segoe UI", 8, "bold")).grid(row=0, column=column, sticky="nsew", pady=(0, 4))
        session_days = {row["day"] for row in self.db.conn.execute("SELECT DISTINCT date(completed_at, 'localtime') AS day FROM sessions").fetchall()}
        first_weekday, number_of_days = calendar.monthrange(self.calendar_month.year, self.calendar_month.month)
        for day_number in range(1, number_of_days + 1):
            index = first_weekday + day_number - 1
            row_index, column = divmod(index, 7)
            selected = self.calendar_selected_date == date(self.calendar_month.year, self.calendar_month.month, day_number)
            day_text = str(day_number) + ("  •" if date(self.calendar_month.year, self.calendar_month.month, day_number).isoformat() in session_days else "")
            button = tk.Button(self.calendar_grid, text=day_text, command=lambda day=day_number: self._select_calendar_date(date(self.calendar_month.year, self.calendar_month.month, day)), bg=COLORS["accent"] if selected else COLORS["panel_alt"], fg="white" if selected else COLORS["text"], activebackground=COLORS["accent_dark"] if selected else COLORS["border"], activeforeground="white" if selected else COLORS["text"], relief="flat", bd=0, font=("Segoe UI", 9, "bold" if selected else "normal"))
            button.grid(row=row_index + 1, column=column, sticky="nsew", padx=2, pady=2, ipady=10)
        self.refresh_calendar_detail()

    def refresh_calendar_detail(self):
        if not getattr(self, "calendar_tree", None):
            return
        selected = self.calendar_selected_date
        self.calendar_day_label.configure(text=selected.strftime("%A, %B %d, %Y"))
        summary = self.db.summary_for_date(selected.isoformat())
        focus_minutes = int(summary["focus_seconds"] or 0) // 60
        self.calendar_focus_label.configure(text=f"{focus_minutes} focused minutes")
        self.calendar_sessions_label.configure(text=f"{int(summary['focus_sessions'] or 0)} focus sessions")
        self.calendar_breaks_label.configure(text=f"{int(summary['breaks'] or 0)} breaks")
        for item in self.calendar_tree.get_children():
            self.calendar_tree.delete(item)
        mode = str(self.calendar_filter_combo.get())
        task_filter = self.calendar_task_entry.get().strip().lower()
        for row in self.db.sessions_for_date(selected.isoformat()):
            is_focus = row["session_type"] == "focus"
            if mode == "Focus only" and not is_focus:
                continue
            if mode == "Breaks only" and is_focus:
                continue
            if task_filter and task_filter not in str(row["task_title"]).lower():
                continue
            completed = datetime.fromisoformat(row["completed_at"]).strftime("%I:%M %p").lstrip("0")
            kind = "Focus" if is_focus else "Break"
            self.calendar_tree.insert("", "end", values=(completed, kind, row["task_title"], row["duration_minutes"]))

    def _build_settings_view(self):
        page = ttk.Frame(self.view_container, style="App.TFrame")
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(1, weight=1)
        self._page_heading(page, "Settings", "Tune FocusFlow to match the way you work.")
        grid = ttk.Frame(page, style="App.TFrame")
        grid.grid(row=1, column=0, sticky="nsew")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        appearance = ttk.Frame(grid, style="Panel.TFrame", padding=20)
        appearance.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))
        timer = ttk.Frame(grid, style="Panel.TFrame", padding=20)
        timer.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))
        sound = ttk.Frame(grid, style="Panel.TFrame", padding=20)
        sound.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 12))
        ttk.Label(appearance, text="Appearance", style="PanelTitle.TLabel").pack(anchor="w")
        self.settings_theme_label = ttk.Label(appearance, style="PanelText.TLabel")
        self.settings_theme_label.pack(anchor="w", pady=(12, 4))
        ttk.Label(appearance, text="Use the header button to switch between light and dark themes. Your choice is saved automatically.", style="Muted.TLabel", wraplength=320).pack(anchor="w")
        ttk.Label(timer, text="Timer defaults", style="PanelTitle.TLabel").pack(anchor="w")
        self.settings_timer_label = ttk.Label(timer, style="PanelText.TLabel")
        self.settings_timer_label.pack(anchor="w", pady=(12, 4))
        ttk.Button(timer, text="Edit timer settings", style="Secondary.TButton", command=self.open_settings).pack(anchor="w", pady=(10, 0))
        ttk.Label(sound, text="Completion sound", style="PanelTitle.TLabel").pack(anchor="w")
        self.settings_sound_label = ttk.Label(sound, style="PanelText.TLabel")
        self.settings_sound_label.pack(anchor="w", pady=(12, 4))
        ttk.Button(sound, text="Edit sound settings", style="Secondary.TButton", command=self.open_settings).pack(anchor="w", pady=(10, 0))
        self.refresh_settings_page()

    def refresh_settings_page(self):
        if not getattr(self, "settings_theme_label", None):
            return
        theme_name = "Light" if self.theme == "light" else "Dark"
        self.settings_theme_label.configure(text=f"Current theme: {theme_name}")
        self.settings_timer_label.configure(text=f"Focus {self.settings.get('focus_minutes', '25')} min  •  Short break {self.settings.get('short_break_minutes', '5')} min  •  Long break {self.settings.get('long_break_minutes', '15')} min")
        sound_name = "Enabled" if self.settings.get("sound_enabled", "1") == "1" else "Disabled"
        notification_name = "Enabled" if self.settings.get("notifications_enabled", "1") == "1" else "Disabled"
        toast_name = "Enabled" if self.settings.get("toast_notifications", "1") == "1" else "Disabled"
        tray_name = "Enabled" if self.settings.get("tray_enabled", "1") == "1" else "Disabled"
        self.settings_sound_label.configure(text=f"Music: {sound_name}  •  Alert: {notification_name}  •  Toast: {toast_name}  •  Tray: {tray_name}")

    def refresh_history(self):
        if not getattr(self, "history_tree", None):
            return
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for row in self.db.all_sessions():
            completed = datetime.fromisoformat(row["completed_at"]).strftime("%b %d, %Y  %I:%M %p").replace(" 0", " ")
            kind = "Focus" if row["session_type"] == "focus" else "Break"
            self.history_tree.insert("", "end", values=(completed.split("  ")[0], kind, row["task_title"], row["duration_minutes"], completed.split("  ")[-1]))

    def export_history(self):
        rows = self.db.all_sessions()
        if not rows:
            messagebox.showinfo("Export history", "There are no completed sessions to export yet.")
            return
        path = filedialog.asksaveasfilename(title="Export focus history", defaultextension=".csv", filetypes=[("CSV files", "*.csv")], initialfile="focusflow-history.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Completed", "Type", "Task", "Planned minutes", "Actual seconds"])
            for row in rows:
                writer.writerow([row["completed_at"], row["session_type"], row["task_title"], row["duration_minutes"], row["actual_seconds"]])
        messagebox.showinfo("Export complete", f"Your history was exported to:\n{path}")

    def _build_task_panel(self):
        ttk.Label(self.left_panel, text="Today’s tasks", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(self.left_panel, text="Add a task, then assign its own focus duration.", style="Muted.TLabel", wraplength=270).pack(anchor="w", pady=(4, 16))

        form = tk.Frame(self.left_panel, bg=COLORS["glass"])
        form.pack(fill="x")
        self.task_entry = tk.Entry(form, bg=COLORS["input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", highlightthickness=1, highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"], font=("Segoe UI", 10))
        self.task_entry.pack(fill="x", ipady=9, pady=(0, 10))
        self.task_entry.bind("<Return>", lambda _event: self.add_task())
        row = tk.Frame(form, bg=COLORS["glass"])
        row.pack(fill="x", pady=(0, 10))
        tk.Label(row, text="Sessions", bg=COLORS["glass"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(side="left")
        self.planned_var = tk.IntVar(value=4)
        tk.Spinbox(row, from_=1, to=99, textvariable=self.planned_var, width=5, bg=COLORS["input"], fg=COLORS["text"], buttonbackground=COLORS["accent_soft"], relief="flat", highlightthickness=1, highlightbackground=COLORS["border"], insertbackground=COLORS["text"]).pack(side="left", padx=(7, 18))
        tk.Label(row, text="Focus min", bg=COLORS["glass"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(side="left")
        self.focus_var = tk.IntVar(value=int(self.settings.get("focus_minutes", "25")))
        tk.Spinbox(row, from_=1, to=180, textvariable=self.focus_var, width=5, bg=COLORS["input"], fg=COLORS["text"], buttonbackground=COLORS["accent_soft"], relief="flat", highlightthickness=1, highlightbackground=COLORS["border"], insertbackground=COLORS["text"]).pack(side="left", padx=(7, 0))
        ttk.Button(form, text="＋  Add task", style="Accent.TButton", command=self.add_task).pack(fill="x")

        ttk.Separator(self.left_panel).pack(fill="x", pady=18)
        self.task_tree = ttk.Treeview(self.left_panel, columns=("task", "progress", "minutes", "status", "priority", "due"), show="headings", selectmode="browse", height=12)
        self.task_tree.heading("task", text="Task")
        self.task_tree.heading("progress", text="Done")
        self.task_tree.heading("minutes", text="Min")
        self.task_tree.heading("status", text="Status")
        self.task_tree.heading("priority", text="Priority")
        self.task_tree.heading("due", text="Due")
        self.task_tree.column("task", width=145, anchor="w")
        self.task_tree.column("progress", width=50, anchor="center")
        self.task_tree.column("minutes", width=42, anchor="center")
        self.task_tree.column("status", width=82, anchor="center")
        self.task_tree.column("priority", width=62, anchor="center")
        self.task_tree.column("due", width=78, anchor="center")
        self.task_tree.pack(fill="both", expand=True)
        self.task_tree.bind("<<TreeviewSelect>>", self.on_task_select)
        self.task_tree.bind("<Double-1>", lambda _event: self.start_selected_task())

        actions = ttk.Frame(self.left_panel, style="Panel.TFrame")
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Start selected", style="Secondary.TButton", command=self.start_selected_task).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(actions, text="Edit", style="Secondary.TButton", command=self.edit_selected_task).pack(side="left", padx=4)
        ttk.Button(actions, text="Delete", style="Secondary.TButton", command=self.delete_selected_task).pack(side="right", padx=(4, 0))

    def _build_timer_panel(self):
        self.mode_label = ttk.Label(self.center_panel, text="FOCUS SESSION", style="Mode.TLabel")
        self.mode_label.pack(anchor="center", pady=(15, 4))
        self.active_task_label = ttk.Label(self.center_panel, text="Select a task to begin", style="HeroTitle.TLabel")
        self.active_task_label.pack(anchor="center")
        self.timer_label = ttk.Label(self.center_panel, text="25:00", style="Timer.TLabel")
        self.timer_label.pack(anchor="center", pady=(28, 12))
        self.timer_progress = ttk.Progressbar(self.center_panel, style="Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.timer_progress.pack(fill="x", padx=25)
        self.timer_status = ttk.Label(self.center_panel, text="Ready when you are.", style="HeroMuted.TLabel")
        self.timer_status.pack(anchor="center", pady=(10, 30))

        controls = ttk.Frame(self.center_panel, style="Hero.TFrame")
        controls.pack(anchor="center")
        self.start_button = ttk.Button(controls, text="Start", style="Accent.TButton", command=self.start_timer)
        self.start_button.grid(row=0, column=0, padx=4)
        self.pause_button = ttk.Button(controls, text="Pause", style="Secondary.TButton", command=self.pause_timer)
        self.pause_button.grid(row=0, column=1, padx=4)
        ttk.Button(controls, text="Reset", style="Secondary.TButton", command=self.reset_timer).grid(row=0, column=2, padx=4)
        ttk.Button(controls, text="Skip", style="Secondary.TButton", command=self.skip_timer).grid(row=0, column=3, padx=4)

        help_text = "Focus sessions are recorded when they finish. Breaks are not added to your focus total."
        ttk.Label(self.center_panel, text=help_text, style="HeroMuted.TLabel", wraplength=430, justify="center").pack(anchor="center", pady=(34, 0))

    def _build_summary_panel(self):
        ttk.Label(self.right_panel, text="Today’s progress", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(self.right_panel, text="A quiet view of what you accomplished.", style="Muted.TLabel", wraplength=240).pack(anchor="w", pady=(4, 16))
        cards = ttk.Frame(self.right_panel, style="Panel.TFrame")
        cards.pack(fill="x")
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)
        self.summary_vars = {}
        card_specs = [("sessions", "0", "sessions"), ("minutes", "0", "focused minutes"), ("remaining", "0", "planned left"), ("rate", "0%", "completion rate")]
        for index, (key, value, caption) in enumerate(card_specs):
            frame = tk.Frame(cards, bg=COLORS["panel_alt"], padx=12, pady=10, highlightthickness=1, highlightbackground=COLORS["border"])
            frame.grid(row=index // 2, column=index % 2, sticky="nsew", padx=3, pady=3)
            self.summary_vars[key] = tk.StringVar(value=value)
            tk.Label(frame, textvariable=self.summary_vars[key], bg=COLORS["panel_alt"], fg=COLORS["text"], font=("Segoe UI", 19, "bold")).pack(anchor="w")
            tk.Label(frame, text=caption, bg=COLORS["panel_alt"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")

        ttk.Separator(self.right_panel).pack(fill="x", pady=18)
        ttk.Label(self.right_panel, text="Recent activity", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 8))
        self.activity_tree = ttk.Treeview(self.right_panel, columns=("type", "task", "when"), show="headings", height=9)
        self.activity_tree.heading("type", text="Type")
        self.activity_tree.heading("task", text="Task")
        self.activity_tree.heading("when", text="Time")
        self.activity_tree.column("type", width=52, anchor="center")
        self.activity_tree.column("task", width=125, anchor="w")
        self.activity_tree.column("when", width=58, anchor="center")
        self.activity_tree.pack(fill="both", expand=True)
        self.tip_label = ttk.Label(self.right_panel, text="Tip: small, specific tasks make it easier to start.", style="Muted.TLabel", wraplength=230)
        self.tip_label.pack(anchor="w", pady=(15, 0))

    def _refresh_all(self):
        self.date_label.configure(text=datetime.now().strftime("%A, %B %d, %Y"))
        self.refresh_tasks()
        self.refresh_summary()
        self.refresh_activity()
        self.refresh_history()
        self.refresh_analytics()
        self.refresh_calendar()
        self.refresh_settings_page()
        self.refresh_active_task_label()

    def refresh_tasks(self):
        if not getattr(self, "task_tree", None):
            return
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
        today_counts = self.db.today_task_counts()
        rows = self.db.list_tasks()
        for row in rows:
            progress = f"{today_counts.get(int(row['id']), 0)}/{row['planned_sessions']}"
            marker = " ✓" if row["completed_sessions"] >= row["planned_sessions"] else ""
            due = row["due_date"] or "—"
            self.task_tree.insert("", "end", iid=str(row["id"]), values=(row["title"] + marker, progress, row["focus_minutes"], row["status"], row["priority"], due))
        if self.selected_task_id is not None and self.task_tree.exists(str(self.selected_task_id)):
            self.task_tree.selection_set(str(self.selected_task_id))
            self.task_tree.see(str(self.selected_task_id))

    def refresh_summary(self):
        if not getattr(self, "summary_vars", None):
            return
        sessions = [row for row in self.db.today_sessions() if row["session_type"] == "focus"]
        minutes = sum(int(row["actual_seconds"] or row["duration_minutes"] * 60) for row in sessions) // 60
        tasks = self.db.list_tasks()
        planned = sum(int(row["planned_sessions"]) for row in tasks)
        complete = len(sessions)
        remaining = max(0, planned - complete)
        rate = int((complete / planned) * 100) if planned else 0
        self.summary_vars["sessions"].set(str(complete))
        self.summary_vars["minutes"].set(str(minutes))
        self.summary_vars["remaining"].set(str(remaining))
        self.summary_vars["rate"].set(f"{rate}%")

    def refresh_activity(self):
        if not getattr(self, "activity_tree", None):
            return
        for item in self.activity_tree.get_children():
            self.activity_tree.delete(item)
        for row in self.db.today_sessions()[:12]:
            completed = datetime.fromisoformat(row["completed_at"]).strftime("%I:%M %p").lstrip("0")
            kind = "Focus" if row["session_type"] == "focus" else "Break"
            self.activity_tree.insert("", "end", values=(kind, row["task_title"], completed))

    def on_task_select(self, _event=None):
        selection = self.task_tree.selection()
        if not selection:
            return
        self.selected_task_id = int(selection[0])
        if self.mode == "focus" and not self.running:
            self._reset_timer_for_mode()
        self.refresh_active_task_label()

    def refresh_active_task_label(self):
        if not getattr(self, "active_task_label", None):
            return
        task = self.db.get_task(self.selected_task_id) if self.selected_task_id else None
        if task:
            self.active_task_label.configure(text=task["title"])
        elif self.mode == "focus":
            self.active_task_label.configure(text="Select a task to begin")
        else:
            self.active_task_label.configure(text="Rest and come back refreshed")

    def add_task(self):
        title = self.task_entry.get().strip()
        if not title:
            messagebox.showwarning("Add a task", "Give your task a short, specific name first.")
            self.task_entry.focus_set()
            return
        try:
            planned = max(1, min(99, int(self.planned_var.get())))
            focus = max(1, min(180, int(self.focus_var.get())))
        except (ValueError, tk.TclError):
            messagebox.showwarning("Check task settings", "Sessions and focus minutes must be whole numbers.")
            return
        task_id = self.db.add_task(title, planned, focus)
        self.task_entry.delete(0, "end")
        self.selected_task_id = task_id
        self.mode = "focus"
        self._refresh_all()
        self._reset_timer_for_mode()
        self.task_tree.selection_set(str(task_id))
        self.task_tree.see(str(task_id))

    def start_selected_task(self):
        selection = self.task_tree.selection()
        if selection:
            self.selected_task_id = int(selection[0])
            self.mode = "focus"
            self._reset_timer_for_mode()
        self.start_timer()

    def edit_selected_task(self):
        if not self.selected_task_id:
            messagebox.showinfo("Edit task", "Select a task first.")
            return
        task = self.db.get_task(self.selected_task_id)
        if not task:
            return
        window = tk.Toplevel(self.root)
        window.title("Edit task")
        window.geometry("440x470")
        window.resizable(False, False)
        window.configure(bg=COLORS["glass"])
        window.transient(self.root)
        window.grab_set()
        outer = tk.Frame(window, bg=COLORS["glass"], padx=24, pady=22)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="Edit task", bg=COLORS["glass"], fg=COLORS["text"], font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(outer, text="Keep the plan clear so every session has a purpose.", bg=COLORS["glass"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 18))

        title_var = tk.StringVar(value=task["title"])
        planned_var = tk.StringVar(value=str(task["planned_sessions"]))
        focus_var = tk.StringVar(value=str(task["focus_minutes"]))
        priority_var = tk.StringVar(value=task["priority"] or "Normal")
        status_var = tk.StringVar(value=task["status"] or "Not started")
        due_var = tk.StringVar(value=task["due_date"] or "")

        def labeled_entry(label, variable, hint=""):
            row = tk.Frame(outer, bg=COLORS["glass"])
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, bg=COLORS["glass"], fg=COLORS["text"], font=("Segoe UI", 9)).pack(anchor="w")
            tk.Entry(row, textvariable=variable, bg=COLORS["input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", highlightthickness=1, highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"]).pack(fill="x", ipady=6, pady=(4, 0))
            if hint:
                tk.Label(row, text=hint, bg=COLORS["glass"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

        labeled_entry("Task name", title_var)
        split = tk.Frame(outer, bg=COLORS["glass"])
        split.pack(fill="x", pady=5)
        left = tk.Frame(split, bg=COLORS["glass"])
        left.pack(side="left", fill="x", expand=True, padx=(0, 6))
        right = tk.Frame(split, bg=COLORS["glass"])
        right.pack(side="right", fill="x", expand=True, padx=(6, 0))
        tk.Label(left, text="Planned sessions", bg=COLORS["glass"], fg=COLORS["text"], font=("Segoe UI", 9)).pack(anchor="w")
        tk.Entry(left, textvariable=planned_var, bg=COLORS["input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", highlightthickness=1, highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"]).pack(fill="x", ipady=6, pady=(4, 0))
        tk.Label(right, text="Focus minutes", bg=COLORS["glass"], fg=COLORS["text"], font=("Segoe UI", 9)).pack(anchor="w")
        tk.Entry(right, textvariable=focus_var, bg=COLORS["input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", highlightthickness=1, highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"]).pack(fill="x", ipady=6, pady=(4, 0))

        def combo_row(label, variable, values):
            row = tk.Frame(outer, bg=COLORS["glass"])
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, bg=COLORS["glass"], fg=COLORS["text"], font=("Segoe UI", 9)).pack(side="left")
            box = ttk.Combobox(row, textvariable=variable, values=values, state="readonly", width=18)
            box.pack(side="right")

        combo_row("Priority", priority_var, ("Low", "Normal", "High"))
        combo_row("Status", status_var, ("Not started", "In progress", "Paused", "Completed"))
        labeled_entry("Due date", due_var, "Optional format: YYYY-MM-DD")

        def save_task():
            title = title_var.get().strip()
            try:
                planned = max(1, min(99, int(planned_var.get())))
                focus = max(1, min(180, int(focus_var.get())))
            except ValueError:
                messagebox.showwarning("Check task", "Sessions and focus minutes must be whole numbers.", parent=window)
                return
            if not title:
                messagebox.showwarning("Check task", "A task name is required.", parent=window)
                return
            due = due_var.get().strip()
            if due:
                try:
                    datetime.strptime(due, "%Y-%m-%d")
                except ValueError:
                    messagebox.showwarning("Check due date", "Use the format YYYY-MM-DD or leave it blank.", parent=window)
                    return
            self.db.update_task(self.selected_task_id, title, planned, focus, priority_var.get(), status_var.get(), due)
            window.destroy()
            if not self.running and self.mode == "focus":
                self._reset_timer_for_mode()
            self._refresh_all()

        buttons = tk.Frame(outer, bg=COLORS["glass"])
        buttons.pack(fill="x", pady=(20, 0))
        ttk.Button(buttons, text="Cancel", style="Secondary.TButton", command=window.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save task", style="Accent.TButton", command=save_task).pack(side="right")

    def delete_selected_task(self):
        if not self.selected_task_id:
            messagebox.showinfo("Delete task", "Select a task first.")
            return
        task = self.db.get_task(self.selected_task_id)
        if not task:
            return
        if not messagebox.askyesno("Delete task", f"Remove ‘{task['title']}’ from your task list?"):
            return
        self.db.archive_task(self.selected_task_id)
        self.selected_task_id = None
        self.mode = "focus"
        self.reset_timer()
        self._refresh_all()

    def _duration_for_mode(self) -> int:
        if self.mode == "focus":
            task = self.db.get_task(self.selected_task_id) if self.selected_task_id else None
            return int(task["focus_minutes"]) if task else int(self.settings.get("focus_minutes", "25"))
        if self.mode == "short_break":
            return int(self.settings.get("short_break_minutes", "5"))
        return int(self.settings.get("long_break_minutes", "15"))

    def _persist_active_session(self):
        if self.session_started_at and (self.running or self.remaining_seconds < self.total_seconds):
            payload = {
                "task_id": self.selected_task_id,
                "mode": self.mode,
                "total_seconds": self.total_seconds,
                "remaining_seconds": self.remaining_seconds,
                "session_started_at": self.session_started_at,
                "deadline": self.session_deadline,
                "running": self.running,
                "saved_at": time.time(),
            }
            self.db.save_settings({"active_session": json.dumps(payload)})
        else:
            self.db.save_settings({"active_session": ""})

    def _restore_active_session(self):
        if self.recovery_prompt_shown:
            return
        self.recovery_prompt_shown = True
        raw = self.settings.get("active_session", "").strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
            total = max(1, int(data.get("total_seconds", 1)))
            remaining = max(0, int(data.get("remaining_seconds", total)))
            mode = data.get("mode", "focus")
            if mode not in {"focus", "short_break", "long_break"}:
                raise ValueError
            deadline = data.get("deadline")
            if data.get("running") and deadline:
                remaining = max(0, int(float(deadline) - time.time()))
            if remaining <= 0:
                self.db.save_settings({"active_session": ""})
                return
            task_id = data.get("task_id")
            if task_id is not None:
                task_id = int(task_id)
            task = self.db.get_task(task_id) if task_id else None
            description = task["title"] if task else ("your break" if mode != "focus" else "your task")
            if not messagebox.askyesno("Resume session?", f"FocusFlow found an unfinished session for {description}.\\n\\nResume the remaining {self._format_seconds(remaining)}?", parent=self.root):
                self.db.save_settings({"active_session": ""})
                return
            self.selected_task_id = task_id
            self.mode = mode
            self.total_seconds = total
            self.remaining_seconds = remaining
            self.session_started_at = data.get("session_started_at") or datetime.now().isoformat(timespec="seconds")
            self.session_deadline = time.time() + remaining if data.get("running") else None
            self.show_view("dashboard")
            if data.get("running"):
                self.running = True
                self.start_button.configure(text="Running…")
                self._tick()
            else:
                self.running = False
                self.start_button.configure(text="Resume")
                self._update_timer_display()
        except (ValueError, TypeError, json.JSONDecodeError):
            self.db.save_settings({"active_session": ""})

    def _format_seconds(self, seconds: int) -> str:
        minutes, remainder = divmod(max(0, int(seconds)), 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} {remainder:02d} seconds"

    def _reset_timer_for_mode(self):
        self._cancel_timer_job()
        self.running = False
        self.total_seconds = max(1, self._duration_for_mode() * 60)
        self.remaining_seconds = self.total_seconds
        self.session_started_at = None
        self.session_deadline = None
        self._persist_active_session()
        self._update_timer_display()
        if getattr(self, "start_button", None):
            self.start_button.configure(text="Start")
        if getattr(self, "pause_button", None):
            self.pause_button.configure(state="normal")
        self.refresh_active_task_label()

    def _update_timer_display(self):
        if not getattr(self, "timer_label", None):
            return
        minutes, seconds = divmod(max(0, self.remaining_seconds), 60)
        self.timer_label.configure(text=f"{minutes:02d}:{seconds:02d}")
        progress = 100 * (1 - self.remaining_seconds / self.total_seconds) if self.total_seconds else 0
        self.timer_progress.configure(value=progress)
        if self.mode == "focus":
            self.mode_label.configure(text="FOCUS SESSION", foreground=COLORS["accent"])
            self.timer_status.configure(text="Stay with one thing until the bell.")
        elif self.mode == "short_break":
            self.mode_label.configure(text="SHORT BREAK", foreground=COLORS["green"])
            self.timer_status.configure(text="Step away for a moment.")
        else:
            self.mode_label.configure(text="LONG BREAK", foreground=COLORS["blue"])
            self.timer_status.configure(text="You earned a longer reset.")

    def start_timer(self):
        if self.mode == "focus" and not self.selected_task_id:
            messagebox.showinfo("Choose a task", "Select or add a task before starting a focus session.")
            return
        if self.mode == "focus" and self.selected_task_id:
            self.db.set_task_status(self.selected_task_id, "In progress")
        if not getattr(self, "start_button", None):
            self.show_view("dashboard")
        if self.running:
            return
        if self.remaining_seconds <= 0:
            self._reset_timer_for_mode()
        self.running = True
        if self.session_started_at is None:
            self.session_started_at = datetime.now().isoformat(timespec="seconds")
        self.session_deadline = time.time() + self.remaining_seconds
        self.last_timer_persist_at = time.time()
        self._persist_active_session()
        if self.start_button:
            self.start_button.configure(text="Running…")
        self._tick()

    def pause_timer(self):
        if self.running:
            self._update_remaining_from_clock()
            self.running = False
            self.session_deadline = None
            if self.mode == "focus" and self.selected_task_id:
                self.db.set_task_status(self.selected_task_id, "Paused")
            self._cancel_timer_job()
            self._persist_active_session()
            if self.start_button:
                self.start_button.configure(text="Resume")
            if self.timer_status:
                self.timer_status.configure(text="Paused. Resume whenever you are ready.")

    def reset_timer(self):
        self._reset_timer_for_mode()
        self._persist_active_session()
        if self.timer_status:
            self.timer_status.configure(text="Timer reset.")

    def skip_timer(self):
        if self.running:
            self.pause_timer()
        if self.mode == "focus":
            self._prepare_break()
        else:
            self.mode = "focus"
            self._reset_timer_for_mode()
        self.refresh_active_task_label()

    def _update_remaining_from_clock(self):
        if self.running and self.session_deadline is not None:
            self.remaining_seconds = max(0, int(round(self.session_deadline - time.time())))

    def _tick(self):
        if not self.running:
            return
        self._update_remaining_from_clock()
        self._update_timer_display()
        now = time.time()
        if self.remaining_seconds <= 0:
            self.running = False
            self.session_deadline = None
            self._cancel_timer_job()
            self._persist_active_session()
            self._finish_current_session()
            return
        if now - self.last_timer_persist_at >= 5:
            self.last_timer_persist_at = now
            self._persist_active_session()
        self.timer_job = self.root.after(250, self._tick)

    def _finish_current_session(self):
        duration_minutes = self.total_seconds // 60
        actual_seconds = self.total_seconds
        if self.mode == "focus":
            self.db.increment_task(self.selected_task_id)
            self.db.record_session(self.selected_task_id, "focus", duration_minutes, actual_seconds, self.session_started_at or datetime.now().isoformat(timespec="seconds"))
            self.completed_focus_since_long_break += 1
            task = self.db.get_task(self.selected_task_id)
            if task:
                next_status = "Completed" if int(task["completed_sessions"]) >= int(task["planned_sessions"]) else "In progress"
                self.db.set_task_status(self.selected_task_id, next_status)
            self._play_completion_sound()
            task_title = task["title"] if task else "your task"
            self._notify_completion("Focus session complete", f"Nice work on {task_title}.")
            messagebox.showinfo("Focus session complete", f"Nice work on ‘{task_title}’. Your session has been recorded.")
            self._prepare_break()
        else:
            self.db.record_session(self.selected_task_id, self.mode, duration_minutes, actual_seconds, self.session_started_at or datetime.now().isoformat(timespec="seconds"))
            self._play_completion_sound()
            self._notify_completion("Break complete", "Your break is over. Ready for another focused session?")
            messagebox.showinfo("Break complete", "Your break is over. Ready for another focused session?")
            self.mode = "focus"
            self._reset_timer_for_mode()
        self._refresh_all()

    def _prepare_break(self):
        before_long = max(1, int(self.settings.get("sessions_before_long_break", "4")))
        self.mode = "long_break" if self.completed_focus_since_long_break >= before_long else "short_break"
        if self.mode == "long_break":
            self.completed_focus_since_long_break = 0
        self._reset_timer_for_mode()

    def _notify_completion(self, title: str, message: str):
        if self.settings.get("notifications_enabled", "1") != "1":
            return
        try:
            self.root.bell()
            if os.name == "nt" and hasattr(ctypes, "windll"):
                ctypes.windll.user32.MessageBeep(0x40)
        except Exception:
            pass
        if self.settings.get("toast_notifications", "1") != "1" or windows_toast is None:
            return

        def send_toast():
            try:
                windows_toast(title, message, duration="short")
            except Exception:
                pass

        threading.Thread(target=send_toast, name="FocusFlowToast", daemon=True).start()

    def _play_completion_sound(self):
        if self.settings.get("sound_enabled", "1") != "1":
            return
        custom = self.settings.get("custom_sound", "").strip()

        def play():
            try:
                if winsound is None:
                    return
                if custom and Path(custom).exists():
                    for index in range(3):
                        winsound.PlaySound(custom, winsound.SND_FILENAME)
                        if index < 2:
                            time.sleep(0.12)
                else:
                    for index, (frequency, duration) in enumerate(((880, 150), (1047, 150), (1319, 240))):
                        winsound.Beep(frequency, duration)
                        if index < 2:
                            time.sleep(0.08)
            except Exception:
                pass

        threading.Thread(target=play, daemon=True).start()

    def open_settings(self):
        window = tk.Toplevel(self.root)
        window.title("FocusFlow Settings")
        window.geometry("430x440")
        window.resizable(False, False)
        window.configure(bg=COLORS["glass"])
        window.transient(self.root)
        window.grab_set()

        outer = tk.Frame(window, bg=COLORS["glass"], padx=24, pady=22)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="Timer settings", bg=COLORS["glass"], fg=COLORS["text"], font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(outer, text="Defaults apply to new tasks and upcoming breaks.", bg=COLORS["glass"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 18))

        fields = [("Default focus minutes", "focus_minutes"), ("Short break minutes", "short_break_minutes"), ("Long break minutes", "long_break_minutes"), ("Sessions before long break", "sessions_before_long_break")]
        vars_map = {}
        for label, key in fields:
            row = tk.Frame(outer, bg=COLORS["glass"])
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, bg=COLORS["glass"], fg=COLORS["text"], font=("Segoe UI", 9)).pack(side="left")
            var = tk.StringVar(value=self.settings.get(key, "25"))
            vars_map[key] = var
            tk.Entry(row, textvariable=var, width=8, bg=COLORS["input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", highlightthickness=1, highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"], justify="right").pack(side="right", ipady=5)

        sound_var = tk.BooleanVar(value=self.settings.get("sound_enabled", "1") == "1")
        tk.Checkbutton(outer, text="Play completion music", variable=sound_var, bg=COLORS["glass"], fg=COLORS["text"], activebackground=COLORS["accent_soft"], activeforeground=COLORS["text"], selectcolor=COLORS["input"], font=("Segoe UI", 9)).pack(anchor="w", pady=(15, 8))
        notification_var = tk.BooleanVar(value=self.settings.get("notifications_enabled", "1") == "1")
        tk.Checkbutton(outer, text="Use Windows completion alert sound", variable=notification_var, bg=COLORS["glass"], fg=COLORS["text"], activebackground=COLORS["accent_soft"], activeforeground=COLORS["text"], selectcolor=COLORS["input"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))
        toast_var = tk.BooleanVar(value=self.settings.get("toast_notifications", "1") == "1")
        tk.Checkbutton(outer, text="Show Windows corner toast notification", variable=toast_var, bg=COLORS["glass"], fg=COLORS["text"], activebackground=COLORS["accent_soft"], activeforeground=COLORS["text"], selectcolor=COLORS["input"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))
        tray_var = tk.BooleanVar(value=self.settings.get("tray_enabled", "1") == "1")
        tk.Checkbutton(outer, text="Enable system-tray controls", variable=tray_var, bg=COLORS["glass"], fg=COLORS["text"], activebackground=COLORS["accent_soft"], activeforeground=COLORS["text"], selectcolor=COLORS["input"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))
        sound_row = tk.Frame(outer, bg=COLORS["glass"])
        sound_row.pack(fill="x")
        sound_var_path = tk.StringVar(value=self.settings.get("custom_sound", ""))
        tk.Entry(sound_row, textvariable=sound_var_path, bg=COLORS["input"], fg=COLORS["muted"], insertbackground=COLORS["text"], relief="flat", highlightthickness=1, highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"]).pack(side="left", fill="x", expand=True, ipady=5)
        ttk.Button(sound_row, text="Browse WAV", style="Secondary.TButton", command=lambda: self._browse_sound(sound_var_path)).pack(side="right", padx=(8, 0))
        tk.Label(outer, text="Leave the WAV path blank to use FocusFlow’s built-in chime.", bg=COLORS["glass"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", pady=(5, 0))

        def save():
            try:
                values = {}
                for key, var in vars_map.items():
                    number = int(var.get())
                    if number < 1 or number > 180:
                        raise ValueError
                    values[key] = str(number)
                values["sound_enabled"] = "1" if sound_var.get() else "0"
                values["notifications_enabled"] = "1" if notification_var.get() else "0"
                values["toast_notifications"] = "1" if toast_var.get() else "0"
                values["tray_enabled"] = "1" if tray_var.get() else "0"
                values["custom_sound"] = sound_var_path.get().strip()
            except ValueError:
                messagebox.showwarning("Check settings", "Use whole numbers from 1 to 180.", parent=window)
                return
            self.db.save_settings(values)
            self.settings = self.db.get_settings()
            window.destroy()
            if not self.running:
                self._reset_timer_for_mode()
            self.refresh_summary()

        buttons = tk.Frame(outer, bg=COLORS["glass"])
        buttons.pack(fill="x", pady=(25, 0))
        ttk.Button(buttons, text="Cancel", style="Secondary.TButton", command=window.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save settings", style="Accent.TButton", command=save).pack(side="right")

    def _browse_sound(self, target_var: tk.StringVar):
        path = filedialog.askopenfilename(title="Choose completion music", filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")])
        if path:
            target_var.set(path)

    def _cancel_timer_job(self):
        if self.timer_job is not None:
            try:
                self.root.after_cancel(self.timer_job)
            except tk.TclError:
                pass
            self.timer_job = None

    def close(self):
        self._update_remaining_from_clock()
        self._persist_active_session()
        self._cancel_timer_job()
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        self.db.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = FocusFlowApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
