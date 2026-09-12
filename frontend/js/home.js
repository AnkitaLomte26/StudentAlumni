document.addEventListener("DOMContentLoaded", () => {
  const button = document.getElementById("check-server");
  const statusEl = document.getElementById("status");
  if (!button) return;

  button.addEventListener("click", async () => {
    button.disabled = true;
    setStatus(statusEl, "Checking backend...");
    try {
      const data = await api("/health");
      if (data.status !== "ok") {
        throw new Error("Unexpected health response from the server.");
      }
      setStatus(statusEl, "Backend connected successfully", "success");
    } catch (error) {
      const detail =
        error instanceof TypeError
          ? "Could not reach the backend. Confirm FastAPI is running on http://localhost:8000."
          : error.message;
      setStatus(statusEl, "Backend connection failed: " + detail, "error");
    } finally {
      button.disabled = false;
    }
  });
});
