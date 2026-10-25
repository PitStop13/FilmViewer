"""Tests for the JAM Watch Party frontend integration.

Verifies:
1. Universal clipboard copy helper (copyToClipboard) exists and supports fallback.
2. JAM module defines required methods: copyRoomCode, copyQuickLink, shareLink,
   getQuickLink, setPendingCode, openQuickModal, openFullSettings.
3. Templates and modals include the JAM quick modal and all required action buttons.
4. Router routes #/settings/jam and #/jam with query parameters correctly.
5. Insecure HTTP context fallback execution passes without exceptions.
"""

from pathlib import Path
import re
import subprocess
import pytest


def test_jam_quick_modal_present_in_modals():
    modals = (Path(__file__).parent.parent / "app" / "templates" / "partials" / "_modals.html").read_text(encoding="utf-8")
    assert 'id="jam-quick-modal"' in modals
    assert 'id="jam-quick-modal-body"' in modals
    assert 'data-action="jam:openFullSettings"' in modals


def test_core_defines_copy_to_clipboard_and_session_preservation():
    core = (Path(__file__).parent.parent / "app" / "static" / "core.js").read_text(encoding="utf-8")
    assert "async function copyToClipboard(text)" in core
    assert "document.execCommand('copy')" in core
    assert "navigator.clipboard.writeText" in core
    assert "_preservePendingJamCode" in core


def test_router_handles_jam_and_params():
    router = (Path(__file__).parent.parent / "app" / "static" / "router.js").read_text(encoding="utf-8")
    assert "openSettingsPage(route.extra[0] || null, route.params)" in router
    assert "if (route.page === 'jam')" in router


def test_page_settings_preserves_jam_params():
    page_settings = (Path(__file__).parent.parent / "app" / "static" / "page-settings.js").read_text(encoding="utf-8")
    assert "async function openSettingsPage(tab, params = null)" in page_settings
    assert "window.Jam.setPendingCode" in page_settings
    assert "code: window.Jam.state.roomCode" in page_settings


def test_jam_proposal_elements_in_modals():
    modals = (Path(__file__).parent.parent / "app" / "templates" / "partials" / "_modals.html").read_text(encoding="utf-8")
    assert 'id="jam-proposal-modal"' in modals
    assert 'id="jam-proposal-nick"' in modals
    assert 'id="jam-proposal-title"' in modals
    assert 'data-action="jam:acceptProposal"' in modals
    assert 'data-action="jam:rejectProposal"' in modals
    assert 'id="stream-player-jam-overlay"' in modals
    assert 'id="stream-player-countdown-overlay"' in modals
    assert 'id="player-jam-overlay"' in modals
    assert 'id="player-countdown-overlay"' in modals


def test_jam_actions_registered():
    jam = (Path(__file__).parent.parent / "app" / "static" / "jam.js").read_text(encoding="utf-8")
    expected_actions = [
        "'jam:create'",
        "'jam:join'",
        "'jam:joinAuto'",
        "'jam:leave'",
        "'jam:forceSync'",
        "'jam:copyCode'",
        "'jam:copyLink'",
        "'jam:shareLink'",
        "'jam:openSettings'",
        "'jam:openFullSettings'",
        "'jam:acceptProposal'",
        "'jam:rejectProposal'",
        "'jam:startNow'",
        "'jam:cancelParty'",
        "'jam:toggleToasts'",
        "'jam:saveNickname'",
    ]
    for action in expected_actions:
        assert action in jam, f"Action {action} missing in jam.js"


