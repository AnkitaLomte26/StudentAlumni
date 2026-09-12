const test = require("node:test");
const assert = require("node:assert/strict");
const {MessageWindow, LiveConversation} = require("../js/realtime.js");

test("POST/history and WebSocket copies of a message render once", () => {
  const window = new MessageWindow();
  window.reset([{id:1,content:"Persisted"}]);
  assert.equal(window.add({id:1,content:"Persisted"}), false);
  assert.equal(window.add({id:2,content:"New"}), true);
  assert.equal(window.add({id:2,content:"New"}), false);
  assert.deepEqual(window.values().map(m=>m.id), [1,2]);
});
test("out-of-order events sort chronologically and bound memory", () => {
  const window = new MessageWindow(3);
  [3,1,2,4].forEach(id=>window.add({id,content:String(id)}));
  assert.deepEqual(window.values().map(m=>m.id), [2,3,4]);
});
test("reconnect backs off and stops after five retries", () => {
  const saved = {socket:global.WebSocket, timer:global.setTimeout, clear:global.clearTimeout};
  const sockets=[], timers=[], delays=[];
  global.WebSocket=class { constructor(){sockets.push(this);} close(){} };
  global.setTimeout=(callback,delay)=>{const item={callback,delay};timers.push(item);delays.push(delay);return item;};
  global.clearTimeout=()=>{};
  try {
    const live=new LiveConversation("ws://example",()=>{},()=>{},()=>{});
    live.start(1);
    for(let i=0;i<6;i++){
      sockets.at(-1).onclose({code:1006});
      if(timers.length) timers.shift().callback();
    }
    assert.equal(sockets.length,6);
    assert.deepEqual(delays,[1000,2000,4000,8000,16000]);
    live.stop();
  } finally {global.WebSocket=saved.socket;global.setTimeout=saved.timer;global.clearTimeout=saved.clear;}
});
test("old conversation events and forbidden reconnects are ignored", () => {
  const original=global.WebSocket, sockets=[], events=[], statuses=[];
  global.WebSocket=class { constructor(){sockets.push(this);} close(){} };
  try {
    const live=new LiveConversation("ws://example",event=>events.push(event),s=>statuses.push(s),()=>{});
    live.start(1);const old=sockets[0];
    live.start(2);
    old.onmessage({data:JSON.stringify({type:"message.created",message:{id:1,conversation_id:1,content:"Old"}})});
    sockets[1].onmessage({data:JSON.stringify({type:"message.created",message:{id:2,conversation_id:2,content:"Current"}})});
    sockets[1].onclose({code:1008});
    assert.equal(events.length,1);
    assert.equal(events[0].conversation_id,2);
    assert.match(statuses.at(-1),/access ended/);
    live.stop();
  } finally {global.WebSocket=original;}
});

