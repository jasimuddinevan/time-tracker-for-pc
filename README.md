# FocusFlow Pomodoro Timer

FocusFlow is a Windows desktop Pomodoro timer with task-specific durations, task planning, daily progress metrics, persistent local history, and an end-of-session musical chime.

## Launch

For distribution, run **FocusFlowSetup.exe**. Its setup window installs FocusFlow for the current Windows account, optionally creates Desktop and Start Menu shortcuts, and does not require administrator permission. The installer also registers FocusFlow under **Windows Settings → Apps → Installed apps**, creates a **Start Menu → FocusFlow → Uninstall FocusFlow** shortcut, and includes a proper per-user uninstaller.

The uninstaller asks whether to keep or remove local FocusFlow data. Keeping data preserves tasks, settings, session history, and the saved name for a future reinstall. Removing data deletes the local `%LOCALAPPDATA%\\FocusFlow` folder as well as the application files and shortcuts.

On the first launch, FocusFlow says **“Hi there, welcome!”**, asks **“What should we call you?”**, and then displays **“Thank you, [name]!”** before opening the Dashboard. The name is stored locally, so returning users go directly to their workspace without seeing onboarding again.

During development, double-click **Run FocusFlow.bat**. The launcher uses the Python runtime detected on this computer. You can also run `focusflow.py` with Python 3.11 or later.

## Navigation and main workflow

The top navigation bar provides seven views: **Dashboard**, **Tasks**, **History**, **Analytics**, **Calendar**, **Settings**, and **About & Support**. Dashboard remains the fastest way to work, combining the task list, timer, and today’s progress in one place.

Add a task from the left panel, choose the planned number of sessions, and set the focus duration for that task. Select the task and choose **Start selected** or press **Start** in the center panel. The timer can be paused, resumed, reset, or skipped. A completed focus session is saved automatically and included in the Today summary.

The **Tasks** view provides a larger task library and quick links back to the dashboard. **History** shows all completed focus and break sessions and includes an **Export CSV** button for backup or analysis. **Analytics** turns completed focus sessions into daily focus-minute bars, focus-by-task charts, total minutes, session counts, average session length, and best-day metrics for a 7-, 14-, or 30-day window. **Calendar** provides month navigation, day markers for completed sessions, daily summaries, task search, and focus/break filters. **Settings** summarizes the active theme, timer defaults, and completion sound preferences. **About & Support** introduces the developer and provides direct links to support the project and view the developer’s public links.

After a focus session, FocusFlow moves into a short break. After the configured number of sessions, it uses a long break instead. When the break ends, the app returns to focus mode.

## Appearance and settings

FocusFlow opens in a polished **light theme** by default, with a soft lavender accent, clean cards, and high-contrast timer controls. Use the **Dark mode** button in the top-right header to switch themes. The selected theme is saved automatically and restored the next time the app starts.

Use **Settings** to change default focus duration, short break duration, long break duration, and the number of focus sessions before a long break. Completion music can be enabled or disabled. You can also select a custom `.wav` file; if none is selected, FocusFlow plays a built-in ascending chime through Windows.

## Data and privacy

Tasks, settings, and session history are stored locally in:

`%LOCALAPPDATA%\FocusFlow\focusflow.db`

No network connection or account is required. The database is created automatically on first launch.

## Professional workflow features

FocusFlow uses elapsed wall-clock timing, so the countdown remains accurate if the window is minimized or the computer is temporarily busy. If the application closes while a session is active or paused, the next launch offers to resume the unfinished session.

Tasks can be edited after creation. Each task supports a status, priority, due date, planned session count, and individual focus duration. Starting a task marks it **In progress**; pausing marks it **Paused**; completing all planned sessions marks it **Completed**. When creating a task, pressing **Enter** opens a planning dialog where you can set the focus duration and choose **Run now** or **Later**. **Run now** is selected by default, and pressing **Enter** again confirms the action.

When a session ends, FocusFlow can play the configured three-note completion chime, use the Windows alert sound, and display a true Windows corner toast notification. Music, alert sound, toast notifications, and system-tray support can be controlled from Settings.

FocusFlow can continue running in the Windows system tray. Use **Minimize** to hide the main window. The tray menu provides Open FocusFlow, Start / Resume, Pause, and Exit actions.