def test_jam_node_runtime_simulation():
    """Runs a simulated DOM test in Node to ensure copyToClipboard and Jam methods execute."""
    node_test = """
    const assert = require('assert');

    // Simulate browser window & document in non-secure HTTP context
    let copiedText = null;
    let toastMessage = null;
    let toastType = null;

    global.window = {
      isSecureContext: false, // Insecure HTTP (e.g. LAN access)
      location: {
        origin: 'http://192.168.1.125:8000',
        pathname: '/',
        hash: '#/settings/jam?code=123456',
        search: ''
      }
    };
    global.navigator = {
      // clipboard is undefined in insecure context!
      userAgent: 'Mozilla/5.0'
    };
    global.localStorage = {
      _data: {},
      getItem(k) { return this._data[k] || null; },
      setItem(k, v) { this._data[k] = String(v); },
      removeItem(k) { delete this._data[k]; }
    };
    global.sessionStorage = {
      _data: {},
      getItem(k) { return this._data[k] || null; },
      setItem(k, v) { this._data[k] = String(v); },
      removeItem(k) { delete this._data[k]; }
    };
    global.document = {
      readyState: 'complete',
      addEventListener() {},
      removeEventListener() {},
      body: {
        appendChild(el) { this.child = el; },
        removeChild(el) { if (this.child === el) this.child = null; }
      },
      createElement(tag) {
        return {
          tagName: tag.toUpperCase(),
          style: {},
          value: '',
          setAttribute() {},
          focus() {},
          select() {},
          setSelectionRange() {},
          addEventListener() {},
          removeEventListener() {}
        };
      },
      execCommand(cmd) {
        if (cmd === 'copy') {
          copiedText = document.body.child ? document.body.child.value : '';
          return true;
        }
        return false;
      },
      getElementById(id) {
        return {
          id: id,
          innerHTML: '',
          dataset: {},
          style: {},
          classList: {
            add() {},
            remove() {},
            contains() { return false; }
          },
          closest() { return null; },
          addEventListener() {},
          removeEventListener() {}
        };
      }
    };
    global.showToast = function(msg, type) {
      toastMessage = msg;
      toastType = type;
    };
    global.escapeHtml = function(s) { return String(s); };

    // Extract copyToClipboard from core.js
    const fs = require('fs');
    const path = require('path');
    const coreCode = fs.readFileSync(path.join(__dirname, '../app/static/core.js'), 'utf-8');
    eval(coreCode.substring(coreCode.indexOf('async function copyToClipboard'), coreCode.indexOf('function escapeHtml')));

    (async () => {
      // 1. Test copyToClipboard in insecure context
      const res = await copyToClipboard('456789');
      assert.strictEqual(res, true, 'copyToClipboard should succeed via execCommand fallback');
      assert.strictEqual(copiedText, '456789', 'Text copied should match');

      // 2. Test Jam quick link generation
      const jamCode = fs.readFileSync(path.join(__dirname, '../app/static/jam.js'), 'utf-8');
      global.Paho = { MQTT: {} };
      global.registerActions = () => {};
      eval(jamCode);

      const jam = window.Jam;
      assert.ok(jam, 'Jam object should be defined on window');
      jam.state.roomCode = '654321';

      const link = jam.getQuickLink();
      assert.strictEqual(link, 'http://192.168.1.125:8000/#/settings/jam?code=654321');

      // 3. Test copyRoomCode
      await jam.copyRoomCode();
      assert.strictEqual(copiedText, '654321');
      assert.ok(toastMessage && toastMessage.includes('654321'));

      // 4. Test copyQuickLink
      await jam.copyQuickLink();
      assert.strictEqual(copiedText, link);
      assert.ok(toastMessage && toastMessage.includes('invito'));

      // 5. Test hasConnectedPeers()
      assert.strictEqual(jam.hasConnectedPeers(), false, 'Should have no connected peers initially');
      jam.state.connected = true;
      assert.strictEqual(jam.hasConnectedPeers(), false, 'Connected but 0 peers');

      jam.state.peers.set('peer_1', { nickname: 'Marco', isHost: false });
      assert.strictEqual(jam.hasConnectedPeers(), true, 'Should have connected peers when map not empty');

      // 6. Test proposeMedia
      let streamPlayerArgs = null;
      global.openStreamPlayer = (opts) => { streamPlayerArgs = opts; };

      const sentActions = [];
      jam.sendAction = (action, extra) => { sentActions.push({ action, extra }); };

      const proposed = jam.proposeMedia({
        type: 'movie',
        id: '123',
        slug: 'inception',
        title: 'Inception',
      });
      assert.strictEqual(proposed, true, 'proposeMedia should return true when active with peers');
      assert.ok(jam.state.activeProposal, 'Active proposal should be created');
      assert.strictEqual(sentActions.length, 1);
      assert.strictEqual(sentActions[0].action, 'PARTY_PROPOSAL');
      assert.strictEqual(sentActions[0].extra.media.title, 'Inception');
      assert.ok(streamPlayerArgs, 'openStreamPlayer should be called');
      assert.strictEqual(streamPlayerArgs._jamDirectPlay, true);
      assert.strictEqual(streamPlayerArgs._jamPendingParty, true);

      // 7. Test receiving PARTY_PROPOSAL as peer
      let shownModal = null;
      global.showModal = (m) => { shownModal = m; };
      let hiddenModal = null;
      global.hideModal = (m) => { hiddenModal = m; };

      jam._handleIncomingMessage(JSON.stringify({
        type: 'PARTY_PROPOSAL',
        clientId: 'peer_1',
        nickname: 'Marco',
        proposalId: 'prop_999',
        media: { type: 'movie', id: '456', title: 'Interstellar' }
      }));
      assert.ok(jam.state.incomingProposal, 'Incoming proposal should be recorded');
      assert.strictEqual(jam.state.incomingProposal.id, 'prop_999');
      assert.strictEqual(shownModal, 'jam-proposal-modal');

      // 8. Test acceptProposal
      sentActions.length = 0;
      jam.acceptProposal();
      assert.strictEqual(sentActions.length, 1);
      assert.strictEqual(sentActions[0].action, 'PARTY_RESPONSE');
      assert.strictEqual(sentActions[0].extra.accepted, true);
      assert.strictEqual(streamPlayerArgs._jamPendingParty, true);

      // 9. Test startNow sends PARTY_START
      sentActions.length = 0;
      jam.startNow();
      assert.ok(sentActions.some(a => a.action === 'PARTY_START'));
      assert.strictEqual(jam.state.countdownActive, true);

      console.log('ALL_FRONTEND_TESTS_PASSED');
      process.exit(0);
    })();
    """

    res = subprocess.run(["node", "-e", node_test], cwd=Path(__file__).parent, capture_output=True, text=True)
    assert res.returncode == 0, f"Node test failed: {res.stderr}\n{res.stdout}"
    assert "ALL_FRONTEND_TESTS_PASSED" in res.stdout


