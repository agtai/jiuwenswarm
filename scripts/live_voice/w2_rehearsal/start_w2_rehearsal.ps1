[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Preflight', 'Controller', 'Chrome', 'SpeechPreflight')]
    [string] $Action,

    [string] $Config,
    [string] $Python,
    [string] $Wav
)

$ErrorActionPreference = 'Stop'
$bundleRoot = $PSScriptRoot

function Resolve-ExistingFile {
    param([Parameter(Mandatory = $true)][string] $Path, [Parameter(Mandatory = $true)][string] $Label)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($item.PSIsContainer -or $item.PSProvider.Name -ne 'FileSystem') {
        throw "$Label must be an existing filesystem file: $Path"
    }
    return $item.FullName
}

$configValue = $null
$candidateBundle = $null
if ($Config) {
    $configPath = Resolve-ExistingFile -Path $Config -Label 'Runtime config'
    $configValue = Get-Content -LiteralPath $configPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($configValue.schema -ne 'machine-private.w2-rehearsal-runtime-config.v2') {
        throw 'Runtime config schema is unsupported'
    }
    $candidateBundle = Join-Path ([string] $configValue.candidate_root) 'scripts\live_voice\w2_rehearsal'
    if (-not (Test-Path -LiteralPath $candidateBundle -PathType Container)) {
        throw "Candidate-bound rehearsal toolkit is missing: $candidateBundle"
    }
}

if (-not $Python) {
    if ($configValue -and $configValue.python) {
        $Python = [string] $configValue.python
    } else {
        $repoPython = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $bundleRoot))) '.venv\Scripts\python.exe'
        $Python = $repoPython
    }
}
$Python = Resolve-ExistingFile -Path $Python -Label 'Python interpreter'

switch ($Action) {
    'Preflight' {
        if (-not $configValue) { throw '-Config is required for Preflight' }
        & $Python (Join-Path $candidateBundle 'w2_rehearsal_runtime_controller.py') --config $configPath --preflight-only
        exit $LASTEXITCODE
    }
    'Controller' {
        if (-not $configValue) { throw '-Config is required for Controller' }
        & $Python -u (Join-Path $candidateBundle 'w2_rehearsal_runtime_controller.py') --config $configPath
        exit $LASTEXITCODE
    }
    'Chrome' {
        if (-not $configValue) { throw '-Config is required for Chrome' }
        $chrome = Resolve-ExistingFile -Path ([string] $configValue.chrome) -Label 'Chrome executable'
        $profile = [IO.Path]::GetFullPath([string] $configValue.chrome_profile)
        if (Test-Path -LiteralPath $profile) {
            throw "Isolated Chrome profile already exists; use a fresh attempt path: $profile"
        }
        $preparedWav = Resolve-ExistingFile -Path ([string] $configValue.prepared_wav) -Label 'Prepared WAV'
        $vitePort = [int] $configValue.ports.vite
        $debugPort = [int] $configValue.ports.chrome_debug
        if (-not (Get-NetTCPConnection -State Listen -LocalPort $vitePort -ErrorAction SilentlyContinue)) {
            throw "Vite is not listening on port $vitePort"
        }
        if (Get-NetTCPConnection -State Listen -LocalPort $debugPort -ErrorAction SilentlyContinue) {
            throw "Chrome debugging port $debugPort is already in use"
        }
        $arguments = @(
            "`"--user-data-dir=$profile`"",
            '--no-first-run',
            '--no-default-browser-check',
            '--use-fake-device-for-media-stream',
            "`"--use-file-for-fake-audio-capture=$preparedWav`"",
            '--use-fake-ui-for-media-stream',
            '--autoplay-policy=no-user-gesture-required',
            '--remote-debugging-address=127.0.0.1',
            "--remote-debugging-port=$debugPort",
            "http://127.0.0.1:$vitePort"
        )
        $process = Start-Process -FilePath $chrome -ArgumentList $arguments -PassThru
        Write-Host "W2_REHEARSAL_CHROME_STARTED pid=$($process.Id) profile=$profile" -ForegroundColor Green
        exit 0
    }
    'SpeechPreflight' {
        if (-not $Wav) {
            $Wav = if ($configValue) {
                [string] $configValue.prepared_wav
            } else {
                Join-Path $bundleRoot 'assets\voice-command-48k-mono-pcm16.wav'
            }
        }
        $Wav = Resolve-ExistingFile -Path $Wav -Label 'Prepared WAV'
        $speechProbe = if ($candidateBundle) {
            Join-Path $candidateBundle 'w2_wav_speech_preflight.py'
        } else {
            Join-Path $bundleRoot 'w2_wav_speech_preflight.py'
        }
        $speechProbe = Resolve-ExistingFile -Path $speechProbe -Label 'Candidate-bound Speech probe'
        $secureKey = Read-Host 'Enter OpenAI API key (hidden; process memory only)' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        $previous = @{}
        foreach ($name in @(
            'LIVE_VOICE_SPEECH_API_KEY', 'LIVE_VOICE_SPEECH_API_BASE',
            'LIVE_VOICE_SPEECH_STT_MODEL', 'LIVE_VOICE_SPEECH_TTS_MODEL',
            'LIVE_VOICE_SPEECH_TTS_VOICE'
        )) {
            $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        }
        $exitCode = 2
        try {
            $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
            $env:LIVE_VOICE_SPEECH_API_KEY = $plainKey
            $env:LIVE_VOICE_SPEECH_API_BASE = 'https://api.openai.com/v1'
            $env:LIVE_VOICE_SPEECH_STT_MODEL = 'gpt-4o-mini-transcribe'
            $env:LIVE_VOICE_SPEECH_TTS_MODEL = 'gpt-4o-mini-tts'
            $env:LIVE_VOICE_SPEECH_TTS_VOICE = 'marin'
            & $Python -u $speechProbe --wav $Wav
            $exitCode = $LASTEXITCODE
        } finally {
            foreach ($name in $previous.Keys) {
                [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
            }
            $plainKey = $null
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
        exit $exitCode
    }
}
