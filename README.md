<p align="center">
  <img src="docs/banner.png" alt="FilmViewer Banner" width="680"/>
</p>

<p align="center">
  <b>Un'interfaccia web per esplorare, guardare e scaricare film e serie TV per uso personale.</b><br/>
  Supporta riproduzione diretta in streaming, download con ripresa automatica (resume) e organizzazione per media center (Jellyfin/Plex).
</p>

<p align="center">
  <a href="#-guida-allinstallazione"><img src="https://img.shields.io/badge/Installazione-CasaOS_%7C_Windows_%7C_macOS-brightgreen?style=flat-square" alt="Install"/></a>
  <a href="#-crediti-e-disclaimer"><img src="https://img.shields.io/badge/Licenza-MIT_%7C_Non--Commercial-blue?style=flat-square" alt="License"/></a>
</p>

---

## 📌 Panoramica

FilmViewer è un'applicazione web leggera pensata per uso personale e domestico tra amici. Offre:
- **Catalogo & Ricerca:** Esplorazione rapida di film e serie TV con locandine e schede informative.
- **Web Player Integrato:** Streaming immediato ad alta risoluzione nel browser.
- **Download con Ripresa (Resume):** Download multi-thread con FFmpeg e recupero istantaneo dei segmenti interrotti.
- **Integrazione Jellyfin opzionale:** Modalità libera con un click ("Continua senza Jellyfin") oppure accesso con server Jellyfin.

<p align="center">
  <img src="docs/home.png" alt="Schermata Principale" width="85%"/>
</p>

---

## 🚀 Guida all'Installazione

### 🏠 CasaOS (Home Server / NAS)

Accedi al terminale di CasaOS (oppure via SSH) ed esegui:
```bash
cd /DATA/AppData
git clone https://github.com/PitStop13/FilmViewer.git
cd FilmViewer
docker compose up -d --build
```
L'applicazione sarà raggiungibile su: 👉 **`http://<IP-DEL-TUO-SERVER>:9876`**

---

### 🪟 Windows (10 / 11)

#### Opzione 1: Con Docker Desktop (Consigliato)
1. Apri **PowerShell** o **Terminale** e clona la repo:
   ```powershell
   git clone https://github.com/PitStop13/FilmViewer.git
   cd FilmViewer
   ```
2. Avvia il container:
   ```powershell
   docker compose up -d --build
   ```
3. Apri il browser su: 👉 **`http://localhost:9876`**

#### Opzione 2: Con Python (Senza Docker)
1. Installa **Python 3.11+** e **FFmpeg**.
2. Esegui nel terminale:
   ```powershell
   pip install -r requirements.txt
   python main.py
   ```
3. Apri il browser su: 👉 **`http://localhost:9876`**

---

### 🍏 macOS (Apple Silicon & Intel)

#### Opzione 1: Con Docker Desktop
```bash
git clone https://github.com/PitStop13/FilmViewer.git
cd FilmViewer
docker compose up -d --build
```
Apri il browser su: 👉 **`http://localhost:9876`**

#### Opzione 2: Senza Docker (Homebrew)
```bash
brew install python ffmpeg git
git clone https://github.com/PitStop13/FilmViewer.git
cd FilmViewer
pip3 install -r requirements.txt
python3 main.py
```
Apri il browser su: 👉 **`http://localhost:9876`**

---

## 🎯 Configurazione al Primo Avvio

La prima volta che ti colleghi a **`http://localhost:9876`**:
1. **Cartella video**: conferma il percorso di salvataggio (se usi Docker lascia `/app/videos`).
2. **Accesso**:
   - Clicca **"Continua senza Jellyfin"** per usare subito l'app in modalità libera.
   - Oppure inserisci URL e credenziali del tuo server Jellyfin se desideri collegarlo.

---

## 📜 Crediti e Disclaimer

### Crediti & Progetto Originale
Questo progetto è basato ed estende il codice di **Edoardo Fiore**, autore del repository open source [StreamingCommunity-downloader](https://github.com/EdoardoFiore/StreamingCommunity-downloader), concesso sotto licenza [MIT](https://github.com/EdoardoFiore/StreamingCommunity-downloader/blob/main/LICENSE).

### Progetto Personale & Non Commerciale
- Questo software è sviluppato e mantenuto **esclusivamente per uso personale, privato e senza fini di lucro**.
- **Non è un prodotto commerciale:** non contiene annunci pubblicitari, non vende nulla e non prevede abbonamenti, donazioni obbligatorie o monetizzazione di alcun genere.

### Disclaimer Legale
Questo software è un client sviluppato a scopo puramente didattico, di studio e di ricerca sui protocolli di streaming HLS e sull'elaborazione multimediale.  
Il programma **non memorizza, non ospita, non ritrasmette e non distribuisce alcun file multimediale o materiale protetto da copyright**. Tutti i flussi e le informazioni vengono richiesti direttamente dai server pubblicamente accessibili sul web.  
L'utente finale è l'unico responsabile dell'utilizzo dello strumento e del rispetto delle normative sul diritto d'autore vigenti nel proprio paese.
