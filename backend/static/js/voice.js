/* EngineVerse voice reader and voice tutor.
 *
 * Listen works with the browser's installed speech voices, even on the static
 * Pages copy. When configured, ElevenLabs supplies a more natural voice via
 * the FastAPI proxy; the browser takes over if that service fails. Neither
 * path ever needs an API key in a page. The optional live voice agent still
 * needs an ElevenLabs backend. On browsers with SpeechRecognition, students
 * can also ask the notes tutor aloud and hear its grounded answer.
 *
 * No text or audio is stored. Reading sends text to ElevenLabs only when that
 * voice is selected; the browser's speech/recognition privacy rules apply to
 * device voices and dictated questions. The microphone is requested only
 * after an explicit click.
 */
(() => {
  "use strict";

  const configNode = document.getElementById("ev-voice-config");
  if (!configNode) return;
  let boot = {};
  try {
    boot = JSON.parse(configNode.textContent || "{}") || {};
  } catch (_) {
    return;
  }

  const API_BASE = String(boot.apiBase || "").replace(/\/+$/, "");
  const STATIC_COPY = Boolean(boot.staticCopy);
  const HAS_API = !STATIC_COPY || Boolean(API_BASE);
  const HAS_BROWSER_SPEECH = Boolean(window.speechSynthesis && window.SpeechSynthesisUtterance);
  const synth = HAS_BROWSER_SPEECH ? window.speechSynthesis : null;
  const documentRoot = document;
  const NO_BACKEND = {
    reason: "A natural ElevenLabs voice is not connected here. You can still listen with a device voice.",
    tts: { available: false, languages: [], defaultLanguage: "en", maxChars: 1200 },
    conversation: { available: false, reason: "Live conversations need an ElevenLabs agent and backend. You can ask the notes tutor above and listen to its answer instead." },
  };

  // ---------------------------------------------------------------- unavailable
  // If neither a backend nor browser speech is available, do not draw dead
  // controls. Keep the written content and an accessible explanation.
  const voiceUnavailable = (message) => {
    const notice =
      message ||
      "This browser has no speech voice available and no voice backend is connected. " +
        "Try a current browser with speech voices installed, or configure the " +
        "ElevenLabs backend. The written tutor and notes still work.";
    documentRoot.documentElement.classList.add("voice-off");
    const panel = documentRoot.querySelector("[data-voice-tutor]");
    if (panel) {
      const chip = documentRoot.getElementById("voice-tutor-chip");
      const startBtn = documentRoot.getElementById("voice-start");
      const setupEl = documentRoot.getElementById("voice-setup");
      const statusEl = documentRoot.getElementById("voice-status");
      if (chip) {
        chip.textContent = "Not connected";
        chip.classList.remove("ok");
        chip.classList.add("warn");
      }
      if (startBtn) {
        startBtn.disabled = true;
        startBtn.setAttribute("aria-disabled", "true");
      }
      if (setupEl) {
        setupEl.hidden = false;
        setupEl.textContent = notice;
      }
      if (statusEl) statusEl.textContent = "No microphone is requested until voice is connected.";
    }
    if (documentRoot.querySelector(".voice-unavailable")) return;
    const host = documentRoot.querySelector("[data-speak], .has-voice");
    if (!host) return;
    const note = documentRoot.createElement("p");
    note.className = "voice-unavailable small muted";
    note.setAttribute("role", "note");
    note.textContent = notice;
    const heading = host.querySelector("h1, h2, h3");
    if (heading && heading.parentNode === host) {
      heading.insertAdjacentElement("afterend", note);
    } else {
      host.insertBefore(note, host.firstChild);
    }
  };

  // A static copy has no /api/voice endpoint. Browser speech works without
  // one; only browsers lacking speech support need the unavailable notice.
  if (!HAS_API && !HAS_BROWSER_SPEECH) {
    const announce = () => voiceUnavailable("");
    if (documentRoot.readyState === "loading") {
      documentRoot.addEventListener("DOMContentLoaded", announce, { once: true });
    } else {
      announce();
    }
    return;
  }
  const IS_ANDROID_APP = /EngineVerseAndroid\//.test(navigator.userAgent || "");
  const PREF_KEY = "ev:voice:v1";
  const SESSION_CHAR_BUDGET = 24000; // one tab; the server also rate-limits per IP

  const svg = (paths, size = 16) =>
    `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" ` +
    `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">` +
    paths.map((d) => `<path d="${d}"/>`).join("") +
    "</svg>";
  const ICONS = {
    speaker: ["M4 9.5h3.5L12 5.5v13L7.5 14.5H4z", "M16 9.2a4 4 0 0 1 0 5.6", "M18.6 6.6a8 8 0 0 1 0 10.8"],
    pause: ["M9 5.5v13", "M15 5.5v13"],
    stop: ["M6.5 6.5h11v11h-11z"],
    replay: ["M20 12a8 8 0 1 1-2.4-5.7", "M20 4.5V10h-5.5"],
    mic: ["M12 4a2.6 2.6 0 0 1 2.6 2.6v4.8a2.6 2.6 0 1 1-5.2 0V6.6A2.6 2.6 0 0 1 12 4z", "M6.5 11.4a5.5 5.5 0 0 0 11 0", "M12 17v3.5"],
    micOff: ["M12 4a2.6 2.6 0 0 1 2.6 2.6v4.8", "M6.5 11.4a5.5 5.5 0 0 0 7.4 5.1", "M12 17v3.5", "M4 4l16 16"],
  };
  const icon = (name, size) => svg(ICONS[name] || ICONS.speaker, size);

  // -------------------------------------------------------------------------
  // Preferences: saved locally, never sent anywhere except as a voice choice.
  // -------------------------------------------------------------------------
  const clampSpeed = (value) => {
    const speed = Number(value);
    return Number.isFinite(speed) && speed >= 0.75 && speed <= 1.5 ? speed : 1;
  };

  const readPrefs = () => {
    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem(PREF_KEY) || "{}") || {};
    } catch (_) {
      saved = {};
    }
    return {
      language: saved.language === "hi" ? "hi" : "en",
      voiceId: typeof saved.voiceId === "string" ? saved.voiceId : "",
      speed: clampSpeed(saved.speed),
    };
  };

  const writePrefs = (patch) => {
    const next = { ...readPrefs(), ...patch };
    try {
      localStorage.setItem(PREF_KEY, JSON.stringify(next));
    } catch (_) {
      /* private mode: preferences simply do not persist */
    }
    return next;
  };

  // -------------------------------------------------------------------------
  // Backend status (public, secret-free). Never call /api/voice on a static
  // copy without an API origin. A down server must not delay device speech.
  // -------------------------------------------------------------------------
  let statusPromise = null;
  let currentStatus = HAS_API ? null : NO_BACKEND;
  const getStatus = () => {
    if (!HAS_API) return Promise.resolve(NO_BACKEND);
    if (!statusPromise) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 7000);
      statusPromise = fetch(`${API_BASE}/api/voice/status`, {
        headers: { accept: "application/json" },
        credentials: "omit",
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) throw new Error(`status ${response.status}`);
          return response.json();
        })
        .then((status) => {
          currentStatus = status;
          return status;
        })
        .catch((error) => {
          statusPromise = null;
          currentStatus = null;
          throw error;
        })
        .finally(() => clearTimeout(timer));
    }
    return statusPromise;
  };

  const errorFrom = async (response, fallback) => {
    let body = {};
    try {
      body = await response.json();
    } catch (_) {
      body = {};
    }
    const error = new Error(body.error || fallback);
    error.code = body.code || "";
    error.status = response.status;
    error.retryAfter = Number(response.headers.get("retry-after") || 0);
    return error;
  };

  // -------------------------------------------------------------------------
  // Text extraction: the article, not the page chrome, and not code blocks.
  // -------------------------------------------------------------------------
  const SKIP_TAGS = new Set([
    "SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "NAV", "BUTTON", "INPUT", "SELECT",
    "TEXTAREA", "PRE", "SVG", "CANVAS", "IFRAME", "ASIDE", "FOOTER", "HEADER",
    "FORM", "DIALOG",
  ]);
  const BLOCK_TAGS = new Set([
    "P", "DIV", "SECTION", "ARTICLE", "LI", "UL", "OL", "H1", "H2", "H3", "H4",
    "H5", "H6", "BLOCKQUOTE", "TR", "TD", "TH", "FIGCAPTION", "FIGURE", "TABLE",
    "TBODY", "THEAD", "SUMMARY", "DETAILS", "BR", "HR", "DL", "DT", "DD",
  ]);

  const collectText = (node, out) => {
    for (const child of node.childNodes) {
      if (child.nodeType === 3) {
        out.push(child.nodeValue || "");
        continue;
      }
      if (child.nodeType !== 1) continue;
      const tag = child.tagName;
      if (SKIP_TAGS.has(tag)) continue;
      if (child.hasAttribute("data-voice-skip")) continue;
      if (child.getAttribute("aria-hidden") === "true") continue;
      if (child.classList && child.classList.contains("voice-controls")) continue;
      if (child.classList && child.classList.contains("sr-only")) continue;
      const isBlock = BLOCK_TAGS.has(tag);
      if (isBlock) out.push("\n\n");
      collectText(child, out);
      if (isBlock) out.push("\n\n");
    }
  };

  const extractText = (element, title) => {
    const parts = [];
    collectText(element, parts);
    let text = parts
      .join(" ")
      .replace(/\u00a0/g, " ")
      .replace(/[ \t]+/g, " ")
      .replace(/\s*\n\s*/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    const heading = String(title || element.getAttribute("data-speak-title") || "").trim();
    if (heading) {
      const start = text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trimStart();
      const wanted = heading.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
      if (wanted && !start.startsWith(wanted)) {
        text = `${heading}. ${text}`;
      }
    }
    return text;
  };

  // Split without losing or repeating words: sentence boundaries first, then
  // spaces, then a hard cut for a single impossible token.
  const chunkText = (text, limit) => {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    if (!clean) return [];
    if (clean.length <= limit) return [clean];

    const sentences = [];
    let rest = clean;
    while (rest.length) {
      const match = /^[\s\S]*?[.!?…](?:["')\]]+)?(?=\s|$)/.exec(rest);
      if (!match) {
        sentences.push(rest);
        break;
      }
      sentences.push(match[0].trim());
      rest = rest.slice(match[0].length).replace(/^\s+/, "");
    }

    const chunks = [];
    let current = "";
    const push = () => {
      if (current.trim()) chunks.push(current.trim());
      current = "";
    };
    for (const sentence of sentences) {
      if (sentence.length > limit) {
        push();
        let remaining = sentence;
        while (remaining.length > limit) {
          let cut = remaining.lastIndexOf(" ", limit);
          if (cut < Math.floor(limit / 2)) cut = limit;
          chunks.push(remaining.slice(0, cut).trim());
          remaining = remaining.slice(cut).trim();
        }
        if (remaining) current = remaining;
        continue;
      }
      if ((current ? current.length + 1 : 0) + sentence.length > limit) push();
      current = current ? `${current} ${sentence}` : sentence;
    }
    push();
    return chunks.filter(Boolean);
  };

  // The browser's voices can arrive *after* page load (notably in Chrome).
  // A device default still works when getVoices() initially returns [].
  const browserVoices = () => {
    try { return synth ? synth.getVoices() || [] : []; }
    catch (_) { return []; }
  };
  const voicesFor = (code) => browserVoices().filter((voice) =>
    String(voice.lang || "").toLowerCase().startsWith(`${code}-`) ||
    String(voice.lang || "").toLowerCase() === code);
  const languageTag = (code) => code === "hi" ? "hi-IN" : "en-US";
  const availableLanguages = (status) => {
    const codes = new Set();
    if (HAS_BROWSER_SPEECH) codes.add("en"); // system default, even before voiceschanged
    if (HAS_BROWSER_SPEECH && voicesFor("hi").length) codes.add("hi");
    if (status.tts?.available) {
      for (const item of status.tts.languages || []) codes.add(item.code);
    }
    return [...codes].filter((code) => code === "en" || code === "hi");
  };
  const selectVoice = (status, preference) => {
    const voices = status.tts?.available
      ? status.tts.languages?.find((item) => item.code === preference.language)?.voices || []
      : [];
    const selected = String(preference.voiceId || "");
    if (selected.startsWith("browser:") && HAS_BROWSER_SPEECH) {
      return { kind: "browser", id: selected.slice(8) };
    }
    const match = voices.find((item) => selected === item.id || selected === `elevenlabs:${item.id}`);
    if (match) return { kind: "elevenlabs", id: match.id };
    if (!selected && voices.length) return { kind: "elevenlabs", id: voices[0].id };
    if (HAS_BROWSER_SPEECH) return { kind: "browser", id: "default" };
    if (voices.length) return { kind: "elevenlabs", id: voices[0].id };
    return null;
  };

  // -------------------------------------------------------------------------
  // Audio helpers
  // -------------------------------------------------------------------------
  const decodeBase64 = (value) => {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  };

  const encodeBase64 = (bytes) => {
    let binary = "";
    const step = 0x8000;
    for (let i = 0; i < bytes.length; i += step) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
    }
    return btoa(binary);
  };

  let sessionChars = 0;
  let activePlayer = null;

  // -------------------------------------------------------------------------
  // One Listen control per educational block.
  // -------------------------------------------------------------------------
  const buildControls = (idleLabel = "Listen") => {
    const row = document.createElement("div");
    row.className = "voice-controls";
    row.setAttribute("data-voice-skip", "");

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn btn-soft btn-sm voice-listen";
    const toggleIcon = document.createElement("span");
    toggleIcon.className = "voice-icon";
    toggleIcon.innerHTML = icon("speaker");
    const toggleLabel = document.createElement("span");
    toggleLabel.className = "voice-label";
    toggleLabel.textContent = idleLabel;
    toggle.append(toggleIcon, toggleLabel);

    const stop = document.createElement("button");
    stop.type = "button";
    stop.className = "btn btn-ghost btn-sm voice-stop";
    stop.hidden = true;
    stop.innerHTML = `${icon("stop")}<span class="voice-label">Stop</span>`;

    const speedWrap = document.createElement("label");
    speedWrap.className = "voice-speed";
    speedWrap.hidden = true;
    speedWrap.textContent = "Speed ";
    const speed = document.createElement("select");
    speed.setAttribute("aria-label", "Playback speed");
    for (const value of [0.85, 1, 1.15, 1.35]) {
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = `${value}×`;
      speed.appendChild(option);
    }
    speedWrap.appendChild(speed);

    // Available on every note, not only on /tutor. These settings are shared
    // between all readers via localStorage, and stay closed until requested.
    const chooser = document.createElement("details");
    chooser.className = "voice-chooser";
    chooser.setAttribute("data-voice-settings", "");
    const summary = document.createElement("summary");
    summary.textContent = "Choose voice";
    const grid = document.createElement("div");
    grid.className = "voice-settings-grid";
    for (const [label, hook] of [["Language", "language"], ["Voice", "voice"]]) {
      const field = document.createElement("label");
      field.textContent = label;
      const select = document.createElement("select");
      select.setAttribute(`data-voice-${hook}`, "");
      select.setAttribute("aria-label", `${label} for reading`);
      field.appendChild(select);
      grid.appendChild(field);
    }
    const hint = document.createElement("p");
    hint.className = "tiny muted";
    hint.textContent = "Device voices depend on your browser. ElevenLabs voices need a connected server.";
    const chooserStatus = document.createElement("p");
    chooserStatus.className = "tiny muted";
    chooserStatus.setAttribute("data-voice-prefs-status", "");
    chooserStatus.setAttribute("role", "status");
    chooser.append(summary, grid, hint, chooserStatus);

    const state = document.createElement("span");
    state.className = "voice-state";
    state.setAttribute("role", "status");
    state.setAttribute("aria-live", "polite");

    row.append(toggle, stop, chooser, speedWrap, state);
    return { row, toggle, toggleIcon, toggleLabel, stop, speedWrap, speed, state, idleLabel };
  };

  const readers = new WeakMap();
  const attach = (host, titleOverride, textProvider, idleLabel = "Listen") => {
    if (!host) return null;
    const existing = readers.get(host);
    if (existing) {
      // Dynamic tutor answers replace innerHTML, which removes the old row.
      // Reattach it instead of leaving data-voice-bound set on a dead control.
      if (!host.contains(existing.ui.row)) {
        existing.stop();
        host.insertBefore(existing.ui.row, host.firstChild);
      }
      return existing;
    }
    host.dataset.voiceBound = "1";
    host.classList.add("has-voice");

    const ui = buildControls(idleLabel);
    const heading = host.querySelector("h1, h2, h3");
    if (heading && heading.parentNode === host) {
      heading.insertAdjacentElement("afterend", ui.row);
    } else {
      host.insertBefore(ui.row, host.firstChild);
    }

    const player = {
      host,
      ui,
      audio: new Audio(),
      utterance: null,
      mode: "",
      chunks: [],
      urls: [],
      index: 0,
      state: "idle",
      controllers: new Set(),
      token: 0,
      prefetching: new Map(),
    };
    readers.set(host, player);
    player.audio.preload = "auto";

    const prefs = () => readPrefs();
    ui.speed.value = String(prefs().speed);

    const isDynamicEmpty = () => {
      if (!host.hasAttribute("data-speak-dynamic")) return false;
      const content = [];
      collectText(host, content); // do not count data-speak-title as an answer
      return content.join(" ").trim().length < 2;
    };

    const setState = (state, message) => {
      player.state = state;
      ui.state.textContent = message || "";
      ui.toggle.disabled = state === "loading" || isDynamicEmpty();
      ui.row.classList.toggle("is-empty", isDynamicEmpty());
      ui.stop.hidden = state === "idle" || state === "error";
      ui.speedWrap.hidden = state === "idle" && !player.chunks.length;
      ui.toggle.setAttribute("aria-pressed", state === "playing" ? "true" : "false");
      if (state === "loading") {
        ui.toggleIcon.innerHTML = icon("speaker");
        ui.toggleLabel.textContent = "Preparing…";
      } else if (state === "playing") {
        ui.toggleIcon.innerHTML = icon("pause");
        ui.toggleLabel.textContent = "Pause";
      } else if (state === "paused") {
        ui.toggleIcon.innerHTML = icon("speaker");
        ui.toggleLabel.textContent = "Resume";
      } else if (state === "ended") {
        ui.toggleIcon.innerHTML = icon("replay");
        ui.toggleLabel.textContent = "Replay";
      } else if (state === "error") {
        ui.toggleIcon.innerHTML = icon("replay");
        ui.toggleLabel.textContent = "Retry";
      } else {
        ui.toggleIcon.innerHTML = icon("speaker");
        ui.toggleLabel.textContent = ui.idleLabel;
      }
    };

    const releaseUrls = () => {
      for (const url of player.urls) URL.revokeObjectURL(url);
      player.urls = [];
      player.prefetching.clear();
      try {
        player.audio.pause();
        player.audio.removeAttribute("src");
        player.audio.load();
      } catch (_) {
        /* nothing loaded */
      }
    };

    const abortRequests = () => {
      for (const controller of player.controllers) controller.abort();
      player.controllers.clear();
    };

    const cancelBrowser = () => {
      if (!player.utterance) return;
      player.utterance.onstart = null;
      player.utterance.onend = null;
      player.utterance.onerror = null;
      player.utterance = null;
      try { synth.cancel(); } catch (_) { /* speech already ended */ }
    };

    const stopPlayback = (message) => {
      player.token += 1;
      player.mode = "";
      abortRequests();
      cancelBrowser();
      releaseUrls();
      player.chunks = [];
      player.index = 0;
      player.pendingNext = null;
      setState("idle", message || "");
    };

    // Only one block may speak at once, across both audio engines.
    const claimPlayer = () => {
      if (activePlayer && activePlayer !== player) activePlayer.stop();
      activePlayer = player;
    };

    // Browser speech synthesizers can stall on long utterances. Small,
    // sentence-aligned chunks keep notes of any length readable. The next
    // utterance is queued only after the previous one has actually finished.
    const speakIndex = (index, notice = "") => {
      const token = player.token;
      if (index >= player.chunks.length) {
        player.utterance = null;
        setState("ended", "Finished.");
        return;
      }
      player.index = index;
      player.pendingNext = null;
      const utterance = new window.SpeechSynthesisUtterance(player.chunks[index]);
      const preference = readPrefs();
      utterance.lang = languageTag(player.language);
      utterance.rate = clampSpeed(preference.speed);
      const voiceId = player.voiceId;
      if (voiceId && voiceId !== "default") {
        const voice = voicesFor(player.language).find((item) => (item.voiceURI || item.name) === voiceId);
        if (voice) utterance.voice = voice;
      }
      const progress = `Speaking part ${index + 1} of ${player.chunks.length} with a device voice.`;
      utterance.onstart = () => {
        if (token === player.token && player.mode === "browser" && player.state !== "paused") {
          setState("playing", `${notice}${progress}`);
        }
      };
      utterance.onend = () => {
        if (token !== player.token || player.mode !== "browser") return;
        player.utterance = null;
        if (player.state === "paused") player.pendingNext = index + 1;
        else speakIndex(index + 1);
      };
      utterance.onerror = (event) => {
        if (token !== player.token || player.mode !== "browser") return;
        player.utterance = null;
        if (event?.error === "canceled" || event?.error === "interrupted") return;
        setState("error", "Your browser could not speak with that voice. Choose another voice or try a different browser.");
      };
      player.utterance = utterance;
      try {
        synth.speak(utterance);
        if (token === player.token && player.mode === "browser" && player.utterance === utterance && player.state !== "error") {
          setState("playing", `${notice}${progress}`);
        }
      } catch (_) {
        player.utterance = null;
        setState("error", "Your browser could not start speech. Check its sound and voice settings, then press Retry.");
      }
    };

    // Fall back from a failed paid request *at the same word*, not at the
    // beginning of the page. Aborted prefetches cannot create dangling blobs.
    const switchToBrowser = (index) => {
      if (!HAS_BROWSER_SPEECH) return false;
      const remaining = player.chunks.slice(index).join(" ");
      player.token += 1;
      player.mode = "browser";
      abortRequests();
      releaseUrls();
      player.chunks = chunkText(remaining, 190);
      player.voiceId = "default";
      speakIndex(0, "Natural voice unavailable; using your device instead. ");
      return true;
    };

    const ensureChunk = (index) => {
      if (index >= player.chunks.length) return Promise.resolve(null);
      if (player.prefetching.has(index)) return player.prefetching.get(index);
      const token = player.token;
      const chunk = player.chunks[index];
      const request = (async () => {
        if (sessionChars + chunk.length > SESSION_CHAR_BUDGET) {
          throw new Error("This tab has reached its ElevenLabs allowance. Listen with your device voice instead.");
        }
        const controller = new AbortController();
        player.controllers.add(controller);
        try {
          const response = await fetch(`${API_BASE}/api/voice/speech`, {
            method: "POST",
            headers: { "content-type": "application/json", accept: "audio/mpeg" },
            credentials: "omit",
            signal: controller.signal,
            body: JSON.stringify({ text: chunk, language: player.language, voiceId: player.voiceId }),
          });
          if (!response.ok) throw await errorFrom(response, "The natural voice service could not read that.");
          const blob = await response.blob();
          if (controller.signal.aborted || token !== player.token) return null;
          if (!blob.size) throw new Error("The voice service returned no audio.");
          sessionChars += chunk.length;
          const url = URL.createObjectURL(blob);
          player.urls.push(url);
          return url;
        } finally {
          player.controllers.delete(controller);
        }
      })().catch((error) => {
        player.prefetching.delete(index);
        throw error;
      });
      player.prefetching.set(index, request);
      return request;
    };

    const playIndex = async (index) => {
      const token = player.token;
      if (index >= player.chunks.length) {
        setState("ended", "Finished.");
        releaseUrls();
        return;
      }
      player.index = index;
      setState("loading", "Preparing natural voice…");
      let url;
      try {
        url = await ensureChunk(index);
      } catch (error) {
        if (token !== player.token || error?.name === "AbortError") return;
        if (switchToBrowser(index)) return;
        releaseUrls();
        setState("error", error.message || "The voice service is unavailable. Try again.");
        return;
      }
      if (token !== player.token) return;
      if (!url) {
        setState("ended", "Finished.");
        releaseUrls();
        return;
      }
      // Fetch one chunk ahead without holding an entire book in memory.
      ensureChunk(index + 1).catch(() => {});
      player.audio.src = url;
      player.audio.playbackRate = clampSpeed(readPrefs().speed);
      try {
        await player.audio.play();
      } catch (_) {
        if (token === player.token && !switchToBrowser(index)) {
          setState("error", "Playback was blocked. Check your sound settings and press Retry.");
        }
        return;
      }
      if (token !== player.token) return;
      setState("playing", `Playing part ${index + 1} of ${player.chunks.length} with ElevenLabs.`);
    };

    player.stop = () => stopPlayback("Stopped.");
    player.setSpeed = (value) => { player.audio.playbackRate = clampSpeed(value); };

    player.audio.addEventListener("ended", () => {
      if (player.mode === "elevenlabs" && player.state === "playing") playIndex(player.index + 1);
    });
    player.audio.addEventListener("error", () => {
      if (player.mode === "elevenlabs" && (player.state === "playing" || player.state === "loading")) {
        if (!switchToBrowser(player.index)) setState("error", "The audio could not be played. Press Retry.");
      }
    });

    const startReading = () => {
      claimPlayer();
      player.token += 1;
      player.mode = "";
      abortRequests();
      cancelBrowser();
      releaseUrls();
      const text = textProvider ? String(textProvider() || "") : extractText(host, titleOverride);
      if (text.length < 2) {
        setState("idle", "There is nothing to read here yet.");
        return;
      }
      const token = player.token;
      const begin = (status, notice = "") => {
        if (token !== player.token) return;
        const preference = readPrefs();
        const codes = availableLanguages(status);
        const language = codes.includes(preference.language) ? preference.language : codes[0] || preference.language;
        const choice = selectVoice(status, { ...preference, language });
        if (!choice) {
          setState("error", status.reason || "No speech voice is available in this browser or on the server.");
          return;
        }
        player.mode = choice.kind;
        player.voiceId = choice.id;
        player.language = language;
        player.urls = [];
        player.prefetching = new Map();
        if (choice.kind === "browser") {
          player.chunks = chunkText(text, 190);
          speakIndex(0, notice);
        } else {
          const limit = Math.max(200, Math.min(3000, Number(status.tts.maxChars) || 1200));
          player.chunks = chunkText(text, limit);
          playIndex(0);
        }
      };

      // When status is still loading, start device speech immediately rather
      // than waiting for a hung server. Next Listen uses ElevenLabs if ready.
      if (currentStatus) begin(currentStatus);
      else if (HAS_BROWSER_SPEECH) {
        begin(NO_BACKEND, "Checking the natural voice; ");
        if (HAS_API) getStatus().then(fillSettings).catch(() => {});
      } else {
        setState("loading", "Checking the voice service…");
        getStatus().then((status) => begin(status)).catch(() => {
          if (token === player.token) setState("error", "The voice service could not be reached. Try again later.");
        });
      }
    };
    player.read = startReading;

    ui.toggle.addEventListener("click", () => {
      const state = player.state;
      if (state === "playing") {
        if (player.mode === "browser") synth.pause();
        else player.audio.pause();
        setState("paused", "Playback paused.");
        return;
      }
      if (state === "paused") {
        if (player.mode === "browser") {
          try {
            synth.resume();
            const next = player.pendingNext;
            if (next !== null) speakIndex(next);
            else setState("playing", `Speaking part ${player.index + 1} of ${player.chunks.length} with a device voice.`);
          } catch (_) { setState("error", "Could not resume speech. Press Retry."); }
        } else {
          const token = player.token;
          player.audio.playbackRate = clampSpeed(readPrefs().speed);
          player.audio.play()
            .then(() => {
              if (token === player.token) setState("playing", `Playing part ${player.index + 1} of ${player.chunks.length} with ElevenLabs.`);
            })
            .catch(() => {
              if (token === player.token) setState("error", "Playback was blocked. Press Retry.");
            });
        }
        return;
      }
      startReading();
    });

    ui.stop.addEventListener("click", () => {
      player.stop();
      ui.toggle.focus();
    });

    ui.speed.addEventListener("change", () => {
      const value = clampSpeed(ui.speed.value);
      writePrefs({ speed: value });
      player.setSpeed(value);
      for (const other of documentRoot.querySelectorAll(".voice-speed select, [data-voice-speed]")) {
        if (other !== ui.speed) other.value = String(value);
      }
      if (player.mode === "browser" && player.state === "playing") {
        ui.state.textContent = "New speed takes effect on the next part.";
      }
    });

    // A dynamically filled block (a tutor answer, a checked quiz explanation)
    // starts empty. Keep the control out of the way until there is text.
    if (host.hasAttribute("data-speak-dynamic")) {
      // Only update the disabled state. Rewriting the status inside this
      // observer would itself create mutations and an endless callback loop.
      new MutationObserver(() => {
        const empty = isDynamicEmpty();
        ui.toggle.disabled = player.state === "loading" || empty;
        ui.row.classList.toggle("is-empty", empty);
      }).observe(host, { childList: true, subtree: true, characterData: true });
    }

    setState("idle", "");
    return player;
  };

  let voicesListenerAdded = false;
  const listenForVoices = () => {
    if (!synth || voicesListenerAdded) return;
    voicesListenerAdded = true;
    const refresh = () => fillSettings(currentStatus || NO_BACKEND);
    if (synth.addEventListener) synth.addEventListener("voiceschanged", refresh);
    else synth.onvoiceschanged = refresh;
  };

  const enhance = (root, title) => {
    const scope = root && root.nodeType === 1 ? root : documentRoot;
    const nodes = [];
    if (scope.hasAttribute && scope.hasAttribute("data-speak")) nodes.push(scope);
    if (title && scope.nodeType === 1 && !nodes.includes(scope)) nodes.push(scope);
    if (scope.querySelectorAll) nodes.push(...scope.querySelectorAll("[data-speak]"));
    for (const node of nodes) attach(node, title);
    // A chat reply can be the first speakable text on a page. Populate its
    // new picker and discover backend voices without requiring a page reload.
    if (root?.nodeType === 1 && nodes.length) {
      listenForVoices();
      fillSettings(currentStatus || NO_BACKEND);
      if (currentStatus && !currentStatus.tts?.available && !HAS_BROWSER_SPEECH) {
        voiceUnavailable(currentStatus.reason);
      }
      if (HAS_API && !currentStatus) getStatus().then((status) => {
        if (!status.tts?.available && !HAS_BROWSER_SPEECH) voiceUnavailable(status.reason);
        fillSettings(status);
      }).catch(() => {
        if (!HAS_BROWSER_SPEECH) voiceUnavailable("The voice service could not be reached, and this browser has no device voice.");
      });
    }
  };

  // On a multi-section lesson the student can hear the whole reading, not
  // only individual excerpts. Only explicitly marked educational blocks are
  // included; the menu, code samples, controls and other page chrome are not.
  const enhancePage = () => {
    const main = documentRoot.getElementById("main");
    const heading = main?.querySelector("h1");
    if (!heading) return;
    const sections = [...main.querySelectorAll("[data-speak]")].filter((node) =>
      !node.hasAttribute("data-speak-dynamic") && !node.parentElement?.closest("[data-speak]"));
    if (sections.length < 2) return;
    const host = documentRoot.createElement("div");
    host.className = "voice-page-reader";
    heading.insertAdjacentElement("afterend", host);
    attach(host, "", () => {
      const parts = sections.map((node) => extractText(node, "")).filter(Boolean);
      return `${heading.textContent.trim()}. ${parts.join("\n\n")}`;
    }, "Listen to all sections");
  };

  // All pickers (on lessons and on /tutor) share one set of preferences.
  // voiceschanged can fire many times; bind change handlers only once.
  const fillSettings = (status) => {
    const codes = availableLanguages(status);
    for (const panel of documentRoot.querySelectorAll("[data-voice-settings]")) {
      const languageSelect = panel.querySelector("[data-voice-language]");
      const voiceSelect = panel.querySelector("[data-voice-voice]");
      const speedSelect = panel.querySelector("[data-voice-speed]");
      const prefsStatus = panel.querySelector("[data-voice-prefs-status]");
      if (!languageSelect || !voiceSelect) continue;
      const prefs = readPrefs();
      languageSelect.replaceChildren();
      for (const code of codes) {
        const option = documentRoot.createElement("option");
        option.value = code;
        option.textContent = code === "hi" ? "Hindi" : "English";
        languageSelect.appendChild(option);
      }
      languageSelect.value = codes.includes(prefs.language) ? prefs.language : codes[0] || "";
      languageSelect.disabled = !codes.length;

      voiceSelect.replaceChildren();
      if (HAS_BROWSER_SPEECH) {
        const defaultVoice = documentRoot.createElement("option");
        defaultVoice.value = "browser:default";
        defaultVoice.textContent = "Device voice (default, free)";
        voiceSelect.appendChild(defaultVoice);
        for (const voice of voicesFor(languageSelect.value)) {
          const option = documentRoot.createElement("option");
          option.value = `browser:${voice.voiceURI || voice.name}`;
          option.textContent = `Device · ${voice.name} (${voice.lang})`;
          voiceSelect.appendChild(option);
        }
      }
      if (status.tts?.available) {
        const language = status.tts.languages?.find((item) => item.code === languageSelect.value);
        for (const voice of language?.voices || []) {
          const option = documentRoot.createElement("option");
          option.value = `elevenlabs:${voice.id}`;
          option.textContent = `ElevenLabs · ${voice.name} (natural)`;
          voiceSelect.appendChild(option);
        }
      }
      // Existing v1 preferences stored bare ElevenLabs IDs; keep them valid.
      const savedId = prefs.voiceId && !prefs.voiceId.includes(":")
        ? `elevenlabs:${prefs.voiceId}` : prefs.voiceId;
      const matches = [...voiceSelect.options].some((option) => option.value === savedId);
      if (matches) voiceSelect.value = savedId;
      else voiceSelect.value = status.tts?.available && !prefs.voiceId
        ? [...voiceSelect.options].find((option) => option.value.startsWith("elevenlabs:"))?.value || voiceSelect.options[0]?.value || ""
        : voiceSelect.options[0]?.value || "";
      voiceSelect.disabled = !voiceSelect.options.length;
      if (speedSelect) speedSelect.value = String(prefs.speed);
      if (prefsStatus) {
        prefsStatus.textContent = codes.length
          ? status.tts?.available
            ? "Device or ElevenLabs voice. Saved on this device."
            : "Device voice. Natural ElevenLabs speech needs a connected backend."
          : "No voice is available here. Try a browser with speech voices installed.";
      }
      if (panel.dataset.voiceSettingsBound === "1") continue;
      panel.dataset.voiceSettingsBound = "1";
      languageSelect.addEventListener("change", () => {
        writePrefs({ language: languageSelect.value, voiceId: "" });
        fillSettings(currentStatus || NO_BACKEND);
      });
      voiceSelect.addEventListener("change", () => {
        writePrefs({ language: languageSelect.value, voiceId: voiceSelect.value });
        fillSettings(currentStatus || NO_BACKEND);
      });
      speedSelect?.addEventListener("change", () => {
        const speed = clampSpeed(speedSelect.value);
        writePrefs({ speed });
        for (const other of documentRoot.querySelectorAll(".voice-speed select, [data-voice-speed]")) {
          if (other !== speedSelect) other.value = String(speed);
        }
        activePlayer?.setSpeed(speed);
      });
    }
  };

  const read = (host, title) => {
    const player = attach(host, title);
    if (!player) return;
    listenForVoices();
    fillSettings(currentStatus || NO_BACKEND);
    player.read();
  };

  // -------------------------------------------------------------------------
  // Spoken tutor (Conversational AI over the signed WebSocket URL)
  // -------------------------------------------------------------------------
  const PcmPlayer = (onIdle) => {
    let context = null;
    let gain = null;
    let nextTime = 0;
    let sources = new Set();
    let outputFormat = "pcm_16000";

    const ensure = () => {
      if (context) return context;
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) throw new Error("This browser cannot play conversation audio.");
      context = new Ctor();
      gain = context.createGain();
      gain.gain.value = 1;
      gain.connect(context.destination);
      return context;
    };

    const sampleRate = () => {
      const match = /pcm_(\d+)/.exec(outputFormat);
      return match ? Number(match[1]) : 16000;
    };

    const schedule = (buffer) => {
      if (!context) return;
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(gain);
      const startAt = Math.max(context.currentTime + 0.06, nextTime);
      source.start(startAt);
      nextTime = startAt + buffer.duration;
      sources.add(source);
      source.onended = () => {
        sources.delete(source);
        if (!sources.size && typeof onIdle === "function") onIdle();
      };
    };

    return {
      setFormat(format) {
        if (format) outputFormat = String(format);
      },
      async push(base64) {
        const ctx = ensure();
        if (ctx.state === "suspended") await ctx.resume();
        const bytes = decodeBase64(base64);
        if (/mp3|mpeg|opus/.test(outputFormat)) {
          const buffer = await ctx.decodeAudioData(bytes.buffer.slice(0));
          schedule(buffer);
          return;
        }
        if (/ulaw|alaw/.test(outputFormat)) {
          throw new Error("The agent is configured with a legacy audio format this browser cannot play.");
        }
        const rate = sampleRate();
        const samples = new Float32Array(Math.floor(bytes.length / 2));
        const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        for (let i = 0; i < samples.length; i += 1) {
          const value = view.getInt16(i * 2, true);
          samples[i] = value / 32768;
        }
        const buffer = ctx.createBuffer(1, samples.length, rate);
        buffer.copyToChannel(samples, 0);
        schedule(buffer);
      },
      stopAll() {
        for (const source of sources) {
          try {
            source.stop();
          } catch (_) {
            /* already stopped */
          }
        }
        sources = new Set();
        nextTime = 0;
      },
      close() {
        this.stopAll();
        try {
          context?.close();
        } catch (_) {
          /* already closed */
        }
        context = null;
        gain = null;
      },
    };
  };

  const setupTutor = (status) => {
    const panel = document.querySelector("[data-voice-tutor]");
    if (!panel) return;
    const startBtn = document.getElementById("voice-start");
    const muteBtn = document.getElementById("voice-mute");
    const endBtn = document.getElementById("voice-end");
    const statusEl = document.getElementById("voice-status");
    const setupEl = document.getElementById("voice-setup");
    const chip = document.getElementById("voice-tutor-chip");
    const transcript = document.getElementById("voice-transcript");
    if (!startBtn || !statusEl) return;

    const say = (message) => {
      statusEl.textContent = message;
    };
    const ready = Boolean(status.conversation && status.conversation.available);
    if (chip) {
      chip.textContent = ready ? "Ready" : "Not configured";
      chip.classList.toggle("ok", ready);
      chip.classList.toggle("warn", !ready);
    }

    if (IS_ANDROID_APP) {
      startBtn.disabled = true;
      if (chip) chip.textContent = "Use a browser";
      say("Spoken conversations need a microphone permission the Android app does not request. Open EngineVerse in Chrome or your browser to use the voice tutor. The written tutor and the voice reader still work here.");
      return;
    }
    if (!ready) {
      startBtn.disabled = true;
      if (setupEl) {
        setupEl.hidden = false;
        setupEl.textContent =
          status.conversation?.reason ||
          "The server has no ElevenLabs agent configured, so a spoken session cannot start yet.";
      }
      say("Use Ask by voice above if your browser supports it, or type a question and tap Listen on the answer. Live conversation requires an ElevenLabs agent.");
      return;
    }

    let ws = null;
    let stream = null;
    let inputCtx = null;
    let processor = null;
    let sourceNode = null;
    let player = null;
    let muted = false;
    let starting = false;
    let lastSpokeAt = 0;

    const addLine = (who, text) => {
      const value = String(text || "").trim();
      if (!value || !transcript) return;
      transcript.hidden = false;
      const line = document.createElement("p");
      line.className = "voice-line";
      const label = document.createElement("strong");
      label.textContent = `${who}: `;
      line.append(label, document.createTextNode(value));
      transcript.appendChild(line);
      while (transcript.children.length > 40) transcript.firstElementChild.remove();
      transcript.scrollTop = transcript.scrollHeight;
    };

    const teardown = () => {
      starting = false; // a failed attempt must not permanently disable Retry
      muted = false;
      try {
        processor?.disconnect();
        sourceNode?.disconnect();
      } catch (_) {
        /* already disconnected */
      }
      try {
        stream?.getTracks().forEach((track) => track.stop());
      } catch (_) {
        /* nothing captured */
      }
      try {
        inputCtx?.close();
      } catch (_) {
        /* already closed */
      }
      processor = null;
      sourceNode = null;
      inputCtx = null;
      stream = null;
      try {
        ws?.close();
      } catch (_) {
        /* already closed */
      }
      ws = null;
      player?.close();
      player = null;
      startBtn.hidden = false;
      startBtn.disabled = false;
      startBtn.textContent = "Start conversation";
      muteBtn.hidden = true;
      muteBtn.setAttribute("aria-pressed", "false");
      endBtn.hidden = true;
    };

    const bail = (message, setup) => {
      teardown();
      say(message);
      if (setup) {
        if (setupEl) {
          setupEl.hidden = false;
          setupEl.textContent = setup;
        }
      } else if (setupEl) {
        setupEl.hidden = true;
      }
    };

    const resample = (input, from, to = 16000) => {
      const outLength = Math.max(1, Math.floor((input.length * to) / from));
      const out = new Float32Array(outLength);
      const ratio = from / to;
      for (let i = 0; i < outLength; i += 1) {
        const position = i * ratio;
        const left = Math.floor(position);
        const right = Math.min(input.length - 1, left + 1);
        const mix = position - left;
        out[i] = (input[left] || 0) * (1 - mix) + (input[right] || 0) * mix;
      }
      return out;
    };

    const toPcm16 = (samples) => {
      const bytes = new Uint8Array(samples.length * 2);
      const view = new DataView(bytes.buffer);
      for (let i = 0; i < samples.length; i += 1) {
        const value = Math.max(-1, Math.min(1, samples[i]));
        view.setInt16(i * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
      }
      return bytes;
    };

    const connect = async () => {
      if (starting) return;
      starting = true;
      startBtn.disabled = true;
      startBtn.textContent = "Connecting…";
      say("Checking the voice service…");
      try {
        const current = await getStatus();
        if (!current.conversation || !current.conversation.available) {
          bail(
            current.conversation?.reason || "No ElevenLabs agent is configured on this server.",
            "An administrator must set ELEVENLABS_AGENT_ID and ENGINEVERSE_ELEVENLABS_ENABLED on the backend. The written tutor keeps working.",
          );
          return;
        }
      } catch (_) {
        bail("The voice service could not be reached. Check the server and try again.");
        return;
      }

      say("Requesting a secure session…");
      let session;
      try {
        const response = await fetch(`${API_BASE}/api/voice/session`, {
          method: "POST",
          headers: { "content-type": "application/json", accept: "application/json" },
          credentials: "omit",
          body: JSON.stringify({ language: readPrefs().language }),
        });
        if (!response.ok) throw await errorFrom(response, "The voice session could not be created.");
        session = await response.json();
      } catch (error) {
        bail(error.code === "agent_not_configured"
          ? "The server has no ElevenLabs agent configured yet."
          : error.message || "The voice session could not be created.",
          error.code === "agent_not_configured"
            ? "An administrator must set ELEVENLABS_AGENT_ID on the backend. The written tutor keeps working."
            : "");
        return;
      }

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        bail("This browser cannot open a microphone here. Voice conversations need HTTPS (or localhost) in a current browser.");
        return;
      }
      say("Asking for microphone permission…");
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      } catch (error) {
        const name = error && error.name;
        const message = name === "NotAllowedError" || name === "SecurityError"
          ? "Microphone permission was denied. Allow the microphone for this site in your browser settings, then press Start again."
          : name === "NotFoundError"
          ? "No microphone was found. Connect one and press Start again."
          : name === "NotReadableError"
          ? "The microphone is in use by another application. Close it and press Start again."
          : "The microphone could not be opened. Check your browser settings and try again.";
        bail(message);
        return;
      }

      player = PcmPlayer(() => {
        if (chip && !muted) chip.textContent = "Listening";
      });
      say("Opening the conversation…");
      try {
        ws = new WebSocket(session.signedUrl);
      } catch (_) {
        bail("The conversation could not be opened. Try again.");
        return;
      }

      ws.onopen = () => {
        starting = false;
        ws.send(JSON.stringify({ type: "conversation_initiation_client_data" }));
        startBtn.hidden = true;
        muteBtn.hidden = false;
        endBtn.hidden = false;
        if (transcript) transcript.hidden = false;
        if (chip) chip.textContent = "Listening";
        say("Connected. The tutor is listening — just start talking.");

        const InputCtor = window.AudioContext || window.webkitAudioContext;
        if (!InputCtor) {
          bail("This browser cannot stream microphone audio. Use the notes tutor above or try a current browser.");
          return;
        }
        try {
          inputCtx = new InputCtor();
          sourceNode = inputCtx.createMediaStreamSource(stream);
          processor = inputCtx.createScriptProcessor(4096, 1, 1);
        } catch (_) {
          bail("The microphone audio could not be started. Check your browser and try again.");
          return;
        }
        processor.onaudioprocess = (event) => {
          if (!ws || ws.readyState !== WebSocket.OPEN) return;
          if (muted) return;
          const input = event.inputBuffer.getChannelData(0);
          // A cheap level check is the only way to show "you are speaking"
          // without sending anything extra: the same samples are already on
          // their way to the agent.
          let energy = 0;
          for (let i = 0; i < input.length; i += 16) energy += input[i] * input[i];
          const level = Math.sqrt(energy / Math.max(1, input.length / 16));
          const now = Date.now();
          if (chip && level > 0.02 && now - lastSpokeAt > 900) {
            lastSpokeAt = now;
            chip.textContent = "You're speaking";
          }
          const samples = resample(input, inputCtx.sampleRate, 16000);
          ws.send(JSON.stringify({ user_audio_chunk: encodeBase64(toPcm16(samples)) }));
        };
        try {
          sourceNode.connect(processor);
          processor.connect(inputCtx.destination);
        } catch (_) {
          bail("The microphone audio could not be streamed. Check your browser and try again.");
        }
      };

      ws.onmessage = (event) => {
        let message;
        try {
          message = JSON.parse(event.data);
        } catch (_) {
          return;
        }
        switch (message.type) {
          case "ping": {
            const pingId = message.ping_event?.event_id ?? message.event_id;
            ws.send(JSON.stringify({ type: "pong", event_id: pingId }));
            break;
          }
          case "conversation_initiation_metadata": {
            const meta = message.conversation_initiation_metadata_event || {};
            player?.setFormat(meta.agent_output_audio_format);
            break;
          }
          case "audio": {
            const audio = message.audio_event?.audio_base_64 || message.audio_base_64;
            if (!audio) return;
            player?.push(audio).catch((error) => {
              say(error.message || "The incoming audio could not be played.");
            });
            if (chip) chip.textContent = "Tutor speaking";
            break;
          }
          case "interruption": {
            player?.stopAll();
            break;
          }
          case "user_transcript": {
            addLine("You", message.user_transcript_event?.user_transcript);
            break;
          }
          case "agent_response": {
            addLine("Tutor", message.agent_response_event?.agent_response);
            break;
          }
          default:
            break;
        }
      };

      ws.onerror = () => {
        if (ws) say("The connection reported a problem. Press End, then Start again.");
      };

      ws.onclose = (event) => {
        const wasActive = Boolean(ws);
        ws = null;
        if (wasActive) {
          if (event && event.code === 1000) {
            bail("Conversation ended.");
          } else {
            bail("The connection closed. Check your network, then press Start again.");
          }
        }
      };
    };

    startBtn.addEventListener("click", connect);

    muteBtn.addEventListener("click", () => {
      muted = !muted;
      muteBtn.setAttribute("aria-pressed", muted ? "true" : "false");
      muteBtn.innerHTML = `${icon(muted ? "micOff" : "mic")}<span class="voice-label">${muted ? "Unmute microphone" : "Mute microphone"}</span>`;
      if (chip) chip.textContent = muted ? "Microphone muted" : "Listening";
      say(muted ? "Microphone muted. The tutor cannot hear you." : "Microphone on. The tutor is listening.");
    });

    endBtn.addEventListener("click", () => {
      bail("Conversation ended. Nothing was saved.");
      startBtn.focus();
    });

    say("Press Start conversation. The microphone stays off until you do.");
    return { stop: () => { if (ws || stream) bail("Conversation ended. Nothing was saved."); } };
  };

  // Voice questions use the browser's speech recognizer, not an unconfigured
  // AI agent. The answer still comes from the existing, source-linked notes
  // tutor. Recognition may use the browser vendor's speech service; never
  // request the microphone on load or pretend it works in every browser.
  const setupVoiceQuestion = () => {
    const button = documentRoot.getElementById("voice-ask");
    const input = documentRoot.getElementById("tutor-question");
    const form = input?.closest("form");
    const status = documentRoot.getElementById("voice-ask-status");
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!button || !input || !form || !status || !Recognition || IS_ANDROID_APP) return null;
    button.hidden = false;
    status.hidden = false;
    status.textContent = "Ask by voice uses your browser's speech recognition service. The answer comes from EngineVerse notes and can be read aloud.";
    let listening = false;
    let recognizer = null;
    let waitingForAnswer = false;
    let heard = false;

    button.addEventListener("click", () => {
      if (listening) { recognizer?.stop(); return; }
      try {
        activePlayer?.stop(); // do not transcribe the app's own voice
        activeTutor?.stop(); // do not share the microphone with a live session
        heard = false;
        recognizer = new Recognition();
        recognizer.lang = languageTag(readPrefs().language);
        recognizer.continuous = false;
        recognizer.interimResults = false;
        recognizer.onstart = () => {
          listening = true;
          button.textContent = "Stop listening";
          status.textContent = "Listening… Ask your question now.";
        };
        recognizer.onresult = (event) => {
          const question = String(event.results?.[0]?.[0]?.transcript || "").trim();
          if (!question || heard) return;
          heard = true;
          waitingForAnswer = true;
          input.value = question.slice(0, input.maxLength > 0 ? input.maxLength : 400);
          status.textContent = `Heard: ${input.value}. Looking in the notes…`;
          if (form.requestSubmit) form.requestSubmit();
          else form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
        };
        recognizer.onerror = (event) => {
          if (heard) return; // the submitted answer may still be on its way
          waitingForAnswer = false;
          const message = event.error === "not-allowed" || event.error === "service-not-allowed"
            ? "Microphone access was denied. Allow it for this site, then try again."
            : event.error === "no-speech"
            ? "No speech was heard. Try again or type your question."
            : event.error === "network"
            ? "Your browser's speech recognition service is offline. Type your question instead."
            : "Could not recognize speech. Check your microphone or type your question.";
          status.textContent = message;
        };
        recognizer.onend = () => {
          listening = false;
          button.textContent = "Ask by voice";
          if (status.textContent.startsWith("Listening")) status.textContent = "Nothing was heard. Try again or type your question.";
          recognizer = null;
        };
        recognizer.start(); // the only place recognition can access the mic
      } catch (_) {
        listening = false;
        button.textContent = "Ask by voice";
        status.textContent = "Could not start the microphone. Use a current browser or type your question.";
      }
    });

    return {
      answered(host) {
        if (!waitingForAnswer) return;
        waitingForAnswer = false;
        if (!host || !extractText(host, "").trim()) {
          status.textContent = "There is no answer to read. Try another question.";
          return;
        }
        status.textContent = "Reading the answer aloud. Use Pause or Stop beside the answer to control it.";
        read(host, "Tutor answer");
      },
      failed() {
        if (!waitingForAnswer) return;
        waitingForAnswer = false;
        status.textContent = "The tutor could not answer. Try again or type your question.";
      },
      stop() { try { recognizer?.abort(); } catch (_) { /* already stopped */ } },
    };
  };
  let voiceQuestion = null;

  // -------------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------------
  let activeTutor = null;
  const bootVoice = () => {
    enhance(documentRoot, "");
    enhancePage();
    voiceQuestion = setupVoiceQuestion();
    // Nothing on this page can speak: do not contact the API at all.
    if (!documentRoot.querySelector("[data-speak], [data-voice-tutor]")) return;
    fillSettings(NO_BACKEND);
    listenForVoices();
    getStatus()
      .then((status) => {
        if (!status.tts?.available && !HAS_BROWSER_SPEECH) voiceUnavailable(status.reason);
        fillSettings(status);
        activeTutor = setupTutor(status);
      })
      .catch(() => {
        if (!HAS_BROWSER_SPEECH) voiceUnavailable("The voice service could not be reached, and this browser has no device voice. Try again later.");
        fillSettings(NO_BACKEND);
        activeTutor = setupTutor({ ...NO_BACKEND, conversation: { available: false, reason: "The live conversation service could not be reached. The device voice reader still works." } });
      });
  };

  // Leaving a page (including a bfcache snapshot) stops both audio engines,
  // releases blobs and microphone tracks, and aborts in-flight synthesis.
  window.addEventListener("pagehide", () => {
    try { activePlayer?.stop(); } catch (_) { /* nothing playing */ }
    voiceQuestion?.stop();
    activeTutor?.stop();
  });

  window.EV = window.EV || {};
  window.EV.voice = {
    enhance, read, extractText, chunkText, status: getStatus,
    tutorAnswered: (host) => voiceQuestion?.answered(host),
    tutorFailed: () => voiceQuestion?.failed(),
  };

  if (documentRoot.readyState === "loading") {
    documentRoot.addEventListener("DOMContentLoaded", bootVoice, { once: true });
  } else {
    bootVoice();
  }
})();
