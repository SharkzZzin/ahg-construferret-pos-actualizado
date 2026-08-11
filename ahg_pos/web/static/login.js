const form = document.querySelector("#login-form");
const errorBox = document.querySelector("#login-error");
const button = document.querySelector("#login-button");
const password = document.querySelector("#password");
const loadingScreen = document.querySelector("#loading-screen");
const accessDialog = document.querySelector("#access-dialog");
const identifier = document.querySelector("#identifier");
const setLoading = (visible) => loadingScreen?.classList.toggle("is-hidden", !visible);

function setLoginOpen(open) {
  accessDialog.hidden = !open;
  document.body.classList.toggle("dialog-open", open);
  if (open) {
    window.requestAnimationFrame(() => identifier.focus());
  }
}

window.addEventListener("load", () => setLoading(false));

document.querySelectorAll("[data-open-login]").forEach((trigger) => {
  trigger.addEventListener("click", () => setLoginOpen(true));
});

document.querySelectorAll("[data-close-login]").forEach((trigger) => {
  trigger.addEventListener("click", () => setLoginOpen(false));
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !accessDialog.hidden) setLoginOpen(false);
});

document.querySelector("#toggle-password").addEventListener("click", (event) => {
  const show = password.type === "password";
  password.type = show ? "text" : "password";
  event.currentTarget.textContent = show ? "Ocultar" : "Ver";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.textContent = "";
  setLoading(true);
  button.disabled = true;
  button.textContent = "Verificando...";
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        identifier: identifier.value,
        password: password.value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "No se pudo iniciar sesión.");
    window.location.assign("/");
  } catch (error) {
    errorBox.textContent = error.message;
  } finally {
    setLoading(false);
    button.disabled = false;
    button.textContent = "Acceder";
  }
});
