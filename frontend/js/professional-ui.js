/* Shared vanilla-JS controls. User content is always rendered as text. */
function el(tag, text = "", className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}
function showError(target, error) {
  if (error.status === 401) { window.location.href = "login.html"; return; }
  setStatus(target, error.message, "error");
}
async function pageUser(role) {
  const user = await api("/api/auth/me");
  if (role && user.role !== role) { redirectByRole(user.role); return null; }
  return user;
}
function pageLogout() {
  document.getElementById("logout").addEventListener("click", async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try { await api("/api/auth/logout", {method:"POST"}); window.location.href = "login.html"; }
    catch (error) { showError(document.getElementById("page-status"), error); button.disabled = false; }
  });
}
async function action(button, status, work) {
  if (button.disabled) return;
  button.disabled = true;
  const original = button.textContent;
  button.textContent = "Working…";
  setStatus(status, "");
  try { await work(); } catch (error) { showError(status, error); }
  finally { button.disabled = false; button.textContent = original; }
}
// Native datalist supplies keyboard/autocomplete behavior; only resolved catalog IDs are used.
function catalogLookup(input, catalog, status) {
  const list = document.createElement("datalist");
  list.id = input.id + "-options";
  input.setAttribute("list", list.id);
  input.autocomplete = "off";
  input.after(list);
  let options = [], selected = null, timer, revision = 0;
  async function load() {
    const version = ++revision;
    try {
      const items = await api("/api/catalogs/" + catalog + "?q=" + encodeURIComponent(input.value.trim()));
      if (version !== revision) return;
      options = items;
      list.replaceChildren(...items.map(item => { const option = document.createElement("option"); option.value = item.name; return option; }));
    } catch (error) { if (version === revision) showError(status, error); }
  }
  input.addEventListener("input", () => {
    selected = null;
    input.setCustomValidity("");
    revision++;
    clearTimeout(timer);
    timer = setTimeout(load, 180);
  });
  input.addEventListener("focus", load);
  load();
  return {
    async get(required = false) {
      const value = input.value.trim();
      if (selected && selected.name === value) return selected;
      clearTimeout(timer);
      await load();
      const found = options.find(item => item.name.toLowerCase() === value.toLowerCase());
      if (found) { selected = found; input.value = found.name; return found; }
      if (value || required) {
        input.setCustomValidity("Choose an item from the suggestions.");
        input.reportValidity();
        throw new Error("Choose an existing " + (catalog === "companies" ? "company" : "catalog item") + " from the suggestions.");
      }
      return null;
    },
    set(item) { selected = item; input.value = item ? item.name : ""; input.setCustomValidity(""); },
    clear() { this.set(null); },
  };
}
function tags(items, emptyText = "Not added yet") {
  const row = el("div", "", "tag-row");
  if (!items.length) row.append(el("span", emptyText, "muted small"));
  items.forEach(item => row.append(el("span", item.name, "tag")));
  return row;
}
function workCard(item) {
  const article = el("article", "", "work-item");
  article.append(el("h3", item.role + " · " + item.company.name));
  article.append(el("p", item.domain, "muted"));
  article.append(el("p", item.start_date + " — " + (item.end_date || "Present"), "small muted"));
  return article;
}
function alumniCard(item, companyId = null, detailed = false) {
  const article = el("article", "", "card alumni-result");
  const badge = el("span", "Verified college alumni", "badge");
  badge.dataset.status = "VERIFIED";
  article.append(badge, el(detailed ? "h1" : "h2", item.name));
  const relevant = item.work_experiences.find(w => w.company_id === Number(companyId)) || item.work_experiences[0];
  if (relevant) article.append(el("p", relevant.role + " @ " + relevant.company.name, "job-title"));
  if (companyId && relevant && item.company_relation) {
    article.append(el("p", (item.company_relation === "CURRENT" ? "Currently at " : "Previously at ") + relevant.company.name, "employment-match"));
  }
  const education = [item.branch, item.graduation_year ? "Class of " + item.graduation_year : ""].filter(Boolean).join(" · ");
  article.append(el("p", education || "Academic background not added", "muted small"));
  if (relevant) article.append(el("p", relevant.domain, "muted small"));
  article.append(el("h3", "Skills"), tags(item.skills), el("h3", "Guidance areas"), tags(item.guidance_areas));
  article.append(el("p", item.accepting_guidance_requests ? "Open to guidance requests" : "Not accepting guidance requests", "availability-line"));
  if (detailed) {
    article.append(el("h2", "About"), el("p", item.bio || "No introduction added yet."));
    article.append(el("h2", "Work experience"));
    if (!item.work_experiences.length) article.append(el("p", "No work experience added yet.", "muted"));
    item.work_experiences.forEach(work => article.append(workCard(work)));
    article.append(el("p", "Verification confirms college-alumni identity only. Employment and skills are self-reported. You can send a request when this alumni is accepting guidance requests.", "hint"));
  } else {
    const link = el("a", "View profile", "button secondary");
    link.href = "alumni-profile.html?id=" + item.user_id;
    link.setAttribute("aria-label", "View " + item.name + "'s profile");
    article.append(link);
  }
  if (item.accepting_guidance_requests) {
    const request = el("a", "Send guidance request", "button");
    request.href = "send-request.html?alumni_id=" + item.user_id;
    request.setAttribute("aria-label", "Send guidance request to " + item.name);
    article.append(request);
  }
  return article;
}
