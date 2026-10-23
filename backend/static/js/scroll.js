/* ===========================================================================
   EngineVerse — home feed behaviour
   Reveal-on-scroll, animated counters, the study-plan ticks and a top bar that
   gets out of the way while you read.

   Deliberately NOT here any more (removed after learner feedback):
   - the fixed streak / level / XP bar that slid in over the content on every
     scroll — streak and XP already live in the top bar for signed-in learners,
     and covering the page with them helped nobody;
   - the floating "Keep exploring" pill and the random motivational toasts;
   - the demo streak number this file used to invent with Math.random().
   Nothing on the page may show progress a learner has not actually made.

   The top bar still carries the streak and level, but it now slides up on a
   downward scroll and returns the moment you scroll up, focus a control, or
   open the menu. Keyboard users therefore never lose it, and a reduced-motion
   preference pins it in place. Zero dependencies, strict-CSP safe.
   =========================================================================== */

(function () {
  "use strict";

  var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Tell the stylesheet that the reveal observer is alive; without this the
  // CSS failsafe reveals every section after 2.6s and the scroll animation is
  // lost for content reached later.
  document.documentElement.classList.add("ev-script-ready");

  /* ---------- scroll reveal ---------- */
  var revealEls = document.querySelectorAll(".ev-reveal");
  if (prefersReduced || !("IntersectionObserver" in window)) {
    revealEls.forEach(function (el) { el.classList.add("ev-show"); });
  } else {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("ev-show");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -10% 0px" });
    revealEls.forEach(function (el, index) {
      el.style.setProperty("--ev-delay", Math.min(index * 55, 220) + "ms");
      observer.observe(el);
    });
  }

  /* ---------- animated counters ---------- */
  function formatNumber(n) {
    return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  function countUp(el) {
    if (el.dataset.evDone === "1") return;
    el.dataset.evDone = "1";
    var target = parseInt(el.getAttribute("data-target"), 10) || 0;
    if (!target || prefersReduced) {
      el.textContent = formatNumber(target);
      return;
    }
    var duration = 1000;
    var startTime = performance.now();
    function frame(now) {
      var p = Math.min((now - startTime) / duration, 1);
      var ease = 1 - Math.pow(1 - p, 3);
      el.textContent = formatNumber(Math.floor(target * ease));
      el.classList.add("ev-counting");
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  var counterEls = document.querySelectorAll(".ev-count .n[data-target]");
  if ("IntersectionObserver" in window && !prefersReduced) {
    var counterObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) countUp(entry.target);
      });
    }, { threshold: 0.4, rootMargin: "0px 0px -10% 0px" });
    counterEls.forEach(function (el) { counterObserver.observe(el); });
  } else {
    counterEls.forEach(function (el) { countUp(el); });
  }

  /* ---------- topbar: depth, progress and auto-hide ---------- */
  var topbar = document.querySelector(".topbar");
  var progress = document.querySelector("[data-scroll-progress]");
  if (topbar) {
    var lastY = window.scrollY || window.pageYOffset || 0;
    var queued = false;

    var applyScroll = function () {
      queued = false;
      var y = window.scrollY || window.pageYOffset || 0;
      topbar.classList.toggle("is-scrolled", y > 8);

      if (progress) {
        var max = document.documentElement.scrollHeight - window.innerHeight;
        var pct = max > 0 ? Math.min(Math.max(y / max, 0), 1) : 0;
        progress.style.transform = "scaleX(" + pct + ")";
      }

      // Never hide the bar while a control inside it has focus (keyboard use)
      // or while the mobile/account panel is open. A pointer hovering the bar
      // is deliberately not an exception: that made the bar stick over the
      // page whenever the cursor rested near the top of the window.
      var busy = topbar.classList.contains("open") || topbar.contains(document.activeElement);
      if (prefersReduced || busy || y < 180) {
        topbar.classList.remove("is-hidden");
      } else {
        var delta = y - lastY;
        if (delta > 8) topbar.classList.add("is-hidden");
        else if (delta < -4) topbar.classList.remove("is-hidden");
      }
      lastY = y;
    };

    window.addEventListener("scroll", function () {
      if (queued) return;
      queued = true;
      requestAnimationFrame(applyScroll);
    }, { passive: true });
    window.addEventListener("resize", applyScroll, { passive: true });
    applyScroll();

    // Tabbing into the bar always brings it back.
    topbar.addEventListener("focusin", function () { topbar.classList.remove("is-hidden"); });
    // Opening the mobile panel or the account menu does too (app.js sets .open
    // on the header for the mobile panel; the menu focuses its own button).
    topbar.addEventListener("pointerdown", function () {
      if (topbar.classList.contains("is-hidden")) topbar.classList.remove("is-hidden");
    });
  }

  /* ---------- today's study plan tick-boxes ----------
     The learner's own ticks, kept on this device under today's date so the
     plan starts clean tomorrow. This is a checklist, not tracked progress:
     signing in is what records real streaks, XP and due cards. */
  var planBoxes = document.querySelectorAll("[data-plan-step]");
  if (planBoxes.length) {
    var summary = document.querySelector("[data-plan-summary]");
    var bar = document.querySelector("[data-plan-bar]");
    var progressbar = document.querySelector("[data-plan-progressbar]");
    var today = new Date();
    var key = "ev:today-plan:" + today.getFullYear() + "-" +
      String(today.getMonth() + 1).padStart(2, "0") + "-" +
      String(today.getDate()).padStart(2, "0");
    var done = {};
    try { done = JSON.parse(localStorage.getItem(key) || "{}") || {}; } catch (e) { done = {}; }
    var update = function () {
      var n = 0;
      planBoxes.forEach(function (box) {
        var on = !!done[box.getAttribute("data-plan-step")];
        box.checked = on;
        var card = box.closest("[data-plan-card]");
        if (card) card.classList.toggle("is-done", on);
        if (on) n++;
      });
      var pct = Math.round((n / planBoxes.length) * 100);
      if (bar) bar.style.width = pct + "%";
      if (progressbar) {
        progressbar.setAttribute("aria-valuenow", String(n));
        progressbar.setAttribute("aria-valuetext", n + " of " + planBoxes.length + " steps done");
      }
      if (summary) {
        summary.textContent = n === planBoxes.length
          ? "All " + planBoxes.length + " done — nice work today"
          : n + " of " + planBoxes.length + " done";
      }
    };
    planBoxes.forEach(function (box) {
      box.addEventListener("change", function () {
        done[box.getAttribute("data-plan-step")] = box.checked;
        try { localStorage.setItem(key, JSON.stringify(done)); } catch (e) { /* storage blocked */ }
        update();
      });
    });
    update();
  }
})();
