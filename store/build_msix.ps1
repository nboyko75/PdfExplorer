[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$AppName = 'DocExplorer',
    [string]$PackageName = 'PdfExplorer',
    [string]$Version = '1.0.0.0',
    [string]$Publisher = 'CN=YourPublisherName',
    [string]$CertificatePath = '',
    [string]$CertificatePassword = ''
)

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path $ProjectRoot).Path
$appDir = Join-Path $root 'dist\DocExplorer'
$storeDir = Join-Path $root 'store'
$packageLayout = Join-Path $storeDir 'PackageLayout'
$manifestPath = Join-Path $storeDir 'AppxManifest.xml'
$outputPath = Join-Path $storeDir "$PackageName.msix"
$outputUploadPath = Join-Path $storeDir "$PackageName.msixupload"

if (-not (Test-Path $appDir)) {
    throw "The PyInstaller app is missing at '$appDir'. Run build.cmd first."
}

if (-not (Test-Path $manifestPath)) {
    throw "The AppxManifest file is missing at '$manifestPath'."
}

$makeAppx = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin\10.0.26100.0\x64\makeappx.exe'
if (-not (Test-Path $makeAppx)) {
    throw "makeappx.exe not found. Install the Windows 10/11 SDK first."
}

$signTool = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe'
if (-not (Test-Path $signTool)) {
    throw "signtool.exe not found. Install the Windows 10/11 SDK first."
}

if (Test-Path $packageLayout) {
    Remove-Item $packageLayout -Recurse -Force
}
New-Item -ItemType Directory -Path $packageLayout -Force | Out-Null

Copy-Item (Join-Path $appDir '*') $packageLayout -Recurse -Force
Copy-Item $manifestPath (Join-Path $packageLayout 'AppxManifest.xml') -Force

$files = Get-ChildItem -Path $storeDir -Filter '*.png' -File -Recurse
if ($files.Count -eq 0) {
    Write-Host 'No PNG assets were found. The manifest will still require them for Store upload; add Assets\Logo44.png and Assets\Logo150.png before signing.'
}

& $makeAppx pack /d $packageLayout /p $outputPath /o
if ($LASTEXITCODE -ne 0) {
    throw "makeappx failed while creating the MSIX package."
}

if ($CertificatePath -and (Test-Path $CertificatePath)) {
    $sigArgs = @('sign', '/fd', 'SHA256', '/a', '/f', $CertificatePath)
    if ($CertificatePassword) {
        $sigArgs += @('/p', $CertificatePassword)
    }
    $sigArgs += @($outputPath)

    & $signTool @sigArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'signtool failed while signing the MSIX package.'
    }
}

Write-Host "MSIX package created at: $outputPath"
Write-Host 'Important: update the Publisher identity and logo assets before uploading to the Microsoft Store.'
