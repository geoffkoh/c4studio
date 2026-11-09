// Runs in <head>, before first paint, so a dark-mode reader never sees a
// flash of the light theme. The choice is a per-viewer convenience: if
// storage is unavailable the page follows the system setting.
(function () {
  try {
    var saved = localStorage.getItem("c4studio-theme");
    if (saved === "light" || saved === "dark") {
      document.documentElement.setAttribute("data-theme", saved);
    }
  } catch (e) {}
})();
