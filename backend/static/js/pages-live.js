/* EngineVerse Live Browser Runtime + GitHub Learner Vault Sync + Multi-Language Code Judge.
 *
 * Powers the public GitHub Pages deployment and the Android APK without requiring
 * visitors to clone the repository or run a local server. Also syncs learner
 * profiles, XP, streaks, completed topics, and solved coding problems directly
 * with `authorsauravkushwaha/EngineVerse` (`data/learners/registry.json`).
 */
(() => {
  "use strict";

  const bootNode = document.getElementById("ev-live");
  if (!bootNode) return;

  let config = {};
  try {
    config = JSON.parse(bootNode.textContent || "{}");
  } catch (_) {
    return;
  }

  const BASE = config.base || "/";
  const GH_REPO = config.githubRepo || "authorsauravkushwaha/EngineVerse";
  const GH_VAULT_PATH = config.githubVaultPath || "data/learners/registry.json";
  const MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const STREAK_KEY = "ev:streak:v1";
  const STORE_KEY = "ev:learner-store:v2";

  const pad = (n) => (n < 10 ? "0" + n : String(n));
  const isoOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parseIso = (iso) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!m) return null;
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    return Number.isNaN(d.getTime()) ? null : d;
  };
  const dayIndex = (d) =>
    Math.floor(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / 86400000);
  const addDays = (d, delta) => {
    const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    copy.setDate(copy.getDate() + delta);
    return copy;
  };
  const longDate = (d) => `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  const shortDate = (d) => `${d.getDate()} ${SHORT_MONTHS[d.getMonth()]}`;
  const toast = (msg, kind = "ok") => {
    if (window.EV?.toast) window.EV.toast(msg, kind);
  };

  // ---------------------------------------------------------------------------
  // Shared helpers
  //
  // `escapeHtml` is published by app.js as window.EV.escapeHtml, but this file
  // must also work when it is loaded on its own (the Android wrapper and the
  // offline shell load scripts individually). An earlier revision called it
  // without ever defining it, so *every* call threw a ReferenceError: the OTP
  // code was never shown, the account icon was never inserted and the boot
  // sequence stopped half way. Keep a local definition and prefer the shared
  // one when app.js has already run.
  // ---------------------------------------------------------------------------
  const escapeHtml = (value) =>
    typeof window.EV?.escapeHtml === "function"
      ? window.EV.escapeHtml(value)
      : String(value ?? "").replace(/[&<>"']/g, (c) =>
          ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
        );

  // One control can have more than one accepted id: the exported markup and
  // this runtime ship independently, and a service-worker cache can pair an
  // older page with a newer script. Look up the current id first and fall back
  // to the spellings earlier exports used instead of binding nothing at all.
  const firstEl = (...ids) => {
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) return el;
    }
    return null;
  };

  const reportRuntimeProblem = (label, error) => {
    if (window.console?.warn) window.console.warn(`[EngineVerse] ${label} failed`, error);
  };

  // Runs one boot step in isolation: a failure on a single page must not take
  // the rest of the runtime (account icon, OTP steps, judges) down with it.
  const safely = (label, fn) => {
    try {
      const result = fn();
      if (result && typeof result.catch === "function") {
        result.catch((error) => reportRuntimeProblem(label, error));
      }
      return result;
    } catch (error) {
      reportRuntimeProblem(label, error);
      return undefined;
    }
  };

  // ---------------------------------------------------------------------------
  // SHA-256 helper (WebCrypto with pure-JS fallback) for GitHub Vault auth
  // ---------------------------------------------------------------------------
  async function sha256Hex(message) {
    const text = String(message || "");
    if (window.crypto?.subtle) {
      const buf = new TextEncoder().encode(text);
      const digest = await window.crypto.subtle.digest("SHA-256", buf);
      return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
    }
    // Minimal deterministic fallback if subtle is unavailable on non-HTTPS file://
    let h1 = 0xdeadbeef ^ text.length, h2 = 0x41c6ce57 ^ text.length;
    for (let i = 0; i < text.length; i++) {
      const ch = text.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    const hex = (h1 >>> 0).toString(16).padStart(8, "0") + (h2 >>> 0).toString(16).padStart(8, "0");
    return hex.repeat(4);
  }

  async function hashPasswordDigest(username, password) {
    const cleanUser = String(username || "").trim().toLowerCase();
    return sha256Hex(`engineverse-v1:${cleanUser}:${password}`);
  }

  // ---------------------------------------------------------------------------
  // Learner Store + Streak Store (localStorage + GitHub Vault Sync)
  // ---------------------------------------------------------------------------
  const readStreak = () => {
    try {
      const raw = JSON.parse(localStorage.getItem(STREAK_KEY) || "{}");
      const days = Array.isArray(raw.days)
        ? raw.days.filter((x) => typeof x === "string" && /^\d{4}-\d{2}-\d{2}$/.test(x))
        : [];
      return { days: Array.from(new Set(days)).sort() };
    } catch (_) {
      return { days: [] };
    }
  };

  const writeStreak = (days) => {
    const clean = Array.from(new Set(days)).sort();
    try {
      localStorage.setItem(STREAK_KEY, JSON.stringify({ days: clean }));
    } catch (_) {
      /* private mode */
    }
    return clean;
  };

  function defaultProfile(overrides = {}) {
    const todayIso = isoOf(new Date());
    return Object.assign({
      username: "guest",
      display_name: "EngineVerse Learner",
      email: "",
      phone: "",
      country_code: "+91",
      otp_verified: true,
      otp_channel: "email",
      branch: "cse",
      year_of_study: 1,
      bio: "Learning core engineering and programming on EngineVerse.",
      xp: 0,
      level: 1,
      // A new account has no study days yet. Showing "1" here invented a
      // streak before the learner had read a single page.
      streak_days: 0,
      longest_streak: 0,
      activity_days: [],
      completed_topics: [],
      solved_problems: [],
      completed_projects: [],
      bookmarks: [],
      quiz_attempts: 0,
      quiz_correct: 0,
      mistakes: [],
      community_posts: [],
      notifications: [
        { title: "Welcome to EngineVerse", body: "Full browser execution and GitHub learner vault sync are active.", ts: todayIso }
      ],
      password_sha256: "",
      updated_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    }, overrides);
  }

  // ---------------------------------------------------------------------------
  // Multi-Layer Synchronized Learner Database (localStorage + sessionStorage +
  // Cookie + window.name + IndexedDB + BroadcastChannel)
  //Inspired by Supabase Auth/Realtime & Appwrite Account/Databases persistence.
  // ---------------------------------------------------------------------------
  const SESSION_USER_KEY = "ev:session:user";
  const IDB_NAME = "EngineVerseVaultDB";
  const IDB_STORE = "kv";
  let authChannel = null;
  try {
    if (typeof BroadcastChannel !== "undefined") {
      authChannel = new BroadcastChannel("ev_auth_sync");
    }
  } catch (_) {}

  function readCookieUser() {
    try {
      const m = /(?:^|;\s*)ev_live_user=([^;\s]+)/.exec(document.cookie || "");
      return m ? decodeURIComponent(m[1]).trim().toLowerCase() : "";
    } catch (_) {
      return "";
    }
  }

  function writeCookieUser(username) {
    try {
      const clean = String(username || "").trim().toLowerCase();
      if (clean && clean !== "guest") {
        document.cookie = `ev_live_user=${encodeURIComponent(clean)}; path=/; max-age=2592000; SameSite=Lax`;
      } else {
        document.cookie = "ev_live_user=; path=/; max-age=0; SameSite=Lax";
      }
    } catch (_) {}
  }

  function idbWriteStore(store) {
    try {
      if (typeof indexedDB === "undefined") return;
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(IDB_STORE)) {
          db.createObjectStore(IDB_STORE);
        }
      };
      req.onsuccess = () => {
        try {
          const db = req.result;
          const tx = db.transaction(IDB_STORE, "readwrite");
          tx.objectStore(IDB_STORE).put(JSON.stringify(store), STORE_KEY);
        } catch (_) {}
      };
    } catch (_) {}
  }

  function idbRestoreIfNeeded(onRestored) {
    try {
      if (typeof indexedDB === "undefined") return;
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(IDB_STORE)) {
          db.createObjectStore(IDB_STORE);
        }
      };
      req.onsuccess = () => {
        try {
          const db = req.result;
          const tx = db.transaction(IDB_STORE, "readonly");
          const getReq = tx.objectStore(IDB_STORE).get(STORE_KEY);
          getReq.onsuccess = () => {
            if (!getReq.result) return;
            try {
              const idbStore = JSON.parse(getReq.result);
              const current = loadStore();
              let changed = false;
              if (idbStore.accounts && typeof idbStore.accounts === "object") {
                for (const [k, acc] of Object.entries(idbStore.accounts)) {
                  if (!current.accounts[k]) {
                    current.accounts[k] = acc;
                    changed = true;
                  }
                }
              }
              if (!current.currentUser && idbStore.currentUser && !sessionStorage.getItem("ev:explicit_logout")) {
                current.currentUser = idbStore.currentUser;
                changed = true;
              }
              if (changed) {
                saveStore(current, { skipBroadcast: true });
                if (typeof onRestored === "function") onRestored();
              }
            } catch (_) {}
          };
        } catch (_) {}
      };
    } catch (_) {}
  }

  function syncGlobalAuthFlag(currentUser) {
    const signedIn = Boolean(currentUser && currentUser !== "guest");
    if (signedIn) {
      document.documentElement.setAttribute("data-ev-signed-in", "true");
    } else {
      document.documentElement.removeAttribute("data-ev-signed-in");
    }
    if (!window.EngineVerse) window.EngineVerse = { csrf: "", user: signedIn };
    else window.EngineVerse.user = signedIn;
  }

  function loadStore() {
    const parseCandidate = (str) => {
      if (!str) return null;
      try {
        const obj = JSON.parse(str);
        return obj && typeof obj === "object" ? obj : null;
      } catch (_) {
        return null;
      }
    };
    let lsObj = null;
    let ssObj = null;
    let wnObj = null;
    try { lsObj = parseCandidate(localStorage.getItem(STORE_KEY)); } catch (_) {}
    try { ssObj = parseCandidate(sessionStorage.getItem(STORE_KEY)); } catch (_) {}
    try {
      if (typeof window.name === "string" && window.name.indexOf("EV_STORE:") === 0) {
        wnObj = parseCandidate(window.name.slice(9));
      }
    } catch (_) {}

    const accounts = {};
    [wnObj, ssObj, lsObj].forEach((cand) => {
      if (cand && cand.accounts && typeof cand.accounts === "object") {
        for (const [uname, acc] of Object.entries(cand.accounts)) {
          accounts[uname] = Object.assign({}, accounts[uname] || {}, acc);
        }
      }
    });

    let explicitLogout = false;
    try { explicitLogout = sessionStorage.getItem("ev:explicit_logout") === "1"; } catch (_) {}

    let currentUser =
      (lsObj && lsObj.currentUser) ||
      (ssObj && ssObj.currentUser) ||
      (wnObj && wnObj.currentUser) ||
      null;

    if (!currentUser && !explicitLogout) {
      try {
        currentUser =
          localStorage.getItem(SESSION_USER_KEY) ||
          sessionStorage.getItem(SESSION_USER_KEY) ||
          readCookieUser() ||
          null;
      } catch (_) {
        currentUser = readCookieUser() || null;
      }
    }
    if (currentUser === "guest" || currentUser === "") currentUser = null;
    if (currentUser && !accounts[currentUser]) {
      accounts[currentUser] = defaultProfile({ username: currentUser, display_name: currentUser });
    }

    const baseObj = lsObj || ssObj || wnObj || {};
    syncGlobalAuthFlag(currentUser);
    return {
      currentUser: currentUser || null,
      accounts,
      otpChallenges: baseObj.otpChallenges && typeof baseObj.otpChallenges === "object" ? baseObj.otpChallenges : {},
      githubRepo: baseObj.githubRepo || GH_REPO,
      githubToken: baseObj.githubToken || "",
      webhookUrl: baseObj.webhookUrl || "",
      lastSyncAt: baseObj.lastSyncAt || "",
    };
  }

  function saveStore(store, opts = {}) {
    const cleanUser = store.currentUser && store.currentUser !== "guest" ? String(store.currentUser).toLowerCase() : null;
    store.currentUser = cleanUser;
    const serialized = JSON.stringify(store);
    try {
      localStorage.setItem(STORE_KEY, serialized);
      if (cleanUser) localStorage.setItem(SESSION_USER_KEY, cleanUser);
      else localStorage.removeItem(SESSION_USER_KEY);
    } catch (_) {}
    try {
      sessionStorage.setItem(STORE_KEY, serialized);
      if (cleanUser) {
        sessionStorage.setItem(SESSION_USER_KEY, cleanUser);
        sessionStorage.removeItem("ev:explicit_logout");
      } else {
        sessionStorage.removeItem(SESSION_USER_KEY);
      }
    } catch (_) {}
    try {
      window.name = "EV_STORE:" + serialized;
    } catch (_) {}
    writeCookieUser(cleanUser || "");
    idbWriteStore(store);
    syncGlobalAuthFlag(cleanUser);
    if (!opts.skipBroadcast && authChannel) {
      try {
        authChannel.postMessage({ type: "ev_store_sync", currentUser: cleanUser, ts: Date.now() });
      } catch (_) {}
    }
  }

  // ---------------------------------------------------------------------------
  // Scoped 6-Digit OTP Engine (Gmail/email & Mobile Number with Country Code)
  // Required ONLY for: (1) new user signup, (2) forgot password, (3) change password.
  // ---------------------------------------------------------------------------
  // === BEGIN EV-IDENTITY-RULES ===
  // Mirror of backend/engineverse/security/email_rules.py and phone_rules.py.
  //
  // The exported site has no server, so this copy is the only check those pages
  // get - which is also why it must not drift: a learner told by the browser
  // that `asha@gmail` is fine gets a page that silently does nothing. The
  // *policy* (plan table, typo map, burner list) is injected into the boot blob
  // by scripts/export_pages.py from the Python module, so both sides read one
  // source; what lives here is the algorithm. FALLBACK_IDENTITY_POLICY exists
  // for the case the export was cached by the service worker next to a newer
  // script (or an older one) - it is a real table, not a permissive stub.
  //
  // Neither side can ask DNS from a static page, so a well-formed address at a
  // domain that does not exist is refused by the hosted app and tolerated here;
  // the 6-digit code is what both of them can actually verify.
  //
  // backend/tests/test_identity_validation.py lifts this block into node and
  // runs the same fixtures through it and through Python.
  const FALLBACK_IDENTITY_POLICY = {
    email: {
      maxLength: 254,
      localRe: "^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$",
      labelRe: "^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$",
      tldRe: "^[A-Za-z]{2,}$",
      localMaxLength: 64,
      reservedTlds: ["example", "test", "invalid", "localhost", "local"],
      reservedDomains: ["example.com", "example.net", "example.org"],
      providers: ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com", "rediffmail.com"],
      // Real providers that look like typos of one. Refusing these is how the
      // first cut of this check locked people out, so they are exempted on both
      // sides, from the exported policy where possible and from this list when
      // a cached page is paired with a newer script.
      lookalikes: ["mail.com", "gmx.com", "zoho.com", "me.com", "mc.com", "juno.com", "proton.me", "fastmail.com", "tutanota.com", "web.de", "gmx.de", "yandex.ru"],
      typos: {
        "gmial.com": "gmail.com", "gmai.com": "gmail.com", "gnail.com": "gmail.com",
        "gmail.co": "gmail.com", "gmail.con": "gmail.com", "gmail.vom": "gmail.com",
        "hotmial.com": "hotmail.com", "hotmai.com": "hotmail.com", "outlok.com": "outlook.com",
        "yahooo.com": "yahoo.com", "yaho.com": "yahoo.com",
      },
      disposable: ["mailinator.com", "10minutemail.com", "guerrillamail.com", "temp-mail.org", "yopmail.com"],
    },
    phone: {
      minDigits: 8,
      maxDigits: 15,
      // nsn = the digits after the country code, trunk prefix already removed.
      plans: {
        "+91": { label: "India", nsn: "^[1-9][0-9]{9}$", example: "+91 98765 43210" },
        "+1": { label: "United States / Canada", nsn: "^[2-9][0-9]{2}[2-9][0-9]{6}$", example: "+1 415 555 2671" },
        "+44": { label: "United Kingdom", nsn: "^(?:1[0-9]{8,9}|2[23478][0-9]{7,8}|7[1-9][0-9]{8})$", example: "+44 7911 123456" },
        "+61": { label: "Australia", nsn: "^[2-9][0-9]{8}$", example: "+61 412 345 678" },
        "+49": { label: "Germany", nsn: "^[1-9][0-9]{5,11}$", example: "+49 151 23456789" },
        "+33": { label: "France", nsn: "^[1-9][0-9]{8}$", example: "+33 6 12 34 56 78" },
        "+65": { label: "Singapore", nsn: "^[3689][0-9]{7}$", example: "+65 8123 4567" },
        "+971": { label: "United Arab Emirates", nsn: "^[2-9][0-9]{7,8}$", example: "+971 50 123 4567" },
        "+81": { label: "Japan", nsn: "^[5789][0-9]{8,9}$", example: "+81 90 1234 5678" },
        "+82": { label: "South Korea", nsn: "^[1-6][0-9]{7,9}$", example: "+82 10 1234 5678" },
        "+86": { label: "China", nsn: "^[1-9][0-9]{9,10}$", example: "+86 138 1234 5678" },
        "+55": { label: "Brazil", nsn: "^[1-9][0-9]{8,10}$", example: "+55 11 96123 4567" },
        "+27": { label: "South Africa", nsn: "^[1-9][0-9]{8}$", example: "+27 82 123 4567" },
        "+234": { label: "Nigeria", nsn: "^[1-9][0-9]{7,9}$", example: "+234 801 234 5678" },
        "+7": { label: "Russia / Kazakhstan", nsn: "^[3489][0-9]{9}$", example: "+7 912 345 67 89" },
      },
    },
  };

  function makeIdentityRules(policy) {
    const emailPolicy = policy.email || {};
    const phonePolicy = policy.phone || {};
    const localRe = new RegExp(emailPolicy.localRe || FALLBACK_IDENTITY_POLICY.email.localRe);
    const labelRe = new RegExp(emailPolicy.labelRe || FALLBACK_IDENTITY_POLICY.email.labelRe);
    const tldRe = new RegExp(emailPolicy.tldRe || FALLBACK_IDENTITY_POLICY.email.tldRe);
    const maxLength = emailPolicy.maxLength || 254;
    const localMaxLength = emailPolicy.localMaxLength || 64;
    const providers = emailPolicy.providers || [];
    const typos = emailPolicy.typos || {};
    const disposable = new Set(emailPolicy.disposable || []);
    const plans = phonePolicy.plans || {};
    const minDigits = phonePolicy.minDigits || 8;
    const maxDigits = phonePolicy.maxDigits || 15;
    const PHONE_CHARS = /^[0-9 +.()-]*$/;
    const reservedDomains = new Set(emailPolicy.reservedDomains || []);
    const reservedSuffixes = new Set(emailPolicy.reservedTlds || []);
    const lookalikes = new Set(emailPolicy.lookalikes || []);

    function isReserved(domain, labels) {
      if (reservedDomains.has(domain)) return true;
      if (reservedSuffixes.has(labels[labels.length - 1])) return true;
      return /\.(?:local|internal|intranet|lan|home|corp)$/.test(domain);
    }

    // Bounded Levenshtein, same limit as email_rules.edit_distance: past two
    // edits a domain is not a typo, it is a different domain.
    function distance(left, right) {
      if (left === right) return 0;
      if (Math.abs(left.length - right.length) > 2) return 3;
      let previous = Array.from({ length: right.length + 1 }, (_, i) => i);
      for (let i = 1; i <= left.length; i += 1) {
        const current = [i];
        let best = i;
        for (let j = 1; j <= right.length; j += 1) {
          const cost = left[i - 1] === right[j - 1] ? 0 : 1;
          const value = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost);
          current.push(value);
          best = Math.min(best, value);
        }
        if (best > 2) return 3;
        previous = current;
      }
      return previous[right.length];
    }

    function nearMiss(domain) {
      if (lookalikes.has(domain) || providers.includes(domain)) return "";
      let best = "";
      let bestDistance = 3;
      for (const provider of providers) {
        const d = distance(domain, provider);
        if (d > 0 && d < bestDistance) {
          best = provider;
          bestDistance = d;
        }
      }
      return best;
    }

    function email(raw) {
      // Lowercased up front, like email_rules.parse(): the store keys lookups on
      // the address, so `Asha@Example.COM` and `asha@example.com` have to be the
      // same account here exactly as they are on the server.
      const text = String(raw || "").trim().toLowerCase();
      if (!text) return { ok: false, error: "Enter your Gmail or email address." };
      if (text.length > maxLength) {
        return { ok: false, error: `An email address is at most ${maxLength} characters. Yours is ${text.length}.` };
      }
      if ((text.match(/@/g) || []).length !== 1) {
        return { ok: false, error: "An email address has one @ sign, for example you@gmail.com." };
      }
      const at = text.indexOf("@");
      const local = text.slice(0, at).trim();
      const domain = text.slice(at + 1).trim().replace(/\.+$/, "").toLowerCase();
      if (!local) return { ok: false, error: "Add the part before the @, for example saurav@gmail.com." };
      if (local.length > localMaxLength) {
        return { ok: false, error: `The part before the @ is limited to ${localMaxLength} characters.` };
      }
      if (!localRe.test(local)) {
        return { ok: false, error: `The part before the @ has a character an email address cannot start or end with, or two dots in a row: ${local}` };
      }
      if (!domain) return { ok: false, error: "Add the domain after the @, for example gmail.com." };
      if (/^\[[0-9.]+\]$/.test(domain)) return { ok: true, value: `${local}@${domain.toLowerCase()}`, domain };
      if (/\s/.test(domain) || domain.includes("@")) {
        return { ok: false, error: "An email address cannot contain spaces or a second @ sign." };
      }
      const labels = domain.split(".");
      if (labels.some((label) => !label)) {
        return { ok: false, error: `There is an empty piece in ${domain}. Remove the extra dot and try again.` };
      }
      if (labels.length === 1) {
        const provider = providers.find((name) => name.split(".")[0] === domain);
        return {
          ok: false,
          error: provider
            ? `Did you mean ${provider}? A ${domain} address needs its domain after the dot.`
            : `'${domain}' is not a domain the internet can route mail to. Use the full address, for example name@gmail.com.`,
        };
      }
      for (const label of labels) {
        if (!labelRe.test(label)) {
          return {
            ok: false,
            error: `'${label}' is not a valid domain part: letters, digits and single dashes, and never a leading or trailing dash.`,
          };
        }
      }
      if (!tldRe.test(labels[labels.length - 1])) {
        return { ok: false, error: `'${labels[labels.length - 1]}' is not a domain extension. A Gmail address ends in gmail.com.` };
      }
      if (typos[domain]) {
        return { ok: false, error: `'${domain}' is not a mail provider - did you mean ${typos[domain]}?`, suggestion: typos[domain] };
      }
      // One or two keystrokes from a real provider, and not itself a provider:
      // `gnail.com`, `gmial.com`. The hosted app reaches the same conclusion via
      // DNS ("nobody can receive mail there") and so leaves an unusual-but-real
      // domain alone; a static page cannot ask DNS, so it treats a near-miss of a
      // known provider as a typo outright. The domains that *look* like typos and
      // are not (mail.com, gmx.com, zoho.com) come from the policy as
      // `lookalikes`, which is why they are listed there rather than hardcoded
      // here - the two sides must refuse the same set.
      if (!isReserved(domain, labels)) {
        const near = nearMiss(domain);
        if (near) {
          return { ok: false, error: `'${domain}' is one keystroke from ${near}. Check the spelling before you save it.`, suggestion: near };
        }
      }
      if (disposable.has(domain)) {
        return {
          ok: false,
          error: "That is a temporary inbox, which stops working before your course does. Use an address you will still have next month.",
        };
      }
      return { ok: true, value: `${local}@${domain}`, domain };
    }

    function splitE164(digits) {
      for (let length = 1; length <= 3; length += 1) {
        const code = `+${digits.slice(0, length)}`;
        if (plans[code]) return { code, nsn: digits.slice(length) };
      }
      for (let length = 1; length <= 3; length += 1) {
        const code = `+${digits.slice(0, length)}`;
        if (/^\+[1-9][0-9]{0,2}$/.test(code) && digits.length > length) {
          return { code, nsn: digits.slice(length) };
        }
      }
      return null;
    }

    // The shapes nobody was issued: one digit repeated, a short ascending or
    // descending run. Longer runs are left alone on purpose - 9876543210 is a
    // real, assignable Indian number and the example in the docs.
    function looksInvented(nsn) {
      if (nsn.length < 4) return true;
      if (/^([0-9])\1{3,}$/.test(nsn)) return true;
      if (nsn.length <= 8) {
        const steps = [];
        for (let i = 0; i + 1 < nsn.length; i += 1) steps.push(Number(nsn[i + 1]) - Number(nsn[i]));
        const up = steps.every((step) => step === 1);
        const down = steps.every((step) => step === -1);
        if (up || down) return true;
      }
      return false;
    }

    function phone(raw, countryCode) {
      const text = String(raw || "").trim();
      if (!text) return { ok: false, error: "Enter a mobile number with country code, for example 98765 43210 with +91." };
      if (!PHONE_CHARS.test(text)) {
        return { ok: false, error: "A mobile number contains digits, spaces, dots, dashes or brackets only." };
      }
      let cc = String(countryCode || "+91").trim().replace(/\s+/g, "");
      if (cc && !cc.startsWith("+")) cc = `+${cc}`;
      if (cc && !/^\+[1-9][0-9]{0,3}$/.test(cc)) {
        return { ok: false, error: "Select a valid country code (for example +91, +1, +44)." };
      }
      let hasPlus = text.includes("+");
      let digits = text.replace(/\D+/g, "");
      if (!digits) return { ok: false, error: "Enter the mobile number that follows the country code." };
      // 00 is the international prefix most of the world dials before a country
      // code, exactly as in validators.normalize_phone_with_country_code.
      if (!hasPlus && digits.startsWith("00")) {
        hasPlus = true;
        digits = digits.slice(2);
      }
      const national = hasPlus ? "" : digits.replace(/^0+/, "");
      let combined = "";
      if (hasPlus) {
        combined = `+${digits}`;
      } else {
        if (!cc) cc = "+91";
        combined = `${cc}${national}`;
      }
      const total = combined.length - 1;
      if (total < minDigits || total > maxDigits) {
        return {
          ok: false,
          error: `A phone number has between ${minDigits} and ${maxDigits} digits including the country code. Count the digits you typed.`,
        };
      }
      const parts = splitE164(combined.slice(1));
      if (!parts) {
        return { ok: false, error: "That country code is not recognised. Start the number with + and its code, for example +91." };
      }
      const plan = plans[parts.code];
      if (plan && !new RegExp(plan.nsn).test(parts.nsn)) {
        return {
          ok: false,
          error: `${plan.label} numbers look like ${plan.example}. The ${parts.nsn.length} digits you typed after ${parts.code} do not match that plan.`,
        };
      }
      if (looksInvented(parts.nsn)) {
        return {
          ok: false,
          error: "That looks like a placeholder rather than a phone number. Type the number as it is written on your SIM.",
        };
      }
      return { ok: true, value: combined };
    }

    // What the sign-in box may hold: an address, a username, or a number that
    // starts with +. A digit-only string is not forced into being a phone,
    // because it is as likely to be somebody's numeric username.
    function identity(raw) {
      const text = String(raw || "").trim();
      if (!text) return { ok: false, error: "Enter the email, username or mobile number on your account." };
      if (text.includes("@")) return email(text);
      if (text.startsWith("+")) return phone(text, "+91");
      return { ok: true, value: text.toLowerCase() };
    }

    return { email, phone, identity, plans };
  }

  const IDENTITY = makeIdentityRules(config.identity || FALLBACK_IDENTITY_POLICY);

  function normalizePhoneWithCountryCode(phoneRaw, countryCode = "+91") {
    const result = IDENTITY.phone(phoneRaw, countryCode);
    return result.ok ? result.value : "";
  }
  // === END EV-IDENTITY-RULES ===

  // One lookup for every account page: username, email, the SHA-256 of either,
  // or a mobile number with its country code. It lives at module scope because
  // sign-in needs it and so does recovery - the forgot-password page has to know
  // which address an account actually holds before it can claim to mail it.
  async function findAccountByIdentity(store, identity) {
    const value = String(identity || "").trim().toLowerCase();
    if (!value) return null;
    const normalizedPhone = value.startsWith("+") || /^\d{7,15}$/.test(value.replace(/\D+/g, ""))
      ? normalizePhoneWithCountryCode(value, "+91")
      : "";
    const idSha = await sha256Hex(value);
    const phoneSha = normalizedPhone ? await sha256Hex(normalizedPhone) : "";
    return (
      Object.values(store.accounts || {}).find(
        (a) =>
          a.username?.toLowerCase() === value ||
          (a.email && a.email.toLowerCase() === value) ||
          (a.email_sha256 && a.email_sha256 === idSha) ||
          (normalizedPhone && a.phone === normalizedPhone) ||
          (phoneSha && a.phone_sha256 === phoneSha)
      ) || null
    );
  }

  function maskDestination(dest, channel = "email") {
    const val = String(dest || "").trim();
    if (channel === "phone" || val.startsWith("+")) {
      const digits = val.replace(/\D+/g, "");
      if (digits.length <= 4) return "••••" + digits;
      return `${val.startsWith("+") ? "+" : ""}${"•".repeat(Math.max(4, digits.length - 4))}${digits.slice(-4)}`;
    }
    const [local, domain] = val.split("@");
    // A username with no @ is not an address, and rendering it as
    // "••••@gmail.com" made the page claim a destination nobody had typed.
    if (!domain) return val ? `••••${local.slice(-4)} (not an address)` : "no address on file";
    const maskedLocal =
      local.length <= 2
        ? local[0] + "•••"
        : local[0] + "•".repeat(Math.max(2, local.length - 2)) + local[local.length - 1];
    return `${maskedLocal}@${domain}`;
  }

  function generateSixDigitOtp() {
    if (window.crypto?.getRandomValues) {
      const arr = new Uint32Array(1);
      window.crypto.getRandomValues(arr);
      return String(arr[0] % 1000000).padStart(6, "0");
    }
    return String(Math.floor(100000 + Math.random() * 900000));
  }

  // Real delivery: when an OTP service is configured (exported meta tag,
  // window.EV_OTP_API_URL, or localStorage "ev:otp_api_url"), the code is
  // generated and SENT by that service (services/otp) to the user's own
  // email/phone. The browser never receives the code. Without a service this
  // static page cannot send anything, so it falls back to showing the code —
  // the honest demo behaviour, labelled as such.
  function otpServiceUrl() {
    const meta = document.querySelector('meta[name="ev-otp-api-url"]');
    let url = (window.EV_OTP_API_URL || config.otpApiUrl || meta?.getAttribute("content") || "").trim();
    if (!url) {
      try { url = String(localStorage.getItem("ev:otp_api_url") || "").trim(); } catch (_) {}
    }
    return url.replace(/\/+$/, "");
  }

  function otpIssueHtml(issued, label) {
    if (issued.error) {
      return `<strong>Code could not be sent:</strong> ${escapeHtml(issued.error)}`;
    }
    if (issued.delivered) {
      return `<strong>${escapeHtml(label)}:</strong> A 6-digit code was sent to ` +
        `<code>${escapeHtml(issued.masked)}</code>. Enter it below — it expires in 10 minutes.`;
    }
    return `<strong>${escapeHtml(label)}:</strong> Static copy: no email or SMS can be sent from this page, so your code is shown here instead — it only proves you can read this screen. On the hosted app the code is delivered to your address. Code for <code>${escapeHtml(issued.masked)}</code>: <code>${issued.code}</code>`;
  }

  function otpIssueToast(issued) {
    if (issued.error) return "Code could not be sent — see the message above";
    return issued.delivered
      ? `6-digit code sent to ${issued.masked}`
      : "Code shown on this page (static copy — nothing was sent)";
  }

  async function issueBrowserOtpChallenge({ purpose, username, channel, destination }) {
    const serviceUrl = otpServiceUrl();
    if (serviceUrl) {
      const masked = maskDestination(destination, channel);
      try {
        const resp = await fetch(`${serviceUrl}/otp/send`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ purpose, channel, destination }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.ok) {
          return { delivered: false, error: data.error || "The OTP service could not send your code.", masked, channel, destination };
        }
        const store = loadStore();
        if (!store.otpChallenges || typeof store.otpChallenges !== "object") store.otpChallenges = {};
        // Only routing metadata is kept locally — no code, no code hash.
        store.otpChallenges[purpose] = {
          purpose, username: String(username || "").toLowerCase(), channel,
          destination, masked: data.masked || masked, remote: true,
          expiresAt: Date.now() + Number(data.expires_in || 600) * 1000, attempts: 0,
        };
        saveStore(store, { skipBroadcast: true });
        return { delivered: true, masked: data.masked || masked, channel, destination };
      } catch (_) {
        return { delivered: false, error: "Could not reach the OTP service. Check your connection and try again.", masked, channel, destination };
      }
    }
    const code = generateSixDigitOtp();
    const digest = await sha256Hex(`ev-otp:${purpose}:${username}:${code}`);
    const masked = maskDestination(destination, channel);
    const store = loadStore();
    if (!store.otpChallenges || typeof store.otpChallenges !== "object") {
      store.otpChallenges = {};
    }
    store.otpChallenges[purpose] = {
      purpose,
      username: String(username || "").toLowerCase(),
      channel,
      destination,
      masked,
      codeHash: digest,
      expiresAt: Date.now() + 10 * 60 * 1000,
      attempts: 0,
    };
    saveStore(store, { skipBroadcast: true });

    // Forward OTP event to n8n / Supabase / Appwrite webhook if configured
    if (store.webhookUrl) {
      forwardWebhook(store.webhookUrl, {
        event: "otp_issued",
        purpose,
        username,
        channel,
        destination_masked: masked,
        otp_code: code,
        ts: new Date().toISOString(),
      }).catch(() => {});
    }
    return { code, masked, channel, destination };
  }

  async function verifyBrowserOtpChallenge(purpose, submittedCode) {
    const cleanCode = String(submittedCode || "").replace(/[\s.-]+/g, "");
    if (!/^\d{6}$/.test(cleanCode)) {
      return { ok: false, error: "Enter a valid 6-digit numeric OTP code." };
    }
    const store = loadStore();
    const ch = store.otpChallenges?.[purpose];
    if (!ch) {
      return { ok: false, error: "No active OTP challenge found. Request a new 6-digit OTP." };
    }
    if (Date.now() > Number(ch.expiresAt || 0)) {
      delete store.otpChallenges[purpose];
      saveStore(store, { skipBroadcast: true });
      return { ok: false, error: "That 6-digit OTP has expired. Click Resend OTP to get a fresh code." };
    }
    if (ch.remote) {
      // The service checks the code; this page never had it.
      const serviceUrl = otpServiceUrl();
      if (!serviceUrl) {
        return { ok: false, error: "The OTP service is no longer configured. Request a new 6-digit OTP." };
      }
      try {
        const resp = await fetch(`${serviceUrl}/otp/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ purpose, destination: ch.destination, code: cleanCode }),
        });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok && data.ok) {
          delete store.otpChallenges[purpose];
          saveStore(store, { skipBroadcast: true });
          return { ok: true, challenge: ch };
        }
        if (resp.status === 401 && /expired|too many/i.test(String(data.error || ""))) {
          delete store.otpChallenges[purpose];
          saveStore(store, { skipBroadcast: true });
        }
        return { ok: false, error: data.error || "That 6-digit OTP was not accepted." };
      } catch (_) {
        return { ok: false, error: "Could not reach the OTP service to verify your code. Try again." };
      }
    }
    const expectedHash = await sha256Hex(`ev-otp:${purpose}:${ch.username}:${cleanCode}`);
    if (expectedHash !== ch.codeHash) {
      ch.attempts = Number(ch.attempts || 0) + 1;
      if (ch.attempts >= 5) {
        delete store.otpChallenges[purpose];
        saveStore(store, { skipBroadcast: true });
        return { ok: false, error: "Too many incorrect OTP attempts. Request a new 6-digit OTP." };
      }
      store.otpChallenges[purpose] = ch;
      saveStore(store, { skipBroadcast: true });
      return { ok: false, error: `Incorrect 6-digit OTP code (${5 - ch.attempts} attempts remaining).` };
    }
    delete store.otpChallenges[purpose];
    saveStore(store, { skipBroadcast: true });
    return { ok: true, challenge: ch };
  }

  function getActiveProfile() {
    const store = loadStore();
    if (store.currentUser && store.accounts[store.currentUser]) {
      return store.accounts[store.currentUser];
    }
    if (!store.accounts.guest) {
      store.accounts.guest = defaultProfile();
      saveStore(store);
    }
    return store.accounts.guest;
  }

  function saveActiveProfile(mutator) {
    const store = loadStore();
    const key = store.currentUser || "guest";
    const profile = store.accounts[key] || defaultProfile({ username: key });
    mutator(profile);
    const streakState = computeStreak(writeStreak((profile.activity_days || []).concat(readStreak().days)));
    profile.activity_days = streakState.days;
    profile.streak_days = streakState.current;
    profile.longest_streak = Math.max(Number(profile.longest_streak || 0), streakState.longest);
    profile.xp = Math.max(0, Number(profile.xp || 0));
    profile.level = Math.max(1, Math.floor(profile.xp / 250) + 1);
    profile.updated_at = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
    store.accounts[key] = profile;
    saveStore(store);
    if (store.webhookUrl) {
      forwardWebhook(store.webhookUrl, toGithubSnapshot(profile)).catch(() => {});
    }
    return profile;
  }

  function toGithubSnapshot(profile) {
    return {
      username: (profile.username || "guest").toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 30) || "learner",
      display_name: String(profile.display_name || profile.username || "Learner").slice(0, 60),
      branch: String(profile.branch || "cse").slice(0, 32),
      year_of_study: Math.min(6, Math.max(1, Number(profile.year_of_study || 1))),
      bio: String(profile.bio || "").slice(0, 240),
      xp: Math.max(0, Number(profile.xp || 0)),
      level: Math.max(1, Number(profile.level || 1)),
      streak_days: Math.max(0, Number(profile.streak_days || 0)),
      longest_streak: Math.max(0, Number(profile.longest_streak || 0)),
      activity_days: Array.from(new Set(profile.activity_days || [])).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d)).sort().slice(-365),
      completed_topics: Array.from(new Set(profile.completed_topics || [])).sort(),
      solved_problems: Array.from(new Set(profile.solved_problems || [])).sort(),
      completed_projects: Array.from(new Set(profile.completed_projects || [])).sort(),
      bookmarks: Array.from(new Set(profile.bookmarks || [])).sort(),
      quiz_attempts: Math.max(0, Number(profile.quiz_attempts || 0)),
      quiz_correct: Math.max(0, Number(profile.quiz_correct || 0)),
      // Progress only. The snapshot is published to a public repository, so
      // it must never carry the password digest or hashed contact details
      // that the device-local profile keeps. Those stay on this device.
      password_sha256: "",
      email_sha256: "",
      phone_sha256: "",
      country_code: String(profile.country_code || "+91"),
      otp_verified: profile.otp_verified !== false,
      updated_at: profile.updated_at || new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    };
  }

  function mergeSnapshotIntoStore(snapshot, setCurrent = false) {
    if (!snapshot || !snapshot.username) return null;
    const uname = String(snapshot.username).toLowerCase().trim();
    const store = loadStore();
    const existing = store.accounts[uname] || defaultProfile({ username: uname });
    const merged = Object.assign({}, existing, {
      username: uname,
      display_name: snapshot.display_name || existing.display_name || uname,
      branch: snapshot.branch || existing.branch || "cse",
      year_of_study: Number(snapshot.year_of_study || existing.year_of_study || 1),
      bio: snapshot.bio || existing.bio || "",
      country_code: snapshot.country_code || existing.country_code || "+91",
      otp_verified: snapshot.otp_verified !== undefined ? Boolean(snapshot.otp_verified) : existing.otp_verified !== false,
      xp: Math.max(Number(existing.xp || 0), Number(snapshot.xp || 0)),
      level: Math.max(Number(existing.level || 1), Number(snapshot.level || 1)),
      streak_days: Math.max(Number(existing.streak_days || 0), Number(snapshot.streak_days || 0)),
      longest_streak: Math.max(Number(existing.longest_streak || 0), Number(snapshot.longest_streak || 0)),
      activity_days: Array.from(new Set([...(existing.activity_days || []), ...(snapshot.activity_days || [])])).sort(),
      completed_topics: Array.from(new Set([...(existing.completed_topics || []), ...(snapshot.completed_topics || [])])).sort(),
      solved_problems: Array.from(new Set([...(existing.solved_problems || []), ...(snapshot.solved_problems || [])])).sort(),
      completed_projects: Array.from(new Set([...(existing.completed_projects || []), ...(snapshot.completed_projects || [])])).sort(),
      bookmarks: Array.from(new Set([...(existing.bookmarks || []), ...(snapshot.bookmarks || [])])).sort(),
      quiz_attempts: Math.max(Number(existing.quiz_attempts || 0), Number(snapshot.quiz_attempts || 0)),
      quiz_correct: Math.max(Number(existing.quiz_correct || 0), Number(snapshot.quiz_correct || 0)),
      // A snapshot pulled from the public registry is untrusted input: it
      // must never set this device's password or contact-identifier hashes.
      // Only the hashes already stored on this device survive a merge.
      password_sha256: existing.password_sha256 || "",
      email_sha256: existing.email_sha256 || "",
      phone_sha256: existing.phone_sha256 || "",
      updated_at: snapshot.updated_at || existing.updated_at,
    });
    store.accounts[uname] = merged;
    if (setCurrent) store.currentUser = uname;
    saveStore(store, { skipBroadcast: !setCurrent });
    if (merged.activity_days?.length) {
      writeStreak(readStreak().days.concat(merged.activity_days));
    }
    return merged;
  }

  // Pull seeded & live GitHub learner vault on boot
  async function pullGithubVault(silent = true) {
    const store = loadStore();
    const repo = store.githubRepo || GH_REPO;
    const urls = [
      `https://api.github.com/repos/${repo}/contents/${GH_VAULT_PATH}`,
      config.vault || `${BASE}learner-vault.json`,
    ];
    for (const url of urls) {
      try {
        const headers = { Accept: "application/vnd.github+json, application/json" };
        if (url.includes("api.github.com") && store.githubToken) {
          headers.Authorization = `Bearer ${store.githubToken}`;
        }
        const res = await fetch(url, { headers, cache: "no-store" });
        if (!res.ok) continue;
        const data = await res.json();
        let registry = data;
        if (data && data.content && data.encoding === "base64") {
          const decoded = decodeURIComponent(escape(atob(String(data.content).replace(/\s+/g, ""))));
          registry = JSON.parse(decoded);
        }
        if (registry && registry.learners && typeof registry.learners === "object") {
          Object.values(registry.learners).forEach((snap) => mergeSnapshotIntoStore(snap, false));
          if (!silent) toast(`Synced ${Object.keys(registry.learners).length} learner record(s) from GitHub Vault.`);
          return registry;
        }
      } catch (_) {
        /* try next fallback */
      }
    }
    if (!silent) toast("Loaded local learner vault cache.", "info");
    return null;
  }

  async function pushSnapshotToGithub(profile, options = {}) {
    const initialStore = loadStore();
    const repo = (options.repo || initialStore.githubRepo || GH_REPO).trim();
    const token = (options.token !== undefined ? options.token : initialStore.githubToken || "").trim();
    const snapshot = toGithubSnapshot(profile);

    const recordSyncTime = () => {
      const latest = loadStore();
      latest.lastSyncAt = new Date().toISOString();
      if (snapshot.username && latest.accounts[snapshot.username]) {
        latest.accounts[snapshot.username] = Object.assign({}, latest.accounts[snapshot.username], profile);
      }
      saveStore(latest, { skipBroadcast: true });
    };

    // 1. Try local FastAPI backend `/api/sync/snapshot` if running on a live server
    try {
      const apiRes = await fetch(`${BASE}api/sync/snapshot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ snapshot, push_github: true }),
      });
      if (apiRes.ok) {
        const out = await apiRes.json();
        if (out.ok) {
          recordSyncTime();
          toast(`Saved learner data for @${snapshot.username} to GitHub vault!`);
          return { ok: true, mode: "backend-api", detail: out };
        }
      }
    } catch (_) {
      /* static host; proceed with direct GitHub push or GitHub Issue workflow */
    }

    // 2. If user provided a GitHub token, push directly via GitHub Contents API
    if (token) {
      const apiUrl = `https://api.github.com/repos/${repo}/contents/${GH_VAULT_PATH}`;
      const headers = {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
      };
      const getRes = await fetch(apiUrl, { headers, cache: "no-store" });
      let registry = { schema_version: 1, repository: repo, updated_at: "", learners: {} };
      let sha = "";
      if (getRes.ok) {
        const current = await getRes.json();
        sha = current.sha || "";
        if (current.content) {
          const decoded = decodeURIComponent(escape(atob(String(current.content).replace(/\s+/g, ""))));
          registry = JSON.parse(decoded);
        }
      }
      if (!registry.learners || typeof registry.learners !== "object") registry.learners = {};
      registry.learners[snapshot.username] = snapshot;
      registry.updated_at = snapshot.updated_at;
      const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(registry, null, 2) + "\n")));
      const putBody = {
        message: `chore(learners): sync progress snapshot for ${snapshot.username}`,
        content: encoded,
        branch: "main",
      };
      if (sha) putBody.sha = sha;
      const putRes = await fetch(apiUrl, {
        method: "PUT",
        headers: Object.assign({ "Content-Type": "application/json" }, headers),
        body: JSON.stringify(putBody),
      });
      if (!putRes.ok) {
        const errData = await putRes.json().catch(() => ({}));
        throw new Error(errData.message || `GitHub API push returned HTTP ${putRes.status}`);
      }
      recordSyncTime();
      toast(`Committed @${snapshot.username}'s progress directly to ${repo}!`);
      return { ok: true, mode: "github-contents-api" };
    }

    // 3. Zero-token GitHub Actions Issue Sync (opens pre-filled issue on authorsauravkushwaha/EngineVerse)
    if (options.useIssueSync) {
      const title = `[learner-sync] @${snapshot.username} (${snapshot.xp} XP · ${snapshot.streak_days}d streak)`;
      const body = [
        "### EngineVerse Learner Progress Sync Request",
        "",
        `This issue asks a maintainer to review and merge a progress-only snapshot for **@${snapshot.username}** to \`data/learners/registry.json\` on \`${repo}\`.`,
        "It contains no password or contact details. A maintainer reviews it and runs the `Learner Data Sync` workflow manually; submitting this issue does not commit anything by itself.",
        "",
        "```engineverse-learner-snapshot",
        JSON.stringify(snapshot, null, 2),
        "```",
      ].join("\n");
      const issueUrl = `https://github.com/${repo}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
      window.open(issueUrl, "_blank", "noopener,noreferrer");
      toast("Opened a GitHub sync request — a maintainer reviews it before anything is saved.");
      return { ok: true, mode: "github-issue-workflow", issueUrl };
    }

    // Save locally and prompt user with one-click GitHub Issue sync
    recordSyncTime();
    return { ok: true, mode: "local-vault", snapshot };
  }

  async function forwardWebhook(url, snapshot) {
    if (!url || !/^https?:\/\//i.test(url)) return;
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "engineverse", event: "learner.snapshot", snapshot }),
    });
  }

  // ---------------------------------------------------------------------------
  // 1. Streak calculation & activity recording
  // ---------------------------------------------------------------------------
  const computeStreak = (days) => {
    const today = new Date();
    const todayNum = dayIndex(today);
    const nums = days
      .map(parseIso)
      .filter(Boolean)
      .map(dayIndex)
      .sort((a, b) => a - b);
    const set = new Set(nums);

    let cursor = set.has(todayNum)
      ? todayNum
      : set.has(todayNum - 1)
      ? todayNum - 1
      : null;
    let current = 0;
    while (cursor !== null && set.has(cursor)) {
      current += 1;
      cursor -= 1;
    }

    let longest = 0;
    let run = 0;
    let prev = null;
    for (const n of set) {
      run = prev !== null && n === prev + 1 ? run + 1 : 1;
      if (run > longest) longest = run;
      prev = n;
    }

    return {
      current,
      longest,
      total: set.size,
      todayDone: set.has(todayNum),
      days,
    };
  };

  const shouldRecordStudy = () => {
    const path = location.pathname;
    return (
      path.includes("/dpp/") ||
      path.includes("/topics/") ||
      path.includes("/practice/") ||
      path.includes("/programming/") ||
      path.includes("/projects/") ||
      path.includes("/tutor/") ||
      path.includes("/flashcards/") ||
      path.includes("/revision/") ||
      path.includes("/studio/") ||
      path.includes("/workflows/") ||
      path.includes("/swarm/")
    );
  };

  let days = readStreak().days;
  if (shouldRecordStudy()) {
    days = writeStreak(days.concat(isoOf(new Date())));
  }
  const streak = computeStreak(days);

  // Sync streak into active learner profile
  saveActiveProfile((p) => {
    p.activity_days = Array.from(new Set([...(p.activity_days || []), ...days]));
  });

  // ---------------------------------------------------------------------------
  // 2. Topbar Account Icon & Cross-Tab Signed-In Hydration
  // ---------------------------------------------------------------------------
  function signOutActiveUser() {
    const store = loadStore();
    store.currentUser = null;
    try { sessionStorage.setItem("ev:explicit_logout", "1"); } catch (_) {}
    saveStore(store);
    safely("hydrateNavigation", hydrateNavigation);
    toast("Signed out of your EngineVerse session.", "info");
    window.location.href = `${BASE}login/`;
  }

  function hydrateNavigation() {
    const store = loadStore();
    const profile = getActiveProfile();
    const signedIn = Boolean(store.currentUser && store.currentUser !== "guest");
    syncGlobalAuthFlag(store.currentUser);

    const topbarRight = document.querySelector(".topbar-right") || document.querySelector(".topbar .actions");
    if (topbarRight) {
      const loginLinks = Array.from(topbarRight.querySelectorAll('a[href*="/login"], a[href*="/register"], [data-ev-anon-auth]'));
      const serverAvatar = topbarRight.querySelector(".avatar:not([data-live-avatar])");
      const navToggle = topbarRight.querySelector("#navtoggle");
      const insertBeforeNode = navToggle || null;

      if (signedIn) {
        // Hide "Sign in" and "Start free" buttons in the topbar
        loginLinks.forEach((el) => {
          el.setAttribute("data-ev-anon-auth", "");
          el.hidden = true;
          el.style.display = "none";
        });

        if (!serverAvatar) {
          // 1. Streak badge
          let streakEl = topbarRight.querySelector("[data-live-streak]");
          if (!streakEl) {
            streakEl = document.createElement("a");
            streakEl.className = "streak";
            streakEl.setAttribute("data-live-streak", "");
            topbarRight.insertBefore(streakEl, insertBeforeNode);
          }
          const sDays = Number(profile.streak_days || streak.current || 0);
          streakEl.href = `${BASE}streaks/`;
          streakEl.title = sDays > 0 ? `Study streak: ${sDays} day(s)` : "No study day yet — open a topic or DPP to start";
          streakEl.innerHTML = `<svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2c1 4 4 6 4 10a4 4 0 1 1-8 0c0-2 1-3 2-5 1 2 2 2 2-5z"/><path d="M8.5 14.5A3.5 3.5 0 0 0 12 18a3.5 3.5 0 0 0 3.5-3.5c0-2-1.5-3-2-5-1 1.5-2.5 2-3.5 5z"/></svg><span>${sDays}</span>`;

          // 2. XP & Level badge
          let xpEl = topbarRight.querySelector("[data-live-xp]");
          if (!xpEl) {
            xpEl = document.createElement("a");
            xpEl.className = "xpchip";
            xpEl.setAttribute("data-live-xp", "");
            topbarRight.insertBefore(xpEl, insertBeforeNode);
          }
          const lvl = Number(profile.level || 1);
          const xpVal = Number(profile.xp || 0);
          xpEl.href = `${BASE}profile/`;
          xpEl.title = `Level ${lvl} · ${xpVal} XP`;
          xpEl.innerHTML = `<span class="lvl">Lv ${lvl}</span><span class="xpv">${xpVal} XP</span>`;

          // 3. Notifications bell icon
          let notifEl = topbarRight.querySelector("[data-live-notif]");
          if (!notifEl) {
            notifEl = document.createElement("a");
            notifEl.className = "iconbtn";
            notifEl.setAttribute("data-live-notif", "");
            notifEl.setAttribute("aria-label", "Notifications");
            notifEl.title = "Notifications";
            topbarRight.insertBefore(notifEl, insertBeforeNode);
          }
          notifEl.href = `${BASE}notifications/`;
          notifEl.innerHTML = `<svg class="i" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>`;

          // 4. Account Profile Icon & Dropdown Menu (replaces Sign in / Start free)
          let accountMenu = topbarRight.querySelector("[data-live-account-menu]");
          if (!accountMenu) {
            accountMenu = document.createElement("div");
            accountMenu.className = "menu";
            accountMenu.setAttribute("data-menu", "");
            accountMenu.setAttribute("data-live-account-menu", "");
            topbarRight.insertBefore(accountMenu, insertBeforeNode);
          }
          const initial = escapeHtml(String(profile.display_name || profile.username || "U").trim().charAt(0).toUpperCase() || "U");
          const unameEsc = escapeHtml(profile.username || "learner");
          const dnameEsc = escapeHtml(profile.display_name || profile.username || "Learner");
          const branchEsc = escapeHtml(String(profile.branch || "cse").toUpperCase());
          const yearEsc = Number(profile.year_of_study || 1);
          accountMenu.innerHTML = `
            <button class="avatar" type="button" data-live-avatar aria-haspopup="true" aria-expanded="false" aria-label="Account menu for ${unameEsc}" title="Signed in as @${unameEsc}">
              <svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              <span class="avatar-initial">${initial}</span>
            </button>
            <div class="menu-pop" role="menu">
              <div class="menu-head">
                <strong>${dnameEsc}</strong>
                <span class="muted small">@${unameEsc} · ${branchEsc} Y${yearEsc}</span>
              </div>
              <a class="menu-item" role="menuitem" href="${BASE}dashboard/"><svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg> Dashboard</a>
              <a class="menu-item" role="menuitem" href="${BASE}profile/"><svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> My profile</a>
              <a class="menu-item" role="menuitem" href="${BASE}portfolio/"><svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg> Public portfolio</a>
              <a class="menu-item" role="menuitem" href="${BASE}today/"><svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg> Today's plan</a>
              <a class="menu-item" role="menuitem" href="${BASE}mistakes/"><svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg> Mistake notebook</a>
              <a class="menu-item" role="menuitem" href="${BASE}leaderboard/"><svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg> Leaderboard</a>
              <a class="menu-item" role="menuitem" href="${BASE}settings/"><svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> Settings &amp; GitHub Sync</a>
              <button class="menu-item danger" type="button" data-live-logout><svg class="i" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg> Sign out</button>
            </div>
          `;
          const logoutBtn = accountMenu.querySelector("[data-live-logout]");
          if (logoutBtn) {
            logoutBtn.addEventListener("click", (e) => {
              e.preventDefault();
              signOutActiveUser();
            });
          }
        }
      } else {
        // Signed out: remove dynamic signed-in topbar items and restore Sign in / Start free
        topbarRight.querySelectorAll("[data-live-streak], [data-live-xp], [data-live-notif], [data-live-account-menu]").forEach((el) => el.remove());
        loginLinks.forEach((el) => {
          el.hidden = false;
          el.style.display = "";
        });
      }
    }

    // Remove "sign in" lock pills across topnav, mobile drawer, and index lists when signed in
    document.querySelectorAll(".navmenu-lock, .indexlist-lock").forEach((badge) => {
      badge.hidden = signedIn;
      badge.style.display = signedIn ? "none" : "";
    });

    // Update topnav and mobile nav links that differ between anonymous and signed-in
    if (signedIn) {
      const branchSlug = encodeURIComponent(profile.branch || "cse");
      document.querySelectorAll('.navmenu-item, .mobilenav-item').forEach((link) => {
        const label = link.querySelector(".navmenu-label")?.textContent?.trim() || link.textContent.trim();
        if (label.startsWith("My branch")) {
          link.setAttribute("href", `${BASE}stream/${branchSlug}/`);
        } else if (label.startsWith("Due flashcards")) {
          link.setAttribute("href", `${BASE}revision/`);
        }
      });

      // Update mobile drawer account buttons
      const mobileCta = document.querySelector("#mobilenav .mobilenav-cta");
      if (mobileCta) {
        mobileCta.innerHTML = `
          <a class="btn btn-primary" href="${BASE}dashboard/">@${escapeHtml(profile.username)} · Dashboard</a>
          <a class="btn btn-ghost" href="${BASE}settings/">Account &amp; Sync Settings</a>
          <button class="btn btn-ghost" type="button" data-live-mobile-logout>Sign out</button>
        `;
        mobileCta.querySelector("[data-live-mobile-logout]")?.addEventListener("click", signOutActiveUser);
      }

      // Update footer Sign in / Create account links
      document.querySelectorAll('.footer a[href*="/login"], .footer a[href*="/register"]').forEach((a) => {
        if (a.getAttribute("href")?.includes("/login")) {
          a.setAttribute("href", `${BASE}dashboard/`);
          a.textContent = `Dashboard (@${profile.username})`;
        } else {
          a.setAttribute("href", `${BASE}settings/`);
          a.textContent = "Account settings";
        }
      });
    }
  }

  // Hydrate page-specific signed-out callouts so switching tabs never shows "Sign in to..." when signed in
  function hydrateSignedInPageContent() {
    const store = loadStore();
    const signedIn = Boolean(store.currentUser && store.currentUser !== "guest");
    if (!signedIn) return;
    const profile = getActiveProfile();
    // `path` was read here without ever being defined in this scope - it only
    // existed inside shouldRecordStudy() - so every check below threw a
    // ReferenceError on the first page that used one. That is why a signed-in
    // learner kept meeting "Sign in to ..." prompts on the revision, sheets,
    // DPP, community and coding tabs.
    const path = window.location.pathname;

    // 1. Generic anonymous auth callouts across tabs (Sheets, DPP, Home, Resources)
    document.querySelectorAll(".callout").forEach((callout) => {
      const text = callout.textContent || "";
      if (text.includes("Sign in to have your progress on this sheet tracked")) {
        const rows = document.querySelectorAll("table.table tbody tr");
        const total = rows.length || 1;
        let solvedOnSheet = 0;
        const solvedSet = new Set(profile.solved_problems || []);
        rows.forEach((tr) => {
          const link = tr.querySelector('a[href*="/practice/problems/"]');
          const slug = link?.getAttribute("href")?.split("/practice/problems/")[1]?.replace(/\/$/, "");
          if (slug && solvedSet.has(slug)) {
            solvedOnSheet += 1;
            const statusCell = tr.querySelector("td:last-child");
            if (statusCell && !statusCell.querySelector(".chip.ok")) {
              statusCell.innerHTML = '<span class="chip ok">Solved ✓</span>';
            }
          }
        });
        const pct = Math.round((solvedOnSheet / total) * 100);
        callout.className = "panel mb";
        callout.innerHTML = `
          <div class="row between">
            <div><strong>Your progress (@${escapeHtml(profile.username)})</strong> — ${solvedOnSheet} of ${ rows.length } solved (${pct}%)</div>
            <span class="chip ${pct === 100 ? "ok" : "info"}">${pct}% complete</span>
          </div>
          <div class="bar lg mt-xs"><span style="width:${pct}%"></span></div>
        `;
      } else if (text.includes("Sign in to record answers, build a streak and get a mistake notebook")) {
        callout.className = "callout ok mt";
        callout.innerHTML = `
          <strong>Signed in as @${escapeHtml(profile.username)}:</strong>
          Your answers on this Daily Practice set are automatically recorded to your
          <a href="${BASE}streaks/">${profile.streak_days || 0}-day streak</a>,
          <a href="${BASE}mistakes/">Mistake Notebook</a>, and
          <a href="${BASE}dashboard/">Learner Dashboard</a> (${profile.xp || 0} XP).
        `;
      } else if (text.includes("Code execution is off on this server")) {
        callout.remove();
      }
    });

    // 2. Revise / Spaced Repetition tab (/revision/)
    if (path.endsWith("/revision/") || path.endsWith("/revision/index.html")) {
      const anonPanel = Array.from(document.querySelectorAll(".panel")).find((p) =>
        (p.textContent || "").includes("Sign in to start revising")
      );
      if (anonPanel) {
        anonPanel.innerHTML = `
          <div class="row between mb">
            <div>
              <h2>Due Flashcards for @${escapeHtml(profile.username)}</h2>
              <p class="small muted">Spaced-repetition SM-2 deck synced with your ${escapeHtml((profile.branch || "cse").toUpperCase())} learner profile.</p>
            </div>
            <span class="chip ok" id="ev-rev-counter">Card 1</span>
          </div>
          <div class="card p" id="ev-rev-card" style="min-height:150px">
            <div class="eyebrow" id="ev-rev-subject">Engineering Core</div>
            <h3 id="ev-rev-front" class="mt-xs">Loading flashcard deck...</h3>
            <div id="ev-rev-back" class="mt pt" style="border-top:1px solid var(--border)" hidden></div>
          </div>
          <div class="row mt" id="ev-rev-actions">
            <button class="btn btn-primary" type="button" id="ev-rev-flip">Show answer</button>
            <div class="row" id="ev-rev-rate" hidden>
              <button class="btn btn-ghost btn-sm" type="button" data-rev-q="1">Again (1d)</button>
              <button class="btn btn-soft btn-sm" type="button" data-rev-q="3">Hard (3d)</button>
              <button class="btn btn-primary btn-sm" type="button" data-rev-q="4">Good</button>
              <button class="btn btn-ok btn-sm" type="button" data-rev-q="5">Easy</button>
            </div>
          </div>
        `;
        fetchJSON(config.corpus || `${BASE}tutor-corpus.json`).then((corpus) => {
          const cards = (corpus?.chunks || []).slice(0, 24).map((c) => ({
            subject: c.subject || c.kind || "Core Engineering",
            front: `Explain the core principle and engineering trade-offs of: ${c.title}`,
            back: c.summary || c.excerpt || "Review the key invariant, complexity bounds, and failure modes.",
          }));
          if (!cards.length) {
            cards.push({
              subject: "Systems & Algorithms",
              front: "What is the time complexity of binary search on a sorted array of N elements?",
              back: "O(log N) comparisons because each probe halves the remaining search interval.",
            });
          }
          let idx = 0;
          const renderCard = () => {
            const card = cards[idx % cards.length];
            const counter = document.getElementById("ev-rev-counter");
            const subj = document.getElementById("ev-rev-subject");
            const front = document.getElementById("ev-rev-front");
            const back = document.getElementById("ev-rev-back");
            const flipBtn = document.getElementById("ev-rev-flip");
            const rateRow = document.getElementById("ev-rev-rate");
            if (counter) counter.textContent = `Card ${(idx % cards.length) + 1} of ${cards.length}`;
            if (subj) subj.textContent = card.subject;
            if (front) front.textContent = card.front;
            if (back) {
              back.textContent = card.back;
              back.hidden = true;
            }
            if (flipBtn) flipBtn.hidden = false;
            if (rateRow) rateRow.hidden = true;
          };
          renderCard();
          document.getElementById("ev-rev-flip")?.addEventListener("click", () => {
            const back = document.getElementById("ev-rev-back");
            const flipBtn = document.getElementById("ev-rev-flip");
            const rateRow = document.getElementById("ev-rev-rate");
            if (back) back.hidden = false;
            if (flipBtn) flipBtn.hidden = true;
            if (rateRow) rateRow.hidden = false;
          });
          anonPanel.querySelectorAll("[data-rev-q]").forEach((btn) => {
            btn.addEventListener("click", () => {
              // Flashcard XP mirrors the server (2 XP per review) but, under
              // knowledge XP, only the first rating of a card per day pays -
              // self-rating the same card "easy" in a loop must not farm XP.
              const cardKey = String(cards[idx]?.front || idx);
              const todayKey = isoOf(new Date());
              let gain = 0;
              saveActiveProfile((p) => {
                const ledger = (p.srs_xp_day && p.srs_xp_day.date === todayKey)
                  ? p.srs_xp_day : { date: todayKey, cards: [] };
                if (!ledger.cards.includes(cardKey)) {
                  ledger.cards.push(cardKey);
                  gain = 2;
                  p.xp = Number(p.xp || 0) + gain;
                }
                p.srs_xp_day = ledger;
              });
              safely("hydrateNavigation", hydrateNavigation);
              toast(gain ? "Card scheduled via SM-2 (+2 XP)" : "Card scheduled via SM-2");
              idx += 1;
              renderCard();
            });
          });
        });
      }
    }

    // 3. Coding Problem tab (/practice/problems/<slug>/)
    const problemView = document.querySelector(".problem-view[data-problem]");
    if (problemView) {
      const slug = problemView.getAttribute("data-problem") || "";
      problemView.querySelectorAll('a[href*="/login"]').forEach((a) => a.remove());
      if (slug && (profile.solved_problems || []).includes(slug)) {
        const solvedChip = document.getElementById("solved-chip");
        if (solvedChip) solvedChip.hidden = false;
      }
    }

    // 4. Community tab (/community/)
    if (path.includes("/community/")) {
      document.querySelectorAll('a[href*="/login"]').forEach((signInBtn) => {
        if ((signInBtn.textContent || "").toLowerCase().includes("sign in")) {
          const postBtn = document.createElement("button");
          postBtn.type = "button";
          postBtn.className = "btn btn-primary";
          postBtn.textContent = "New discussion post";
          signInBtn.replaceWith(postBtn);
          postBtn.addEventListener("click", () => {
            let box = document.getElementById("ev-live-community-composer");
            if (!box) {
              box = document.createElement("section");
              box.id = "ev-live-community-composer";
              box.className = "panel mb";
              box.innerHTML = `
                <h2>Start a Discussion as @${escapeHtml(profile.username)}</h2>
                <form id="ev-community-post-form" class="form">
                  <label class="field"><span>Title</span><input type="text" name="title" required maxlength="140" placeholder="Question or engineering insight..."></label>
                  <label class="field"><span>Details</span><textarea name="body" rows="3" required placeholder="Share your derivation, benchmark, or question..."></textarea></label>
                  <button class="btn btn-primary btn-sm" type="submit">Publish post (+10 XP)</button>
                </form>
              `;
              postBtn.closest(".page-head")?.after(box);
              box.querySelector("#ev-community-post-form")?.addEventListener("submit", (ev) => {
                ev.preventDefault();
                const fd = new FormData(ev.currentTarget);
                const title = String(fd.get("title") || "").trim();
                const body = String(fd.get("body") || "").trim();
                if (!title || !body) return;
                const updated = saveActiveProfile((p) => {
                  // Matches the server's community-post award (5 XP).
                  p.xp = Number(p.xp || 0) + 5;
                  p.community_posts = [{ title, body, ts: isoOf(new Date()) }].concat(p.community_posts || []).slice(0, 30);
                });
                pushSnapshotToGithub(updated).catch(() => {});
                safely("hydrateNavigation", hydrateNavigation);
                const list = document.querySelector(".list");
                if (list) {
                  const row = document.createElement("div");
                  row.className = "list-row";
                  row.innerHTML = `<div><strong>${escapeHtml(title)}</strong><div class="muted small">${escapeHtml(body)}</div><div class="muted small">by ${escapeHtml(updated.display_name)} (@${escapeHtml(updated.username)}) · just now</div></div><div class="right"><span class="chip ok">Published</span></div>`;
                  list.prepend(row);
                }
                box.remove();
                toast("Published discussion post (+5 XP)!");
              });
            }
          });
        }
      });
    }

    // 5. Home page hero & bottom CTA (/ or /index.html)
    if (path === BASE || path === `${BASE}index.html`) {
      document.querySelectorAll('a[href*="/register"], a[href*="/login"]').forEach((link) => {
        if (link.closest(".topbar-right") || link.closest(".footer")) return;
        link.href = `${BASE}dashboard/`;
        if ((link.textContent || "").toLowerCase().includes("create") || (link.textContent || "").toLowerCase().includes("start")) {
          link.textContent = `Open Dashboard (@${profile.username})`;
        } else if ((link.textContent || "").toLowerCase().includes("sign in")) {
          link.textContent = "My Progress & Streak";
          link.href = `${BASE}streaks/`;
        }
      });
    }

    // 6. Every other "Sign in to …" call to action in the catalogue.
    //
    // The exported pages are one anonymous snapshot served to everybody, so a
    // signed-in reader used to keep meeting prompts for a step they had already
    // taken: "Sign in to post" on the community tab, "Sign in to submit" beside
    // the run button, "Sign in to save a personal SM-2 schedule" on flashcards,
    // "Create an account or sign in to track your XP" on the hosting page. One
    // sweep covers them (and any page added later) instead of a special case per
    // template:
    //
    //   * an anchor that only exists to offer sign-in/sign-up becomes a link to
    //     the dashboard, or disappears when its container already offers an
    //     action (the practice page has its own Submit button);
    //   * the matching sentence, when the prompt is plain text, says who is
    //     signed in instead of asking again.
    const signInWord = /\bsign in\b|\bcreate (a free )?account\b|\bregister\b/i;
    const keepAction = (link) => {
      const container = link.closest(".row, .between, .page-head, .panel, .callout, p");
      if (!container) return false;
      const siblings = Array.from(container.querySelectorAll("a, button")).filter((el) => el !== link);
      return siblings.length === 0;
    };
    document.querySelectorAll("main a[href*='/login'], main a[href*='/register'], main a[href*='login/'], main a[href*='register/']").forEach((link) => {
      if (link.closest(".topbar-right") || link.closest(".footer") || link.closest("nav")) return;
      if (!signInWord.test(link.textContent || "")) return;
      if (keepAction(link)) {
        link.textContent = `Open dashboard (@${profile.username})`;
        link.href = `${BASE}dashboard/`;
        link.classList.remove("btn-primary");
        link.classList.add("btn-soft");
        return;
      }
      link.remove();
    });
    document.querySelectorAll("main p, main span, main div, main h2, main h3").forEach((node) => {
      // Only leaf elements that no longer carry a control of their own: a
      // paragraph that still has a link or a form is left exactly as it is.
      if (node.querySelector("a, button, input, select, textarea")) return;
      const text = node.textContent || "";
      if (!/sign in to /i.test(text)) return;
      node.textContent = text.replace(/sign in to /i, (match) =>
        match[0] === match[0].toUpperCase()
          ? `Signed in as @${profile.username} — `
          : `signed in as @${profile.username} — `
      );
    });
  }

  // The exported country rows used to hardcode a nine-option list *and* an
  // Indian placeholder, so a learner who chose +1 was still prompted with
  // "9876543210". The example now follows the selected plan, from the same table
  // the check itself runs against.
  function bindPhoneFieldHints() {
    document.querySelectorAll(".phone-cc-row").forEach((row) => {
      const select = row.querySelector("select");
      const input = row.querySelector("input");
      if (!select || !input || input.dataset.evPhoneHint) return;
      input.dataset.evPhoneHint = "1";
      const apply = () => {
        const plan = IDENTITY.plans[String(select.value || "+91")];
        if (plan && plan.example) {
          input.placeholder = plan.example.split(" ").slice(1).join(" ");
          input.title = `${plan.label} numbers look like ${plan.example}`;
        }
      };
      select.addEventListener("change", apply);
      apply();
    });
  }

  // Every boot step is isolated: an earlier revision called an undefined
  // helper here, which threw out of the IIFE and silently disabled the whole
  // runtime - no account icon, no OTP code, no streak calendar.
  const refreshSignedInUi = () => {
    safely("hydrateNavigation", hydrateNavigation);
    safely("hydrateSignedInPageContent", hydrateSignedInPageContent);
    safely("bindPhoneFieldHints", bindPhoneFieldHints);
  };

  refreshSignedInUi();
  safely("idbRestoreIfNeeded", () =>
    idbRestoreIfNeeded(() => {
      refreshSignedInUi();
      safely("renderAccountPage", renderAccountPage);
    })
  );
  safely("pullGithubVault", () =>
    pullGithubVault(true).then(() => {
      refreshSignedInUi();
      safely("renderAccountPage", renderAccountPage);
    })
  );

  // Synchronize auth and profile state immediately across tabs and back/forward navigation
  window.addEventListener("storage", (ev) => {
    if (!ev.key || ev.key === STORE_KEY || ev.key === SESSION_USER_KEY) {
      refreshSignedInUi();
    }
  });
  window.addEventListener("pageshow", refreshSignedInUi);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refreshSignedInUi();
    }
  });
  if (authChannel) {
    authChannel.addEventListener("message", refreshSignedInUi);
  }

  // ---------------------------------------------------------------------------
  // 3. DPP Calendar Rotation + Streak Page Rendering
  // ---------------------------------------------------------------------------
  const dppUrls = Array.isArray(config.dpp) ? config.dpp.filter(Boolean) : [];
  if (dppUrls.length) {
    const today = new Date();
    const pickUrl = (d) => {
      const iso = isoOf(d);
      const exact = dppUrls.find((u) => u.includes(`/dpp/${iso}`));
      if (exact) return exact;
      const pick = dppUrls[((dayIndex(d) % dppUrls.length) + dppUrls.length) % dppUrls.length];
      return `${pick}${pick.includes("?") ? "&" : "?"}day=${iso}`;
    };

    const todayLink = document.querySelector("[data-live-dpp-today]");
    if (todayLink) todayLink.setAttribute("href", pickUrl(today));
    const dateLabel = document.querySelector("[data-live-dpp-date]");
    if (dateLabel) dateLabel.textContent = longDate(today);
    const titleNode = document.querySelector("[data-live-dpp-title]");
    if (titleNode) titleNode.textContent = `Daily Practice - ${longDate(today)}`;

    const dayList = document.querySelector("[data-live-dpp-days]");
    if (dayList) {
      const sampleRow = dayList.querySelector("a");
      const metaSample = sampleRow ? sampleRow.querySelector(".muted") : null;
      const metaSuffix = metaSample
        ? metaSample.textContent.replace(/^.*?(·\s*\d+\s*questions.*)$/i, "$1")
        : "· 5 questions · 20 min";
      dayList.replaceChildren();
      for (let offset = 0; offset < 14; offset += 1) {
        const d = addDays(today, -offset);
        const iso = isoOf(d);
        const a = document.createElement("a");
        a.className = "card row";
        a.style.justifyContent = "space-between";
        a.href = pickUrl(d);

        const left = document.createElement("div");
        const strong = document.createElement("strong");
        strong.textContent = offset === 0 ? `Today · ${longDate(d)}` : longDate(d);
        const meta = document.createElement("div");
        meta.className = "small muted";
        meta.textContent = `${iso} ${metaSuffix}`;
        left.append(strong, meta);

        const right = document.createElement("span");
        right.className = offset === 0 ? "chip accent" : "chip";
        right.textContent = offset === 0 ? "Open today's set" : "Open set";

        a.append(left, right);
        dayList.appendChild(a);
      }
    }

    const params = new URLSearchParams(location.search);
    const requested = parseIso(params.get("day"));
    if (requested && location.pathname.includes("/dpp/")) {
      const heading = document.querySelector("main h1");
      if (heading) heading.textContent = `Daily Practice - ${longDate(requested)}`;
      document.title = `Daily Practice - ${longDate(requested)} - EngineVerse`;
    }
  }

  const setText = (sel, val) => {
    document.querySelectorAll(sel).forEach((el) => {
      el.textContent = String(val);
    });
  };
  setText("[data-streak-current]", streak.current);
  setText("[data-streak-longest]", streak.longest);
  setText("[data-streak-total]", streak.total);

  // The per-browser card is only worth showing once this device has a day on
  // record. It ships hidden so a first-time visitor is not told "0 day streak"
  // by a counter that has never seen them.
  const localCard = document.getElementById("local-streak");
  if (localCard && streak.total > 0) localCard.hidden = false;

  const statusNode = document.querySelector("[data-streak-status]");
  if (statusNode) {
    if (streak.todayDone) {
      statusNode.textContent = `Checked in for ${longDate(new Date())}. Keep going tomorrow.`;
    } else if (streak.current > 0) {
      statusNode.textContent = `${streak.current}-day streak active. Open a note, DPP or problem today to extend it.`;
    } else {
      statusNode.textContent = "Open any topic note, today's DPP, or a coding problem to start your streak.";
    }
  }

  const checkInBtn = document.querySelector("[data-streak-checkin]");
  if (checkInBtn) {
    const refreshBtn = (done) => {
      checkInBtn.textContent = done ? "Checked in for today" : "Mark today studied";
      checkInBtn.disabled = done;
    };
    refreshBtn(streak.todayDone);
    checkInBtn.addEventListener("click", () => {
      const updated = computeStreak(writeStreak(readStreak().days.concat(isoOf(new Date()))));
      setText("[data-streak-current]", updated.current);
      setText("[data-streak-longest]", updated.longest);
      setText("[data-streak-total]", updated.total);
      refreshBtn(true);
      if (statusNode) {
        statusNode.textContent = `Checked in for ${longDate(new Date())}. Keep going tomorrow.`;
      }
      // No XP for checking in: under knowledge XP the streak itself is the
      // record of showing up; XP counts questions and problems passed.
      safely("hydrateNavigation", hydrateNavigation);
    });
  }

  const grid = document.querySelector("[data-streak-grid]");
  if (grid) {
    const activeSet = new Set(readStreak().days);
    const today = new Date();
    grid.replaceChildren();
    for (let offset = 27; offset >= 0; offset -= 1) {
      const d = addDays(today, -offset);
      const iso = isoOf(d);
      const done = activeSet.has(iso);
      const cell = document.createElement("div");
      cell.className = "panel tight";
      cell.style.textAlign = "center";
      if (done) {
        cell.style.borderColor = "var(--accent)";
        cell.style.background = "var(--accent-soft)";
      }
      const dayLabel = document.createElement("div");
      dayLabel.className = "tiny muted";
      dayLabel.textContent = shortDate(d);
      const state = document.createElement("div");
      state.className = "small";
      state.style.fontWeight = "600";
      state.textContent = done ? "Studied" : offset === 0 ? "Today" : "—";
      cell.append(dayLabel, state);
      grid.appendChild(cell);
    }
  }

  // ---------------------------------------------------------------------------
  // 4. Interactive Quiz & Checkpoint Grading (quiz-bank.json)
  // ---------------------------------------------------------------------------
  let quizBankPromise = null;
  function loadQuizBank() {
    if (!quizBankPromise) {
      const url = config.quizBank || `${BASE}quiz-bank.json`;
      quizBankPromise = fetch(url)
        .then((r) => (r.ok ? r.json() : {}))
        .catch(() => ({}));
    }
    return quizBankPromise;
  }

  window.EV_GRADE_QUIZ = async function (form) {
    const card = form.closest("[data-quiz]");
    if (!card) return;
    const qid = card.getAttribute("data-quiz") || "";
    const bank = await loadQuizBank();
    const item = bank[qid];
    const explain = card.querySelector(".explain");
    const badge = card.querySelector(".verdict-inline");
    const chosenRadio = form.querySelector("input[name='option']:checked");
    const textInput = form.querySelector("input[name='answer']");

    if (!chosenRadio && (!textInput || !textInput.value.trim())) {
      toast("Select an option or type an answer first.", "bad");
      return;
    }

    let isCorrect = false;
    let correctLabel = item?.correctLabel || "";
    const optionNodes = Array.from(form.querySelectorAll(".option"));
    optionNodes.forEach((n) => n.classList.remove("correct", "wrong"));

    if (item && chosenRadio) {
      const chosenIdx = Number(chosenRadio.value);
      isCorrect = chosenIdx === Number(item.correctIndex);
      if (optionNodes[chosenIdx]) {
        optionNodes[chosenIdx].classList.add(isCorrect ? "correct" : "wrong");
      }
      if (!isCorrect && item.correctIndex >= 0 && optionNodes[item.correctIndex]) {
        optionNodes[item.correctIndex].classList.add("correct");
      }
    } else if (item && textInput) {
      const given = textInput.value.trim().toLowerCase();
      const expected = String(item.answerText || "").trim().toLowerCase();
      isCorrect = Boolean(expected && (given === expected || Math.abs(Number(given) - Number(expected)) <= 1e-3));
      correctLabel = item.answerText || "";
    } else {
      // No bank entry for this question: nothing was graded. The previous
      // fallback declared the answer correct and paid XP for it, which made
      // browser XP meaningless. Say so instead and award nothing.
      toast("This question could not be graded in the browser copy — no XP awarded.", "bad");
      return;
    }

    if (explain) {
      if (!explain.textContent.trim() && item?.explanation) {
        explain.textContent = item.explanation;
      }
      explain.classList.add("on");
    }

    // Knowledge XP (owner decision, 2026-10-19), same rule as the server:
    // only the FIRST correct answer to a question pays - its difficulty
    // value, matching practice.record_answer - and wrong answers pay 0.
    // Browser XP is device-local state, so this stops honest accidents and
    // casual farming; it is not a security boundary.
    const XP_BY_DIFFICULTY = { easy: 5, beginner: 5, medium: 10, hard: 15, expert: 25 };
    const profileNow = getActiveProfile();
    const alreadySolvedQ = Array.isArray(profileNow.solved_questions)
      && profileNow.solved_questions.includes(qid);
    const xpGain = isCorrect && !alreadySolvedQ
      ? (XP_BY_DIFFICULTY[String(item.difficulty || "medium").toLowerCase()] || 10)
      : 0;

    if (badge) {
      badge.textContent = isCorrect
        ? (xpGain ? `Correct! +${xpGain} XP` : "Correct — already solved before, XP was earned then")
        : correctLabel
        ? `Not quite — Answer: ${correctLabel}`
        : "Review explanation below";
      badge.className = "verdict-inline chip " + (isCorrect ? "ok" : "bad");
      badge.style.display = "inline-block";
    }

    // Record XP and Mistake Notebook entry
    saveActiveProfile((p) => {
      p.quiz_attempts = (p.quiz_attempts || 0) + 1;
      if (isCorrect) {
        p.quiz_correct = (p.quiz_correct || 0) + 1;
        const solvedQ = new Set(Array.isArray(p.solved_questions) ? p.solved_questions : []);
        if (!solvedQ.has(qid)) {
          solvedQ.add(qid);
          p.xp = (p.xp || 0) + xpGain;
        }
        p.solved_questions = Array.from(solvedQ);
      } else {
        const mistakes = Array.isArray(p.mistakes) ? p.mistakes : [];
        if (!mistakes.some((m) => m.id === qid)) {
          mistakes.unshift({
            id: qid,
            stem: item?.stem || card.querySelector(".q-stem")?.textContent?.trim() || qid,
            correctLabel: correctLabel,
            explanation: item?.explanation || explain?.textContent?.trim() || "",
            topicTitle: item?.topicTitle || "",
            topicUrl: item?.topicUrl || location.pathname,
            ts: isoOf(new Date()),
          });
        }
        p.mistakes = mistakes.slice(0, 100);
      }
    });
    safely("hydrateNavigation", hydrateNavigation);
  };

  // ---------------------------------------------------------------------------
  // 5. Topic Completion, Bookmarks & Flashcards in the Browser
  // ---------------------------------------------------------------------------
  document.querySelectorAll("[data-complete-topic]").forEach((btn) => {
    const slug = btn.getAttribute("data-complete-topic");
    const profile = getActiveProfile();
    if (profile.completed_topics?.includes(slug)) {
      btn.textContent = "✓ Completed";
      btn.classList.add("btn-primary");
      btn.classList.remove("btn-ghost");
    }
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopImmediatePropagation();
      const updated = saveActiveProfile((p) => {
        const set = new Set(p.completed_topics || []);
        if (!set.has(slug)) {
          set.add(slug);
          p.xp = (p.xp || 0) + 25;
          toast("Topic marked complete! +25 XP");
        }
        p.completed_topics = Array.from(set);
      });
      if (updated.completed_topics.includes(slug)) {
        btn.textContent = "✓ Completed";
        btn.classList.add("btn-primary");
        btn.classList.remove("btn-ghost");
      }
      safely("hydrateNavigation", hydrateNavigation);
    }, true);
  });

  document.querySelectorAll("[data-bookmark]").forEach((btn) => {
    const key = `${btn.getAttribute("data-bookmark")}:${btn.getAttribute("data-id")}`;
    const profile = getActiveProfile();
    if (profile.bookmarks?.includes(key)) {
      btn.setAttribute("aria-pressed", "true");
      btn.textContent = "★ Saved";
    }
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopImmediatePropagation();
      const updated = saveActiveProfile((p) => {
        const set = new Set(p.bookmarks || []);
        if (set.has(key)) {
          set.delete(key);
          toast("Removed from saved items", "info");
        } else {
          set.add(key);
          toast("Saved to your profile!");
        }
        p.bookmarks = Array.from(set);
      });
      const saved = updated.bookmarks.includes(key);
      btn.setAttribute("aria-pressed", saved ? "true" : "false");
      btn.textContent = saved ? "★ Saved" : "☆ Save";
    }, true);
  });

  // ---------------------------------------------------------------------------
  // 5b. Isolated browser execution (Workers + CPython via Pyodide)
  //
  // Audit F-14/F-15 follow-up (owner decision, 2026-10-19). The old static
  // runner executed learner JavaScript with `new Function` IN THE PAGE
  // ORIGIN - submitted code could read the vault profile and identity digests
  // from localStorage, edit the DOM, and an infinite loop froze the tab. And
  // "Python" was a regex transpiler subset, not Python. Both are gone:
  //
  // * JavaScript now runs inside a dedicated Web Worker created from a Blob.
  //   A worker has no DOM and no access to the page; a runaway loop is ended
  //   with worker.terminate() from the main thread. (A worker is isolation
  //   from the page, not a security boundary against the learner's own
  //   browser - the code is theirs, in their browser, like devtools.)
  // * Python runs on real CPython compiled to WebAssembly (Pyodide), loaded
  //   lazily on first use from the same-origin `pyodide/` files the Pages
  //   workflow bundles (scripts/fetch_pyodide.py). Problem judging appends
  //   the exact driver the server judge appends (exported per problem), so
  //   stdin/stdout semantics cannot drift between the two copies. If the
  //   runtime files are absent, Python reports NOT RUN - never a substitute.
  // * Every other language runs on its real compiler/interpreter compiled
  //   to WebAssembly, vendored pinned and same-origin by
  //   scripts/fetch_browser_runtimes.py and verified end-to-end (compile +
  //   run + diagnostics per language) by scripts/check_browser_runtimes.js
  //   in the Pages workflow - see section 5c. A language whose runtime
  //   files are absent from runtimes/manifest.json reports NOT RUN here,
  //   exactly like a missing Pyodide: never simulated, never faked.
  // ---------------------------------------------------------------------------
  const EV_WORKER_TIMEOUT_MS = 12000;
  const EV_PYODIDE_BOOT_TIMEOUT_MS = 180000;
  const EV_PYODIDE_RUN_TIMEOUT_MS = 30000;

  // Live compiler progress bus so /compiler, /codelab and problem pages can
  // show real toolchain download/compile progress instead of appearing frozen.
  const _evStatusListeners = new Set();
  function evEmitStatus(lang, message) {
    if (!message) return;
    _evStatusListeners.forEach((fn) => {
      try { fn({ lang, message }); } catch (_) {}
    });
  }
  window.EV_ON_RUNTIME_STATUS = function (listener) {
    if (typeof listener !== "function") return () => {};
    _evStatusListeners.add(listener);
    return () => _evStatusListeners.delete(listener);
  };

  const _evJsWorkerSource = [
    "'use strict';",
    "function _evMakeEnv(rawStdin) {",
    "  const text = String(rawStdin == null ? '' : rawStdin);",
    "  const enc = new TextEncoder();",
    "  const dec = new TextDecoder('utf-8');",
    "  const stdinBytes = enc.encode(text);",
    "  const lines = text === '' ? [] : text.replace(/\\r\\n/g, '\\n').replace(/\\n$/, '').split('\\n');",
    "  let lineIdx = 0;",
    "  const logs = [];",
    "  const errs = [];",
    "  let stdoutRaw = '';",
    "  const fmtOne = function (a) {",
    "    if (a === null) return 'null';",
    "    if (a === undefined) return 'undefined';",
    "    if (typeof a === 'string') return a;",
    "    if (typeof a === 'bigint') return String(a) + 'n';",
    "    if (a instanceof Error) return a.stack || (a.name + ': ' + a.message);",
    "    if (typeof a === 'object') { try { return JSON.stringify(a); } catch (_) { return String(a); } }",
    "    return String(a);",
    "  };",
    "  const fmt = function (args) { return Array.prototype.map.call(args, fmtOne).join(' '); };",
    "  const pushOut = function (s) { stdoutRaw += String(s); };",
    "  const pushErr = function (s) { errs.push(String(s)); };",
    "  const cons = {",
    "    log: function () { const line = fmt(arguments); logs.push(line); stdoutRaw += line + '\\n'; },",
    "    info: function () { const line = fmt(arguments); logs.push(line); stdoutRaw += line + '\\n'; },",
    "    debug: function () { const line = fmt(arguments); logs.push(line); stdoutRaw += line + '\\n'; },",
    "    dir: function (o) { const line = fmtOne(o); logs.push(line); stdoutRaw += line + '\\n'; },",
    "    table: function (o) { const line = fmtOne(o); logs.push(line); stdoutRaw += line + '\\n'; },",
    "    warn: function () { errs.push(fmt(arguments)); },",
    "    error: function () { errs.push(fmt(arguments)); },",
    "    assert: function (c) { if (!c) errs.push('Assertion failed: ' + fmt(Array.prototype.slice.call(arguments, 1))); },",
    "    time: function () {},",
    "    timeEnd: function () {},",
    "    clear: function () {}",
    "  };",
    "  const vfs = new Map([['/dev/stdin', stdinBytes]]);",
    "  const norm = function (p) { return '/' + String(p || '').replace(/\\\\/g, '/').split('/').filter(Boolean).join('/'); };",
    "  const mkBuf = function (src, encoding) {",
    "    const u8 = src instanceof Uint8Array ? new Uint8Array(src) : enc.encode(String(src == null ? '' : src));",
    "    u8.toString = function (mode) {",
    "      const m = String(mode || 'utf8').toLowerCase();",
    "      if (m === 'hex') return Array.from(u8).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');",
    "      if (m === 'base64') { let b = ''; for (let i = 0; i < u8.length; i++) b += String.fromCharCode(u8[i]); return btoa(b); }",
    "      return dec.decode(u8);",
    "    };",
    "    return u8;",
    "  };",
    "  const BufferShim = function (v, e) { return mkBuf(v, e); };",
    "  BufferShim.from = mkBuf;",
    "  BufferShim.alloc = function (n, fill) { const u = mkBuf(new Uint8Array(Number(n) || 0)); if (fill !== undefined) u.fill(typeof fill === 'string' ? fill.charCodeAt(0) : Number(fill) || 0); return u; };",
    "  BufferShim.allocUnsafe = function (n) { return mkBuf(new Uint8Array(Number(n) || 0)); };",
    "  BufferShim.isBuffer = function (v) { return v instanceof Uint8Array; };",
    "  BufferShim.byteLength = function (s) { return typeof s === 'string' ? enc.encode(s).length : (s ? s.byteLength || 0 : 0); };",
    "  BufferShim.concat = function (list) {",
    "    const total = list.reduce(function (s, b) { return s + b.length; }, 0);",
    "    const out = new Uint8Array(total); let off = 0;",
    "    for (let i = 0; i < list.length; i++) { out.set(list[i], off); off += list[i].length; }",
    "    return mkBuf(out);",
    "  };",
    "  const fsMod = {",
    "    readFileSync: function (target, opts) {",
    "      let bytes;",
    "      if (target === 0 || target === '/dev/stdin' || target === '/dev/fd/0') bytes = stdinBytes;",
    "      else { const k = norm(target); if (!vfs.has(k)) throw new Error('ENOENT: no such file or directory, open ' + target); bytes = vfs.get(k); }",
    "      const e = typeof opts === 'string' ? opts : opts && opts.encoding;",
    "      return e ? mkBuf(bytes).toString(e) : mkBuf(bytes);",
    "    },",
    "    writeFileSync: function (target, data) {",
    "      if (target === 1 || target === '/dev/stdout') { pushOut(data); return; }",
    "      if (target === 2 || target === '/dev/stderr') { pushErr(data); return; }",
    "      vfs.set(norm(target), data instanceof Uint8Array ? new Uint8Array(data) : enc.encode(String(data)));",
    "    },",
    "    appendFileSync: function (target, data) {",
    "      const k = norm(target); const prev = vfs.get(k) || new Uint8Array(0);",
    "      const add = data instanceof Uint8Array ? data : enc.encode(String(data));",
    "      vfs.set(k, BufferShim.concat([prev, add]));",
    "    },",
    "    existsSync: function (target) { return target === 0 || target === '/dev/stdin' || vfs.has(norm(target)); },",
    "    mkdirSync: function () {},",
    "    unlinkSync: function (target) { vfs.delete(norm(target)); }",
    "  };",
    "  fsMod.promises = { readFile: async function (t, o) { return fsMod.readFileSync(t, o); }, writeFile: async function (t, d) { fsMod.writeFileSync(t, d); } };",
    "  const pathMod = {",
    "    sep: '/', delimiter: ':',",
    "    join: function () { return Array.prototype.slice.call(arguments).filter(Boolean).join('/').replace(/\\/+/g, '/'); },",
    "    resolve: function () { return norm('/tmp/' + Array.prototype.slice.call(arguments).join('/')); },",
    "    basename: function (p) { return String(p || '').split('/').pop() || ''; },",
    "    dirname: function (p) { const n = norm(p); const i = n.lastIndexOf('/'); return i <= 0 ? '/' : n.slice(0, i); },",
    "    extname: function (p) { const b = String(p || '').split('/').pop() || ''; const i = b.lastIndexOf('.'); return i <= 0 ? '' : b.slice(i); }",
    "  };",
    "  const assertFn = function (v, m) { if (!v) throw new Error(m || 'Assertion failed'); };",
    "  assertFn.ok = assertFn;",
    "  assertFn.equal = function (a, b, m) { assertFn(a == b, m); };",
    "  assertFn.strictEqual = function (a, b, m) { assertFn(Object.is(a, b), m); };",
    "  assertFn.deepEqual = function (a, b, m) { assertFn(JSON.stringify(a) === JSON.stringify(b), m); };",
    "  assertFn.deepStrictEqual = assertFn.deepEqual;",
    "  const readlineMod = {",
    "    createInterface: function () {",
    "      const handlers = { line: [], close: [] }; let pumped = false;",
    "      const pump = function () { if (pumped) return; pumped = true; queueMicrotask(function () { lines.forEach(function (l) { handlers.line.forEach(function (f) { f(l); }); }); handlers.close.forEach(function (f) { f(); }); }); };",
    "      const rl = {",
    "        on: function (ev, fn) { if (handlers[ev]) { handlers[ev].push(fn); pump(); } return rl; },",
    "        close: function () {},",
    "        question: function (q, cb) { if (q) pushOut(q); cb(lineIdx < lines.length ? lines[lineIdx++] : ''); }",
    "      };",
    "      rl[Symbol.asyncIterator] = async function* () { for (let i = 0; i < lines.length; i++) yield lines[i]; };",
    "      return rl;",
    "    }",
    "  };",
    "  let exitCode = 0;",
    "  const ExitSignal = function (c) { this.evExit = true; this.code = Number(c) || 0; };",
    "  const stdinEmitter = { on: function (ev, fn) { queueMicrotask(function () { if (ev === 'data' && text.length) fn(text); if (ev === 'end') fn(); }); return stdinEmitter; }, setEncoding: function () { return stdinEmitter; }, resume: function () { return stdinEmitter; } };",
    "  const proc = {",
    "    argv: ['node', '/tmp/main.js'], env: { NODE_ENV: 'production', HOME: '/tmp' },",
    "    platform: 'linux', arch: 'wasm32', version: 'v22.0.0', cwd: function () { return '/tmp'; },",
    "    stdin: stdinEmitter,",
    "    stdout: { write: function (s) { pushOut(s); return true; } },",
    "    stderr: { write: function (s) { pushErr(s); return true; } },",
    "    nextTick: function (fn) { const a = Array.prototype.slice.call(arguments, 1); queueMicrotask(function () { fn.apply(null, a); }); },",
    "    exit: function (c) { throw new ExitSignal(c); },",
    "    hrtime: Object.assign(function () { return [0, Math.round(performance.now() * 1e6)]; }, { bigint: function () { return BigInt(Math.round(performance.now() * 1e6)); } })",
    "  };",
    "  const mods = { fs: fsMod, 'fs/promises': fsMod.promises, path: pathMod, assert: assertFn, 'assert/strict': assertFn, readline: readlineMod, util: { format: function () { return fmt(arguments); }, inspect: fmtOne, TextEncoder: TextEncoder, TextDecoder: TextDecoder }, os: { EOL: '\\n', platform: function () { return 'linux'; }, tmpdir: function () { return '/tmp'; } }, buffer: { Buffer: BufferShim }, crypto: { randomUUID: function () { return crypto.randomUUID(); } }, url: { URL: URL, URLSearchParams: URLSearchParams }, perf_hooks: { performance: performance } };",
    "  const req = function (id) { const k = String(id || '').replace(/^node:/, ''); if (Object.prototype.hasOwnProperty.call(mods, k)) return mods[k]; throw new Error(\"Cannot find module '\" + id + \"'\"); };",
    "  const rlLine = function () { return lineIdx < lines.length ? lines[lineIdx++] : null; };",
    "  return { cons: cons, logs: logs, errs: errs, getStdout: function () { return stdoutRaw; }, req: req, proc: proc, BufferShim: BufferShim, rlLine: rlLine, text: text, ExitSignal: ExitSignal, getExit: function () { return exitCode; }, setExit: function (c) { exitCode = c; } };",
    "}",
    "self.onmessage = async function (ev) {",
    "  const msg = ev.data || {};",
    "  const env = _evMakeEnv(msg.stdin);",
    "  self.__STDIN__ = env.text;",
    "  self.Buffer = env.BufferShim;",
    "  self.process = env.proc;",
    "  try {",
    "    if (msg.mode === 'raw') {",
    "      const modObj = { exports: {} };",
    "      const run = new Function('require', 'module', 'exports', '__filename', '__dirname', 'process', 'Buffer', 'console', 'stdin', 'input', 'readline', 'print', '{ ' + String(msg.code || '') + '\\n}');",
    "      const ret = run(env.req, modObj, modObj.exports, '/tmp/main.js', '/tmp', env.proc, env.BufferShim, env.cons, env.text, env.text, env.rlLine, env.cons.log);",
    "      if (ret && typeof ret.then === 'function') await ret;",
    "      await new Promise(function (r) { setTimeout(r, 0); });",
    "      self.postMessage({ id: msg.id, ok: env.getExit() === 0, stdout: env.getStdout(), stderr: env.errs.join('\\n'), logs: env.logs, exitCode: env.getExit(), error: env.getExit() !== 0 ? (env.errs.join('\\n') || ('Exited with code ' + env.getExit())) : '' });",
    "      return;",
    "    }",
    "    const entry = String(msg.entry || 'solution');",
    "    const modObj = { exports: {} };",
    "    const factory = new Function('require', 'module', 'exports', 'process', 'Buffer', 'console', '{ ' + String(msg.code || '') + '\\nreturn typeof ' + entry + ' !== \"undefined\" ? ' + entry + ' : null;\\n}');",
    "    const fn = factory(env.req, modObj, modObj.exports, env.proc, env.BufferShim, env.cons);",
    "    if (typeof fn !== 'function') {",
    "      self.postMessage({ id: msg.id, ok: false, logs: env.logs, stdout: env.getStdout(), stderr: env.errs.join('\\n'), error: 'Entry point ' + entry + ' is not defined as a function/class in your code.' });",
    "      return;",
    "    }",
    "    if (msg.lru) {",
    "      const cmds = msg.args && msg.args[0] || [];",
    "      const inst = new fn(Number(cmds[0] || 2));",
    "      const gets = [];",
    "      cmds.slice(1).forEach(function (c) {",
    "        const parts = String(c).split(/\\s+/);",
    "        if (parts[0] === 'put') inst.put(Number(parts[1]), Number(parts[2]));",
    "        else if (parts[0] === 'get') gets.push(inst.get(Number(parts[1])));",
    "      });",
    "      self.postMessage({ id: msg.id, ok: true, logs: env.logs, stdout: env.getStdout(), stderr: env.errs.join('\\n'), value: gets.join(' ') });",
    "      return;",
    "    }",
    "    let value = fn.apply(null, msg.args || []);",
    "    if (value && typeof value.then === 'function') value = await value;",
    "    try { self.postMessage({ id: msg.id, ok: true, logs: env.logs, stdout: env.getStdout(), stderr: env.errs.join('\\n'), value: value }); }",
    "    catch (cloneErr) { self.postMessage({ id: msg.id, ok: true, logs: env.logs, stdout: env.getStdout(), stderr: env.errs.join('\\n'), value: undefined, cloneError: true }); }",
    "  } catch (err) {",
    "    if (err && err.evExit) {",
    "      self.postMessage({ id: msg.id, ok: err.code === 0, stdout: env.getStdout(), stderr: env.errs.join('\\n'), logs: env.logs, exitCode: err.code, error: err.code === 0 ? '' : (env.errs.join('\\n') || ('Exited with code ' + err.code)) });",
    "      return;",
    "    }",
    "    const errMsg = String(err && (err.stack || err.message) || err);",
    "    self.postMessage({ id: msg.id, ok: false, stdout: env.getStdout(), stderr: env.errs.concat([errMsg]).join('\\n'), logs: env.logs, error: errMsg });",
    "  }",
    "};",
  ].join("\n");

  let _evJsWorker = null;
  let _evJsSeq = 0;
  const _evJsPending = new Map();

  function _evJsWorkerGet() {
    if (_evJsWorker) return _evJsWorker;
    const url = URL.createObjectURL(new Blob([_evJsWorkerSource], { type: "text/javascript" }));
    _evJsWorker = new Worker(url);
    _evJsWorker.onmessage = (ev) => {
      const { id } = ev.data || {};
      const slot = _evJsPending.get(id);
      if (!slot) return;
      _evJsPending.delete(id);
      clearTimeout(slot.timer);
      slot.resolve(ev.data);
    };
    return _evJsWorker;
  }

  function runJavaScriptInWorker(payload) {
    if (typeof Worker === "undefined") {
      return Promise.resolve({
        ok: false, workerUnavailable: true,
        error: "This browser does not support Web Workers, so JavaScript cannot be run in isolation here.",
      });
    }
    return new Promise((resolve) => {
      const id = ++_evJsSeq;
      const timer = setTimeout(() => {
        // The only reliable way to stop a runaway loop: kill the worker.
        _evJsPending.delete(id);
        if (_evJsWorker) { _evJsWorker.terminate(); _evJsWorker = null; }
        resolve({ ok: false, timeout: true, logs: [], error: "Time limit exceeded (worker terminated)." });
      }, EV_WORKER_TIMEOUT_MS);
      _evJsPending.set(id, { resolve, timer });
      try {
        _evJsWorkerGet().postMessage(Object.assign({ id }, payload));
      } catch (err) {
        _evJsPending.delete(id);
        clearTimeout(timer);
        resolve({ ok: false, logs: [], error: String(err && err.message || err) });
      }
    });
  }

  const _evPyWorkerSource = [
    "'use strict';",
    "let pyodide = null;",
    "self.onmessage = function (ev) {",
    "  const msg = ev.data || {};",
    "  if (msg.type === 'init') {",
    "    self.postMessage({ type: 'progress', message: 'Loading CPython 3.12 WebAssembly runtime…' });",
    "    try { importScripts(msg.indexURL + 'pyodide.js'); }",
    "    catch (err) { self.postMessage({ type: 'init_error', error: 'Could not load pyodide.js: ' + String(err && err.message || err) }); return; }",
    "    loadPyodide({ indexURL: msg.indexURL }).then(function (instance) {",
    "      pyodide = instance;",
    "      self.postMessage({ type: 'ready' });",
    "    }, function (err) {",
    "      self.postMessage({ type: 'init_error', error: 'Pyodide failed to start: ' + String(err && err.message || err) });",
    "    });",
    "    return;",
    "  }",
    "  if (msg.type === 'run') {",
    "    if (!pyodide) { self.postMessage({ id: msg.id, ok: false, errorType: 'RuntimeError', error: 'Python runtime is not ready yet.', stdout: '', stderr: '' }); return; }",
    "    const outBytes = []; const errBytes = [];",
    "    const bytes = new TextEncoder().encode(String(msg.stdin || ''));",
    "    let pos = 0;",
    "    pyodide.setStdin({ stdin: function () { return pos < bytes.length ? bytes[pos++] : null; } });",
    "    pyodide.setStdout({ raw: function (ch) { outBytes.push(ch & 255); } });",
    "    pyodide.setStderr({ raw: function (ch) { errBytes.push(ch & 255); } });",
    "    const decodeUtf8 = function (arr) { return new TextDecoder('utf-8').decode(new Uint8Array(arr)); };",
    "    pyodide.runPythonAsync(String(msg.code || '')).then(function () {",
    "      return pyodide.runPythonAsync('import sys as _ev_s; _ev_s.stdout.flush(); _ev_s.stderr.flush()');",
    "    }).then(function () {",
    "      self.postMessage({ id: msg.id, ok: true, stdout: decodeUtf8(outBytes), stderr: decodeUtf8(errBytes) });",
    "    }, function (err) {",
    "      self.postMessage({ id: msg.id, ok: false, errorType: String(err && err.type || ''), error: String(err && err.message || err), stdout: decodeUtf8(outBytes), stderr: decodeUtf8(errBytes) });",
    "    });",
    "  }",
    "};",
  ].join("\n");

  let _evPyWorker = null;
  let _evPyReady = null;
  let _evPySeq = 0;
  const _evPyPending = new Map();

  function _evPyodideBase() {
    const raw = config.pyodide || `${BASE}pyodide/`;
    const abs = new URL(raw, window.location.href).href;
    return abs.endsWith("/") ? abs : `${abs}/`;
  }

  function ensurePyodide() {
    if (_evPyReady) return _evPyReady;
    _evPyReady = new Promise((resolve) => {
      if (typeof Worker === "undefined") {
        resolve({ ok: false, error: "This browser does not support Web Workers." });
        return;
      }
      const url = URL.createObjectURL(new Blob([_evPyWorkerSource], { type: "text/javascript" }));
      _evPyWorker = new Worker(url);
      const failTimer = setTimeout(() => {
        if (_evPyWorker) { _evPyWorker.terminate(); _evPyWorker = null; }
        _evPyReady = null;
        resolve({ ok: false, error: "The Python runtime did not start within 3 minutes." });
      }, EV_PYODIDE_BOOT_TIMEOUT_MS);
      _evPyWorker.onmessage = (ev) => {
        const data = ev.data || {};
        if (data.type === "progress") { evEmitStatus("python", data.message); return; }
        if (data.type === "ready") { clearTimeout(failTimer); resolve({ ok: true }); return; }
        if (data.type === "init_error") {
          clearTimeout(failTimer);
          if (_evPyWorker) { _evPyWorker.terminate(); _evPyWorker = null; }
          _evPyReady = null;
          resolve({ ok: false, error: data.error });
          return;
        }
        const slot = _evPyPending.get(data.id);
        if (slot) {
          _evPyPending.delete(data.id);
          clearTimeout(slot.timer);
          slot.resolve(data);
        }
      };
      _evPyWorker.onerror = (ev) => {
        clearTimeout(failTimer);
        if (_evPyWorker) { _evPyWorker.terminate(); _evPyWorker = null; }
        _evPyReady = null;
        resolve({ ok: false, error: String((ev && ev.message) || "Python worker script error") });
      };
      _evPyWorker.postMessage({ type: "init", indexURL: _evPyodideBase() });
    });
    return _evPyReady;
  }

  async function runPythonInBrowser(code, stdinText) {
    const ready = await ensurePyodide();
    if (!ready.ok) {
      return {
        status: "sandbox_unavailable", executed: false, stdout: "", runtimeMs: 0,
        via: "static copy",
        stderr: "Not run: the Python runtime (CPython via Pyodide/WebAssembly) is not available in this "
          + `copy. ${ready.error || ""} Your code was not executed - use the hosted EngineVerse Python `
          + "compiler, or a deployment that bundles the pyodide/ runtime files.",
      };
    }
    const t0 = performance.now();
    const result = await new Promise((resolve) => {
      const id = ++_evPySeq;
      const timer = setTimeout(() => {
        _evPyPending.delete(id);
        if (_evPyWorker) { _evPyWorker.terminate(); _evPyWorker = null; }
        _evPyReady = null; // next run rebuilds the interpreter
        resolve({ ok: false, timeout: true, stdout: "", stderr: "" });
      }, EV_PYODIDE_RUN_TIMEOUT_MS);
      _evPyPending.set(id, { resolve, timer });
      _evPyWorker.postMessage({ type: "run", id, code: String(code || ""), stdin: String(stdinText || "") });
    });
    const runtimeMs = Math.max(1, Math.round(performance.now() - t0));
    if (result.timeout) {
      return { status: "timeout", executed: true, stdout: "", stderr: "Time limit exceeded (Python worker terminated).", runtimeMs, via: "CPython in browser (Pyodide)" };
    }
    if (!result.ok) {
      if (result.errorType === "SystemExit") {
        return { status: "accepted", executed: true, stdout: result.stdout || "", stderr: result.stderr || "", runtimeMs, via: "CPython in browser (Pyodide)" };
      }
      return {
        status: result.errorType === "SyntaxError" ? "compile_error" : "runtime_error",
        executed: true,
        stdout: result.stdout || "",
        stderr: [result.stderr || "", result.error || ""].filter(Boolean).join("\n"),
        runtimeMs, via: "CPython in browser (Pyodide)",
      };
    }
    return { status: "accepted", executed: true, stdout: result.stdout || "", stderr: result.stderr || "", runtimeMs, via: "CPython in browser (Pyodide)" };
  }

  // ---------------------------------------------------------------------------
  // 5c. Vendored in-browser runtimes for every other language
  //
  // scripts/fetch_browser_runtimes.py vendors real compilers/interpreters -
  // pinned npm artifacts, same-origin, loaded lazily per language - under
  // runtimes/ with a manifest.json saying which languages this deployment
  // actually carries. The workers below are driven with the exact message
  // protocols scripts/check_browser_runtimes.js verifies in CI:
  //
  //   * ev-runtime-worker.js - Clang 22 (C/C++), the TypeScript compiler
  //     (full type checking), sql.js (SQLite) and GopherJS (Go) behind one
  //     adapter protocol;
  //   * runtimes/java/worker-java.js - OpenJDK's javac + the TeaVM AOT
  //     compiler (@live-codes/java-wasm);
  //   * runtimes/rust/worker.iife.js - rustc's Miri interpreter
  //     (@live-codes/rust-wasm + the wasm-rustc toolchain);
  //   * csharp-worker.js - the real Roslyn compiler on Blazor WebAssembly
  //     (@live-codes/blazor-wasm, the bundle the hosted judge runs).
  //
  // Known platform limits, labelled wherever they apply rather than hidden:
  // Go on GopherJS cannot read stdin; the Rust worker wraps snippets that
  // lack `fn main` instead of erroring like rustc. Everything else -
  // compilation, stdin, stdout, diagnostics, exit codes - is the real
  // toolchain's own behaviour, and a missing/failed runtime degrades to
  // NOT RUN for that language only.
  // ---------------------------------------------------------------------------
  const EV_RUNTIME_BOOT_TIMEOUT_MS = 300000;
  const EV_RUNTIME_RUN_TIMEOUT_MS = 45000;

  function evRuntimesBase() {
    const raw = config.runtimes || `${BASE}runtimes/`;
    const abs = new URL(raw, window.location.href).href;
    return abs.endsWith("/") ? abs : `${abs}/`;
  }

  let _evManifestPromise = null;
  function evLoadManifest() {
    if (_evManifestPromise) return _evManifestPromise;
    _evManifestPromise = (async () => {
      const base = evRuntimesBase();
      try {
        const res = await fetch(`${base}manifest.json`, { credentials: "omit" });
        if (!res.ok) throw new Error(`manifest.json: HTTP ${res.status}`);
        const manifest = await res.json();
        const languages = new Set();
        Object.values(manifest.runtimes || {}).forEach((rt) =>
          (rt.languages || []).forEach((l) => languages.add(l)));
        return { base, languages, tsLibs: (manifest.runtimes?.typescript?.libs) || [] };
      } catch (_) {
        // No vendored runtimes in this copy: every compiled language keeps
        // reporting NOT RUN, exactly as it did before they existed.
        return { base, languages: new Set(), tsLibs: [] };
      }
    })();
    return _evManifestPromise;
  }

  // Languages this copy can execute beyond JavaScript/Python, once the
  // vendored runtimes are known. CodeLab lights up its language pills
  // from this list; the compiler/problem pages read the same manifest.
  window.EV_RUNTIME_LANGUAGES = async () =>
    Array.from((await evLoadManifest()).languages).sort();

  function evWithTimeout(promise, ms, what) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        const err = new Error(`${what} timed out`);
        err.evTimeout = true;
        reject(err);
      }, ms);
      promise.then(
        (v) => { clearTimeout(timer); resolve(v); },
        (e) => { clearTimeout(timer); reject(e); }
      );
    });
  }

  // One persistent worker per engine, created lazily. Runs are serialized
  // (every engine holds per-run stdin/stdout state), toolchain download and
  // WebAssembly compilation run inside `boot` / `ensureLang` under
  // EV_RUNTIME_BOOT_TIMEOUT_MS (never eating into the per-program run clock),
  // and a run timeout terminates ONLY that worker so the next run rebuilds it.
  function evEngineSession(create) {
    let session = null;
    let chain = Promise.resolve();
    async function getSession(langHint) {
      if (!session) {
        const fresh = create();
        session = fresh;
        try {
          await evWithTimeout(fresh.boot(), EV_RUNTIME_BOOT_TIMEOUT_MS, "runtime boot");
        } catch (err) {
          try { fresh.worker.terminate(); } catch (_) {}
          if (session === fresh) session = null;
          throw err;
        }
      }
      if (langHint && typeof session.ensureLang === "function") {
        await evWithTimeout(session.ensureLang(langHint), EV_RUNTIME_BOOT_TIMEOUT_MS, `${langHint} runtime boot`);
      }
      return session;
    }
    return {
      warm(langHint) {
        const task = () => getSession(langHint);
        const result = chain.then(task, task);
        chain = result.catch(() => {});
        return result;
      },
      run(payload) {
        const task = async () => {
          const s = await getSession(payload && payload.lang);
          const tRunStart = performance.now();
          try {
            const raw = await evWithTimeout(s.run(payload), EV_RUNTIME_RUN_TIMEOUT_MS, "run");
            if (raw && typeof raw === "object" && raw.evExecMs == null) {
              raw.evExecMs = Math.max(1, Math.round(performance.now() - tRunStart));
            }
            return raw;
          } catch (err) {
            if (err && err.evTimeout) {
              try { s.worker.terminate(); } catch (_) {}
              if (session === s) session = null;
            }
            throw err;
          }
        };
        const result = chain.then(task, task);
        chain = result.catch(() => {});
        return result;
      },
    };
  }

  function evMakeAdapterEngine(engineName) {
    return evEngineSession(() => {
      const worker = new Worker(`${BASE}static/js/ev-runtime-worker.js`);
      let seq = 0;
      const pending = new Map();
      const bootedLangs = new Map();
      const rejectAll = (reason) => {
        pending.forEach((slot) => { try { slot.reject(reason); } catch (_) {} });
        pending.clear();
        bootedLangs.clear();
      };
      worker.onmessage = (ev) => {
        const msg = ev.data || {};
        if (msg.type === "progress") {
          evEmitStatus(msg.lang || engineName, msg.message);
          return;
        }
        if ((msg.type === "ready" || msg.type === "init-error" || msg.type === "result") && pending.has(msg.id)) {
          const slot = pending.get(msg.id);
          pending.delete(msg.id);
          if (msg.type === "init-error") slot.reject(new Error(msg.error || `Failed to initialise ${msg.lang || engineName}`));
          else slot.resolve(msg);
        }
      };
      worker.onerror = (ev) => {
        rejectAll(new Error(String((ev && ev.message) || `${engineName} worker error`)));
      };
      return {
        worker,
        boot: async () => {
          const m = await evLoadManifest();
          worker.postMessage({
            type: "assets",
            assets: {
              clang: `${m.base}clang/`,
              typescript: `${m.base}typescript/`,
              sql: `${m.base}sql/`,
              go: `${m.base}go/`,
              bash: `${m.base}bash/`,
              tsLibs: m.tsLibs,
            },
          });
        },
        ensureLang: (lang) => {
          if (!lang) return Promise.resolve();
          if (bootedLangs.has(lang)) return bootedLangs.get(lang);
          const p = new Promise((resolve, reject) => {
            const id = ++seq;
            pending.set(id, { resolve, reject });
            worker.postMessage({ type: "init", id, lang });
          }).catch((err) => {
            bootedLangs.delete(lang);
            throw err;
          });
          bootedLangs.set(lang, p);
          return p;
        },
        run: ({ lang, code, stdin }) =>
          new Promise((resolve, reject) => {
            const id = ++seq;
            pending.set(id, { resolve, reject });
            worker.postMessage({ type: "run", id, lang, code, stdin });
          }),
      };
    });
  }

  // Isolate heavy native/WASM toolchains into dedicated workers so a runaway
  // loop in C never tears down pre-warmed TypeScript, SQL, Go, or Bash state.
  const evAdapterEngine = evMakeAdapterEngine("clang");
  const evAdapterEngines = {
    c: evAdapterEngine,
    cpp: evAdapterEngine,
    typescript: evMakeAdapterEngine("typescript"),
    javascript: evMakeAdapterEngine("javascript"),
    sql: evMakeAdapterEngine("sql"),
    go: evMakeAdapterEngine("go"),
    bash: evMakeAdapterEngine("bash"),
  };

  const evJavaEngine = evEngineSession(() => {
    const base = `${evRuntimesBase()}java/`;
    const worker = new Worker(`${base}worker-java.js`);
    let bootSlot = null;
    let current = null;
    worker.onmessage = (ev) => {
      const msg = ev.data || {};
      if (msg.type === "initialized" && bootSlot) { const b = bootSlot; bootSlot = null; b.resolve(); return; }
      if (msg.type === "init-error" && bootSlot) {
        const b = bootSlot;
        bootSlot = null;
        b.reject(new Error(msg.error || "OpenJDK + TeaVM runtime failed to initialize"));
        return;
      }
      if (msg.type === "result" && current) { const c = current; current = null; c.resolve(msg); }
    };
    worker.onerror = (ev) => {
      const err = new Error(String((ev && ev.message) || "Java worker failed to load"));
      if (bootSlot) { const b = bootSlot; bootSlot = null; b.reject(err); }
      if (current) { const c = current; current = null; c.reject(err); }
    };
    return {
      worker,
      boot: () =>
        new Promise((resolve, reject) => {
          evEmitStatus("java", "Loading OpenJDK javac + TeaVM WebAssembly compiler…");
          bootSlot = { resolve, reject };
          worker.postMessage({ cmd: "init", baseUrl: `${base}teavm/`, persistFiles: false });
        }),
      run: ({ code, stdin, mainClass }) =>
        new Promise((resolve, reject) => {
          current = { resolve, reject };
          worker.postMessage({ cmd: "run", source: code, input: stdin, mainClass });
        }),
    };
  });

  const evRustEngine = evEngineSession(() => {
    const base = `${evRuntimesBase()}rust/`;
    const worker = new Worker(`${base}worker.iife.js`);
    let seq = 0;
    let bootSlot = null;
    const pending = new Map();
    worker.onmessage = (ev) => {
      const msg = ev.data || {};
      if (msg.type === "progress") {
        const n = msg.loaded || 0;
        const tot = msg.total || 0;
        evEmitStatus("rust", tot ? `Loading Rust compiler & standard library (${n}/${tot})…` : "Loading Rust compiler…");
        return;
      }
      if (msg.type === "ready" && bootSlot) { const b = bootSlot; bootSlot = null; b.resolve(); return; }
      if (msg.type === "error") {
        const err = new Error(msg.message || msg.error || "Rust toolchain failed to start");
        if (bootSlot) { const b = bootSlot; bootSlot = null; b.reject(err); return; }
        if (msg.id && pending.has(msg.id)) {
          const slot = pending.get(msg.id);
          pending.delete(msg.id);
          slot.reject(err);
        }
        return;
      }
      if (msg.type === "run-error" && pending.has(msg.id)) {
        const slot = pending.get(msg.id);
        pending.delete(msg.id);
        slot.resolve({ id: msg.id, stdout: "", stderr: String(msg.message || msg.error || "Rust execution failed"), exitCode: 1 });
        return;
      }
      if (msg.type === "result" && pending.has(msg.id)) {
        const slot = pending.get(msg.id);
        pending.delete(msg.id);
        slot.resolve(msg);
      }
    };
    worker.onerror = (ev) => {
      const err = new Error(String((ev && ev.message) || "Rust worker script error"));
      if (bootSlot) { const b = bootSlot; bootSlot = null; b.reject(err); }
      pending.forEach((slot) => { try { slot.reject(err); } catch (_) {} });
      pending.clear();
    };
    return {
      worker,
      boot: () =>
        new Promise((resolve, reject) => {
          evEmitStatus("rust", "Loading Rust compiler & Miri standard library…");
          bootSlot = { resolve, reject };
          worker.postMessage({ type: "init", toolchain: { baseUrl: `${base}toolchain/`, gzipped: true } });
        }),
      run: ({ code, stdin }) =>
        new Promise((resolve, reject) => {
          const id = ++seq;
          pending.set(id, { resolve, reject });
          worker.postMessage({ type: "run", id, code, input: stdin });
        }),
    };
  });

  const evCSharpEngine = evEngineSession(() => {
    const base = `${evRuntimesBase()}csharp/`;
    const worker = new Worker(`${BASE}static/js/csharp-worker.js`, { type: "module" });
    let seq = 0;
    let bootSlot = null;
    const pending = new Map();
    worker.onmessage = (ev) => {
      const msg = ev.data || {};
      if (msg.type === "progress") { evEmitStatus("csharp", msg.message); return; }
      if (msg.type === "ready" && bootSlot) { const b = bootSlot; bootSlot = null; b.resolve(); return; }
      if (msg.type === "init-error" && bootSlot) {
        const b = bootSlot;
        bootSlot = null;
        b.reject(new Error(msg.error || "the C# runtime failed to start"));
        return;
      }
      if (msg.type === "result" && pending.has(msg.id)) {
        const slot = pending.get(msg.id);
        pending.delete(msg.id);
        slot.resolve(msg);
      }
    };
    worker.onerror = (ev) => {
      const err = new Error(String((ev && ev.message) || "C# worker failed to load"));
      if (bootSlot) { const b = bootSlot; bootSlot = null; b.reject(err); }
      pending.forEach((slot) => { try { slot.reject(err); } catch (_) {} });
      pending.clear();
    };
    return {
      worker,
      boot: () =>
        new Promise((resolve, reject) => {
          evEmitStatus("csharp", "Loading Roslyn & .NET WebAssembly runtime…");
          bootSlot = { resolve, reject };
          worker.postMessage({ type: "init", baseUrl: base });
        }),
      run: ({ code, stdin }) =>
        new Promise((resolve, reject) => {
          const id = ++seq;
          pending.set(id, { resolve, reject });
          worker.postMessage({ type: "run", id, baseUrl: base, code, stdin });
        }),
    };
  });

  const EV_ENGINE_LABEL = {
    c: "Clang in browser (WebAssembly)",
    cpp: "Clang in browser (WebAssembly)",
    typescript: "TypeScript compiler in browser",
    javascript: "JavaScript worker in browser",
    sql: "SQLite in browser (WebAssembly)",
    go: "Go in browser (GopherJS)",
    bash: "Bash in browser",
    java: "OpenJDK + TeaVM in browser",
    rust: "rustc in browser (Miri/WebAssembly)",
    csharp: "Roslyn in browser (.NET WebAssembly)",
  };

  function evDetectJavaMainClass(source) {
    const cleaned = String(source || "")
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .replace(/\/\/[^\n]*/g, " ")
      .replace(/"(?:\\.|[^"\\])*"/g, '""');
    const pub = /\bpublic\s+(?:final\s+|abstract\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]{0,63})\b/.exec(cleaned);
    if (pub) return pub[1];
    const classes = [];
    const re = /\bclass\s+([A-Za-z_$][A-Za-z0-9_$]{0,63})\b/g;
    let m;
    while ((m = re.exec(cleaned)) !== null) {
      classes.push({ name: m[1], idx: m.index });
    }
    const mainPos = /\bstatic\s+void\s+main\s*\(/.exec(cleaned);
    if (mainPos && classes.length) {
      let chosen = classes[0].name;
      for (const c of classes) {
        if (c.idx <= mainPos.index) chosen = c.name;
      }
      return chosen;
    }
    return classes.length ? classes[0].name : "Main";
  }

  // Adapter/C# workers already return the judge's result shape.
  function evMapWorkerResult(raw, t0, via) {
    const status = (raw && raw.status) || "runtime_error";
    return {
      status,
      executed: status !== "sandbox_unavailable",
      stdout: (raw && raw.stdout) || "",
      stderr: (raw && raw.stderr) || "",
      compileOutput: (raw && raw.compileOutput) || "",
      exitCode: raw && raw.exitCode != null ? raw.exitCode : null,
      runtimeMs: Math.max(1, Math.round((raw && (raw.runtimeMs || raw.evExecMs)) || (performance.now() - t0))),
      via,
    };
  }

  function evMapJavaResult(raw, t0, via) {
    const runtimeMs = Math.max(1, Math.round((raw && raw.evExecMs) || (performance.now() - t0)));
    if (!raw) {
      return { status: "sandbox_unavailable", executed: false, stdout: "", stderr: "The Java runtime returned no result.", compileOutput: "", exitCode: null, runtimeMs, via };
    }
    if (raw.ok) {
      return { status: "accepted", executed: true, stdout: raw.stdout || "", stderr: raw.stderr || "", compileOutput: "", exitCode: 0, runtimeMs, via };
    }
    const diags = Array.isArray(raw.diagnostics) ? raw.diagnostics : [];
    let stderr = String(raw.stderr || "");
    if (!diags.length && raw.error) {
      // TeaVM reports the exception object separately; its first line is
      // the exception class/message a JVM would print - the wasm stack
      // frames under it are noise, so only the first line is appended.
      const firstLine = String(raw.error).split("\n")[0];
      if (firstLine && !stderr.includes(firstLine)) stderr = [stderr, firstLine].filter(Boolean).join("\n");
    }
    const compileError = diags.length > 0;
    return {
      status: compileError ? "compile_error" : "runtime_error",
      executed: true,
      stdout: raw.stdout || "",
      stderr,
      compileOutput: compileError ? stderr : "",
      exitCode: raw.exitCode != null ? raw.exitCode : 1,
      runtimeMs,
      via,
    };
  }

  function evMapRustResult(raw, t0, via) {
    const runtimeMs = Math.max(1, Math.round(performance.now() - t0));
    const stdout = (raw && raw.stdout) || "";
    const stderr = (raw && raw.stderr) || "";
    const exitCode = raw && raw.exitCode != null ? raw.exitCode : null;
    if (exitCode === 0) {
      return { status: "accepted", executed: true, stdout, stderr, compileOutput: "", exitCode, runtimeMs, via };
    }
    const compileError = !/panicked|Undefined Behavior/i.test(stderr) && /(^|\n)\s*error(\[|:)/.test(stderr);
    return {
      status: compileError ? "compile_error" : "runtime_error",
      executed: true,
      stdout,
      stderr,
      compileOutput: compileError ? stderr : "",
      exitCode: exitCode != null ? exitCode : 1,
      runtimeMs,
      via,
    };
  }

  window.EV_BROWSER_PREWARM = async function (lang) {
    try {
      if (!lang || lang === "javascript") {
        _evJsWorkerGet();
        return true;
      }
      if (lang === "python") {
        await ensurePyodide();
        return true;
      }
      const manifest = await evLoadManifest();
      if (!manifest.languages.has(lang)) return false;
      if (evAdapterEngines[lang]) { await evAdapterEngines[lang].warm(lang); return true; }
      if (lang === "java") { await evJavaEngine.warm("java"); return true; }
      if (lang === "rust") { await evRustEngine.warm("rust"); return true; }
      if (lang === "csharp") { await evCSharpEngine.warm("csharp"); return true; }
      return false;
    } catch (_) {
      return false;
    }
  };

  // Runs one program on the vendored runtime for `lang`. Returns null when
  // this deployment carries no runtime for the language (the caller then
  // reports NOT RUN); boot failures and timeouts are mapped, never thrown.
  async function evRuntimeRun(lang, code, stdinText) {
    const manifest = await evLoadManifest();
    if (!manifest.languages.has(lang)) return null;
    const t0 = performance.now();
    const via = EV_ENGINE_LABEL[lang] || "in-browser runtime";
    try {
      if (evAdapterEngines[lang]) {
        return evMapWorkerResult(
          await evAdapterEngines[lang].run({ lang, code: String(code || ""), stdin: String(stdinText || "") }),
          t0, via);
      }
      if (lang === "java") {
        return evMapJavaResult(
          await evJavaEngine.run({ code: String(code || ""), stdin: String(stdinText || ""), mainClass: evDetectJavaMainClass(code) }),
          t0, via);
      }
      if (lang === "rust") {
        return evMapRustResult(
          await evRustEngine.run({ code: String(code || ""), stdin: String(stdinText || "") }),
          t0, via);
      }
      if (lang === "csharp") {
        return evMapWorkerResult(
          await evCSharpEngine.run({ code: String(code || ""), stdin: String(stdinText || "") }),
          t0, via);
      }
      return null;
    } catch (err) {
      const runtimeMs = Math.max(1, Math.round(performance.now() - t0));
      if (err && err.evTimeout) {
        const msg = String((err && err.message) || "");
        if (/boot/i.test(msg)) {
          return {
            status: "sandbox_unavailable", executed: false, stdout: "", compileOutput: "", exitCode: null,
            stderr: `Not run: downloading/initialising the ${via} toolchain timed out on this connection. `
              + "Your code was not executed — tap Run again to resume from cached browser files.",
            runtimeMs, via: "static copy",
          };
        }
        return {
          status: "timeout", executed: true, stdout: "", compileOutput: "", exitCode: null,
          stderr: `Time limit exceeded (the ${lang} browser worker was terminated).`,
          runtimeMs, via,
        };
      }
      return {
        status: "sandbox_unavailable", executed: false, stdout: "", compileOutput: "", exitCode: null, runtimeMs: 0,
        stderr: `Not run: the ${via} runtime could not start in this browser (${String((err && err.message) || err)}). `
          + "Your code was not executed.",
        via: "static copy",
      };
    }
  }

  // Terminal used by the /compiler page on this static copy (app.js prefers
  // this over the API whenever the ev-live marker is present).
  window.EV_BROWSER_TERMINAL = async function (lang, code, stdinText) {
    const t0 = performance.now();
    if (!String(code || "").trim()) {
      return { status: "runtime_error", executed: true, stdout: "", stderr: "Editor is empty.", runtimeMs: 0, via: "static copy" };
    }
    if (lang === "python") return runPythonInBrowser(code, stdinText);
    if (lang === "javascript") {
      const r = await runJavaScriptInWorker({ mode: "raw", code, stdin: stdinText });
      const runtimeMs = Math.max(1, Math.round(performance.now() - t0));
      if (r.workerUnavailable) {
        return { status: "sandbox_unavailable", executed: false, stdout: "", stderr: `Not run: ${r.error}`, runtimeMs: 0, via: "static copy" };
      }
      const outText = r.stdout !== undefined ? r.stdout : (r.logs || []).join("\n");
      if (r.timeout) {
        return { status: "timeout", executed: true, stdout: outText, stderr: r.error, runtimeMs, via: "JavaScript worker" };
      }
      return {
        status: r.ok ? "accepted" : "runtime_error",
        executed: true,
        stdout: outText,
        stderr: r.ok ? (r.stderr || "") : (r.error || r.stderr || ""),
        exitCode: r.exitCode != null ? r.exitCode : (r.ok ? 0 : 1),
        runtimeMs,
        via: "JavaScript worker",
      };
    }
    // C, C++, Java, Rust, C#, TypeScript, Go, Bash and SQL run on the vendored
    // real toolchains (section 5c) whenever this deployment bundles them.
    const runtime = await evRuntimeRun(lang, code, stdinText);
    if (runtime) return runtime;
    return {
      status: "unsupported_language", executed: false, stdout: "", runtimeMs: 0, via: "static copy",
      stderr: `Not run: this copy of EngineVerse carries no browser runtime for ${String(lang).toUpperCase()}, `
        + "so it cannot compile or execute it here and will not pretend to. Your code was not executed. "
        + "JavaScript (worker) and Python (CPython via WebAssembly) run above; the hosted EngineVerse "
        + "compiler runs every language on its judge.",
    };
  };

  // ---------------------------------------------------------------------------
  // 6. Multi-Language In-Browser Coding Runner & Judge (/practice/problems/*)
  // ---------------------------------------------------------------------------
  const editor = document.getElementById("code-editor");
  if (editor) {
    const problemSlug = editor.getAttribute("data-problem");
    const langSelect = document.getElementById("lang-select");
    const customInput = document.getElementById("custom-input");
    const outputEl = document.getElementById("run-output");
    const runBtn = document.getElementById("btn-run");
    const submitBtn = document.getElementById("btn-submit");
    const resetBtn = document.getElementById("btn-reset");

    let problemsCatalogPromise = null;
    const loadProblemsCatalog = () => {
      if (!problemsCatalogPromise) {
        const url = config.codingProblems || `${BASE}coding-problems.json`;
        problemsCatalogPromise = fetch(url)
          .then((r) => (r.ok ? r.json() : {}))
          .catch(() => ({}));
      }
      return problemsCatalogPromise;
    };

    const EV_PROBLEM_FALLBACK_STUBS = {
      javascript: [
        'const fs = require("fs");',
        'const raw = fs.readFileSync(0, "utf8");',
        "",
        "// Read problem input from `raw` and print your answer with `console.log(...)`.",
        "console.log(raw.trim());",
        "",
      ].join("\n"),
      typescript: [
        'import * as fs from "fs";',
        'const raw: string = fs.readFileSync(0, "utf8");',
        "",
        "// Read problem input from `raw` and print your answer with `console.log(...)`.",
        "console.log(raw.trim());",
        "",
      ].join("\n"),
      c: [
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "#include <string.h>",
        "",
        "int main(void) {",
        "  // Read stdin and print your answer to stdout.",
        "  return 0;",
        "}",
        "",
      ].join("\n"),
      cpp: [
        "#include <iostream>",
        "#include <vector>",
        "#include <string>",
        "#include <algorithm>",
        "#include <unordered_map>",
        "using namespace std;",
        "",
        "int main() {",
        "  ios::sync_with_stdio(false);",
        "  cin.tie(nullptr);",
        "  // Read stdin and print your answer to stdout.",
        "  return 0;",
        "}",
        "",
      ].join("\n"),
      java: [
        "import java.io.*;",
        "import java.util.*;",
        "",
        "public class Main {",
        "  public static void main(String[] args) throws Exception {",
        "    Scanner sc = new Scanner(System.in);",
        "    // Read input from `sc` and print your answer with `System.out.println(...)`.",
        "  }",
        "}",
        "",
      ].join("\n"),
      csharp: [
        "using System;",
        "using System.Collections.Generic;",
        "using System.Linq;",
        "",
        "class Program {",
        "  static void Main() {",
        "    string input = Console.In.ReadToEnd();",
        "    // Parse `input` and write your answer with `Console.WriteLine(...)`.",
        "  }",
        "}",
        "",
      ].join("\n"),
      go: [
        "package main",
        "",
        "import (",
        '  "bufio"',
        '  "fmt"',
        '  "io"',
        '  "os"',
        ")",
        "",
        "func main() {",
        "  data, _ := io.ReadAll(bufio.NewReader(os.Stdin))",
        "  _ = data",
        "  // Parse `string(data)` and print your answer with `fmt.Println(...)`.",
        "}",
        "",
      ].join("\n"),
      rust: [
        "use std::io::{self, Read};",
        "",
        "fn main() {",
        "  let mut input = String::new();",
        "  io::stdin().read_to_string(&mut input).unwrap();",
        "  // Parse `input` and print your answer with `println!(...)`.",
        "}",
        "",
      ].join("\n"),
      sql: "-- Write your SQL query below.\nSELECT 1;\n",
    };

    window.EV_ON_RUNTIME_STATUS(({ lang, message }) => {
      if (!outputEl || !langSelect || langSelect.value !== lang) return;
      if ((runBtn && runBtn.disabled) || (submitBtn && submitBtn.disabled)) {
        outputEl.innerHTML = `<div class="muted small">${escapeHtml(message)}</div>`;
      }
    });

    langSelect?.addEventListener("change", () => {
      if (window.EV_BROWSER_PREWARM) window.EV_BROWSER_PREWARM(langSelect.value);
    });

    // Enable all language options and populate stubs from coding-problems.json
    loadProblemsCatalog().then((catalog) => {
      const prob = catalog[problemSlug];
      if (!prob || !langSelect) return;
      window.EV_STUBS = window.EV_STUBS || {};
      Object.entries(EV_PROBLEM_FALLBACK_STUBS).forEach(([lSlug, tmpl]) => {
        if (!window.EV_STUBS[lSlug]) window.EV_STUBS[lSlug] = tmpl;
      });
      Object.entries(prob.stubs || {}).forEach(([lSlug, info]) => {
        if (info.stub) window.EV_STUBS[lSlug] = info.stub;
      });
      // Every stub stays selectable for reading/editing. JavaScript (Web
      // Worker) and Python (real CPython via Pyodide) execute immediately;
      // the compiled languages and TypeScript/SQL light up once the
      // vendored-runtime manifest (runtimes/manifest.json) confirms this
      // deployment carries their real browser toolchains. Anything missing
      // there keeps its honest "cannot run here" label instead of being
      // silently enabled as if this static copy could compile it.
      const RUNNABLE_HERE = new Set(["javascript", "python"]);
      Array.from(langSelect.options).forEach((opt) => {
        opt.disabled = false;
        opt.textContent = opt.textContent.replace(/\s*\(starter only\)/i, "");
        if (!RUNNABLE_HERE.has(opt.value) && !/cannot run here/i.test(opt.textContent)) {
          opt.textContent = `${opt.textContent} (cannot run here)`;
        }
        if (opt.value === "python" && !/CPython/i.test(opt.textContent)) {
          opt.textContent = `${opt.textContent} (CPython in browser)`;
        }
      });
      evLoadManifest().then(({ languages }) => {
        Array.from(langSelect.options).forEach((opt) => {
          if (!languages.has(opt.value)) return;
          opt.textContent = opt.textContent.replace(/\s*\(cannot run here\)/i, "");
          if (!/in browser/i.test(opt.textContent)) {
            opt.textContent = `${opt.textContent} (in browser)`;
          }
        });
      });
    });

    function parseLiteralList(line) {
      const s = String(line || "").trim();
      if (!s) return [];
      if (s.startsWith("[")) {
        try { return JSON.parse(s); } catch (_) {}
      }
      return s.split(/\s+/).filter(Boolean).map((x) => (Number.isNaN(Number(x)) ? x : Number(x)));
    }

    function buildLinkedList(vals) {
      let dummy = { value: 0, val: 0, next: null };
      let tail = dummy;
      for (const v of vals) {
        const node = { value: v, val: v, next: null };
        tail.next = node;
        tail = node;
      }
      return dummy.next;
    }

    function dumpLinkedList(head) {
      const out = [];
      let curr = head;
      let guard = 0;
      while (curr && guard < 10000) {
        out.push(curr.value !== undefined ? curr.value : curr.val);
        curr = curr.next;
        guard += 1;
      }
      return out.join(" ");
    }

    function buildTree(tokens) {
      if (!tokens.length || tokens[0] === null) return null;
      const root = { value: tokens[0], val: tokens[0], left: null, right: null };
      const q = [root];
      let idx = 1;
      while (q.length && idx < tokens.length) {
        const node = q.shift();
        if (idx < tokens.length) {
          if (tokens[idx] !== null) {
            node.left = { value: tokens[idx], val: tokens[idx], left: null, right: null };
            q.push(node.left);
          }
          idx += 1;
        }
        if (idx < tokens.length) {
          if (tokens[idx] !== null) {
            node.right = { value: tokens[idx], val: tokens[idx], left: null, right: null };
            q.push(node.right);
          }
          idx += 1;
        }
      }
      return root;
    }

    function parseWrapperInput(wrapper, rawStdin) {
      const text = String(rawStdin || "");
      const lines = text.split("\n");
      const l0 = (lines[0] || "").trim();
      const l1 = (lines[1] || "").trim();
      switch (wrapper) {
        case "raw":
          return [text];
        case "list-target":
          return [parseLiteralList(l0), Number(l1 || 0)];
        case "int-list-int":
          return [l0 ? l0.split(/\s+/).map(Number) : [], Number(l1 || 0)];
        case "int-list":
          return [text.trim() ? text.trim().split(/\s+/).map(Number) : []];
        case "string-bool":
        case "string-int":
          return [lines[0] || ""];
        case "two-lists":
        case "list-pair":
          return [
            l0 ? l0.split(/\s+/).map(Number) : [],
            l1 ? l1.split(/\s+/).map(Number) : [],
          ];
        case "lines":
        case "int-n":
          return [Number(text.trim() || 0)];
        case "int-int": {
          const parts = text.trim().split(/\s+/).map(Number);
          return [parts[0] || 0, parts[1] || 0];
        }
        case "string-list":
          return [text.trim() ? text.trim().split(/\s+/) : []];
        case "two-lines":
          return [lines[0] || "", lines[1] || ""];
        case "linked-list":
          return [buildLinkedList(text.trim() ? text.trim().split(/\s+/).map(Number) : [])];
        case "cycle": {
          const toks = text.trim() ? text.trim().split(/\s+/).map(Number) : [];
          const vals = toks.length > 1 ? toks.slice(0, -1) : [];
          const target = toks.length ? toks[toks.length - 1] : null;
          const nodes = vals.map((v) => ({ value: v, val: v, next: null }));
          for (let i = 0; i < nodes.length - 1; i++) nodes[i].next = nodes[i + 1];
          if (nodes.length && target !== null) {
            const hit = nodes.find((n) => n.value === target);
            if (hit) nodes[nodes.length - 1].next = hit;
          }
          return [nodes[0] || null];
        }
        case "tree": {
          const toks = text.trim()
            ? text.trim().split(/\s+/).map((t) => (t === "None" || t === "null" ? null : Number(t)))
            : [];
          return [buildTree(toks)];
        }
        case "matrix": {
          const nonEmpty = lines.map((l) => l.trim()).filter(Boolean);
          const bodyLines = nonEmpty.slice(1);
          return [bodyLines.map((r) => r.split(/\s+/).map(Number))];
        }
        case "intervals": {
          const nonEmpty = lines.map((l) => l.trim()).filter(Boolean);
          const pairs = nonEmpty.slice(1).map((r) => r.split(/\s+/).map(Number));
          return [pairs];
        }
        case "grid": {
          const nonEmpty = lines.map((l) => l.trim()).filter(Boolean);
          const rows = nonEmpty.slice(1).map((r) => r.split(""));
          return [rows];
        }
        case "word-ladder": {
          const nonEmpty = lines.map((l) => l.trim()).filter(Boolean);
          return [nonEmpty[0] || "", nonEmpty[1] || "", nonEmpty.slice(2)];
        }
        case "graph": {
          const nonEmpty = lines.map((l) => l.trim()).filter(Boolean);
          const endNode = nonEmpty.pop() || "";
          const startNode = nonEmpty.pop() || "";
          const adj = {};
          nonEmpty.forEach((row) => {
            const [u, rest] = row.split(":");
            adj[u] = [];
            if (rest) {
              rest.split(",").filter(Boolean).forEach((edge) => {
                const m = /^([A-Za-z0-9_]+?)(\d+)$/.exec(edge.trim());
                if (m) adj[u].push([m[1], Number(m[2])]);
              });
            }
          });
          return [adj, startNode, endNode];
        }
        case "lru":
          return [lines.map((l) => l.trim()).filter(Boolean)];
        default:
          return [text];
      }
    }

    function formatWrapperOutput(wrapper, res) {
      if (res === undefined || res === null) return "";
      if (wrapper === "string-bool" || wrapper === "cycle") {
        return res ? "True" : "False";
      }
      if (wrapper === "two-lists" || wrapper === "lines") {
        return Array.isArray(res) ? res.join(" ") : String(res);
      }
      if (wrapper === "linked-list") {
        return Array.isArray(res) ? res.join(" ") : dumpLinkedList(res);
      }
      if (wrapper === "intervals") {
        if (Array.isArray(res) && Array.isArray(res[0])) {
          return res.map((pair) => pair.join(" ")).join("\n");
        }
        return String(res);
      }
      if (wrapper === "matrix") {
        if (Array.isArray(res) && Array.isArray(res[0])) {
          return res.map((row) => row.join(" ")).join("\n");
        }
      }
      if (typeof res === "boolean") return res ? "True" : "False";
      if (Array.isArray(res)) {
        if (wrapper === "list-target") return `[${res.join(", ")}]`;
        return JSON.stringify(res).replace(/,/g, ", ");
      }
      return String(res);
    }

    // The entry name for a JavaScript submission comes from its own stub
    // signature (`function twoSum(...)` / `class LRUCache`); prob.entry is
    // the PYTHON name and is only a fallback.
    function jsEntryFor(prob) {
      const sig = String(prob?.stubs?.javascript?.signature || "");
      const m = /(?:function|class)\s+([A-Za-z_$][\w$]*)/.exec(sig);
      if (m) return m[1];
      const fallback = String(prob?.entry || "solution");
      return /^[A-Za-z_$][\w$]*$/.test(fallback) ? fallback : "solution";
    }

    async function executeSingleCase(prob, lang, code, stdinText) {
      const t0 = performance.now();
      const trimmed = String(code || "").trim();
      if (!trimmed) {
        return { status: "runtime_error", stdout: "", stderr: "Editor is empty.", runtimeMs: 0 };
      }

      // Check if user left the unimplemented starter stub untouched
      const stub = prob?.stubs?.[lang]?.stub?.trim() || "";
      if (stub && trimmed === stub && /\b(pass|todo|return\s+0;|return\s+null;|return\s+"";)\b/i.test(trimmed)) {
        return {
          status: "wrong_answer",
          stdout: "None",
          stderr: "Starter stub is still unimplemented — write your solution inside the function/method.",
          runtimeMs: 1,
        };
      }

      if (lang === "python") {
        // Real CPython (Pyodide) running the learner's code plus the exact
        // harness the server judge appends for this problem, exported as
        // prob.driverPython. Without that driver the function would never
        // be called, so a missing driver is NOT RUN, never a guess.
        if (prob && typeof prob.driverPython !== "string") {
          return {
            status: "sandbox_unavailable", executed: false, stdout: "", runtimeMs: 0,
            stderr: "Not run: this export is missing the Python harness for the problem, so the browser "
              + "cannot call your function the way the judge does. Re-export the site or use the hosted app.",
          };
        }
        const program = prob ? `${String(code).replace(/\n+$/, "")}\n${prob.driverPython}` : String(code);
        const res = await runPythonInBrowser(program, stdinText);
        return {
          status: res.status, executed: res.executed, stdout: (res.stdout || "").trim(),
          stderr: res.stderr || "", runtimeMs: res.runtimeMs,
        };
      }

      if (lang === "javascript") {
        // If no function/class stub exists for JavaScript on this problem (or
        // the learner wrote a standalone script reading stdin), execute raw mode!
        const hasJsStub = Boolean(prob?.stubs?.javascript?.signature);
        if (!hasJsStub) {
          const rRaw = await runJavaScriptInWorker({ mode: "raw", code, stdin: stdinText });
          const runtimeMsRaw = Math.max(1, Math.round(performance.now() - t0));
          if (rRaw.workerUnavailable) {
            return { status: "sandbox_unavailable", executed: false, stdout: "", stderr: `Not run: ${rRaw.error}`, runtimeMs: 0 };
          }
          if (rRaw.timeout) {
            return { status: "timeout", stdout: (rRaw.stdout || "").trim(), stderr: rRaw.error, runtimeMs: runtimeMsRaw };
          }
          return {
            status: rRaw.ok ? "accepted" : "runtime_error",
            stdout: String(rRaw.stdout !== undefined ? rRaw.stdout : (rRaw.logs || []).join("\n")).trim(),
            stderr: rRaw.ok ? "" : (rRaw.error || rRaw.stderr || ""),
            runtimeMs: runtimeMsRaw,
          };
        }
        const args = parseWrapperInput(prob?.wrapper || "raw", stdinText);
        const r = await runJavaScriptInWorker({
          mode: "call", code, entry: jsEntryFor(prob), args,
          lru: (prob?.wrapper || "") === "lru",
        });
        const runtimeMs = Math.max(1, Math.round(performance.now() - t0));
        const logs = r.logs || [];
        if (r.workerUnavailable) {
          return { status: "sandbox_unavailable", executed: false, stdout: "", stderr: `Not run: ${r.error}`, runtimeMs: 0 };
        }
        if (r.timeout) {
          return { status: "timeout", stdout: logs.join("\n"), stderr: r.error, runtimeMs };
        }
        if (!r.ok && /Entry point .* is not defined/.test(String(r.error || ""))) {
          const rRaw = await runJavaScriptInWorker({ mode: "raw", code, stdin: stdinText });
          const runtimeMsRaw = Math.max(1, Math.round(performance.now() - t0));
          if (rRaw.timeout) return { status: "timeout", stdout: (rRaw.stdout || "").trim(), stderr: rRaw.error, runtimeMs: runtimeMsRaw };
          return {
            status: rRaw.ok ? "accepted" : "runtime_error",
            stdout: String(rRaw.stdout !== undefined ? rRaw.stdout : (rRaw.logs || []).join("\n")).trim(),
            stderr: rRaw.ok ? "" : (rRaw.error || rRaw.stderr || ""),
            runtimeMs: runtimeMsRaw,
          };
        }
        if (!r.ok) {
          return { status: "runtime_error", stdout: logs.join("\n"), stderr: r.error || "", runtimeMs };
        }
        let stdout;
        if (logs.length) stdout = logs.join("\n");
        else if ((prob?.wrapper || "") === "lru") stdout = String(r.value ?? "");
        else stdout = formatWrapperOutput(prob?.wrapper || "raw", r.value);
        return { status: "accepted", stdout: String(stdout).trim(), stderr: "", runtimeMs };
      }

      // TypeScript, C, C++, Java, C#, Go, Rust, SQL: for these languages a
      // submission IS the whole program (drivers.py: "the learner writes a
      // complete program that reads stdin and prints the answer"), so it
      // runs verbatim against this test case's stdin on the vendored real
      // toolchain - the same contract the server judge applies. Go is the
      // one labelled exception: GopherJS cannot read stdin, so a Go program
      // runs with empty input exactly as its starter page explains.
      const rt = await evRuntimeRun(lang, code, stdinText);
      if (rt) {
        return {
          status: rt.status, executed: rt.executed, stdout: (rt.stdout || "").trim(),
          stderr: rt.stderr || "", runtimeMs: rt.runtimeMs,
        };
      }

      // What remains has no runtime in this copy. An earlier implementation
      // "verified" these languages by looking for a keyword such as `for`
      // and returning the test case's *expected output* as if the program
      // had printed it; a later one transpiled a Python subset with regexes.
      // Both presented unexecuted code as a verdict. Report not-executed
      // instead, the same contract the server judge uses.
      return {
        status: "unsupported_language",
        executed: false,
        stdout: "",
        stderr:
          `Not run: this static copy cannot compile or execute ${String(lang).toUpperCase()}. ` +
          "Your code was not executed, so this is not a pass or a fail. " +
          "JavaScript runs in an isolated worker here and Python runs on real CPython (Pyodide); " +
          "for other languages use the hosted EngineVerse compiler, whose judge has every toolchain, " +
          "or run the code locally.",
        runtimeMs: 0,
      };
    }

    function normalizeOut(s) {
      return String(s || "").trim().replace(/\r\n/g, "\n").replace(/[ \t]+$/gm, "");
    }

    if (runBtn) {
      runBtn.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopImmediatePropagation();
        runBtn.disabled = true;
        runBtn.textContent = "Running…";
        if (outputEl) outputEl.innerHTML = '<div class="muted small">Running in browser judge…</div>';
        try {
          const catalog = await loadProblemsCatalog();
          const prob = catalog[problemSlug];
          const lang = langSelect ? langSelect.value : "python";
          const sampleInput = customInput?.value ? customInput.value : prob?.testcases?.[0]?.input || "";
          const expected = !customInput?.value ? prob?.testcases?.[0]?.expected : null;
          const res = await executeSingleCase(prob, lang, editor.value, sampleInput);
          const passed = expected !== null && expected !== undefined
            ? normalizeOut(res.stdout) === normalizeOut(expected) && res.status === "accepted"
            : null;
          const runnerLabel = {
            python: "in-browser (CPython via Pyodide/WebAssembly)",
            javascript: "in-browser (JavaScript, isolated worker)",
            c: "in-browser (Clang/WebAssembly)",
            cpp: "in-browser (Clang/WebAssembly)",
            java: "in-browser (OpenJDK + TeaVM)",
            typescript: "in-browser (TypeScript compiler)",
            go: "in-browser (Go 1.24 via GopherJS)",
            rust: "in-browser (rustc/Miri)",
            csharp: "in-browser (Roslyn/.NET WebAssembly)",
            sql: "in-browser (SQLite/WebAssembly)",
          }[lang] || "static copy — not executed";
          const statusChip =
            res.executed === false
              ? '<span class="chip bad">Not run</span>'
              : passed === true
              ? '<span class="chip ok">Sample Passed</span>'
              : passed === false
              ? '<span class="chip bad">Output Mismatch</span>'
              : `<span class="chip">${escapeHtml(res.status)}</span>`;
          if (outputEl) {
            // stdout/stderr/expected are program output: escape before
            // innerHTML, or a solution that prints markup runs it here.
            outputEl.innerHTML = `
              <div class="row mb" style="justify-content:space-between">
                ${statusChip}
                <span class="tiny muted">${res.runtimeMs} ms · ${runnerLabel}</span>
              </div>
              ${res.stdout ? `<div class="small"><strong>Output</strong><pre>${escapeHtml(res.stdout)}</pre></div>` : ""}
              ${expected ? `<div class="small"><strong>Expected</strong><pre>${escapeHtml(expected)}</pre></div>` : ""}
              ${res.stderr ? `<div class="small" style="color:var(--danger)"><strong>Stderr</strong><pre>${escapeHtml(res.stderr)}</pre></div>` : ""}
            `;
          }
        } finally {
          runBtn.disabled = false;
          runBtn.textContent = "Run";
        }
      }, true);
    }

    if (submitBtn) {
      submitBtn.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopImmediatePropagation();
        submitBtn.disabled = true;
        submitBtn.textContent = "Judging…";
        if (outputEl) outputEl.innerHTML = '<div class="muted small">Running against all test cases in browser judge…</div>';
        try {
          const catalog = await loadProblemsCatalog();
          const prob = catalog[problemSlug];
          const lang = langSelect ? langSelect.value : "python";
          const cases = prob?.testcases || [];
          let passedCount = 0;
          let totalMs = 0;
          let firstErr = "";
          let notExecuted = false;
          // Sequential, not parallel: every case shares one interpreter
          // (worker/Pyodide) whose stdin/stdout are per-run state.
          const caseResults = [];
          for (let idx = 0; idx < cases.length; idx++) {
            const tc = cases[idx];
            const r = await executeSingleCase(prob, lang, editor.value, tc.input);
            totalMs += r.runtimeMs;
            if (r.executed === false || r.status === "unsupported_language") notExecuted = true;
            const ok = r.status === "accepted" && normalizeOut(r.stdout) === normalizeOut(tc.expected);
            if (ok) passedCount += 1;
            else if (!firstErr && r.stderr) firstErr = r.stderr;
            caseResults.push({ idx: idx + 1, ok, input: tc.input, expected: tc.expected, stdout: r.stdout, isSample: tc.isSample });
          }
          // Not-executed is its own verdict: no XP, no solved record, and
          // never presented as "wrong answer" (nothing was graded).
          const allAccepted = !notExecuted && cases.length > 0 && passedCount === cases.length;
          let xpAwarded = 0;
          if (allAccepted) {
            saveActiveProfile((p) => {
              const solved = new Set(p.solved_problems || []);
              const isFirst = !solved.has(problemSlug);
              solved.add(problemSlug);
              p.solved_problems = Array.from(solved);
              // Knowledge XP: only the first accepted solution pays (30),
              // exactly like the server - re-submitting a known solution
              // must not farm XP.
              xpAwarded = isFirst ? 30 : 0;
              p.xp = (p.xp || 0) + xpAwarded;
            });
            safely("hydrateNavigation", hydrateNavigation);
            toast(xpAwarded
              ? `Accepted! Passed ${passedCount}/${cases.length} test cases (+${xpAwarded} XP)`
              : `Accepted! Passed ${passedCount}/${cases.length} test cases (first solve already earned its XP)`);
          } else if (notExecuted) {
            toast("Not run — this language cannot execute on the static copy.", "bad");
          } else {
            toast(`Passed ${passedCount}/${cases.length} test cases`, "bad");
          }
          if (outputEl) {
            const caseHtml = caseResults.map((c) => `
              <div class="row tiny" style="padding:4px 0;border-bottom:1px solid var(--border)">
                <span class="chip ${c.ok ? "ok" : "bad"}">Case #${c.idx}: ${notExecuted ? "Not run" : c.ok ? "Passed" : "Failed"}</span>
                ${c.isSample ? `<span class="muted">stdout: <code>${escapeHtml(c.stdout || "(empty)")}</code> · expected: <code>${escapeHtml(c.expected)}</code></span>` : `<span class="muted">Hidden test case</span>`}
              </div>
            `).join("");
            outputEl.innerHTML = `
              <div class="row mb" style="justify-content:space-between">
                <span class="chip ${allAccepted ? "ok" : "bad"}">${notExecuted ? "NOT RUN" : allAccepted ? "ACCEPTED" : "WRONG ANSWER"} · ${passedCount}/${cases.length} passed</span>
                <span class="tiny muted">${totalMs} ms${xpAwarded ? ` · +${xpAwarded} XP` : ""}</span>
              </div>
              ${firstErr ? `<div class="small" style="color:var(--danger)"><strong>Diagnostic</strong><pre>${escapeHtml(firstErr)}</pre></div>` : ""}
              <div>${caseHtml}</div>
            `;
          }
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = "Submit";
        }
      }, true);
    }

    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        const lang = langSelect ? langSelect.value : "python";
        if (window.EV_STUBS && window.EV_STUBS[lang]) {
          editor.value = window.EV_STUBS[lang];
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // 6b. Compiler page on the static copy (/compiler, /python-compiler)
  //
  // app.js owns the page (editor, language switching, rendering) and calls
  // window.EV_BROWSER_TERMINAL when the ev-live marker is present. This
  // section only corrects the server-rendered host claims for the browser:
  // which languages can run HERE (the vendored-runtime manifest decides,
  // exactly as on the problem pages), and the browser starters for the
  // languages whose server starter assumes Node or stdin plumbing the
  // browser engines do not have.
  // ---------------------------------------------------------------------------
  const cplEditorEl = document.getElementById("cpl-editor");
  if (cplEditorEl) {
    const BROWSER_JS_STARTER = [
      "// Supports both Node style (`require('fs').readFileSync(0, 'utf8')`)",
      "// and browser globals (`input`, `readline()`, `print`, `console.log`).",
      'const fs = require("fs");',
      'const name = fs.readFileSync(0, "utf8").trim() || "engineer";',
      "console.log(`Hello, ${name}!`);",
      'console.log("Squares:", [1, 2, 3, 4, 5].map((n) => n * n).join(" "));',
      "",
    ].join("\n");
    const BROWSER_TS_STARTER = [
      "// Type-checked by the full TypeScript 5.9 compiler before execution.",
      "// Supports both `require('fs').readFileSync(0, 'utf8')` and `input` / `print`.",
      'import * as fs from "fs";',
      'const name: string = fs.readFileSync(0, "utf8").trim() || "engineer";',
      "function squares(upto: number): number[] {",
      "  return Array.from({ length: upto }, (_, i) => (i + 1) * (i + 1));",
      "}",
      "console.log(`Hello, ${name}!`);",
      'console.log("Squares:", squares(5).join(" "));',
      "",
    ].join("\n");
    const BROWSER_GO_STARTER = [
      "package main",
      "",
      "import (",
      '  "bufio"',
      '  "fmt"',
      '  "os"',
      '  "strings"',
      ")",
      "",
      "func main() {",
      "  line, _ := bufio.NewReader(os.Stdin).ReadString('\\n')",
      "  name := strings.TrimSpace(line)",
      '  if name == "" {',
      '    name = "engineer"',
      "  }",
      '  fmt.Printf("Hello, %s!\\n", name)',
      "  squares := []int{}",
      "  for i := 1; i <= 5; i++ {",
      "    squares = append(squares, i*i)",
      "  }",
      '  fmt.Println("Squares:", squares)',
      "}",
      "",
    ].join("\n");
    try {
      if (!localStorage.getItem("ev:compiler:code:javascript")) {
        localStorage.setItem("ev:compiler:code:javascript", BROWSER_JS_STARTER);
      }
      if (!localStorage.getItem("ev:compiler:code:typescript")) {
        localStorage.setItem("ev:compiler:code:typescript", BROWSER_TS_STARTER);
      }
      const prevGo = localStorage.getItem("ev:compiler:code:go");
      if (!prevGo || prevGo.includes("This engine cannot read stdin")) {
        localStorage.setItem("ev:compiler:code:go", BROWSER_GO_STARTER);
      }
    } catch (_) {}

    const cplLangEl = document.getElementById("cpl-lang");
    if (cplLangEl) {
      // JavaScript and Python are runnable synchronously; the compiled
      // languages + TypeScript/SQL stay disabled until the manifest
      // confirms this deployment bundles their browser toolchains.
      const RUNNABLE_HERE = new Set(["javascript", "python"]);
      Array.from(cplLangEl.options).forEach((opt) => {
        const runnable = RUNNABLE_HERE.has(opt.value);
        opt.disabled = !runnable;
        opt.textContent = opt.textContent.replace(/\s*\((no runtime here|cannot run here)\)/i, "");
        if (!runnable) opt.textContent = `${opt.textContent} (cannot run here)`;
        if (opt.value === "python" && !/CPython/i.test(opt.textContent)) {
          opt.textContent = `${opt.textContent} (CPython in browser)`;
        }
      });
      if (cplLangEl.selectedOptions?.[0]?.disabled) cplLangEl.value = "python";
    }

    const hostNote = document.getElementById("cpl-host-note");
    if (hostNote) {
      hostNote.classList.remove("warning");
      hostNote.innerHTML = '<span class="label">Static copy</span> '
        + "Every language here compiles and executes right on your device with its real "
        + "compiler or interpreter — Clang 22 (C17/C++20), OpenJDK + TeaVM (Java), rustc (Rust), "
        + "Roslyn (.NET C#), TypeScript 5.9, Go 1.24, Bash, SQLite (SQL), CPython 3.12 (Python), "
        + "and Node-compatible JavaScript — cached offline after first download.";
    }

    const runtimeEl = document.getElementById("cpl-runtime");
    const noteEl = document.getElementById("cpl-note");
    const cplOutputEl = document.getElementById("cpl-output");
    const cplRunBtn = document.getElementById("cpl-run");
    const EV_CPL_LABEL = {
      python: "CPython 3.12 in your browser (Pyodide/WebAssembly)",
      javascript: "JavaScript in an isolated Web Worker (Node fs + browser APIs)",
      c: "Clang 22 (GNU17) in your browser (WebAssembly)",
      cpp: "Clang 22 (GNU++20) in your browser (WebAssembly)",
      java: "OpenJDK javac + TeaVM in your browser",
      typescript: "TypeScript 5.9 compiler in your browser",
      sql: "SQLite in your browser (WebAssembly)",
      go: "Go 1.24 in your browser (GopherJS)",
      bash: "Bash in your browser",
      rust: "rustc (Miri) in your browser (WebAssembly)",
      csharp: "Roslyn on .NET WebAssembly in your browser",
    };
    const EV_CPL_NOTE = {
      javascript: "Supports Node style (`require('fs').readFileSync(0, 'utf8')`, `process`, `Buffer`, `readline`) as well as `input` and `print(...)` / `console.log(...)`.",
      python: "Full CPython 3.12 standard library: `input()`, `sys.stdin`, `collections`, `heapq`, `bisect`, `itertools`, `math`, `re`, `json`, classes and dataclasses.",
      typescript: "Full TypeScript 5.9 type checking (`strict: false`, ES2023 + Node `fs`/`process`/`Buffer` + `input`/`print`).",
      sql: "The input box is the optional setup script (`CREATE TABLE` / `INSERT`); your editor query runs right after it.",
      go: "Real Go 1.24 compiler with full `os.Stdin` (`fmt.Scan`, `bufio.Scanner`, `bufio.Reader`, `io.ReadAll`) and standard library.",
      bash: "POSIX/Bash shell with `awk`, `sed`, `grep`, `jq`, `sort`, `uniq`, `tr`, `cut`, `xargs`, arrays, functions, pipes and stdin.",
      java: "Real OpenJDK compiles your classes (`public class` or `class Main`/`Solution` with `main`), then TeaVM runs it with stdin.",
      rust: "Real `rustc` + Miri standard library reading stdin (`std::io::stdin()`, collections, iterators, traits, structs).",
      csharp: "Real Roslyn compiler on .NET WebAssembly: both top-level statements and full `class Program { static void Main() }` work with `Console.ReadLine()`.",
      c: "Clang 22 (`-std=gnu17 -O2 -lm`): full C standard headers (`<stdio.h>`, `<stdlib.h>`, `<string.h>`, `<math.h>`, `<stdint.h>`, `<stdbool.h>`, `<limits.h>`).",
      cpp: "Clang 22 (`-std=gnu++20 -O2`): full C++20 STL (`<iostream>`, `<vector>`, `<string>`, `<algorithm>`, `<map>`, `<unordered_map>`, `<set>`, `<queue>`, `<stack>`, `<numeric>`, `<cmath>`).",
    };
    window.EV_ON_RUNTIME_STATUS(({ lang, message }) => {
      if (!cplOutputEl || !cplLangEl || cplLangEl.value !== lang) return;
      if (cplRunBtn && cplRunBtn.disabled) {
        cplOutputEl.innerHTML = `<div class="muted small">${escapeHtml(message)}</div>`;
      }
    });
    const schedulePrewarm = () => {
      const slug = cplLangEl ? cplLangEl.value : "python";
      if (window.EV_BROWSER_PREWARM) window.EV_BROWSER_PREWARM(slug);
    };
    const paintStaticMeta = () => {
      const slug = cplLangEl ? cplLangEl.value : "python";
      if (runtimeEl) {
        runtimeEl.textContent = EV_CPL_LABEL[slug] || "Runs on the hosted judge, not in this static copy";
      }
      if (noteEl && EV_CPL_NOTE[slug]) {
        noteEl.textContent = EV_CPL_NOTE[slug];
      }
    };
    cplLangEl?.addEventListener("change", () => {
      paintStaticMeta();
      schedulePrewarm();
    });
    paintStaticMeta();
    // Once the vendored runtimes are known, light up every language this
    // deployment actually carries (a missing one keeps its honest label).
    evLoadManifest().then(({ languages }) => {
      if (!cplLangEl) return;
      let changed = false;
      Array.from(cplLangEl.options).forEach((opt) => {
        if (!languages.has(opt.value) || !opt.disabled) return;
        opt.disabled = false;
        opt.textContent = opt.textContent.replace(/\s*\(cannot run here\)/i, "");
        changed = true;
      });
      if (changed) {
        paintStaticMeta();
        cplLangEl.dispatchEvent(new Event("change"));
      }
      setTimeout(schedulePrewarm, 150);
    });
    cplLangEl?.dispatchEvent(new Event("change"));
  }

  // ---------------------------------------------------------------------------
  // 7. Interactive Account, Profile, Settings, Dashboard & GitHub Vault Pages
  // ---------------------------------------------------------------------------
  function renderAccountPage() {
    const pageRoot = document.querySelector("[data-ev-page]");
    if (!pageRoot) return;
    const pageKind = pageRoot.getAttribute("data-ev-page");
    const store = loadStore();
    const profile = getActiveProfile();

    const setElText = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = String(text);
    };

    if (pageKind === "logout") {
      store.currentUser = null;
      try { sessionStorage.setItem("ev:explicit_logout", "1"); } catch (_) {}
      saveStore(store);
      safely("hydrateNavigation", hydrateNavigation);
      return;
    }

    if (pageKind === "login") {
      const form = document.getElementById("ev-login-form");
      const alertBox = document.getElementById("ev-auth-alert");
      const demoBtn = document.getElementById("ev-demo-signin");
      const pullBtn = document.getElementById("ev-github-pull-signin");
      const alreadyBox = document.getElementById("ev-already-signed-in");
      const alreadyUser = firstEl("ev-already-user", "ev-already-signed-in-text");
      const switchBtn = document.getElementById("ev-switch-account-btn");
      const otpStep = firstEl("ev-login-otp-step");
      const otpPreview = firstEl("ev-login-otp-preview");
      const otpInput = firstEl("ev-login-otp", "ev-login-otp-code");
      const otpForm = firstEl("ev-login-otp-form");
      const otpResend = firstEl("ev-login-otp-resend");
      const submitBtn = firstEl("ev-login-submit-btn");

      const nextParam = new URLSearchParams(window.location.search).get("next");
      if (store.currentUser && store.currentUser !== "guest") {
        if (nextParam && nextParam.startsWith("/")) {
          window.location.href = nextParam;
          return;
        }
        if (alreadyBox) {
          alreadyBox.hidden = false;
          if (alreadyUser) alreadyUser.textContent = `@${store.currentUser}`;
        }
      }
      if (switchBtn && !switchBtn.dataset.bound) {
        switchBtn.dataset.bound = "1";
        switchBtn.addEventListener("click", () => {
          const s = loadStore();
          s.currentUser = null;
          try { sessionStorage.setItem("ev:explicit_logout", "1"); } catch (_) {}
          saveStore(s);
          if (alreadyBox) alreadyBox.hidden = true;
          safely("hydrateNavigation", hydrateNavigation);
        });
      }

      // --- shared sign-in steps ------------------------------------------
      // "Sign in" is one flow with up to two steps. Both the password form and
      // the OTP form (a separate <form> in the exported markup) call these, so
      // the code step cannot dead-end the way it did when only the first form
      // had a handler.
      const identityOfForm = () =>
        String(document.getElementById("ev-login-identity")?.value || "").trim().toLowerCase();

      const startLoginOtp = async (account) => {
        const ch = account.phone ? "phone" : "email";
        // Never invent a destination. `account.username + "@gmail.com"` used to
        // be the fallback, which masked a *made-up* address as if it were the
        // learner's own - so the page read "code sent to a***@gmail.com" for an
        // account that has no Gmail at all. A contact-less account is told so.
        const dest = account.phone || account.email || "";
        if (!dest) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent =
              `@${account.username} has no mobile number or Gmail address saved on this device, ` +
              "so there is nowhere to send a code. Sign in with the password you set here, or " +
              "create the account again with a real address.";
          }
          return null;
        }
        const issued = await issueBrowserOtpChallenge({
          purpose: "signup_verify",
          username: account.username,
          channel: ch,
          destination: dest,
        });
        if (otpStep) otpStep.hidden = false;
        if (otpPreview) {
          otpPreview.hidden = false;
          otpPreview.innerHTML = otpIssueHtml(issued, "First-time account verification");
        }
        if (submitBtn) submitBtn.textContent = "Verify 6-digit OTP & Sign in";
        if (otpInput) otpInput.focus();
        toast(otpIssueToast(issued));
      };

      const completeSignIn = async (account) => {
        const digest = await hashPasswordDigest(account.username, String(document.getElementById("ev-login-password")?.value || ""));
        account.password_sha256 = digest;
        account.otp_verified = true;
        const latest = loadStore();
        latest.accounts[account.username] = account;
        latest.currentUser = account.username;
        saveStore(latest);
        safely("hydrateNavigation", hydrateNavigation);
        toast(`Welcome back, ${account.display_name || account.username}!`);
        location.href = nextParam && nextParam.startsWith("/") ? nextParam : `${BASE}dashboard/`;
      };

      const finishLoginOtp = async (account) => {
        const verified = await verifyBrowserOtpChallenge("signup_verify", otpInput?.value || "");
        if (!verified.ok) {
          if (alertBox) { alertBox.hidden = false; alertBox.textContent = verified.error; }
          return;
        }
        account.otp_verified = true;
        await completeSignIn(account);
      };

      if (demoBtn && !demoBtn.dataset.bound) {
        demoBtn.dataset.bound = "1";
        demoBtn.addEventListener("click", async () => {
          await pullGithubVault(true);
          const s = loadStore();
          if (!s.accounts.saurav) {
            s.accounts.saurav = defaultProfile({
              username: "saurav",
              display_name: "Saurav Kushwaha",
              email: "saurav@gmail.com",
              country_code: "+91",
              otp_verified: true,
              branch: "cse",
              year_of_study: 3,
              xp: 480,
              level: 3,
              streak_days: 5,
              longest_streak: 12,
              completed_topics: ["ohms-law-and-kirchhoff", "time-complexity-and-asymptotics", "boolean-algebra-and-logic-gates"],
              solved_problems: ["two-sum", "valid-parentheses", "binary-search"],
            });
          }
          s.currentUser = "saurav";
          saveStore(s);
          safely("hydrateNavigation", hydrateNavigation);
          toast("Signed in as Saurav Kushwaha!");
          location.href = nextParam && nextParam.startsWith("/") ? nextParam : `${BASE}dashboard/`;
        });
      }

      if (pullBtn && !pullBtn.dataset.bound) {
        pullBtn.dataset.bound = "1";
        pullBtn.addEventListener("click", async () => {
          await pullGithubVault(false);
        });
      }

      if (form && !form.dataset.bound) {
        form.dataset.bound = "1";
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          await pullGithubVault(true);
          const identity = String(document.getElementById("ev-login-identity")?.value || "").trim().toLowerCase();
          const password = String(document.getElementById("ev-login-password")?.value || "");
          if (!identity || !password) {
            if (alertBox) { alertBox.hidden = false; alertBox.textContent = "Enter your username/Gmail/mobile number and password."; }
            return;
          }
          // Shape before lookup. "asha@gmail" is not anybody's account, so
          // saying so leaks nothing, and it beats the alternative: silently
          // searching for a string that could never match and reporting
          // "no verified account found" to someone whose real problem is a typo.
          const checked = IDENTITY.identity(identity);
          if (!checked.ok) {
            if (alertBox) { alertBox.hidden = false; alertBox.textContent = checked.error; }
            return;
          }
          const account = await findAccountByIdentity(loadStore(), (checked.value || identity).toLowerCase());

          if (!account) {
            if (alertBox) {
              alertBox.hidden = false;
              alertBox.innerHTML = `No verified account found for <strong>${escapeHtml(identity)}</strong>. New users must <a href="${BASE}register/">create an account with 6-digit OTP verification</a> first.`;
            }
            return;
          }

          if (!account.password_sha256) {
            // An account restored from the vault without a password digest must
            // not be signable-in with an arbitrary password: there is nothing
            // to compare against. Send the learner through OTP recovery, which
            // sets a password on this device.
            if (alertBox) {
              alertBox.hidden = false;
              alertBox.innerHTML = `No password is saved for <strong>@${escapeHtml(account.username)}</strong> on this device yet. <a href="${BASE}forgot-password/">Set one with a 6-digit OTP</a> — or use the demo button below.`;
            }
            return;
          }

          const digest = await hashPasswordDigest(account.username, password);
          if (account.password_sha256 !== digest) {
            if (alertBox) {
              alertBox.hidden = false;
              alertBox.innerHTML = `Incorrect password for <strong>@${escapeHtml(account.username)}</strong>. <a href="${BASE}forgot-password/">Forgot password? Reset via 6-digit OTP</a>.`;
            }
            return;
          }

          // Only require OTP on login if this is an unverified new account
          // (`otp_verified === false`). A returning learner who already passed
          // the one-time check signs in with the password alone.
          if (account.otp_verified === false) {
            if (otpStep && otpStep.hidden) {
              await startLoginOtp(account);
              return;
            }
            await finishLoginOtp(account);
            return;
          }

          // Returning verified user -> direct password sign-in without OTP.
          await completeSignIn(account);
        });
      }

      // The code is typed into its own small form on the exported page, so that
      // form needs the same handler as the password form. Without it, pressing
      // "Verify OTP" reloaded the page, hid the step again and left the learner
      // stuck in a loop with no way to finish signing in.
      if (otpForm && !otpForm.dataset.bound) {
        otpForm.dataset.bound = "1";
        otpForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const account = await findAccountByIdentity(loadStore(), identityOfForm());
          if (!account) {
            if (alertBox) { alertBox.hidden = false; alertBox.textContent = "Start again: enter your username/Gmail/mobile number and password."; }
            return;
          }
          await finishLoginOtp(account);
        });
      }

      if (otpResend && !otpResend.dataset.bound) {
        otpResend.dataset.bound = "1";
        otpResend.addEventListener("click", async () => {
          const account = await findAccountByIdentity(loadStore(), identityOfForm());
          if (account) await startLoginOtp(account);
        });
      }
    }

    if (pageKind === "register") {
      const form = document.getElementById("ev-register-form");
      const alertBox = document.getElementById("ev-auth-alert");
      const otpStep = document.getElementById("ev-reg-otp-step");
      const otpPreview = document.getElementById("ev-reg-otp-preview");
      const otpInput = firstEl("ev-reg-otp", "ev-reg-otp-code");
      const otpForm = firstEl("ev-reg-otp-form");
      const submitBtn = firstEl("ev-reg-submit-btn");
      const resendBtn = firstEl("ev-reg-resend-otp", "ev-reg-otp-resend");
      const switchBtn = firstEl("ev-reg-otp-switch");

      // Read and validate the contact fields in one place. Both the step that
      // sends the code and the step that creates the account call this: the code
      // is typed into a separate <form>, and checking only the first one let a
      // learner edit the address box after the code was issued and store the
      // unvalidated value.
      const readSignupIdentity = () => {
        const email = IDENTITY.email(document.getElementById("ev-reg-email")?.value || "");
        const countryCode = String(document.getElementById("ev-reg-country-code")?.value || "+91");
        const rawPhone = String(document.getElementById("ev-reg-phone")?.value || "").trim();
        const phone = rawPhone ? IDENTITY.phone(rawPhone, countryCode) : { ok: true, value: "" };
        const username = String(document.getElementById("ev-reg-username")?.value || "").trim().toLowerCase();
        let error = "";
        if (!/^[a-z0-9](?:[a-z0-9._-]{1,22}[a-z0-9])?$/.test(username)) {
          error = "A username is 3–24 characters: letters, numbers, dot, dash or underscore, starting and ending with a letter or digit.";
        } else if (!email.ok) {
          error = email.error;
        } else if (!phone.ok) {
          error = phone.error;
        }
        return { username, email: email.value || "", phone: phone.value || "", error };
      };

      const sendSignupOtp = async () => {
        const identity = readSignupIdentity();
        const password = String(document.getElementById("ev-reg-password")?.value || "");
        const channel = String(document.getElementById("ev-reg-otp-channel")?.value || "email");
        // One username, from readSignupIdentity, in both steps. This function
        // used to run its own `replace(/[^a-z0-9_-]/g, "")`, which silently
        // deleted the dot from `aarav.sharma` while the account-creating step kept
        // it - so the code was issued for @aaravsharma and verified against
        // @aarav.sharma, and a learner who typed a legal dotted username could not
        // finish signing up at all.
        const username = identity.username;
        if (password.length < 8) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = "A password of at least 8 characters is required on this copy; the hosted app asks for 10.";
          }
          return false;
        }
        if (identity.error) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = identity.error;
          }
          return false;
        }
        const normalizedPhone = identity.phone;
        if (channel === "phone" && !normalizedPhone) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = "Enter your mobile number with country code to receive SMS OTP, or switch channel to Gmail.";
          }
          return false;
        }
        const dest = channel === "phone" ? normalizedPhone : identity.email;
        const issued = await issueBrowserOtpChallenge({
          purpose: "signup_verify",
          username,
          channel,
          destination: dest,
        });
        if (alertBox) alertBox.hidden = true;
        if (otpStep) otpStep.hidden = false;
        if (resendBtn) resendBtn.hidden = false;
        if (submitBtn) submitBtn.textContent = "Verify 6-digit OTP & Create Account";
        if (otpPreview) {
          otpPreview.hidden = false;
          otpPreview.innerHTML = otpIssueHtml(issued, "6-digit signup code");
        }
        if (otpInput) otpInput.focus();
        toast(otpIssueToast(issued));
        return true;
      };

      if (resendBtn && !resendBtn.dataset.bound) {
        resendBtn.dataset.bound = "1";
        resendBtn.addEventListener("click", () => {
          sendSignupOtp();
        });
      }

      // Switching channel restarts the challenge for the other destination, so
      // "Switch Gmail / Mobile OTP" is not a button that does nothing.
      if (switchBtn && !switchBtn.dataset.bound) {
        switchBtn.dataset.bound = "1";
        switchBtn.addEventListener("click", async () => {
          const select = document.getElementById("ev-reg-otp-channel");
          if (select) select.value = select.value === "phone" ? "email" : "phone";
          await sendSignupOtp();
        });
      }

      // Creates the account once the 6-digit code has been accepted. Shared by
      // the signup form and the OTP form below it: the code is typed into a
      // separate <form>, which previously had no submit handler at all.
      const completeSignup = async () => {
        const verified = await verifyBrowserOtpChallenge("signup_verify", otpInput?.value || "");
        if (!verified.ok) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = verified.error;
          }
          return;
        }

        const displayName = String(document.getElementById("ev-reg-display")?.value || "").trim();
        const countryCode = String(document.getElementById("ev-reg-country-code")?.value || "+91");
        // Checked again, here, because this is the step that writes the account:
        // the address stored is the one that passed, never whatever the boxes say
        // after the code was issued.
        const identity = readSignupIdentity();
        if (identity.error) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = identity.error;
          }
          return;
        }
        const username = identity.username;
        const email = identity.email;
        const normalizedPhone = identity.phone;
        const branch = String(document.getElementById("ev-reg-branch")?.value || "cse");
        const year = Number(document.getElementById("ev-reg-year")?.value || 1);
        const password = String(document.getElementById("ev-reg-password")?.value || "");

        const digest = await hashPasswordDigest(username, password);
        const emailSha = email ? await sha256Hex(email) : "";
        const phoneSha = normalizedPhone ? await sha256Hex(normalizedPhone) : "";
        const s = loadStore();
        const existing = s.accounts[username] || defaultProfile({ username });
        if (s.accounts[username] && existing.password_sha256 && existing.email_sha256 && emailSha && existing.email_sha256 !== emailSha) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.innerHTML = `The username <strong>@${escapeHtml(username)}</strong> is already registered to another address. <a href="${BASE}forgot-password/">Recover it with a 6-digit OTP</a> instead.`;
          }
          return;
        }
        const created = Object.assign({}, existing, {
          username,
          display_name: displayName || username,
          email,
          email_sha256: emailSha,
          phone: normalizedPhone,
          phone_sha256: phoneSha,
          country_code: countryCode,
            otp_verified: true,
            branch,
            year_of_study: year,
            password_sha256: digest,
            xp: Math.max(50, Number(existing.xp || 0)),
          });
          s.accounts[username] = created;
          s.currentUser = username;
          saveStore(s);
          safely("hydrateNavigation", hydrateNavigation);
          try {
            await pushSnapshotToGithub(created, { useIssueSync: false });
          } catch (_) {}
          toast(`Verified 6-digit OTP! Account @${username} created (+50 Welcome XP)`);
          location.href = `${BASE}dashboard/`;
      };

      if (form && !form.dataset.bound) {
        form.dataset.bound = "1";
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          if (otpStep && otpStep.hidden) {
            await sendSignupOtp();
            return;
          }
          await completeSignup();
        });
      }

      // The code field lives in its own form in the exported page; without a
      // submit handler here, pressing "Verify 6-digit OTP" reloaded the page
      // and threw the code away.
      if (otpForm && !otpForm.dataset.bound) {
        otpForm.dataset.bound = "1";
        otpForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          await completeSignup();
        });
      }
    }

    if (pageKind === "forgot-password" || pageKind === "reset-password") {
      const form = document.getElementById("ev-forgot-form");
      const alertBox = document.getElementById("ev-auth-alert");
      const otpStep = document.getElementById("ev-forgot-otp-step");
      const otpPreview = document.getElementById("ev-forgot-otp-preview");
      const otpInput = firstEl("ev-forgot-otp", "ev-forgot-otp-code");
      const submitBtn = firstEl("ev-forgot-submit-btn");
      const resendBtn = firstEl("ev-forgot-resend-btn");

      const sendResetOtp = async () => {
        await pullGithubVault(true);
        const identity = String(document.getElementById("ev-forgot-identity")?.value || "").trim().toLowerCase();
        const channel = String(document.getElementById("ev-forgot-channel")?.value || "email");
        const countryCode = String(document.getElementById("ev-forgot-country-code")?.value || "+91");
        const rawPhone = String(document.getElementById("ev-forgot-phone")?.value || "").trim();

        if (!identity && !rawPhone) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = "Enter your username, Gmail address, or mobile number with country code.";
          }
          return false;
        }
        const typedPhone = rawPhone || (identity.startsWith("+") ? identity : "");
        const normalizedPhone = typedPhone ? normalizePhoneWithCountryCode(typedPhone, countryCode) : "";
        if (typedPhone && !normalizedPhone) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = IDENTITY.phone(typedPhone, countryCode).error;
          }
          return false;
        }
        if (identity.includes("@")) {
          const checkedEmail = IDENTITY.email(identity);
          if (!checkedEmail.ok) {
            if (alertBox) {
              alertBox.hidden = false;
              alertBox.textContent = checkedEmail.error;
            }
            return false;
          }
        }
        if (channel === "phone" && !normalizedPhone) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = "Enter a valid mobile number with your country code to receive SMS OTP.";
          }
          return false;
        }
        // The destination is the one on the account, never one guessed from the
        // login name. `uname + "@gmail.com"` used to be the fallback for a
        // username recovery, so recovery "sent a code" to an address nobody owns -
        // and on a static page that address is the learner's own typing.
        const recoveryAccount = await findAccountByIdentity(loadStore(), identity);
        const uname = (recoveryAccount && recoveryAccount.username)
          || identity.split("@")[0].replace(/[^a-z0-9_-]/g, "") || "learner";
        const dest = channel === "phone"
          ? normalizedPhone
          : ((recoveryAccount && recoveryAccount.email) || (identity.includes("@") ? identity : ""));
        if (!dest) {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent =
              `@${uname} has no Gmail address or mobile number saved on this device, so there is ` +
              "no way to verify it. Sign in with your password, or set the contact details from the " +
              "device where you created the account.";
          }
          return false;
        }
        const issued = await issueBrowserOtpChallenge({
          purpose: "password_reset",
          username: uname,
          channel,
          destination: dest,
        });
        if (alertBox) alertBox.hidden = true;
        if (otpStep) otpStep.hidden = false;
        if (resendBtn) resendBtn.hidden = false;
        if (submitBtn) submitBtn.textContent = "Verify 6-digit OTP & Reset Password";
        if (otpPreview) {
          otpPreview.hidden = false;
          otpPreview.innerHTML = otpIssueHtml(issued, "6-digit password reset code");
        }
        if (otpInput) otpInput.focus();
        toast(otpIssueToast(issued));
        return true;
      };

      if (resendBtn && !resendBtn.dataset.bound) {
        resendBtn.dataset.bound = "1";
        resendBtn.addEventListener("click", () => {
          sendResetOtp();
        });
      }

      if (form && !form.dataset.bound) {
        form.dataset.bound = "1";
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          if (otpStep && otpStep.hidden) {
            await sendResetOtp();
            return;
          }

          const verified = await verifyBrowserOtpChallenge("password_reset", otpInput?.value || "");
          if (!verified.ok) {
            if (alertBox) {
              alertBox.hidden = false;
              alertBox.textContent = verified.error;
            }
            return;
          }

          const identity = String(document.getElementById("ev-forgot-identity")?.value || "").trim().toLowerCase();
          const newPass = String(document.getElementById("ev-forgot-new-password")?.value || "");
          const confirmPass = String(document.getElementById("ev-forgot-confirm-password")?.value || newPass);
          if (newPass.length < 8) {
            if (alertBox) { alertBox.hidden = false; alertBox.textContent = "New password must be at least 8 characters."; }
            return;
          }
          if (newPass !== confirmPass) {
            if (alertBox) { alertBox.hidden = false; alertBox.textContent = "New password and confirmation do not match."; }
            return;
          }
          const s = loadStore();
          const matchedAcc = Object.values(s.accounts).find(
            (a) => a.username?.toLowerCase() === identity || (a.email && a.email.toLowerCase() === identity)
          );
          const uname = matchedAcc?.username || identity.split("@")[0].replace(/[^a-z0-9_-]/g, "") || "learner";
          const digest = await hashPasswordDigest(uname, newPass);
          const acc = s.accounts[uname] || defaultProfile({ username: uname, display_name: uname });
          acc.password_sha256 = digest;
          acc.otp_verified = true;
          acc.password_changed_via_otp = true;
          s.accounts[uname] = acc;
          s.currentUser = uname;
          saveStore(s);
          safely("hydrateNavigation", hydrateNavigation);
          try {
            await pushSnapshotToGithub(acc, { useIssueSync: false });
          } catch (_) {}
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = `Verified 6-digit OTP! Password updated for @${uname}. Redirecting to your dashboard…`;
          }
          setTimeout(() => { location.href = `${BASE}dashboard/`; }, 700);
        });
      }
    }

    if (pageKind === "dashboard") {
      setElText("ev-dash-greeting", `Welcome, ${profile.display_name} (@${profile.username})`);
      setElText("ev-stat-xp", `${profile.xp || 0} XP`);
      setElText("ev-stat-level", `Level ${profile.level || 1} · ${profile.branch?.toUpperCase() || "CSE"}`);
      setElText("ev-stat-streak", `${profile.streak_days || streak.current || 0} days`);
      setElText("ev-stat-longest", `Longest: ${profile.longest_streak || streak.longest || 1}d`);
      setElText("ev-stat-topics", (profile.completed_topics || []).length);
      setElText("ev-stat-problems", (profile.solved_problems || []).length);
      setElText("ev-stat-quizzes", `${profile.quiz_correct || 0}/${profile.quiz_attempts || 0} quizzes correct`);

      const statusBox = document.getElementById("ev-dash-sync-status");
      if (statusBox) {
        statusBox.textContent = store.lastSyncAt
          ? `Synced with ${store.githubRepo || GH_REPO} · Last sync: ${store.lastSyncAt}`
          : `Ready to sync @${profile.username}'s progress (${profile.xp || 0} XP) to ${store.githubRepo || GH_REPO}.`;
      }
      const actBox = document.getElementById("ev-dash-activity");
      if (actBox) {
        const items = [
          ...(profile.solved_problems || []).map((s) => `Solved coding problem: <a href="${BASE}practice/problems/${s}/">${s}</a>`),
          ...(profile.completed_topics || []).map((t) => `Completed topic note: <a href="${BASE}topics/${t}/">${t}</a>`),
        ];
        if (items.length) {
          actBox.innerHTML = `<ul class="small">${items.slice(0, 8).map((i) => `<li>${i}</li>`).join("")}</ul>`;
        }
      }
    }

    if (pageKind === "profile") {
      setElText("ev-profile-name", profile.display_name || "EngineVerse Learner");
      setElText("ev-profile-username", `@${profile.username || "guest"}`);
      setElText("ev-profile-branch", `${(profile.branch || "cse").toUpperCase()} · Year ${profile.year_of_study || 1}`);
      setElText("ev-profile-xp", `${profile.xp || 0} XP (Lv ${profile.level || 1})`);
      const topBox = document.getElementById("ev-profile-topics");
      if (topBox && (profile.completed_topics?.length || profile.bookmarks?.length)) {
        topBox.innerHTML = `<ul class="small">${(profile.completed_topics || []).map((t) => `<li>✓ <a href="${BASE}topics/${t}/">${t}</a></li>`).join("")}${(profile.bookmarks || []).map((b) => `<li>★ Saved: ${b}</li>`).join("")}</ul>`;
      }
      const probBox = document.getElementById("ev-profile-problems");
      if (probBox && profile.solved_problems?.length) {
        probBox.innerHTML = `<ul class="small">${profile.solved_problems.map((s) => `<li>✓ <a href="${BASE}practice/problems/${s}/">${s}</a></li>`).join("")}</ul>`;
      }
    }

    if (pageKind === "settings") {
      const ghRepoIn = document.getElementById("ev-gh-repo");
      const ghTokenIn = document.getElementById("ev-gh-token");
      const dispIn = document.getElementById("ev-set-display");
      const branchIn = document.getElementById("ev-set-branch");
      const yearIn = document.getElementById("ev-set-year");
      const bioIn = document.getElementById("ev-set-bio");
      const webIn = document.getElementById("ev-set-webhook");
      const alertBox = document.getElementById("ev-settings-alert");

      if (ghRepoIn) ghRepoIn.value = store.githubRepo || GH_REPO;
      if (ghTokenIn) ghTokenIn.value = store.githubToken || "";
      if (dispIn) dispIn.value = profile.display_name || "";
      if (branchIn) branchIn.value = profile.branch || "cse";
      if (yearIn) yearIn.value = String(profile.year_of_study || 1);
      if (bioIn) bioIn.value = profile.bio || "";
      if (webIn) webIn.value = store.webhookUrl || "";

      const ghForm = document.getElementById("ev-github-sync-form");
      if (ghForm && !ghForm.dataset.bound) {
        ghForm.dataset.bound = "1";
        ghForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const s = loadStore();
          s.githubRepo = String(ghRepoIn?.value || GH_REPO).trim();
          s.githubToken = String(ghTokenIn?.value || "").trim();
          saveStore(s);
          try {
            const res = await pushSnapshotToGithub(getActiveProfile(), {
              repo: s.githubRepo,
              token: s.githubToken,
              useIssueSync: !s.githubToken,
            });
            if (alertBox) {
              alertBox.hidden = false;
              alertBox.textContent = res.mode === "github-contents-api"
                ? `Successfully committed @${profile.username}'s snapshot to ${s.githubRepo}/data/learners/registry.json!`
                : `Prepared GitHub learner snapshot for ${s.githubRepo}.`;
            }
          } catch (err) {
            if (alertBox) { alertBox.hidden = false; alertBox.textContent = String(err.message || err); }
          }
        });
      }

      const issueBtn = document.getElementById("ev-gh-issue-sync");
      if (issueBtn && !issueBtn.dataset.bound) {
        issueBtn.dataset.bound = "1";
        issueBtn.addEventListener("click", () => {
          pushSnapshotToGithub(getActiveProfile(), { useIssueSync: true });
        });
      }

      const pullBtn = document.getElementById("ev-gh-pull-btn");
      if (pullBtn && !pullBtn.dataset.bound) {
        pullBtn.dataset.bound = "1";
        pullBtn.addEventListener("click", async () => {
          await pullGithubVault(false);
          renderAccountPage();
        });
      }

      const exportBtn = document.getElementById("ev-export-json");
      if (exportBtn && !exportBtn.dataset.bound) {
        exportBtn.dataset.bound = "1";
        exportBtn.addEventListener("click", () => {
          const snap = toGithubSnapshot(getActiveProfile());
          const blob = new Blob([JSON.stringify(snap, null, 2) + "\n"], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `engineverse-learner-${snap.username}.json`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        });
      }

      const importIn = document.getElementById("ev-import-json");
      if (importIn && !importIn.dataset.bound) {
        importIn.dataset.bound = "1";
        importIn.addEventListener("change", async () => {
          const file = importIn.files?.[0];
          if (!file) return;
          try {
            const text = await file.text();
            const parsed = JSON.parse(text);
            const snap = parsed.learners ? Object.values(parsed.learners)[0] : parsed;
            const merged = mergeSnapshotIntoStore(snap, true);
            if (merged) {
              toast(`Imported learner snapshot for @${merged.username}!`);
              safely("hydrateNavigation", hydrateNavigation);
              renderAccountPage();
            }
          } catch (_) {
            toast("Invalid learner snapshot JSON file.", "bad");
          }
        });
      }

      const profForm = document.getElementById("ev-profile-form");
      const emailIn = document.getElementById("ev-set-email");
      const ccIn = document.getElementById("ev-set-country-code");
      const phoneIn = document.getElementById("ev-set-phone");
      if (emailIn) emailIn.value = profile.email || "";
      if (ccIn) ccIn.value = profile.country_code || "+91";
      if (phoneIn) {
        const rawP = String(profile.phone || "");
        // Show the national digits beside the selector, never the number with
        // its own country code inside the digits box: re-saving what used to be
        // prefilled prepended the code a second time.
        const stored = rawP.trim().startsWith("+") ? rawP.trim() : "";
        const code = Object.keys(IDENTITY.plans)
          .filter((candidate) => stored.startsWith(candidate) && stored.length > candidate.length)
          .sort((a, b) => b.length - a.length)[0];
        phoneIn.value = code ? stored.slice(code.length) : stored.replace(/^\+/, "");
        if (ccIn && code) ccIn.value = code;
      }

      if (profForm && !profForm.dataset.bound) {
        profForm.dataset.bound = "1";
        profForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const rawEmailVal = String(emailIn?.value || profile.email || "").trim();
          const ccVal = String(ccIn?.value || profile.country_code || "+91").trim();
          const rawPhoneVal = String(phoneIn?.value || "").trim();
          // An unusable contact used to be dropped in silence: the digits were
          // thrown away only if they failed the loose shape test, and the page
          // still reported "Saved". The learner believed a phone number they had
          // not actually stored. Both fields are now checked and named.
          const refuse = (message) => {
            if (alertBox) {
              alertBox.hidden = false;
              alertBox.textContent = message;
            }
            toast(message, "bad");
          };
          const checkedEmail = IDENTITY.email(rawEmailVal);
          if (!rawEmailVal || !checkedEmail.ok) {
            refuse(checkedEmail.error || "Add the Gmail address you sign in with.");
            return;
          }
          const emailVal = (checkedEmail.value || rawEmailVal).toLowerCase();
          let normPhone = "";
          if (rawPhoneVal) {
            const checkedPhone = IDENTITY.phone(rawPhoneVal, ccVal);
            if (!checkedPhone.ok) {
              refuse(checkedPhone.error);
              return;
            }
            normPhone = checkedPhone.value;
          }
          const emailSha = emailVal ? await sha256Hex(emailVal) : "";
          const phoneSha = normPhone ? await sha256Hex(normPhone) : "";

          const updated = saveActiveProfile((p) => {
            p.display_name = String(dispIn?.value || p.display_name).trim();
            p.email = emailVal;
            p.email_sha256 = emailSha || p.email_sha256 || "";
            p.country_code = ccVal;
            if (normPhone) {
              p.phone = normPhone;
              p.phone_sha256 = phoneSha;
            }
            p.branch = String(branchIn?.value || p.branch);
            p.year_of_study = Number(yearIn?.value || p.year_of_study || 1);
            p.bio = String(bioIn?.value || "").trim();
          });
          const s = loadStore();
          s.webhookUrl = String(webIn?.value || "").trim();
          saveStore(s);
          safely("hydrateNavigation", hydrateNavigation);
          pushSnapshotToGithub(updated).catch(() => {});
          toast("Saved profile, contact channels, and sync settings!");
        });
      }

      // Section 3: Change Password via 6-Digit OTP (Gmail or Mobile Number with Country Code)
      const pwdForm = document.getElementById("ev-password-change-form");
      const pwdAlert = document.getElementById("ev-pwd-otp-alert");
      const pwdStep = document.getElementById("ev-pwd-otp-step");
      const pwdPreview = document.getElementById("ev-pwd-otp-preview");
      const pwdSubmitBtn = document.getElementById("ev-pwd-submit-btn");
      if (pwdForm && !pwdForm.dataset.bound) {
        pwdForm.dataset.bound = "1";
        pwdForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const active = getActiveProfile();
          const channel = String(document.getElementById("ev-pwd-otp-channel")?.value || "email");
          const cc = String(document.getElementById("ev-pwd-country-code")?.value || active.country_code || "+91");
          const rawPhone = String(document.getElementById("ev-pwd-phone")?.value || active.phone || "").trim();
          let normPhone = rawPhone ? normalizePhoneWithCountryCode(rawPhone, cc) : "";

          if (pwdStep && pwdStep.hidden) {
            const checkedPhone = rawPhone ? IDENTITY.phone(rawPhone, cc) : { ok: true, value: "" };
            if (!checkedPhone.ok) {
              if (pwdAlert) {
                pwdAlert.hidden = false;
                pwdAlert.textContent = checkedPhone.error;
              }
              return;
            }
            normPhone = checkedPhone.value;
            if (channel === "phone" && !normPhone) {
              if (pwdAlert) {
                pwdAlert.hidden = false;
                pwdAlert.textContent = "Enter your mobile number with country code to receive SMS OTP.";
              }
              return;
            }
            // Same rule as recovery: the code goes to a contact on file, and an
            // account with no address is told so instead of being "sent" a code
            // for a Gmail account this device invented from the username.
            const dest = channel === "phone" ? normPhone : (active.email || "");
            if (!dest) {
              if (pwdAlert) {
                pwdAlert.hidden = false;
                pwdAlert.textContent =
                  "This account has no Gmail address saved on this device, so a code cannot be " +
                  "delivered to it. Add one under Contact channels, or choose the mobile-number channel.";
              }
              return;
            }
            const issued = await issueBrowserOtpChallenge({
              purpose: "password_change",
              username: active.username,
              channel,
              destination: dest,
            });
            if (pwdAlert) pwdAlert.hidden = true;
            pwdStep.hidden = false;
            if (pwdSubmitBtn) pwdSubmitBtn.textContent = "Verify 6-digit OTP & Update Password";
            if (pwdPreview) {
              pwdPreview.hidden = false;
              pwdPreview.innerHTML = otpIssueHtml(issued, "6-digit password change code");
            }
            document.getElementById("ev-pwd-otp-code")?.focus();
            toast(otpIssueToast(issued));
            return;
          }

          const code = String(document.getElementById("ev-pwd-otp-code")?.value || "");
          const newPass = String(document.getElementById("ev-pwd-new-password")?.value || "");
          const confirmPass = String(document.getElementById("ev-pwd-confirm-password")?.value || "");
          if (newPass.length < 8) {
            if (pwdAlert) { pwdAlert.hidden = false; pwdAlert.textContent = "New password must be at least 8 characters."; }
            return;
          }
          if (newPass !== confirmPass) {
            if (pwdAlert) { pwdAlert.hidden = false; pwdAlert.textContent = "New password and confirmation do not match."; }
            return;
          }
          const verified = await verifyBrowserOtpChallenge("password_change", code);
          if (!verified.ok) {
            if (pwdAlert) { pwdAlert.hidden = false; pwdAlert.textContent = verified.error; }
            return;
          }
          const digest = await hashPasswordDigest(active.username, newPass);
          const updated = saveActiveProfile((p) => {
            p.password_sha256 = digest;
            p.otp_verified = true;
            p.password_changed_via_otp = true;
            if (normPhone) p.phone = normPhone;
            p.country_code = cc;
          });
          pushSnapshotToGithub(updated).catch(() => {});
          if (pwdStep) pwdStep.hidden = true;
          if (pwdSubmitBtn) pwdSubmitBtn.textContent = "Send 6-digit OTP to change password";
          if (pwdAlert) {
            pwdAlert.hidden = false;
            pwdAlert.textContent = `Verified 6-digit OTP! Password updated and synced for @${updated.username}.`;
          }
          toast("Password updated via 6-digit OTP!");
        });
      }

      const signoutBtn = document.getElementById("ev-signout-btn");
      if (signoutBtn && !signoutBtn.dataset.bound) {
        signoutBtn.dataset.bound = "1";
        signoutBtn.addEventListener("click", () => {
          signOutActiveUser();
        });
      }
    }

    if (pageKind === "mistakes") {
      const box = document.getElementById("ev-mistakes-list");
      const mistakes = profile.mistakes || [];
      if (box && mistakes.length) {
        box.innerHTML = `<h2>Recorded mistakes (${mistakes.length})</h2>` + mistakes.map((m) => `
          <article class="card mb">
            <div class="row" style="justify-content:space-between">
              <strong>${m.topicTitle || "Practice Question"}</strong>
              <span class="chip bad">Correct: ${m.correctLabel || "See explanation"}</span>
            </div>
            <p class="mt">${m.stem}</p>
            ${m.explanation ? `<p class="small muted">${m.explanation}</p>` : ""}
            <div class="row mt">
              <a class="btn btn-ghost btn-sm" href="${m.topicUrl || (BASE + "practice/questions/")}">Review topic</a>
            </div>
          </article>
        `).join("");
      }
    }

    if (pageKind === "portfolio") {
      setElText("ev-portfolio-title", `${profile.display_name}'s Engineering Portfolio`);
      setElText("ev-portfolio-summary", `@${profile.username} · ${(profile.branch || "cse").toUpperCase()} Year ${profile.year_of_study || 1} · ${profile.xp || 0} XP · ${(profile.completed_topics || []).length} topics mastered · ${(profile.solved_problems || []).length} coding problems solved · Backed by ${GH_REPO}.`);
      const projBox = document.getElementById("ev-portfolio-projects");
      if (projBox && profile.completed_topics?.length) {
        projBox.innerHTML = `<ul class="small">${profile.completed_topics.map((t) => `<li>✓ <a href="${BASE}topics/${t}/">${t}</a></li>`).join("")}</ul>`;
      }
      const codeBox = document.getElementById("ev-portfolio-coding");
      if (codeBox && profile.solved_problems?.length) {
        codeBox.innerHTML = `<ul class="small">${profile.solved_problems.map((s) => `<li>✓ <a href="${BASE}practice/problems/${s}/">${s}</a></li>`).join("")}</ul>`;
      }
    }

    if (pageKind === "certificates") {
      const list = document.getElementById("ev-certificates-list");
      if (list) {
        const topicsCount = (profile.completed_topics || []).length;
        const probsCount = (profile.solved_problems || []).length;
        list.innerHTML = `
          <div class="grid g2">
            <article class="card">
              <span class="chip ${topicsCount >= 1 ? "ok" : ""}">${topicsCount >= 1 ? "Unlocked" : `${topicsCount}/1 topics`}</span>
              <h3 class="mt">Core Engineering Foundations</h3>
              <p class="small muted">Issued to <strong>${profile.display_name} (@${profile.username})</strong> · Verified on GitHub Vault <code>${GH_REPO}</code>.</p>
            </article>
            <article class="card">
              <span class="chip ${probsCount >= 1 ? "ok" : ""}">${probsCount >= 1 ? "Unlocked" : `${probsCount}/1 problems`}</span>
              <h3 class="mt">Algorithmic Problem Solving</h3>
              <p class="small muted">Issued to <strong>${profile.display_name} (@${profile.username})</strong> · ${probsCount} problem(s) solved in browser judge.</p>
            </article>
          </div>
        `;
      }
    }

    // Bind any `[data-ev-sync-github]` and `[data-ev-pull-github]` buttons on the page
    document.querySelectorAll("[data-ev-sync-github]").forEach((btn) => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", async () => {
        const s = loadStore();
        try {
          await pushSnapshotToGithub(getActiveProfile(), {
            repo: s.githubRepo || GH_REPO,
            token: s.githubToken || "",
            useIssueSync: !s.githubToken,
          });
        } catch (err) {
          toast(String(err.message || err), "bad");
        }
      });
    });

    document.querySelectorAll("[data-ev-pull-github]").forEach((btn) => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", async () => {
        await pullGithubVault(false);
        safely("hydrateNavigation", hydrateNavigation);
        renderAccountPage();
      });
    });
  }

  renderAccountPage();

  // ---------------------------------------------------------------------------
  // 8. Browser Tutor (runs on /tutor/ where [data-tutor-form] lives)
  // ---------------------------------------------------------------------------
  const tutorForm = document.querySelector("[data-tutor-form]");
  if (!tutorForm || !config.tutor) return;

  const modeSelect = tutorForm.querySelector("[name='mode']");
  const queryInput = tutorForm.querySelector("[name='q']");
  const out = document.querySelector("[data-tutor-output]");
  let corpusPromise = null;

  const loadCorpus = () => {
    if (!corpusPromise) {
      corpusPromise = fetch(config.tutor)
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []);
    }
    return corpusPromise;
  };

  const STOP = new Set([
    "what", "is", "the", "a", "an", "of", "in", "on", "to", "for", "and", "or",
    "how", "why", "does", "do", "explain", "define", "tell", "me", "about",
    "with", "by", "from", "at", "as", "be", "are", "was", "were", "can", "you",
    "give", "show", "example", "simple", "terms", "work", "works", "used",
  ]);

  const tokenise = (text) =>
    (text || "")
      .toLowerCase()
      .replace(/[^a-z0-9\s+-]/g, " ")
      .split(/\s+/)
      .filter((w) => w.length >= 2 && !STOP.has(w));

  const scoreItem = (item, tokens, raw) => {
    const title = (item.title || "").toLowerCase();
    const subject = (item.subject || "").toLowerCase();
    const body = `${item.simple || ""} ${item.definition || ""} ${item.intuition || ""} ${item.example || ""} ${item.mistakes || ""}`.toLowerCase();
    let score = 0;
    if (raw && title.includes(raw)) score += 30;
    for (const tok of tokens) {
      if (title === tok) score += 25;
      else if (title.includes(tok)) score += 12;
      if (subject.includes(tok)) score += 4;
      if (body.includes(tok)) score += 3;
    }
    return score;
  };

  const sectionBlock = (heading, body) => {
    if (!body) return null;
    const wrap = document.createElement("div");
    wrap.className = "mb";
    const h = document.createElement("div");
    h.className = "eyebrow";
    h.textContent = heading;
    const p = document.createElement("p");
    p.textContent = body;
    wrap.append(h, p);
    return wrap;
  };

  const renderMatch = (item, mode) => {
    const card = document.createElement("article");
    card.className = "panel mb";

    const head = document.createElement("div");
    head.className = "row mb";
    head.style.justifyContent = "space-between";
    const title = document.createElement("h3");
    title.style.margin = "0";
    const link = document.createElement("a");
    link.href = item.url || "#";
    link.textContent = item.title;
    title.appendChild(link);
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = item.subject || "Topic";
    head.append(title, chip);
    card.appendChild(head);

    const order =
      mode === "beginner"
        ? [
            ["In plain words", item.simple || item.definition],
            ["Mental picture", item.intuition],
            ["Worked example", item.example],
          ]
        : mode === "revision"
        ? [
            ["Core definition", item.definition || item.simple],
            ["Key points", item.points || item.intuition],
            ["Common mistakes", item.mistakes],
          ]
        : mode === "practice"
        ? [
            ["Worked example", item.example || item.definition],
            ["Traps to avoid", item.mistakes],
            ["Core idea", item.simple || item.intuition],
          ]
        : [
            ["Definition", item.definition || item.simple],
            ["Intuition", item.intuition],
            ["Example", item.example],
            ["Common mistakes", item.mistakes],
          ];

    for (const [label, text] of order) {
      const block = sectionBlock(label, text);
      if (block) card.appendChild(block);
    }

    const foot = document.createElement("a");
    foot.className = "btn btn-ghost btn-sm";
    foot.href = item.url || "#";
    foot.textContent = "Open full topic note →";
    card.appendChild(foot);
    return card;
  };

  const answer = async () => {
    if (!out) return;
    const raw = (queryInput.value || "").trim().toLowerCase();
    const mode = modeSelect ? modeSelect.value : "concept";
    if (!raw) {
      out.replaceChildren();
      return;
    }
    const corpus = await loadCorpus();
    const tokens = tokenise(raw);
    const ranked = corpus
      .map((item) => ({ item, score: scoreItem(item, tokens, raw) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 3);

    out.replaceChildren();
    if (!ranked.length) {
      const empty = document.createElement("div");
      empty.className = "panel";
      empty.textContent =
        "No matching note found for that phrasing. Try a topic name such as Ohm's Law, Bernoulli, pointers, deadlock, Carnot, or Dijkstra.";
      out.appendChild(empty);
      return;
    }
    for (const r of ranked) {
      out.appendChild(renderMatch(r.item, mode));
    }
  };

  tutorForm.addEventListener("submit", (event) => {
    event.preventDefault();
    answer();
  });

  document.querySelectorAll("[data-tutor-prompt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      queryInput.value = btn.getAttribute("data-tutor-prompt") || "";
      if (modeSelect && btn.getAttribute("data-tutor-mode")) {
        modeSelect.value = btn.getAttribute("data-tutor-mode");
      }
      answer();
    });
  });
})();
