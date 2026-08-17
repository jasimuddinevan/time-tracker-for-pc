<div align="center">
  <img src="focusflow_logo.svg" alt="FocusFlow logo" width="112">
  <h1>FocusFlow</h1>
  <p><strong>A calm, focused Pomodoro workspace for Windows.</strong></p>
  <p>Plan one meaningful task, protect your attention, and build a clear record of your progress.</p>

  <p>
    <a href="https://github.com/jasimuddinevan/time-tracker-for-pc/releases/download/windows-apps/FocusFlowSetup.exe"><strong>Download FocusFlow for Windows</strong></a>
    &nbsp; · &nbsp;
    <a href="https://github.com/jasimuddinevan/time-tracker-for-pc">View source</a>
    &nbsp; · &nbsp;
    <a href="https://github.com/jasimuddinevan/time-tracker-for-pc/issues">Report an issue</a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/platform-Windows%2011-5b2be0?style=flat-square" alt="Windows 11">
    <img src="https://img.shields.io/badge/license-MIT-2f855a?style=flat-square" alt="MIT License">
    <img src="https://img.shields.io/badge/mode-offline--first-475569?style=flat-square" alt="Offline first">
  </p>
</div>

## What is FocusFlow?

FocusFlow is an offline-first Pomodoro timer and personal productivity workspace for Windows. It combines task planning, focused timing, session history, progress summaries, analytics, and calendar review in one quiet interface.

The application is intentionally local. Your tasks, session history, settings, saved name, and onboarding state remain on your computer, so FocusFlow does not require an account or a permanent internet connection for its core workflow.

> **The idea is simple:** choose one task, give it a defined amount of time, and finish the next small step.

## Download and install

The fastest way to get started is to download the installer:

