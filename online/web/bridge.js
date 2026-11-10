/* Transport has no combat logic. Latest-state mailbox keeps slow renderers bounded. */
(function(root) {
'use strict';
class Bridge {
  constructor(options = {}) {
    this.WebSocket = options.WebSocket || root.WebSocket;
    this.location = options.location || root.location;
    this.storage = options.storage || root.sessionStorage;
    this.onState = options.onState || (() => {});
    this.onStatus = options.onStatus || (() => {});
    this.getOrientation = options.getOrientation || (() => (root.innerWidth >= root.innerHeight ? 'landscape' : 'portrait'));
    this.isHidden = options.isHidden || (() => root.document?.hidden === true);
    this.retryCount = 0; this.lastError = '';
    this.slot = 0; this.match = null; this.seq = 0; this.latest = '';
    this.welcomed = false; this.socket = null; this.generation = 0; this.code = ''; this.stopped = true;
    this.schedule = options.schedule || ((fn, ms) => setTimeout(fn, ms));
  }
  connect(code) {
    this.disconnect(); this.retryCount = 0; this.lastError = ''; this.stopped = false; this.code = code.toUpperCase().trim();
    this.open();
  }
  open() {
    const generation = ++this.generation;
    const scheme = this.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = this.socket = new this.WebSocket(`${scheme}//${this.location.host}/ws`);
    this.seq = 0; this.latest = ''; this.match = null; this.slot = 0; this.welcomed = false; this.onStatus('connecting');
    ws.onopen = () => {
      if (generation !== this.generation) return;
      let token = null;
      try { token = this.storage.getItem('llonline:' + this.code); } catch (_) {}
      ws.send(JSON.stringify({type:'hello', version:1, code:this.code, ...(token ? {token} : {})}));
    };
    ws.onmessage = e => {
      if (generation !== this.generation) return;
      let data; try { data = JSON.parse(e.data); } catch (_) { return; }
      if (data.type === 'welcome') {
        this.slot = data.slot; this.match = data.match_id; this.welcomed = true; this.retryCount = 0; this.lastError = '';
        try { this.storage.setItem('llonline:' + this.code, data.token); } catch (_) {}
        this.reportOrientation();
        if (this.isHidden()) this.action('suspend');
        this.onStatus('connected');
      } else if (data.type === 'state' && data.version === 1) {
        this.match = data.match_id; this.latest = JSON.stringify(data); this.onState(data);
      } else if (data.type === 'error') {
        const reason = data.code || data.error || '';
        this.lastError = reason;
        const terminal = ['room_full','invalid_token','invalid_room','protocol_version','bad_hello','room_code','wrong_room_code','invalid_reconnect_token','hello_required','unsupported_version','invalid_code'].includes(reason);
        if (terminal) { this.stopped = true; this.welcomed = false; }
        this.onStatus(terminal ? 'stopped' : 'error', data.message || reason || '请求失败');
      }
    };
    ws.onclose = () => {
      if (generation !== this.generation || this.stopped) return;
      this.welcomed = false; this.onStatus('disconnected');
      this.schedule(() => { if (!this.stopped && generation === this.generation) this.open(); }, Math.min(8000, 1500 * 2 ** Math.min(this.retryCount++, 3)));
    };
    ws.onerror = () => {};
  }
  resetRejectedToken(code) {
    // Only an explicit UI action for this exact rejected room can discard a credential.
    if (code !== this.code || this.lastError !== 'invalid_reconnect_token') return false;
    try { this.storage.removeItem('llonline:' + code); } catch (_) { return false; }
    this.connect(code); return true;
  }
  disconnect() { this.welcomed = false; this.stopped = true; this.generation++; if(this.socket) this.socket.close(); this.socket = null; }
  send(data) { if (!this.socket || this.socket.readyState !== 1) return false; this.socket.send(JSON.stringify(data)); return true; }
  input(dx, dy, shoot) { if (!this.welcomed) return false; return this.send({type:'input', seq:++this.seq, match_id:this.match, dx,dy,shoot}); }
  action(action,key) { if (!this.welcomed) return false; return this.send({type:'action',seq:++this.seq,match_id:this.match,action,...(key !== undefined ? {key} : {})}); }
  reportOrientation() { if (!this.welcomed) return false; return this.send({type:'orientation',orientation:this.getOrientation()}); }
  takeState() { const result = this.latest; this.latest = ''; return result; }
}
root.LLBridge = Bridge;
if (typeof module !== 'undefined') module.exports = Bridge;
})(typeof window === 'undefined' ? globalThis : window);
