# ElevenLabs voice reader and voice tutor

EngineVerse can read educational content aloud without an account using the
browser's installed speech voices. **Listen**, **Listen to all sections**, and
**Choose voice** work even on the static GitHub Pages copy with no backend.
The notes tutor can also take a spoken question in browsers with
`SpeechRecognition` and read the answer it actually found in the notes. This
is not an open-ended AI conversation: questions outside the notes are reported
as unmatched. Browser voice quality, languages and speech-recognition support
vary by device. Recognition may send audio to the browser vendor's service;
use typed questions if you prefer not to do that.

The *optional* ElevenLabs features are separate and require a hosted backend:

| Capability | Where it appears | What it needs |
| --- | --- | --- |
| **Natural voice reader** | Notes, complete lessons, formulas, roadmaps, tutor/assistant answers and checked explanations | `ENGINEVERSE_ELEVENLABS_ENABLED=1`, `ELEVENLABS_API_KEY`, and an English or Hindi voice ID |
| **Live voice tutor** (Conversational AI) | *Start conversation* on `/tutor` | The key above plus `ELEVENLABS_AGENT_ID` and a configured agent |

When these are not configured or are unreachable, the free device reader keeps
working (if supported); no ElevenLabs call is made. Neither browser text-to-
speech nor ElevenLabs can invent an explanation of a topic absent from the
notes; only a separately configured AI agent can answer more freely, and its
answers are not grounded in the live notes database.

---

## 1. Which parts work on GitHub Pages

`https://sauravprivatelimited369-byte.github.io/Engine_Verse/` is a **static**
site. It cannot store an API key and cannot run Python. Without a backend,
**Listen** still speaks with a voice available in the browser, and the notes
tutor can take a dictated question where supported. No `/api/voice` request is
sent when the public backend origin is empty.

For the optional **ElevenLabs** voices and live agent on Pages:

* Set the repository **variable** `ENGINEVERSE_VOICE_API_URL` to the public
  HTTPS origin of the deployed EngineVerse app (for example
  `https://engineverse.example.com`, no trailing path).
* The Pages workflow passes it to `scripts/export_pages.py` as a public,
  non-secret runtime setting. If empty, natural voices and Start conversation
  are unavailable, but the device reader is still offered where supported.
* Internal links and assets keep the `/EngineVerse/` base path; the voice API
  URL is an absolute origin, so it is unaffected by the base path.

Adding `ENGINEVERSE_VOICE_API_URL` is not enough on its own: the backend must
also allow the Pages origin (`https://sauravprivatelimited369-byte.github.io`)
in its CORS allow-list. That origin is included by default; see §7.

---

## 2. Why the API key stays in the backend

* Anyone can view the source of a public web page. A key in JavaScript is a
  key published to the world, and ElevenLabs bills per character.
* The key is read only by `backend/engineverse/voice.py` from the environment.
  It is sent only in an `xi-api-key` request header to `api.elevenlabs.io`.
  It is never logged, never returned by the API, and never rendered into a
  template or the exported `site/` directory.
* The browser talks to EngineVerse; EngineVerse talks to ElevenLabs.
* For the spoken tutor, the backend asks ElevenLabs for a **short-lived signed
  WebSocket URL**. Only that URL reaches the browser; the key does not.

If a key is ever committed by accident, revoke it in the ElevenLabs dashboard
immediately (the old key is compromised the moment it is pushed), create a new
one, and remove it from Git history. The repository's
`docs/INCIDENT_RESPONSE.md` describes the same process for credentials.

---

## 3. Create an ElevenLabs account and API key

1. Sign in at <https://elevenlabs.io/>.
2. Open **Profile → API keys** and create a key.
   Give it the narrowest scope that works: text-to-speech and Conversational
   AI (signed URLs) only, with a usage limit if your plan offers one.
3. Copy the key **once**. It is not shown again. Put it in your local `.env`
   or your server's secret manager — never in this repository.

