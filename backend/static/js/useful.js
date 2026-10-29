/* ==========================================================================
   "Was this page useful?"

   The privacy rule is the whole point of this file: the request carries the
   route, a verdict and an optional note. It carries no identifier - no
   account, no cookie, no device id - because the server stores exactly what
   it is given and nothing else.

   The vote is sent with the page's CSRF token, which the server checks like
   any other write. Without JavaScript the buttons simply do nothing, so the
   widget is hidden until this file has wired it up.
   ========================================================================== */

(function () {
  "use strict";

  var cfg = window.EngineVerse || {};
  var root = document.querySelector("[data-ev-useful]");
  if (!root) return;

  var path = window.location.pathname;
  var kind = root.getAttribute("data-kind") || "page";
  var status = root.querySelector("[data-ev-useful-status]");
  var noteBox = root.querySelector("[data-ev-useful-note]");
  var detail = root.querySelector("[data-ev-useful-detail]");
  var yesBtn = root.querySelector("[data-ev-useful-yes]");
  var noBtn = root.querySelector("[data-ev-useful-no]");
  var sendBtn = root.querySelector("[data-ev-useful-send]");
  if (!yesBtn || !noBtn) return;

  function say(message) {
    if (status) status.textContent = message;
  }

  function post(body) {
    var headers = { "Content-Type": "application/json", "Accept": "application/json" };
    if (cfg.csrf) headers["X-CSRF-Token"] = cfg.csrf;
    return fetch("/api/content/feedback", {
      method: "POST",
      headers: headers,
      credentials: "same-origin",
      body: JSON.stringify(body)
    }).then(function (res) {
      return res.json().catch(function () { return {}; });
    });
  }

  function finish(verdict, note) {
    var body = { path: path, kind: kind, verdict: verdict };
    if (note) body.detail = note;
    return post(body).then(function (data) {
      if (data && data.ok && data.stored) {
        say("Thanks — that reached the people who write these pages.");
      } else {
        say("Sorry, that did not save. You can still email the site instead.");
      }
      root.setAttribute("data-ev-useful-done", "1");
      yesBtn.disabled = true;
      noBtn.disabled = true;
      if (noteBox) noteBox.hidden = true;
    }).catch(function () {
      say("That did not send. Check your connection and try again.");
    });
  }

  yesBtn.addEventListener("click", function () {
    finish("useful", "");
  });

  noBtn.addEventListener("click", function () {
    if (noteBox) {
      noteBox.hidden = false;
      if (detail) detail.focus();
    }
  });

  if (sendBtn) {
    sendBtn.addEventListener("click", function () {
      sendBtn.disabled = true;
      finish("not_useful", detail ? detail.value.trim() : "");
    });
  }

  root.hidden = false;
})();
