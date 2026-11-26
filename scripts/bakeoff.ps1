<#
Model comparison on the dev set (experiment 3.7, rule in docs/20). Two steps, from the repo root:

  1. Calibrate (about 20 to 40 minutes): three fixed answerable questions per model and variant,
     timed, then a projected full-run time and a RUN or SKIP decision. Writes
     eval\runs\bakeoff\calibration.json.
         .\scripts\bakeoff.ps1 -Calibrate
  2. Run (unattended): every variant marked RUN, one full dev run each, under a hard time cap.
         .\scripts\bakeoff.ps1

Reasoning models get two separate variants: "think" (thinking on, 3500-token answer budget) and
"nothink" (thinking off, 512 tokens, the same as the reference). Other models get one: "plain"
(512 tokens). A run that passes its time cap is stopped and logged. Nothing here touches
git-tracked files or the hold-out.
#>
param(
    [switch]$Calibrate,
    # quick, non-reasoning models first so their results exist even if a slow one is cut off
    [string[]]$Models = @("gemma3:12b", "phi4:14b", "gemma4:12b", "qwen3.5:9b", "qwen3:14b"),
    [string]$Reference = "eval\runs\20261125T183115Z-baseline-dev",
    [string]$CalibrationItems = "G-B13-001,G-CPR-004,G-STR-001",
    [int]$ThinkBudget = 3500,
    [int]$PlainBudget = 512,
    [int]$MaxRunMin = 90,
    [int]$TotalBudgetMin = 600,
    [int]$CalibrationTimeoutMin = 25,
    [int]$DevItems = 47,
    [string]$OllamaUrl = "http://127.0.0.1:11434"
)

$ErrorActionPreference = "Continue"
$stamp = (Get-Date).ToString("yyyyMMdd-HHmm")
$base = "eval\runs\bakeoff"
$calFile = Join-Path $base "calibration.json"
$root = if ($Calibrate) { "$base\$stamp-calibration" } else { "$base\$stamp" }
New-Item -ItemType Directory -Force -Path $root | Out-Null
$summary = Join-Path $root "summary.txt"

function Log([string]$text) {
    $line = "{0}  {1}" -f (Get-Date).ToString("HH:mm:ss"), $text
    Write-Host $line
    Add-Content -Path $summary -Value $line
}

