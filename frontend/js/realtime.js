/* Bounded live delivery client. REST remains responsible for sending and history. */
class MessageWindow {
  constructor(limit = 30) { this.limit = limit; this.items = new Map(); }
  reset(items) { this.items = new Map(items.map(item => [item.id, item])); }
  add(item) {
    if (this.items.has(item.id)) return false;
    this.items.set(item.id, item);
    while (this.items.size > this.limit) this.items.delete(Math.min(...this.items.keys()));
    return true;
  }
  values() { return [...this.items.values()].sort((a,b) => a.id-b.id); }
}
class LiveConversation {
  constructor(base, onMessage, onStatus, onReady) {
    Object.assign(this,{base,onMessage,onStatus,onReady});
    this.socket = null; this.timer = null; this.stableTimer = null; this.attempt = 0; this.generation = 0;
  }
  start(id) {
    this.stop(); this.id = id; this.attempt = 0;
    this.connect(this.generation);
  }
  stop() {
    this.generation++;
    clearTimeout(this.timer); clearTimeout(this.stableTimer);
    if (this.socket) { const old = this.socket; this.socket = null; old.onclose = null; old.close(); }
  }
  retry() { if (this.id) this.start(this.id); }
  connect(generation) {
    if (generation !== this.generation) return;
    this.onStatus(this.attempt ? "Reconnecting…" : "Connecting…");
    const socket = new WebSocket(this.base + "/ws/conversations/" + this.id);
    this.socket = socket;
    socket.onmessage = event => {
      if (generation !== this.generation) return;
      let data;
      try { data = JSON.parse(event.data); } catch { return; }
      if (data.type === "ready") {
        this.onStatus("Live");
        this.stableTimer = setTimeout(() => { this.attempt = 0; }, 30000);
        this.onReady();
      } else if (data.type === "message.created" && data.message && Number.isSafeInteger(data.message.id) &&
                 data.message.conversation_id === this.id && typeof data.message.content === "string") {
        this.onMessage(data.message);
      }
    };
    socket.onerror = () => { if (generation === this.generation) this.onStatus("Live delivery unavailable; REST still works."); };
    socket.onclose = event => {
      clearTimeout(this.stableTimer);
      if (generation !== this.generation) return;
      this.socket = null;
      if (event.code === 1008) { this.onStatus("Live access ended. Refresh or sign in again."); return; }
      if (this.attempt >= 5) { this.onStatus("Offline · Use Refresh to reconnect."); return; }
      const delay = Math.min(30000, 1000 * 2 ** this.attempt++);
      this.onStatus("Disconnected · Reconnecting shortly…");
      this.timer = setTimeout(() => this.connect(generation), delay);
    };
  }
}
if (typeof module !== "undefined") module.exports = {MessageWindow, LiveConversation};

