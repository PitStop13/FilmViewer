<p align="center">
  <img src="docs/banner.png" alt="FilmViewer Banner" width="680"/>
</p>

<p align="center">
  <b>Un'interfaccia web moderna, veloce e intuitiva per esplorare, guardare e scaricare film e serie TV per uso personale.</b><br/>
  Streaming player HLS integrato, catalogo dinamico con algoritmo di raccomandazione, auto-recovery del dominio, download ultra-rapido con ripresa (resume), "Continua a guardare" per utente e gestione multi-utenza.
</p>

<p align="center">
  <a href="#-guida-allinstallazione"><img src="https://img.shields.io/badge/Installazione-CasaOS_%7C_Windows_%7C_macOS_%7C_Linux-brightgreen?style=flat-square" alt="Install"/></a>
  <a href="#-funzionalità-principali"><img src="https://img.shields.io/badge/Funzionalità-Streaming_%2B_Download_%2B_AutoDomain-orange?style=flat-square" alt="Features"/></a>
  <a href="#-crediti-e-disclaimer"><img src="https://img.shields.io/badge/Licenza-MIT_%7C_Non--Commercial-blue?style=flat-square" alt="License"/></a>
</p>

---

## 📌 Panoramica

FilmViewer è un'applicazione web pensata per la fruizione domestica e privata tra amici e familiari. Combina le funzionalità di un catalogo multimediale in stile Netflix con un player streaming HLS ad alta risoluzione, un potente motore di download e la completa indipendenza dai cambi di dominio delle sorgenti.

<p align="center">
  <img src="docs/home.png" alt="Schermata Principale" width="88%"/>
</p>

---

## ✨ Funzionalità Principali

### 🌐 Auto-Recovery e Rotazione Automatica del Dominio
- **Sempre Funzionante:** Le sorgenti online cambiano periodicamente estensione o indirizzo. FilmViewer integra un sistema di monitoraggio continuo (*Domain Health Check*) che interroga resolver DNS alternativi (Cloudflare, Google, OpenDNS).
- **Aggiornamento a Caldo (`domain_auto_apply`):** Se il dominio attivo non risponde, l'applicazione individua autonomamente il nuovo dominio valido e aggiorna la configurazione all'istante senza bisogno di riavvii o interventi manuali.

### 🎬 Catalogo Dinamico & Algoritmo di Raccomandazione
- **Home Page Viva e Rinnovata:** La schermata principale non è mai statica. Oltre alla Top 10 della settimana e del mese, i cataloghi di film e serie TV si rinnovano regolarmente proponendo titoli variegati dall'archivio.
- **"Perché hai guardato...":** Algoritmo di raccomandazione personalizzato basato sulla reale cronologia di visione dell'utente. Se completi o guardi con interesse un film o una serie, la Home ti suggerirà automaticamente opere correlate e simili.
- **Rendering Istantaneo (Stale-While-Revalidate):** Grazie al caching intelligente e alla pre-risoluzione asincrona, la navigazione nella Home è immediata (0 ms di latenza percepita).

### ▶️ Web Player HLS Integrato
- **Streaming Diretto nel Browser:** Guarda film e serie TV con un click senza dover prima scaricare il file.
- **Risoluzione Automatica Episodi Serie TV:** Per le serie TV, il player riprende automaticamente l'ultimo episodio guardato oppure avvia l'episodio 1 di default.
- **Multi-Qualità & Multi-Traccia Audio:** Selettore dinamico della risoluzione video (Auto, 1080p, 720p, 480p) e cambio al volo della lingua audio (italiano, lingua originale, ecc.).
- **Scorciatoie da Tastiera Avanzate:**
  - `Spazio`: Play / Pausa.
  - `Freccia Destra` / `Freccia Sinistra`: Salto rapido di 10 secondi avanti/indietro.
  - `F`: Schermo intero reale HTML5 Fullscreen.

