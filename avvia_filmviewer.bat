@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title FilmViewer - Avvio e Gestione

:: Spostati nella cartella del progetto (C:\Film se esiste, altrimenti la cartella dello script)
if exist "C:\Film" (
    cd /d "C:\Film"
) else (
    cd /d "%~dp0"
)

echo =======================================================================
echo                     AVVIO DI FILMVIEWER
echo =======================================================================
echo  Cartella di lavoro: %CD%
echo.

:: 1. Verifica se Docker Desktop e' in esecuzione
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Docker Desktop non risulta avviato.
    echo [*] Avvio automatico di Docker Desktop in corso...
    if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
        start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    ) else (
        echo [!] Percorso di Docker Desktop non trovato in Program Files.
        echo     Per favore avvia Docker Desktop manualmente e premi un tasto.
        pause
    )
    echo [*] In attesa che il motore Docker sia pronto...
    :wait_docker
    timeout /t 3 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 (
        goto wait_docker
    )
    echo [OK] Docker Desktop e' ora attivo e pronto!
    echo.
)

:: 2. Controllo aggiornamenti dal repository GitHub
echo [*] Verifica aggiornamenti del codice (git pull)...
git pull
echo.

:: 3. Avvio / build del container FilmViewer
echo [*] Avvio del container FilmViewer...
docker compose up -d --build
if %errorlevel% neq 0 (
    echo.
    echo [ERRORE] Impossibile avviare il container FilmViewer.
    echo Assicurati che Docker Desktop sia completamente avviato.
    pause
    exit /b 1
)

echo [OK] Container avviato con successo!
echo.

:: 4. Apertura del browser
echo [*] Apertura dell'interfaccia su http://localhost:9876...
timeout /t 2 /nobreak >nul
start http://localhost:9876

:: 5. Schermata di attesa
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

:: 6. Chiusura del container e di Docker per liberare risorse
cls
echo =======================================================================
echo                     ARRESTO E PULIZIA RISORSE
echo =======================================================================
echo.
echo [*] Spegnimento del container FilmViewer in corso...
docker compose down
echo [OK] Container arrestato e rimosso con successo.
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
