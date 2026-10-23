/* ===========================================================================
   EngineVerse — i18n (internationalisation)
   Client-side language switching for the UI chrome. Content (notes, problems,
   etc.) stays in the author's language but remains browsable everywhere.
   Zero dependencies, strict-CSP safe (loaded as an external script).
   =========================================================================== */

(function () {
  "use strict";

  var LOCALES_DIR = "/static/locales/";
  var AVAILABLE = {
    en: { name: "English", dir: "ltr" },
    es: { name: "Español", dir: "ltr" },
    hi: { name: "हिन्दी", dir: "ltr" },
    ar: { name: "العربية", dir: "rtl" },
    zh: { name: "中文", dir: "ltr" },
    fr: { name: "Français", dir: "ltr" },
    pt: { name: "Português", dir: "ltr" },
    bn: { name: "বাংলা", dir: "ltr" },
    ru: { name: "Русский", dir: "ltr" },
    ur: { name: "اردو", dir: "rtl" }
  };
  var DEFAULT = "en";
  var STORAGE_KEY = "ev:lang";

  var current = DEFAULT;
  var strings = {};
  var callbacks = [];

  /* ---------- load a locale JSON ---------- */
  function load(locale, done) {
    var url = LOCALES_DIR + locale + ".json";
    var xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.onload = function () {
      if (xhr.status === 200) {
        try {
          strings = JSON.parse(xhr.responseText);
          current = locale;
          document.documentElement.setAttribute("lang", strings.lang || locale);
          document.documentElement.setAttribute("dir", strings.dir || "ltr");
          applyTranslations();
          runCallbacks();
          if (done) done(null, strings);
        } catch (e) {
          if (done) done(e);
        }
      } else if (done) {
        done(new Error("Locale " + locale + " not found (" + xhr.status + ")"));
      }
    };
    xhr.onerror = function () {
      if (done) done(new Error("Failed to load locale " + locale));
    };
    xhr.send();
  }

  /* ---------- resolve saved preference ---------- */
  function resolveLocale() {
    var saved = "";
    try { saved = localStorage.getItem(STORAGE_KEY) || ""; } catch (e) {}
    if (saved && AVAILABLE[saved]) return saved;
    // Browser language hint (primary subtag only).
    var nav = (navigator.languages && navigator.languages[0]) ||
              navigator.language || navigator.userLanguage || "";
    var hint = nav.split("-")[0].toLowerCase();
    if (AVAILABLE[hint]) return hint;
    return DEFAULT;
  }

  /* ---------- apply data-i18n="key.path" to elements ---------- */
  function applyTranslations() {
    var root = strings.lang || current;
    var dir = strings.dir || "ltr";
    document.documentElement.setAttribute("lang", root);
    document.documentElement.setAttribute("dir", dir);
    document.documentElement.classList.remove("dir-ltr", "dir-rtl");
    document.documentElement.classList.add(dir === "rtl" ? "dir-rtl" : "dir-ltr");

    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      var value = lookup(strings, key);
      if (value === undefined) return;
      // Support {placeholders} like {site}, {n}.
      if (el.dataset.i18nArgs) {
        try {
          var args = JSON.parse(el.dataset.i18nArgs);
          Object.keys(args).forEach(function (k) {
            value = value.replace(new RegExp("\\{" + k + "\\}", "g"), args[k]);
          });
        } catch (e) {}
      }
      // If the element has a placeholder attribute and no text, fill placeholder.
      if (el.getAttribute("placeholder") && !el.textContent.trim()) {
        el.setAttribute("placeholder", value);
      } else {
        el.textContent = value;
      }
    });

    // Update document title if a page-title key exists.
    var titleKey = document.querySelector("[data-i18n-title]");
    if (titleKey) {
      var t = lookup(strings, titleKey.getAttribute("data-i18n-title"));
      if (t) document.title = t;
    }
  }

  function lookup(obj, path) {
    var parts = path.split(".");
    var cur = obj;
    for (var i = 0; i < parts.length; i++) {
      if (cur === null || cur === undefined || typeof cur !== "object") return undefined;
      cur = cur[parts[i]];
    }
    return cur;
  }

  function runCallbacks() {
    callbacks.forEach(function (cb) { cb(current, strings); });
    callbacks = [];
  }

  /* ---------- public API ---------- */
  window.EV = window.EV || {};
  window.EV.i18n = {
    available: AVAILABLE,
    current: function () { return current; },
    set: function (locale, done) {
      if (!AVAILABLE[locale]) {
        if (done) done(new Error("Unknown locale " + locale));
        return;
      }
      try { localStorage.setItem(STORAGE_KEY, locale); } catch (e) {}
      load(locale, done);
    },
    t: function (key) { return lookup(strings, key) || key; },
    dir: function () { return strings.dir || "ltr"; },
    onReady: function (cb) {
      if (current !== DEFAULT || Object.keys(strings).length > 0) {
        cb(current, strings);
      } else {
        callbacks.push(cb);
      }
    },
    init: function () {
      var saved = resolveLocale();
      load(saved);
      // Expose a tiny language picker builder.
      window.EV.i18n.picker = function (containerEl, labelKey) {
        if (!containerEl) return;
        containerEl.innerHTML = "";
        var label = document.createElement("label");
        label.textContent = lookup(strings, labelKey || "nav.home") || "Language";
        label.style.fontSize = ".78rem";
        label.style.color = "var(--muted)";
        label.style.marginRight = "6px";
        containerEl.appendChild(label);

        var select = document.createElement("select");
        select.setAttribute("aria-label", "Choose language");
        select.style.fontSize = ".82rem";
        select.style.padding = "4px 8px";
        select.style.borderRadius = "8px";
        select.style.border = "1px solid var(--edge)";
        select.style.background = "var(--surface)";
        select.style.color = "var(--text)";
        Object.keys(AVAILABLE).forEach(function (code) {
          var opt = document.createElement("option");
          opt.value = code;
          opt.textContent = AVAILABLE[code].name;
          if (code === current) opt.selected = true;
          select.appendChild(opt);
        });
        select.addEventListener("change", function () {
          window.EV.i18n.set(select.value);
        });
        containerEl.appendChild(select);
      };
    }
  };

  // Auto-init when DOM is ready.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", window.EV.i18n.init);
  } else {
    window.EV.i18n.init();
  }
})();
