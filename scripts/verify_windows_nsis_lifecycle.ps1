param(
  [Parameter(Mandatory = $true)][string]$CandidateInstaller,
  [Parameter(Mandatory = $true)][string]$ExpectedVersion,
  [Parameter(Mandatory = $true)][string]$Output
)

$ErrorActionPreference = 'Stop'
$installer = (Resolve-Path -LiteralPath $CandidateInstaller).Path
$installRoot = Join-Path $env:LOCALAPPDATA 'Programs\DBFox'

try {
  $process = Start-Process -FilePath $installer -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
  if ($process.ExitCode -ne 0) { throw "NSIS install failed: $($process.ExitCode)" }
  $application = Join-Path $installRoot 'DBFox.exe'
  if (-not (Test-Path -LiteralPath $application -PathType Leaf)) {
    throw "Installed DBFox executable is missing: $application"
  }
  $installedVersion = (Get-Item -LiteralPath $application).VersionInfo.ProductVersion
  if (-not $installedVersion.StartsWith($ExpectedVersion)) {
    throw "Installed version $installedVersion does not match $ExpectedVersion"
  }
  $signature = Get-AuthenticodeSignature -LiteralPath $application
  if ($signature.Status -ne 'Valid') {
    throw "Installed DBFox signature is invalid: $($signature.Status)"
  }

  $uninstaller = Join-Path $installRoot 'Uninstall DBFox.exe'
  if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) {
    throw 'NSIS uninstaller is missing.'
  }
  $uninstall = Start-Process -FilePath $uninstaller -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
  if ($uninstall.ExitCode -ne 0) { throw "NSIS uninstall failed: $($uninstall.ExitCode)" }
  if (Test-Path -LiteralPath $application) { throw 'NSIS uninstall retained the application binary.' }

  $result = [ordered]@{
    schemaVersion = 1
    installer = $installer
    expectedVersion = $ExpectedVersion
    installedVersion = $installedVersion
    authenticode = 'Valid'
    freshInstall = 'passed'
    uninstall = 'passed'
  }
  $outputPath = [IO.Path]::GetFullPath($Output)
  [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputPath)) | Out-Null
  $result | ConvertTo-Json | Set-Content -LiteralPath $outputPath -Encoding utf8
} finally {
  $fallbackUninstaller = Join-Path $installRoot 'Uninstall DBFox.exe'
  if (Test-Path -LiteralPath $fallbackUninstaller) {
    Start-Process -FilePath $fallbackUninstaller -ArgumentList '/S' `
      -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue
  }
}
