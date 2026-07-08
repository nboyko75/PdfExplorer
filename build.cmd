@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "DIST_DIR=%PROJECT_DIR%dist"
set "SETTINGS_FILE=.pdf_explorer_settings.json"

pyinstaller --onefile --windowed "%PROJECT_DIR%main.py"
if errorlevel 1 (
	exit /b %errorlevel%
)

if not exist "%DIST_DIR%" (
	mkdir "%DIST_DIR%"
)

if exist "%PROJECT_DIR%%SETTINGS_FILE%" (
	copy /Y "%PROJECT_DIR%%SETTINGS_FILE%" "%DIST_DIR%\%SETTINGS_FILE%" >nul
) else (
	echo {}>"%DIST_DIR%\%SETTINGS_FILE%"
)

echo Settings file prepared: "%DIST_DIR%\%SETTINGS_FILE%"
endlocal