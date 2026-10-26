<p align="center">
  <img src="docs/banner.png" alt="FilmViewer Banner" width="680"/>
</p>

<p align="center">
  <b>Un'interfaccia web moderna, veloce e intuitiva per esplorare, guardare e scaricare film e serie TV per uso personale.</b><br/>
  Watch Party JAM sincronizzato in tempo reale, streaming player HLS integrato, catalogo dinamico con raccomandazioni personalizzate, auto-recovery intelligente del dominio, motore di download ad alte prestazioni con pausa/ripresa/cancellazione pulita, I miei Preferiti con Mi piace (❤️) e gestione multi-utenza con ruoli e richieste.
</p>

<p align="center">
  <a href="#-guida-allinstallazione"><img src="https://img.shields.io/badge/Installazione-CasaOS_%7C_Windows_%7C_macOS_%7C_Linux-brightgreen?style=flat-square" alt="Install"/></a>
  <a href="#-funzionalità-principali"><img src="https://img.shields.io/badge/Funzionalità-JAM_Watch_Party_%2B_Streaming_%2B_Download_%2B_AutoDomain_%2B_MultiUser-orange?style=flat-square" alt="Features"/></a>
  <a href="#-crediti-e-disclaimer"><img src="https://img.shields.io/badge/Licenza-MIT_%7C_Non--Commercial-blue?style=flat-square" alt="License"/></a>
</p>

---

## 📌 Panoramica

FilmViewer è un'applicazione web moderna concepita per la fruizione domestica e privata tra amici e familiari. Combina l'esperienza d'uso di un catalogo in stile Netflix con un player streaming HLS ad alta risoluzione, la sincronizzazione **JAM Watch Party** per guardare contenuti assieme a distanza, un avanzato motore di download parallelo e un sistema di auto-aggiornamento intelligente che previene qualsiasi interruzione dovuta ai cambi di dominio della sorgente.

<p align="center">
  <img src="docs/home.png" alt="Schermata Principale" width="88%"/>
</p>

---

## ✨ Funzionalità Principali

### 🍿 JAM (Watch Party Sincronizzata in Tempo Reale)
- **Accesso Diretto dalla Barra Laterale (`#/jam`):** Ora accessibile direttamente dalla navigazione laterale per tutti gli utenti (sia amministratori sia utenti base). Ogni utente può creare o gestire le proprie stanze in totale autonomia.
- **Guarda Insieme a Distanza:** Crea una stanza istantanea o unisciti a una sessione con codice a 6 caratteri o tramite link diretto di invito copiabile con un clic.
- **Sincronizzazione Totale di Play, Pausa e Salto Temporale:** Quando un partecipante mette in pausa, riprende o salta in un punto del film, tutti i dispositivi connessi si sincronizzano all'istante con compensazione automatica della latenza.
- **Proposta di Visione Condivisa (Watch Party):**
  - Quando sei all'interno di una JAM e avvii la riproduzione di un titolo, compare a tutti i partecipanti un pop-up con la proposta di visione (*"TIZIO ha avviato la riproduzione di... Unisciti / Rifiuta"*).
  - La riproduzione rimane in attesa finché gli altri rispondono o finché il conduttore non decide di avviare subito.
  - Overlay informativo sullo stato di preparazione dei partecipanti (*In attesa*, *Pronto*).
- **Conto alla Rovescia Sincronizzato (3... 2... 1... VIA!):** Non appena tutti i partecipanti hanno preparato il flusso, scatta un countdown animato a schermo intero sincronizzato al millisecondo, facendo partire la visione esattamente nello stesso istante per tutti.
- **Chat e Presenza Live:** Pannello laterale per chattare durante la visione, contatore partecipanti con avatar, indicatore di stato della connessione MQTT/WebSocket sicura e auto-riconnessione silenziosa.

---

### 🚀 Motore ad Alte Prestazioni & Zero Latenza (Ultra-Fast)
- **Image Proxy con Cache su Disco Locale:** Tutte le locandine e i poster scaricati vengono memorizzati in una cache locale su disco (`tmp/img_cache`). Le visite successive servono le immagini in **<1ms** a costo di rete zero.
- **Worker Pool Dedicato (Anti-Starvation):** Le richieste grafiche operano su un `ThreadPoolExecutor` isolato (`img-proxy`), impedendo alla coda delle immagini di saturare il thread pool di FastAPI: ricerche, avvio streaming e caricamento pagine rimangono sempre istantanei.
- **Avvio Streaming HLS Accelerato:** Risoluzione ultra-rapida dell'embed video (<1 secondo) e prefetch in background asincrono della chiave di decifrazione AES-128: la riproduzione inizia all'istante senza attese.
- **Home Shelves Ottimizzate:** Caricamento snello e fulmineo dei caroselli principali (Di tendenza, Nuove uscite, Top 10, Film e Serie popolari) con caching intelligente condiviso.
- **Connection Pooling Globale:** Connessioni HTTP riutilizzabili con keep-alive e fail-fast intelligente su timeout DNS/TLS.

