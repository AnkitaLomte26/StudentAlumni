document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("login-form");
  const statusEl = document.getElementById("status");
  const validate = setupValidation(form);
  if (new URLSearchParams(window.location.search).get("registered") === "1") {
    setStatus(statusEl, "Account created. Log in with your email and password.", "success");
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (form.dataset.busy === "true" || !validate()) return;
    setFormBusy(form, true, "Logging in…");
    setStatus(statusEl, "Checking your account…");
    try {
      const user = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: document.getElementById("email").value.trim(),
          password: document.getElementById("password").value,
        }),
      });
      redirectByRole(user.role);
    } catch (error) {
      setStatus(statusEl, error.message, "error");
    } finally {
      setFormBusy(form, false);
    }
  });
});
