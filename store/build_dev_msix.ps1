#Requires -Version 5.1
<#
.SYNOPSIS
Packages the existing PyInstaller output and signs it with a development certificate.
.EXAMPLE
.\store\build_dev_msix.ps1
.EXAMPLE
.\store\build_dev_msix.ps1 -Version 1.0.4.0
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Version
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
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
$manifestPath = Join-Path $storeDir 'AppxManifest.xml'
$outputPath = Join-Path $storeDir 'DocExplorer.Dev.msix'
$certificatePath = Join-Path $storeDir 'DocExplorer.Dev.cer'

[xml]$manifest = Get-Content -LiteralPath $manifestPath -Raw
$ns = New-Object System.Xml.XmlNamespaceManager($manifest.NameTable)
$ns.AddNamespace('m', $manifest.DocumentElement.NamespaceURI)
$identity = $manifest.SelectSingleNode('/m:Package/m:Identity', $ns)
if (-not $identity -or -not $identity.Publisher) {
    throw 'The manifest must contain an Identity with a Publisher.'
}
if ($Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+\.\d+$' -or
        @($Version.Split('.') | Where-Object { [double]$_ -gt 65535 }).Count -gt 0) {
        throw 'Version must have four numeric components between 0 and 65535.'
    }
    $identity.SetAttribute('Version', $Version)
}

$appDir = @('dist\DocExplorer', 'dist') |
    ForEach-Object { Join-Path $root $_ } |
    Where-Object { Test-Path -LiteralPath (Join-Path $_ 'DocExplorer.exe') -PathType Leaf } |
    Select-Object -First 1
if (-not $appDir) {
    throw 'PyInstaller output is missing. Run build.cmd first.'
}

$sdkBin = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
$sdk = Get-ChildItem -LiteralPath $sdkBin -Directory |
    Where-Object {
        $_.Name -match '^\d+\.\d+\.\d+\.\d+$' -and
        (Test-Path -LiteralPath (Join-Path $_.FullName 'x64\makeappx.exe')) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName 'x64\signtool.exe')) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName 'x64\makepri.exe'))
    } |
    Sort-Object { [version]$_.Name } -Descending |
    Select-Object -First 1
if (-not $sdk) {
    throw 'Install the Windows 10/11 SDK with makeappx.exe, signtool.exe, and makepri.exe.'
}
$makeAppx = Join-Path $sdk.FullName 'x64\makeappx.exe'
$signTool = Join-Path $sdk.FullName 'x64\signtool.exe'
$makePri = Join-Path $sdk.FullName 'x64\makepri.exe'
$priConfig = Join-Path $PSScriptRoot 'priconfig.xml'
if (-not (Test-Path -LiteralPath $priConfig -PathType Leaf)) {
    throw "The resource index configuration is missing: $priConfig"
}

# Keep the private key in the current user's certificate store, never in the repo.
$friendlyName = 'DocExplorer MSIX Development'
$certificate = Get-ChildItem Cert:\CurrentUser\My |
    Where-Object {
        $_.FriendlyName -eq $friendlyName -and
        $_.Subject -ceq $identity.Publisher -and $_.HasPrivateKey -and
        $_.NotBefore -le (Get-Date) -and $_.NotAfter -gt (Get-Date).AddDays(30) -and
        @($_.EnhancedKeyUsageList | Where-Object { $_.ObjectId -eq '1.3.6.1.5.5.7.3.3' }).Count -gt 0
    } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1
if (-not $certificate) {
    $certificate = New-SelfSignedCertificate -Type Custom `
        -Subject $identity.Publisher -FriendlyName $friendlyName `
        -CertStoreLocation 'Cert:\CurrentUser\My' `
        -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 `
        -KeyUsage DigitalSignature -KeyExportPolicy NonExportable `
        -NotAfter (Get-Date).AddYears(1) `
        -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3', '2.5.29.19={text}')
}
Export-Certificate -Cert $certificate -FilePath $certificatePath -Force | Out-Null

$layout = Join-Path $storeDir ('DevPackageLayout-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $layout | Out-Null
try {
    Get-ChildItem -LiteralPath $appDir -Force | Copy-Item -Destination $layout -Recurse -Force
    $assets = Join-Path $layout 'Assets'
    New-Item -ItemType Directory -Path $assets -Force | Out-Null
    # Include the required target-size unplated icons alongside the base logos.
    Get-ChildItem -LiteralPath $assetsDir -Force |
        Copy-Item -Destination $assets -Recurse -Force
    $manifest.Save((Join-Path $layout 'AppxManifest.xml'))

    # Register target-size and unplated variants for Windows Shell icon selection.
    & $makePri new /pr $layout /cf $priConfig /mn (Join-Path $layout 'AppxManifest.xml') /of (Join-Path $layout 'resources.pri') /o
    if ($LASTEXITCODE -ne 0) { throw 'makepri failed while indexing the MSIX icon assets.' }

    & $makeAppx pack /d $layout /p $outputPath /o
    if ($LASTEXITCODE -ne 0) { throw 'makeappx failed to create the development MSIX.' }

    & $signTool sign /fd SHA256 /s My /sha1 $certificate.Thumbprint $outputPath
    if ($LASTEXITCODE -ne 0) { throw 'signtool failed to sign the development MSIX.' }
}
finally {
    # Only remove the unique staging directory created by this invocation.
    $resolvedLayout = [IO.Path]::GetFullPath($layout)
    if ([IO.Path]::GetDirectoryName($resolvedLayout) -ne [IO.Path]::GetFullPath($storeDir) -or
        [IO.Path]::GetFileName($resolvedLayout) -notmatch '^DevPackageLayout-[0-9a-f]{32}$') {
        throw "Refusing to remove unexpected staging directory: $resolvedLayout"
    }
    Remove-Item -LiteralPath $resolvedLayout -Recurse -Force
}

Write-Host "Signed development MSIX: $outputPath"
Write-Host "Public certificate: $certificatePath (expires $($certificate.NotAfter))"
Write-Host 'For local installation, run the following in an elevated PowerShell window:'
Write-Host "Import-Certificate -FilePath '$($certificatePath.Replace("'", "''"))' -CertStoreLocation Cert:\LocalMachine\TrustedPeople"
Write-Host 'Then install the package as your normal user:'
Write-Host "Add-AppxPackage -Path '$($outputPath.Replace("'", "''"))'"