---

## 4. Configure voices and the model

In the ElevenLabs dashboard, open **Voices**, pick the voices you want students
to hear, and copy their **Voice ID** (not the name). Use one English and one
Hindi voice, or only one of them; the site shows only the voices you configure.

Pick a model that supports both languages. The default is
`eleven_multilingual_v2`; you can change it with `ELEVENLABS_TTS_MODEL_ID`.
A voice that cannot speak Hindi will produce poor Hindi even if it is listed
under the Hindi variable — the language setting selects the vocabulary of the
request, not a language-switching voice.

Optional friendly names appear in the picker:

```
ELEVENLABS_TTS_VOICE_ID_EN=your_english_voice_id
ELEVENLABS_TTS_VOICE_NAME_EN=Anika (English)
ELEVENLABS_TTS_VOICE_ID_HI=your_hindi_voice_id
ELEVENLABS_TTS_VOICE_NAME_HI=Arjun (Hindi)
ELEVENLABS_TTS_MODEL_ID=eleven_multilingual_v2
```

To offer more than one voice per language, comma-separate the IDs and the
names in the same order.

---

## 5. Create the Conversational AI agent (voice tutor)

1. In ElevenLabs, open **Agents → Create agent**.
2. Choose a voice, then paste the instruction below into the agent's system
   prompt. It is written for an engineering study assistant and is deliberately
   honest about not knowing things.
3. Set the agent's **first message** to something short, for example:
   *"Hi, I'm the EngineVerse study tutor. What topic should we work on?"*
4. Save the agent and copy its **Agent ID** into `ELEVENLABS_AGENT_ID`.
5. Enable **signed URL authentication** for this agent (the documented secure
   way for a browser to connect without exposing the API key). EngineVerse asks
   `GET /v1/convai/conversation/get-signed-url` on the server and hands only the
   returned `wss://` URL to the browser.

### Agent instruction (paste into the agent)

```
You are the EngineVerse engineering study tutor, a patient voice tutor for
undergraduate engineering students.

HOW YOU TEACH
- Explain in simple, student-friendly language and adjust to the level the
  student states. If their level is unclear, ask once.
- Cover mathematics, physics, programming and engineering fundamentals.
- Explain step by step and show your reasoning; do not just give the final
  answer. When you give an answer, say what assumption it relies on.
- Use a short example or analogy when it helps, and offer a small practice
  question when the student seems ready. Keep follow-up questions purposeful.
- For code, explain the underlying cause of a bug and how to check it, rather
  than only rewriting the code.
- Offer a concise revision summary when asked.

HOW YOU SPEAK
- Answers are spoken aloud: keep them short and well structured, usually under
  150 words unless the student asks for detail.
- Say equations as words ("V equals I times R"), not symbol soup.
- Support English and Hindi. Reply in the language the student uses.

HONESTY
- Distinguish established facts from uncertainty. Say when you do not know, and
  suggest how the student could find out.
- Never invent page references, sources, citations, syllabus coverage or
  "the notes say" claims. You cannot read EngineVerse's database, the student's
  progress, or their course material unless it was given to you in this
  conversation.
- Do not claim an answer has been checked against EngineVerse notes.
- Do not help with anything unsafe or unethical; redirect to the learning goal.
```

### Knowledge grounding — what the voice agent can and cannot see

The written Study Tutor (`backend/engineverse/tutor.py`) answers **only** from
EngineVerse's own database and always lists its sources. The Conversational AI
agent does not have access to that database, and EngineVerse does not send it
the catalogue: the voice session is opened directly between the browser and
ElevenLabs. Do not tell students the voice agent knows every topic.

A practical, honest way to ground it:

1. `scripts/export_pages.py` already writes `site/tutor-corpus.json` from the
   published beginner/standard note sections.
2. Upload that file as a **knowledge base document** for the agent in the
   ElevenLabs dashboard, and add to the instruction: *"Answer from the attached
   EngineVerse note excerpts when the question matches them, and say when no
   excerpt covers the question."*
