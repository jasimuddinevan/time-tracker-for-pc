import tempfile
from pathlib import Path

# Run on the attached Windows desktop so tray and translucent-window behavior are exercised.
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QPushButton
import focusflow_qt


with tempfile.TemporaryDirectory() as folder:
    focusflow_qt.DB_PATH = Path(folder) / "focusflow.db"
    app = QApplication(["focusflow-qt-smoke"])
    window = None
    try:
        window = focusflow_qt.FocusFlowQt()
        window.show()
        app.processEvents()
        assert set(window.pages) == {"dashboard", "tasks", "history", "analytics", "calendar", "settings", "about"}
        for page in window.pages:
            window.show_view(page)
            assert window.current_view == page
        window.toggle_theme()
        assert window.theme == "dark"
        window.toggle_theme()
        assert window.theme == "light"
        assert window.calendar.palette().color(QPalette.ColorRole.Base).name().lower() == "#ffffff"
        assert window.task_table.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert window.tasks_table.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert len(window._shortcut_objects) == 18
        assert window.shortcut_table.rowCount() == len(window._shortcut_rows())
        window.show_view("about")
        assert window.current_view == "about"
        assert window.nav_buttons["about"].text() == "About & Support"
        assert window.pages["about"].findChildren(QPushButton)[0].text() == "Support my work"
        assert window.pages["about"].findChildren(QPushButton)[1].text() == "Visit my links"
        task_dialog = focusflow_qt.NewTaskDialog(25, window)
        assert task_dialog.focus.value() == 25
        assert task_dialog.run_now.isChecked()
        assert task_dialog.save_button.text() == "Start task"
        task_dialog.later.click()
        assert task_dialog.save_button.text() == "Save for later"
        task_dialog.run_now.click()
        assert task_dialog.save_button.text() == "Start task"
        task_dialog.close()
        welcome = focusflow_qt.WelcomeDialog(None, window)
        assert welcome.title_label.text() == "Hi there, welcome!"
        assert welcome.prompt_label.text() == "What should we call you?"
        assert welcome.name_edit.objectName() == "onboardingName"
        assert welcome.name_edit.styleSheet() == ""
        welcome.name_edit.setText("Aisha")
        welcome.save_name()
        assert welcome.user_name == "Aisha"
        assert welcome.title_label.text() == "Thank you, Aisha!"
        window.user_name = "Aisha"
        window.refresh_dashboard_greeting()
        assert window.dashboard_greeting.text().endswith("Aisha!")
        welcome.close()
        window.focus_new_task()
        app.processEvents()
        assert window.current_view == "tasks"
        assert window.tasks_entry.hasFocus()
        window.show_shortcut_reference()
        assert window.current_view == "settings"
        window.reset_timer()
        window.refresh_all()
        print("QT_SMOKE_OK")
    finally:
        if window is not None:
            window.close()
            app.processEvents()
            window.deleteLater()
            app.processEvents()
        app.quit()
        del window
        del app