# Run one `eval` command with a time limit. Retries when Application Control blocks the launcher
# (intermittent; a retry works). Returns @{Code; Out; Err; TimedOut}.
function Invoke-Eval([string]$evalArgs, [string]$tag, [int]$timeoutMin) {
    for ($try = 1; $try -le 3; $try++) {
        $out = Join-Path $root "$tag.out.txt"
        $err = Join-Path $root "$tag.err.txt"
        $argLine = "run python -m bfs_reg_copilot.eval $evalArgs"
        $p = Start-Process -FilePath "uv" -ArgumentList $argLine -NoNewWindow -PassThru `
            -RedirectStandardOutput $out -RedirectStandardError $err
        $null = $p.Handle  # keeps ExitCode readable after the process ends (Windows PowerShell quirk)
        $done = $p.WaitForExit($timeoutMin * 60 * 1000)
        if (-not $done) {
            & taskkill /PID $p.Id /T /F | Out-Null
            $partial = if (Test-Path $out) { Get-Content $out -Raw } else { "" }
            return @{ Code = -1; Out = $partial; Err = "timed out after $timeoutMin min"; TimedOut = $true }
        }
        $outText = if (Test-Path $out) { Get-Content $out -Raw } else { "" }
        $errText = if (Test-Path $err) { Get-Content $err -Raw } else { "" }
        if ($p.ExitCode -ne 0 -and ($errText -match "4551" -or $errText -match "Application Control")) {
            Log "  launch blocked by Application Control (attempt $try of 3); waiting 30 s"
            Start-Sleep -Seconds 30
            continue
        }
        return @{ Code = $p.ExitCode; Out = $outText; Err = $errText; TimedOut = $false }
    }
    return @{ Code = -2; Out = ""; Err = "launcher blocked three times"; TimedOut = $false }
}

function Unload-Model([string]$model) {
    try {
        $body = @{ model = $model; keep_alive = 0 } | ConvertTo-Json
        Invoke-RestMethod -Uri "$OllamaUrl/api/generate" -Method Post -ContentType "application/json" -Body $body | Out-Null
    } catch { Log "  could not unload $model ($($_.Exception.Message))" }
}

# Load the model with the same window the experiment uses, so the timed run is not a cold start.
function Warm-Model([string]$model) {
    try {
        $body = @{ model = $model; prompt = "ok"; stream = $false; keep_alive = "10m"
                   options = @{ num_ctx = 8192; num_predict = 1 } } | ConvertTo-Json -Depth 4
        Invoke-RestMethod -Uri "$OllamaUrl/api/generate" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 600 | Out-Null
    } catch { Log "  warm-up failed ($($_.Exception.Message)); the timing will include loading" }
}

function Get-Thinker([string]$model) {
    try {
        $body = @{ model = $model } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "$OllamaUrl/api/show" -Method Post -ContentType "application/json" -Body $body
        if ($null -ne $r.capabilities) {
            $caps = @($r.capabilities)
            Log "  capabilities: $($caps -join ', ')"
            return ($caps -contains "thinking")
        }
    } catch { }
    $guess = $model -match "^qwen3"
    Log "  capabilities not reported by Ollama; guessing thinker = $guess from the name"
    return $guess
}

# clean = ran, no item errors, no malformed model outputs
function Test-Clean($result) {
    if ($result.Code -ne 0) { return $false }
    $errors = [regex]::Match($result.Out, "errors (\d+)")
    $malformed = [regex]::Match($result.Out, "malformed model outputs: (\d+)")
    if (-not $errors.Success -or -not $malformed.Success) { return $false }
    return ([int]$errors.Groups[1].Value -eq 0) -and ([int]$malformed.Groups[1].Value -eq 0)
}

function Get-InstalledTags {
    return @((Invoke-RestMethod -Uri "$OllamaUrl/api/tags").models | ForEach-Object { $_.name })
}

try { $tags = Get-InstalledTags } catch { Log "STOP: cannot reach Ollama at $OllamaUrl"; exit 1 }

# ---------------------------------------------------------------- calibration
if ($Calibrate) {
    Log "calibration started: items $CalibrationItems; a full dev run is $DevItems items"
    $itemCount = ($CalibrationItems -split ",").Count
    $rows = @()
    foreach ($model in $Models) {
        $safe = $model -replace "[:/]", "-"
        Log "=== $model ==="
        if ($tags -notcontains $model) { Log "  SKIP: not installed (ollama pull $model)"; continue }
        $thinker = Get-Thinker $model
        $variants = if ($thinker) { @("think", "nothink") } else { @("plain") }
        foreach ($variant in $variants) {
            $budget = if ($variant -eq "think") { $ThinkBudget } else { $PlainBudget }
            $flag = if ($variant -eq "nothink") { "--no-think" } else { "" }
            Warm-Model $model
            $watch = [System.Diagnostics.Stopwatch]::StartNew()
            $r = Invoke-Eval "run --pipeline baseline --model $model --items $CalibrationItems --max-answer-tokens $budget --out-dir $root\cal-$safe-$variant $flag" "cal-$safe-$variant" $CalibrationTimeoutMin
            $watch.Stop()
            $clean = Test-Clean $r
            $perItem = [math]::Round($watch.Elapsed.TotalSeconds / $itemCount, 1)
            $projected = [math]::Round($perItem * $DevItems / 60, 0)
            $decision = "RUN"
            if (-not $clean) { $decision = "SKIP (not clean: $($r.Err))" }
            elseif ($projected -gt (0.7 * $MaxRunMin)) { $decision = "SKIP (projected $projected min is over 70% of the $MaxRunMin min cap)" }
            Log ("  {0,-8} clean={1}  {2} s per item  projected full run {3} min  -> {4}" -f $variant, $clean, $perItem, $projected, $decision)
            $rows += [pscustomobject]@{ model = $model; variant = $variant; budget = $budget; noThink = ($variant -eq "nothink")
                                        clean = $clean; secondsPerItem = $perItem; projectedMin = $projected; decision = $decision }
        }
        Unload-Model $model
    }
    ConvertTo-Json -InputObject @($rows) -Depth 4 | Set-Content -Path $calFile -Encoding ASCII
    Log "calibration written to $calFile"
    $runs = @($rows | Where-Object { $_.decision -eq "RUN" })
    $total = ($runs | Measure-Object -Property projectedMin -Sum).Sum
    Log "variants to run: $($runs.Count); projected total about $total min (each capped at $MaxRunMin min)"
    exit 0
}

# ---------------------------------------------------------------- full runs
if (-not (Test-Path $calFile)) { Log "STOP: no calibration yet; run .\scripts\bakeoff.ps1 -Calibrate first"; exit 1 }
if (-not (Test-Path (Join-Path $Reference "grades.csv"))) { Log "STOP: no grades.csv in $Reference"; exit 1 }
$plan = @((Get-Content $calFile -Raw | ConvertFrom-Json) | Where-Object { $_.decision -eq "RUN" })
Log "bake-off started; reference $Reference; $($plan.Count) variants; hard cap $MaxRunMin min each; total budget $TotalBudgetMin min"
$began = Get-Date

foreach ($row in $plan) {
    $model = $row.model
    $variant = $row.variant
    $safe = $model -replace "[:/]", "-"
    Log "=== $model ($variant) ==="
    $elapsed = ((Get-Date) - $began).TotalMinutes
    if (($elapsed + $MaxRunMin) -gt $TotalBudgetMin) { Log "  SKIP: the total time budget would be exceeded"; continue }
    $flag = if ($row.noThink) { "--no-think" } else { "" }
    Warm-Model $model
    $runDir = Join-Path $root "$safe-$variant"
    $started = Get-Date
    $r = Invoke-Eval "run --pipeline baseline --model $model --max-answer-tokens $($row.budget) --out-dir $runDir $flag" "$safe-$variant-full" $MaxRunMin
    $minutes = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
    if ($r.TimedOut -or $r.Code -ne 0) { Log "  FAILED after $minutes min: code $($r.Code) $($r.Err)"; Unload-Model $model; continue }
    $folder = Get-ChildItem $runDir -Directory | Select-Object -First 1
    if ($null -eq $folder) { Log "  FAILED: no run folder written"; Unload-Model $model; continue }
    Log "  full run done in $minutes min (projected $($row.projectedMin)): $($folder.FullName)"
    $score = Invoke-Eval "score $($folder.FullName)" "$safe-$variant-score" 10
    Add-Content -Path $summary -Value $score.Out
    $sheet = Invoke-Eval "grade-sheet $($folder.FullName) --carry-from $Reference --carry-grades $Reference\grades.csv" "$safe-$variant-sheet" 10
    Add-Content -Path $summary -Value $sheet.Out
    Unload-Model $model
}
Log "bake-off finished"
