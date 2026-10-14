<p align="center">
  <img src="docs/banner.png" alt="StreamingCommunity Downloader & FilmViewer" width="720"/>
</p>

<p align="center">
  <b>Un pannello web self-hosted premium per esplorare, guardare in streaming e scaricare film e serie TV direttamente nella tua libreria multimediale Jellyfin.</b><br/>
  Catalogo ricco suddiviso in Film e Serie TV, player streaming integrato fino a 1080p, ripresa automatica dei download (resume), coda richieste stile Overseerr, monitoraggio nuove uscite e file manager integrato.
</p>

<p align="center">
  <a href="#-guida-allinstallazione"><img src="https://img.shields.io/badge/Installazione-Facile_e_Guidata-brightgreen?style=flat-square" alt="Install"/></a>
  <a href="#-casaos-home-server--nas"><img src="https://img.shields.io/badge/CasaOS-Supportato-blue?style=flat-square" alt="CasaOS"/></a>
  <a href="#-windows-10--11"><img src="https://img.shields.io/badge/Windows-Docker_%7C_Python-0078D6?style=flat-square" alt="Windows"/></a>
  <a href="#-macos-apple-silicon--intel"><img src="https://img.shields.io/badge/macOS-Apple_Silicon_%7C_Intel-white?style=flat-square" alt="macOS"/></a>
</p>

---

## 📸 Anteprime

<p align="center">
  <img src="docs/home.png" alt="Pagina iniziale" width="90%"/>
</p>
<p align="center">
  <sub><b>Home Page Completa</b> — Catalogo ricco con oltre 250 titoli suddivisi tra Film e Serie TV, con filtri rapidi, locandine in alta qualità e navigazione ultra-fluida.</sub>
</p>

### Catalogo & Dettagli Titolo

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/search.png" alt="Risultati di ricerca"/><br/>
      <sub><b>Catalogo e Ricerca Istantanea</b> — Ricerca veloce di film e serie TV con badge di stato in libreria visibili direttamente sulla scheda.</sub>
    </td>
    <td width="50%" valign="top">
      <img src="docs/film-detail.png" alt="Scheda film"/><br/>
      <sub><b>Scheda Titolo Dettagliata</b> — Trama, generi, anno, valutazione e trailer estratti direttamente dalla sorgente, senza bisogno di API key esterne (TMDB).</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/serie-detail.png" alt="Scheda serie"/><br/>
      <sub><b>Gestione Stagioni ed Episodi</b> — Selezione comoda di stagioni e puntate con verifica in tempo reale delle tracce audio (italiano, lingua originale) e dei sottotitoli.</sub>
    </td>
    <td width="50%" valign="top">
      <img src="docs/downloads.png" alt="Download in corso"/><br/>
      <sub><b>Gestione Download & Resume</b> — Monitoraggio in tempo reale (download video → audio → unione FFmpeg) con opzione di pausa e ripresa senza perdere segmenti già scaricati.</sub>
    </td>
  </tr>
</table>

### Coda Richieste & Monitoraggio

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/request.png" alt="Le mie richieste"/><br/>
      <sub><b>Portale Richieste</b> — Gli utenti di casa possono richiedere film o serie TV, che vengono inseriti nella coda di approvazione per l'amministratore.</sub>
    </td>
    <td width="50%" valign="top">
      <img src="docs/request-approval.png" alt="Approvazione richieste"/><br/>
      <sub><b>Approvazione Amministratore</b> — L'approvazione verifica e seleziona le tracce audio richieste prima di avviare il download automatico.</sub>
    </td>
  </tr>
  <tr>
    <td colspan="2" align="center" valign="top">
      <img src="docs/series-follow.png" alt="Serie seguite" width="60%"/><br/>
      <sub><b>Serie Seguite (Watchlist)</b> — Il sistema cerca automaticamente nuove puntate in background. Quando esce un nuovo episodio, lo scarica direttamente nella libreria.</sub>
    </td>
  </tr>
</table>

### Gestione & Sistema

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/settings.png" alt="Impostazioni"/><br/>
      <sub><b>Impostazioni Avanzate</b> — Gestione cartelle della libreria multimediale, formati di esportazione (MKV/MP4), template per i nomi dei file e notifiche.</sub>
    </td>
    <td width="50%" valign="top">
      <img src="docs/jellyfin-users.png" alt="Utenti Jellyfin"/><br/>
      <sub><b>Integrazione Utenti Jellyfin</b> — Accesso tramite Jellyfin SSO con gestione granulare dei permessi (richiesta, download, impostazioni).</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/file-manager.png" alt="File manager"/><br/>
      <sub><b>File Manager Integrato</b> — Esplora i file scaricati sul disco, visualizza lo spazio residuo del volume, sposta o elimina elementi direttamente dal browser.</sub>
    </td>
    <td width="50%" valign="top">
      <img src="docs/login.png" alt="Login"/><br/>
      <sub><b>Accesso Flessibile</b> — Accesso tramite Jellyfin oppure modalità aperta ("Continua senza Jellyfin") impostabile con un click al primo avvio.</sub>
    </td>
  </tr>
