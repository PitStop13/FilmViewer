(function () {
  "use strict";

  const form = document.getElementById("auth-form");
  const usernameInput = document.getElementById("auth-username");
  const passwordInput = document.getElementById("auth-password");
  const confirmGroup = document.getElementById("confirm-pwd-group");
  const confirmInput = document.getElementById("auth-password-confirm");
  const alertBox = document.getElementById("auth-alert");
  const setupBanner = document.getElementById("setup-banner");
  const title = document.getElementById("auth-title");
  const hint = document.getElementById("auth-hint");
  const submitBtn = document.getElementById("btn-submit");
  const btnText = document.getElementById("btn-text");
  const btnSpinner = document.getElementById("btn-spinner");

  let isSetupMode = false;

  function showAlert(message, isInfo) {
    if (!message) {
      alertBox.style.display = "none";
      alertBox.textContent = "";
      alertBox.className = "auth-alert";
      return;
    }
    alertBox.textContent = message;
    alertBox.className = isInfo ? "auth-alert info" : "auth-alert";
    alertBox.style.display = "block";
  }

  function setSubmitting(loading) {
    submitBtn.disabled = loading;
    btnSpinner.style.display = loading ? "inline-block" : "none";
    if (loading) {
      btnText.textContent = isSetupMode ? "Configurazione in corso..." : "Accesso in corso...";
    } else {
      btnText.textContent = isSetupMode ? "Crea account e Accedi" : "Accedi";
    }
  }

  async function checkStatus() {
    try {
      const res = await fetch("/api/auth/status");
      if (!res.ok) return;
      const data = await res.json();
      if (!data.setup_done) {
        isSetupMode = true;
        setupBanner.style.display = "block";
        confirmGroup.style.display = "block";
        confirmInput.required = true;
        title.textContent = "Crea account Admin";
        hint.textContent = "Imposta le credenziali del proprietario del server per iniziare.";
        btnText.textContent = "Crea account e Accedi";
        document.title = "Configurazione Iniziale - FilmViewer";
      } else {
        isSetupMode = false;
        setupBanner.style.display = "none";
        confirmGroup.style.display = "none";
        confirmInput.required = false;
        title.textContent = "Accedi";
        hint.textContent = "Inserisci le tue credenziali per accedere al pannello.";
        btnText.textContent = "Accedi";
        document.title = "Accedi - FilmViewer";
      }
    } catch (e) {
      console.warn("Could not check auth status", e);
    }
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    showAlert(null);

    const username = (usernameInput.value || "").trim();
    const password = (passwordInput.value || "").trim();

    if (!username) {
      showAlert("Inserisci il nome utente.");
      usernameInput.focus();
      return;
    }
    if (!password) {
      showAlert("Inserisci la password.");
      passwordInput.focus();
      return;
    }

    if (isSetupMode) {
      const confirmPwd = (confirmInput.value || "").trim();
      if (password.length < 4) {
        showAlert("La password deve contenere almeno 4 caratteri.");
        passwordInput.focus();
        return;
      }
      if (password !== confirmPwd) {
        showAlert("Le due password non corrispondono.");
        confirmInput.focus();
        return;
      }
    }

    setSubmitting(true);

    try {
      const endpoint = isSetupMode ? "/api/auth/setup" : "/api/auth/login";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const errorMsg = body.detail || (isSetupMode ? "Errore durante la configurazione" : "Nome utente o password non corretti");
        showAlert(errorMsg);
        setSubmitting(false);
        return;
      }

      // Success! Save user theme and redirect to home
      if (body && body.user && body.user.theme) {
        try { localStorage.setItem("sc_theme", body.user.theme); } catch (e) {}
      }
      window.location.href = "/";
    } catch (err) {
      showAlert("Errore di connessione con il server. Riprova tra poco.");
      setSubmitting(false);
    }
  });

  checkStatus();
})();
