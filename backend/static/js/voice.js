/* EngineVerse voice reader and voice tutor.
 *
 * Two capabilities, one opt-in module:
 *
 *  1. A Listen control on educational text. The text is extracted from the
 *     surrounding article (never the whole page), split into sentence-aligned
 *     chunks, and each chunk is synthesised by the FastAPI backend, which talks
 *     to ElevenLabs. Audio is played from a blob URL and released when done.
 *  2. A spoken tutor on /tutor. The browser asks the backend for a short-lived
 *     signed Conversational AI URL, then opens a WebSocket straight to
 *     ElevenLabs. The microphone is requested only after "Start conversation".
 *
 * Nothing here is required for EngineVerse to work: without this file, or
 * without a configured backend, the written site is unchanged. No API key is
 * ever present in the browser; the backend holds it.
 *
 * Privacy: spoken text is sent only when a student presses Listen, transcripts
 * stay in the page and are discarded when the conversation ends, and no audio
 * is stored in localStorage or on the server.
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
  // On GitHub Pages there is no server at all. Without a configured voice API
  // origin the controls are not rendered, so nobody is offered a button that
  // cannot work.
  if (STATIC_COPY && !API_BASE) return;

  const documentRoot = document;
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
  // Backend status (public, secret-free). Fetched once, and again after a
  // failure so a server brought online later starts working without a reload.
  // -------------------------------------------------------------------------
  let statusPromise = null;
  const getStatus = () => {
    if (!statusPromise) {
      statusPromise = fetch(`${API_BASE}/api/voice/status`, {
        headers: { accept: "application/json" },
        credentials: "omit",
      })
        .then((response) => {
          if (!response.ok) throw new Error(`status ${response.status}`);
          return response.json();
        })
        .catch((error) => {
          statusPromise = null;
          throw error;
        });
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
  const buildControls = (host) => {
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
    toggleLabel.textContent = "Listen";
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

    const state = document.createElement("span");
    state.className = "voice-state";
    state.setAttribute("role", "status");
    state.setAttribute("aria-live", "polite");

    row.append(toggle, stop, speedWrap, state);
    return { row, toggle, toggleIcon, toggleLabel, stop, speedWrap, speed, state };
  };

  const attach = (host, titleOverride) => {
    if (!host || host.dataset.voiceBound === "1") return;
    host.dataset.voiceBound = "1";
    host.classList.add("has-voice");

    const title = titleOverride || host.getAttribute("data-speak-title") || "this section";
    const ui = buildControls(host);
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
      chunks: [],
      urls: [],
      index: 0,
      state: "idle",
      controllers: new Set(),
      token: 0,
      prefetching: new Map(),
    };
    player.audio.preload = "auto";

    const prefs = () => readPrefs();
    ui.speed.value = String(prefs().speed);

    const isDynamicEmpty = () =>
      host.hasAttribute("data-speak-dynamic") && extractText(host, "").length < 2;

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
        ui.toggleLabel.textContent = "Listen";
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
      for (const controller of player.controllers) {
        try {
          controller.abort();
        } catch (_) {
          /* already aborted */
        }
      }
      player.controllers.clear();
    };

    const stopPlayback = (message) => {
      player.token += 1;
      abortRequests();
      releaseUrls();
      player.chunks = [];
      player.index = 0;
      setState("idle", message || "");
    };

    // Only one block may speak at once: starting a second one stops the first
    // and cancels its in-flight request, so two voices can never overlap.
    const claimPlayer = () => {
      if (activePlayer && activePlayer !== player) activePlayer.stop();
      activePlayer = player;
    };

    const ensureChunk = (index) => {
      if (index >= player.chunks.length) return Promise.resolve(null);
      if (player.prefetching.has(index)) return player.prefetching.get(index);
      const request = (async () => {
        if (sessionChars + player.chunks[index].length > SESSION_CHAR_BUDGET) {
          throw new Error(
            "This tab has read its voice allowance for now. A new tab starts a fresh allowance.",
          );
        }
        const status = await getStatus();
        if (!status.tts || !status.tts.available) {
          throw new Error(
            status.reason || status.tts?.reason || "The voice reader is not configured on this server.",
          );
        }
        const preference = prefs();
        const language = status.tts.languages.some((item) => item.code === preference.language)
          ? preference.language
          : status.tts.defaultLanguage;
        const controller = new AbortController();
        player.controllers.add(controller);
        const response = await fetch(`${API_BASE}/api/voice/speech`, {
          method: "POST",
          headers: { "content-type": "application/json", accept: "audio/mpeg" },
          credentials: "omit",
          signal: controller.signal,
          body: JSON.stringify({
            text: player.chunks[index],
            language,
            voiceId: preference.voiceId || undefined,
          }),
        });
        if (!response.ok) throw await errorFrom(response, "The voice service could not read that.");
        player.controllers.delete(controller);
        player.controllers.delete(controller);
        const blob = await response.blob();
        if (!blob.size) throw new Error("The voice service returned no audio.");
        sessionChars += player.chunks[index].length;
        const url = URL.createObjectURL(blob);
        player.urls.push(url);
        return url;
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
        releaseUrls();
        setState("ended", "Finished.");
        return;
      }
      player.index = index;
      setState("loading", "Preparing audio…");
      let url;
      try {
        url = await ensureChunk(index);
      } catch (error) {
        if (token !== player.token) return;
        if (error && error.name === "AbortError") return;
        releaseUrls();
        setState("error", error.message || "The voice service is unavailable. Try again.");
        return;
      }
      if (token !== player.token) return;
      if (!url) {
        releaseUrls();
        setState("ended", "Finished.");
        return;
      }
      // Prefetch the next chunk while this one plays, one request at a time.
      ensureChunk(index + 1).catch(() => {});
      player.audio.src = url;
      player.audio.playbackRate = clampSpeed(readPrefs().speed);
      try {
        await player.audio.play();
      } catch (_) {
        if (token === player.token) setState("error", "Playback was blocked. Press Listen again.");
        return;
      }
      if (token !== player.token) return;
      setState("playing", `Playing part ${index + 1} of ${player.chunks.length}.`);
    };

    player.stop = () => stopPlayback("Stopped.");
    player.setSpeed = (value) => {
      player.audio.playbackRate = clampSpeed(value);
    };

    player.audio.addEventListener("ended", () => {
      if (player.state === "playing") playIndex(player.index + 1);
    });
    player.audio.addEventListener("error", () => {
      if (player.state === "playing" || player.state === "loading") {
        setState("error", "The audio could not be played. Press Retry.");
      }
    });

    const startReading = async () => {
      claimPlayer();
      player.token += 1;
      abortRequests();
      releaseUrls();
      const text = extractText(host, titleOverride);
      if (text.length < 2) {
        setState("idle", "There is nothing to read here yet.");
        return;
      }
      setState("loading", "Checking the voice service…");
      let status;
      try {
        status = await getStatus();
      } catch (_) {
        setState("error", "The voice service could not be reached. Check the server and try again.");
        return;
      }
      if (!status.tts || !status.tts.available) {
        setState("error", status.reason || status.tts?.reason || "The voice reader is not configured.");
        return;
      }
      const limit = Math.max(200, Math.min(3000, Number(status.tts.maxChars) || 1200));
      player.chunks = chunkText(text, limit);
      if (!player.chunks.length) {
        setState("idle", "There is nothing to read here yet.");
        return;
      }
      player.urls = [];
      player.prefetching = new Map();
      setState("playing", ""); // transient; playIndex sets the real state
      await playIndex(0);
    };

    ui.toggle.addEventListener("click", () => {
      const state = player.state;
      if (state === "playing") {
        player.audio.pause();
        setState("paused", "Playback paused.");
        return;
      }
      if (state === "paused") {
        player.audio.playbackRate = clampSpeed(readPrefs().speed);
        player.audio
          .play()
          .then(() => setState("playing", `Playing part ${player.index + 1} of ${player.chunks.length}.`))
          .catch(() => setState("error", "Playback was blocked. Press Resume again."));
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
      for (const other of documentRoot.querySelectorAll(".voice-speed select")) {
        if (other !== ui.speed) other.value = String(value);
      }
    });

    // A dynamically filled block (a tutor answer, a checked quiz explanation)
    // starts empty. Keep the control out of the way until there is text.
    if (host.hasAttribute("data-speak-dynamic")) {
      // A tutor answer or a checked quiz explanation is filled in later, so the
      // control must react to text appearing rather than being decided once.
      new MutationObserver(() => setState(player.state, ui.state.textContent)).observe(host, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }

    setState("idle", "");
  };

  const enhance = (root, title) => {
    const scope = root && root.nodeType === 1 ? root : documentRoot;
    const nodes = [];
    if (scope.hasAttribute && scope.hasAttribute("data-speak")) nodes.push(scope);
    if (title && scope.nodeType === 1 && !nodes.includes(scope)) nodes.push(scope);
    if (scope.querySelectorAll) nodes.push(...scope.querySelectorAll("[data-speak]"));
    for (const node of nodes) attach(node, title);
  };

  // -------------------------------------------------------------------------
  // Voice settings (rendered on the tutor page, used by every player).
  // -------------------------------------------------------------------------
  const fillSettings = (status) => {
    const languageSelect = document.getElementById("voice-language");
    const voiceSelect = document.getElementById("voice-voice");
    const speedSelect = document.getElementById("voice-speed");
    const prefsStatus = document.getElementById("voice-prefs-status");
    if (!languageSelect || !voiceSelect) return;
    const languages = (status.tts && status.tts.languages) || [];
    const prefs = readPrefs();
    languageSelect.replaceChildren();
    for (const language of languages) {
      const option = document.createElement("option");
      option.value = language.code;
      option.textContent = language.label;
      languageSelect.appendChild(option);
    }
    const chosenLanguage = languages.some((item) => item.code === prefs.language)
      ? prefs.language
      : languages[0]?.code || "en";
    languageSelect.value = chosenLanguage;
    languageSelect.disabled = !languages.length;

    const renderVoices = () => {
      const language = languages.find((item) => item.code === languageSelect.value);
      voiceSelect.replaceChildren();
      for (const voice of (language && language.voices) || []) {
        const option = document.createElement("option");
        option.value = voice.id;
        option.textContent = voice.name;
        voiceSelect.appendChild(option);
      }
      const current = readPrefs();
      if (current.voiceId && [...voiceSelect.options].some((option) => option.value === current.voiceId)) {
        voiceSelect.value = current.voiceId;
      }
      voiceSelect.disabled = !voiceSelect.options.length;
    };
    renderVoices();
    if (speedSelect) speedSelect.value = String(prefs.speed);
    if (prefsStatus) {
      prefsStatus.textContent = languages.length
        ? "Saved on this device."
        : "No voices are configured yet, so there is nothing to choose.";
    }

    languageSelect.addEventListener("change", () => {
      renderVoices();
      writePrefs({ language: languageSelect.value, voiceId: voiceSelect.value || "" });
    });
    voiceSelect.addEventListener("change", () => {
      writePrefs({ language: languageSelect.value, voiceId: voiceSelect.value || "" });
    });
    speedSelect?.addEventListener("change", () => {
      writePrefs({ speed: clampSpeed(speedSelect.value) });
    });
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
      say("The written tutor above still works. The voice reader on notes and formulas works independently of this panel.");
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
        inputCtx = new InputCtor();
        sourceNode = inputCtx.createMediaStreamSource(stream);
        processor = inputCtx.createScriptProcessor(4096, 1, 1);
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
        sourceNode.connect(processor);
        processor.connect(inputCtx.destination);
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
  };

  // -------------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------------
  const bootVoice = () => {
    enhance(documentRoot, "");
    // Nothing on this page can speak: do not contact the API at all.
    if (!documentRoot.querySelector("[data-speak], [data-voice-tutor]")) return;
    getStatus()
      .then((status) => {
        // A successful status that says "not configured" means the Listen
        // controls would be dead buttons. Hide them instead of pretending the
        // feature is available; the tutor panel still explains what is missing.
        if (!status.tts || !status.tts.available) {
          documentRoot.documentElement.classList.add("voice-off");
        }
        fillSettings(status);
        setupTutor(status);
      })
      .catch(() => {
        fillSettings({ tts: { languages: [] } });
        setupTutor({ conversation: { available: false, reason: "The voice service could not be reached." }, tts: { languages: [] } });
      });
  };

  // Leaving the page (or switching tab away from a bfcache snapshot) releases
  // the audio blobs and stops any in-flight synthesis request.
  window.addEventListener("pagehide", () => {
    try {
      activePlayer?.stop();
    } catch (_) {
      /* nothing playing */
    }
  });

  window.EV = window.EV || {};
  window.EV.voice = { enhance, extractText, chunkText, status: getStatus };

  if (documentRoot.readyState === "loading") {
    documentRoot.addEventListener("DOMContentLoaded", bootVoice, { once: true });
  } else {
    bootVoice();
  }
})();
