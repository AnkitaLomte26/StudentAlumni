document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("register-form");
  const studentFields = document.getElementById("student-fields");
  const alumniFields = document.getElementById("alumni-fields");
  const statusEl = document.getElementById("status");
  const validate = setupValidation(form);
  const selectedRole = () => form.querySelector('input[name="role"]:checked').value;

  function syncRoleFields() {
    const isStudent = selectedRole() === "STUDENT";
    studentFields.hidden = !isStudent;
    alumniFields.hidden = isStudent;
    studentFields.querySelectorAll("input").forEach(input => { input.disabled = !isStudent; });
    alumniFields.querySelectorAll("input").forEach(input => { input.disabled = isStudent; });
    form.querySelector('button[type="submit"]').textContent =
      isStudent ? "Create student account" : "Create alumni account";
    // Remove errors belonging to the now inactive role.
    form.querySelectorAll("input:disabled").forEach(input => {
      input.removeAttribute("aria-invalid");
      const error = document.getElementById(input.id + "-error");
      if (error) error.textContent = "";
    });
  }
  form.querySelectorAll('input[name="role"]').forEach(input => input.addEventListener("change", syncRoleFields));
  syncRoleFields();

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (form.dataset.busy === "true" || !validate()) return;
    const payload = {
      name: document.getElementById("name").value.trim(),
      email: document.getElementById("email").value.trim(),
      password: document.getElementById("password").value,
      role: selectedRole(),
      branch: document.getElementById("branch").value.trim() || null,
      graduation_year: document.getElementById("graduation_year").value
        ? Number(document.getElementById("graduation_year").value) : null,
      bio: document.getElementById("bio").value.trim() || null,
    };
    if (payload.role === "STUDENT") {
      payload.current_year = document.getElementById("current_year").value
        ? Number(document.getElementById("current_year").value) : null;
    } else {
      payload.accepting_guidance_requests = document.getElementById("accepting_guidance_requests").checked;
    }
    setFormBusy(form, true, "Creating account…");
    form.querySelectorAll('input[name="role"]').forEach(input => { input.disabled = true; });
    setStatus(statusEl, "Creating your account…");
    try {
      await api("/api/auth/register", { method: "POST", body: JSON.stringify(payload) });
      window.location.href = "login.html?registered=1";
    } catch (error) {
      setStatus(statusEl, error.message, "error");
    } finally {
      setFormBusy(form, false);
      form.querySelectorAll('input[name="role"]').forEach(input => { input.disabled = false; });
    }
  });
});