---

### 🌐 Auto-Recovery e Rotazione Intelligente del Dominio
- **Monitoraggio e Ricerca Automatica:** Le piattaforme sorgente cambiano periodicamente dominio. FilmViewer interroga in background i canali ufficiali e rileva istantaneamente il nuovo indirizzo.
- **Auto-Recovery in Streaming:** Se durante la riproduzione o la preparazione dello streaming si verifica un errore di connessione (`Connection Refused`), FilmViewer attiva istantaneamente il controllo del dominio e tenta automaticamente il ripristino del flusso senza bloccare l'utente.
- **Triplo Filtro di Sicurezza:**
  1. *Filtro del Nome:* Accetta esclusivamente domini conformi alla struttura ufficiale (`streaming(community|unity)...`).
  2. *Anti-SSRF su IP Pubblici:* Risolve il DNS e rifiuta rigorosamente IP locali, loopback (localhost) o reti private.
  3. *Verifica Runtime della Firma:* Interroga il server e verifica che risponda con la versione e l'architettura autentica prima di prenderlo in considerazione.
- **Due Modalità di Applicazione:**
  - *Con Notifica e Banner (Default):* Propone il nuovo dominio con un banner in cima all'interfaccia; basta un clic su **"Applica"** per confermarlo.
  - *Zero-Click (`domain_auto_apply`):* Se abilitato nelle Impostazioni, FilmViewer aggiorna il dominio da solo non appena quello vecchio scade, svuotando all'istante le cache DNS, immagini e catalogo senza interruzioni.
- **Trigger Reattivo & Pulsante "Controlla ora":** Il controllo scatta automaticamente se una richiesta fallisce (con protezione anti-stampede di 10 minuti) oppure manualmente su richiesta dell'amministratore.

---

### ⚡ Engine di Download Ultra-Rapido & Gestione Coda
- **Download Multi-Thread con AdaptiveLimiter:** Algoritmo intelligente a scaricamento parallelo che massimizza la velocità di download e previene blocchi o ban temporanei da parte del CDN.
- **Pausa, Ripresa e Cancellazione Istantanea:**
  - **Pausa / Resume:** Metti in pausa qualsiasi download e riprendilo in un secondo momento riscaricando unicamente i segmenti mancanti.
  - **Cancellazione Pulita:** Cliccando sulla **X** durante il download o mentre è in pausa, il worker viene terminato all'istante, la memoria RAM viene disallocata, i file temporanei vengono cancellati dal disco e la lista si aggiorna immediatamente in tempo reale senza errori.
- **Multi-Traccia Audio & Sottotitoli:** Possibilità di selezionare la lingua audio desiderata e scaricare i sottotitoli incorporati nel contenitore video (.mkv/.mp4) o come file `.vtt` separati.
- **Muxing con FFmpeg & Naming Personalizzato:** Assemblaggio continuo con FFmpeg e template di rinomina dei file personalizzabili (compatibili al 100% con Plex, Jellyfin ed Emby).

---

### ❤️ I miei Preferiti ("Mi piace")
- **Salva Film e Serie TV con un Clic:** Cliccando sul pulsante a forma di cuore ❤️ su qualsiasi film o serie TV, il titolo viene aggiunto all'istante alla tua lista personale dei preferiti per ricordarti di guardarlo.
- **Sezione Dedicata con Filtri:** Visualizza tutti i tuoi titoli salvati in una griglia elegante con filtri rapidi per categoria (*Tutti*, *Film*, *Serie TV*) e badge informativi.
- **Avvio Immediato & Gestione Rapida:** Avvia direttamente la riproduzione in streaming con il tasto rapido **"Guarda"**, apri la scheda di dettaglio o rimuovilo in qualunque momento con un altro clic sul cuore.
- **Supporto Multi-Profilo & Ospite:** Ogni utente ha la propria lista di preferiti, accessibile e sincronizzata sia per gli account registrati sia in modalità aperta.

---

### 🎬 Catalogo Dinamico & Raccomandazioni Intelligenti
- **Home Page Sempre Nuova:** Classifiche aggiornate (Top 10 settimanale e mensile) e caroselli a rotazione che pescano continuamente dal catalogo per non mostrare mai una pagina statica.
- **"Perché hai guardato...":** Algoritmo di raccomandazione personalizzato basato sulla reale cronologia di visione dell'utente.
- **Navigazione a Zero Latenza (Stale-While-Revalidate):** I dati del catalogo e le locandine vengono pre-risolti e serviti con latenza percepita di 0 ms.

---

