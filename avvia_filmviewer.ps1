# ==============================================================================
# FilmViewer - Avvio e Gestione Automatica
# ==============================================================================

# Forza codifica UTF-8 per supportare caratteri speciali, box drawing ed emoji
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$esc = [char]27
$cReset  = "$esc[0m"
$cBold   = "$esc[1m"
$cDim    = "$esc[2m"
$cCyan   = "$esc[38;5;39m"
$cNeon   = "$esc[38;5;51m"
$cGreen  = "$esc[38;5;46m"
$cYellow = "$esc[38;5;214m"
$cRed    = "$esc[38;5;196m"
$cGray   = "$esc[38;5;245m"
$cPurple = "$esc[38;5;141m"

try {
    $Host.UI.RawUI.WindowTitle = "FilmViewer - Streaming & Centro Multimediale"
} catch {}

Clear-Host

# Banner iniziale moderno
Write-Host ""
Write-Host "  $cPurple╭─────────────────────────────────────────────────────────────────────────╮$cReset"
Write-Host "  $cPurple│$cReset  $cNeon$cBold  ███████╗██╗██╗     ███╗   ███╗██╗   ██╗██╗███████╗██╗    ██╗      $cReset  $cPurple│$cReset"
Write-Host "  $cPurple│$cReset  $cNeon$cBold  ██╔════╝██║██║     ████╗ ████║██║   ██║██║██╔════╝██║    ██║      $cReset  $cPurple│$cReset"
Write-Host "  $cPurple│$cReset  $cNeon$cBold  █████╗  ██║██║     ██╔████╔██║██║   ██║██║█████╗  ██║ █╗ ██║      $cReset  $cPurple│$cReset"
Write-Host "  $cPurple│$cReset  $cNeon$cBold  ██╔══╝  ██║██║     ██║╚██╔╝██║╚██╗ ██╔╝██║██╔══╝  ██║███╗██║      $cReset  $cPurple│$cReset"
Write-Host "  $cPurple│$cReset  $cNeon$cBold  ██║     ██║███████╗██║ ╚═╝ ██║ ╚████╔╝ ██║███████╗╚███╔███╔╝      $cReset  $cPurple│$cReset"
Write-Host "  $cPurple│$cReset  $cNeon$cBold  ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝  ╚═══╝  ╚═╝╚══════╝ ╚══╝╚══╝       $cReset  $cPurple│$cReset"
Write-Host "  $cPurple│                                                                         │$cReset"
Write-Host "  $cPurple│$cReset            $cCyan$cBold🎬  CENTRO MULTIMEDIALE  •  AVVIO AUTOMATICO$cReset             $cPurple│$cReset"
Write-Host "  $cPurple╰─────────────────────────────────────────────────────────────────────────╯$cReset"
Write-Host ""

# 1. Determinazione cartella del progetto
$projectDir = $null
$searchCandidates = @(
    $PSScriptRoot,
    "C:\Film\FilmViewer",
    "C:\Film",
    "$env:USERPROFILE\Music\Crack\FilmViewer",
    (Get-Location).Path
)

foreach ($dir in $searchCandidates) {
    if ($dir -and (Test-Path (Join-Path $dir "docker-compose.yml"))) {
        $projectDir = $dir
        break
    }
}

if (-not $projectDir) {
    Write-Host "  $cRed✖ ERRORE: Impossibile trovare la cartella di FilmViewer con docker-compose.yml!$cReset"
    Write-Host "  $cGrayCartelle verificate: C:\Film, C:\Film\FilmViewer, $PSScriptRoot$cReset"
    Write-Host ""
    Write-Host -NoNewline "  Premi INVIO per uscire..."
    $null = Read-Host
    exit 1
}

Set-Location $projectDir
Write-Host "  $cGray📁 Cartella di lavoro:$cReset $cCyan$projectDir$cReset"
Write-Host ""

# 2. Controllo e Avvio Automatico di Docker Desktop
function Find-DockerDesktopPath {
    $paths = @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Programs\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
    )

    foreach ($p in $paths) {
        if ($p -and (Test-Path $p)) {
            return $p
        }
    }

    # Controllo scorciatoie Start Menu
    $shortcuts = @(
        "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Docker Desktop.lnk",
        "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Docker Desktop.lnk"
    )
    foreach ($s in $shortcuts) {
        if (Test-Path $s) {
            try {
                $sh = New-Object -ComObject WScript.Shell
                $target = $sh.CreateShortcut($s).TargetPath
                if ($target -and (Test-Path $target)) {
                    return $target
                }
            } catch {}
        }
    }

    # Ricerca rapida in LocalAppData
    $quick = Get-ChildItem "$env:LOCALAPPDATA\Programs" -Filter "Docker Desktop.exe" -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($quick) { return $quick.FullName }

    return $null
}

# Verifica se Docker e' gia' attivo
& docker info 2>&1 | Out-Null
$isDockerRunning = ($LASTEXITCODE -eq 0)

