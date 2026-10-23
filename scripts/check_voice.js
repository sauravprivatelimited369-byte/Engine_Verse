#!/usr/bin/env node
/* Behaviour checks for the voice reader and spoken tutor (static/js/voice.js).
 *
 *   npm install --prefix .toolchain/jsdom jsdom@26
 *   node scripts/check_voice.js
 *
 * No network, no credentials: the backend, WebSocket, device speech engine and
 * speech recognizer are stubbed. This verifies playback and fallback logic,
 * real exported markup (when site/ exists), long-form chunking without lost
 * words, controls after dynamic updates, cleanup and opt-in microphone access.
 * It cannot prove that an ElevenLabs account or a browser's installed voices
 * actually produce sound on a particular device.
 */
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const jsdomDir = process.env.JSDOM_DIR || path.join(__dirname, "..", ".toolchain", "jsdom");
let jsdom;
try {
  jsdom = require(path.join(path.resolve(jsdomDir), "node_modules", "jsdom"));
} catch (_) {
  jsdom = require("jsdom");
}
const { JSDOM, VirtualConsole } = jsdom;

const RUNTIME = fs.readFileSync(
  path.join(__dirname, "..", "backend", "static", "js", "voice.js"),
  "utf8",
);

const failures = [];
let passes = 0;
function check(label, condition, detail) {
  if (condition) {
    passes += 1;
  } else {
    failures.push(detail ? `${label}: ${detail}` : label);
  }
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const SECTION_HTML = `
  <nav><a href="/x">Navigation must not be read</a></nav>
  <h1>Example lessons</h1>
  <article data-speak data-speak-title="Ohm's law">
    <h2>Ohm's law</h2>
    <p>Voltage equals current multiplied by resistance. V = IR describes a linear resistor.</p>
    <pre class="console">print("console output must not be read")</pre>
    <p>It applies to many conductors at room temperature.</p>
    <button>Mark complete</button>
  </article>
  <footer>Footer text must not be read</footer>`;

const SECOND_SECTION = `
  <section data-speak data-speak-title="Power">
    <h2>Power</h2>
    <p>Electrical power is voltage multiplied by current.</p>
  </section>`;

const TUTOR_HTML = `
  <form id="tutor-voice-form" data-tutor-form><input id="tutor-question" maxlength="400">
    <button type="submit" id="tutor-send">Ask</button>
    <button type="button" id="voice-ask" hidden>Ask by voice</button></form>
  <p id="voice-ask-status" role="status" hidden></p>
  <div id="tutor-answer" data-speak data-speak-dynamic></div>
  <section data-voice-tutor id="voice-tutor">
    <span id="voice-tutor-chip">Checking</span>
    <button id="voice-start" type="button">Start conversation</button>
    <button id="voice-mute" type="button" hidden>Mute microphone</button>
    <button id="voice-end" type="button" hidden>End conversation</button>
    <p id="voice-status" role="status" aria-live="polite"></p>
    <p id="voice-setup" hidden></p>
    <div id="voice-transcript" hidden></div>
    <details id="voice-settings" data-voice-settings><summary>Voice settings</summary>
      <select id="voice-language" data-voice-language></select>
      <select id="voice-voice" data-voice-voice></select>
      <select id="voice-speed" data-voice-speed><option value="1">1x</option></select>
      <p id="voice-prefs-status" data-voice-prefs-status></p>
    </details>
  </section>`;

const STATUS_READY = {
  enabled: true,
  configured: true,
  reason: "",
  tts: {
    available: true,
    maxChars: 1200,
    defaultLanguage: "en",
    languages: [
      { code: "en", label: "English", voices: [{ id: "voice-en", name: "English voice" }] },
      { code: "hi", label: "Hindi", voices: [{ id: "voice-hi", name: "Hindi voice" }] },
    ],
  },
  conversation: { available: true, agentConfigured: true, reason: "" },
};

class FakeAudio extends EventTarget {
  static instances = [];
  constructor() {
    super();
    FakeAudio.instances.push(this);
    this._src = "";
    this.paused = true;
    this.playbackRate = 1;
    this.playCalls = 0;
  }
  set src(value) {
    this._src = value;
  }
  get src() {
    return this._src;
  }
  play() {
    this.paused = false;
    this.playCalls += 1;
    return Promise.resolve();
  }
  pause() {
    this.paused = true;
  }
  removeAttribute() {
    this._src = "";
  }
  load() {}
  finish() {
    this.paused = true;
    this.dispatchEvent(new Event("ended"));
  }
}

function response(body, { status = 200, type = "application/json", headers = {} } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (key) => headers[String(key).toLowerCase()] ?? null },
    async json() {
      return typeof body === "string" ? JSON.parse(body) : body;
    },
    async blob() {
      return { size: 12, type };
    },
  };
}