3. Re-upload it when the notes change (it is rebuilt on every Pages deploy).
4. Keep the written tutor as the citation-carrying surface: it is the one that
   can quote the live database and show sources.

This is a snapshot, not a live query. That limitation is intentional and is
stated in the tutor panel on the page.

---

## 6. Local setup

```bash
# 1. Install the Python dependencies and seed a throwaway database
python -m pip install -r requirements.txt
cp .env.example .env          # then edit .env, never commit it
python scripts/seed.py --fresh

# 2. Put these in .env (values are yours; placeholders below are not real keys)
#    ENGINEVERSE_ELEVENLABS_ENABLED=1
#    ELEVENLABS_API_KEY=<your key>
#    ELEVENLABS_TTS_VOICE_ID_EN=<voice id>
#    ELEVENLABS_TTS_VOICE_ID_HI=<voice id>
#    ELEVENLABS_TTS_MODEL_ID=eleven_multilingual_v2
#    ELEVENLABS_AGENT_ID=<agent id>          # only for the spoken tutor

# 3. Run the app
python -m uvicorn backend.main:app --reload --port 8000
#    or: uvicorn main:app --app-dir backend --reload --port 8000
```

Open <http://localhost:8000/topics/arrays> (any note page) and use a Listen
button; open <http://localhost:8000/tutor> and press **Start conversation**.
Without those variables, **Listen** instead uses the browser's device voice;
**Ask by voice** works where browser recognition is available. Only the live
conversation button needs an agent.

Useful checks before spending credits:

```bash
curl -s http://localhost:8000/api/voice/status | python -m json.tool
```

That endpoint reports languages, voice labels, the character limit and whether
the tutor agent is configured. It never returns the key, the agent ID or a
signed URL. If `available` is false, the `reason` field names what is missing.

A quick mocked end-to-end check (no account needed):

```bash
python -m pytest backend/tests/test_voice.py -q
node scripts/check_voice.js          # needs: npm install --prefix .toolchain/jsdom jsdom@26
```

---

## 7. Hosting the backend and connecting the website

The repository's existing deployment is a Docker Compose stack
(`deploy/docker-compose.yml`, see `GLOBAL_DEPLOYMENT.md`). The same image serves
the pages and `/api/voice/*`; nothing new needs to be hosted.

1. Add the voice variables to `deploy/.env` (git-ignored):

   ```
   ENGINEVERSE_ELEVENLABS_ENABLED=1
   ELEVENLABS_API_KEY=<your key>
   ELEVENLABS_TTS_VOICE_ID_EN=<voice id>
   ELEVENLABS_TTS_VOICE_ID_HI=<voice id>
   ELEVENLABS_TTS_MODEL_ID=eleven_multilingual_v2
   ELEVENLABS_AGENT_ID=<agent id>
   ENGINEVERSE_VOICE_ORIGINS=https://sauravprivatelimited369-byte.github.io
   ENGINEVERSE_VOICE_MAX_CHARS=1200
   ENGINEVERSE_VOICE_TIMEOUT_SECONDS=30
   ```

2. Bring the stack up (or restart the `web` service):

   ```bash
   docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d
   ```

3. The app must be reachable over HTTPS. GitHub Pages is HTTPS, so a browser
   will refuse to mix in an HTTP API, and microphone access (voice tutor)
   requires a secure context anyway.

4. In GitHub: **Settings → Secrets and variables → Actions → Variables**, add
   `ENGINEVERSE_VOICE_API_URL=https://your-engineverse-host`. The Pages workflow
   bakes that origin into the static copy.

