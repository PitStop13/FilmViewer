/* StreamingCommunity Web Panel — jam.js */
//
// JAM Watch Party: real-time playback synchronization between two (or more)
// local Docker instances anywhere in the world (e.g. London <-> Stuttgart)
// using a 6-digit room code over secure public WebSockets MQTT.
//
// Zero port-forwarding or external IP configuration required. Video streams/files
// stay local; only lightweight control actions (play/pause/seek/tick) are shared.

(function() {
  'use strict';

  const BROKERS = [
    { host: 'broker.hivemq.com', port: 8884, path: '/mqtt', name: 'HiveMQ (Primary)' },
    { host: 'broker.emqx.io', port: 8084, path: '/mqtt', name: 'EMQX (Backup)' },
  ];

  const STORAGE_KEYS = {
    nickname: 'fv_jam_nickname',
    roomCode: 'fv_jam_room_code',
    isHost: 'fv_jam_is_host',
    drift: 'fv_jam_drift',
    toasts: 'fv_jam_toasts',
  };

  let _client = null;
  let _activeBrokerIdx = 0;
  let _suppressLocalEvents = false;
  let _heartbeatTimer = null;
  let _pingTimer = null;
  let _lastSentTime = -1;
  let _lastSentState = null;

  const Jam = {
    state: {
      connected: false,
      connecting: false,
      brokerName: '',
      roomCode: null,
      isHost: false,
      nickname: '',
      clientId: `fv_${Math.random().toString(36).substring(2, 9)}`,
      peers: new Map(), // clientId -> { nickname, isHost, pingMs, lastSeen, playing, currentTime }
      driftThreshold: parseFloat(localStorage.getItem(STORAGE_KEYS.drift) || '1.5'),
      showToasts: localStorage.getItem(STORAGE_KEYS.toasts) !== '0',
      lastRemoteMedia: null,
      statusMessage: '',
      statusType: 'muted', // 'muted' | 'success' | 'warning' | 'danger'
    },

    init() {
      // Restore nickname
      const savedNick = localStorage.getItem(STORAGE_KEYS.nickname);
      const userNick = (typeof _me !== 'undefined' && _me && _me.user && _me.user.username) ? _me.user.username : '';
      this.state.nickname = savedNick || userNick || 'Ospite';

      // Check URL parameters for direct room join (e.g., #/settings/jam?code=123456)
      this._checkUrlCode();

      // Hook existing or future video players
      this._hookPlayers();

      // Register global action handlers
      if (typeof registerActions === 'function') {
        registerActions({
          'jam:create': () => this.createRoom(),
          'jam:join': () => this.joinFromInput(),
          'jam:leave': () => this.leaveRoom(),
          'jam:forceSync': () => this.forceSync(),
          'jam:copyCode': () => this.copyRoomCode(),
          'jam:copyLink': () => this.copyQuickLink(),
          'jam:openSettings': () => this.openJamSettings(),
          'jam:toggleToasts': (el) => {
            const enabled = !!el.checked;
            this.state.showToasts = enabled;
            localStorage.setItem(STORAGE_KEYS.toasts, enabled ? '1' : '0');
          },
          'jam:saveNickname': () => {
            const input = document.getElementById('jam-nick-input');
            if (input && input.value.trim()) {
              this.setNickname(input.value.trim());
              if (typeof showToast === 'function') showToast('Nome aggiornato', 'success');
              this.renderSettings();
            }
          },
        });
      }

      // Check if we were previously in a room before reload
      const prevRoom = localStorage.getItem(STORAGE_KEYS.roomCode);
      if (prevRoom && prevRoom.length === 6) {
        const wasHost = localStorage.getItem(STORAGE_KEYS.isHost) === '1';
        this.joinRoom(prevRoom, wasHost, true);
      }
    },

    isActive() {
      return this.state.connected && !!this.state.roomCode;
    },

    setNickname(name) {
      if (!name) return;
      this.state.nickname = name;
      localStorage.setItem(STORAGE_KEYS.nickname, name);
      if (this.isActive()) {
        this.sendAction('NICK_CHANGE', { nickname: name });
      }
    },

    _checkUrlCode() {
      try {
        const hash = window.location.hash || '';
        const match = hash.match(/code=([0-9]{6})/);
        if (match && match[1]) {
          this._pendingCodeFromUrl = match[1];
        }
      } catch (_) {}
    },

    generateRoomCode() {
      return String(Math.floor(100000 + Math.random() * 900000));
    },

    createRoom() {
      const code = this.generateRoomCode();
      this.joinRoom(code, true);
    },

    joinFromInput() {
      const input = document.getElementById('jam-join-code-input');
      if (!input) return;
      const code = input.value.replace(/[^0-9]/g, '');
      if (code.length !== 6) {
        if (typeof showToast === 'function') showToast('Inserisci un codice valido a 6 cifre', 'warning');
        input.focus();
        return;
      }
      this.joinRoom(code, false);
    },

    joinRoom(code, isHost = false, isAutoRejoin = false) {
      if (!window.Paho || !window.Paho.MQTT) {
        if (typeof showToast === 'function') showToast('Libreria di connessione non disponibile', 'danger');
        return;
      }

      code = String(code).trim();
      if (code.length !== 6) return;

      this.leaveRoom(false);

      this.state.connecting = true;
      this.state.roomCode = code;
      this.state.isHost = isHost;
      this.state.statusMessage = 'Connessione al server JAM sicuro in corso...';
      this.state.statusType = 'warning';

      localStorage.setItem(STORAGE_KEYS.roomCode, code);
      localStorage.setItem(STORAGE_KEYS.isHost, isHost ? '1' : '0');

      this.renderSettings();
      this._updatePlayerPills();

      _activeBrokerIdx = 0;
      this._connectToBroker();
    },

    _connectToBroker() {
      const broker = BROKERS[_activeBrokerIdx];
      this.state.brokerName = broker.name;

      try {
        _client = new Paho.MQTT.Client(broker.host, Number(broker.port), broker.path, this.state.clientId);

        _client.onConnectionLost = (responseObject) => {
          console.warn('[JAM] Connection lost:', responseObject.errorMessage);
          this.state.connected = false;
          this.state.connecting = false;
          this.state.peers.clear();
          this._stopLoops();
          this._updatePlayerPills();

          if (this.state.roomCode) {
            this.state.statusMessage = `Connessione interrotta (${responseObject.errorMessage || 'Timeout'}). Riconnessione...`;
            this.state.statusType = 'danger';
            this.renderSettings();
            setTimeout(() => {
              if (this.state.roomCode) this._connectToBroker();
            }, 3000);
          }
        };

        _client.onMessageArrived = (message) => {
          this._handleIncomingMessage(message.payloadString);
        };

        const connectOptions = {
          timeout: 6,
          keepAliveInterval: 30,
          cleanSession: true,
          useSSL: true,
          onSuccess: () => {
            console.info('[JAM] Connected to broker:', broker.name);
            this.state.connected = true;
            this.state.connecting = false;
            this.state.statusMessage = `Connesso alla Stanza #${this.state.roomCode}`;
            this.state.statusType = 'success';

            // Subscribe to room topic
            const topic = `filmviewer/jam/v1/${this.state.roomCode}`;
            _client.subscribe(topic, { qos: 0 });

            // Announce presence
            this.sendAction('JOIN', {
              nickname: this.state.nickname,
              isHost: this.state.isHost,
            });

            this._startLoops();
            this.renderSettings();
            this._updatePlayerPills();

            if (typeof showToast === 'function') {
              showToast(`JAM: Entrato nella stanza #${this.state.roomCode}`, 'success');
            }
          },
          onFailure: (err) => {
            console.error('[JAM] Broker connect failed:', err);
            // Try fallback broker
            if (_activeBrokerIdx < BROKERS.length - 1) {
              _activeBrokerIdx++;
              console.info('[JAM] Retrying with backup broker:', BROKERS[_activeBrokerIdx].name);
              this._connectToBroker();
            } else {
              this.state.connecting = false;
              this.state.connected = false;
              this.state.statusMessage = 'Impossibile raggiungere i server JAM. Verifica la connessione internet.';
              this.state.statusType = 'danger';
              this.renderSettings();
              if (typeof showToast === 'function') {
                showToast('Errore di connessione a JAM', 'danger');
              }
            }
          }
        };

        _client.connect(connectOptions);
      } catch (err) {
        console.error('[JAM] Setup error:', err);
        this.state.connecting = false;
        this.state.connected = false;
        this.renderSettings();
      }
    },

    leaveRoom(notify = true) {
      if (notify && this.isActive()) {
        try {
          this.sendAction('LEAVE', { nickname: this.state.nickname });
        } catch (_) {}
      }

      this._stopLoops();

      if (_client) {
        try {
          if (_client.isConnected()) {
            _client.disconnect();
          }
        } catch (_) {}
        _client = null;
      }

      this.state.connected = false;
      this.state.connecting = false;
      this.state.roomCode = null;
      this.state.isHost = false;
      this.state.peers.clear();
      this.state.statusMessage = 'Disconnesso';
      this.state.statusType = 'muted';

      localStorage.removeItem(STORAGE_KEYS.roomCode);
      localStorage.removeItem(STORAGE_KEYS.isHost);

      this.renderSettings();
      this._updatePlayerPills();
    },

    sendAction(actionType, extra = {}) {
      if (!this.isActive() || !_client || !_client.isConnected()) return;

      const payload = {
        type: actionType,
        clientId: this.state.clientId,
        nickname: this.state.nickname,
        roomCode: this.state.roomCode,
        sentAt: Date.now(),
        ...extra,
      };

      try {
        const topic = `filmviewer/jam/v1/${this.state.roomCode}`;
        const msg = new Paho.MQTT.Message(JSON.stringify(payload));
        msg.destinationName = topic;
        msg.qos = 0;
        _client.send(msg);
      } catch (e) {
        console.warn('[JAM] Send error:', e);
      }
    },

    _handleIncomingMessage(jsonStr) {
      let data;
      try {
        data = JSON.parse(jsonStr);
      } catch (_) {
        return;
      }

      // Ignore messages from self
      if (!data || data.clientId === this.state.clientId) return;

      const senderId = data.clientId;
      const nick = data.nickname || 'Amico';

      switch (data.type) {
        case 'JOIN': {
          this.state.peers.set(senderId, {
            nickname: nick,
            isHost: !!data.isHost,
            lastSeen: Date.now(),
            pingMs: null,
            playing: false,
            currentTime: 0,
          });

          // Welcome them and send our current state
          const activePlayer = this.getActivePlayer();
          this.sendAction('WELCOME', {
            nickname: this.state.nickname,
            isHost: this.state.isHost,
            media: this._getCurrentMediaInfo(),
            playing: activePlayer ? !activePlayer.paused : false,
            currentTime: activePlayer ? activePlayer.currentTime : 0,
          });

          if (this.state.showToasts && typeof showToast === 'function') {
            showToast(`🎧 ${nick} si è unito alla JAM!`, 'success');
          }
          this.renderSettings();
          this._updatePlayerPills();
          break;
        }

        case 'WELCOME': {
          this.state.peers.set(senderId, {
            nickname: nick,
            isHost: !!data.isHost,
            lastSeen: Date.now(),
            pingMs: null,
            playing: !!data.playing,
            currentTime: data.currentTime || 0,
          });

          if (data.media && data.media.title) {
            this.state.lastRemoteMedia = data.media;
          }

          this.renderSettings();
          this._updatePlayerPills();
          break;
        }

        case 'LEAVE': {
          this.state.peers.delete(senderId);
          if (this.state.showToasts && typeof showToast === 'function') {
            showToast(`🎧 ${nick} è uscito dalla stanza`, 'info');
          }
          this.renderSettings();
          this._updatePlayerPills();
          break;
        }

        case 'NICK_CHANGE': {
          if (this.state.peers.has(senderId)) {
            const peer = this.state.peers.get(senderId);
            peer.nickname = nick;
            this.renderSettings();
            this._updatePlayerPills();
          }
          break;
        }

        case 'PING': {
          this.sendAction('PONG', { origT: data.sentAt, targetId: senderId });
          break;
        }

        case 'PONG': {
          if (data.targetId === this.state.clientId && data.origT) {
            const rtt = Date.now() - data.origT;
            const peer = this.state.peers.get(senderId);
            if (peer) {
              peer.pingMs = Math.max(1, Math.round(rtt / 2));
              peer.lastSeen = Date.now();
              this._updatePeerPings();
            }
          }
          break;
        }

        case 'PLAY': {
          this._applyRemotePlayback(true, data.time, nick);
          break;
        }

        case 'PAUSE': {
          this._applyRemotePlayback(false, data.time, nick);
          break;
        }

        case 'SEEK': {
          this._applyRemoteSeek(data.time, data.playing, nick);
          break;
        }

        case 'TICK': {
          // Heartbeat / Drift correction
          const peer = this.state.peers.get(senderId);
          if (peer) {
            peer.playing = !!data.playing;
            peer.currentTime = data.time || 0;
            peer.lastSeen = Date.now();
          }
          this._checkDrift(data.time, data.playing);
          break;
        }

        case 'MEDIA_ANNOUNCE': {
          this.state.lastRemoteMedia = {
            title: data.title,
            mediaType: data.mediaType,
            id: data.id,
            timestamp: Date.now(),
          };
          if (this.state.showToasts && typeof showToast === 'function') {
            showToast(`🎧 ${nick} sta guardando: "${data.title}"`, 'info');
          }
          this.renderSettings();
          break;
        }
      }
    },

    _applyRemotePlayback(play, timestamp, senderNick) {
      const video = this.getActivePlayer();
      if (!video) return;

      _suppressLocalEvents = true;

      if (typeof timestamp === 'number' && !isNaN(timestamp)) {
        const drift = Math.abs(video.currentTime - timestamp);
        if (drift > 0.4) {
          video.currentTime = timestamp;
        }
      }

      if (play) {
        video.play().catch(() => {});
        if (this.state.showToasts && typeof showToast === 'function') {
          showToast(`🎧 ${senderNick} ha avviato la riproduzione`, 'info');
        }
      } else {
        video.pause();
        if (this.state.showToasts && typeof showToast === 'function') {
          showToast(`🎧 ${senderNick} ha messo in pausa a ${this.formatTime(video.currentTime)}`, 'info');
        }
      }

      setTimeout(() => {
        _suppressLocalEvents = false;
      }, 350);
    },

    _applyRemoteSeek(timestamp, resumePlay, senderNick) {
      const video = this.getActivePlayer();
      if (!video) return;

      _suppressLocalEvents = true;
      if (typeof timestamp === 'number' && !isNaN(timestamp)) {
        video.currentTime = timestamp;
      }

      if (resumePlay) {
        video.play().catch(() => {});
      }

      if (this.state.showToasts && typeof showToast === 'function') {
        showToast(`🎧 ${senderNick} è saltato a ${this.formatTime(timestamp)}`, 'info');
      }

      setTimeout(() => {
        _suppressLocalEvents = false;
      }, 350);
    },

    _checkDrift(remoteTime, remotePlaying) {
      const video = this.getActivePlayer();
      if (!video || video.paused || !remotePlaying) return;

      const localTime = video.currentTime;
      const drift = Math.abs(localTime - remoteTime);

      if (drift > this.state.driftThreshold) {
        console.info(`[JAM] Drift detected (${drift.toFixed(2)}s). Resyncing...`);
        _suppressLocalEvents = true;
        video.currentTime = remoteTime;
        setTimeout(() => {
          _suppressLocalEvents = false;
        }, 350);
      }
    },

    forceSync() {
      const video = this.getActivePlayer();
      if (!video) {
        if (typeof showToast === 'function') showToast('Nessun video attualmente in riproduzione', 'warning');
        return;
      }

      this.sendAction('SEEK', {
        time: video.currentTime,
        playing: !video.paused,
      });

      if (!video.paused) {
        this.sendAction('PLAY', { time: video.currentTime });
      } else {
        this.sendAction('PAUSE', { time: video.currentTime });
      }

      if (typeof showToast === 'function') showToast('Stato sincronizzato con la stanza!', 'success');
    },

    _getCurrentMediaInfo() {
      const streamTitleEl = document.getElementById('stream-player-modal-title');
      const streamSubEl = document.getElementById('stream-player-modal-sub');
      const localTitleEl = document.getElementById('player-modal-title');

      if (streamTitleEl && streamTitleEl.textContent) {
        return {
          title: streamTitleEl.textContent,
          subtitle: streamSubEl ? streamSubEl.textContent : '',
          type: 'stream',
        };
      }
      if (localTitleEl && localTitleEl.textContent) {
        return {
          title: localTitleEl.textContent,
          type: 'file',
        };
      }
      return null;
    },

    broadcastMedia(title, mediaType = 'movie', id = null) {
      if (!this.isActive() || !title) return;
      this.sendAction('MEDIA_ANNOUNCE', {
        title,
        mediaType,
        id,
      });
    },

    getActivePlayer() {
      if (typeof getActiveVideoPlayer === 'function') {
        const v = getActiveVideoPlayer();
        if (v) return v;
      }
      const streamModal = document.getElementById('stream-player-modal');
      const streamVideo = document.getElementById('stream-video-player');
      if (streamModal && (streamModal.classList.contains('show') || streamModal.style.display === 'block')) {
        return streamVideo;
      }
      const playerModal = document.getElementById('player-modal');
      const localVideo = document.getElementById('video-player');
      if (playerModal && (playerModal.classList.contains('show') || playerModal.style.display === 'block')) {
        return localVideo;
      }
      return null;
    },

    _hookPlayers() {
      const bind = (id) => {
        const el = document.getElementById(id);
        if (!el || el._jamAttached) return;
        el._jamAttached = true;

        el.addEventListener('play', () => {
          if (_suppressLocalEvents || !this.isActive()) return;
          this.sendAction('PLAY', { time: el.currentTime });
        });

        el.addEventListener('pause', () => {
          if (_suppressLocalEvents || !this.isActive()) return;
          if (el.ended) return; // natural finish
          this.sendAction('PAUSE', { time: el.currentTime });
        });

        el.addEventListener('seeked', () => {
          if (_suppressLocalEvents || !this.isActive()) return;
          this.sendAction('SEEK', { time: el.currentTime, playing: !el.paused });
        });
      };

      bind('stream-video-player');
      bind('video-player');

      // Re-check periodically in case DOM elements were reconstructed
      setInterval(() => {
        bind('stream-video-player');
        bind('video-player');
      }, 2000);
    },

    _startLoops() {
      this._stopLoops();

      // Heartbeat every 2.5s while playing
      _heartbeatTimer = setInterval(() => {
        if (!this.isActive()) return;
        const video = this.getActivePlayer();
        if (video && !video.paused) {
          this.sendAction('TICK', {
            time: video.currentTime,
            playing: true,
          });
        }
      }, 2500);

      // Ping peers every 5s to measure latency
      _pingTimer = setInterval(() => {
        if (!this.isActive() || this.state.peers.size === 0) return;
        this.sendAction('PING', {});
      }, 5000);
    },

    _stopLoops() {
      if (_heartbeatTimer) clearInterval(_heartbeatTimer);
      if (_pingTimer) clearInterval(_pingTimer);
      _heartbeatTimer = null;
      _pingTimer = null;
    },

    _updatePlayerPills() {
      const isLive = this.isActive();
      const code = this.state.roomCode || '';
      const peerCount = this.state.peers.size;
      const countLabel = peerCount === 1 ? '1 amico' : `${peerCount} amici`;

      const updatePill = (pillId) => {
        const pill = document.getElementById(pillId);
        if (!pill) return;
        if (!isLive) {
          pill.style.display = 'none';
          return;
        }
        pill.style.display = 'inline-flex';
        pill.innerHTML = `
          <span class="jam-dot ${peerCount > 0 ? 'online' : 'waiting'}"></span>
          <span class="jam-pill-text">JAM: <strong>#${code}</strong></span>
          <span class="badge ${peerCount > 0 ? 'bg-green-lt' : 'bg-yellow-lt'} ms-1" style="font-size:10px;">${countLabel}</span>
        `;
      };

      updatePill('player-jam-pill');
      updatePill('stream-player-jam-pill');
    },

    _updatePeerPings() {
      const el = document.getElementById('jam-peers-list');
      if (el) this._renderPeersList(el);
      this._updatePlayerPills();
    },

    formatTime(sec) {
      if (sec == null || isNaN(sec) || sec < 0) return '00:00';
      sec = Math.floor(sec);
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = sec % 60;
      if (h > 0) {
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
      }
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    },

    copyRoomCode() {
      if (!this.state.roomCode) return;
      navigator.clipboard.writeText(this.state.roomCode).then(() => {
        if (typeof showToast === 'function') showToast(`Codice #${this.state.roomCode} copiato!`, 'success');
      }).catch(() => {
        if (typeof showToast === 'function') showToast(`Codice: ${this.state.roomCode}`, 'info');
      });
    },

    copyQuickLink() {
      if (!this.state.roomCode) return;
      const url = `${window.location.origin}/#/settings/jam?code=${this.state.roomCode}`;
      navigator.clipboard.writeText(url).then(() => {
        if (typeof showToast === 'function') showToast('Link rapido per l\'amico copiato negli appunti!', 'success');
      }).catch(() => {
        if (typeof showToast === 'function') showToast(url, 'info');
      });
    },

    openJamSettings() {
      if (typeof switchSettingsTab === 'function') {
        if (typeof openSettings === 'function') openSettings();
        setTimeout(() => switchSettingsTab('jam'), 50);
      }
    },

    // ── Render Settings Pane ──────────────────────────────────────────────────

    renderSettings() {
      const container = document.getElementById('jam-container');
      if (!container) return;

      const isLive = this.isActive();
      const code = this.state.roomCode;
      const isConnecting = this.state.connecting;

      if (!isLive && !isConnecting) {
        // Disconnected view: Create or Join
        const pending = this._pendingCodeFromUrl || '';
        this._pendingCodeFromUrl = null;

        container.innerHTML = `
          <!-- Header Banner -->
          <div class="jam-hero-banner mb-4">
            <div class="d-flex align-items-center gap-3">
              <div class="jam-icon-box">
                <i class="ti ti-headphones fs-1 text-primary"></i>
              </div>
              <div>
                <h3 class="mb-1 text-white fw-bold d-flex align-items-center gap-2">
                  JAM Watch Party
                  <span class="badge bg-purple-lt">P2P Cloud Sync</span>
                </h3>
                <p class="text-muted small mb-0">
                  Guarda film e serie insieme a distanza, perfettamente sincronizzati secondo per secondo.
                  Ciascuno esegue il proprio container Docker in locale (es. Londra e Stoccarda): nessuna porta da aprire sul router, basta un codice a 6 cifre.
                </p>
              </div>
            </div>
          </div>

          <!-- Nickname Config -->
          <div class="card mb-4" style="background:var(--bg-surface); border:1px solid var(--border);">
            <div class="card-body p-3">
              <div class="row g-2 align-items-center">
                <div class="col-auto">
                  <span class="text-muted small"><i class="ti ti-user me-1"></i>Il tuo nome visualizzato:</span>
                </div>
                <div class="col" style="max-width:240px;">
                  <input type="text" class="form-control form-control-sm bg-dark text-white border-secondary" id="jam-nick-input"
                         value="${typeof escapeHtml === 'function' ? escapeHtml(this.state.nickname) : this.state.nickname}" maxlength="24">
                </div>
                <div class="col-auto">
                  <button type="button" class="btn btn-sm btn-outline-secondary" data-action="jam:saveNickname">Salva nome</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Two Main Cards: Create or Join -->
          <div class="row g-3">
            <!-- Create Room -->
            <div class="col-md-6">
              <div class="card h-100 jam-action-card" style="background:var(--bg-surface); border:1px solid var(--border-mid); border-radius:12px;">
                <div class="card-body p-4 text-center d-flex flex-column justify-content-between">
                  <div>
                    <div class="mb-3 d-inline-flex p-3 rounded-circle" style="background:rgba(61,107,245,0.12);">
                      <i class="ti ti-circle-plus text-primary fs-1"></i>
                    </div>
                    <h4 class="text-white fw-bold mb-2">Crea una Stanza</h4>
                    <p class="text-muted small mb-4">
                      Genera un codice a 6 cifre univoco e invialo al tuo amico. Tu sarai l'Host della sessione.
                    </p>
                  </div>
                  <div>
                    <button type="button" class="btn btn-primary w-100 py-2 fw-bold" data-action="jam:create">
                      <i class="ti ti-sparkles me-2"></i>Crea nuova Stanza JAM
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Join Room -->
            <div class="col-md-6">
              <div class="card h-100 jam-action-card" style="background:var(--bg-surface); border:1px solid var(--border-mid); border-radius:12px;">
                <div class="card-body p-4 text-center d-flex flex-column justify-content-between">
                  <div>
                    <div class="mb-3 d-inline-flex p-3 rounded-circle" style="background:rgba(47,191,113,0.12);">
                      <i class="ti ti-login text-success fs-1"></i>
                    </div>
                    <h4 class="text-white fw-bold mb-2">Partecipa a una Stanza</h4>
                    <p class="text-muted small mb-3">
                      Inserisci il codice a 6 cifre fornito dal tuo amico per collegarti istantaneamente alla sua sessione.
                    </p>
                    <div class="mb-3" style="max-width:240px; margin:0 auto;">
                      <input type="text" id="jam-join-code-input" class="form-control text-center text-white fw-bold font-monospace"
                             style="font-size:24px; letter-spacing:6px; background:var(--bg-input); border:1px solid var(--accent-ring);"
                             placeholder="000000" maxlength="6" value="${pending}" autocomplete="off" inputmode="numeric">
                    </div>
                  </div>
                  <div>
                    <button type="button" class="btn btn-success w-100 py-2 fw-bold" data-action="jam:join">
                      <i class="ti ti-arrows-join me-2"></i>Entra nella JAM
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Feature Description & FAQ -->
          <div class="card mt-4" style="background:rgba(255,255,255,0.02); border:1px solid var(--border);">
            <div class="card-body p-3">
              <div class="d-flex align-items-center gap-2 mb-2">
                <i class="ti ti-info-circle text-info"></i>
                <h5 class="m-0 text-white fw-bold" style="font-size:14px;">Come funziona la sincronizzazione tra Londra e Stoccarda?</h5>
              </div>
              <ul class="text-muted small mb-0 ps-3">
                <li class="mb-1"><strong>Nessun file o video viene inviato:</strong> ciascun utente riproduce il film localmente sul proprio Docker.</li>
                <li class="mb-1"><strong>Zero configurazione di rete:</strong> la connessione usa WebSocket sicuri crittografati su porte standard aperte in uscita.</li>
                <li class="mb-1"><strong>Sincronizzazione al frame:</strong> se metti in pausa, riproduci o salti avanti/indietro, l'azione si riflette in millisecondi sull'altro player.</li>
                <li><strong>Anti-Drift automatico:</strong> se uno dei due subisce un buffering di rete, il player si riallinea da solo dopo 1.5 secondi per restare sempre sincronizzato.</li>
              </ul>
            </div>
          </div>
        `;

        const joinInput = document.getElementById('jam-join-code-input');
        if (joinInput) {
          joinInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.joinFromInput();
          });
        }
        return;
      }

      // Connecting State
      if (isConnecting) {
        container.innerHTML = `
          <div class="card text-center p-5" style="background:var(--bg-surface); border:1px solid var(--border);">
            <div class="spinner-border text-primary mb-3" style="width:3rem; height:3rem;" role="status"></div>
            <h4 class="text-white fw-bold mb-1">Connessione alla Stanza #${code}...</h4>
            <p class="text-muted small mb-4">${this.state.statusMessage}</p>
            <div>
              <button type="button" class="btn btn-outline-secondary btn-sm" data-action="jam:leave">Annulla</button>
            </div>
          </div>
        `;
        return;
      }

      // Active Room Dashboard
      const codeFormatted = `${code.slice(0, 3)} ${code.slice(3)}`;
      const peerCount = this.state.peers.size;

      container.innerHTML = `
        <!-- Active Room Header Card -->
        <div class="card mb-4" style="background:linear-gradient(135deg, rgba(61,107,245,0.12), rgba(16,21,31,0.9)); border:1px solid var(--accent-ring); border-radius:12px;">
          <div class="card-body p-4">
            <div class="d-flex flex-wrap align-items-center justify-content-between gap-3">
              <div>
                <span class="badge bg-purple-lt mb-2">
                  <i class="ti ti-broadcast me-1"></i>SESSIONE ATTIVA
                </span>
                <div class="d-flex align-items-baseline gap-3">
                  <h1 class="text-white fw-bold font-monospace m-0" style="font-size:38px; letter-spacing:4px;">
                    #${codeFormatted}
                  </h1>
                  <button type="button" class="btn btn-sm btn-outline-primary" data-action="jam:copyCode" title="Copia codice">
                    <i class="ti ti-copy me-1"></i>Copia Codice
                  </button>
                  <button type="button" class="btn btn-sm btn-outline-secondary" data-action="jam:copyLink" title="Copia link rapido">
                    <i class="ti ti-link me-1"></i>Link rapido
                  </button>
                </div>
                <div class="text-muted small mt-2 d-flex align-items-center gap-2">
                  <span class="jam-dot ${peerCount > 0 ? 'online' : 'waiting'}"></span>
                  <span>${peerCount > 0 ? `Connesso con ${peerCount === 1 ? '1 amico' : peerCount + ' amici'}` : 'In attesa dell\'amico... Invia il codice a 6 cifre per farlo unire!'}</span>
                  &bull;
                  <span class="text-info">${this.state.brokerName}</span>
                </div>
              </div>

              <div class="d-flex gap-2">
                <button type="button" class="btn btn-outline-primary" data-action="jam:forceSync" title="Forza sincronizzazione immediata">
                  <i class="ti ti-refresh me-1"></i>Forza Sincro
                </button>
                <button type="button" class="btn btn-outline-danger" data-action="jam:leave" title="Esci dalla stanza">
                  <i class="ti ti-logout me-1"></i>Esci dalla JAM
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Participants List -->
        <div class="row g-3 mb-4">
          <div class="col-md-7">
            <div class="card h-100" style="background:var(--bg-surface); border:1px solid var(--border);">
              <div class="card-header py-2 px-3 border-0 d-flex justify-content-between align-items-center" style="background:rgba(255,255,255,0.02); border-bottom:1px solid var(--border) !important;">
                <h5 class="card-title m-0 text-white fw-bold" style="font-size:14px;">
                  <i class="ti ti-users me-1 text-primary"></i>Partecipanti alla Stanza
                </h5>
                <span class="badge bg-secondary-lt">${peerCount + 1} presenti</span>
              </div>
              <div class="card-body p-3" id="jam-peers-list"></div>
            </div>
          </div>

          <!-- Preferences and Quick Actions -->
          <div class="col-md-5">
            <div class="card h-100" style="background:var(--bg-surface); border:1px solid var(--border);">
              <div class="card-header py-2 px-3 border-0" style="background:rgba(255,255,255,0.02); border-bottom:1px solid var(--border) !important;">
                <h5 class="card-title m-0 text-white fw-bold" style="font-size:14px;">
                  <i class="ti ti-adjustments me-1 text-primary"></i>Preferenze JAM
                </h5>
              </div>
              <div class="card-body p-3">
                <div class="mb-3">
                  <label class="form-label small text-muted mb-1">Tolleranza Auto-Sync (Anti-Drift):</label>
                  <select class="form-select form-select-sm bg-dark text-white border-secondary" id="jam-drift-select">
                    <option value="1.0" ${this.state.driftThreshold === 1.0 ? 'selected' : ''}>1.0 secondo (Più aggressivo)</option>
                    <option value="1.5" ${this.state.driftThreshold === 1.5 ? 'selected' : ''}>1.5 secondi (Consigliato)</option>
                    <option value="2.5" ${this.state.driftThreshold === 2.5 ? 'selected' : ''}>2.5 secondi (Tollerante per connessioni lente)</option>
                  </select>
                  <small class="text-muted" style="font-size:11px;">Riallinea il timestamp se uno dei due accumula ritardo durante la riproduzione.</small>
                </div>

                <div class="form-check form-switch mb-3">
                  <input class="form-check-input" type="checkbox" id="jam-toasts-toggle" ${this.state.showToasts ? 'checked' : ''} data-action="jam:toggleToasts">
                  <label class="form-check-label text-white small" for="jam-toasts-toggle">Mostra notifiche azioni dell'amico</label>
                  <div class="text-muted" style="font-size:11px;">Mostra un avviso a schermo quando l'amico mette in pausa, riprende o salta nel video.</div>
                </div>

                ${this._renderMediaStatusCard()}
              </div>
            </div>
          </div>
        </div>
      `;

      const peersListEl = document.getElementById('jam-peers-list');
      if (peersListEl) this._renderPeersList(peersListEl);

      const driftSelect = document.getElementById('jam-drift-select');
      if (driftSelect) {
        driftSelect.addEventListener('change', (e) => {
          const val = parseFloat(e.target.value);
          this.state.driftThreshold = val;
          localStorage.setItem(STORAGE_KEYS.drift, String(val));
          if (typeof showToast === 'function') showToast(`Tolleranza sincronizzazione impostata a ${val}s`, 'success');
        });
      }
    },

    _renderPeersList(container) {
      const peers = Array.from(this.state.peers.values());
      const safeMyNick = typeof escapeHtml === 'function' ? escapeHtml(this.state.nickname) : this.state.nickname;
      const myPlayer = this.getActivePlayer();
      const myPlaying = myPlayer ? !myPlayer.paused : false;
      const myTime = myPlayer ? this.formatTime(myPlayer.currentTime) : 'Inattivo';

      let html = `
        <!-- Local User -->
        <div class="d-flex align-items-center justify-content-between p-2 mb-2 rounded" style="background:rgba(255,255,255,0.03); border:1px solid var(--border);">
          <div class="d-flex align-items-center gap-2">
            <span class="jam-dot online"></span>
            <div>
              <div class="text-white fw-bold small">${safeMyNick} <span class="badge bg-primary-lt ms-1">Tu (${this.state.isHost ? 'Host' : 'Guest'})</span></div>
              <small class="text-muted" style="font-size:11px;">${myPlaying ? '🟢 In riproduzione' : '⏸️ In pausa'} a ${myTime}</small>
            </div>
          </div>
          <span class="badge bg-secondary-lt" style="font-size:11px;">Locale</span>
        </div>
      `;

      if (peers.length === 0) {
        html += `
          <div class="text-center py-4 text-muted small">
            <i class="ti ti-user-plus fs-2 mb-2 d-block text-secondary"></i>
            Nessun amico collegato al momento.<br>
            Comunica il codice a 6 cifre <strong>#${this.state.roomCode}</strong> per iniziare a guardare insieme!
          </div>
        `;
      } else {
        peers.forEach(peer => {
          const safePeerNick = typeof escapeHtml === 'function' ? escapeHtml(peer.nickname) : peer.nickname;
          const pingStr = peer.pingMs != null ? `${peer.pingMs} ms` : 'Calcolo...';
          const peerTime = peer.currentTime ? this.formatTime(peer.currentTime) : '—';
          html += `
            <div class="d-flex align-items-center justify-content-between p-2 mb-2 rounded" style="background:rgba(255,255,255,0.03); border:1px solid var(--border);">
              <div class="d-flex align-items-center gap-2">
                <span class="jam-dot online"></span>
                <div>
                  <div class="text-white fw-bold small">${safePeerNick} <span class="badge bg-secondary-lt ms-1">${peer.isHost ? 'Host' : 'Partner'}</span></div>
                  <small class="text-muted" style="font-size:11px;">${peer.playing ? '🟢 In riproduzione' : '⏸️ In pausa'} a ${peerTime}</small>
                </div>
              </div>
              <div class="text-end">
                <span class="badge bg-green-lt" title="Latenza stimata"><i class="ti ti-activity me-1"></i>${pingStr}</span>
              </div>
            </div>
          `;
        });
      }

      container.innerHTML = html;
    },

    _renderMediaStatusCard() {
      const activeVideo = this.getActivePlayer();
      const currentMedia = this._getCurrentMediaInfo();

      if (activeVideo && currentMedia) {
        return `
          <div class="p-2 rounded mt-2" style="background:rgba(47,191,113,0.08); border:1px solid var(--green-ring);">
            <div class="text-success small fw-bold mb-1"><i class="ti ti-movie me-1"></i>In riproduzione locale:</div>
            <div class="text-white small fw-bold text-truncate">${typeof escapeHtml === 'function' ? escapeHtml(currentMedia.title) : currentMedia.title}</div>
            <small class="text-muted">${this.formatTime(activeVideo.currentTime)}</small>
          </div>
        `;
      }

      if (this.state.lastRemoteMedia && this.state.lastRemoteMedia.title) {
        return `
          <div class="p-2 rounded mt-2" style="background:rgba(61,107,245,0.08); border:1px solid var(--accent-ring);">
            <div class="text-primary small fw-bold mb-1"><i class="ti ti-device-tv me-1"></i>L'amico ha avviato:</div>
            <div class="text-white small fw-bold text-truncate">${typeof escapeHtml === 'function' ? escapeHtml(this.state.lastRemoteMedia.title) : this.state.lastRemoteMedia.title}</div>
          </div>
        `;
      }

      return `
        <div class="p-2 rounded mt-2" style="background:rgba(255,255,255,0.02); border:1px solid var(--border);">
          <small class="text-muted"><i class="ti ti-player-play me-1"></i>Avvia un film o una serie dallo streaming o dai File: il controllo verrà sincronizzato automaticamente.</small>
        </div>
      `;
    }
  };

  // Expose globally
  window.Jam = Jam;

  // Initialize on DOM load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Jam.init());
  } else {
    Jam.init();
  }
})();