### ▶️ Web Player HLS Integrato & "Continua a Guardare"
- **Streaming Diretto nel Browser:** Guarda film e serie TV con un click senza dover attendere il completamento del download.
- **Controlli Nativi & Puliti:** Player ottimizzato senza overlay invasivi; riproduzione e pausa native immediate tramite tasto e barra spaziatrice.
- **Risoluzione Automatica per Serie TV:** Seleziona in automatico l'ultimo episodio guardato o avvia il primo episodio di default, con passaggio fluido all'episodio successivo.
- **Selettore Risoluzione & Audio:** Scelta rapida della risoluzione (Auto, 1080p, 720p, 480p) e della traccia audio.
- **Scorciatoie da Tastiera:**
  - `Spazio`: Play / Pausa.
  - `Freccia Destra` / `Freccia Sinistra`: Salto rapido di 10 secondi avanti/indietro.
  - `F`: Modalità a schermo intero reale (HTML5 Fullscreen).
- **Continua a Guardare Persistente:** Progresso salvato automaticamente alla pausa e alla chiusura (senza spam di polling di rete durante la riproduzione), con visualizzazione immediata in Home Page e pulsanti per riprendere con precisione o ricominciare dall'inizio. Rimozione automatica a visione ultimata (≥95%).

---

### 👥 Multi-Utenza, Ruoli & Sistema di Richieste
- **Profili Protetti:** Autenticazione sicura con hash bcrypt per le password e gestione delle sessioni tramite cookie protetti.
- **Ruoli & Permessi Granulari:**
  - **Amministratore:** Controllo completo delle impostazioni di rete, gestione sorgente, librerie disco, approvazione richieste e gestione utenti.
  - **Utente Base:** Accesso indipendente allo streaming, cronologia personale, download dei propri contenuti e invio di richieste.
- **Flusso Richieste con Notifiche SSE:** Gli utenti possono richiedere titoli non ancora presenti sul server; gli amministratori possono approvare, rifiutare o avviare il download con aggiornamento in tempo reale (badge campanella e notifiche push interne).
- **File Manager Integrato (`#/files`) & Pulizia Automatica:** Sezione dedicata per consultare i file salvati su disco; l'eliminazione di un elemento ripulisce fisicamente i file e le cartelle vuote.

---

### 🎨 Design Moderno & Reattivo (Smart TV, PC & Mobile)
- **Aestetica Premium:** Interfaccia scura raffinata con palette armoniose, trasparenze in stile glassmorphism, badge di stato chiari e micro-animazioni fluide.
- **Card e Locandine Perfettamente Proporzionate:** Dimensioni uniformi e bilanciate in stile cinema/Netflix su tutte le sezioni (Home, Ricerca, Preferiti).
- **Completamente Responsive:** Layout ottimizzato per l'uso da smartphone, tablet, computer e browser per Smart TV. Sui display mobili le card non vengono tagliate sui bordi e garantiscono uno scroll orizzontale tattile perfetto.
- **DNS Cache In-Memory:** Cache interna ad alta velocità che elimina i ritardi di risoluzione DNS tipici dei container Docker su Windows e Linux.

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
    en_us: Modern web interface to stream and download movies and TV series for personal use.
    it_it: Interfaccia web per guardare e scaricare film e serie TV con player HLS integrato, auto-domain e download rapido.
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
6. Apri FilmViewer cliccando sulla sua icona o collegandoti a: 👉 **`http://<IP-DEL-TUO-SERVER>:9876`**

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
Puoi avviare FilmViewer con un semplice doppio clic sullo script **`avvia_filmviewer.bat`**:
- Esegue in automatico `git pull` per verificare nuovi aggiornamenti.
- Avvia Docker Desktop e il container.
- Apre automaticamente FilmViewer nel tuo browser predefinito (`http://localhost:9876`).
- Quando hai finito di guardare il film, premi **INVIO** nel terminale per arrestare i container e chiudere Docker Desktop liberando immediatamente tutta la memoria RAM.

In alternativa, da terminale PowerShell:
```powershell
git clone https://github.com/PitStop13/FilmViewer.git
cd FilmViewer
docker compose up -d --build
```
Apri il browser su: 👉 **`http://localhost:9876`**

#### Opzione 2: Senza Docker (Python)
1. Installa **Python 3.11+** e **FFmpeg** (assicurandoti che `ffmpeg` sia aggiunto al PATH di sistema).
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
   - Alla prima apertura dell'indirizzo `http://localhost:9876` o `http://<IP-SERVER>:9876`, comparirà la procedura guidata per impostare username e password dell'account **Admin**.
2. **Creazione Profili Aggiuntivi:**
   - Dall'account admin, accedi alla sezione **Impostazioni → Utenti** per aggiungere nuovi account con ruolo Amministratore o Utente Base.
3. **Cartella di Download:**
   > ⚠️ **NOTA SUI VOLUMI DOCKER / CASAOS:**  
   > Nel campo del percorso video dell'interfaccia web lascia o inserisci **`/app/videos`** (valore predefinito).  
   > **Non inserire percorsi fisici dell'host come `C:\...` o `/DATA/...`**: il container Docker utilizza `/app/videos` come mount point interno collegato alla tua cartella reale.

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
