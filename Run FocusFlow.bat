@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0dist\FocusFlow.exe" (
    start "" "%~dp0dist\FocusFlow.exe"
) else (
    set "PYTHON_EXE=C:\Users\busin\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
    if exist "%PYTHON_EXE%" (
        start "FocusFlow" "%PYTHON_EXE%" "%~dp0focusflow_qt.py"
    ) else (
        start "FocusFlow" python "%~dp0focusflow_qt.py"
    )
)
endlocal