</table>

---

## ⚡ Caratteristiche Principali

- **Home Page Ricca & Suddivisa (Stile StreamingCommunity):**
  - Oltre **250 titoli** sempre aggiornati direttamente dalla piattaforma.
  - Suddivisione chiara e dedicata:
    - **Sezioni Generali:** *🔥 Di tendenza*, *✨ Aggiunti di recente*, *🏆 Top 10 di oggi*.
    - **Sezioni Film:** *🎬 Film del momento e più visti*, *✨ Nuove uscite Film*, *⭐ I Film più votati*.
    - **Sezioni Serie TV:** *📺 Serie TV più viste*, *✨ Nuove serie TV*, *⭐ Le Serie TV più votate*.
  - **Filtri rapidi per categoria** in cima alla pagina: `[ Tutti i titoli ]`, `[ 🎬 Film ]`, `[ 📺 Serie TV ]` per filtrare all'istante l'intero catalogo.
  - Navigazione ultra-fluida accelerata via GPU a 60/120 fps, con supporto a scorrimento tramite frecce e trascinamento col mouse (Drag & Scroll).
- **Streaming Diretto ("Guarda Subito"):**
  - Riproduzione immediata in-browser di film ed episodi tramite popup Web Player con streaming HLS ad alta risoluzione (fino a 1080p).
  - Tasto dedicato per aprire la scheda ufficiale del titolo su StreamingCommunity.
- **Ripresa dei Download (Resume):**
  - Se interrompi o metti in pausa un download, o se salta la connessione internet, i segmenti `.ts` già scaricati rimangono salvati nella cartella temporanea.
  - Cliccando su **Riprendi** o **Riprova falliti**, il download riparte all'istante dal punto esatto in cui era arrivato, senza riscaricare i dati già ottenuti.
- **Auto-Discovery e Domain Recovery:**
  - Sistema intelligente anti-blocco che rileva autonomamente se il dominio di StreamingCommunity cambia, individuando l'indirizzo funzionante da fonti verificate e aggiornandolo senza interruzioni.
- **Motore di Download HLS / M3U8:**
  - Parsing automatico dei flussi HLS e download multi-thread accelerato.
  - Decifratura integrata al volo per stream protetti da crittografia **AES-128-CBC**.
  - Unione ed esportazione ultra-rapida tramite **FFmpeg** in formato `.mkv` (o `.mp4`) senza ricodifica video (qualità nativa al 100%).
  - Download selettivo delle tracce audio (italiano, originale) e dei sottotitoli.
- **Integrazione Jellyfin & Setup Guidato:**
  - **Wizard iniziale:** Al primo avvio scegli la cartella di download e decidi se collegare il tuo Jellyfin per l'accesso SSO oppure usare la modalità aperta senza password.
  - **Organizzazione cartelle automatica:** I file vengono rinominati e ordinati automaticamente secondo gli standard di Jellyfin (`Film (Anno)/Film (Anno).mkv`, `Serie TV/Season 01/Serie S01E01.mkv`).
  - Scansione automatica della libreria Jellyfin via webhook al termine di ogni download.
- **Prestazioni Elevate & Caching Intelligente:**
  - **Proxy Immagini ultra-veloce:** Caching in RAM delle locandine con intestazioni HTTP `Cache-Control` (7 giorni) per il caching lato browser; le locandine già caricate si aprono a 0ms senza intasare la banda né i thread del server.
  - **Ricerca e Catalogo Accelerati:** Cache in memoria a breve termine per ricerche e navigazione archivio con pooling delle connessioni HTTP e socket keep-alive riutilizzati.
  - **Apertura Istantanea dei Titoli:** Risoluzione diretta del player StreamingCommunity prioritizzando i percorsi corretti ed eliminando tentativi a vuoto su endpoint 404, con cache delle tracce audio e sottotitoli per navigare tra schede e puntate in una frazione di secondo.

---

## 🚀 Guida all'Installazione

Scegli la modalità adatta al tuo sistema operativo o al tuo server domestico:

---

### 🏠 CasaOS (Home Server / NAS)

CasaOS è una delle piattaforme più comode per eseguire FilmViewer tramite Docker.

#### Metodo 1: Da Terminale CasaOS / SSH (Consigliato, 2 minuti)
1. Accedi al terminale di CasaOS (oppure via SSH con un programma come PuTTY o Terminale).
2. Posizionati nella cartella delle tue applicazioni ed esegui il clone:
   ```bash
   cd /DATA/AppData
   git clone https://github.com/PitStop13/FilmViewer.git
   cd FilmViewer
   ```
