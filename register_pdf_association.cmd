@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "DIST_EXE=%SCRIPT_DIR%dist\PdfExplorer.exe"
set "ROOT_EXE=%SCRIPT_DIR%PdfExplorer.exe"

if exist "%DIST_EXE%" (
	set "APP_EXE=%DIST_EXE%"
) else (
	if exist "%ROOT_EXE%" (
		set "APP_EXE=%ROOT_EXE%"
	) else (
		echo PdfExplorer.exe was not found.
		echo Build the project first, then run this script again.
		exit /b 1
	)
)

echo Registering PdfExplorer as the PDF handler for the current user.
echo App: "%APP_EXE%"

reg add "HKCU\Software\Classes\PdfExplorer.File" /ve /d "PDF document" /f >nul
reg add "HKCU\Software\Classes\PdfExplorer.File\DefaultIcon" /ve /d "\"%APP_EXE%\",0" /f >nul
reg add "HKCU\Software\Classes\PdfExplorer.File\shell\open\command" /ve /d "\"%APP_EXE%\" \"%%1\"" /f >nul
reg add "HKCU\Software\Classes\.pdf" /ve /d "PdfExplorer.File" /f >nul
reg add "HKCU\Software\Classes\.pdf\OpenWithProgids" /v "PdfExplorer.File" /t REG_NONE /d "" /f >nul
reg add "HKCU\Software\Classes\Applications\PdfExplorer.exe\shell\open\command" /ve /d "\"%APP_EXE%\" \"%%1\"" /f >nul
reg add "HKCU\Software\Classes\Applications\PdfExplorer.exe\FriendlyAppName" /ve /d "Pdf Explorer" /f >nul
reg add "HKCU\Software\Classes\Applications\PdfExplorer.exe\SupportedTypes" /v ".pdf" /t REG_NONE /d "" /f >nul

echo Done.
echo If Windows does not switch the default immediately, pick PdfExplorer in the Default apps UI for .pdf files.

endlocal