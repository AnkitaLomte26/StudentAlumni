/* Session-authenticated Phase 4 screens; all account content uses textContent. */
(async function () {
  const kind = document.body.dataset.networkPage;
  const status = document.getElementById("page-status");
  let user, page = 1, totalPages = 0, loading = false;
  function confirmChange(message) {
    return new Promise(resolve => {
      const dialog = el("dialog");
      const title = el("h2", "Confirm change"); title.id = "confirm-title";
      dialog.setAttribute("aria-labelledby", title.id);
      dialog.append(title, el("p", message));
      const form = document.createElement("form"); form.method = "dialog";
      const cancel = el("button", "Keep unchanged", "secondary"); cancel.value = "cancel";
      const confirm = el("button", "Confirm change"); confirm.value = "confirm";
      form.className = "form-actions"; form.append(cancel, confirm); dialog.append(form);
      dialog.addEventListener("close", () => { const accepted = dialog.returnValue === "confirm"; dialog.remove(); resolve(accepted); }, {once:true});
      document.body.append(dialog); dialog.showModal(); cancel.focus();
    });
  }
  const date = value => value ? new Date(value).toLocaleString() : "Not connected yet";
  function badge(value) { const node = el("span", value, "badge"); node.dataset.status = value; return node; }
  function link(text, href) { const node = el("a", text, "button secondary"); node.href = href; return node; }
  function button(text, callback, target) {
    const node = el("button", text, "secondary");
    node.type = "button";
    node.addEventListener("click", () => action(node, target || status, callback));
    return node;
  }
  function basic(person) {
    const box = el("div");
    box.append(el("h3", person.name), el("p", [person.branch, person.graduation_year && "Class of " + person.graduation_year].filter(Boolean).join(" · "), "muted"), tags(person.skills));
    return box;
  }
  function localStatus(card) {
    const node = el("p", "", "status");
    node.setAttribute("role", "status"); node.setAttribute("aria-live", "polite");
    card.append(node); return node;
  }
  async function mutate(url, options = {}) {
    await api(url, {method: "PATCH", ...options});
    await load();
    setStatus(status, "Saved. Your list is up to date.", "success");
    status.tabIndex = -1; status.focus();
  }
  function requestCard(item) {
    const card = el("article", "", "card network-card");
    const peer = user.role === "STUDENT" ? item.alumni : item.student;
    card.append(badge(item.status), basic(peer), el("h3", item.guidance_area.name), el("p", item.message, "request-message"), el("p", "Sent " + date(item.created_at), "small muted"));
    if (item.cooldown_until) card.append(el("p", new Date(item.cooldown_until) > new Date() ? "You may request this alumni again after " + date(item.cooldown_until) + "." : "The rejection cooldown has ended.", "hint"));
    if (item.status === "CANCELLED") card.append(el("p", "Cancelled by the student or because the relationship was blocked.", "hint"));
    const actions = el("div", "", "form-actions"); card.append(actions);
    const feedback = localStatus(card);
    if (user.role === "ALUMNI") {
      actions.append(button("View student profile", async () => {
        const profile = await api("/api/guidance-requests/" + item.id + "/student-profile");
        const detail = document.getElementById("student-detail");
        detail.replaceChildren(basic(profile), el("p", profile.bio || "No introduction added."));
        document.getElementById("student-dialog").showModal();
      }, feedback));
    }
    if (item.status === "PENDING") {
      const actionsForRole = user.role === "STUDENT" ? [["Cancel request","cancel"]] : [["Accept request","accept"],["Reject request","reject"]];
      actionsForRole.forEach(([label, verb]) => actions.append(button(label, async () => {
        if (verb === "reject" && !await confirmChange("Reject this request? The student must wait 30 days before requesting you again.")) return;
        await mutate("/api/guidance-requests/" + item.id + "/" + verb);
      }, feedback)));
      actions.append(button("Block " + peer.name, async () => {
        if (!await confirmChange("Block this relationship and cancel the pending request?")) return;
        await mutate("/api/connections/block", {method:"POST", body:JSON.stringify({other_user_id:peer.user_id})});
      }, feedback));
    }
    return card;
  }
  function connectionCard(item) {
    const card = el("article", "", "card network-card");
    const peer = user.role === "STUDENT" ? item.alumni : item.student;
    card.append(badge(item.status), basic(peer), el("p", "Connected: " + date(item.connected_at), "small muted"));
    if (item.status !== "ACTIVE") card.append(el("p", "Updated " + date(item.updated_at), "small muted"));
    const actions = el("div", "", "form-actions"); card.append(actions);
    const feedback = localStatus(card);
    if (item.conversation_id) actions.append(link("View messages", "chat.html?conversation_id=" + item.conversation_id));
    else if (item.status === "ACTIVE") actions.append(link("Open conversation", "chat.html?connection_id=" + item.id));
    const options = item.status === "ACTIVE" ? ["disconnect","block"] : item.status === "DISCONNECTED" ? ["block"] : item.blocked_by_user_id === user.id ? ["unblock"] : [];
    if (item.status === "BLOCKED") card.append(el("p", item.blocked_by_user_id === user.id ? "You blocked this relationship. Unblocking leaves it disconnected." : "This relationship is blocked.", "hint"));
    options.forEach(verb => actions.append(button(verb[0].toUpperCase() + verb.slice(1), async () => {
      const explanation = verb === "block" ? "Block this relationship? New requests will be prevented and pending requests cancelled." : verb === "disconnect" ? "Disconnect? Your history will remain." : "Unblock? This will not automatically reconnect you.";
      if (!await confirmChange(explanation)) return;
      await mutate("/api/connections/" + item.id + "/" + verb);
    }, feedback)));
    return card;
  }
  function notificationCard(item) {
    const card = el("article", "", "card network-card");
    card.append(badge(item.is_read ? "READ" : "UNREAD"), el("h2", item.type === "MESSAGE_RECEIVED" ? "New message" : item.type === "REQUEST_RECEIVED" ? "New guidance request" : item.type === "REQUEST_ACCEPTED" ? "Request accepted" : "Request rejected"), el("p", item.message), el("p", date(item.created_at), "small muted"));
    const actions = el("div", "", "form-actions"); card.append(actions);
    const feedback = localStatus(card);
    actions.append(item.type === "MESSAGE_RECEIVED" ? link("View conversation", "chat.html?conversation_id=" + item.conversation_id) : link("View guidance requests", "requests.html"));
    if (!item.is_read) actions.append(button("Mark as read", () => mutate("/api/notifications/" + item.id + "/read"), feedback));
    return card;
  }
  async function load() {
    if (loading) return;
    loading = true;
    const list = document.getElementById("network-list");
    list.setAttribute("aria-busy","true");
    const refresh = document.getElementById("refresh"); refresh.disabled = true;
    const filter = document.getElementById("status-filter");
    if (filter) filter.disabled = true;
    try {
      const path = kind === "requests" ? "/api/guidance-requests/" + (user.role === "STUDENT" ? "my" : "incoming") : "/api/" + kind;
      const params = new URLSearchParams({page, page_size:12});
      if (filter && filter.value) params.set("status",filter.value);
      const data = await api(path + "?" + params);
      totalPages = data.total_pages;
      if (page > Math.max(1,totalPages)) { page = Math.max(1,totalPages); loading = false; return await load(); }
      const render = kind === "requests" ? requestCard : kind === "connections" ? connectionCard : notificationCard;
      list.replaceChildren(...data.items.map(render));
      if (!data.items.length) {
        const empty = el("section", "", "card empty-state");
        empty.append(el("h2", kind === "notifications" ? "You are all caught up." : "Nothing here yet."), el("p", kind === "requests" ? "Requests matching this status will appear here. Try another status to see your history." : kind === "connections" ? "Accepted guidance requests create connections. Try another status to see past relationships." : "New requests and responses will appear here."));
        if (user.role === "STUDENT") empty.append(link("Find alumni","find-alumni.html"));
        list.append(empty);
      }
      document.getElementById("list-summary").textContent = data.total_results + " results" + (kind === "requests" ? " · " + data.pending_count + (user.role === "STUDENT" ? " of " + data.pending_limit : "") + " pending" : kind === "notifications" ? " · " + data.unread_count + " unread" : "");
      document.getElementById("page-info").textContent = totalPages ? "Page " + page + " of " + totalPages : "No pages";
      document.getElementById("previous-page").disabled = page <= 1;
      document.getElementById("next-page").disabled = page >= totalPages;
    } finally { loading = false; list.setAttribute("aria-busy","false"); refresh.disabled = false; if (filter) filter.disabled = false; }
  }
  async function sendPage() {
    const id = Number(new URLSearchParams(location.search).get("alumni_id"));
    if (!Number.isSafeInteger(id) || id <= 0) throw new Error("Choose a verified alumni profile first.");
    const [alumni, areas] = await Promise.all([api("/api/alumni/" + id), api("/api/catalogs/guidance-areas")]);
    document.getElementById("recipient").append(basic(alumni));
    const select = document.getElementById("guidance-area");
    areas.forEach(area => { const option = el("option", area.name); option.value = area.id; select.append(option); });
    if (!alumni.accepting_guidance_requests) { setStatus(status,"This alumni is not accepting guidance requests right now.","error"); return; }
    document.getElementById("send-fields").disabled = false;
    const form = document.getElementById("send-form"), feedback = document.getElementById("send-status");
    form.addEventListener("submit", event => {
      event.preventDefault();
      const submit = form.querySelector('button[type="submit"]');
      action(submit, feedback, async () => {
        const message = document.getElementById("request-message").value.trim();
        if (!message) throw new Error("Enter a short message about the guidance you are looking for.");
        await api("/api/guidance-requests", {method:"POST", body:JSON.stringify({alumni_user_id:id,guidance_area_id:Number(select.value),message})});
        document.getElementById("send-fields").disabled = true;
        setStatus(feedback,"Request sent. You can follow its status in My Guidance Requests.","success");
        feedback.tabIndex = -1; feedback.focus();
      });
    });
  }
  try {
    pageLogout();
    user = await pageUser(kind === "send-request" ? "STUDENT" : null);
    if (!user) return;
    if (!["STUDENT","ALUMNI"].includes(user.role)) { redirectByRole(user.role); return; }
    document.getElementById("dashboard-link").href = user.role === "STUDENT" ? "student-dashboard.html" : "alumni-dashboard.html";
    document.getElementById("discovery-link").hidden = user.role !== "STUDENT";
    document.getElementById("network-content").hidden = false;
    setStatus(status,"");
    if (kind === "send-request") { await sendPage(); return; }
    const filter = document.getElementById("status-filter");
    if (kind === "requests" && user.role === "ALUMNI") filter.value = "PENDING";
    if (filter) filter.addEventListener("change", () => { page = 1; load().catch(error => showError(status,error)); });
    document.getElementById("refresh").addEventListener("click", () => { setStatus(status,""); load().catch(error => showError(status,error)); });
    ["previous-page","next-page"].forEach((id,index) => document.getElementById(id).addEventListener("click", () => {
      if (loading) return;
      page += index ? 1 : -1; load().catch(error => showError(status,error));
    }));
    await load();
  } catch (error) { showError(status,error); }
})();