3. Avvia il container:
   ```bash
   docker compose up -d --build
   ```
4. **Fatto!** L'applicazione apparirà automaticamente o sarà raggiungibile all'indirizzo del tuo server sulla porta `9876`:
   👉 **`http://<IP-DEL-TUO-SERVER>:9876`** (es. `http://192.168.1.100:9876`).

#### Metodo 2: Dall'Interfaccia Web di CasaOS (App Personalizzata)
1. Nella schermata principale di CasaOS, clicca sul pulsante **"+"** in alto a destra e seleziona **"Installa applicazione personalizzata"**.
2. Clicca sul pulsante **"Importa"** in alto a destra (icona del file di testo).
3. Incolla il seguente codice di configurazione:
   ```yaml
   name: filmviewer
   services:
     web:
       image: filmviewer-web:latest
       build: https://github.com/PitStop13/FilmViewer.git#feature/sc-downloader-app-279818825438426161
       container_name: filmviewer-panel
       ports:
         - "9876:9876"
       volumes:
         - /DATA/Media/FilmViewer/videos:/app/videos
         - /DATA/AppData/FilmViewer/config:/app/config
       environment:
         - HOST=0.0.0.0
         - PORT=9876
         - VIDEOS_DIR=/app/videos
         - DB_FILE=/app/config/panel.db
         - DATA_FILE=/app/config/data.json
         - SCHEDULE_FILE=/app/config/schedule.json
         - COOKIE_SECURE=0
         - COOKIE_SAMESITE=lax
         - TRUST_PROXY_HEADERS=0
       restart: unless-stopped
   ```
4. Controlla che le cartelle sull'host (`/DATA/Media/FilmViewer/videos` e `/DATA/AppData/FilmViewer/config`) esistano, poi clicca **"Installa"**.
5. Al termine dell'installazione, clicca sull'icona dell'applicazione per aprirla.

---

### 🪟 Windows (10 / 11)

