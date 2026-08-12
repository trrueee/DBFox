param(
  [Parameter(Mandatory = $true)]
  [string]$CandidateMsi,
  [Parameter(Mandatory = $true)]
  [string]$ExpectedVersion,
  [string]$PreviousMsi,
  [Parameter(Mandatory = $true)]
  [string]$Output
)

$ErrorActionPreference = 'Stop'

function Invoke-Msi {
  param([ValidateSet('install', 'uninstall')][string]$Operation, [string]$Path)
  $verb = if ($Operation -eq 'install') { '/i' } else { '/x' }
  $process = Start-Process `
    -FilePath 'msiexec.exe' `
    -ArgumentList @($verb, "`"$Path`"", '/qn', '/norestart') `
    -Wait `
    -PassThru `
    -WindowStyle Hidden
  if ($process.ExitCode -notin @(0, 3010)) {
    throw "MSI $Operation failed with exit code $($process.ExitCode): $Path"
  }
}

function Get-DBFoxInstall {
  $roots = @(
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
  )
  return $roots |
    ForEach-Object { Get-ItemProperty $_ -ErrorAction SilentlyContinue } |
    Where-Object { $_.DisplayName -eq 'DBFox' } |
    Select-Object -First 1
}

function Assert-InstalledVersion {
  param([string]$Version)
  $installed = Get-DBFoxInstall
  if ($null -eq $installed) {
    throw "DBFox is not registered as installed after MSI operation."
  }
  if ($installed.DisplayVersion -ne $Version) {
    throw "Expected installed DBFox $Version, found $($installed.DisplayVersion)."
  }
}

$candidate = (Resolve-Path -LiteralPath $CandidateMsi).Path
$previous = if ([string]::IsNullOrWhiteSpace($PreviousMsi)) {
  $null
} else {
  (Resolve-Path -LiteralPath $PreviousMsi).Path
}
$outputPath = [IO.Path]::GetFullPath($Output)
$candidateInstalled = $false
$previousInstalled = $false

if ($null -ne (Get-DBFoxInstall)) {
  throw 'DBFox is already installed on the clean release runner.'
}

try {
  if ($null -ne $previous) {
    Invoke-Msi -Operation install -Path $previous
    $previousInstalled = $true
    if ($null -eq (Get-DBFoxInstall)) {
      throw 'The previous published DBFox MSI did not register an installation.'
    }
  }

  Invoke-Msi -Operation install -Path $candidate
  $candidateInstalled = $true
  $previousInstalled = $false
  Assert-InstalledVersion -Version $ExpectedVersion

  Invoke-Msi -Operation uninstall -Path $candidate
  $candidateInstalled = $false
  if ($null -ne (Get-DBFoxInstall)) {
    throw 'DBFox remains registered after candidate MSI uninstall.'
  }

  $result = [ordered]@{
    verified = $true
    candidate_msi = $candidate
    expected_version = $ExpectedVersion
    fresh_install = $true
    upgrade = if ($null -eq $previous) { 'not-applicable-no-published-predecessor' } else { 'verified' }
    uninstall = 'verified'
  }
  $directory = Split-Path -Parent $outputPath
  New-Item -ItemType Directory -Path $directory -Force | Out-Null
  $result | ConvertTo-Json | Set-Content -LiteralPath $outputPath -Encoding utf8
  $result | ConvertTo-Json -Compress
} finally {
  if ($candidateInstalled) {
    Invoke-Msi -Operation uninstall -Path $candidate
  } elseif ($previousInstalled -and $null -ne $previous) {
    Invoke-Msi -Operation uninstall -Path $previous
  }
}
