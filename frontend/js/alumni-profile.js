document.addEventListener("DOMContentLoaded", async () => {
  const status = document.getElementById("page-status");
  try {
    if (!await pageUser("STUDENT")) return;
    pageLogout();
    const id = Number(new URLSearchParams(location.search).get("id"));
    if (!Number.isInteger(id) || id <= 0) throw new Error("Choose an alumni profile from Find alumni.");
    const profile = await api("/api/alumni/" + id);
    document.title = profile.name + " | AlumniConnect";
    document.getElementById("public-profile").append(alumniCard(profile,null,true));
    setStatus(status,"");
  } catch(error) { showError(status,error); }
});