### ⏱️ Continua a Guardare & Cronologia Personale
- **Sincronizzazione in Tempo Reale:** Posizione di visione salvata ogni 5 secondi nel database SQLite locale, isolata per ciascun utente.
- **Controlli Flessibili:** Dalla Home o dalla scheda del titolo puoi riprendere la visione esattamente dal minuto in cui eri rimasto (con badge del tempo residuo), ricominciare dall'inizio oppure eliminare il contenuto dalla lista.

### ⚡ Engine di Download Ultra-Rapido ad Alta Concorrenza
- **AdaptiveLimiter ad Alte Prestazioni:** Motore multi-thread parallelo con rilevamento della tolleranza del CDN. I timeout di lettura sono ottimizzati per evitare qualsiasi blocco della banda anche in caso di connessioni ballerine.
- **Resume Automatico:** Se un download viene interrotto o la connessione salta, la ripresa riscarica solo i segmenti mancanti senza ripartire da zero.
- **Tracce Audio & Sottotitoli:** Possibilità di selezionare le lingue audio desiderate e scaricare i sottotitoli incorporati nel contenitore video (.mkv/.mp4) o estratti come file `.vtt`.
- **Muxing con FFmpeg:** Unione dei flussi video/audio a livello di pacchetti continui e pulizia automatica dei file temporanei.

### 🚀 DNS Cache In-Memory
- **Zero Latenza di Risoluzione:** Cache interna DNS (`TTL 300s`) che previene le perdite di pacchetti UDP e i tipici timeout di 8 secondi riscontrati negli ambienti containerizzati Docker su Windows e Linux.

### 👥 Multi-utenza & Gestione Richieste
- **Profili Sicuri:** Autenticazione protetta con crittografia bcrypt per password.
- **Ruoli & Permessi:**
  - **Admin:** Pieno controllo su impostazioni, configurazione di rete, gestione utenti e approvazione globale.
  - **Utente Base:** Accesso indipendente allo streaming, catalogo, continua a guardare e gestione autonoma dei propri download.
- **Pulizia Disco Automatica:** L'eliminazione di un film o di una serie dalla sezione richieste rimuove fisicamente i file dal disco rigido e ripulisce le cartelle vuote.

---

## 🚀 Guida all'Installazione

### 🏠 CasaOS (Home Server / NAS)

#### Metodo 1: Dall'interfaccia web di CasaOS (Consigliato)

1. Nella dashboard di CasaOS, clicca sul pulsante **"+"** (in alto a destra nella sezione App) e seleziona **"Installa un'applicazione personalizzata"** (*Install a customized app*).
2. In alto a destra della finestra, clicca sull'icona **"Importa"** (`</>` o icona file).
3. Incolla il seguente codice Docker Compose completo:

```yaml
name: filmviewer
services:
  filmviewer:
    image: ghcr.io/pitstop13/filmviewer:latest
    container_name: filmviewer-panel
    ports:
      - "9876:9876"
    volumes:
      # Cartella sul tuo NAS/Server dove memorizzare i download video
      - /DATA/Storage/nas/Download-Film:/app/videos
      # Cartella per configurazione, database utenti e stato persistente
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
    x-casaos:
      ports:
        - container: "9876"
          description:
            en_us: Porta interfaccia Web FilmViewer
      volumes:
        - container: /app/videos
          description:
            en_us: Cartella video e download
        - container: /app/config
          description:
            en_us: Configurazione e database
x-casaos:
  architectures:
    - amd64
    - arm64
    - arm
  main: filmviewer
  description:
    en_us: Web interface to stream and download movies and TV series for personal use.
    it_it: Interfaccia web per guardare e scaricare film e serie TV con player integrato e resume.
  tagline:
    en_us: Streaming & Downloader
    it_it: Streaming & Downloader
  developer: FilmViewer
  author: PitStop13
  icon: https://raw.githubusercontent.com/PitStop13/FilmViewer/main/docs/logo.png
  thumbnail: https://raw.githubusercontent.com/PitStop13/FilmViewer/main/docs/logo.png
  title:
    en_us: FilmViewer
  index: /
  port_map: "9876"
```