def test_stream_prepare_connection_error_recovery(monkeypatch):
    """Verifies prepare_stream auto-recovers when connection refused occurs on the old domain."""
    import asyncio
    from unittest.mock import MagicMock
    from fastapi import Request
    from app.routers import stream
    from app.core import domain_recovery

    recovered = [False]
    def fake_run_check(force=False):
        recovered[0] = True
        return {"applied": True, "candidate": "streamingcommunityz.build"}

    monkeypatch.setattr(domain_recovery, "run_check", fake_run_check)

    call_count = [0]
    async def mock_to_thread(fn, *args, **kwargs):
        if fn == domain_recovery.run_check:
            return fake_run_check(*args, **kwargs)
        # fn is _resolve inside prepare_stream
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Failed to establish a new connection: [WinError 10061] Connection refused")
        return "mock_token_123", None, None, None

    monkeypatch.setattr(asyncio, "to_thread", mock_to_thread)

    req = stream.StreamPrepareRequest(content_type="movie", id="100", slug="test")
    fake_request = MagicMock(spec=Request)
    fake_request.state = MagicMock()

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(stream.prepare_stream(req, fake_request))
        assert recovered[0] is True, "domain_recovery.run_check should have been triggered"
        assert res["stream_token"] == "mock_token_123"
        assert res["master_url"] == "/api/stream/hls/mock_token_123/master.m3u8"
    finally:
        loop.close()

