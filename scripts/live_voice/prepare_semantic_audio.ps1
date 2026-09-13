[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$CorpusPath = (Join-Path $PSScriptRoot '../../tests/support/live_voice/audio_journey/corpus.json'),
    [string]$Voice = 'Microsoft Huihui Desktop'
)
$ErrorActionPreference = 'Stop'
$audioOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $audioOutput -Force | Out-Null
$corpus = Get-Content -LiteralPath $CorpusPath -Raw -Encoding UTF8 | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$entries = @()
try {
    $synth.SelectVoice($Voice)
    foreach ($sample in $corpus.samples) {
        if ($sample.id -notmatch '^[a-zA-Z0-9_]{1,64}$') { throw 'Invalid audio sample ID' }
        $target = Join-Path $audioOutput ($sample.id + '.wav')
        if (Test-Path -LiteralPath $target) { throw "Refusing to replace cached audio: $target" }
        $synth.SetOutputToWaveFile($target, $format)
        $synth.Speak([string]$sample.text)
        $synth.SetOutputToNull()
        $entries += [ordered]@{
            id = $sample.id; text = $sample.text; source = ('Windows System.Speech / ' + $Voice)
            file = ($sample.id + '.wav'); format = 'WAV PCM signed 16-bit mono 24000 Hz'
            sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
} finally { $synth.Dispose() }
$manifest = [ordered]@{
    schema_version = 1; created_at = [DateTimeOffset]::UtcNow.ToString('o')
    corpus_sha256 = (Get-FileHash -LiteralPath $CorpusPath -Algorithm SHA256).Hash.ToLowerInvariant()
    samples = $entries
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $audioOutput 'manifest.json') -Encoding UTF8
Write-Output "Prepared $($entries.Count) audio samples in $audioOutput (input generation only; not E2E evidence)."
