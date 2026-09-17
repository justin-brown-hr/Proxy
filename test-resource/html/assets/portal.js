(function () {
  function initials(name) {
    const parts = String(name || "U").trim().split(/\s+/).slice(0, 2);
    return parts.map((p) => p.charAt(0).toUpperCase()).join("") || "U";
  }

  function applySession(data) {
    const user = data.user || "usuario";
    const email = data.email || "—";
    const userEl = document.getElementById("user");
    const emailEl = document.getElementById("email");
    const chip = document.getElementById("user-chip");
    const chipName = document.getElementById("chip-name");
    const chipAvatar = document.getElementById("chip-avatar");
    if (userEl) userEl.textContent = user;
    if (emailEl) emailEl.textContent = email;
    if (chip && chipName && chipAvatar) {
      chipName.textContent = email !== "—" ? email : user;
      chipAvatar.textContent = initials(user);
      chip.classList.add("is-ready");
    }
  }

  fetch("/whoami")
    .then((r) => r.json())
    .then(applySession)
    .catch(() => applySession({ user: "usuario", email: "—" }));
})();
