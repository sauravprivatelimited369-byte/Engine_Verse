/* EngineVerse static-copy runtime: local progress, quizzes and the browser code judge.
 *
 * Runs only on pages exported by scripts/export_pages.py (they carry the
 * #ev-live boot block). The static GitHub Pages copy has no accounts and no
 * server: progress, streaks and the mistake notebook are kept in this browser's
 * localStorage and never uploaded. Learners move them between devices with the
 * JSON export and import on the settings page.
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
  const MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const STREAK_KEY = "ev:streak:v1";

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
  // without ever defining it, so *every* call threw a ReferenceError and the
  // boot sequence stopped half way. Keep a local definition and prefer the shared
  // one when app.js has already run.
  // ---------------------------------------------------------------------------
  const escapeHtml = (value) =>
    typeof window.EV?.escapeHtml === "function"
      ? window.EV.escapeHtml(value)
      : String(value ?? "").replace(/[&<>"']/g, (c) =>
          ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
        );

  const reportRuntimeProblem = (label, error) => {
    if (window.console?.warn) window.console.warn(`[EngineVerse] ${label} failed`, error);
  };

  // Runs one boot step in isolation: a failure on a single page must not take
  // the rest of the runtime (progress, quizzes, judges) down with it.
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
  // Local learner profile (this browser only)
  //
  // The static copy has no accounts and no server. Progress lives in a single
  // localStorage record and is never uploaded. Earlier versions kept password
  // hashes, OTP challenges, a GitHub personal access token and a "GitHub learner
  // vault" in the browser; migrateLegacyStores() copies the progress fields out
  // of those layers once and then deletes them.
  // ---------------------------------------------------------------------------
  const PROFILE_KEY = "ev:local-profile:v1";
  const PROFILE_FORMAT = "engineverse-local-progress";
  const LEGACY_STORE_KEY = "ev:learner-store:v2";
  const LEGACY_KEYS = [LEGACY_STORE_KEY, "ev:session:user", "ev:explicit_logout", "ev:otp_api_url"];
  const LIMITS = { topics: 2000, problems: 1000, questions: 5000, bookmarks: 500, mistakes: 100, days: 3660 };

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
    const clean = Array.from(new Set(days.filter((x) => typeof x === "string" && parseIso(x)))).sort()
      .slice(-LIMITS.days);
    try {
      localStorage.setItem(STREAK_KEY, JSON.stringify({ days: clean }));
    } catch (_) {
      /* private mode: the streak lasts for this page only */
    }
    return clean;
  };

  const nowStamp = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const cleanText = (value, max) =>
    String(value == null ? "" : value).replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, max);
  const cleanSlug = (value) => {
    const s = String(value == null ? "" : value).trim().toLowerCase();
    return /^[a-z0-9][a-z0-9._:-]{0,119}$/.test(s) ? s : "";
  };
  const cleanSlugList = (value, max) =>
    Array.isArray(value) ? Array.from(new Set(value.map(cleanSlug).filter(Boolean))).slice(0, max) : [];
  const cleanInt = (value, max) => {
    const n = Math.floor(Number(value));
    return Number.isFinite(n) && n > 0 ? Math.min(n, max) : 0;
  };
  // Only same-site paths are kept, so an imported file cannot plant a
  // javascript: or off-site link in the mistake notebook.
  const cleanLocalPath = (value) => {
    const s = String(value == null ? "" : value).trim();
    return /^\/(?!\/)[A-Za-z0-9/_.~%-]*(\?[A-Za-z0-9=&_.%-]*)?$/.test(s) ? s.slice(0, 300) : "";
  };

  function defaultProfile() {
    return {
      display_name: "",
      branch: "",
      year_of_study: 0,
      bio: "",
      xp: 0,
      level: 1,
      streak_days: 0,
      longest_streak: 0,
      activity_days: [],
      completed_topics: [],
      solved_problems: [],
      solved_questions: [],
      completed_projects: [],
      bookmarks: [],
      quiz_attempts: 0,
      quiz_correct: 0,
      mistakes: [],
      srs_xp_day: "",
      updated_at: nowStamp(),
    };
  }

  // Whitelist every field. Anything else - including the password, email,
  // phone and token fields older versions stored - is dropped.
  function sanitizeProfile(raw) {
    const p = defaultProfile();
    if (!raw || typeof raw !== "object") return p;
    p.display_name = cleanText(raw.display_name === "EngineVerse Learner" || raw.display_name === "EngineVerse Learner" ? "" : raw.display_name, 60);
    p.branch = cleanText(raw.branch, 60);
    p.year_of_study = Math.min(cleanInt(raw.year_of_study, 5), 5);
    p.bio = cleanText(raw.bio === "Learning core engineering and programming on EngineVerse." || raw.bio === "Learning core engineering and programming on EngineVerse." ? "" : raw.bio, 240);
    p.xp = cleanInt(raw.xp, 10000000);
    p.quiz_attempts = cleanInt(raw.quiz_attempts, 1000000);
    p.quiz_correct = cleanInt(raw.quiz_correct, 1000000);
    if (p.quiz_correct > p.quiz_attempts) p.quiz_attempts = p.quiz_correct;
    p.streak_days = cleanInt(raw.streak_days, LIMITS.days);
    p.longest_streak = Math.max(cleanInt(raw.longest_streak, LIMITS.days), p.streak_days);
    p.activity_days = Array.isArray(raw.activity_days)
      ? Array.from(new Set(raw.activity_days.filter((d) => typeof d === "string" && parseIso(d)))).sort().slice(-LIMITS.days)
      : [];
    p.completed_topics = cleanSlugList(raw.completed_topics, LIMITS.topics);
    p.solved_problems = cleanSlugList(raw.solved_problems, LIMITS.problems);
    p.solved_questions = cleanSlugList(raw.solved_questions, LIMITS.questions);
    p.completed_projects = cleanSlugList(raw.completed_projects, LIMITS.topics);
    p.bookmarks = cleanSlugList(raw.bookmarks, LIMITS.bookmarks);
    p.srs_xp_day = typeof raw.srs_xp_day === "string" && parseIso(raw.srs_xp_day) ? raw.srs_xp_day : "";
    p.mistakes = Array.isArray(raw.mistakes)
      ? raw.mistakes.filter((m) => m && typeof m === "object").slice(0, LIMITS.mistakes).map((m) => ({
          id: cleanSlug(m.id) || cleanText(m.id, 80),
          stem: cleanText(m.stem, 1200),
          correctLabel: cleanText(m.correctLabel, 300),
          explanation: cleanText(m.explanation, 2000),
          topicTitle: cleanText(m.topicTitle, 160),
          topicUrl: cleanLocalPath(m.topicUrl),
          ts: typeof m.ts === "string" && parseIso(m.ts) ? m.ts : "",
        })).filter((m) => m.id && m.stem)
      : [];
    p.level = Math.max(1, Math.floor(p.xp / 250) + 1);
    p.updated_at = typeof raw.updated_at === "string" ? cleanText(raw.updated_at, 30) : nowStamp();
    return p;
  }

  function readProfile() {
    try {
      const raw = localStorage.getItem(PROFILE_KEY);
      return raw ? sanitizeProfile(JSON.parse(raw)) : null;
    } catch (_) {
      return null;
    }
  }

  let memoryProfile = null; // used when storage is blocked
  function writeProfile(profile) {
    memoryProfile = profile;
    try {
      localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
      return true;
    } catch (_) {
      return false;
    }
  }

  // One-time move out of the old multi-layer "vault". Every layer it used is
  // removed: localStorage/sessionStorage keys, the ev_live_user cookie, the
  // IndexedDB database, the window.name mirror and the GitHub token it held.
  function migrateLegacyStores() {
    let legacy = null;
    for (const area of ["localStorage", "sessionStorage"]) {
      try {
        const raw = window[area].getItem(LEGACY_STORE_KEY);
        if (raw && !legacy) legacy = JSON.parse(raw);
      } catch (_) { /* unreadable: nothing to migrate */ }
    }
    if (legacy && typeof legacy === "object" && legacy.accounts && typeof legacy.accounts === "object" && !readProfile()) {
      const accounts = legacy.accounts;
      const picked = (legacy.currentUser && accounts[legacy.currentUser]) || accounts.guest ||
        Object.values(accounts).sort((a, b) => String(b?.updated_at || "").localeCompare(String(a?.updated_at || "")))[0];
      if (picked) writeProfile(sanitizeProfile(picked));
    }
    for (const key of LEGACY_KEYS) {
      try { localStorage.removeItem(key); } catch (_) { /* ignore */ }
      try { sessionStorage.removeItem(key); } catch (_) { /* ignore */ }
    }
    try {
      if (/(?:^|;\s*)ev_live_user=/.test(document.cookie || "")) {
        document.cookie = "ev_live_user=; path=/; max-age=0; SameSite=Lax";
      }
    } catch (_) { /* ignore */ }
    try {
      if (typeof window.name === "string" && window.name.startsWith("EV_STORE:")) window.name = "";
    } catch (_) { /* ignore */ }
    try {
      if (window.indexedDB && !localStorage.getItem("ev:legacy-cleaned")) {
        window.indexedDB.deleteDatabase("EngineVerseVaultDB");
        localStorage.setItem("ev:legacy-cleaned", "1");
      }
    } catch (_) { /* ignore */ }
  }

  function getActiveProfile() {
    const stored = readProfile();
    if (stored) return stored;
    if (memoryProfile) return memoryProfile;
    const fresh = defaultProfile();
    writeProfile(fresh);
    return fresh;
  }

  function saveActiveProfile(mutator) {
    const profile = getActiveProfile();
    mutator(profile);
    const streakState = computeStreak(writeStreak((profile.activity_days || []).concat(readStreak().days)));
    profile.activity_days = streakState.days;
    profile.streak_days = streakState.current;
    profile.longest_streak = Math.max(Number(profile.longest_streak || 0), streakState.longest);
    profile.xp = Math.max(0, Number(profile.xp || 0));
    profile.level = Math.max(1, Math.floor(profile.xp / 250) + 1);
    profile.updated_at = nowStamp();
    const clean = sanitizeProfile(profile);
    writeProfile(clean);
    return clean;
  }

  function exportProfilePayload() {
    const profile = getActiveProfile();
    return {
      format: PROFILE_FORMAT,
      version: 1,
      exported_at: nowStamp(),
      profile,
      streak_days: readStreak().days,
    };
  }

  // Returns the sanitised profile, or throws an Error with a learner-facing message.
  function parseProfileImport(text) {
    let raw;
    try {
      raw = JSON.parse(text);
    } catch (_) {
      throw new Error("That file is not valid JSON.");
    }
    if (!raw || typeof raw !== "object") throw new Error("That file is not a EngineVerse progress export.");
    // Accept this format and the progress-only snapshot older versions exported.
    const body = raw.format === PROFILE_FORMAT ? raw.profile
      : raw.format === "engineverse-progress-export" ? raw
      : raw.schema === "engineverse.learner.v1" || raw.completed_topics ? raw : null;
    if (!body || typeof body !== "object") throw new Error("That file is not a EngineVerse progress export.");
    const profile = sanitizeProfile(body);
    const days = Array.isArray(raw.streak_days) ? raw.streak_days : profile.activity_days;
    return { profile, days };
  }

  function clearLocalProgress() {
    for (const key of [PROFILE_KEY, STREAK_KEY]) {
      try { localStorage.removeItem(key); } catch (_) { /* ignore */ }
    }
    memoryProfile = null;
  }

  safely("migrateLegacyStores", migrateLegacyStores);

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

  // Record study days in the local profile as well as the streak store.
  saveActiveProfile((p) => {
    p.activity_days = Array.from(new Set([...(p.activity_days || []), ...days]));
  });


  // ---------------------------------------------------------------------------
  // 2. Top bar progress button and sheet progress
  //
  // base.html renders a "My progress" button on the static copy. This fills in
  // the streak from this browser's record. There is no signed-in state to
  // reconcile: the static copy has no accounts.
  // ---------------------------------------------------------------------------
  function hydrateNavigation() {
    const profile = getActiveProfile();
    const current = computeStreak(readStreak().days).current;
    document.querySelectorAll("[data-ev-local-streak]").forEach((el) => {
      el.textContent = String(current);
    });
    document.querySelectorAll("[data-ev-local-progress]").forEach((el) => {
      el.title = current > 0
        ? `${current}-day streak · ${profile.xp || 0} XP · saved on this device`
        : "No study days yet · progress is saved on this device";
    });
  }

  // Sheet pages list problems in a table; mark the ones solved in this browser.
  function markSheetProgress() {
    const note = document.querySelector("[data-ev-sheet-progress]");
    if (!note) return;
    const solved = new Set(getActiveProfile().solved_problems || []);
    const rows = Array.from(document.querySelectorAll("table tbody tr"));
    let done = 0;
    let total = 0;
    rows.forEach((tr) => {
      const link = tr.querySelector('a[href*="/practice/problems/"]');
      if (!link) return;
      total += 1;
      const slug = (link.getAttribute("href") || "").split("/practice/problems/")[1]?.replace(/[/?#].*$/, "");
      if (slug && solved.has(slug)) {
        done += 1;
        if (!tr.querySelector("[data-ev-solved]")) {
          const chip = document.createElement("span");
          chip.className = "chip ok";
          chip.setAttribute("data-ev-solved", "");
          chip.textContent = "Solved";
          link.after(document.createTextNode(" "), chip);
        }
      }
    });
    if (total) {
      note.textContent = `${done} of ${total} solved on this device (${Math.round((done / total) * 100)}%). ` +
        "Progress is saved in this browser only.";
    }
  }

  const refreshLocalUi = () => {
    safely("hydrateNavigation", hydrateNavigation);
    safely("markSheetProgress", markSheetProgress);
  };
  refreshLocalUi();

  // Another tab recorded progress: refresh what this one shows.
  window.addEventListener("storage", (ev) => {
    if (!ev.key || ev.key === PROFILE_KEY || ev.key === STREAK_KEY) {
      refreshLocalUi();
      safely("renderAccountPage", () => renderAccountPage());
    }
  });
  window.addEventListener("pageshow", refreshLocalUi);

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
    const slug = btn.getAttribute("data-complete-topic") || btn.getAttribute("data-id") || "";
    if (!slug) return;
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
  // 7. Personal pages on the static copy: dashboard, profile, settings,
  //    mistakes and portfolio (markup written by scripts/export_pages.py)
  //
  // Everything shown here comes from this browser's local profile. All
  // learner-supplied text is written with textContent.
  // ---------------------------------------------------------------------------
  let titleIndexPromise = null;
  function loadTitleIndex() {
    if (!titleIndexPromise) {
      if (typeof window.fetch !== "function") return Promise.resolve(new Map());
      titleIndexPromise = window.fetch(`${BASE}search-index.json`, { credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : []))
        .then((rows) => {
          const map = new Map();
          (Array.isArray(rows) ? rows : []).forEach((row) => {
            const m = /\/(topics|practice\/problems|projects)\/([^/]+)\/?$/.exec(String(row.url || ""));
            if (m && row.title) map.set(`${m[1]}:${m[2]}`, String(row.title));
          });
          return map;
        })
        .catch(() => new Map());
    }
    return titleIndexPromise;
  }

  const humanize = (slug) => {
    const text = String(slug || "").replace(/[-_]+/g, " ").trim();
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
  };

  function setTextById(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function showEmpty(listId, isEmpty) {
    document.querySelectorAll(`[data-ev-empty="${listId}"]`).forEach((el) => { el.hidden = !isEmpty; });
  }

  // kind: "topics" | "practice/problems" | "projects"
  function fillLinkList(listId, kind, slugs, limit, append = false) {
    const list = document.getElementById(listId);
    if (!list) return;
    const items = (slugs || []).slice(-limit).reverse();
    if (!append) list.textContent = "";
    const anchors = [];
    items.forEach((slug) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = `${BASE}${kind}/${encodeURIComponent(slug)}/`;
      a.textContent = humanize(slug);
      a.dataset.evTitleKey = `${kind}:${slug}`;
      li.appendChild(a);
      list.appendChild(li);
      anchors.push(a);
    });
    showEmpty(listId, list.children.length === 0);
    if (anchors.length) {
      loadTitleIndex().then((map) => {
        anchors.forEach((a) => {
          const title = map.get(a.dataset.evTitleKey);
          if (title) a.textContent = title;
        });
      });
    }
  }

  function fillBookmarks(listId, keys) {
    const list = document.getElementById(listId);
    if (!list) return;
    list.textContent = "";
    const routes = { topic: "topics", project: "projects", problem: "practice/problems" };
    const anchors = [];
    (keys || []).slice(-20).reverse().forEach((key) => {
      const [type, id] = String(key).split(":");
      const li = document.createElement("li");
      if (routes[type] && id) {
        const a = document.createElement("a");
        a.href = `${BASE}${routes[type]}/${encodeURIComponent(id)}/`;
        a.textContent = humanize(id);
        a.dataset.evTitleKey = `${routes[type]}:${id}`;
        li.appendChild(a);
        anchors.push(a);
      } else {
        li.textContent = humanize(id || type);
      }
      list.appendChild(li);
    });
    showEmpty(listId, !(keys || []).length);
    if (anchors.length) {
      loadTitleIndex().then((map) => {
        anchors.forEach((a) => {
          const title = map.get(a.dataset.evTitleKey);
          if (title) a.textContent = title;
        });
      });
    }
  }

  function fillStats(profile) {
    const s = computeStreak(readStreak().days);
    setTextById("ev-stat-xp", String(profile.xp || 0));
    setTextById("ev-stat-level", `Level ${profile.level || 1}`);
    setTextById("ev-stat-streak", String(s.current));
    setTextById("ev-stat-longest", `best ${Math.max(s.longest, profile.longest_streak || 0)}`);
    setTextById("ev-stat-topics", String((profile.completed_topics || []).length));
    setTextById("ev-stat-problems", String((profile.solved_problems || []).length));
    const attempts = Number(profile.quiz_attempts || 0);
    setTextById("ev-stat-quizzes", `${attempts} question${attempts === 1 ? "" : "s"} answered`);
  }

  const yearLabel = (y) => (y >= 5 ? "5th year or later" : y > 0 ? `${["", "1st", "2nd", "3rd", "4th"][y]} year` : "");

  function renderMistakes(profile) {
    const list = document.getElementById("ev-mistakes-list");
    if (!list) return;
    list.textContent = "";
    const mistakes = profile.mistakes || [];
    mistakes.forEach((m) => {
      const li = document.createElement("li");
      li.className = "panel";
      const stem = document.createElement("p");
      stem.className = "ev-mistake-stem";
      stem.textContent = m.stem;
      li.appendChild(stem);
      if (m.correctLabel) {
        const ans = document.createElement("p");
        const strong = document.createElement("strong");
        strong.textContent = "Correct answer: ";
        ans.appendChild(strong);
        ans.appendChild(document.createTextNode(m.correctLabel));
        li.appendChild(ans);
      }
      if (m.explanation) {
        const ex = document.createElement("p");
        ex.className = "muted";
        ex.textContent = m.explanation;
        li.appendChild(ex);
      }
      const row = document.createElement("p");
      row.className = "row small";
      if (m.topicUrl) {
        const a = document.createElement("a");
        a.href = m.topicUrl;
        a.textContent = m.topicTitle ? `Revise: ${m.topicTitle}` : "Open the question again";
        row.appendChild(a);
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-ghost btn-sm";
      btn.textContent = "Mark as understood";
      btn.addEventListener("click", () => {
        saveActiveProfile((p) => { p.mistakes = (p.mistakes || []).filter((x) => x.id !== m.id); });
        renderAccountPage();
        toast("Removed from your mistake notebook");
      });
      row.appendChild(btn);
      li.appendChild(row);
      list.appendChild(li);
    });
    showEmpty("ev-mistakes-list", mistakes.length === 0);
  }

  function settingsStatus(message, kind = "info") {
    const box = document.getElementById("ev-settings-status");
    if (!box) { toast(message, kind === "bad" ? "bad" : "ok"); return; }
    box.className = `callout ${kind === "bad" ? "warning" : kind} mb`;
    box.textContent = message;
    box.hidden = false;
  }

  let settingsBound = false;
  function bindSettings() {
    if (settingsBound) return;
    settingsBound = true;
    const form = document.getElementById("ev-profile-form");
    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const name = cleanText(form.elements.display_name.value, 60);
        if (/@|\d{7,}/.test(name)) {
          settingsStatus("Use a name rather than an email address or phone number.", "bad");
          form.elements.display_name.focus();
          return;
        }
        saveActiveProfile((p) => {
          p.display_name = name;
          p.branch = cleanText(form.elements.branch.value, 60);
          p.year_of_study = Math.min(cleanInt(form.elements.year_of_study.value, 5), 5);
          p.bio = cleanText(form.elements.bio.value, 240);
        });
        settingsStatus("Profile saved on this device.", "ok");
        refreshLocalUi();
      });
    }
    document.getElementById("ev-export-json")?.addEventListener("click", () => {
      // The Android app's viewer cannot save blob downloads; say so instead of
      // reporting an export that did not happen.
      if (/EngineVerseAndroid\//.test(navigator.userAgent)) {
        settingsStatus("Saving files is not available inside the EngineVerse Android app. Use \u201cOpen in browser\u201d (top right) to save this file.", "warn");
        return;
      }
      const blob = new Blob([JSON.stringify(exportProfilePayload(), null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `engineverse-progress-${isoOf(new Date())}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      settingsStatus("Progress exported. Keep the file somewhere safe.", "ok");
    });
    document.getElementById("ev-import-json")?.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      e.target.value = "";
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) { settingsStatus("That file is too large to be a progress export.", "bad"); return; }
      const reader = new FileReader();
      reader.onload = () => {
        let parsed;
        try {
          parsed = parseProfileImport(String(reader.result || ""));
        } catch (err) {
          settingsStatus(err.message, "bad");
          return;
        }
        const p = parsed.profile;
        const summary = `${p.completed_topics.length} topics, ${p.solved_problems.length} problems, ${p.xp} XP`;
        if (!window.confirm(`Replace the progress stored in this browser with the imported file (${summary})?`)) return;
        writeStreak(parsed.days);
        writeProfile(p);
        saveActiveProfile(() => {});
        settingsStatus(`Imported ${summary}.`, "ok");
        refreshLocalUi();
        renderAccountPage();
      };
      reader.onerror = () => settingsStatus("Could not read that file.", "bad");
      reader.readAsText(file);
    });
    document.getElementById("ev-clear-data")?.addEventListener("click", () => {
      if (!window.confirm("Delete your profile, streak and progress from this browser? This cannot be undone. Export first if you want a copy.")) return;
      clearLocalProgress();
      settingsStatus("Your progress has been deleted from this browser.", "ok");
      refreshLocalUi();
      renderAccountPage();
    });
  }

  function renderAccountPage() {
    const pageRoot = document.querySelector("[data-ev-page]");
    if (!pageRoot) return;
    const kind = pageRoot.getAttribute("data-ev-page");
    const profile = getActiveProfile();
    const name = profile.display_name || "";

    if (kind === "dashboard") {
      setTextById("ev-dash-greeting", name ? `${name}'s progress` : "My progress");
      fillStats(profile);
      fillLinkList("ev-dash-activity", "topics", profile.completed_topics, 8);
      fillLinkList("ev-dash-activity", "practice/problems", profile.solved_problems, 6, true);
      fillBookmarks("ev-dash-bookmarks", profile.bookmarks);
    }

    if (kind === "profile") {
      setTextById("ev-profile-name", name || "EngineVerse learner");
      const branchBits = [profile.branch, yearLabel(profile.year_of_study)].filter(Boolean);
      setTextById("ev-profile-branch", branchBits.length ? branchBits.join(" · ") : "Branch not set");
      setTextById("ev-profile-xp", `${profile.xp || 0} XP · level ${profile.level || 1}`);
      setTextById("ev-profile-bio", profile.bio || "");
      fillLinkList("ev-profile-topics", "topics", profile.completed_topics, 200);
      fillLinkList("ev-profile-problems", "practice/problems", profile.solved_problems, 200);
    }

    if (kind === "settings") {
      const form = document.getElementById("ev-profile-form");
      if (form) {
        form.elements.display_name.value = profile.display_name || "";
        form.elements.branch.value = profile.branch || "";
        form.elements.year_of_study.value = String(profile.year_of_study || 0);
        form.elements.bio.value = profile.bio || "";
      }
      bindSettings();
    }

    if (kind === "mistakes") renderMistakes(profile);

    if (kind === "portfolio") {
      setTextById("ev-portfolio-title", name ? `${name}: learning portfolio` : "Learning portfolio");
      const parts = [
        `${(profile.completed_topics || []).length} topics completed`,
        `${(profile.solved_problems || []).length} coding problems solved`,
        `${profile.quiz_correct || 0} of ${profile.quiz_attempts || 0} practice questions correct`,
      ];
      const branchBits = [profile.branch, yearLabel(profile.year_of_study)].filter(Boolean);
      setTextById("ev-portfolio-summary", (branchBits.length ? `${branchBits.join(", ")}. ` : "") + parts.join(" · ") + ".");
      fillLinkList("ev-portfolio-topics", "topics", profile.completed_topics, 500);
      fillLinkList("ev-portfolio-problems", "practice/problems", profile.solved_problems, 500);
      const printBtn = document.getElementById("ev-portfolio-print");
      if (printBtn && !printBtn.dataset.bound) {
        printBtn.dataset.bound = "1";
        printBtn.addEventListener("click", () => window.print());
      }
    }
  }

  safely("renderAccountPage", renderAccountPage);

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
