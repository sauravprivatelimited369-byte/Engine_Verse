#!/usr/bin/env node
/* Behaviour checks for the voice reader and spoken tutor (static/js/voice.js).
 *
 *   npm install --prefix .toolchain/jsdom jsdom@26
 *   node scripts/check_voice.js
 *
 * No network, no credentials: the backend and the ElevenLabs WebSocket are
 * stubbed, so this proves what the browser code does with a response, not that
 * a real ElevenLabs account is reachable. It covers the parts a screenshot
 * cannot: which text is submitted, chunking without losing words, one active
 * player, cleanup of blob URLs, error messaging, and that the microphone is
 * untouched until the student presses Start.
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
  <section data-voice-tutor id="voice-tutor">
    <span id="voice-tutor-chip">Checking</span>
    <button id="voice-start" type="button">Start conversation</button>
    <button id="voice-mute" type="button" hidden>Mute microphone</button>
    <button id="voice-end" type="button" hidden>End conversation</button>
    <p id="voice-status" role="status" aria-live="polite"></p>
    <p id="voice-setup" hidden></p>
    <div id="voice-transcript" hidden></div>
    <details id="voice-settings"><summary>Voice settings</summary>
      <select id="voice-language"></select>
      <select id="voice-voice"></select>
      <select id="voice-speed"><option value="1">1x</option></select>
      <p id="voice-prefs-status"></p>
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
  withTutor = false,
} = {}) {
  const html = `<!doctype html><html><head><meta charset="utf-8">
    <script type="application/json" id="ev-voice-config">${JSON.stringify({ apiBase, staticCopy })}</script>
    </head><body>${body}${withTutor ? TUTOR_HTML : ""}</body></html>`;
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

  const calls = { fetch: [], revoked: [], created: 0, status: 0, speech: 0, session: 0, getUserMedia: 0 };
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
      return response(status);
    }
    if (url.endsWith("/api/voice/speech")) {
      calls.speech += 1;
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

  w.eval(RUNTIME);
  await sleep(20);
  return { w, d: w.document, calls, errors, tracks, FakeSocket, blobUrls, FakeAudio };
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
      Boolean(notice) && /not connected/i.test(notice.textContent) && notice.textContent.length > 40,
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
