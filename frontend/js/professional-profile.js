document.addEventListener("DOMContentLoaded", async () => {
  const host = document.getElementById("professional");
  const pageStatus = document.getElementById("professional-status");
  try {
    const user = await pageUser(host.dataset.role);
    if (!user) return;
    host.hidden = false;
    await relations("skills", "/api/profiles/me/skills", "skills");
    if (user.role !== "ALUMNI") return;
    await relations("areas", "/api/profiles/alumni/me/guidance-areas", "guidance-areas");
    const workForm = document.getElementById("work-form");
    const workStatus = document.getElementById("work-status");
    const company = catalogLookup(document.getElementById("work-company"), "companies", workStatus);
    let editingId = null;
    const workList = document.getElementById("work-list");
    const fields = ["role","domain","start_date","end_date"];
    function resetWork() {
      workForm.reset(); company.clear(); editingId = null;
      document.getElementById("work-submit").textContent = "Add work experience";
      document.getElementById("work-cancel").hidden = true;
    }
    document.getElementById("work-cancel").addEventListener("click", resetWork);
    async function loadWork() {
      const items = await api("/api/profiles/alumni/me/work-experiences");
      workList.replaceChildren();
      if (!items.length) workList.append(el("p", "No work experience yet. Add your current or previous roles below.", "muted"));
      items.forEach(item => {
        const card = workCard(item);
        const actions = el("div", "", "button-row");
        const edit = el("button", "Edit " + item.company.name, "secondary"); edit.type = "button";
        edit.addEventListener("click", () => {
          editingId = item.id; company.set(item.company);
          fields.forEach(key => { document.getElementById("work-" + key).value = item[key] || ""; });
          document.getElementById("work-submit").textContent = "Save work experience";
          document.getElementById("work-cancel").hidden = false;
          document.getElementById("work-company").focus();
        });
        const remove = el("button", "Delete " + item.company.name, "secondary"); remove.type = "button";
        remove.addEventListener("click", () => action(remove, workStatus, async () => {
          await api("/api/profiles/alumni/me/work-experiences/" + item.id, {method:"DELETE"});
          if (editingId === item.id) resetWork();
          await loadWork(); setStatus(workStatus, "Work experience deleted.", "success");
        }));
        actions.append(edit, remove); card.append(actions); workList.append(card);
      });
    }
    workForm.addEventListener("submit", event => {
      event.preventDefault();
      action(document.getElementById("work-submit"), workStatus, async () => {
        const item = await company.get(true);
        const data = {company_id:item.id};
        fields.forEach(key => { data[key] = document.getElementById("work-" + key).value.trim() || null; });
        const id = editingId;
        await api("/api/profiles/alumni/me/work-experiences" + (id ? "/" + id : ""), {method:id?"PUT":"POST",body:JSON.stringify(data)});
        resetWork(); await loadWork(); setStatus(workStatus, "Work experience saved.", "success");
      }).then(() => { document.getElementById("work-submit").textContent = editingId ? "Save work experience" : "Add work experience"; });
    });
    await loadWork();
    const proofForm = document.getElementById("proof-form");
    const proofStatus = document.getElementById("proof-status");
    async function loadProof() {
      const data = await api("/api/profiles/alumni/me/verification");
      const badge = document.getElementById("proof-badge");
      badge.textContent = data.verification_status; badge.dataset.status = data.verification_status;
      proofForm.hidden = data.verification_status === "VERIFIED";
      document.getElementById("proof-info").textContent = data.verification_status === "VERIFIED"
        ? "Your college-alumni identity is approved. Your proof has been deleted."
        : data.rejection_reason ? "Not approved: " + data.rejection_reason + " Upload a new proof to request another review."
        : data.has_proof ? "Proof received. Awaiting administrator review. You may replace the submitted proof below."
        : "Upload a college ID to request verification and appear in student discovery.";
      const summary = document.getElementById("verification_status");
      summary.textContent = data.verification_status; summary.dataset.status = data.verification_status;
    }
    proofForm.addEventListener("submit", event => {
      event.preventDefault();
      action(document.getElementById("proof-submit"), proofStatus, async () => {
        const file = document.getElementById("proof-file").files[0];
        if (!file || file.size > 5 * 1024 * 1024) throw new Error("Choose a PNG, JPEG, or PDF of at most 5 MB.");
        const body = new FormData(); body.append("file",file);
        await api("/api/profiles/alumni/me/verification", {method:"POST",body});
        proofForm.reset(); await loadProof(); setStatus(proofStatus, "College ID submitted for review.", "success");
      });
    });
    await loadProof();
  } catch(error) { showError(pageStatus, error); }

  async function relations(prefix, endpoint, catalog) {
    const input = document.getElementById(prefix + "-input");
    const status = document.getElementById(prefix + "-status");
    const picker = catalogLookup(input, catalog, status);
    const form = document.getElementById(prefix + "-form");
    const list = document.getElementById(prefix + "-list");
    async function load() {
      const items = await api(endpoint);
      list.replaceChildren();
      if (!items.length) list.append(el("p", "Nothing added yet. Choose an item below.", "muted small"));
      items.forEach(item => {
        const chip = el("span", "", "selected-chip"); chip.append(el("span", item.name));
        const remove = el("button", "×"); remove.type = "button";
        remove.setAttribute("aria-label", "Remove " + item.name);
        remove.addEventListener("click", () => action(remove, status, async () => {
          await api(endpoint + "/" + item.id, {method:"DELETE"}); await load();
          setStatus(status, item.name + " removed.", "success");
        }));
        chip.append(remove); list.append(chip);
      });
    }
    form.addEventListener("submit", event => {
      event.preventDefault();
      action(form.querySelector("button"), status, async () => {
        const item = await picker.get(true);
        await api(endpoint + "/" + item.id, {method:"POST"});
        picker.clear(); await load(); setStatus(status, item.name + " added.", "success");
      });
    });
    await load();
  }
});