### Keyboard shortcuts

FocusFlow keeps single-key timer controls inactive while you are typing in a text or numeric field, so task entry remains predictable.

| Shortcut | Action |
|---|---|
| Space | Start or pause the current timer |
| R | Reset the current timer |
| S | Skip the current mode |
| Ctrl+N | Open Tasks and focus the new-task field |
| Ctrl+E | Edit the selected task |
| Ctrl+Shift+S | Start the selected task |
| Ctrl+Shift+T | Toggle light and dark mode |
| Ctrl+Shift+M | Minimize FocusFlow |
| Ctrl+, | Open timer settings |
| F1 | Open the in-app shortcut reference |
| F5 | Refresh tasks, history, analytics, and calendar |
| Ctrl+1 | Dashboard |
| Ctrl+2 | Tasks |
| Ctrl+3 | History |
| Ctrl+4 | Settings page |
| Ctrl+5 | Analytics |
| Ctrl+6 | Calendar |
| Ctrl+7 | About & Support |
| Enter | Open the task planning dialog while focused in a task-entry field; Enter again confirms the selected action |

## Controls

| Control | Action |
|---|---|
| Start | Begin or resume the current timer |
| Pause | Pause the current timer |
| Reset | Reset the current session to its full duration |
| Skip | Move to the next mode without recording the current session |
| Start selected | Select the highlighted task and start a focus session |
| Edit | Change the selected task’s title, plan, duration, priority, status, or due date |
| Delete | Archive the selected task from the visible task list |

## Notes

The app uses Python’s standard library, Tkinter, SQLite, and Windows `winsound`; charts are drawn with native Tk Canvas controls, so no data-visualization package is required.

## Modern glossy interface

The current release includes a cohesive glossy visual system across the entire desktop application. It uses layered glass-like surfaces, soft borders, an accent glow rail, an elevated hero timer, inset input fields, polished navigation states, stronger typography, and improved table and progress-bar spacing.

The light theme remains the default. Dark mode uses the same design language with deeper layered surfaces and accessible accent contrast. The theme toggle in the header continues to persist the selected appearance across launches. The redesign is applied consistently to Dashboard, Tasks, History, Analytics, Calendar, Settings, task editing dialogs, timer settings, and system controls.

All existing timer, recovery, toast, tray, task, history, analytics, and calendar behavior remains unchanged.

## PySide6 modern interface edition

The project now includes a custom PySide6 visual layer in `focusflow_qt.py`. This edition uses a frameless rounded application shell, layered glass-like cards, custom shadows, gradient background lighting, glowing accent colors, a polished sidebar, custom navigation buttons, a large timer hero, modern tables, inset controls, and native canvas charts.

The primary `Run FocusFlow.bat` launcher opens `dist\\FocusFlow.exe` when the packaged build exists. During development it falls back to the detected Python runtime and opens `focusflow_qt.py` directly. The original Tkinter source remains available in `focusflow.py` as a compatibility and database module, while the Qt edition reuses the same local SQLite database and retains the existing timer, recovery, task, history, analytics, calendar, notification, tray, keyboard-shortcut, and CSV-export behavior.


## Developer credit and support

FocusFlow is designed and developed by **Jasim Uddin**. The project is shared openly so Windows users can use, study, improve, and adapt it for personal productivity.

If FocusFlow is useful to you, you can support continued development or find the developer’s other links here:

<p>
  <a href="https://buymeacoffee.com/jasimuddin"><img src="https://cdn.simpleicons.org/buymeacoffee/FFDD00" alt="Support Jasim Uddin on Buy Me a Coffee" height="32"></a>
  &nbsp;
  <a href="https://bio.link/jasimuddin"><img src="https://cdn.simpleicons.org/linktree/39E09B" alt="Visit Jasim Uddin's links" height="32"></a>
</p>

The project is released under the **MIT License**. Contributions, bug reports, design suggestions, and improvements are welcome through GitHub Issues and Pull Requests.

## Public repository

The source code is available at [github.com/jasimuddinevan/time-tracker-for-pc](https://github.com/jasimuddinevan/time-tracker-for-pc). The repository is intended for the source and development files. Windows users who want the packaged application should use `FocusFlowSetup.exe` from a published distribution archive or build the application locally.
