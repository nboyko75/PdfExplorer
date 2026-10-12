<#
.SYNOPSIS
Open the Store review dialog immediately, without starting DocExplorer.
.DESCRIPTION
Uses the real dialog with an in-memory first-use date that makes it due now.
Reminder and dismissal choices do not change your saved app settings.
The Microsoft Store button opens the real Store review page.
.EXAMPLE
.\script\run_store_review.ps1
.EXAMPLE
.\script\run_store_review.ps1 -Locale en
#>
[CmdletBinding()]
param(
    [ValidateSet('en', 'uk', 'de', 'fr', 'es', 'it', 'pt_br', 'ja', 'ko', 'zh_cn', 'ru')]
    [string]$Locale = 'uk',
    [string]$PythonExe
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

if (-not $PythonExe) {
    $PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        $PythonExe = (Get-Command python -ErrorAction Stop).Source
    }
}

$dialogScript = @'
import json
import sys
from datetime import date, timedelta
from unittest.mock import patch

try:
    import wx
except ImportError:
    raise SystemExit("wxPython is required. Use -PythonExe to select the app's Python environment.")

from controls import store_review
from localization import load_locale

load_locale(sys.argv[1])
settings = {
    store_review.SETTINGS_KEY: {
        "first_used": (date.today() - timedelta(days=store_review.FIRST_PROMPT_DAY - 1)).isoformat()
    }
}

app = wx.App(False)
parent = wx.Frame(None, title="DocExplorer")
try:
    with patch.object(store_review, "load_settings", return_value=settings), \
         patch.object(store_review, "update_settings", side_effect=settings.update):
        store_review.check_store_review(parent)
    print("Preview result (not saved): " + json.dumps(settings[store_review.SETTINGS_KEY]))
finally:
    parent.Destroy()
'@

Push-Location -LiteralPath $ProjectRoot
try {
    $dialogScript | & $PythonExe - $Locale
    if ($LASTEXITCODE -ne 0) {
        throw "Store review dialog exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
