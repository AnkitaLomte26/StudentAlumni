/* Shared presentation for the existing student/alumni profile endpoints. */
function initDashboard(role) {
  const isAlumni = role === "ALUMNI";
  const endpoint = "/api/profiles/" + (isAlumni ? "alumni" : "student") + "/me";
  const fields = ["branch", "graduation_year", ...(isAlumni ? [] : ["current_year"]), "bio"];
  const form = document.getElementById("profile-form");
  const fieldset = document.getElementById("profile-fields");
  const statusEl = document.getElementById("status");
  const loadStatus = document.getElementById("load-status");
  const retry = document.getElementById("retry-load");
  const logout = document.getElementById("logout");
  const validate = setupValidation(form);
  let loading = false;
  let profileLoaded = false;

  function handleError(error, target) {
    if (error.status === 401) {
      window.location.href = "login.html";
      return;
    }
    setStatus(target, error.message, "error");
  }

  function renderProfile(profile) {
    fields.forEach(key => {
      document.getElementById(key).value = profile[key] ?? "";
      document.getElementById("summary-" + key).textContent =
        profile[key] === null || profile[key] === undefined || String(profile[key]).trim() === ""
          ? (key === "bio" ? "Add a short introduction to tell your story." : "Not added yet")
          : String(profile[key]);
    });
    const completed = fields.filter(key => profile[key] !== null &&
      profile[key] !== undefined && String(profile[key]).trim() !== "").length;
    document.getElementById("profile-completion").value = completed;
    document.getElementById("completion-count").textContent = completed + " of " + fields.length;
    document.getElementById("completion-hint").textContent = completed === fields.length
      ? "Your background is complete. You can update it anytime."
      : "Add your background details to help others get to know you.";
    if (isAlumni) {
      const verification = document.getElementById("verification_status");
      verification.textContent = profile.verification_status;
      verification.dataset.status = profile.verification_status;
      const explanations = {
        PENDING: "Your alumni profile has not yet been verified.",
        VERIFIED: "Your college-alumni identity is verified. Employment is self-reported.",
        REJECTED: "Your alumni verification was not approved.",
      };
      document.getElementById("verification-help").textContent =
        explanations[profile.verification_status] || "Verification status unavailable.";
      document.getElementById("accepting_guidance_requests").checked = !!profile.accepting_guidance_requests;
      document.getElementById("guidance-status").textContent = profile.accepting_guidance_requests
        ? "Open to guidance requests" : "Not accepting requests";
    }
  }

  async function load() {
    if (loading) return;
    loading = true;
    fieldset.disabled = true;
    retry.hidden = true;
    setStatus(loadStatus, "Loading your profile…");
    try {
      const user = await api("/api/auth/me");
      if (user.role !== role) {
        redirectByRole(user.role);
        return;
      }
      document.getElementById("welcome-name").textContent = ", " + user.name;
      document.getElementById("profile-name").textContent = user.name;
      document.getElementById("user-info").textContent = user.email;
      document.getElementById("avatar").textContent =
        user.name.trim().split(/\s+/u).slice(0, 2).map(part => Array.from(part)[0]).join("").toUpperCase();
      const account = document.getElementById("account-status");
      account.textContent = user.account_status;
      account.dataset.status = user.account_status;
      renderProfile(await api(endpoint));
      profileLoaded = true;
      fieldset.disabled = false;
      setStatus(loadStatus, "");
    } catch (error) {
      handleError(error, loadStatus);
      retry.hidden = error.status === 401;
    } finally {
      loading = false;
    }
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!profileLoaded || form.dataset.busy === "true" || !validate()) return;
    const payload = {};
    fields.forEach(key => {
      const value = document.getElementById(key).value.trim();
      payload[key] = value === "" ? null :
        (key === "graduation_year" || key === "current_year" ? Number(value) : value);
    });
    if (isAlumni) payload.accepting_guidance_requests =
      document.getElementById("accepting_guidance_requests").checked;
    setFormBusy(form, true, "Saving profile…");
    fieldset.disabled = true;
    setStatus(statusEl, "Saving your changes…");
    try {
      const profile = await api(endpoint, { method: "PUT", body: JSON.stringify(payload) });
      renderProfile(profile);
      setStatus(statusEl, "Profile saved. Your summary is up to date.", "success");
    } catch (error) {
      handleError(error, statusEl);
    } finally {
      fieldset.disabled = false;
      setFormBusy(form, false);
    }
  });

  logout.addEventListener("click", async () => {
    if (logout.disabled) return;
    logout.disabled = true;
    logout.textContent = "Logging out…";
    try {
      await api("/api/auth/logout", { method: "POST" });
      window.location.href = "login.html";
    } catch (error) {
      if (error.status === 401) {
        window.location.href = "login.html";
        return;
      }
      setStatus(loadStatus, "Could not log out. Please try again. " + error.message, "error");
      logout.disabled = false;
      logout.textContent = "Log out";
    }
  });
  retry.addEventListener("click", load);
  load();
}
