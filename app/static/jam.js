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
  let _reconnectTimer = null;
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
      activeProposal: null, // when initiating: { id, media, responses: Map<peerId, { nickname, status, ready }>, initiatorReady: false }
      incomingProposal: null, // when receiving: { id, senderId, senderNick, media }
      countdownActive: false,
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
          'jam:joinAuto': (d) => {
            const code = (d && d.code) || this._pendingCodeFromUrl;
            if (code) this.joinRoom(code, false);
          },
          'jam:leave': () => this.leaveRoom(),
          'jam:forceSync': () => this.forceSync(),
          'jam:copyCode': (d, el) => this.copyRoomCode(el),
          'jam:copyLink': (d, el) => this.copyQuickLink(el),
          'jam:shareLink': (d, el) => this.shareLink(el),
          'jam:openSettings': () => this.openJamSettings(),
          'jam:openFullSettings': () => this.openFullSettings(),
          'jam:acceptProposal': () => this.acceptProposal(),
          'jam:rejectProposal': () => this.rejectProposal(),
          'jam:startNow': () => this.startNow(),
          'jam:cancelParty': () => this.cancelParty(),
          'jam:toggleToasts': (d, el) => {
            const enabled = !!(el && el.checked);
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

    hasConnectedPeers() {
      if (!this.isActive()) return false;
      return this.state.peers.size > 0;
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
        const stored = sessionStorage.getItem('fv_jam_pending_code');
        if (stored && /^[0-9]{6}$/.test(stored)) {
          sessionStorage.removeItem('fv_jam_pending_code');
          this._pendingCodeFromUrl = stored;
          return;
        }

        const raw = (window.location.hash || '') + (window.location.search || '');
        const match = raw.match(/code=([0-9]{6})/);
        if (match && match[1]) {
          this._pendingCodeFromUrl = match[1];
        }
      } catch (_) {}
    },

    setPendingCode(code) {
      if (!code) return;
      code = String(code).trim().replace(/[^0-9]/g, '');
      if (code.length === 6) {
        this._pendingCodeFromUrl = code;
        if (!this.isActive() && !this.state.connecting) {
          this.renderSettings();
        }
      }
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

          if (_reconnectTimer) clearTimeout(_reconnectTimer);
          if (this.state.roomCode) {
            this.state.statusMessage = `Connessione interrotta (${responseObject.errorMessage || 'Timeout'}). Riconnessione...`;
            this.state.statusType = 'danger';
            this.renderSettings();
            _reconnectTimer = setTimeout(() => {
              _reconnectTimer = null;
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
      if (_reconnectTimer) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = null;
      }

      if (notify && this.isActive()) {
        try {
          this.sendAction('LEAVE', { nickname: this.state.nickname });
        } catch (_) {}
      }

      this._stopLoops();

      if (_client) {
        try {
          _client.onConnectionLost = null;
          _client.onMessageArrived = null;
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
      this.state.activeProposal = null;
      this.state.incomingProposal = null;
      this.state.countdownActive = false;
      this._hidePartyOverlays();
      if (typeof hideModal === 'function') {
        hideModal('jam-proposal-modal');
      }
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

        case 'PARTY_PROPOSAL': {
          if (!data.proposalId || !data.media) return;
          this.state.incomingProposal = {
            id: data.proposalId,
            senderId,
            senderNick: nick,
            media: data.media,
          };
          this._showProposalModal(nick, data.media);
          break;
        }

        case 'PARTY_RESPONSE': {
          if (!this.state.activeProposal || this.state.activeProposal.id !== data.proposalId) return;

          const prop = this.state.activeProposal;
          const peerResp = prop.responses.get(senderId) || { nickname: nick };
          peerResp.status = data.accepted ? 'accepted' : 'rejected';
          prop.responses.set(senderId, peerResp);

          if (data.accepted) {
            if (this.state.showToasts && typeof showToast === 'function') {
              showToast(`🎉 ${nick} ha accettato l'invito! Caricamento in corso...`, 'success');
            }
          } else {
            if (this.state.showToasts && typeof showToast === 'function') {
              showToast(`ℹ️ ${nick} ha rifiutato l'invito.`, 'info');
            }
          }

          this._updatePartyOverlays();
          this._checkPartyAllReady();
          break;
        }

        case 'PARTY_READY': {
          if (!this.state.activeProposal || this.state.activeProposal.id !== data.proposalId) return;

          const prop = this.state.activeProposal;
          const peerResp = prop.responses.get(senderId) || { nickname: nick };
          peerResp.status = 'accepted';
          peerResp.ready = true;
          prop.responses.set(senderId, peerResp);

          this._updatePartyOverlays();
          this._checkPartyAllReady();
          break;
        }

        case 'PARTY_START': {
          const sec = Number(data.countdownSec) || 3;
          this._runCountdown(sec);
          break;
        }

        case 'PARTY_CANCEL': {
          if (this.state.incomingProposal && this.state.incomingProposal.id === data.proposalId) {
            this.state.incomingProposal = null;
            if (typeof hideModal === 'function') {
              hideModal('jam-proposal-modal');
            }
            this._hidePartyOverlays();
            if (this.state.showToasts && typeof showToast === 'function') {
              showToast(`Invito Watch Party annullato da ${nick}.`, 'warning');
            }
          }
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

    proposeMedia(opts) {
      if (!this.isActive() || !this.hasConnectedPeers()) return false;

      const proposalId = 'jam_prop_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7);
      const media = {
        type: opts.type || 'movie',
        id: opts.id,
        slug: opts.slug || '',
        title: opts.title || 'Film',
        episodeId: opts.episodeId,
        episodeNumber: opts.episodeNumber,
        episodeTitle: opts.episodeTitle,
        poster: opts.poster || '',
        startTime: opts.startTime || 0,
      };

      const responses = new Map();
      this.state.peers.forEach((peer, peerId) => {
        responses.set(peerId, {
          nickname: peer.nickname || 'Amico',
          status: 'pending',
          ready: false,
        });
      });

      this.state.activeProposal = {
        id: proposalId,
        media,
        responses,
        initiatorReady: false,
      };

      // Broadcast proposal to all peers in room
      this.sendAction('PARTY_PROPOSAL', {
        proposalId,
        media,
      });

      // Open stream player with flags so it buffers and stays paused
      if (typeof openStreamPlayer === 'function') {
        openStreamPlayer({
          ...opts,
          _jamDirectPlay: true,
          _jamPendingParty: true,
        });
      }

      this._updatePartyOverlays();
      return true;
    },

    _showProposalModal(nick, media) {
      const modal = document.getElementById('jam-proposal-modal');
      if (!modal) return;

      const nickEl = document.getElementById('jam-proposal-nick');
      const titleEl = document.getElementById('jam-proposal-title');
      const subEl = document.getElementById('jam-proposal-sub');
      const posterImg = document.getElementById('jam-proposal-poster');
      const posterFallback = document.getElementById('jam-proposal-poster-fallback');
      const roomBadge = document.getElementById('jam-proposal-room-badge');

      if (nickEl) nickEl.textContent = nick;
      if (titleEl) titleEl.textContent = media.title || 'Film';
      if (subEl) {
        if (media.type === 'movie') {
          subEl.textContent = 'Film';
        } else {
          subEl.textContent = media.episodeTitle ? `${media.episodeTitle} (Ep. ${media.episodeNumber || 1})` : `Episodio ${media.episodeNumber || 1}`;
        }
      }
      if (roomBadge) roomBadge.textContent = `Stanza #${this.state.roomCode}`;

      if (posterImg && posterFallback) {
        if (media.poster) {
          posterImg.src = media.poster;
          posterImg.style.display = 'block';
          posterFallback.style.display = 'none';
          posterImg.onerror = () => {
            posterImg.style.display = 'none';
            posterFallback.style.display = 'flex';
          };
        } else {
          posterImg.style.display = 'none';
          posterFallback.style.display = 'flex';
        }
      }

      if (typeof showModal === 'function') {
        showModal('jam-proposal-modal');
      }
    },

    acceptProposal() {
      const prop = this.state.incomingProposal;
      if (!prop) return;

      if (typeof hideModal === 'function') {
        hideModal('jam-proposal-modal');
      }

      this.sendAction('PARTY_RESPONSE', {
        proposalId: prop.id,
        accepted: true,
      });

      // Open player paused
      if (typeof openStreamPlayer === 'function') {
        openStreamPlayer({
          ...prop.media,
          _jamDirectPlay: true,
          _jamPendingParty: true,
        });
      }

      this._showReceiverWaitOverlay(prop.senderNick);
    },

    rejectProposal() {
      const prop = this.state.incomingProposal;
      if (typeof hideModal === 'function') {
        hideModal('jam-proposal-modal');
      }
      if (!prop) return;

      this.sendAction('PARTY_RESPONSE', {
        proposalId: prop.id,
        accepted: false,
      });
      this.state.incomingProposal = null;
    },

    notifyPlayerReady() {
      const player = this.getActivePlayer();
      if (player) {
        try { player.pause(); } catch (_) {}
      }

      // If we are receiver of an incoming proposal
      if (this.state.incomingProposal) {
        this.sendAction('PARTY_READY', {
          proposalId: this.state.incomingProposal.id,
        });
        const statusEl = document.getElementById('stream-player-jam-desc') || document.getElementById('player-jam-desc');
        if (statusEl) {
          const initiatorName = typeof escapeHtml === 'function' ? escapeHtml(this.state.incomingProposal.senderNick || 'l\'organizzatore') : (this.state.incomingProposal.senderNick || 'l\'organizzatore');
          statusEl.textContent = `Video pronto! In attesa che ${initiatorName} dia il via sincronizzato...`;
        }
      }

      // If we are initiator
      if (this.state.activeProposal) {
        this.state.activeProposal.initiatorReady = true;
        this._checkPartyAllReady();
      }
    },

    _checkPartyAllReady() {
      if (!this.state.activeProposal) return;
      const prop = this.state.activeProposal;

      if (!prop.initiatorReady) return;

      let allResponded = true;
      let hasAccepted = false;
      let allAcceptedReady = true;

      prop.responses.forEach((resp) => {
        if (resp.status === 'pending') allResponded = false;
        if (resp.status === 'accepted') {
          hasAccepted = true;
          if (!resp.ready) allAcceptedReady = false;
        }
      });

      if (allResponded && hasAccepted && allAcceptedReady) {
        this.startNow();
      }
    },

    startNow() {
      const proposalId = this.state.activeProposal ? this.state.activeProposal.id : (this.state.incomingProposal ? this.state.incomingProposal.id : null);
      if (proposalId) {
        this.sendAction('PARTY_START', {
          proposalId,
          countdownSec: 3,
        });
      }
      this._runCountdown(3);
    },

    cancelParty() {
      if (this.state.activeProposal) {
        this.sendAction('PARTY_CANCEL', { proposalId: this.state.activeProposal.id });
        this.state.activeProposal = null;
      }
      this.state.incomingProposal = null;
      this._hidePartyOverlays();
      if (typeof hideModal === 'function') {
        hideModal('stream-player-modal');
        hideModal('player-modal');
        hideModal('jam-proposal-modal');
      }
    },

    _runCountdown(sec) {
      this.state.countdownActive = true;
      this._hidePartyOverlays();

      const streamCd = document.getElementById('stream-player-countdown-overlay');
      const localCd = document.getElementById('player-countdown-overlay');
      const streamNum = document.getElementById('stream-player-countdown-number');
      const localNum = document.getElementById('player-countdown-number');

      const isStreamShown = streamCd && streamCd.closest && (streamCd.closest('.modal')?.classList.contains('show') || streamCd.closest('.modal')?.style.display === 'block');
      const cdOverlay = isStreamShown ? streamCd : (streamCd || localCd);
      const numEl = cdOverlay === streamCd ? streamNum : localNum;

      if (cdOverlay) {
        cdOverlay.style.display = 'flex';
      }

      let current = sec;
      if (numEl) {
        numEl.textContent = String(current);
        numEl.style.color = '#2ed573';
      }

      const player = this.getActivePlayer();
      if (player) {
        try {
          player.pause();
          player.currentTime = 0;
        } catch (_) {}
      }

      const timer = setInterval(() => {
        current--;
        if (current > 0) {
          if (numEl) {
            numEl.textContent = String(current);
            numEl.style.animation = 'none';
            void numEl.offsetWidth;
            numEl.style.animation = 'jamCountdownPop 0.85s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
          }
        } else if (current === 0) {
          if (numEl) {
            numEl.textContent = 'VIA!';
            numEl.style.color = '#fff';
          }
        } else {
          clearInterval(timer);
          if (cdOverlay) cdOverlay.style.display = 'none';
          this.state.countdownActive = false;
          this.state.activeProposal = null;
          this.state.incomingProposal = null;

          const p = this.getActivePlayer();
          if (p) {
            p.play().catch(() => {});
          }
        }
      }, 1000);
    },

    _updatePartyOverlays() {
      if (!this.state.activeProposal) return;
      const prop = this.state.activeProposal;

      const overlays = [
        { overlay: document.getElementById('stream-player-jam-overlay'), peersEl: document.getElementById('stream-player-jam-peers'), titleEl: document.getElementById('stream-player-jam-title'), descEl: document.getElementById('stream-player-jam-desc') },
        { overlay: document.getElementById('player-jam-overlay'), peersEl: document.getElementById('player-jam-peers'), titleEl: document.getElementById('player-jam-title'), descEl: document.getElementById('player-jam-desc') },
      ];

      overlays.forEach(({ overlay, peersEl, titleEl, descEl }) => {
        if (!overlay || !peersEl) return;
        overlay.style.display = 'flex';

        if (titleEl) titleEl.textContent = 'Sondaggio Watch Party in corso...';
        if (descEl) descEl.textContent = 'Il film non inizierà finché i partecipanti non avranno risposto, per partire tutti nello stesso momento.';

        let html = '';
        prop.responses.forEach((resp) => {
          let badge = '';
          if (resp.status === 'pending') {
            badge = '<span class="badge bg-warning-lt"><i class="ti ti-hourglass-empty me-1"></i>In attesa...</span>';
          } else if (resp.status === 'accepted') {
            badge = resp.ready
              ? '<span class="badge bg-success-lt"><i class="ti ti-check me-1"></i>Pronto al via!</span>'
              : '<span class="badge bg-info-lt"><i class="spinner-border spinner-border-sm me-1"></i>Caricamento...</span>';
          } else if (resp.status === 'rejected') {
            badge = '<span class="badge bg-secondary-lt"><i class="ti ti-x me-1"></i>Ha rifiutato</span>';
          }
          const name = typeof escapeHtml === 'function' ? escapeHtml(resp.nickname) : resp.nickname;
          html += `
            <div class="d-flex align-items-center justify-content-between p-2 rounded" style="background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.08);">
              <span class="text-white fw-bold"><i class="ti ti-user me-1 text-muted"></i>${name}</span>
              ${badge}
            </div>
          `;
        });
        peersEl.innerHTML = html;
      });
    },

    _showReceiverWaitOverlay(initiatorNick) {
      const name = typeof escapeHtml === 'function' ? escapeHtml(initiatorNick || 'Amico') : (initiatorNick || 'Amico');
      const overlays = [
        { overlay: document.getElementById('stream-player-jam-overlay'), titleEl: document.getElementById('stream-player-jam-title'), descEl: document.getElementById('stream-player-jam-desc'), peersEl: document.getElementById('stream-player-jam-peers'), actionsEl: document.getElementById('stream-player-jam-actions') },
        { overlay: document.getElementById('player-jam-overlay'), titleEl: document.getElementById('player-jam-title'), descEl: document.getElementById('player-jam-desc'), peersEl: document.getElementById('player-jam-peers'), actionsEl: document.getElementById('player-jam-actions') },
      ];

      overlays.forEach(({ overlay, titleEl, descEl, peersEl, actionsEl }) => {
        if (!overlay) return;
        overlay.style.display = 'flex';
        if (titleEl) titleEl.textContent = 'Connesso al Watch Party!';
        if (descEl) descEl.textContent = `Caricamento flusso video... In attesa del via simultaneo da parte di ${name}.`;
        if (peersEl) peersEl.innerHTML = '<div class="spinner-border text-success my-2" role="status"></div>';
        if (actionsEl) {
          actionsEl.innerHTML = `
            <button type="button" class="btn btn-outline-secondary btn-sm px-3" data-action="jam:cancelParty">
              <i class="ti ti-x me-1"></i>Esci dal Party
            </button>
          `;
        }
      });
    },

    _hidePartyOverlays() {
      const o1 = document.getElementById('stream-player-jam-overlay');
      const o2 = document.getElementById('player-jam-overlay');
      if (o1) o1.style.display = 'none';
      if (o2) o2.style.display = 'none';
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
      const qEl = document.getElementById('jam-quick-modal-body');
      if (qEl && document.getElementById('jam-quick-modal')?.classList.contains('show')) {
        this.renderQuickModal();
      }
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

    getQuickLink() {
      if (!this.state.roomCode) return '';
      const base = window.location.origin + window.location.pathname;
      return `${base.replace(/\/+$/, '')}/#/settings/jam?code=${this.state.roomCode}`;
    },

    async copyRoomCode(btnEl) {
      const code = this.state.roomCode;
      if (!code) return;

      const success = (typeof copyToClipboard === 'function')
        ? await copyToClipboard(code)
        : false;

      if (success) {
        if (typeof showToast === 'function') {
          showToast(`Codice #${code} copiato negli appunti!`, 'success');
        }
        this._flashBtnSuccess(btnEl || document.getElementById('jam-btn-copy-code'), 'Copiato!');
      } else {
        if (typeof scPrompt === 'function') {
          scPrompt('Copia il codice della stanza:', code);
        } else if (typeof showToast === 'function') {
          showToast(`Codice: ${code}`, 'info');
        }
      }
    },

    async copyQuickLink(btnEl) {
      const url = this.getQuickLink();
      if (!url) return;

      const success = (typeof copyToClipboard === 'function')
        ? await copyToClipboard(url)
        : false;

      if (success) {
        if (typeof showToast === 'function') {
          showToast('Link di invito copiato negli appunti!', 'success');
        }
        this._flashBtnSuccess(btnEl || document.getElementById('jam-btn-copy-link'), 'Link Copiato!');
      } else {
        if (typeof scPrompt === 'function') {
          scPrompt('Copia questo link di invito e invialo al tuo amico:', url);
        } else if (typeof showToast === 'function') {
          showToast(`Link: ${url}`, 'info');
        }
      }
    },

    async shareLink(btnEl) {
      const url = this.getQuickLink();
      if (!url) return;

      if (navigator.share) {
        try {
          await navigator.share({
            title: 'JAM Watch Party - FilmViewer',
            text: `Unisciti alla mia stanza JAM #${this.state.roomCode} per guardare insieme in sincronia!`,
            url: url,
          });
          return;
        } catch (err) {
          if (err.name !== 'AbortError') {
            console.warn('[JAM] Web Share failed, copying instead:', err);
          } else {
            return;
          }
        }
      }

      await this.copyQuickLink(btnEl);
    },

    _flashBtnSuccess(btn, tempText = 'Copiato!') {
      if (!btn) return;
      const originalHtml = btn.dataset.origHtml || btn.innerHTML;
      btn.dataset.origHtml = originalHtml;
      btn.innerHTML = `<i class="ti ti-check me-1"></i>${escapeHtml(tempText)}`;
      btn.classList.add('btn-success');
      btn.classList.remove('btn-outline-primary', 'btn-outline-secondary', 'btn-primary');
      setTimeout(() => {
        btn.innerHTML = originalHtml;
        btn.classList.remove('btn-success');
        if (btn.id === 'jam-btn-copy-code') {
          btn.classList.add('btn-outline-primary');
        } else if (btn.id === 'jam-btn-copy-link') {
          btn.classList.add('btn-primary');
        } else if (!btn.classList.contains('jam-code-display')) {
          btn.classList.add('btn-outline-primary');
        }
      }, 2000);
    },

    openJamSettings() {
      const streamModal = document.getElementById('stream-player-modal');
      const playerModal = document.getElementById('player-modal');
      const inStream = streamModal && (streamModal.classList.contains('show') || streamModal.style.display === 'block');
      const inPlayer = playerModal && (playerModal.classList.contains('show') || playerModal.style.display === 'block');

      if (inStream || inPlayer) {
        this.openQuickModal();
        return;
      }

      this.openFullSettings();
    },

    openQuickModal() {
      this.renderQuickModal();
      if (typeof showModal === 'function') {
        showModal('jam-quick-modal');
      }
    },

    openFullSettings() {
      if (typeof hideModal === 'function') {
        hideModal('jam-quick-modal');
      }
      if (typeof openSettingsPage === 'function') {
        openSettingsPage('jam');
      } else if (typeof openSettings === 'function') {
        openSettings();
        setTimeout(() => {
          if (typeof switchSettingsTab === 'function') switchSettingsTab('jam');
        }, 50);
      }
    },

    renderQuickModal() {
      const container = document.getElementById('jam-quick-modal-body');
      if (!container) return;

      const isLive = this.isActive();
      const code = this.state.roomCode;
      const codeFormatted = code ? `${code.slice(0, 3)} ${code.slice(3)}` : '';
      const quickLink = this.getQuickLink();
      const peerCount = this.state.peers.size;

      if (!isLive) {
        container.innerHTML = `
          <div class="text-center py-3">
            <div class="mb-3 d-inline-flex p-3 rounded-circle" style="background:rgba(61,107,245,0.12);">
              <i class="ti ti-headphones text-primary fs-1"></i>
            </div>
            <h4 class="text-white fw-bold mb-2">JAM Watch Party non attiva</h4>
            <p class="text-muted small mb-4">
              Crea una stanza o entra con un codice a 6 cifre per sincronizzare il film con il tuo amico.
            </p>
            <div class="d-flex gap-2 justify-content-center">
              <button type="button" class="btn btn-primary" data-action="jam:create">
                <i class="ti ti-sparkles me-1"></i>Crea nuova Stanza
              </button>
              <button type="button" class="btn btn-outline-secondary" data-action="jam:openFullSettings">
                Impostazioni JAM
              </button>
            </div>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div class="mb-3 p-3 rounded text-center" style="background:linear-gradient(135deg, rgba(61,107,245,0.15), rgba(16,21,31,0.95)); border:1px solid var(--accent-ring);">
          <span class="badge bg-purple-lt mb-1"><i class="ti ti-broadcast me-1"></i>SESSIONE ATTIVA</span>
          <div class="d-flex align-items-center justify-content-center gap-2 my-1">
            <span class="text-white fw-bold font-monospace jam-code-display" data-action="jam:copyCode" title="Clicca per copiare il codice" style="font-size:32px; letter-spacing:4px; cursor:pointer;">
              #${codeFormatted}
            </span>
            <button type="button" class="btn btn-sm btn-outline-primary" data-action="jam:copyCode" title="Copia codice">
              <i class="ti ti-copy me-1"></i>Copia Codice
            </button>
          </div>
          <small class="text-muted d-block mt-1">
            <span class="jam-dot ${peerCount > 0 ? 'online' : 'waiting'} me-1"></span>
            ${peerCount > 0 ? `Connesso con ${peerCount === 1 ? '1 amico' : peerCount + ' amici'}` : 'In attesa dell\'amico... Invia il codice o il link per farlo unire!'}
          </small>
        </div>

        <div class="mb-3 p-3 rounded" style="background:rgba(255,255,255,0.02); border:1px solid var(--border);">
          <label class="form-label text-white small fw-bold mb-1">
            <i class="ti ti-link me-1 text-primary"></i>Link rapido di invito:
          </label>
          <div class="input-group input-group-sm mb-1">
            <input type="text" readonly class="form-control bg-dark text-white border-secondary font-monospace"
                   value="${quickLink}" onclick="this.select()" style="font-size:12px;">
            <button type="button" class="btn btn-primary" data-action="jam:copyLink">
              <i class="ti ti-copy me-1"></i>Copia
            </button>
            <button type="button" class="btn btn-outline-light" data-action="jam:shareLink" title="Condividi">
              <i class="ti ti-share me-1"></i>Condividi
            </button>
          </div>
          <small class="text-muted" style="font-size:11px;">Invia questo link al tuo amico per farlo entrare istantaneamente.</small>
        </div>

        <div class="d-flex gap-2">
          <button type="button" class="btn btn-outline-primary flex-fill" data-action="jam:forceSync">
            <i class="ti ti-refresh me-1"></i>Forza Sincro
          </button>
          <button type="button" class="btn btn-outline-danger" data-action="jam:leave">
            <i class="ti ti-logout me-1"></i>Esci dalla stanza
          </button>
        </div>
      `;
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
                  Ciascuno esegue il proprio container Docker in locale (es. Londra e Stoccarda): nessuna porta da aprire sul router, basta un codice a 6 cifre o un link rapido.
                </p>
              </div>
            </div>
          </div>

          ${pending ? `
            <div class="alert alert-info d-flex flex-wrap align-items-center justify-content-between gap-3 p-3 mb-4" style="background:rgba(61,107,245,0.15); border:1px solid var(--accent-ring); border-radius:12px;">
              <div class="d-flex align-items-center gap-3">
                <div class="p-2 rounded-circle" style="background:rgba(61,107,245,0.25);">
                  <i class="ti ti-mail-opened fs-2 text-primary"></i>
                </div>
                <div>
                  <h4 class="text-white fw-bold mb-1">Invito a stanza JAM ricevuto!</h4>
                  <p class="text-muted small mb-0">Sei stato invitato a unirti alla sessione <strong class="text-white font-monospace">#${pending}</strong>.</p>
                </div>
              </div>
              <button type="button" class="btn btn-success fw-bold px-3 py-2" data-action="jam:joinAuto" data-code="${pending}">
                <i class="ti ti-arrows-join me-1"></i>Entra Subito (#${pending})
              </button>
            </div>
          ` : ''}

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
      const quickLink = this.getQuickLink();

      container.innerHTML = `
        <!-- Active Room Header Card -->
        <div class="card mb-4" style="background:linear-gradient(135deg, rgba(61,107,245,0.12), rgba(16,21,31,0.95)); border:1px solid var(--accent-ring); border-radius:12px;">
          <div class="card-body p-4">
            <div class="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-3">
              <div>
                <span class="badge bg-purple-lt mb-2">
                  <i class="ti ti-broadcast me-1"></i>SESSIONE ATTIVA
                </span>
                <div class="d-flex align-items-center gap-2 flex-wrap">
                  <span class="text-white fw-bold font-monospace m-0 jam-code-display" data-action="jam:copyCode" title="Clicca per copiare il codice" style="font-size:38px; letter-spacing:4px; cursor:pointer;">
                    #${codeFormatted}
                  </span>
                  <button type="button" class="btn btn-sm btn-outline-primary" id="jam-btn-copy-code" data-action="jam:copyCode" title="Copia codice a 6 cifre">
                    <i class="ti ti-copy me-1"></i>Copia Codice
                  </button>
                </div>
                <div class="text-muted small mt-2 d-flex align-items-center gap-2">
                  <span class="jam-dot ${peerCount > 0 ? 'online' : 'waiting'}"></span>
                  <span>${peerCount > 0 ? `Connesso con ${peerCount === 1 ? '1 amico' : peerCount + ' amici'}` : 'In attesa dell\'amico... Invia il codice o il link per farlo unire!'}</span>
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

            <!-- Quick Invite Box -->
            <div class="p-3 rounded" style="background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.08);">
              <label class="form-label text-white small fw-bold mb-1">
                <i class="ti ti-link me-1 text-primary"></i>Link rapido di invito per l'amico:
              </label>
              <div class="input-group input-group-sm mb-2">
                <input type="text" readonly class="form-control bg-dark text-white border-secondary font-monospace" id="jam-share-link-input"
                       value="${quickLink}" onclick="this.select()" title="Clicca per selezionare tutto" style="font-size:12px;">
                <button type="button" class="btn btn-primary fw-bold" id="jam-btn-copy-link" data-action="jam:copyLink">
                  <i class="ti ti-copy me-1"></i>Copia Link
                </button>
                <button type="button" class="btn btn-outline-light" id="jam-btn-share-link" data-action="jam:shareLink" title="Condividi">
                  <i class="ti ti-share me-1"></i>Condividi
                </button>
              </div>
              <p class="text-muted mb-0" style="font-size:11.5px;">
                <i class="ti ti-info-circle me-1"></i>Invia questo link al tuo amico: aprendolo entrerà istantaneamente nella sessione JAM senza dover digitare il codice a mano.
              </p>
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
