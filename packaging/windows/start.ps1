# VietPoet launcher for Windows: choose a model, download it, start LM Studio's server, load the model, open the poem page.
# ASCII only on purpose: Windows PowerShell 5.1 misreads UTF-8 files without a BOM.
param(
    [string]$Size,          # 4B or 9B (skips the question)
    [string]$Device,        # gpu or cpu (skips the question)
    [switch]$Reconfigure,   # ask again instead of using the saved choice
    [switch]$NoBrowser,     # do not open the page in the browser
    [switch]$SetupOnly      # do everything except starting the page (used to test the package)
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'    # Invoke-WebRequest is far faster without its progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Owner = if ($env:VIETPOET_HF_OWNER) { $env:VIETPOET_HF_OWNER } else { 'peterbuitho' }
$HfBase = if ($env:VIETPOET_HF_BASE) { $env:VIETPOET_HF_BASE } else { 'https://huggingface.co' }
$PagePort = if ($env:VIETPOET_PORT) { $env:VIETPOET_PORT } else { '7860' }
$Identifier = 'vietpoet'
$SettingsPath = Join-Path $Root 'settings.json'
$MarginMiB = 600      # graphics memory kept free for the desktop and browser

# Graphics memory (MiB) each setup needs once loaded, measured with LM Studio (context = 1k tokens per parallel slot).
# Listed best first: the larger file (Q8_0, near-lossless) and more parallel requests (faster) are preferred.
$Profiles = @(
    @{ Size = '4B'; Quant = 'Q8_0';   Par = 16; Need = 6104 },
    @{ Size = '4B'; Quant = 'Q8_0';   Par = 8;  Need = 5404 },
    @{ Size = '4B'; Quant = 'Q8_0';   Par = 4;  Need = 5054 },
    @{ Size = '4B'; Quant = 'Q4_K_M'; Par = 16; Need = 4412 },
    @{ Size = '4B'; Quant = 'Q4_K_M'; Par = 8;  Need = 3712 },
    @{ Size = '4B'; Quant = 'Q4_K_M'; Par = 4;  Need = 3362 },
    @{ Size = '9B'; Quant = 'Q8_0';   Par = 16; Need = 9890 },
    @{ Size = '9B'; Quant = 'Q8_0';   Par = 8;  Need = 9190 },
    @{ Size = '9B'; Quant = 'Q8_0';   Par = 4;  Need = 8858 },
    @{ Size = '9B'; Quant = 'Q4_K_M'; Par = 16; Need = 6658 },
    @{ Size = '9B'; Quant = 'Q4_K_M'; Par = 8;  Need = 5958 },
    @{ Size = '9B'; Quant = 'Q4_K_M'; Par = 4;  Need = 5626 }
)

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Note($text) { Write-Host "   $text" }

function Get-Local($url) {
    # Windows PowerShell 5.1 spends about 2 s per call on proxy auto-detection, which trips short timeouts on localhost
    $old = [System.Net.WebRequest]::DefaultWebProxy
    [System.Net.WebRequest]::DefaultWebProxy = $null
    try { return Invoke-RestMethod $url -TimeoutSec 5 } finally { [System.Net.WebRequest]::DefaultWebProxy = $old }
}

function Get-Gpu {
    # NVIDIA only: nvidia-smi is the one reliable way to read free graphics memory. Returns $null if there is none.
    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { return $null }
    try {
        $line = (& nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits) | Select-Object -First 1
        $p = $line -split ',\s*'
        $free = [int]$p[2]
        if ($env:VIETPOET_TEST_FREE_MIB) { $free = [int]$env:VIETPOET_TEST_FREE_MIB }    # lets the package be tested with a "small" card
        return @{ Name = $p[0]; TotalMiB = [int]$p[1]; FreeMiB = $free }
    } catch { return $null }
}

function Select-GpuProfile($size, $freeMiB) {
    return $Profiles | Where-Object { $_.Size -eq $size -and ($_.Need + $MarginMiB) -le $freeMiB } | Select-Object -First 1
}

function Ask($question, $options, $default) {
    # Shows numbered options and returns the chosen number; Enter, or no keyboard input at all, gives the default.
    Write-Host ""
    Write-Host $question
    for ($i = 0; $i -lt $options.Count; $i++) { Write-Host ("  [{0}] {1}" -f ($i + 1), $options[$i]) }
    $answer = ''
    try { $answer = Read-Host ("Type 1-{0} and press Enter (just Enter = {1})" -f $options.Count, $default) } catch { $answer = '' }
    $n = 0
    if ([int]::TryParse("$answer", [ref]$n) -and $n -ge 1 -and $n -le $options.Count) { return $n }
    return $default
}

function Lms-Text {
    # Output of an lms command as text. Windows PowerShell 5.1 turns anything a native command writes to stderr into a
    # terminating error while $ErrorActionPreference is Stop, so relax it for the call.
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { return ((& $lms @args 2>&1 | ForEach-Object { "$_" }) -join "`n") } finally { $ErrorActionPreference = $old }
}

function Gb($mib) { return ('{0:N1} GB' -f ($mib / 1024)) }

function New-Setup($size, $device, $profile) {
    $setup = @{ Size = $size; Device = $device }
    if ($device -eq 'cpu') { $setup.Quant = 'Q4_K_M'; $setup.Par = 4; $setup.Gpu = 'off' }
    elseif ($profile) { $setup.Quant = $profile.Quant; $setup.Par = $profile.Par; $setup.Gpu = 'auto' }
    else { $setup.Quant = 'Q4_K_M'; $setup.Par = 4; $setup.Gpu = 'auto' }    # graphics card of unknown size: smallest setup
    return $setup
}

function Choose-Setup {
    $gpu = Get-Gpu
    Step 'Checking this computer'
    if ($gpu) { Note ("graphics card: {0} - {1} total, {2} free" -f $gpu.Name, (Gb $gpu.TotalMiB), (Gb $gpu.FreeMiB)) }
    else { Note 'no NVIDIA graphics card found (AMD and Intel cards cannot be checked)' }

    # 1. which model
    $size = if ($env:VIETPOET_SIZE) { $env:VIETPOET_SIZE } elseif ($Size) { $Size } else { $null }
    if ($size) { $size = $size.ToUpper() }
    if ($size -ne '4B' -and $size -ne '9B') {
        $n = Ask 'Which model do you want?' @(
            '4B - faster, smaller download (2.8 to 4.6 GB). Recommended.',
            '9B - larger (5.8 to 9.8 GB), needs more memory and is a little slower') 1
        $size = @('4B', '9B')[$n - 1]
    }

    # 2. where it runs
    $device = if ($env:VIETPOET_DEVICE) { $env:VIETPOET_DEVICE } elseif ($Device) { $Device } else { $null }
    if ($device) { $device = $device.ToLower() }
    if ($device -eq 'gpu' -or $device -eq 'cpu') {
        $profile = if ($gpu) { Select-GpuProfile $size $gpu.FreeMiB } else { $null }
        return (New-Setup $size $device $profile)
    }
    if ($gpu) {
        $fit = Select-GpuProfile $size $gpu.FreeMiB
        if ($fit) {
            $n = Ask "Where should the $size model run?" @(
                ("Graphics card - fast. Uses the $($fit.Quant) file and needs about {0} of graphics memory. Recommended." -f (Gb ($fit.Need))),
                'CPU - works on any computer but is slow (roughly 15 to 30 seconds per poem or more)') 1
            return (New-Setup $size @('gpu', 'cpu')[$n - 1] $fit)
        }
        # not enough free graphics memory for the chosen size
        $smallest = $Profiles | Where-Object { $_.Size -eq $size } | Select-Object -Last 1
        Write-Host ""
        Write-Host ("The $size model needs at least {0} of free graphics memory and this card has {1} free." -f (Gb ($smallest.Need + $MarginMiB)), (Gb $gpu.FreeMiB)) -ForegroundColor Yellow
        Write-Host 'Close other programs that use the graphics card, or choose:'
        $alt = if ($size -eq '9B') { Select-GpuProfile '4B' $gpu.FreeMiB } else { $null }
        if ($alt) {
            $n = Ask 'What now?' @(
                'Use the 4B model on the graphics card instead. Recommended.',
                "Run the $size model on the CPU (slow)") 1
            if ($n -eq 1) { return (New-Setup '4B' 'gpu' $alt) }
            return (New-Setup $size 'cpu' $null)
        }
        $n = Ask 'What now?' @("Run the $size model on the CPU (slow). Recommended.", 'Try the graphics card anyway (may fail to load)') 1
        if ($n -eq 1) { return (New-Setup $size 'cpu' $null) }
        return (New-Setup $size 'gpu' $null)
    }
    $n = Ask 'No NVIDIA graphics card was found. Where should the model run?' @(
        'CPU - works on any computer but is slow (roughly 15 to 30 seconds per poem or more). Recommended.',
        'Graphics card anyway (AMD or Intel, LM Studio decides; smallest setup, may fail to load)') 1
    return (New-Setup $size @('cpu', 'gpu')[$n - 1] $null)
}

try {
    # ---- 1. LM Studio's command line tool ------------------------------------------------------
    Step 'Looking for LM Studio'
    $lms = $null
    $cmd = Get-Command lms -ErrorAction SilentlyContinue
    if ($cmd) { $lms = $cmd.Source }
    elseif (Test-Path (Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe')) { $lms = Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe' }
    if (-not $lms) {
        throw "LM Studio was not found. Install it from https://lmstudio.ai, open it once, close it, then run this again."
    }
    Note "found $lms"

    # ---- 2. Model size and hardware: ask on the first run, then remember --------------------------
    $setup = $null
    $forced = $Size -or $Device -or $env:VIETPOET_SIZE -or $env:VIETPOET_DEVICE
    if ((Test-Path $SettingsPath) -and -not $Reconfigure -and -not $forced) {
        try {
            $saved = Get-Content $SettingsPath -Raw | ConvertFrom-Json
            $setup = @{ Size = $saved.Size; Device = $saved.Device; Quant = $saved.Quant; Par = [int]$saved.Par; Gpu = $saved.Gpu }
        } catch { $setup = $null }
    }
    if (-not $setup) {
        # our own model from an earlier run would count against the free graphics memory we are about to measure
        if ((Lms-Text ps) -match "(?m)^\s*$Identifier\s") { Lms-Text unload $Identifier | Out-Null; Start-Sleep -Seconds 2 }
        $setup = Choose-Setup
        [pscustomobject]$setup | ConvertTo-Json | Set-Content $SettingsPath
        Note 'saved; run "Change model or hardware.bat" to choose again'
    }
    if ($env:VIETPOET_QUANT) { $setup.Quant = $env:VIETPOET_QUANT }
    $parallel = [int]$setup.Par
    $candidates = if ($env:VIETPOET_CANDIDATES) { [int]$env:VIETPOET_CANDIDATES } else { $parallel }
    $context = 1024 * $parallel                 # each parallel slot needs about 1k tokens
    $where = if ($setup.Device -eq 'cpu') { 'on the CPU' } else { 'on the graphics card' }
    Step ("Model: {0} {1} {2} ({3} requests at a time, {4} candidates per line)" -f $setup.Size, $setup.Quant, $where, $parallel, $candidates)

    # ---- 3. Get the model ----------------------------------------------------------------------
    $Repo = "$Owner/VietPoet-Qwen3.5-$($setup.Size)-GGUF"
    $file = "VietPoet-Qwen3.5-$($setup.Size)-$($setup.Quant).gguf"
    function Find-Model {
        $json = ((& $lms ls --json) -join "`n")
        if (-not $json) { return $null }
        return ($json | ConvertFrom-Json) | Where-Object { $_.path -like "*$file" } | Select-Object -First 1
    }
    $model = Find-Model
    if (-not $model) {
        Step "Downloading $file from Hugging Face ($Repo)"
        $dl = Join-Path $Root 'downloads'
        New-Item -ItemType Directory -Force $dl | Out-Null
        $part = Join-Path $dl "$file.part"
        Note 'this is a few GB; if it stops, run this file again and it resumes'
        & curl.exe -L --fail -C - -o $part "$HfBase/$Repo/resolve/main/$file"
        if ($LASTEXITCODE -ne 0) { throw "Download failed (curl exit code $LASTEXITCODE). Check your internet connection and run this again." }
        Move-Item $part (Join-Path $dl $file) -Force
        Note 'adding it to LM Studio'
        # --copy: the default "move" mode asks a question even with -y and would hang; we delete our copy afterwards
        & $lms import -y --copy --user-repo $Repo (Join-Path $dl $file)
        if ($LASTEXITCODE -ne 0) { throw 'LM Studio could not import the model file.' }
        Remove-Item $dl -Recurse -Force -ErrorAction SilentlyContinue
        $model = Find-Model
        if (-not $model) { throw "The model was downloaded but LM Studio does not list it ($file)." }
    } else {
        Note "already downloaded: $($model.modelKey)"
    }

    # ---- 4. Start the server and load the model ------------------------------------------------
    Step 'Starting the LM Studio server'
    $port = 1234
    $status = Lms-Text status
    if ($status -match 'Server:\s*ON.*?port:\s*(\d+)') { $port = [int]$Matches[1] }
    else { & $lms server start -p $port | Out-Null }
    $api = "http://localhost:$port/v1"
    $ready = $false
    for ($i = 0; $i -lt 60 -and -not $ready; $i++) {
        try { Get-Local "$api/models" | Out-Null; $ready = $true } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) { throw "The LM Studio server did not answer on $api." }
    Note "server ready on $api"

    Step 'Loading the model'
    if ((Lms-Text ps) -match "(?m)^\s*$Identifier\s") { Lms-Text unload $Identifier | Out-Null }
    $loadArgs = @($model.modelKey, '--identifier', $Identifier, '-c', $context, '--parallel', $parallel, '-y')
    if ($setup.Gpu -eq 'off') { $loadArgs += @('--gpu', 'off') }
    # LM Studio's speculative decoding (on by default) accepted about 1 draft token in 20 here, made generation slower, and
    # crashed the CUDA engine at 16 parallel requests; turn it off. Older LM Studio versions do not know the flag: retry without it.
    & $lms load @loadArgs '--no-speculative-draft-mtp' | Out-Null
    if ($LASTEXITCODE -ne 0) { & $lms load @loadArgs | Out-Null }
    if ($LASTEXITCODE -ne 0) { throw 'LM Studio could not load the model (not enough memory?). Run "Change model or hardware.bat" and pick a smaller setup or the CPU.' }
    Note 'loaded'

    # ---- 5. Python environment (uv brings its own Python, so nothing needs to be installed) ------
    Step 'Preparing the poem page'
    $uv = $null
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { $uv = $cmd.Source }
    else {
        $uv = Join-Path $Root 'tools\uv.exe'
        if (-not (Test-Path $uv)) {
            Note 'downloading uv (a small Python installer, about 20 MB)'
            $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'aarch64' } else { 'x86_64' }
            New-Item -ItemType Directory -Force (Join-Path $Root 'tools') | Out-Null
            $zip = Join-Path $Root 'tools\uv.zip'
            Invoke-WebRequest "https://github.com/astral-sh/uv/releases/latest/download/uv-$arch-pc-windows-msvc.zip" -OutFile $zip
            Expand-Archive $zip -DestinationPath (Join-Path $Root 'tools') -Force
            Remove-Item $zip
            if (-not (Test-Path $uv)) { throw 'Could not unpack uv.' }
        }
    }
    $venv = Join-Path $Root '.venv-app'
    $python = Join-Path $venv 'Scripts\python.exe'
    $marker = Join-Path $venv 'requirements.sha256'
    $want = (Get-FileHash (Join-Path $Root 'requirements.txt') -Algorithm SHA256).Hash
    if (-not ((Test-Path $marker) -and ((Get-Content $marker -Raw).Trim() -eq $want))) {
        Note 'installing (first run only, a minute or two)'
        & $uv venv $venv --python 3.12 --clear --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
        & $uv pip install --python $python -r (Join-Path $Root 'requirements.txt') --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Could not install the page requirements.' }
        Set-Content $marker $want
    } else { Note 'ready' }

    if ($SetupOnly) { Step 'Setup finished (-SetupOnly).'; return }

    # ---- 6. Run the page -----------------------------------------------------------------------
    $env:VIETPOET_BASE_URL = $api
    $env:VIETPOET_MODEL = $Identifier
    $env:VIETPOET_CANDIDATES = "$candidates"
    $env:VIETPOET_PORT = $PagePort
    $env:GRADIO_ANALYTICS_ENABLED = 'False'
    $env:PYTHONUTF8 = '1'
    Step "The poem page is starting on http://127.0.0.1:$PagePort  (close this window or press Ctrl+C to stop)"
    $page = Start-Process $python -ArgumentList '-m', 'app.webui' -NoNewWindow -PassThru
    try {
        if (-not $NoBrowser) {
            for ($i = 0; $i -lt 60 -and -not $page.HasExited; $i++) {
                try { Get-Local "http://127.0.0.1:$PagePort/" | Out-Null; Start-Process "http://127.0.0.1:$PagePort/"; break } catch { Start-Sleep -Seconds 1 }
            }
        }
        $page.WaitForExit()
    } finally {
        if (-not $page.HasExited) { $page.Kill() }
        Lms-Text unload $Identifier | Out-Null            # free the graphics memory
    }
}
catch {
    Write-Host ""
    Write-Host "Something went wrong: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