async function boot({
  body = SECTION_HTML + SECOND_SECTION,
  apiBase = "https://voice.example",
  staticCopy = true,
  status = STATUS_READY,
  session = { ok: true, signedUrl: "wss://api.elevenlabs.io/v1/convai/conversation?token=x" },
  speechStatus = 200,
  speechHang = false,
  statusError = false,
  browserSpeech = false,
  recognition = false,
  withTutor = false,
} = {}) {
  const html = `<!doctype html><html><head><meta charset="utf-8">
    <script type="application/json" id="ev-voice-config">${JSON.stringify({ apiBase, staticCopy })}</script>
    </head><body><main id="main">${body}${withTutor ? TUTOR_HTML : ""}</main></body></html>`;
  const virtualConsole = new VirtualConsole();
  const errors = [];
  virtualConsole.on("jsdomError", (error) => errors.push(String(error && error.message || error)));
  const dom = new JSDOM(html, {
    url: `${staticCopy ? "https://example.github.io/EngineVerse/" : "http://localhost:8000/"}tutor/`,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const w = dom.window;
  await sleep(5);

  const calls = { fetch: [], revoked: [], created: 0, status: 0, speech: 0, session: 0, getUserMedia: 0, recognition: 0 };
  const blobUrls = new Set();
  w.URL.createObjectURL = () => {
    calls.created += 1;
    const url = `blob:test-${calls.created}`;
    blobUrls.add(url);
    return url;
  };
  w.URL.revokeObjectURL = (url) => calls.revoked.push(url);
  FakeAudio.instances = [];
  w.Audio = FakeAudio;
  w.fetch = async (url, options = {}) => {
    calls.fetch.push({ url, options });
    if (url.endsWith("/api/voice/status")) {
      calls.status += 1;
      if (statusError) throw new Error("No backend");
      return response(status);
    }
    if (url.endsWith("/api/voice/speech")) {
      calls.speech += 1;
      if (speechHang) return new Promise((resolve, reject) => {
        options.signal.addEventListener("abort", () => reject(Object.assign(new Error("Aborted"), { name: "AbortError" })));
      });
      if (speechStatus !== 200) {
        return response(
          { ok: false, error: "The voice service is unavailable right now.", code: "upstream_unavailable" },
          { status: speechStatus },
        );
      }
      return response("audio", { type: "audio/mpeg" });
    }
    if (url.endsWith("/api/voice/session")) {
      calls.session += 1;
      if (session.status && session.status !== 200) {
        return response(session.body || { ok: false, error: "No agent.", code: session.code }, {
          status: session.status,
          headers: session.code === "agent_not_configured" ? { "x-voice-setup-required": "1" } : {},
        });
      }
      return response(session);
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  class FakeSocket {
    static OPEN = 1;
    static instances = [];
    constructor(url) {
      this.url = url;
      this.readyState = 1;
      this.sent = [];
      this.closed = false;
      FakeSocket.instances.push(this);
    }
    send(data) {
      this.sent.push(data);
    }
    close() {
      this.closed = true;
    }
  }
  w.WebSocket = FakeSocket;

  const tracks = [];
  w.navigator.mediaDevices = {
    getUserMedia: async () => {
      calls.getUserMedia += 1;
      const track = { stopped: false, stop() { this.stopped = true; } };
      tracks.push(track);
      return { getTracks: () => [track] };
    },
  };

  class FakeAudioContext {
    constructor() {
      this.currentTime = 0;
      this.state = "running";
      this.sampleRate = 48000;
      this.destination = {};
    }
    createGain() {
      return { gain: { value: 1 }, connect() {} };
    }
    createBufferSource() {
      return {
        buffer: null,
        connect() {},
        start() {},
        stop() {},
        onended: null,
      };
    }
    createBuffer(channels, length) {
      return { duration: length / 16000, copyToChannel() {} };
    }
    createMediaStreamSource() {
      return { connect() {}, disconnect() {} };
    }
    createScriptProcessor() {
      return { connect() {}, disconnect() {}, onaudioprocess: null };
    }
    resume() {
      return Promise.resolve();
    }
    close() {
      return Promise.resolve();
    }
  }
  w.AudioContext = FakeAudioContext;

  const spoken = {
    utterances: [], current: null, pauses: 0, resumes: 0, cancels: 0, voices: [],
    getVoices() { return this.voices; },
    speak(utterance) {
      this.current = utterance;
      this.utterances.push(utterance);
      utterance.onstart?.();
    },
    pause() { this.pauses += 1; },
    resume() { this.resumes += 1; },
    cancel() { this.cancels += 1; this.current = null; },
    finish() { const current = this.current; this.current = null; current?.onend?.(); },
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    loadVoices(voices) { this.voices = voices; this.listeners.voiceschanged?.(); },
  };
  if (browserSpeech) {
    w.SpeechSynthesisUtterance = class {
      constructor(text) { this.text = text; this.rate = 1; this.voice = null; }
    };
    w.speechSynthesis = spoken;
  }

  const recognizers = [];
  if (recognition) {
    w.SpeechRecognition = class {
      constructor() { recognizers.push(this); }
      start() { calls.recognition += 1; this.onstart?.(); }
      stop() { this.onend?.(); }
      abort() { this.onend?.(); }
      result(text) { this.onresult?.({ results: [[{ transcript: text }]] }); }
      error(reason) { this.onerror?.({ error: reason }); this.onend?.(); }
    };
  }

  w.eval(RUNTIME);
  await sleep(20);
  return { w, d: w.document, calls, errors, tracks, FakeSocket, blobUrls, FakeAudio, spoken, recognizers };
}

const section = (d) => d.querySelector("article[data-speak]");
const controlsIn = (host) => host.querySelector(".voice-controls");
const stateOf = (host) => host.querySelector(".voice-state").textContent;

async function main() {
  // ----------------------------------------------------------------- 1. controls
  {
    const { d } = await boot();
    const article = section(d);
    check("reader: a Listen control is added to educational text", Boolean(controlsIn(article)));
    check("reader: the control has an accessible label", /\bListen\b/.test(article.querySelector(".voice-listen").textContent));
    check("reader: no control inside a code block", !d.querySelector("pre .voice-controls"));
    check("reader: no control inside navigation", !d.querySelector("nav .voice-controls"));
    check("reader: second section gets its own control", Boolean(controlsIn(d.querySelectorAll("[data-speak]")[1])));
  }

  // ------------------------------------------------------------- 2. extraction
  {
    const { w, d } = await boot();
    const host = section(d);
    const text = w.EV.voice.extractText(host, "Ohm's law");
    check("extract: heading once", (text.match(/Ohm's law/g) || []).length === 1, text);
    check("extract: keeps the explanation", /linear resistor/.test(text));
    check("extract: drops code output", !/console output/.test(text));
    check("extract: drops navigation and footer", !/Navigation must not/.test(text) && !/Footer text/.test(text));
    check("extract: drops button labels", !/Mark complete/.test(text));
  }

  // -------------------------------------------------------------- 3. chunking
  {
    const { w } = await boot();
    const text = ("A sentence about thermodynamics with several words. ").repeat(40);
    const chunks = w.EV.voice.chunkText(text, 120);
    const words = (value) => value.replace(/\s+/g, " ").trim().split(" ");
    check("chunk: every chunk within the limit", chunks.every((chunk) => chunk.length <= 120), chunks.map((c) => c.length).join(","));
    check("chunk: no words lost or repeated", words(chunks.join(" ")).join(" ") === words(text).join(" "));
    check("chunk: more than one chunk for long text", chunks.length > 1);
  }

  // ------------------------------------------- 3b. long content, chunk by chunk
  {
    const longText = Array.from({ length: 14 }, (_, i) =>
      `Rule ${i + 1} explains how a resistor behaves under load.`).join(" ");
    const body = `<article data-speak data-speak-title="Long note"><h2>Long note</h2><p>${longText}</p></article>`;
    const status = { ...STATUS_READY, tts: { ...STATUS_READY.tts, maxChars: 240 } };
    const { d, w, calls, FakeAudio } = await boot({ body, status });
    const article = d.querySelector("article[data-speak]");
    article.querySelector(".voice-listen").click();
    await sleep(20);
    let guard = 0;
    while (guard < 40) {
      guard += 1;
      const state = d.querySelector("article .voice-state").textContent;
      if (/Finished/.test(state)) break;
      const audio = FakeAudio.instances.filter((item) => item.src).pop();
      if (audio && !audio.paused) audio.finish();
      else await sleep(15);
      await sleep(15);
    }
    const sent = calls.fetch
      .filter((call) => call.url.endsWith("/speech"))
      .map((call) => JSON.parse(call.options.body).text);
    const expected = w.EV.voice.extractText(article, "Long note");
    const words = (value) => value.replace(/\s+/g, " ").trim().split(" ");
    check("long: every chunk was synthesised", sent.length > 1, String(sent.length));
    check("long: no words lost or repeated across chunks",
      words(sent.join(" ")).join(" ") === words(expected).join(" "));
    check("long: each request stays within the server limit",
      sent.every((text) => text.length <= 240), sent.map((t) => t.length).join(","));
    check("long: playback reaches the end", /Finished/.test(d.querySelector("article .voice-state").textContent));
  }

  // ---------------------------------------------------------------- 4. playing
  {
    const { w, d, calls } = await boot();
    const article = section(d);
    article.querySelector(".voice-listen").click();
    await sleep(20);
    check("play: a synthesis request is sent", calls.speech === 1);
    const sent = JSON.parse(calls.fetch.find((call) => call.url.endsWith("/speech")).options.body);
    check("play: the request contains the article, not the page", /linear resistor/.test(sent.text) && !/Navigation/.test(sent.text));
    check("play: language is sent", sent.language === "en");
    check("play: no API key is present in the page request", !JSON.stringify(sent).toLowerCase().includes("elevenlabs-api-key"));
    const audio = article.querySelector(".voice-listen");
    check("play: state becomes playing", /Playing part 1/.test(stateOf(article)), stateOf(article));
    check("play: the button offers Pause", /Pause/.test(audio.textContent));
    check("play: an object URL was created", calls.created === 1);
    check("play: nothing is stored in localStorage except preferences", !Object.keys(w.localStorage).some((k) => k.includes("transcript")));
  }

  // --------------------------------------------------- 5. pause/resume/stop/speed
  {
    const { d, calls, FakeAudio } = await boot();
    const article = section(d);
    const toggle = article.querySelector(".voice-listen");
    toggle.click();
    await sleep(20);
    toggle.click();
    check("playback: Pause shows paused state", /paused/i.test(stateOf(article)), stateOf(article));
    check("playback: Resume is offered", /Resume/.test(toggle.textContent));
    toggle.click();
    await sleep(20);
    check("playback: Resume plays again", /Playing/.test(stateOf(article)));
    const speed = article.querySelector(".voice-speed select");
    speed.value = "1.35";
    speed.dispatchEvent(new d.defaultView.Event("change"));
    const audio = FakeAudio.instances.find((item) => item.src);
    check("playback: speed applies to the audio in progress", Boolean(audio) && audio.playbackRate === 1.35,
      audio ? String(audio.playbackRate) : "no audio");
    check("playback: speed preference is remembered", /"speed":1.35/.test(d.defaultView.localStorage.getItem("ev:voice:v1") || ""));
    article.querySelector(".voice-stop").click();
    check("playback: Stop clears the state", stateOf(article) === "Stopped.", stateOf(article));
    check("playback: Stop releases the audio URL", calls.revoked.length >= 1);
    check("playback: Stop labels the control Listen again", /Listen/.test(toggle.textContent));
  }

  // ------------------------------------------------- 6. one active player only
  {
    const { d, calls } = await boot();
    const first = section(d);
    const second = d.querySelectorAll("[data-speak]")[1];
    first.querySelector(".voice-listen").click();
    await sleep(20);
    second.querySelector(".voice-listen").click();
    await sleep(20);
    check("players: only one block is active", /Stopped/.test(stateOf(first)) && /Playing/.test(stateOf(second)),
      `${stateOf(first)} / ${stateOf(second)}`);
    check("players: switching released the first audio", calls.revoked.length >= 1);
  }

  // ------------------------------------------------------------ 7. error + retry
  {
    const { d } = await boot({ speechStatus: 503 });
    const article = section(d);
    const toggle = article.querySelector(".voice-listen");
    toggle.click();
    await sleep(20);
    check("error: a friendly message is shown", /unavailable/i.test(stateOf(article)), stateOf(article));
    check("error: a retry is offered", /Retry/.test(toggle.textContent));
    check("error: the message is announced politely", article.querySelector(".voice-state").getAttribute("aria-live") === "polite");
  }

  // ------------------------------------------------ 8. feature not configured
  {
    const notConfigured = {
      ...STATUS_READY,
      configured: false,
      tts: { available: false, maxChars: 1200, languages: [], defaultLanguage: "en" },
      reason: "The server has no ElevenLabs API key configured.",
    };
    const { d, calls } = await boot({ status: notConfigured });
    section(d).querySelector(".voice-listen").click();
    await sleep(20);
    check("setup: missing key is explained", /API key configured/.test(stateOf(section(d))), stateOf(section(d)));
    check("setup: no paid request is made", calls.speech === 0);
  }

  // ------------------------------------------- 9. static copy without a backend
  {
    const { d, calls } = await boot({ apiBase: "" });
    check("static: no reader controls without a voice API", !d.querySelector(".voice-controls"));
    check("static: the status endpoint is not called", calls.status === 0);
  }

  // ---------------------------------------------------- 10. microphone consent
  {
    const { d, calls } = await boot({ withTutor: true });
    check("tutor: microphone is not touched on load", calls.getUserMedia === 0);
    check("tutor: settings list the configured voices", d.querySelectorAll("#voice-voice option").length === 1);
    d.querySelector("#voice-language").value = "hi";
    d.querySelector("#voice-language").dispatchEvent(new d.defaultView.Event("change"));
    check("tutor: changing language persists the choice", /"language":"hi"/.test(d.defaultView.localStorage.getItem("ev:voice:v1") || ""));
  }

  // ----------------------------------------------- 11. start / mute / end flow
  {
    const { d, calls, tracks, FakeSocket } = await boot({ withTutor: true });
    const start = d.querySelector("#voice-start");
    const mute = d.querySelector("#voice-mute");
    const end = d.querySelector("#voice-end");
    start.click();
    await sleep(40);
    check("tutor: session is requested from the backend", calls.session === 1);
    check("tutor: microphone requested only after Start", calls.getUserMedia === 1);
    const socket = FakeSocket.instances[0];
    check("tutor: the signed URL is used for the socket", socket && /wss:\/\//.test(socket.url));
    socket.onopen();
    await sleep(10);
    check("tutor: Start hides when connected", start.hidden === true);
    check("tutor: mute and end appear", mute.hidden === false && end.hidden === false);
    check("tutor: the connection state is announced", /Connected/.test(d.querySelector("#voice-status").textContent));
    socket.onmessage({ data: JSON.stringify({ type: "ping", ping_event: { event_id: 9 } }) });
    check("tutor: a ping is answered with a pong", socket.sent.some((raw) => /"pong"/.test(raw) && /9/.test(raw)));
    mute.click();
    check("tutor: mute is a pressed toggle", mute.getAttribute("aria-pressed") === "true");
    check("tutor: mute relabels the control", /Unmute/.test(mute.textContent));
    end.click();
    await sleep(10);
    check("tutor: End closes the socket", socket.closed === true);
    check("tutor: End releases the microphone", tracks.every((track) => track.stopped));
    check("tutor: End returns to the Start control", start.hidden === false && end.hidden === true);
  }

  // -------------------------------------------- 12. missing agent is explained
  {
    const { d, calls } = await boot({
      withTutor: true,
      session: { status: 503, code: "agent_not_configured", body: { ok: false, code: "agent_not_configured", error: "No agent." } },
    });
    d.querySelector("#voice-start").click();
    await sleep(40);
    const setup = d.querySelector("#voice-setup");
    check("tutor: missing agent shows setup guidance", setup.hidden === false && /ELEVENLABS_AGENT_ID/.test(setup.textContent), setup.textContent);
    check("tutor: microphone is never requested without an agent", calls.getUserMedia === 0);
  }

  // ------------------------------- 13. no API origin: honest, not silent
  {
    const { d, calls } = await boot({ apiBase: "", withTutor: true });
    const notice = d.querySelector(".voice-unavailable");
    check("unconfigured: the page says voice is not connected", Boolean(notice), "no notice rendered");
    check(
      "unconfigured: the notice is readable text, not an empty placeholder",
      Boolean(notice) && /no voice backend is connected/i.test(notice.textContent) && notice.textContent.length > 40,
      notice && notice.textContent,
    );
    check("unconfigured: the notice is a note, not a live region", Boolean(notice) && notice.getAttribute("role") === "note");
    check("unconfigured: no Listen button is offered", d.querySelectorAll(".voice-listen").length === 0);
    check("unconfigured: no request is sent to an empty endpoint", calls.fetch.length === 0, JSON.stringify(calls.fetch));
    check("unconfigured: the tutor Start control is disabled", d.querySelector("#voice-start").disabled === true);
    check(
      "unconfigured: the tutor chip reports Not connected",
      /Not connected/.test(d.querySelector("#voice-tutor-chip").textContent),
      d.querySelector("#voice-tutor-chip").textContent,
    );
    check("unconfigured: no microphone is requested", calls.getUserMedia === 0);
    check("unconfigured: the page is marked voice-off", d.documentElement.classList.contains("voice-off"));
    check("unconfigured: one notice only", d.querySelectorAll(".voice-unavailable").length === 1);
  }

  // --------------------------------- 14. free, real device speech on Pages
  {
    const { d, w, calls, spoken, errors } = await boot({ apiBase: "", browserSpeech: true });
    const article = section(d);
    const readAll = d.querySelector(".voice-page-reader");
    check("device: Listen appears without an API origin", Boolean(article.querySelector(".voice-listen")));
    check("device: a multi-section page offers Listen to all", /Listen to all sections/.test(readAll?.textContent || ""));
    check("device: a voice picker is accessible on the article", Boolean(article.querySelector("[data-voice-voice]")));
    check("device: nothing calls a nonexistent Pages API", calls.fetch.length === 0, JSON.stringify(calls.fetch));
    article.querySelector(".voice-listen").click();
    check("device: speech synthesis is invoked by a click", spoken.utterances.length === 1);
    check("device: only the relevant note is read", /linear resistor/.test(spoken.utterances[0]?.text || "") &&
      !/Navigation|console output|Footer text/.test(spoken.utterances[0]?.text || ""));
    check("device: device speech has a real playing state", /device voice/.test(stateOf(article)));
    const toggle = article.querySelector(".voice-listen");
    toggle.click();
    check("device: Pause calls the speech engine", spoken.pauses === 1 && /paused/.test(stateOf(article)));
    toggle.click();
    check("device: Resume calls the speech engine", spoken.resumes === 1 && /Speaking/.test(stateOf(article)));
    readAll.querySelector(".voice-listen").click();
    check("device: starting all sections cancels the previous voice", spoken.cancels === 1 && /Stopped/.test(stateOf(article)));
    check("device: all-section speech starts with the page heading", /Ohm's law/.test(spoken.current?.text || ""));
    const spokenAll = [];
    let guard = 0;
    while (guard++ < 30 && !/Finished/.test(readAll.querySelector(".voice-state").textContent)) {
      if (spoken.current) { spokenAll.push(spoken.current.text); spoken.finish(); }
      else break;
    }
    const allWords = spokenAll.join(" ");
    check("device: all-section speech includes the other section", /Electrical power/.test(allWords));
    check("device: all-section speech omits page chrome and code", !/Navigation|console output|Footer text/.test(allWords));
    check("device: all-section reading finishes", /Finished/.test(readAll.querySelector(".voice-state").textContent));
    check("device: no browser exceptions", errors.length === 0, errors.join("; "));
  }

  // ----------------------------------------------- 15. no lost long sentences
  {
    const longText = Array.from({ length: 35 }, (_, i) => `Rule ${i + 1} explains a circuit clearly.`).join(" ");
    const body = `<article data-speak data-speak-title="Long note"><h2>Long note</h2><p>${longText}</p></article>`;
    const { d, w, spoken, calls } = await boot({ body, apiBase: "", browserSpeech: true });
    const host = section(d);
    host.querySelector(".voice-listen").click();
    let guard = 0;
    while (guard++ < 60 && !/Finished/.test(stateOf(host))) spoken.finish();
    const actual = spoken.utterances.map((item) => item.text);
    const expected = w.EV.voice.extractText(host, "Long note").replace(/\s+/g, " ").trim();
    check("long device: several short utterances", actual.length > 2 && actual.every((item) => item.length <= 190), actual.map((a) => a.length).join(","));
    check("long device: no words lost or repeated", actual.join(" ") === expected);
    check("long device: completion is announced", /Finished/.test(stateOf(host)));
    check("long device: no backend charge", calls.speech === 0);
  }

  // -------------------------------------- 16. installed language/voice picker
  {
    const { d, w, spoken } = await boot({ apiBase: "", browserSpeech: true, withTutor: true });
    const english = { voiceURI: "english-1", lang: "en-US", name: "Clear English" };
    const hindi = { voiceURI: "hindi-1", lang: "hi-IN", name: "Hindi speaker" };
    spoken.loadVoices([english, hindi]);
    const language = d.querySelector("#voice-language");
    check("settings: late-loaded Hindi voice is offered", [...language.options].some((o) => o.value === "hi"));
    language.value = "hi";
    language.dispatchEvent(new w.Event("change"));
    const voice = d.querySelector("#voice-voice");
    check("settings: device voice has a name", [...voice.options].some((o) => /Hindi speaker/.test(o.textContent)));
    voice.value = "browser:hindi-1";
    voice.dispatchEvent(new w.Event("change"));
    const lessonVoice = section(d).querySelector("[data-voice-voice]");
    check("settings: tutor and lesson choices stay in sync", lessonVoice.value === voice.value);
    section(d).querySelector(".voice-listen").click();
    check("settings: chosen voice and language are spoken", spoken.current?.voice === hindi && spoken.current?.lang === "hi-IN");
    check("settings: chosen voice persists", /browser:hindi-1/.test(w.localStorage.getItem("ev:voice:v1") || ""));
  }

  // ------------------------------------- 17. backend outages never silence us
  {
    const { d, calls, spoken } = await boot({ browserSpeech: true, speechStatus: 503 });
    const host = section(d);
    host.querySelector(".voice-listen").click();
    await sleep(20);
    check("fallback: natural voice was attempted when configured", calls.speech === 1);
    check("fallback: device voice actually starts on upstream failure", spoken.utterances.length === 1, stateOf(host));
    check("fallback: reason and provider are visible", /Natural voice unavailable.*device/.test(stateOf(host)), stateOf(host));
    host.querySelector(".voice-stop").click();
    check("fallback: Stop cancels the active device voice", spoken.cancels === 1);
  }
  {
    const { d, w, calls, spoken } = await boot({ browserSpeech: true, speechHang: true });
    const realTimeout = w.setTimeout.bind(w);
    w.setTimeout = (fn, ms, ...args) => realTimeout(fn, ms === 35000 ? 1 : ms, ...args);
    section(d).querySelector(".voice-listen").click();
    await sleep(20);
    check("fallback: a timed-out natural voice request starts device speech", calls.speech === 1 && spoken.utterances.length === 1);
  }
  {
    const unavailable = { ...STATUS_READY, tts: { ...STATUS_READY.tts, available: false, languages: [] },
      conversation: { available: false, reason: "No agent." }, reason: "No API key configured." };
    const { d, calls, spoken } = await boot({ browserSpeech: true, withTutor: true, status: unavailable });
    check("fallback: reader remains visible without an API key", !d.documentElement.classList.contains("voice-off"));
    section(d).querySelector(".voice-listen").click();
    check("fallback: speech works without a paid request", spoken.utterances.length === 1 && calls.speech === 0);
    check("fallback: live tutor remains honestly disabled", d.querySelector("#voice-start").disabled);
    check("fallback: settings call the speech device a device voice", /Device voice/.test(d.querySelector("#voice-voice").textContent));
  }
  {
    const { d, calls, spoken } = await boot({ browserSpeech: true, statusError: true });
    section(d).querySelector(".voice-listen").click();
    check("fallback: unreachable status does not delay device speech", spoken.utterances.length === 1);
    check("fallback: unreachable status never attempts paid synthesis", calls.speech === 0);
  }

  // ----------------------- 18. dynamically arrived assistant replies
  {
    const { d, w, spoken, calls } = await boot({ body: '<div id="assistant"></div>', apiBase: "", browserSpeech: true });
    const reply = d.createElement("div");
    reply.textContent = "Here is the result of your calculation.";
    d.querySelector("#assistant").appendChild(reply);
    w.EV.voice.enhance(reply, "Assistant reply");
    check("dynamic reply: a Listen control appears without earlier notes", Boolean(reply.querySelector(".voice-listen")));
    check("dynamic reply: the device voice picker is ready", Boolean(reply.querySelector("[data-voice-voice] option")));
    reply.querySelector(".voice-listen").click();
    check("dynamic reply: speech starts without a backend or a reload", spoken.utterances.length === 1 && calls.fetch.length === 0);
  }

  // ----------------------- 19. replacing an answer must not eat its controls
  {
    const { d, w, spoken, errors } = await boot({ browserSpeech: true, apiBase: "", withTutor: true });
    const answer = d.querySelector("#tutor-answer");
    check("dynamic: empty answer hides its Listen control", answer.querySelector(".voice-listen").disabled &&
      answer.querySelector(".voice-controls").classList.contains("is-empty"));
    answer.innerHTML = "<p>First answer with a resistor.</p>";
    w.EV.voice.enhance(answer, "Tutor answer");
    check("dynamic: Listen reattaches after innerHTML replacement", Boolean(answer.querySelector(".voice-listen")));
    await sleep(5);
    answer.querySelector(".voice-listen").click();
    check("dynamic: first answer is read", /First answer/.test(spoken.current?.text || ""));
    answer.innerHTML = "<p>Second answer with a capacitor.</p>";
    w.EV.voice.enhance(answer, "Tutor answer");
    await sleep(5);
    answer.querySelector(".voice-listen").click();
    check("dynamic: new answer is read rather than the old one", /Second answer/.test(spoken.current?.text || "") &&
      !/First answer/.test(spoken.current?.text || ""));
    check("dynamic: no self-triggering observer errors", errors.length === 0, errors.join("; "));
  }

  // ------------------------- 20. one explicit mic click -> grounded answer
  {
    const { d, w, calls, spoken, recognizers } = await boot({ browserSpeech: true, recognition: true, apiBase: "", withTutor: true });
    const button = d.querySelector("#voice-ask");
    const input = d.querySelector("#tutor-question");
    const answer = d.querySelector("#tutor-answer");
    d.querySelector("#tutor-voice-form").addEventListener("submit", (event) => {
      event.preventDefault();
      answer.innerHTML = "<p>Ohm's law states that voltage equals current times resistance.</p>";
      w.EV.voice.enhance(answer, "Tutor answer");
      w.EV.voice.tutorAnswered(answer);
    });
    check("dictation: Ask by voice is available when recognition exists", button.hidden === false);
    check("dictation: microphone not opened on load", calls.recognition === 0 && calls.getUserMedia === 0);
    button.click();
    check("dictation: permission only requested by a click", calls.recognition === 1 && calls.getUserMedia === 0);
    check("dictation: browser knows which language to recognize", recognizers[0].lang === "en-US");
    recognizers[0].result("What is Ohm's law?");
    check("dictation: recognized question is submitted", input.value === "What is Ohm's law?");
    check("dictation: sourced answer is spoken automatically", /voltage equals current/.test(spoken.current?.text || ""));
    check("dictation: status explains how to stop", /Pause or Stop/.test(d.querySelector("#voice-ask-status").textContent));
    recognizers[0].stop();
    button.click();
    recognizers[1].error("not-allowed");
    check("dictation: denied permission has a useful message", /Microphone access was denied/.test(d.querySelector("#voice-ask-status").textContent));
  }

  // ---------------------------------------------------- 21. session retry works
  {
    const session = { status: 503, code: "agent_not_configured", body: { code: "agent_not_configured", error: "No agent" } };
    const { d, calls, FakeSocket } = await boot({ withTutor: true, session });
    const start = d.querySelector("#voice-start");
    start.click();
    await sleep(20);
    session.status = 200;
    session.signedUrl = "wss://api.elevenlabs.io/v1/convai/conversation?token=x";
    start.click();
    await sleep(20);
    check("tutor retry: session is requested again after an earlier failure", calls.session === 2);
    check("tutor retry: microphone opens on the second try", calls.getUserMedia === 1);
    check("tutor retry: socket opens after recovering", FakeSocket.instances.length === 1);
  }

  // ---------------------- 22. exercise the *exported* Pages markup too
  // The small fixtures above test state machines. This catches an exporter or
  // template change that silently drops the config, scripts or speakable blocks.
  const site = path.resolve(process.argv[2] || path.join(__dirname, "..", "site"));
  if (fs.existsSync(path.join(site, "tutor", "index.html"))) {
    check("export: shipped voice JS matches the checked source",
      fs.readFileSync(path.join(site, "static", "js", "voice.js"), "utf8") === RUNTIME);
    const exported = fs.readFileSync(path.join(site, "tutor", "index.html"), "utf8");
    const page = new JSDOM(exported).window.document;
    const bootConfig = JSON.parse(page.getElementById("ev-voice-config").textContent);
    check("export: static copy identifies itself", bootConfig.staticCopy === true);
    const live = await boot({ body: page.getElementById("main").innerHTML, staticCopy: true,
      apiBase: bootConfig.apiBase, browserSpeech: true });
    check("export: the real tutor has the browser voice reader", Boolean(live.d.querySelector("#tutor-answer .voice-listen")));
    check("export: the real tutor has the voice question control", Boolean(live.d.getElementById("voice-ask")));
    check("export: without a backend, the real page makes no voice request", bootConfig.apiBase ? true : live.calls.fetch.length === 0);
    // Run both shipped scripts against the real tutor markup: a recognized
    // question must reach the static corpus and become *spoken*, not merely
    // change a stubbed DOM in an isolated reader test.
    if (!bootConfig.apiBase) {
      const rendered = new JSDOM(exported, { url: "https://example.github.io/Engine_Verse/tutor/",
        runScripts: "outside-only", pretendToBeVisual: true });
      const v = rendered.window;
      let microphone = null;
      const said = [];
      const corpus = [{ title: "Arrays", subject: "Data structures", url: "/Engine_Verse/topics/arrays/",
        simple: "An array stores values contiguously in memory.", definition: "Indexing is constant time." }];
      v.Audio = FakeAudio;
      v.speechSynthesis = { getVoices: () => [], speak: (u) => { said.push(u.text); u.onstart?.(); },
        cancel() {}, pause() {}, resume() {}, addEventListener() {} };
      v.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
      v.SpeechRecognition = class {
        constructor() { microphone = this; }
        start() { this.onstart?.(); }
        stop() { this.onend?.(); }
        result(text) { this.onresult?.({ results: [[{ transcript: text }]] }); }
      };
      v.fetch = async (url) => {
        if (String(url).endsWith("tutor-corpus.json")) return { ok: true, json: async () => corpus };
        throw new Error(`No backend on Pages: ${url}`);
      };
      v.eval(RUNTIME);
      v.eval(fs.readFileSync(path.join(site, "static", "js", "pages-live.js"), "utf8"));
      await sleep(25);
      v.document.getElementById("voice-ask").click();
      microphone?.result("Arrays");
      await sleep(35);
      check("export: dictated question is submitted to the real Pages tutor",
        v.document.getElementById("tutor-question").value === "Arrays" &&
        Boolean(v.document.querySelector("#tutor-browser-results .panel")));
      check("export: Pages tutor's real answer actually reaches speech synthesis",
        said.some((text) => /Indexing is constant time/.test(text)), said.join(" | ").slice(0, 180));
      rendered.window.close();
    }
    const topicFile = path.join(site, "topics", "arrays", "index.html");
    if (fs.existsSync(topicFile)) {
      const topic = new JSDOM(fs.readFileSync(topicFile, "utf8")).window.document;
      const checked = await boot({ body: topic.getElementById("main").innerHTML,
        apiBase: bootConfig.apiBase, browserSpeech: true });
      check("export: real note sections and whole-page control exist",
        checked.d.querySelectorAll("[data-speak] .voice-listen").length > 1 &&
        Boolean(checked.d.querySelector(".voice-page-reader .voice-listen")));
      checked.d.querySelector(".voice-page-reader .voice-listen").click();
      check("export: real note text reaches speech synthesis", checked.spoken.utterances.length === 1 &&
        /Arrays/i.test(checked.spoken.current?.text || ""));
    }
  }

  if (failures.length) {
    console.error(`voice checks: ${failures.length} failed, ${passes} passed`);
    for (const failure of failures) console.error(`  FAIL ${failure}`);
    process.exit(1);
  }
  console.log(`voice checks: all ${passes} passed`);
  process.exit(0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
