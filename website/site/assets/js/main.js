/*
  rhinvoice.com — the only script, two small helpers. Without it every page still works:
  - the "back to top" link appears once the reader has scrolled down a little (otherwise it
    is simply always there);
  - the language menu closes on Escape and on a click outside (otherwise with its button).
*/
(function () {
  "use strict";

  var link = document.querySelector(".to-top");
  if (!link) return;

  var THRESHOLD = 600;

  function update() {
    var shown = window.scrollY > THRESHOLD;
    link.setAttribute("data-shown", String(shown));
    // A hidden link must not be reachable with the keyboard either.
    if (shown) link.removeAttribute("tabindex");
    else link.setAttribute("tabindex", "-1");
  }

  window.addEventListener("scroll", update, { passive: true });
  update();
})();

(function () {
  "use strict";

  var menu = document.querySelector(".lang details");
  if (!menu) return;

  document.addEventListener("click", function (event) {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });

  menu.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || !menu.open) return;
    event.preventDefault();
    menu.open = false;
    menu.querySelector("summary").focus();
  });
})();
