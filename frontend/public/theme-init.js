// Applies the stored colour scheme before the first paint to avoid a flash.
// Kept as an external file because the Content-Security-Policy forbids inline scripts.
(function () {
  var preference = "system";
  try {
    preference = localStorage.getItem("rhinvoice.theme") || "system";
  } catch (error) {
    // Storage unavailable: follow the system setting.
  }
  var dark =
    preference === "dark" ||
    (preference === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
})();
