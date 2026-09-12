document.addEventListener("DOMContentLoaded", async () => {
  const status = document.getElementById("page-status");
  const form = document.getElementById("search-form");
  const results = document.getElementById("search-results");
  const previous = document.getElementById("previous-page"), next = document.getElementById("next-page");
  let currentPage = 1, lastParams = new URLSearchParams(), busy = false;
  try {
    if (!await pageUser("STUDENT")) return;
    pageLogout();
    document.getElementById("search-content").hidden = false;
    const company = catalogLookup(document.getElementById("filter-company"), "companies", status);
    const skillPicker = filterPicker("filter-skills", "skills");
    const areaPicker = filterPicker("filter-areas", "guidance-areas");
    async function search(page = 1, newFilters = false) {
      if (busy) return;
      busy = true;
      form.querySelector('button[type="submit"]').disabled = true;
      previous.disabled = next.disabled = true;
      try {
        if (newFilters) {
          const params = new URLSearchParams();
          const selected = await company.get();
          if (selected) params.set("company_id", selected.id);
          for (const name of ["role","domain","branch","graduation_year_from","graduation_year_to","accepting_guidance_requests","page_size"]) {
            const value = form.elements[name].value.trim();
            if (value) params.set(name,value);
          }
          skillPicker.ids().forEach(id => params.append("skill_ids",id));
          areaPicker.ids().forEach(id => params.append("guidance_area_ids",id));
          lastParams = params;
        }
        results.setAttribute("aria-busy","true");
        setStatus(status, "Finding verified alumni…");
        const params = new URLSearchParams(lastParams); params.set("page",page);
        const data = await api("/api/alumni?" + params.toString());
        currentPage = data.page;
        results.replaceChildren();
        data.items.forEach(item => results.append(alumniCard(item, params.get("company_id"))));
        if (!data.items.length) {
          const empty = el("div", "", "card empty-state");
          empty.append(el("h2","No alumni match these filters."),el("p","Try fewer filters or a wider graduation-year range. Only approved college alumni appear here.","muted"));
          results.append(empty);
        }
        document.getElementById("result-count").textContent = data.total_results + (data.total_results === 1 ? " alumni profile" : " alumni profiles");
        document.getElementById("page-info").textContent = data.total_pages ? "Page " + data.page + " of " + data.total_pages : "No results";
        previous.disabled = data.page <= 1; next.disabled = data.page >= data.total_pages;
        setStatus(status, data.total_results + " matching alumni found.", "success");
      } catch(error) {
        results.replaceChildren();
        document.getElementById("result-count").textContent = "Results unavailable";
        document.getElementById("page-info").textContent = "";
        showError(status,error);
      } finally {
        busy = false; results.setAttribute("aria-busy","false");
        form.querySelector('button[type="submit"]').disabled = false;
      }
    }
    form.addEventListener("submit", event => { event.preventDefault(); search(1,true); });
    document.getElementById("reset-filters").addEventListener("click", () => {
      if (busy) return;
      form.reset(); company.clear(); skillPicker.clear(); areaPicker.clear(); search(1,true);
    });
    previous.addEventListener("click", () => search(currentPage - 1));
    next.addEventListener("click", () => search(currentPage + 1));
    await search(1,true);
  } catch(error) { showError(status,error); }

  function filterPicker(id,catalog) {
    const picker = catalogLookup(document.getElementById(id),catalog,status);
    const items = new Map();
    const list = document.getElementById(id + "-selected");
    function render() {
      list.replaceChildren(...[...items.values()].map(item => {
        const chip = el("span","","selected-chip"); chip.append(el("span",item.name));
        const remove = el("button","×"); remove.type="button"; remove.setAttribute("aria-label","Remove filter " + item.name);
        remove.addEventListener("click", () => {items.delete(item.id);render();});
        chip.append(remove); return chip;
      }));
    }
    document.getElementById(id + "-add").addEventListener("click", async () => {
      try {
        const item = await picker.get(true);
        if (items.size >= 20 && !items.has(item.id)) throw new Error("Choose up to 20 items.");
        items.set(item.id,item); picker.clear(); render();
      } catch(error) { showError(status,error); }
    });
    return {ids:()=>[...items.keys()],clear(){items.clear();picker.clear();render();}};
  }
});
