#Requires -Version 7.4
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InstallRoot,

    [string]$ProfileRoot = (Join-Path $env:APPDATA 'DBFox'),

    [ValidatePattern('^[a-z0-9][a-z0-9._-]*:[a-zA-Z0-9._-]+$')]
    [string]$Model = 'qwen3.5:4b-q4_K_M',

    [ValidateRange(8192, 32768)]
    [int]$ContextLength = 32768
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') {
    throw 'The portable DBFox local-model setup requires Windows x64.'
}
if ($Model.EndsWith('-cloud') -or $Model.EndsWith(':cloud')) {
    throw 'Choose a downloadable model for local inference.'
}

# Official standalone Windows release, including the NVIDIA runner libraries.
$release = 'v0.40.16'
$archiveName = 'ollama-windows-amd64.zip'
$archiveHash = '50fcf5ad54277f2fa5d173ebfc93bcb017adbc0c9ef2314daabc96ca9e6aa64e'
$install = [IO.Path]::GetFullPath($InstallRoot)
$drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($install))
if ($drive.DriveType -ne [IO.DriveType]::Fixed) {
    throw 'Choose a fixed local drive for the runtime and weights.'
}
if ($drive.AvailableFreeSpace -lt 12GB) {
    throw "At least 12 GiB of free space is required on $($drive.Name) for download, extraction and model storage."
}
$runtime = Join-Path $install "runtime\$release"
$models = Join-Path $install 'models'
$state = Join-Path $install 'state'
$scratch = Join-Path $install 'tmp'
$exe = Join-Path $runtime 'ollama.exe'
New-Item -ItemType Directory -Force -Path $runtime, $models, $state, $scratch | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $runtime '.verified-archive-sha256'))) {
    $archive = Join-Path $scratch $archiveName
    Write-Output "Downloading $release to $scratch"
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        & curl.exe --fail --location --silent --show-error --continue-at - --output $archive "https://github.com/ollama/ollama/releases/download/$release/$archiveName"
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 2
    }
    if ($LASTEXITCODE -ne 0) {
        throw 'Ollama download failed. Run the same command again to resume.'
    }
    $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $archiveHash) {
        Remove-Item -LiteralPath $archive -Force
        throw 'The Ollama archive checksum did not match the pinned release.'
    }
    Write-Output "Extracting the verified runtime to $runtime"
    [IO.Compression.ZipFile]::ExtractToDirectory($archive, $runtime, $true)
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw 'The runtime archive did not contain ollama.exe.'
    }
    Set-Content -LiteralPath (Join-Path $runtime '.verified-archive-sha256') -Value $archiveHash -Encoding ascii
    Remove-Item -LiteralPath $archive -Force
}
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "The verified Ollama runtime is incomplete at $runtime."
}

$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
try {
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
} finally {
    $listener.Stop()
}
$endpoint = "127.0.0.1:$port"
$ollamaEnvironment = @{
    OLLAMA_HOST = $endpoint
    OLLAMA_MODELS = $models
    OLLAMA_NO_CLOUD = '1'
    OLLAMA_CONTEXT_LENGTH = [string]$ContextLength
    OLLAMA_NUM_PARALLEL = '1'
    OLLAMA_MAX_LOADED_MODELS = '1'
    USERPROFILE = $state
    TEMP = $scratch
    TMP = $scratch
}
$serverOptions = @{
    FilePath = $exe
    ArgumentList = 'serve'
    WorkingDirectory = $runtime
    Environment = $ollamaEnvironment
    WindowStyle = 'Hidden'
    PassThru = $true
    RedirectStandardOutput = (Join-Path $scratch 'setup.stdout.log')
    RedirectStandardError = (Join-Path $scratch 'setup.stderr.log')
}
$server = Start-Process @serverOptions
try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($server.HasExited) {
            throw "Ollama exited during startup. See $scratch\setup.stderr.log."
        }
        try {
            $status = Invoke-RestMethod -Uri "http://$endpoint/api/version" -TimeoutSec 2 -NoProxy
            if ('v' + $status.version -eq $release) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) {
        throw 'The dedicated loopback Ollama instance did not become ready.'
    }
    Write-Output "Downloading $Model to $models"
    $pullOptions = $serverOptions.Clone()
    $pullOptions.ArgumentList = @('pull', $Model)
    $pullOptions.Wait = $true
    $pullOptions.RedirectStandardOutput = Join-Path $scratch 'pull.stdout.log'
    $pullOptions.RedirectStandardError = Join-Path $scratch 'pull.stderr.log'
    $pull = Start-Process @pullOptions
    if ($pull.ExitCode -ne 0) {
        throw "Model pull failed. See $scratch\pull.stderr.log and rerun the setup to resume."
    }
    $downloaded = (Invoke-RestMethod -Uri "http://$endpoint/api/tags" -TimeoutSec 10 -NoProxy).models |
        Where-Object { $_.name -ceq $Model } | Select-Object -First 1
    if (-not $downloaded -or $downloaded.size -le 0) {
        throw 'The downloaded model could not be verified in the local store.'
    }
    $showOptions = @{
        Method = 'Post'
        Uri = "http://$endpoint/api/show"
        TimeoutSec = 10
        NoProxy = $true
        ContentType = 'application/json'
        Body = (@{ model = $Model } | ConvertTo-Json -Compress)
    }
    $modelInfo = Invoke-RestMethod @showOptions
    if ($modelInfo.capabilities -notcontains 'tools') {
        throw 'The downloaded model does not advertise function calling.'
    }
} finally {
    if (-not $server.HasExited) {
        $server.Kill($true)
        $server.WaitForExit(8000) | Out-Null
    }
}

$profile = [IO.Path]::GetFullPath($ProfileRoot)
New-Item -ItemType Directory -Force -Path $profile | Out-Null
$profilePath = Join-Path $profile 'local-model.json'
$pending = "$profilePath.$([guid]::NewGuid().ToString('N')).tmp"
@{
    model_name = $Model
    model_digest = [string]$downloaded.digest
    model_size_bytes = [long]$downloaded.size
    executable = $exe
    models_dir = $models
    state_dir = $state
    scratch_dir = $scratch
    context_length = $ContextLength
} | ConvertTo-Json | Set-Content -LiteralPath $pending -Encoding utf8
[IO.File]::Move($pending, $profilePath, $true)
Write-Output "$Model installed ($([Math]::Round($downloaded.size / 1GB, 2)) GiB). Local default saved in $profilePath."
