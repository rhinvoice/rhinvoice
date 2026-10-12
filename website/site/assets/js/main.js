/*
  rhinvoice.com — the only script: the "back to top" link appears once the reader
  has scrolled down a little. Without the script the link is simply always there.
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
