@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title FilmViewer - Avvio e Gestione

:: 1. Cerca lo script PowerShell avanzato (avvia_filmviewer.ps1) per la grafica moderna
set "SCRIPT_PS1=%~dp0avvia_filmviewer.ps1"
if not exist "!SCRIPT_PS1!" (
    if exist "C:\Film\FilmViewer\avvia_filmviewer.ps1" (
        set "SCRIPT_PS1=C:\Film\FilmViewer\avvia_filmviewer.ps1"
    ) else if exist "C:\Film\avvia_filmviewer.ps1" (
        set "SCRIPT_PS1=C:\Film\avvia_filmviewer.ps1"
    ) else if exist "%USERPROFILE%\Music\Crack\FilmViewer\avvia_filmviewer.ps1" (
        set "SCRIPT_PS1=%USERPROFILE%\Music\Crack\FilmViewer\avvia_filmviewer.ps1"
    )
)

if exist "!SCRIPT_PS1!" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "!SCRIPT_PS1!"
    exit /b !errorlevel!
)

:: ==============================================================================
:: FALLBACK BATCH (se PowerShell non fosse disponibile)
:: ==============================================================================

:: Cerca cartella del progetto
if exist "%~dp0docker-compose.yml" (
    cd /d "%~dp0"
) else if exist "C:\Film\docker-compose.yml" (
    cd /d "C:\Film"
) else if exist "C:\Film\FilmViewer\docker-compose.yml" (
    cd /d "C:\Film\FilmViewer"
) else (
    cd /d "%~dp0"
)

cls
echo =======================================================================
echo          FILMVIEWER - CENTRO MULTIMEDIALE (AVVIO AUTOMATICO)
echo =======================================================================
echo  Cartella di lavoro: %CD%
echo.

:: Rilevamento automatico di Docker Desktop su tutti i percorsi noti
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Docker Desktop non risulta avviato.
    echo [*] Ricerca e avvio automatico di Docker Desktop in corso...

    set "DOCKER_EXE="
    if exist "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" (
        set "DOCKER_EXE=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
    ) else if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
        set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Docker\Docker\Docker Desktop.exe" (
        set "DOCKER_EXE=%LOCALAPPDATA%\Programs\Docker\Docker\Docker Desktop.exe"
    ) else if exist "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe" (
        set "DOCKER_EXE=%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
    )

    if defined DOCKER_EXE (
        start "" "!DOCKER_EXE!"
    ) else (
        start "" "Docker Desktop" 2>nul
    )

    echo [*] In attesa che il motore Docker sia pronto...
    :wait_docker_loop
    timeout /t 2 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 (
        goto wait_docker_loop
    )
    echo [OK] Docker Desktop e' ora attivo e pronto!
    echo.
)

:: Controllo aggiornamenti git
echo [*] Verifica aggiornamenti del codice (git pull)...
git pull >nul 2>&1
echo [OK] Controllo completato.
echo.

:: Avvio container
echo [*] Avvio del container FilmViewer...
docker compose up -d --build
if %errorlevel% neq 0 (
    echo.
    echo [ERRORE] Impossibile avviare il container FilmViewer.
    pause
    exit /b 1
)

echo [OK] Container avviato con successo!
echo.

:: Apertura browser
echo [*] Apertura dell'interfaccia su http://localhost:9876...
timeout /t 2 /nobreak >nul
start http://localhost:9876

:: Dashboard di esecuzione
cls
echo =======================================================================
echo                     FILMVIEWER E' IN ESECUZIONE
echo =======================================================================
echo.
echo   Indirizzo:  http://localhost:9876
echo   Stato:      ATTIVO (in riproduzione / pronto)
echo.
echo -----------------------------------------------------------------------
echo   Buona visione!
echo.
echo   Quando hai finito di guardare:
echo   PREMI INVIO qui dentro per SPEGNERE automaticamente
echo   il container e chiudere Docker, liberando la memoria RAM.
echo -----------------------------------------------------------------------
echo.
pause >nul

:: Chiusura e rilascio RAM
cls
echo =======================================================================
echo                     ARRESTO E PULIZIA RISORSE
echo =======================================================================
echo.
echo [*] Spegnimento del container FilmViewer in corso...
docker compose down >nul 2>&1
echo [OK] Container arrestato.
echo.

echo [*] Chiusura di Docker Desktop e rilascio memoria RAM (vmmem/WSL)...
taskkill /F /IM "Docker Desktop.exe" /T >nul 2>&1
taskkill /F /IM "com.docker.backend.exe" /T >nul 2>&1
taskkill /F /IM "com.docker.proxy.exe" /T >nul 2>&1
taskkill /F /IM "docker.exe" /T >nul 2>&1
wsl --shutdown >nul 2>&1

echo [OK] Docker chiuso e memoria RAM liberata completamente!
echo.
echo =======================================================================
echo   Operazione completata. Arrivederci!
echo =======================================================================
timeout /t 2 /nobreak >nul
exit /b 0