if (-not $isDockerRunning) {
    Write-Host "  $cYellow🐳 Docker Desktop non risulta avviato.$cReset"
    Write-Host "  $cNeon • Avvio automatico di Docker Desktop in background...$cReset"
    
    $dockerExe = Find-DockerDesktopPath
    if ($dockerExe) {
        $dockerDir = Split-Path $dockerExe
        Start-Process -FilePath $dockerExe -WorkingDirectory $dockerDir
    } else {
        # Prova ad avviarlo tramite protocollo o nome generico
        try {
            Start-Process "Docker Desktop"
        } catch {
            Write-Host "  $cRed✖ Impossibile localizzare Docker Desktop sul sistema.$cReset"
            Write-Host "  $cGrayAssicurati che Docker Desktop sia installato.$cReset"
            Write-Host -NoNewline "`n  Premi INVIO per uscire..."
            $null = Read-Host
            exit 1
        }
    }

    # Attesa automatica con spinner grafico (codici Unicode sicuri)
    $spinner = @([char]0x280B, [char]0x2819, [char]0x2839, [char]0x2838, [char]0x283C, [char]0x2834, [char]0x2826, [char]0x2827, [char]0x2807, [char]0x280F)
    $spinIdx = 0
    $startTime = Get-Date

    while ($true) {
        & docker info 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            break
        }
        $char = $spinner[$spinIdx % $spinner.Length]
        $spinIdx++
        $elapsed = [math]::Floor(((Get-Date) - $startTime).TotalSeconds)
        Write-Host -NoNewline "`r  $cYellow$char$cReset Inizializzazione motore Docker in corso... $cGray(${elapsed}s)$cReset   "
        Start-Sleep -Milliseconds 250

        # Timeout di sicurezza a 120 secondi
        if ($elapsed -gt 120) {
            Write-Host "`n`n  $cRed✖ Timeout durante l'avvio del motore Docker.$cReset"
            Write-Host "  $cGrayVerifica che Docker Desktop sia autorizzato e funzionante.$cReset"
            Write-Host -NoNewline "`n  Premi INVIO per uscire..."
            $null = Read-Host
            exit 1
        }
    }
    Write-Host "`r  $cGreen✔$cReset $cBold$cGreen Motore Docker attivo e pronto!$cReset                     "
} else {
    Write-Host "  $cGreen✔$cReset $cGreen Docker Desktop e' gia' in esecuzione e pronto.$cReset"
}
Write-Host ""

# 3. Controllo aggiornamenti (git pull)
Write-Host "  $cCyan⚡ Verifica aggiornamenti del codice (git pull)...$cReset"
try {
    & git pull 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  $cGreen✔$cReset $cGray Codice sincronizzato con GitHub.$cReset"
    } else {
        Write-Host "  $cYellow[!]$cReset $cGray Git pull non riuscito o modifiche locali presenti; continuo con i file attuali.$cReset"
    }
} catch {
    Write-Host "  $cYellow[!]$cReset $cGray Connessione non disponibile; continuo con la versione locale.$cReset"
}
Write-Host ""

# 4. Avvio container FilmViewer
Write-Host "  $cNeon🚀 Avvio e compilazione del container FilmViewer...$cReset"
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  $cRed✖ ERRORE durante l'avvio del container FilmViewer.$cReset"
    Write-Host "  $cGrayVerifica i messaggi di errore qui sopra.$cReset"
    Write-Host ""
    Write-Host -NoNewline "  Premi INVIO per uscire..."
    $null = Read-Host
    exit 1
}

Write-Host "  $cGreen✔$cReset $cBold$cGreen Container avviato con successo!$cReset"
Write-Host ""

# 5. Apertura browser automatico
Write-Host "  $cCyan🌐 Apertura automatica nel browser (http://localhost:9876)...$cReset"
Start-Sleep -Seconds 2
Start-Process "http://localhost:9876"

