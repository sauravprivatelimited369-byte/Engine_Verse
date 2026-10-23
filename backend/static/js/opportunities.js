/* Opportunities page: client-side filter by category, region and text.
 * Without JavaScript every card stays visible, grouped by category, so the
 * page is fully usable; this script only narrows what is shown. */
(function () {
  "use strict";
  var form = document.querySelector("[data-opp-filters]");
  if (!form) return;
  var cards = Array.prototype.slice.call(document.querySelectorAll("[data-opp-card]"));
  var groups = Array.prototype.slice.call(document.querySelectorAll("[data-opp-group]"));
  var catButtons = Array.prototype.slice.call(form.querySelectorAll("[data-opp-cat]"));
  var q = form.querySelector("#opp-q");
  var region = form.querySelector("#opp-region");
  var status = document.querySelector("[data-opp-status]");
  var empty = document.querySelector("[data-opp-empty]");
  var reset = document.querySelector("[data-opp-reset]");
  var category = "";

  form.hidden = false;

  // Allow deep links such as /opportunities?category=scholarship&region=india.
  try {
    var params = new URLSearchParams(window.location.search);
    if (params.get("category")) category = params.get("category");
    if (params.get("region")) region.value = params.get("region");
    if (params.get("q")) q.value = params.get("q");
  } catch (e) { /* URLSearchParams unsupported: ignore */ }
  if (!catButtons.some(function (b) { return b.getAttribute("data-opp-cat") === category; })) category = "";

  function apply() {
    var terms = (q.value || "").toLowerCase().trim().split(/\s+/).filter(Boolean);
    var reg = region.value;
    var shown = 0;
    cards.forEach(function (card) {
      var text = card.getAttribute("data-text") || "";
      var ok = (!category || card.getAttribute("data-cat") === category) &&
        (!reg || card.getAttribute("data-region") === reg) &&
        terms.every(function (t) { return text.indexOf(t) !== -1; });
      card.hidden = !ok;
      if (ok) shown++;
    });
    groups.forEach(function (g) {
      g.hidden = !g.querySelector("[data-opp-card]:not([hidden])");
    });
    catButtons.forEach(function (b) {
      var on = b.getAttribute("data-opp-cat") === category;
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.classList.toggle("accent", on);
    });
    if (empty) empty.hidden = shown !== 0;
    if (status) {
      status.textContent = shown === cards.length
        ? "Showing all " + shown + " opportunities."
        : "Showing " + shown + " of " + cards.length + " opportunities.";
    }
  }

  catButtons.forEach(function (b) {
    b.addEventListener("click", function () {
      category = b.getAttribute("data-opp-cat") || "";
      apply();
    });
  });
  q.addEventListener("input", apply);
  region.addEventListener("change", apply);
  form.addEventListener("submit", function (e) { e.preventDefault(); apply(); });
  if (reset) {
    reset.addEventListener("click", function () {
      category = ""; q.value = ""; region.value = "";
      apply();
      q.focus();
    });
  }
  apply();
})();