#### Metodo A: Con Docker Desktop (Consigliato)
1. **Scarica e installa Docker Desktop**:
   Se non lo hai già, scarica [Docker Desktop per Windows](https://www.docker.com/products/docker-desktop/) (assicurati di attivare l'estensione WSL2 durante l'installazione).
2. **Scarica il progetto**:
   Apri **PowerShell** o **Terminale di Windows** e clona la repository:
   ```powershell
   git clone https://github.com/PitStop13/FilmViewer.git
   cd FilmViewer
   ```
   *(In alternativa puoi scaricare il file ZIP da GitHub ed estrarlo in una cartella a tuo piacimento)*.
3. **Avvia il programma**:
   All'interno della cartella del progetto, avvia il container con:
   ```powershell
   docker compose up -d --build
   ```
4. **Apri il browser**:
   Collegati all'indirizzo: 👉 **`http://localhost:9876`**
   I video scaricati verranno salvati automaticamente nella cartella `videos` all'interno della cartella del progetto!

#### Metodo B: Senza Docker (Python Nativo)
Se preferisci non usare Docker:
1. Installa **Python 3.11** o superiore da [python.org](https://www.python.org/) (ricordati di selezionare la spunta **"Add python.exe to PATH"** durante l'installazione).
2. Installa **FFmpeg** (o lascia che l'applicazione utilizzi il modulo di fallback automatico).
3. Apri PowerShell nella cartella del progetto ed esegui:
   ```powershell
   pip install -r requirements.txt
   python main.py
   ```
4. Apri il browser su: 👉 **`http://localhost:9876`**.

---

### 🍏 macOS (Apple Silicon M1/M2/M3/M4 & Intel)

#### Metodo A: Con Docker Desktop per Mac (Consigliato)
1. Installa [Docker Desktop per Mac](https://www.docker.com/products/docker-desktop/) (scegli la versione per processori *Apple Silicon* o *Intel* in base al tuo Mac).
2. Apri il **Terminale** e clona la repository:
   ```bash
   git clone https://github.com/PitStop13/FilmViewer.git
   cd FilmViewer
   ```
3. Avvia il container:
   ```bash
   docker compose up -d --build
   ```
4. Apri Safari o Chrome su: 👉 **`http://localhost:9876`**.

#### Metodo B: Senza Docker (Nativo con Homebrew)
1. Se hai [Homebrew](https://brew.sh/), apri il Terminale e installa Python e FFmpeg:
   ```bash
   brew install python ffmpeg git
   ```
2. Clona ed esegui:
   ```bash
   git clone https://github.com/PitStop13/FilmViewer.git
   cd FilmViewer
   pip3 install -r requirements.txt
   python3 main.py
   ```
3. Apri il browser su: 👉 **`http://localhost:9876`**.

---

## 🎯 Configurazione al Primo Avvio (Wizard)

La prima volta che apri **`http://localhost:9876`**, vedrai il menu di benvenuto:

1. **Cartella di salvataggio**: specifica la cartella in cui scaricare i contenuti (in Docker lascia `/app/videos`).
2. **Accesso**:
   - **Opzione con Jellyfin:** inserisci l'indirizzo del tuo server Jellyfin (es. `http://192.168.1.10:8096`) e le credenziali di un utente amministratore. Il pannello collegherà il tuo account in modo sicuro.
   - **Opzione senza Jellyfin:** clicca sul pulsante **"Continua senza Jellyfin"** per usare immediatamente l'applicazione in modalità libera, senza bisogno di configurare alcun server media.

---

## ⚙️ Variabili d'Ambiente

Se desideri personalizzare le impostazioni avanzate tramite `docker-compose.yml` o file `.env`:

| Variabile | Default | Descrizione |
|---|---|---|
| `HOST` | `0.0.0.0` | Indirizzo di ascolto del server (in Docker lasciare `0.0.0.0`). |
| `PORT` | `9876` | Porta web del pannello (default `9876`). |
| `VIDEOS_DIR` | `/app/videos` | Percorso interno in cui salvare i filmati scaricati. |
| `DB_FILE` | `/app/config/panel.db` | Percorso database SQLite per utenti, impostazioni e richieste. |
| `DATA_FILE` | `/app/config/data.json` | Percorso del file JSON di configurazione runtime. |
| `SCHEDULE_FILE` | `/app/config/schedule.json`| Registro delle serie seguite e download pianificati. |
| `COOKIE_SECURE` | `0` | Impostare a `1` solo se il sito è protetto da un certificato HTTPS/SSL. |
| `COOKIE_SAMESITE`| `lax` | Regola cookie di sessione (`lax`, `strict`, `none`). |
| `TRUST_PROXY_HEADERS` | `0` | Impostare a `1` se si utilizza un Reverse Proxy (es. Nginx, Cloudflare, Traefik). |
| `FFMPEG_PATH` | *(auto)* | Percorso binario personalizzato di FFmpeg (se non nel PATH). |

---

## 📁 Struttura Cartelle di Output (Standard Jellyfin / Plex)

I contenuti vengono salvati e nominati in modo ordinato e pulito:

```
videos/
├── Film (2024)/
│   ├── Film (2024).mkv
│   └── Film (2024).it.vtt          # Sottotitoli (se scaricati)
└── Nome Serie (2023)/
    └── Season 01/
        ├── Nome Serie S01E01.mkv
        └── Nome Serie S01E02.mkv
```

Puoi personalizzare la struttura dei nomi dei file in qualsiasi momento da **Impostazioni → Nomi**.

---

## ⏯️ Come Funziona la Ripresa dei Download (Resume)

1. **Pausa o Stop:** se durante un download clicchi sull'icona di arresto (quadrato rosso) o la connessione salta, il download si arresta ma i segmenti video già scaricati rimangono preservati nella cartella temporanea locale.
2. **Ripresa immediata:** cliccando su **Riprendi** (icona rotonda) o su **Riprova falliti**, il sistema riutilizza automaticamente tutti i segmenti già completati e riprende dal punto esatto dell'interruzione.
3. **Pulizia automatica:** i file temporanei vengono eliminati solo quando il file finale è stato unito e salvato correttamente, o se elimini manualmente la scheda del download (`X`).

---

## 🔒 Sicurezza e Privacy

- **100% Locale e Indipendente:** Nessuna telemetria, nessun tracciamento degli utenti, nessun cookie di terze parti.
- **Protezione Anti-SSRF:** La ricerca di domini alternativi controlla e impedisce connessioni a reti locali o indirizzi IP privati.
- **Consiglio per esposizione pubblica:** Se decidi di esporre la porta su Internet, proteggila con un reverse proxy con HTTPS (Nginx Proxy Manager, Caddy o Cloudflare Zero Trust) e imposta una password o collega Jellyfin.

---

## 📜 Licenza e Disclaimer

### Licenza
Distribuito con licenza **MIT**. Consulta il file `LICENSE` per maggiori informazioni.

### Disclaimer Legale ed Educativo
Questo software è sviluppato ed erogato **esclusivamente a scopo illustrativo, personale ed educativo** per dimostrare l'interazione con stream multimediali HLS/M3U8, algoritmi di decifratura simmetrica AES-CBC, pipeline di elaborazione video tramite FFmpeg e architetture web asincrone in Python con FastAPI.

Il progetto **non memorizza, non ospita e non distribuisce alcun file audiovisivo o materiale protetto da copyright**. Si limita a fungere da client per flussi pubblicamente disponibili sul web. L'utente finale è l'unico responsabile dell'utilizzo dello strumento e del rispetto delle normative vigenti sul diritto d'autore nel proprio Paese.
