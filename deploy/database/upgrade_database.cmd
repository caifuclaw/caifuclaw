@echo off
REM Company: 深圳智柠网络科技有限公司
REM Author: mohsen liang

setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Set-Location -LiteralPath '%PROJECT_ROOT%';" ^
  "python 'deploy\database\upgrade_database.py' %*"

endlocal
