@echo off
setlocal

set "PROGID=PdfExplorer.File"

echo Removing PdfExplorer PDF association entries for the current user.

for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Classes\.pdf" /ve 2^>nul ^| find /i "(Default)"') do (
	if /i "%%B"=="%PROGID%" (
		reg delete "HKCU\Software\Classes\.pdf" /ve /f >nul 2>nul
	)
)

reg delete "HKCU\Software\Classes\%PROGID%\shell\open\command" /f >nul 2>nul
reg delete "HKCU\Software\Classes\%PROGID%\DefaultIcon" /f >nul 2>nul
reg delete "HKCU\Software\Classes\%PROGID%" /f >nul 2>nul
reg delete "HKCU\Software\Classes\.pdf\OpenWithProgids" /v "%PROGID%" /f >nul 2>nul
reg delete "HKCU\Software\Classes\Applications\PdfExplorer.exe\shell\open\command" /f >nul 2>nul
reg delete "HKCU\Software\Classes\Applications\PdfExplorer.exe\FriendlyAppName" /f >nul 2>nul
reg delete "HKCU\Software\Classes\Applications\PdfExplorer.exe\SupportedTypes" /v ".pdf" /f >nul 2>nul
reg delete "HKCU\Software\Classes\Applications\PdfExplorer.exe" /f >nul 2>nul

echo Done.
echo If Windows still shows PdfExplorer in the Default apps list, clear the .pdf default there once.

endlocal