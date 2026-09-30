[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$AppName = 'DocExplorer',
    [string]$PackageName = 'DocExplorer',
    [string]$Version = '1.0.1.0',
    [string]$Publisher = 'CN=Nick Boiko',
    [string]$CertificatePath = '',
    [string]$CertificatePassword = ''
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $ProjectRoot = Split-Path -Parent $PSScriptRoot
    }
    elseif ($MyInvocation.MyCommand.Path) {
        $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    else {
        $ProjectRoot = (Get-Location).Path
    }
}

$root = (Resolve-Path $ProjectRoot).Path
$appDirCandidates = @(
    (Join-Path $root 'dist\DocExplorer'),
    (Join-Path $root 'dist')
)
$appDir = $appDirCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if (-not $appDir) {
    throw "The PyInstaller app output is missing. Run build.cmd first. Expected one of: $($appDirCandidates -join ', ')"
}

$storeDir = Join-Path $root 'store'
$assetsDir = Join-Path $storeDir 'Assets'
$requiredIconAssets = @(
    'Logo44.targetsize-16_altform-unplated.png',
    'Logo44.targetsize-32_altform-unplated.png',
    'Logo44.targetsize-48_altform-unplated.png',
    'Logo44.targetsize-256_altform-unplated.png'
)
foreach ($assetName in $requiredIconAssets) {
    if (-not (Test-Path -LiteralPath (Join-Path $assetsDir $assetName) -PathType Leaf)) {
        throw "Required MSIX icon is missing: $assetName. Add it to '$assetsDir' before building."
    }
}
$packageLayout = Join-Path $storeDir 'PackageLayout'
$manifestPath = Join-Path $storeDir 'AppxManifest.xml'
$outputPath = Join-Path $storeDir "$PackageName.msix"
$outputUploadPath = Join-Path $storeDir "$PackageName.msixupload"

if (-not (Test-Path $manifestPath)) {
    throw "The AppxManifest file is missing at '$manifestPath'."
}

[xml]$manifestXml = Get-Content -Path $manifestPath
$ns = New-Object System.Xml.XmlNamespaceManager($manifestXml.NameTable)
$ns.AddNamespace('m', $manifestXml.DocumentElement.NamespaceURI)
$identity = $manifestXml.SelectSingleNode('/m:Package/m:Identity', $ns)
if (-not $identity) {
    throw "The AppxManifest file does not contain a Package/Identity node."
}
$identity.Version = $Version
$manifestXml.Save($manifestPath)

$makeAppx = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin\10.0.26100.0\x64\makeappx.exe'
if (-not (Test-Path $makeAppx)) {
    throw "makeappx.exe not found. Install the Windows 10/11 SDK first."
}

$signTool = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe'
if (-not (Test-Path $signTool)) {
    throw "signtool.exe not found. Install the Windows 10/11 SDK first."
}

$makePri = Join-Path (Split-Path -Parent $makeAppx) 'makepri.exe'
$priConfig = Join-Path $PSScriptRoot 'priconfig.xml'
if (-not (Test-Path -LiteralPath $makePri -PathType Leaf)) {
    throw 'makepri.exe not found. Install the Windows SDK resource indexing tools.'
}
if (-not (Test-Path -LiteralPath $priConfig -PathType Leaf)) {
    throw "The resource index configuration is missing: $priConfig"
}

if (Test-Path $packageLayout) {
    $resolvedLayout = [IO.Path]::GetFullPath($packageLayout)
    if ([IO.Path]::GetDirectoryName($resolvedLayout) -ne [IO.Path]::GetFullPath($storeDir) -or
        [IO.Path]::GetFileName($resolvedLayout) -ne 'PackageLayout') {
        throw "Refusing to remove unexpected staging directory: $resolvedLayout"
    }
    Remove-Item -LiteralPath $resolvedLayout -Recurse -Force
}
New-Item -ItemType Directory -Path $packageLayout -Force | Out-Null

Copy-Item (Join-Path $appDir '*') $packageLayout -Recurse -Force

$packageAssetsDir = Join-Path $packageLayout 'Assets'
if (Test-Path $assetsDir) {
    if (-not (Test-Path $packageAssetsDir)) {
        New-Item -ItemType Directory -Path $packageAssetsDir -Force | Out-Null
    }
    # Include the required target-size unplated icons alongside the base logos.
    Copy-Item (Join-Path $assetsDir '*') $packageAssetsDir -Recurse -Force
}

Copy-Item $manifestPath (Join-Path $packageLayout 'AppxManifest.xml') -Force

# Copying qualified PNGs alone does not register their size/alternate-form variants.
& $makePri new /pr $packageLayout /cf $priConfig /mn (Join-Path $packageLayout 'AppxManifest.xml') /of (Join-Path $packageLayout 'resources.pri') /o
if ($LASTEXITCODE -ne 0) {
    throw 'makepri failed while indexing the MSIX icon assets.'
}

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
