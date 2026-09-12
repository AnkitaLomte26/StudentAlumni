/* REST persistence/history plus authenticated live delivery events. */
(async function () {
  const status = document.getElementById("page-status"), feedback = document.getElementById("chat-status");
  const list = document.getElementById("message-list"), input = document.getElementById("message-content");
  let user, current = null, detail = null, page = 1, snapshot = null, totalPages = 0;
  let listPage = 1, listPages = 0, busy = false;
  let totalMessages = 0, historyDirty = false;
  const drafts = new Map();
  const displayed = new MessageWindow(30), pendingEvents = new Map();
  let catchup = false, activityTimer = null;
  const live = new LiveConversation(WS_BASE, receiveLive, text => {
    document.getElementById("live-status").textContent = text;
  }, () => {
    catchup = true;
    if (!busy) recoverLive();
  });
  window.addEventListener("pagehide", () => { live.stop(); clearTimeout(activityTimer); });
  function renderMessages() {
    list.replaceChildren();
    displayed.values().forEach(item => {
      const own = item.sender_user_id === user.id;
      const li = el("li", "", "message-bubble" + (own ? " own-message" : ""));
      li.dataset.messageId = item.id;
      li.append(el("strong", own ? "You" : detail.other_participant.name, "message-author"), el("p", item.content, "message-text"));
      const time = el("time", formatDate(item.created_at), "small"); time.dateTime = item.created_at;
      li.append(time);
      if (own && item.read_at) li.append(el("span", " · Read", "small"));
      list.append(li);
    });
    if (!displayed.items.size) list.append(el("li", "No messages yet. A thoughtful hello is a good start.", "message-empty"));
  }
  function receiveLive(item) {
    if (item.conversation_id !== current) return;
    if (busy || !detail) {
      pendingEvents.set(item.id, item);
      if (pendingEvents.size > 100) { pendingEvents.delete(pendingEvents.keys().next().value); catchup = true; }
      return;
    }
    if (page !== 1) { setStatus(feedback,"New messages are available. Use Refresh to see the latest.","success"); return; }
    if (snapshot && item.id <= snapshot) return;
    if (!displayed.add(item)) return;
    const oldScroll = list.scrollTop, atBottom = list.scrollHeight - list.clientHeight - oldScroll < 60;
    renderMessages();
    list.scrollTop = atBottom ? list.scrollHeight : oldScroll;
    // Live arrivals start a new history snapshot; older pages use REST against it.
    historyDirty = true;
    totalPages = Math.ceil(++totalMessages / 30);
    document.getElementById("older-messages").disabled = page >= totalPages;
    document.getElementById("history-page").textContent = "Page " + page + " of " + totalPages;
    setStatus(feedback, item.sender_user_id === user.id ? "Message delivered." : "New message received.", "success");
    const id = current;
    clearTimeout(activityTimer);
    activityTimer = setTimeout(async () => {
      try {
        if (current !== id) return;
        if (document.visibilityState === "visible") await api("/api/conversations/" + id + "/read", {method:"PATCH",body:JSON.stringify({through_message_id:Math.max(...displayed.items.keys())})});
        if (current === id) await conversationList();
      } catch (error) { if (current === id) showError(feedback,error); }
    }, 350);
  }
  function recoverLive() {
    if (!catchup || busy || !current) return;
    catchup = false;
    if (page !== 1) { setStatus(feedback,"Live connection restored. Refresh when ready to see the latest messages."); return; }
    work(async () => { await history(true); await conversationList(); });
  }
  const formatDate = value => new Date(value).toLocaleString();
  function busyState(value) {
    busy = value;
    document.getElementById("refresh-chat").disabled = value;
    document.getElementById("composer").disabled = value || !detail || !detail.can_send;
    document.getElementById("older-messages").disabled = value || page >= totalPages;
    document.getElementById("newer-messages").disabled = value || page <= 1;
    document.getElementById("list-previous").disabled = value || listPage <= 1;
    document.getElementById("list-next").disabled = value || listPage >= listPages;
    document.querySelectorAll(".conversation-option").forEach(button => button.disabled = value);
    list.setAttribute("aria-busy", String(value));
  }
  async function work(callback) {
    if (busy) return;
    busyState(true);
    setStatus(feedback, "");
    try { await callback(); }
    catch (error) { showError(feedback, error); }
    finally {
      busyState(false);
      const queued = [...pendingEvents.values()]; pendingEvents.clear();
      queued.forEach(receiveLive);
      recoverLive();
    }
  }
  async function conversationList() {
    const data = await api("/api/conversations?page=" + listPage + "&page_size=12");
    listPages = data.total_pages;
    const holder = document.getElementById("conversation-list");
    holder.replaceChildren();
    data.items.forEach(item => {
      const button = el("button", "", "conversation-option secondary");
      button.type = "button";
      if (item.id === current) button.setAttribute("aria-current", "true");
      button.append(el("strong", item.other_participant.name), el("span", item.last_message_preview || "No messages yet", "conversation-preview"), el("span", item.connection_status + (item.unread_count ? " · " + item.unread_count + " unread" : ""), "small"));
      button.append(el("span", formatDate(item.updated_at), "small muted"));
      button.addEventListener("click", () => work(() => choose(item.id)));
      holder.append(button);
    });
    if (!data.items.length) holder.append(el("p", "No conversations yet. Open an active connection to begin.", "muted"));
    document.getElementById("list-page").textContent = listPages ? listPage + " / " + listPages : "0";
  }
  function renderDetail() {
    document.getElementById("chat-title").textContent = "Conversation with " + detail.other_participant.name;
    document.getElementById("chat-subtitle").textContent = [detail.other_participant.role, detail.other_participant.branch, detail.other_participant.graduation_year && "Class of " + detail.other_participant.graduation_year].filter(Boolean).join(" · ");
    document.getElementById("connection-notice").textContent = detail.connection_status === "DISCONNECTED" ? "This connection is disconnected. Previous messages remain available." : detail.connection_status === "BLOCKED" ? "Messaging is unavailable because this connection is blocked. Previous messages remain available." : !detail.can_send ? "Messaging is unavailable while a participant's account is inactive. Previous messages remain available." : "Connected · Replies appear live. You can also refresh to load saved messages.";
  }
  async function history(latest = false) {
    if (!current) return;
    if (latest) { page = 1; snapshot = null; }
    const params = new URLSearchParams({page, page_size:30});
    if (snapshot && !historyDirty) params.set("snapshot_id", snapshot);
    const [summary, data] = await Promise.all([api("/api/conversations/" + current), api("/api/conversations/" + current + "/messages?" + params)]);
    detail = summary; snapshot = data.snapshot_id; totalPages = data.total_pages;
    totalMessages = data.total_results; historyDirty = false;
    renderDetail();
    displayed.reset(data.items);
    renderMessages();
    document.getElementById("history-navigation").hidden = false;
    document.getElementById("history-page").textContent = totalPages ? "Page " + page + " of " + totalPages : "No messages";
    list.scrollTop = page === 1 ? list.scrollHeight : 0;
    // Viewing a page acknowledges received messages through the newest displayed ID.
    if (data.items.length) {
      await api("/api/conversations/" + current + "/read", {method:"PATCH", body:JSON.stringify({through_message_id:Math.max(...data.items.map(item => item.id))})});
    }
  }
  async function choose(id) {
    if (current) drafts.set(current, input.value);
    current = id; detail = null; page = 1; snapshot = null;
    pendingEvents.clear(); catchup = false;
    live.start(id);
    list.replaceChildren();
    document.getElementById("chat-title").textContent = "Loading conversation…";
    document.getElementById("chat-subtitle").textContent = "";
    input.value = drafts.get(id) || "";
    window.history.replaceState(null, "", "chat.html?conversation_id=" + id);
    await history(true);
    await conversationList();
  }
  try {
    pageLogout();
    user = await pageUser();
    if (!user) return;
    if (!["STUDENT","ALUMNI"].includes(user.role)) { redirectByRole(user.role); return; }
    document.getElementById("dashboard-link").href = user.role === "STUDENT" ? "student-dashboard.html" : "alumni-dashboard.html";
    document.getElementById("chat-content").hidden = false;
    setStatus(status, "");
    document.getElementById("refresh-chat").addEventListener("click", () => { live.retry(); work(async () => { await history(true); await conversationList(); setStatus(feedback,"Messages refreshed.","success"); }); });
    [["older-messages",1],["newer-messages",-1]].forEach(([id,delta]) => document.getElementById(id).addEventListener("click", () => work(async () => { page += delta; await history(); })));
    [["list-previous",-1],["list-next",1]].forEach(([id,delta]) => document.getElementById(id).addEventListener("click", () => work(async () => { listPage += delta; await conversationList(); })));
    document.getElementById("message-form").addEventListener("submit", event => {
      event.preventDefault();
      work(async () => {
        const content = input.value.trim();
        if (!content) { input.focus(); throw new Error("Enter a message before sending."); }
        try {
          await api("/api/conversations/" + current + "/messages", {method:"POST", body:JSON.stringify({content})});
        } catch (error) {
          if (error.status === 409) {
            detail = await api("/api/conversations/" + current);
            renderDetail();
          }
          throw error;
        }
        input.value = ""; drafts.delete(current);
        await history(true); await conversationList();
        setStatus(feedback,"Message sent.","success");
      });
    });
    await work(async () => {
      const params = new URLSearchParams(location.search);
      const connection = params.get("connection_id"), conversation = params.get("conversation_id");
      if (connection || conversation) {
        const id = Number(connection || conversation);
        if (!Number.isSafeInteger(id) || id <= 0) throw new Error("Choose a valid conversation from your connections.");
        if (connection) {
          const opened = await api("/api/connections/" + id + "/conversation", {method:"POST"});
          await choose(opened.id);
        } else await choose(id);
      } else await conversationList();
    });
  } catch (error) { showError(status,error); }
})();
