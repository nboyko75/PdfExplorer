@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "DIST_DIR=%PROJECT_DIR%dist"
set "IMAGES_DIST_DIR=%DIST_DIR%\images"
set "IMAGES_PROJECT_DIR=%PROJECT_DIR%\images"
set "LOCALIZATION_DIST_DIR=%DIST_DIR%\localization"
set "LOCALIZATION_PROJECT_DIR=%PROJECT_DIR%\localization"
set "SETTINGS_FILE=.pdf_explorer_settings.json"

if not exist "%IMAGES_DIST_DIR%" (
	mkdir "%IMAGES_DIST_DIR%"
)
copy /Y "%IMAGES_PROJECT_DIR%\*.*" "%IMAGES_DIST_DIR%" >nul
echo images are copied to "%IMAGES_DIST_DIR%"

if not exist "%LOCALIZATION_DIST_DIR%" (
	mkdir "%LOCALIZATION_DIST_DIR%"
)
copy /Y "%LOCALIZATION_PROJECT_DIR%\localization*.*" "%LOCALIZATION_DIST_DIR%" >nul
echo images are copied to "%LOCALIZATION_DIST_DIR%"

pyinstaller --onefile --windowed --name PdfExplorer --icon="%IMAGES_PROJECT_DIR%\main.ico" --add-data "images;images" --add-data "localization;localization" "%PROJECT_DIR%main.py"

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

if exist "%PROJECT_DIR%register_pdf_association.cmd" (
	copy /Y "%PROJECT_DIR%register_pdf_association.cmd" "%DIST_DIR%\register_pdf_association.cmd" >nul
	echo PDF association helper copied to "%DIST_DIR%\register_pdf_association.cmd"
)

if exist "%PROJECT_DIR%unregister_pdf_association.cmd" (
	copy /Y "%PROJECT_DIR%unregister_pdf_association.cmd" "%DIST_DIR%\unregister_pdf_association.cmd" >nul
	echo PDF association uninstall helper copied to "%DIST_DIR%\unregister_pdf_association.cmd"
)

endlocal                                                                            