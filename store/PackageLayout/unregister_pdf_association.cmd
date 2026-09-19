@echo off
setlocal

set "PROGID=DocExplorer.File"

echo Removing DocExplorer PDF association entries for the current user.

for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Classes\.pdf" /ve 2^>nul ^| find /i "(Default)"') do (
	if /i "%%B"=="%PROGID%" (
		reg delete "HKCU\Software\Classes\.pdf" /ve /f >nul 2>nul
	)
)

reg delete "HKCU\Software\Classes\%PROGID%\shell\open\command" /f >nul 2>nul
reg delete "HKCU\Software\Classes\%PROGID%\DefaultIcon" /f >nul 2>nul
reg delete "HKCU\Software\Classes\%PROGID%" /f >nul 2>nul
reg delete "HKCU\Software\Classes\.pdf\OpenWithProgids" /v "%PROGID%" /f >nul 2>nul
reg delete "HKCU\Software\Classes\Applications\DocExplorer.exe\shell\open\command" /f >nul 2>nul
reg delete "HKCU\Software\Classes\Applications\DocExplorer.exe\FriendlyAppName" /f >nul 2>nul
reg delete "HKCU\Software\Classes\Applications\DocExplorer.exe\SupportedTypes" /v ".pdf" /f >nul 2>nul
reg delete "HKCU\Software\Classes\Applications\DocExplorer.exe" /f >nul 2>nul

echo Done.
echo If Windows still shows DocExplorer in the Default apps list, clear the .pdf default there once.

endlocal