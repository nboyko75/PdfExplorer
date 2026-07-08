@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "DIST_DIR=%PROJECT_DIR%dist"
set "IMAGES_DIST_DIR=%DIST_DIR%images"
set "IMAGES_PROJECT_DIR=%PROJECT_DIR%images"
set "SETTINGS_FILE=.pdf_explorer_settings.json"

if not exist "%IMAGES_DIST_DIR%" (
	mkdir "%IMAGES_DIST_DIR%"
)
copy /Y "%IMAGES_PROJECT_DIR%\*.bmp" "%IMAGES_DIST_DIR%" >nul
copy /Y "%IMAGES_PROJECT_DIR%\*.ico" "%IMAGES_DIST_DIR%" >nul

echo images are copied to "%IMAGES_DIST_DIR%"

pyinstaller --onefile --windowed --icon="%IMAGES_PROJECT_DIR%\main.ico" "%PROJECT_DIR%main.py"

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