**[Download FocusFlowSetup.exe](https://github.com/jasimuddinevan/time-tracker-for-pc/releases/download/windows-apps/FocusFlowSetup.exe)**

Run the installer and follow the short setup flow. FocusFlow installs for the current Windows account without requiring administrator permission. The setup can create Desktop and Start Menu shortcuts and registers the application in **Windows Settings → Apps → Installed apps**.

On the first launch, FocusFlow welcomes the user, asks for a name, and then opens a personalized Dashboard greeting such as **“Good morning, Aisha!”**. Returning users go directly to their workspace.

### Uninstalling FocusFlow

FocusFlow includes a proper Windows uninstaller. It is available from **Settings → Apps → Installed apps → FocusFlow** and from **Start Menu → FocusFlow → Uninstall FocusFlow**.

During uninstall, FocusFlow clearly asks whether local user data should be preserved. Keeping data retains tasks, settings, history, and the saved name for a future reinstall. Selecting removal deletes the local FocusFlow data after the application closes.

## The FocusFlow workflow

| Step | What happens |
|---|---|
| **1. Choose** | Add a task and decide how many focus sessions it needs. |
| **2. Plan** | Set a task-specific focus duration, priority, status, and optional due date. |
| **3. Focus** | Start the timer, pause when needed, or skip to the next mode. |
| **4. Recover** | Resume an unfinished session after an unexpected close or restart. |
| **5. Review** | Use History, Analytics, and Calendar to understand your focus rhythm. |

## Features

### A timer that follows the work

FocusFlow supports task-specific focus durations, configurable short and long breaks, planned session counts, accurate elapsed wall-clock timing, pause and resume behavior, reset and skip controls, and session recovery after restart.

When a focus session ends, the app can play a built-in three-note ascending **“ting ting ting”** chime, play a custom WAV file, show a Windows toast notification, and move into the appropriate break mode.

### Task planning without friction

Press `Enter` in a task-entry field to open the planning dialog. Choose the focus duration and select either **Run now** or **Later**. **Run now** is selected by default, and pressing `Enter` again confirms the action.

Tasks can be edited after creation. Each task supports a title, planned sessions, individual focus minutes, priority, status, and due date. Starting a task marks it in progress; completing its planned sessions marks it complete.

### A clear record of progress

FocusFlow turns completed sessions into useful local history rather than leaving progress as a vague feeling.

| View | Purpose |
|---|---|
| **Dashboard** | Select a task, run the timer, and see today’s progress. |
| **Tasks** | Manage the task library and edit task details. |
| **History** | Review completed focus and break sessions and export CSV data. |
| **Analytics** | Explore daily focus minutes, task charts, totals, averages, and best days. |
| **Calendar** | Browse focus activity by month, day, task, and session type. |
| **Settings** | Configure timer defaults, sound, notifications, theme, tray behavior, and shortcuts. |
| **About & Support** | Learn about the developer and support the project. |

### A polished Windows interface

The current interface is built with a custom PySide6 visual layer. It uses a light theme by default, a dark-mode alternative, soft lavender accents, glass-like cards, a square primary window, rounded inner surfaces, custom navigation, a branded icon, and a system-tray experience.

Light-mode Calendar and Analytics views use dedicated palettes to avoid dark color bleed. Task selection uses a clean filled state without the old focus-outline border.

### System integration

FocusFlow supports Windows toast notifications, a system-tray menu, minimize-to-tray behavior, taskbar and tray branding, and keyboard-first control. The app remains fully usable without an internet connection.

## Keyboard shortcuts

Single-key timer commands are disabled while typing in a text, numeric, or combo-box field, so task entry remains predictable.

| Shortcut | Action |
|---|---|
| `Space` | Start or pause the current timer |
| `R` | Reset the current timer |
| `S` | Skip the current focus or break mode |
| `Ctrl+N` | Open Tasks and focus the new-task field |
| `Ctrl+E` | Edit the selected task |
| `Ctrl+Shift+S` | Start the selected task |
| `Ctrl+Shift+T` | Toggle light and dark mode |
| `Ctrl+Shift+M` | Minimize FocusFlow |
| `Ctrl+,` | Open timer settings |
| `F1` | Open the in-app shortcut reference |
| `F5` | Refresh task, history, analytics, and calendar data |
| `Ctrl+1` | Dashboard |
| `Ctrl+2` | Tasks |
| `Ctrl+3` | History |
| `Ctrl+4` | Settings |
| `Ctrl+5` | Analytics |
| `Ctrl+6` | Calendar |
| `Ctrl+7` | About & Support |
| `Enter` | Open the task-planning dialog from a task-entry field; press again to confirm |

## Privacy and local data

FocusFlow stores application data locally at:

```text
%LOCALAPPDATA%\FocusFlow\focusflow.db
```

The local SQLite database contains tasks, settings, session history, and onboarding information. No account is required, and the core timer does not depend on a network service.

The optional About & Support buttons open external pages in the default browser only when the user chooses them.

## Run from source

The packaged installer is recommended for everyday use. Developers can run the project from source on Windows with Python 3.11 or later.

```powershell
python -m pip install -r requirements.txt
python focusflow_qt.py
```

The repository also includes `Run FocusFlow.bat`. When `dist\FocusFlow.exe` exists, the launcher opens the packaged application; otherwise it falls back to the available Python runtime and starts the Qt source edition.

The main files are:

| File | Role |
|---|---|
| `focusflow_qt.py` | Main PySide6 application and modern interface |
| `focusflow.py` | Local database, data model, and compatibility module |
| `FocusFlowInstaller.py` | Per-user installer source |
| `FocusFlowUninstaller.py` | Data-aware Windows uninstaller source |
| `focusflow_logo.svg` | FocusFlow branding asset |
| `focusflow_qt_smoke_test.py` | UI and integration verification test |

## Build the Windows application

The packaged Windows files are generated locally with PyInstaller. A typical application build is:

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name FocusFlow focusflow_qt.py
```

The installer and uninstaller are packaged separately from their corresponding Python entry points. The final distribution should be tested on a clean Windows account or isolated user-data directory before release.

## Developer credit

<div align="center">
  <h3>Made with care by Jasim Uddin</h3>
  <p>FocusFlow is an independent productivity project created to make focused work feel calmer, clearer, and easier to sustain.</p>
  <p>
    <a href="https://bio.link/jasimuddin"><img src="https://cdn.simpleicons.org/linktree/39E09B" alt="Jasim Uddin's links" height="30"></a>
    &nbsp;&nbsp;
    <a href="https://buymeacoffee.com/jasimuddin"><img src="https://cdn.simpleicons.org/buymeacoffee/FFDD00" alt="Support Jasim Uddin" height="30"></a>
  </p>
  <p><sub>Explore the developer's links or support continued development if FocusFlow helps your work.</sub></p>
</div>

## Support the project

If FocusFlow helps you protect your attention or build a better routine, support is appreciated but never required.

- **Support development:** [Buy Me a Coffee](https://buymeacoffee.com/jasimuddin)
- **Developer links and profiles:** [bio.link/jasimuddin](https://bio.link/jasimuddin)
- **Questions and bugs:** [Open a GitHub Issue](https://github.com/jasimuddinevan/time-tracker-for-pc/issues)

## Contributing

Suggestions, bug reports, documentation improvements, and pull requests are welcome. Please describe the problem clearly, include reproducible steps where possible, and keep changes focused on one improvement at a time.

## License

FocusFlow is released under the [MIT License](LICENSE). You are free to use, study, modify, and redistribute the project in accordance with that license.

## Links

- [Download FocusFlowSetup.exe](https://github.com/jasimuddinevan/time-tracker-for-pc/releases/download/windows-apps/FocusFlowSetup.exe)
- [FocusFlow GitHub repository](https://github.com/jasimuddinevan/time-tracker-for-pc)
- [Buy Me a Coffee — Jasim Uddin](https://buymeacoffee.com/jasimuddin)
- [Developer links — Jasim Uddin](https://bio.link/jasimuddin)