4. Clicca su **"Invia"** (*Submit*). I parametri principali risulteranno già precompilati.
5. Clicca su **"Installa"** e attendi il completamento.
6. Apri FilmViewer cliccando sulla sua icona o su: 👉 **`http://<IP-DEL-TUO-SERVER>:9876`**

#### Metodo 2: Da Terminale (o SSH)
```bash
cd /DATA/AppData
git clone https://github.com/PitStop13/FilmViewer.git
cd FilmViewer
docker compose up -d --build
```

---

### 🪟 Windows (10 / 11)

#### Opzione 1: Con Docker Desktop (Consigliato)
1. Apri **PowerShell** e clona il repository:
   ```powershell
   git clone https://github.com/PitStop13/FilmViewer.git
   cd FilmViewer
   ```
2. Avvia il container:
   ```powershell
   docker compose up -d --build
   ```
3. Apri il browser su: 👉 **`http://localhost:9876`**

#### Opzione 2: Senza Docker (Python)
1. Installa **Python 3.11+** e **FFmpeg** (assicurandoti che `ffmpeg` sia nel PATH di sistema).
2. Nel terminale esegui:
   ```powershell
   pip install -r requirements.txt
   python main.py
   ```
3. Apri il browser su: 👉 **`http://localhost:9876`**

---

### 🍏 macOS (Apple Silicon & Intel)

#### Con Docker Desktop
```bash
git clone https://github.com/PitStop13/FilmViewer.git
cd FilmViewer
docker compose up -d --build
```
Apri il browser su: 👉 **`http://localhost:9876`**

#### Senza Docker (Homebrew)
```bash
brew install python ffmpeg git
git clone https://github.com/PitStop13/FilmViewer.git
cd FilmViewer
pip3 install -r requirements.txt
python3 main.py
```
Apri il browser su: 👉 **`http://localhost:9876`**

---

## 🎯 Configurazione e Primo Accesso

1. **Creazione Account Amministratore:**
   - Alla prima apertura dell'indirizzo `http://localhost:9876` o `http://<IP-SERVER>:9876`, comparirà la schermata di configurazione iniziale per impostare le credenziali dell'account **Admin**.
2. **Creazione Profili Aggiuntivi:**
   - Dall'account admin, vai in **Impostazioni → Utenti** per aggiungere account per amici e parenti (ruolo Amministratore o Utente Base).
3. **Cartella di Download:**
   > ⚠️ **NOTA SUI VOLUMI DOCKER / CASAOS:**  
   > Nel campo del percorso video dell'interfaccia lascia o inserisci **`/app/videos`** (valore di default).  
   > **Non inserire percorsi host come `C:\...` o `/DATA/...`**: il container Docker usa `/app/videos` come mount point interno collegato alla tua cartella reale.

---

## 📜 Crediti e Disclaimer

### Crediti
Questo progetto è basato ed estende il codice di **Edoardo Fiore**, autore del repository open source [StreamingCommunity-downloader](https://github.com/EdoardoFiore/StreamingCommunity-downloader), concesso sotto licenza [MIT](https://github.com/EdoardoFiore/StreamingCommunity-downloader/blob/main/LICENSE).

### Progetto Personale & Senza Fini di Lucro
- Questo software è sviluppato e mantenuto **esclusivamente per uso personale, privato e senza fini di lucro**.
- Non contiene annunci pubblicitari, non offre servizi a pagamento, non vende nulla e non richiede donazioni.

### Disclaimer Legale
Questo programma è un client software concepito a scopo didattico, di studio e di ricerca sui protocolli di streaming multimediale HLS.  
L'applicazione **non memorizza, non ospita, non ritrasmette e non distribuisce alcun file multimediale o materiale protetto da copyright**. Tutte le informazioni e i flussi vengono richiesti direttamente dai server pubblicamente accessibili sul web.  
L'utente finale è l'unico responsabile dell'utilizzo dello strumento e del rispetto delle normative sul diritto d'autore vigenti nel proprio paese.