5. Re-run the **GitHub Pages** workflow (or push). The workflow now gates the
   release in both directions (`scripts/verify_voice_api.py`):

   | `ENGINEVERSE_VOICE_API_URL` | What the build requires | What ships |
   | --- | --- | --- |
   | set | a bare HTTPS origin that answers `GET /api/voice/status` with a status payload and allows the Pages origin on a real `OPTIONS` preflight for `POST /api/voice/speech`; the exported `apiBase` must equal it | ElevenLabs when configured, otherwise device voice |
   | unset | no backend is contacted; `apiBase` must be empty | device voice in supporting browsers, no live agent |

   A configured but unreachable backend fails the build instead of publishing a
   dead control, and neither mode may publish a key, agent id or signed URL.

   Verify the backend by hand as well:

   ```bash
   python scripts/verify_voice_api.py --url https://your-engineverse-host
   curl -s https://your-engineverse-host/api/voice/status | python -m json.tool
   ```

   Then open the live Pages site, a topic page, and press Listen. A green Pages
   run proves the *configuration*; it does not prove ElevenLabs answered for
   your account. That needs the live test in section 9.

If you do not host the backend, the Pages copy still speaks with installed
device voices. It shows the natural voice and live agent as unconnected, not as
working ElevenLabs features. **Do not publish an API key in the static site** —
it cannot be done safely.

---

## 8. CORS, limits and cost control

**CORS.** `/api/voice/*` is a public, cookie-free API because the Pages copy has
no accounts. Cross-origin requests are allowed only from:

* `ENGINEVERSE_SITE_URL`'s origin (the app itself),
* every origin in `ENGINEVERSE_VOICE_ORIGINS` (comma-separated, exact scheme +
  host + port),
* the project's own GitHub Pages origin (`https://<owner>.github.io`).

Nothing else is allowed; `*` is never used. There is no `Access-Control-Allow-
Credentials`, because these endpoints never read a cookie.

**Request validation.** JSON only (a cross-site HTML form cannot send
`application/json` without a preflight), `language` must be `en` or `hi`, the
voice must be one of the server-configured IDs, and the text must be between 1
and `ENGINEVERSE_VOICE_MAX_CHARS` characters (default 1200, hard ceiling 3000).
The browser splits long articles at sentence boundaries and sends the chunks
one at a time.

**Rate limiting.** Per IP, by `RateLimitMiddleware`:

* `/api/voice/speech`: 20 requests / 10 minutes
* `/api/voice/session`: 6 requests / 10 minutes

The client also stops after 24,000 characters of *ElevenLabs* speech per tab;
the device reader can continue from the remaining text without a paid request.

These are **in-process counters** (plus the shared database counter used by the
rest of the app). Behind a reverse proxy, set `ENGINEVERSE_TRUST_PROXY=1` only
when the proxy is the sole way in and overwrites `X-Forwarded-For`; otherwise
every visitor shares the proxy's address. The voice limiter uses the same
client-IP resolution as the login limiter. If you run several replicas, the
database-shared counter keeps the budget consistent.

**Upstream behaviour.** One attempt per request, no automatic retry on 5xx or
429 (a blind retry could double the bill while the account is already out of
quota). Timeouts are `ENGINEVERSE_VOICE_TIMEOUT_SECONDS` (default 30). Upstream
401/403 becomes a generic 502 "check the server's credentials"; the raw body is
never echoed. A 429 is passed through with `Retry-After`.

**Nothing is stored by EngineVerse.** No text, audio, transcript or signed URL
is written to its database or filesystem. Audio blobs are revoked by the
browser on Stop, completion or navigation. With a device voice, synthesis runs
through the browser/OS; some voices use the device's speech service. Browser
speech recognition may use a remote service chosen by the browser vendor; the
student opts in by pressing **Ask by voice**, or can type instead.

**Android.** The app's WebView does not request `RECORD_AUDIO`, so neither
Ask by voice nor a live conversation is available there. Device reading works
only if that WebView exposes `speechSynthesis`; with a configured ElevenLabs
backend, MP3 playback is another option. No microphone permission was added to
the manifest. Opening EngineVerse in Chrome on Android enables the browser
voice features supported by that device.