# 6. Dashboard a schermo intero durante l'esecuzione
Clear-Host
Write-Host ""
Write-Host "  $cNeon╭─────────────────────────────────────────────────────────────────────────╮$cReset"
Write-Host "  $cNeon│$cReset  $cPurple$cBold  ███████╗██╗██╗     ███╗   ███╗██╗   ██╗██╗███████╗██╗    ██╗      $cReset  $cNeon│$cReset"
Write-Host "  $cNeon│$cReset  $cPurple$cBold  ██╔════╝██║██║     ████╗ ████║██║   ██║██║██╔════╝██║    ██║      $cReset  $cNeon│$cReset"
Write-Host "  $cNeon│$cReset  $cPurple$cBold  █████╗  ██║██║     ██╔████╔██║██║   ██║██║█████╗  ██║ █╗ ██║      $cReset  $cNeon│$cReset"
Write-Host "  $cNeon│$cReset  $cPurple$cBold  ██╔══╝  ██║██║     ██║╚██╔╝██║╚██╗ ██╔╝██║██╔══╝  ██║███╗██║      $cReset  $cNeon│$cReset"
Write-Host "  $cNeon│$cReset  $cPurple$cBold  ██║     ██║███████╗██║ ╚═╝ ██║ ╚████╔╝ ██║███████╗╚███╔███╔╝      $cReset  $cNeon│$cReset"
Write-Host "  $cNeon│$cReset  $cPurple$cBold  ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝  ╚═══╝  ╚═╝╚══════╝ ╚══╝╚══╝       $cReset  $cNeon│$cReset"
Write-Host "  $cNeon│                                                                         │$cReset"
Write-Host "  $cNeon│$cReset             $cGreen$cBold🟢  FILMVIEWER E' ATTIVO E IN ESECUZIONE$cReset                $cNeon│$cReset"
Write-Host "  $cNeon├─────────────────────────────────────────────────────────────────────────┤$cReset"
Write-Host "  $cNeon│                                                                         │$cReset"
Write-Host "  $cNeon│$cReset   🌐  $cBold Indirizzo Web :$cReset $cNeon http://localhost:9876$cReset                              $cNeon│$cReset"
Write-Host "  $cNeon│$cReset   ⚡  $cBold Stato         :$cReset $cGreen Online (Pronto per streaming, JAM e video)$cReset       $cNeon│$cReset"
Write-Host "  $cNeon│$cReset   📁  $cBold Cartella      :$cReset $cGray $projectDir$cReset"
Write-Host "  $cNeon│                                                                         │$cReset"
Write-Host "  $cNeon├─────────────────────────────────────────────────────────────────────────┤$cReset"
Write-Host "  $cNeon│                                                                         │$cReset"
Write-Host "  $cNeon│$cReset   $cYellow$cBold💡 ISTRUZIONI PER LO SPEGNIMENTO:$cReset                                        $cNeon│$cReset"
Write-Host "  $cNeon│$cReset      Quando hai terminato la visione, torna qui dentro e:                 $cNeon│$cReset"
Write-Host "  $cNeon│$cReset      $cBold$cYellow PREMI [ INVIO ]$cReset sulla tastiera per spegnere automaticamente       $cNeon│$cReset"
Write-Host "  $cNeon│$cReset      il container e chiudere Docker, liberando la memoria RAM.           $cNeon│$cReset"
Write-Host "  $cNeon│                                                                         │$cReset"
Write-Host "  $cNeon╰─────────────────────────────────────────────────────────────────────────╯$cReset"
Write-Host ""

# Attesa specifica del solo tasto INVIO
Write-Host -NoNewline "  $cYellow⌨  Premi [ INVIO ] per spegnere FilmViewer e liberare la RAM... $cReset"
try {
    $null = Read-Host
} catch {
    [Console]::ReadLine() | Out-Null
}
Write-Host ""

# 7. Spegnimento ordinato e pulizia risorse
Clear-Host
Write-Host ""
Write-Host "  $cYellow╭─────────────────────────────────────────────────────────────────────────╮$cReset"
Write-Host "  $cYellow│$cReset            $cBold🛑  ARRESTO E RILASCIO COMPLETO MEMORIA RAM$cReset              $cYellow│$cReset"
Write-Host "  $cYellow╰─────────────────────────────────────────────────────────────────────────╯$cReset"
Write-Host ""

Write-Host "  $cCyan • Spegnimento del container FilmViewer in corso...$cReset"
& docker compose down 2>&1 | Out-Null
Write-Host "  $cGreen✔$cReset $cGray Container FilmViewer arrestato e rimosso.$cReset"
Write-Host ""

Write-Host "  $cCyan • Chiusura di Docker Desktop e processi in background...$cReset"
$dockerProcessNames = @("Docker Desktop", "com.docker.backend", "com.docker.proxy", "docker", "com.docker.build", "com.docker.admin")
foreach ($procName in $dockerProcessNames) {
    Stop-Process -Name $procName -Force -ErrorAction SilentlyContinue
}
# Chiusura forzata sicura via taskkill come salvaguardia
taskkill /F /IM "Docker Desktop.exe" /T 2>&1 | Out-Null
taskkill /F /IM "com.docker.backend.exe" /T 2>&1 | Out-Null
taskkill /F /IM "com.docker.proxy.exe" /T 2>&1 | Out-Null
taskkill /F /IM "docker.exe" /T 2>&1 | Out-Null
Write-Host "  $cGreen✔$cReset $cGray Processi di Docker terminati.$cReset"
Write-Host ""

Write-Host "  $cCyan • Rilascio della memoria RAM del sottosistema WSL (vmmem)...$cReset"
& wsl --shutdown 2>&1 | Out-Null
Write-Host "  $cGreen✔$cReset $cBold$cGreen WSL arrestato. Memoria RAM liberata al 100%!$cReset"
Write-Host ""

Write-Host "  $cGreen╔═════════════════════════════════════════════════════════════════════════╗$cReset"
Write-Host "  $cGreen║            ✨  OPERAZIONE COMPLETATA. ARRIVEDERCI!                      ║$cReset"
Write-Host "  $cGreen╚═════════════════════════════════════════════════════════════════════════╝$cReset"
Write-Host ""

Start-Sleep -Seconds 2
exit 0
