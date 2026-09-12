/* Small shared helpers for accessible validation and request feedback. */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-password-toggle]").forEach(button => {
    const input = document.getElementById(button.dataset.passwordToggle);
    if (!input) return;
    function setVisible(visible) {
      input.type = visible ? "text" : "password";
      button.setAttribute("aria-pressed", String(visible));
      button.setAttribute("aria-label", visible ? "Hide password" : "Show password");
      button.querySelector("[data-password-label]").textContent = visible ? "Hide" : "Show";
    }
    button.hidden = false;
    setVisible(false);
    button.addEventListener("click", () => setVisible(input.type === "password"));
    input.form?.addEventListener("reset", () => setVisible(false));
  });
});

function setupValidation(form) {
  // Keep native validation as a fallback when JavaScript is unavailable.
  form.noValidate = true;
  const fields = [...form.querySelectorAll("input:not([type=radio]):not([type=checkbox]), textarea")];
  function validate(field) {
    field.setCustomValidity("");
    if (field.id === "name" && field.value && field.value.trim().length < 2) {
      field.setCustomValidity("Enter a name with at least 2 characters.");
    }
    if (field.id === "password" && field.autocomplete === "new-password" && field.value) {
      if (field.value.length < 8 || !/\p{L}/u.test(field.value) || !/\p{N}/u.test(field.value)) {
        field.setCustomValidity("Use at least 8 characters, including a letter and a number.");
      }
    }
    const valid = field.disabled || field.validity.valid;
    const error = document.getElementById(field.id + "-error");
    if (error) error.textContent = valid ? "" : field.validationMessage;
    if (valid) field.removeAttribute("aria-invalid");
    else field.setAttribute("aria-invalid", "true");
    return valid;
  }
  fields.forEach(field => {
    field.addEventListener("blur", () => validate(field));
    field.addEventListener("input", () => {
      if (field.hasAttribute("aria-invalid")) validate(field);
    });
  });
  return () => {
    const invalid = fields.filter(field => !validate(field));
    if (invalid.length) {
      setStatus(document.getElementById("status"), "Please check the highlighted fields.", "error");
      invalid[0].focus();
    }
    return invalid.length === 0;
  };
}

function setFormBusy(form, busy, label) {
  const button = form.querySelector('button[type="submit"]');
  form.dataset.busy = String(busy);
  form.setAttribute("aria-busy", String(busy));
  if (busy) {
    button.dataset.originalLabel = button.innerHTML;
    button.textContent = label;
  } else if (button.dataset.originalLabel) {
    button.innerHTML = button.dataset.originalLabel;
  }
  button.disabled = busy;
}
