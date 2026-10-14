# SC Downloader - Web App

Un'applicazione Web completa (Backend + Frontend) progettata per girare esclusivamente all'interno di un container Docker, creata per cercare, visualizzare e scaricare contenuti in streaming (film e serie TV) dalla piattaforma StreamingCommunity.

## 🚀 Caratteristiche Principali

- **Auto-Discovery del Dominio:** Rilevamento automatico del dominio funzionante di StreamingCommunity (nessun bisogno di aggiornare manualmente l'URL quando cambia).
- **Player Integrato ("Guarda Subito"):** Riproduzione diretta dei video tramite un web player HTML5 integrato (HLS.js + Plyr).
- **Download Avanzato:** Supporto per il download di specifiche qualità video (1080p, 720p, 480p, ecc.) estratte direttamente dalle playlist M3U8 originali.
- **Formati Muxing Personalizzati:** Possibilità di esportare i download nei formati MP4, MKV o AVI usando FFmpeg (che opera senza re-encoding, mantenendo la qualità originale).
- **Gestore di Coda (Queue Manager):** Un pannello WebSocket in tempo reale per monitorare il download (Avanzamento, Velocità, ETA) con funzioni di Pausa, Ripresa e Annullamento.
- **Interfaccia Web Responsiva:** Ottimizzata per PC, tablet e smartphone con TailwindCSS.
- **Porta Dedicata:** Esposta di default sulla porta `9876`.

## 🛠️ Tecnologie Utilizzate

- **Backend:** Python 3.11, FastAPI, Uvicorn, WebSockets, BeautifulSoup4, FFmpeg.
- **Frontend:** HTML5, JS Vanilla, TailwindCSS, HLS.js, Plyr.
- **Infrastruttura:** Docker, Docker Compose.

---

## 💻 Come testarlo in locale (Linux, macOS, Windows)

Assicurati di aver installato **Docker** e **Docker Compose** sul tuo computer.

1. **Clona questo repository:**
   ```bash
   git clone https://github.com/tuo-utente/sc-downloader-app.git
   cd sc-downloader-app
   ```

2. **Avvia il container:**
   ```bash
   docker compose up -d --build
   ```

3. **Accedi all'interfaccia web:**
   Apri il browser all'indirizzo: `http://localhost:9876`

4. **Cartelle generate:**
   I file scaricati finiranno all'interno della cartella `./downloads` che verrà creata automaticamente nella directory del progetto, assieme alla cartella `./config`.

---

## 🏠 Installazione su CasaOS

Poiché CasaOS gestisce ottimamente i file `docker-compose.yml`, ci sono due approcci.

### Metodo CLI (Consigliato per versioni non ancora su Docker Hub)

Il modo più rapido per installarlo in CasaOS senza aver caricato l'immagine su Docker Hub è compilarlo localmente tramite SSH.

1. Accedi via **SSH** al tuo server CasaOS.
2. Crea una cartella per l'app e scarica i file:
   ```bash
   mkdir -p /DATA/AppData/sc-downloader
   cd /DATA/AppData/sc-downloader
   # (Trasferisci o clona qui i file di questo repository)
   ```
3. Imposta i permessi per le cartelle dei volumi:
   ```bash
   mkdir -p downloads config
   chmod 777 downloads config
   ```
4. Fai la build e lancia il container:
   ```bash
   docker compose up -d --build
   ```
5. **Fatto!** L'app comparirà nella dashboard di CasaOS. Puoi accedervi all'indirizzo `http://<IP_DI_CASAOS>:9876`.

### Metodo via Interfaccia Web CasaOS (Richiede immagine pubblicata)

Se un giorno decidi di fare il push di questa immagine su Docker Hub (es. `tuo-utente/sc-downloader:latest`), potrai installarlo direttamente dalla Web UI di CasaOS:

1. Dalla dashboard, clicca sul pulsante **"+"** per installare una nuova app.
2. Scegli **Custom Install**.
3. Clicca sull'icona per importare da **Docker Compose** (in alto a destra).
4. Incolla questo `docker-compose.yml`:

```yaml
version: '3.8'
services:
  web:
    image: tuo-utente/sc-downloader:latest  # <- Cambia questo con la tua immagine Docker Hub
    ports:
      - "9876:9876"
    volumes:
      - /DATA/AppData/sc-downloader/downloads:/app/downloads
      - /DATA/AppData/sc-downloader/config:/app/config
    environment:
      - PORT=9876
    restart: unless-stopped
```

## 📜 Licenza
Questo progetto è stato creato a scopo educativo. Si declina ogni responsabilità per l'uso improprio.
