@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_hands_free_demo.ps1" -RestartExisting %*
if errorlevel 1 (
  echo.
  echo Live Voice Demo failed to start. Review the error above.
  pause
)
endlocal
