import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QCheckBox,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "FocusFlow"
APP_EXE = "FocusFlow.exe"
UNINSTALLER_EXE = "FocusFlowUninstaller.exe"
UNINSTALL_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\FocusFlow"


def bundle_path(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / name


class InstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FocusFlow Setup")
        self.setMinimumSize(620, 460)
        self.resize(680, 500)
        icon_path = bundle_path("focusflow.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._install_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / APP_NAME
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(34, 30, 34, 30)
        outer.setSpacing(18)

        header = QFrame()
        header.setObjectName("hero")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        eyebrow = QLabel("PERSONAL PRODUCTIVITY")
        eyebrow.setObjectName("eyebrow")
        header_layout.addWidget(eyebrow)
        title = QLabel("Install FocusFlow")
        title.setObjectName("title")
        header_layout.addWidget(title)
        subtitle = QLabel("A calm workspace for choosing one task and finishing the next small step.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)
        outer.addWidget(header)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(14)
        intro = QLabel("FocusFlow will be installed for your Windows account. No administrator permission is required.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        card_layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(12)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(str(self._install_dir))
        self.path_edit.setToolTip("Choose where FocusFlow should be installed")
        path_row.addWidget(self.path_edit, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.choose_folder)
        path_row.addWidget(browse)
        path_label = QLabel("Install location")
        form.addRow(path_label, path_row)
        card_layout.addLayout(form)

        self.desktop_shortcut = QCheckBox("Create a desktop shortcut")
        self.desktop_shortcut.setChecked(True)
        card_layout.addWidget(self.desktop_shortcut)
        self.start_menu_shortcut = QCheckBox("Create a Start Menu shortcut")
        self.start_menu_shortcut.setChecked(True)
        card_layout.addWidget(self.start_menu_shortcut)

        self.status = QLabel("Ready to install FocusFlow.")
        self.status.setObjectName("muted")
        card_layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        card_layout.addWidget(self.progress)
        outer.addWidget(card, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)
        buttons.addWidget(self.cancel_button)
        self.install_button = QPushButton("Install FocusFlow")
        self.install_button.setObjectName("primary")
        self.install_button.setDefault(True)
        self.install_button.clicked.connect(self.install)
        buttons.addWidget(self.install_button)
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
        QLineEdit { background: #F8FAFC; color: #172033; border: 1px solid #E4E7F0; border-radius: 11px; padding: 10px 12px; }
        QLineEdit:focus { border-color: #7C3AED; }
        QPushButton { background: #FFFFFF; color: #172033; border: 1px solid #E4E7F0; border-radius: 12px; padding: 11px 16px; font-weight: 700; }
        QPushButton:hover { background: #EDE9FE; border-color: #A78BFA; }
        QPushButton#primary { background: #7C3AED; color: white; border: none; padding: 12px 18px; }
        QPushButton#primary:hover { background: #5B21B6; }
        QCheckBox { color: #172033; spacing: 8px; }
        QProgressBar { background: #EDE9FE; border: none; border-radius: 6px; height: 10px; }
        QProgressBar::chunk { background: #7C3AED; border-radius: 6px; }
        """)

    def choose_folder(self):
        selected = QFileDialog.getExistingDirectory(self, "Choose install location", str(self._install_dir))
        if selected:
            self.path_edit.setText(selected)

    def _shortcut(self, shortcut_path: Path, target: Path, description: str):
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        script = (
            "$ws=New-Object -ComObject WScript.Shell; "
            f"$s=$ws.CreateShortcut('{str(shortcut_path).replace(chr(39), chr(39) + chr(39))}'); "
            f"$s.TargetPath='{str(target).replace(chr(39), chr(39) + chr(39))}'; "
            f"$s.WorkingDirectory='{str(target.parent).replace(chr(39), chr(39) + chr(39))}'; "
            f"$s.Description='{description}'; $s.Save()"
        )
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _register_uninstaller(self, destination: Path, target: Path):
        """Register this per-user installation in Windows Installed apps."""
        uninstaller = destination / UNINSTALLER_EXE
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REGISTRY_PATH) as key:
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
                winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "1.0.0")
                winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "FocusFlow")
                winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(destination))
                winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(target))
                winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller}"')
                winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, f'"{uninstaller}"')
                winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, max(1, int(target.stat().st_size / 1024)))
                winreg.SetValueEx(key, "InstallDate", 0, winreg.REG_SZ, __import__("datetime").datetime.now().strftime("%Y%m%d"))
        except (ImportError, OSError):
            # The application remains usable even if registry registration is unavailable.
            pass

    def install(self):
        destination = Path(self.path_edit.text().strip()).expanduser()
        if not destination:
            QMessageBox.warning(self, "Choose a location", "Please choose an installation folder.")
            return
        source = bundle_path(APP_EXE)
        if not source.exists():
            QMessageBox.critical(self, "Installer error", "The bundled FocusFlow application could not be found.")
            return
        try:
            self.install_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.status.setText("Preparing your FocusFlow workspace…")
            self.progress.setValue(20)
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / APP_EXE
            subprocess.run(["taskkill", "/IM", APP_EXE, "/F", "/T"], capture_output=True, text=True, check=False)
            copy_error = None
            for _attempt in range(6):
                try:
                    shutil.copy2(source, target)
                    copy_error = None
                    break
                except PermissionError as error:
                    copy_error = error
                    time.sleep(0.5)
            if copy_error is not None:
                raise copy_error
            uninstaller_source = bundle_path(UNINSTALLER_EXE)
            if not uninstaller_source.exists():
                raise FileNotFoundError("The bundled FocusFlow uninstaller could not be found.")
            uninstaller_target = destination / UNINSTALLER_EXE
            shutil.copy2(uninstaller_source, uninstaller_target)
            icon_source = bundle_path("focusflow.ico")
            if icon_source.exists():
                shutil.copy2(icon_source, destination / "focusflow.ico")
            self.progress.setValue(65)
            if self.desktop_shortcut.isChecked():
                desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
                self._shortcut(desktop / "FocusFlow.lnk", target, "FocusFlow productivity timer")
            start_menu = Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
            if self.start_menu_shortcut.isChecked():
                self._shortcut(start_menu / "FocusFlow.lnk", target, "FocusFlow productivity timer")
            self._shortcut(start_menu / "Uninstall FocusFlow.lnk", uninstaller_target, "Uninstall FocusFlow")
            self._register_uninstaller(destination, target)
            self.progress.setValue(100)
            self.status.setText("Installation complete. FocusFlow is now available in Installed apps. Opening FocusFlow…")
            QTimer.singleShot(700, lambda: self.launch(target))
        except Exception as error:
            self.install_button.setEnabled(True)
            self.cancel_button.setEnabled(True)
            self.status.setText("Installation could not be completed.")
            QMessageBox.critical(self, "Installation failed", str(error))

    def launch(self, target: Path):
        try:
            subprocess.Popen([str(target)], cwd=str(target.parent))
        finally:
            self.close()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FocusFlow Setup")
    window = InstallerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
