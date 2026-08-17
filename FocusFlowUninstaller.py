import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "FocusFlow"
APP_EXE = "FocusFlow.exe"
UNINSTALLER_EXE = "FocusFlowUninstaller.exe"
UNINSTALL_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\FocusFlow"
DATA_RESET_MARKER_NAME = "FocusFlow.remove-data"


def bundle_path(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / name


def install_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / APP_NAME


def data_reset_marker_path() -> Path:
    return user_data_directory().parent / DATA_RESET_MARKER_NAME


def shortcut_paths():
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    start_menu = Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
    return desktop / "FocusFlow.lnk", start_menu / "FocusFlow.lnk", start_menu / "Uninstall FocusFlow.lnk"


def remove_registry_registration():
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REGISTRY_PATH)
    except (FileNotFoundError, OSError, ImportError):
        pass


def terminate_running_app():
    if os.name != "nt":
        return
    for process_name in (APP_EXE,):
        subprocess.run(
            ["taskkill.exe", "/IM", process_name, "/F", "/T"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def _remove_readonly(func, path, _exc_info):
    """Allow shutil.rmtree to remove files marked read-only on Windows."""
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    func(path)


def remove_tree(path: Path) -> bool:
    """Remove a file or directory tree and report whether it is gone."""
    path = Path(path)
    if not path.exists():
        return True
    try:
        if path.is_dir():
            shutil.rmtree(path, onerror=_remove_readonly)
        else:
            try:
                path.chmod(stat.S_IWRITE)
            except OSError:
                pass
            path.unlink()
    except (OSError, shutil.Error):
        return False
    return not path.exists()


def _powershell_quote(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def schedule_cleanup(paths):
    """Schedule deletion outside the running uninstaller, with retries for locked files."""
    targets = [Path(path).resolve() for path in paths if path]
    targets = list(dict.fromkeys(targets))
    if not targets:
        return
    if os.name != "nt":
        for target in targets:
            remove_tree(target)
        return
    script_path = Path(tempfile.gettempdir()) / f"FocusFlowCleanup_{os.getpid()}.ps1"
    target_lines = ",\n        ".join(_powershell_quote(target) for target in targets)
    script = f"""$targets = @(
        {target_lines}
    )
    Start-Sleep -Milliseconds 1200
    for ($attempt = 0; $attempt -lt 40; $attempt++) {{
        foreach ($target in $targets) {{
            if (Test-Path -LiteralPath $target) {{
                try {{
                    Get-ChildItem -LiteralPath $target -Force -Recurse -ErrorAction SilentlyContinue | ForEach-Object {{
                        try {{ $_.Attributes = 'Normal' }} catch {{}}
                    }}
                    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop
                }} catch {{}}
            }}
        }}
        $remaining = @($targets | Where-Object {{ Test-Path -LiteralPath $_ }})
        if ($remaining.Count -eq 0) {{ break }}
        Start-Sleep -Milliseconds 500
    }}
    Remove-Item -LiteralPath {_powershell_quote(script_path)} -Force -ErrorAction SilentlyContinue
    """
    try:
        script_path.write_text(script, encoding="utf-8")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script_path)],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
    except OSError:
        for target in targets:
            remove_tree(target)


class UninstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.install_dir = install_directory()
        self.data_dir = user_data_directory()
        self.setWindowTitle("Uninstall FocusFlow")
        self.setMinimumSize(620, 430)
        self.resize(680, 470)
        icon_path = self.install_dir / "focusflow.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(34, 30, 34, 30)
        outer.setSpacing(18)

        header = QFrame(objectName="hero")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        eyebrow = QLabel("FOCUSFLOW")
        eyebrow.setObjectName("eyebrow")
        header_layout.addWidget(eyebrow)
        title = QLabel("Uninstall FocusFlow")
        title.setObjectName("title")
        header_layout.addWidget(title)
        subtitle = QLabel("Remove the application from this Windows account.")
        subtitle.setObjectName("muted")
        header_layout.addWidget(subtitle)
        outer.addWidget(header)

        card = QFrame(objectName="card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(14)
        explanation = QLabel(
            "FocusFlow will be removed from its installation folder and its shortcuts will be deleted. "
            "Your local tasks, settings, session history, and saved name are kept unless you choose otherwise."
        )
        explanation.setObjectName("muted")
        explanation.setWordWrap(True)
        card_layout.addWidget(explanation)

        self.remove_data = QCheckBox("Also remove my local FocusFlow data")
        self.remove_data.setChecked(False)
        card_layout.addWidget(self.remove_data)
        data_note = QLabel(f"Stored locally in: {self.data_dir}")
        data_note.setObjectName("muted")
        data_note.setWordWrap(True)
        card_layout.addWidget(data_note)
        outer.addWidget(card, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        buttons.addWidget(cancel)
        self.uninstall_button = QPushButton("Uninstall FocusFlow")
        self.uninstall_button.setObjectName("primary")
        self.uninstall_button.setDefault(True)
        self.uninstall_button.clicked.connect(self.confirm_uninstall)
        buttons.addWidget(self.uninstall_button)
        outer.addLayout(buttons)

    def _apply_style(self):
        self.setStyleSheet("""
        QWidget { color: #172033; font-family: 'Segoe UI'; font-size: 10pt; }
        QMainWindow { background: #F3F5FB; }
        QFrame#hero { background: #F0EAFE; border: 1px solid #DDD0FF; border-radius: 20px; }
        QFrame#card { background: #FFFFFF; border: 1px solid #E4E7F0; border-radius: 20px; }
        QLabel#title { color: #172033; font-size: 24pt; font-weight: 800; }
        QLabel#eyebrow { color: #7C3AED; font-size: 8pt; font-weight: 800; letter-spacing: 2px; }
        QLabel#muted { color: #667085; }
        QPushButton { background: #FFFFFF; color: #172033; border: 1px solid #E4E7F0; border-radius: 12px; padding: 11px 16px; font-weight: 700; }
        QPushButton:hover { background: #EDE9FE; border-color: #A78BFA; }
        QPushButton#primary { background: #7C3AED; color: white; border: none; padding: 12px 18px; }
        QPushButton#primary:hover { background: #5B21B6; }
        QCheckBox { color: #172033; spacing: 8px; font-weight: 700; }
        """)

    def confirm_uninstall(self):
        if self.remove_data.isChecked():
            answer = QMessageBox.question(
                self,
                "Remove local data?",
                "This will permanently delete your FocusFlow tasks, settings, session history, and saved name. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        else:
            answer = QMessageBox.question(
                self,
                "Confirm uninstall",
                "Uninstall FocusFlow while keeping your local data for a future reinstall?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.perform_uninstall()

    def perform_uninstall(self):
        self.uninstall_button.setEnabled(False)
        try:
            terminate_running_app()
            desktop_link, start_link, uninstall_link = shortcut_paths()
            for shortcut in (desktop_link, start_link, uninstall_link):
                try:
                    shortcut.unlink()
                except FileNotFoundError:
                    pass
            cleanup_targets = [self.install_dir]
            if self.remove_data.isChecked():
                # Keep a marker outside the data folder. If a file remains locked,
                # the next installer/app launch will finish the requested reset.
                marker = data_reset_marker_path()
                marker.write_text("remove", encoding="utf-8")
                cleanup_targets.append(self.data_dir)
            remove_registry_registration()
            schedule_cleanup(cleanup_targets)
            QMessageBox.information(
                self,
                "FocusFlow removed",
                "FocusFlow has been uninstalled. Your local data cleanup will finish after this window closes."
                if self.remove_data.isChecked()
                else "FocusFlow has been uninstalled. Your local data was kept.",
            )
            self.close()
        except Exception as error:
            self.uninstall_button.setEnabled(True)
            QMessageBox.critical(self, "Uninstallation failed", str(error))

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FocusFlow Uninstaller")
    window = UninstallerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

__all__ = [
    "APP_NAME",
    "APP_EXE",
    "UNINSTALLER_EXE",
    "UNINSTALL_REGISTRY_PATH",
    "UninstallerWindow",
    "install_directory",
    "user_data_directory",
    "shortcut_paths",
    "remove_registry_registration",
    "remove_tree",
    "schedule_cleanup",
    "user_data_directory",
    "data_reset_marker_path",
]

# Keep a stable build marker for packaging diagnostics.
BUILD_DATE = datetime.now().strftime("%Y-%m-%d")