---

## 9. Testing with real credentials

```bash
# Backend status (does not spend credits)
curl -s https://your-host/api/voice/status | python -m json.tool

# One short synthesis (spends a few characters)
curl -s -X POST https://your-host/api/voice/speech \
  -H 'content-type: application/json' \
  -d '{"text":"V = IR","language":"en"}' -o /tmp/ev.mp3 -D -
file /tmp/ev.mp3        # expect: MPEG ADTS / audio

# A signed conversation URL (spends nothing until you connect)
curl -s -X POST https://your-host/api/voice/session \
  -H 'content-type: application/json' -d '{"language":"en"}'
```

Then in the browser: press Listen on a note section, use Pause, Resume, Stop,
Replay and the speed picker; on `/tutor`, press **Start conversation**, allow
the microphone, speak, use Mute and End. Check the DevTools console for errors
and the Network panel for the exact requests.

Automated tests use `httpx.MockTransport`; they prove request shape and error
mapping, **not** that your account, voice or agent works.

---

## 10. Manual dashboard steps (not automatable here)

- Create the API key and store it in the hosting secret manager.
- Create/choose the voices and copy their IDs.
- Create the Conversational AI agent, paste the instruction, set the first
  message, enable signed URL authentication, copy the Agent ID.
- Optionally attach `tutor-corpus.json` as the agent's knowledge document.
- Set the GitHub repository variable `ENGINEVERSE_VOICE_API_URL` and re-run the
  Pages workflow.
- Review the ElevenLabs usage limit and billing for the account.

---

## 11. Known limitations

* **Model and language quality.** Hindi quality depends on the chosen voice and
  model. The language picker chooses which configured voice is used; it cannot
  teach an English-only voice to speak Hindi.
* **Maths is read approximately.** For ElevenLabs, the backend expands
  `V = IR` to "voltage equals current multiplied by resistance", along with
  common units and operators. Device voices read the text as displayed and
  may pronounce symbols differently. Neither is a formal maths-to-speech
  engine. Code blocks are skipped, not read.
* **The voice tutor is not grounded in the live database.** See §5. It cannot
  see progress, notes, or the student's course unless you attach the corpus.
* **No transcript retention.** Transcripts exist only in the page while the
  conversation runs.
* **Browsers.** The device reader needs `speechSynthesis` and an installed
  voice; its voices, supported languages and quality depend on the OS/browser.
  Ask by voice needs `SpeechRecognition` (typically Chrome/Edge), and may use
  the browser vendor's network service. If it is absent, type the question and
  tap Listen on the answer. ElevenLabs playback needs `fetch` and `Audio`;
  the live agent needs `getUserMedia`, `AudioContext` and WebSockets over HTTPS.
  Browsers without either speech engine still get the written page.
* **Android app.** Spoken conversations are unavailable in the current WebView
  (no microphone permission is requested); the reader works if the page is
  served over HTTPS.
* **Cost.** Speech is billed by ElevenLabs per character. The limits above cap
  one deployment's exposure but are not a billing guarantee; set a usage limit
  in the ElevenLabs dashboard as well.
* **Rate limits are per process (plus the shared counter).** They are not a
  substitute for an upstream spend cap.

---

## 12. Disable ElevenLabs safely

Set `ENGINEVERSE_ELEVENLABS_ENABLED=0` (or remove it) and restart the web
process. Then:

* `/api/voice/status` reports `enabled: false`. The live conversation Start
  button is disabled, but Listen uses a device voice in supported browsers.
* Clear `ENGINEVERSE_VOICE_API_URL` on the Pages export too. With no backend
  origin, the browser sends no voice requests; Listen still uses its device.
* Notes, formulas, practice, coding, and the written tutor still work. No
  ElevenLabs request is made.

Removing the API key alone is also safe: the status endpoint then reports that
the server has no key, and the UI explains it without breaking any page.
