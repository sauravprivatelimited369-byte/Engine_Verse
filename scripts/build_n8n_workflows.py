#!/usr/bin/env python3
"""Generate the importable n8n workflows in ``n8n/workflows/``.

Why generate rather than hand-write six JSON files
--------------------------------------------------
Every workflow shares the same shape: a trigger, a guard Code node, an optional
model call, an optional datastore write and a reply. Hand-written JSON drifts -
one file ends up with a different credential placeholder, another forgets the
CORS origin, and a third has a connection pointing at a renamed node. Building
them from one table means those things are decided once, and
``scripts/check_n8n_workflows.py`` can then validate the output.

Nothing here contains a credential, a token, an API key or a webhook secret.
Credential slots carry a placeholder id/name that n8n shows as "not configured"
until the operator selects their own credential - which is the honest state.

Run:  python scripts/build_n8n_workflows.py
Check: python scripts/check_n8n_workflows.py
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "n8n" / "workflows"

NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

#: The production origins allowed to call the Chat Trigger from a browser.
#: The first is the GitHub Pages project site; the second is a local preview.
#: A self-hosted EngineVerse origin must be added by the operator here AND in
#: ENGINEVERSE_ASSISTANT_PUBLIC_URL's workflow settings, or the browser will be
#: refused by CORS - which is the correct failure mode.
ALLOWED_ORIGINS = (
    "https://sauravprivatelimited369-byte.github.io",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)

SYSTEM_PROMPT = """\
You are the EngineVerse study assistant: an AI assistant for engineering
students, mostly in India and also internationally. EngineVerse is a free study
platform with notes for 93 subjects, coding practice, a study planner, projects
and placement preparation.

How to answer
- Be direct and warm. Prefer short paragraphs, then a bullet list or a small
  worked example.
- Teach, do not just answer: name the idea, show one concrete example, and say
  what a student should try next.
- Use fenced code blocks for code, with the language tag.
- If the student writes in Hindi or Hinglish, answer in the same language.
  Otherwise answer in the language they used.
- Keep the usual answer under 250 words unless the student asks for depth.

Honesty rules (do not break these)
- You cannot run code, browse the web, open files or see the student's account.
  Say so if asked, and suggest an EngineVerse page that can help instead.
- If you are unsure or the question needs very recent or local information,
  say that plainly. Never invent a citation, a statistic, a deadline or a URL.
- Do not claim to be a person. You are an AI assistant.
- Never ask for passwords, API keys, Aadhaar/ID numbers, phone numbers or
  anything about another person. If a student pastes a secret, tell them to
  rotate it and do not repeat it back.

Scope
- Programming (Python, Java, C, C++, JavaScript, DSA), web development, AI/ML
  basics, study plans, revision schedules, interview and hackathon preparation,
  project ideas and portfolios.
- For medical, legal or financial decisions, give general study guidance and
  point to a qualified professional.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def nid(name: str, workflow: str) -> str:
    """A stable node id, so regenerating produces a reviewable diff."""
    return str(uuid.uuid5(NS, f"engineverse-n8n:{workflow}:{name}"))


def node(name: str, workflow: str, kind: str, version: float | int, position: tuple[int, int],
         parameters: dict | None = None, *, notes: str = "", disabled: bool = False,
         credentials: dict | None = None, extra: dict | None = None) -> dict:
    data = {
        "parameters": parameters or {},
        "id": nid(name, workflow),
        "name": name,
        "type": kind,
        "typeVersion": version,
        "position": list(position),
    }
    if notes:
        data["notes"] = notes
        data["notesInFlow"] = True
    if disabled:
        data["disabled"] = True
    if credentials:
        data["credentials"] = credentials
    if extra:
        data.update(extra)
    return data


def code(name: str, workflow: str, position: tuple[int, int], js: str, *, notes: str = "",
         disabled: bool = False) -> dict:
    return node(name, workflow, "n8n-nodes-base.code", 2, position,
                {"mode": "runOnceForAllItems", "jsCode": js.strip() + "\n"},
                notes=notes, disabled=disabled)


def http(name: str, workflow: str, position: tuple[int, int], url: str, *, method: str = "POST",
         body: str | None = None, notes: str = "", disabled: bool = False,
         header_auth: bool = False, timeout_ms: int = 30000) -> dict:
    parameters: dict = {
        "method": method,
        "url": url,
        "options": {"timeout": timeout_ms},
    }
    if header_auth:
        parameters["authentication"] = "genericCredentialType"
        parameters["genericAuthType"] = "httpHeaderAuth"
    if body is not None:
        parameters["sendBody"] = True
        parameters["specifyBody"] = "json"
        parameters["jsonBody"] = body
    return node(name, workflow, "n8n-nodes-base.httpRequest", 4.2, position, parameters,
                notes=notes, disabled=disabled)


def webhook(name: str, workflow: str, position: tuple[int, int], path: str, *, notes: str = "",
            response_mode: str = "responseNode") -> dict:
    return node(
        name, workflow, "n8n-nodes-base.webhook", 2, position,
        {
            "httpMethod": "POST",
            "path": path,
            "authentication": "none",
            "responseMode": response_mode,
            "options": {"allowedOrigins": ",".join(ALLOWED_ORIGINS)},
        },
        notes=notes,
        extra={"webhookId": str(uuid.uuid5(NS, f"engineverse-n8n:webhook:{path}"))},
    )


def respond(name: str, workflow: str, position: tuple[int, int], body: str, *,
            status: int = 200, notes: str = "") -> dict:
    return node(
        name, workflow, "n8n-nodes-base.respondToWebhook", 1.1, position,
        {"respondWith": "json", "responseBody": body, "options": {"responseCode": status}},
        notes=notes,
    )


def if_node(name: str, workflow: str, position: tuple[int, int], left: str,
            *, boolean_true: bool = True, notes: str = "") -> dict:
    operator = ({"type": "boolean", "operation": "true", "singleValue": True}
                if boolean_true else {"type": "boolean", "operation": "false", "singleValue": True})
    return node(
        name, workflow, "n8n-nodes-base.if", 2.2, position,
        {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                            "version": 2},
                "conditions": [{"id": str(uuid.uuid5(NS, f"cond:{workflow}:{name}")),
                                "leftValue": left, "rightValue": "", "operator": operator}],
                "combinator": "and",
            },
            "options": {},
        },
        notes=notes,
    )


def schedule(name: str, workflow: str, position: tuple[int, int], *, hours: int = 24,
             minute: int = 0, notes: str = "") -> dict:
    return node(
        name, workflow, "n8n-nodes-base.scheduleTrigger", 1.2, position,
        {"rule": {"interval": [{"field": "hours", "hoursInterval": hours}]}},
        notes=notes,
    )


def postgres(name: str, workflow: str, position: tuple[int, int], query: str, *,
             replacements: str = "", notes: str = "", disabled: bool = True) -> dict:
    parameters: dict = {
        "operation": "executeQuery",
        "query": query.strip(),
        "options": {},
    }
    if replacements:
        parameters["options"]["queryReplacement"] = replacements
    return node(
        name, workflow, "n8n-nodes-base.postgres", 2.5, position, parameters,
        notes=notes, disabled=disabled,
        credentials={"postgres": {"id": "REPLACE_WITH_POSTGRES_CREDENTIAL", "name": "EngineVerse Postgres"}},
    )


def email(name: str, workflow: str, position: tuple[int, int], *, subject: str, body: str,
          notes: str = "") -> dict:
    return node(
        name, workflow, "n8n-nodes-base.emailSend", 2.1, position,
        {
            "fromEmail": "assistant@example.org",
            "toEmail": "admin@example.org",
            "subject": subject,
            "emailFormat": "text",
            "text": body,
            "options": {},
        },
        notes=notes, disabled=True,
        credentials={"smtp": {"id": "REPLACE_WITH_SMTP_CREDENTIAL", "name": "EngineVerse SMTP"}},
    )


def telegram(name: str, workflow: str, position: tuple[int, int], text: str, *, notes: str = "") -> dict:
    return node(
        name, workflow, "n8n-nodes-base.telegram", 1.2, position,
        {"chatId": "REPLACE_WITH_CHAT_ID", "text": text, "additionalFields": {}},
        notes=notes, disabled=True,
        credentials={"telegramApi": {"id": "REPLACE_WITH_TELEGRAM_CREDENTIAL", "name": "EngineVerse Telegram"}},
    )


def noop(name: str, workflow: str, position: tuple[int, int], notes: str = "") -> dict:
    return node(name, workflow, "n8n-nodes-base.noOp", 1, position, {}, notes=notes)


def connect(*pairs: tuple[str, str, int]) -> dict:
    """``connect(("A", "B", 0), ("A", "C", 1))`` -> n8n connections object."""
    out: dict[str, dict] = {}
    for source, target, output_index in pairs:
        out.setdefault(source, {"main": []})
        while len(out[source]["main"]) <= output_index:
            out[source]["main"].append([])
        out[source]["main"][output_index].append({"node": target, "type": "main", "index": 0})
    return out


def workflow(name: str, slug: str, nodes: list[dict], connections: dict, *, notes: str = "") -> dict:
    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {
            "executionOrder": "v1",
            # Keep a bounded, useful record of failures without storing every
            # student message. Success data is pruned aggressively on purpose:
            # EngineVerse keeps no transcript, and neither should n8n.
            "saveDataSuccessExecution": "none",
            "saveDataErrorExecution": "all",
            "saveManualExecutions": True,
            "callerPolicy": "workflowsFromSameOwner",
        },
        "staticData": None,
        "pinData": {},
        "meta": {"templateCredsSetupCompleted": False, "description": notes or name},
        "tags": [{"name": "EngineVerse"}],
    }


# ---------------------------------------------------------------------------
# Shared JavaScript
# ---------------------------------------------------------------------------

GUARD_JS = r"""
// Validate one chat message before it costs a model call.
//
// The same rules EngineVerse enforces server-side (800 characters, control
// characters stripped) plus a small per-session budget kept in the workflow's
// static data. Static data is persisted for active workflows, so this survives
// a restart; it is per-n8n-instance, which is exactly why the website also
// rate-limits per IP and per session before it ever reaches n8n.
const MAX_CHARS = 800;
const PER_HOUR = 20;
const WINDOW_MS = 60 * 60 * 1000;

const item = $json || {};
const raw = item.chatInput ?? item.body?.chatInput ?? "";
const session = String(item.sessionId ?? item.body?.sessionId ?? "unknown").slice(0, 64);

const question = String(raw)
  .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
  .replace(/\r\n?/g, "\n")
  .replace(/\n{3,}/g, "\n\n")
  .trim();

const now = Date.now();
const store = $getWorkflowStaticData("global");
store.buckets = store.buckets || {};
// Prune first: an unbounded map is a memory leak that also makes n8n's own
// database grow.
for (const [key, bucket] of Object.entries(store.buckets)) {
  if (!bucket || now - bucket.start > WINDOW_MS * 24) delete store.buckets[key];
}
const bucket = store.buckets[session] || { start: now, count: 0 };
if (now - bucket.start > WINDOW_MS) {
  bucket.start = now;
  bucket.count = 0;
}
bucket.count += 1;
store.buckets[session] = bucket;

let refusal = "";
if (question.length < 2) refusal = "Ask a question of at least a few words and I will help.";
else if (question.length > MAX_CHARS) refusal = `Keep your question under ${MAX_CHARS} characters.`;
else if (bucket.count > PER_HOUR) refusal = "That is a lot of questions in one hour. Take a short break and try again later.";

const systemPrompt = $vars.engineverse_system_prompt || %s;

return [{
  json: {
    allowed: refusal === "",
    refusal,
    question,
    questionChars: question.length,
    sessionId: session,
    messages: refusal
      ? []
      : [{ role: "system", content: systemPrompt }, { role: "user", content: question }],
  },
}];
""".strip() % json.dumps(SYSTEM_PROMPT)

SHAPE_JS = r"""
// Turn an OpenAI-compatible response into the Chat Trigger's reply shape.
// n8n's hosted chat reads `output`; the fallback keeps a plain-text body and a
// refusal honest rather than rendering JSON at the student.
const data = $json || {};
const choice = Array.isArray(data.choices) ? data.choices[0] : null;
const message = choice?.message?.content ?? data.output ?? data.text ?? "";
const text = String(message).replace(/<[^>]+>/g, "").trim();

return [{
  json: {
    output: text || "I could not produce an answer for that. Please rephrase the question.",
    questionChars: $("Guard question").item.json.questionChars,
    sessionId: $("Guard question").item.json.sessionId,
    model: data.model || "unknown",
  },
}];
""".strip()

# ---------------------------------------------------------------------------
# Workflow A - student copilot (HTTP variant, no LangChain node versions)
# ---------------------------------------------------------------------------

WF_A = "student-copilot"

workflow_a_nodes = [
    node(
        "Chat Trigger", WF_A, "@n8n/n8n-nodes-langchain.chatTrigger", 1.1, (-200, 0),
        {
            # Embedded Chat: our own interface in EngineVerse calls the Chat URL.
            # "public" makes the webhook reachable without an n8n session.
            "public": True,
            "mode": "webhook",
            "options": {
                "allowedOrigins": ",".join(ALLOWED_ORIGINS),
            },
        },
        notes="Embedded Chat. Copy the Chat URL from this node into "
              "ENGINEVERSE_ASSISTANT_URL (proxy) and/or "
              "ENGINEVERSE_ASSISTANT_PUBLIC_URL (static Pages copy).",
        extra={"webhookId": str(uuid.uuid5(NS, "engineverse-n8n:chat:student-copilot"))},
        credentials=None,
    ),
    code("Guard question", WF_A, (20, 0), GUARD_JS,
         notes="Length bounds, control characters and a per-session budget of 20 questions/hour."),
    if_node("Allowed?", WF_A, (240, 0), "={{ $json.allowed }}",
            notes="A refused message never reaches the model."),
    http(
        "Model (OpenAI-compatible)", WF_A, (460, 0),
        "https://api.openai.com/v1/chat/completions",
        body=("={{ JSON.stringify({ model: 'gpt-4o-mini', messages: $json.messages, "
              "temperature: 0.3, max_tokens: 800 }) }}"),
        notes="Point this at any OpenAI-compatible /chat/completions endpoint. "
              "The credential is an HTTP Header Auth credential holding "
              "Authorization: Bearer <your key> - never put the key in this node.",
        header_auth=True,
        timeout_ms=30000,
    ),
    code("Shape reply", WF_A, (680, 0), SHAPE_JS),
    postgres(
        "Log metadata (optional)", WF_A, (900, 0),
        """
        INSERT INTO assistant_events (occurred_at, session_ref, question_chars, answer_chars, model)
        VALUES (to_timestamp($1::double precision / 1000), $2, $3, $4, $5)
        """,
        replacements=("={{ Date.now() }},{{ $('Guard question').item.json.sessionId }},"
                      "{{ $('Guard question').item.json.questionChars }},{{ $json.output.length }},"
                      "{{ $json.model }}"),
        notes="Disabled by default. Enable only after creating the table (see "
              "n8n/README.md) and choosing a retention period. No question text is written.",
    ),
    code(
        "Reply", WF_A, (1120, 0),
        r"""
const item = $json || {};
return [{ json: { output: item.output ?? "I could not answer that." } }];
""",
        notes="The last node's `output` is what n8n returns to the chat.",
    ),
    code("Refusal", WF_A, (460, 220),
         r"""
return [{ json: { output: $json.refusal || "Ask a question of at least a few words." } }];
""",
         notes="Terminal node for a message that failed validation."),
]
workflow_a_connections = connect(
    ("Chat Trigger", "Guard question", 0),
    ("Guard question", "Allowed?", 0),
    ("Allowed?", "Model (OpenAI-compatible)", 0),
    ("Allowed?", "Refusal", 1),
    ("Model (OpenAI-compatible)", "Shape reply", 0),
    ("Shape reply", "Log metadata (optional)", 0),
    ("Log metadata (optional)", "Reply", 0),
)

# ---------------------------------------------------------------------------
# Workflow A2 - the same assistant, with LangChain memory
# ---------------------------------------------------------------------------

WF_A2 = "student-copilot-memory"

workflow_a2_nodes = [
    node(
        "Chat Trigger", WF_A2, "@n8n/n8n-nodes-langchain.chatTrigger", 1.1, (-200, 0),
        {
            "public": True,
            "mode": "webhook",
            "options": {"allowedOrigins": ",".join(ALLOWED_ORIGINS)},
        },
        notes="Embedded Chat variant. Requires the LangChain nodes bundled with n8n.",
        extra={"webhookId": str(uuid.uuid5(NS, "engineverse-n8n:chat:student-copilot-memory"))},
    ),
    node(
        "AI Agent", WF_A2, "@n8n/n8n-nodes-langchain.agent", 1.7, (20, 0),
        {
            "promptType": "define",
            "text": "={{ $json.chatInput }}",
            "options": {"systemMessage": SYSTEM_PROMPT},
        },
        notes="Answers the student. The model and memory arrive through the "
              "ai_languageModel and ai_memory connections below.",
    ),
    node(
        "OpenAI Chat Model", WF_A2, "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, (-40, 220),
        {"model": {"__rl": True, "value": "gpt-4o-mini", "mode": "list"},
         "options": {"temperature": 0.3, "maxTokens": 800}},
        notes="Choose any chat model. Select your own credential after importing.",
        credentials={"openAiApi": {"id": "REPLACE_WITH_OPENAI_CREDENTIAL", "name": "OpenAI account"}},
    ),
    node(
        "Window Memory", WF_A2, "@n8n/n8n-nodes-langchain.memoryBufferWindow", 1.3, (180, 220),
        {"sessionIdType": "customKey", "sessionKey": "={{ $('Chat Trigger').item.json.sessionId }}",
         "contextWindowLength": 10},
        notes="Keeps the last 10 turns per EngineVerse session. EngineVerse sends a "
              "stable but unguessable session id; no account data is involved.",
    ),
    code(
        "Reply", WF_A2, (260, 0),
        r"""
// The agent returns its answer in `output`. Keep the contract explicit.
const text = ($json.output ?? $json.text ?? "").toString().trim();
return [{ json: { output: text || "I could not answer that. Please rephrase the question." } }];
""",
    ),
]
workflow_a2_connections = {
    "Chat Trigger": {"main": [[{"node": "AI Agent", "type": "main", "index": 0}]]},
    "OpenAI Chat Model": {"ai_languageModel": [[{"node": "AI Agent", "type": "ai_languageModel", "index": 0}]]},
    "Window Memory": {"ai_memory": [[{"node": "AI Agent", "type": "ai_memory", "index": 0}]]},
    "AI Agent": {"main": [[{"node": "Reply", "type": "main", "index": 0}]]},
}


def build() -> dict[str, dict]:
    flows: dict[str, dict] = {}

    flows["01-student-copilot.json"] = workflow(
        "EngineVerse · Student copilot (HTTP model)", "student-copilot",
        workflow_a_nodes, workflow_a_connections,
        notes="Chat Trigger → validate/limit → OpenAI-compatible model → reply. "
              "No LangChain node versions to match; point the HTTP node at any "
              "OpenAI-compatible endpoint.",
    )
    flows["01b-student-copilot-agent.json"] = workflow(
        "EngineVerse · Student copilot (agent + memory)", "student-copilot-memory",
        workflow_a2_nodes, workflow_a2_connections,
        notes="The same assistant built on the AI Agent node, with a 10-turn "
              "window memory keyed by EngineVerse's session id.",
    )

    # ----------------------------------------------------------- B: feedback
    WF_B = "feedback"
    flows["02-feedback-intake.json"] = workflow(
        "EngineVerse · Feedback intake", "feedback",
        [
            webhook("Feedback webhook", WF_B, (-200, 0), "engineverse/feedback",
                    notes="POST { message, email?, consent, page } from an EngineVerse "
                          "form. CORS is restricted to the origins above."),
            code(
                "Validate and sanitise", WF_B, (20, 0),
                r"""
// Consent is explicit: an optional contact address is only kept when the
// student ticked the box. Everything is length-bounded before it is stored or
// classified, and no field is treated as HTML.
const body = $json.body ?? $json;
const text = String(body.message ?? "").trim();
const email = String(body.email ?? "").trim().toLowerCase();
const consent = body.consent === true || body.consent === "true" || body.consent === "on";
const page = String(body.page ?? "").slice(0, 200);

const problems = [];
if (text.length < 10) problems.push("Please describe the issue in at least 10 characters.");
if (text.length > 4000) problems.push("Please keep feedback under 4000 characters.");
if (consent && email && !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email)) {
  problems.push("That email address does not look valid.");
}

// A simple, explainable first pass. A human reviews anything ambiguous.
const lower = text.toLowerCase();
const categories = [
  ["bug", /(broken|error|crash|not working|500|404|bug|fail)/],
  ["content", /(wrong|typo|incorrect|outdated|mistake|note)/],
  ["accessibility", /(screen reader|contrast|keyboard|aria|font size)/],
  ["account", /(login|sign in|password|otp|email)/],
  ["request", /(please add|would like|suggest|feature)/],
];
const category = (categories.find(([, pattern]) => pattern.test(lower)) || ["other"])[0];

return [{
  json: {
    valid: problems.length === 0,
    problems,
    message: text.slice(0, 4000),
    contact: consent ? email.slice(0, 254) : "",
    consent,
    page,
    category,
    receivedAt: new Date().toISOString(),
    // Deduplicate accidental double-submits without storing anything extra.
    dedupeKey: `${category}:${text.slice(0, 120)}:${Math.floor(Date.now() / 600000)}`,
  },
}];
""",
                notes="Consent-gated contact details, bounded text, explainable categories.",
            ),
            if_node("Valid?", WF_B, (240, 0), "={{ $json.valid }}"),
            postgres(
                "Store feedback (optional)", WF_B, (460, 0),
                """
                INSERT INTO feedback_events
                  (occurred_at, category, message, contact, consent, page, dedupe_key)
                VALUES (now(), $1, $2, $3, $4, $5, $6)
                ON CONFLICT (dedupe_key) DO NOTHING
                """,
                replacements="={{ $json.category }},{{ $json.message }},{{ $json.contact }},"
                             "{{ $json.consent }},{{ $json.page }},{{ $json.dedupeKey }}",
                notes="Disabled until an operator creates the table and picks a retention "
                      "period. The unique dedupe_key makes a double submit harmless.",
            ),
            respond("Acknowledgement", WF_B, (680, 0),
                    "={{ JSON.stringify({ ok: true, category: $json.category, "
                    "message: 'Thank you - your feedback was received.' }) }}",
                    notes="Same-origin POSTs from EngineVerse also need CORS on this node."),
            respond("Rejected", WF_B, (460, 220),
                    "={{ JSON.stringify({ ok: false, problems: $json.problems }) }}",
                    status=400),
        ],
        connect(
            ("Feedback webhook", "Validate and sanitise", 0),
            ("Validate and sanitise", "Valid?", 0),
            ("Valid?", "Store feedback (optional)", 0),
            ("Valid?", "Rejected", 1),
            ("Store feedback (optional)", "Acknowledgement", 0),
        ),
        notes="Validate → consent → store (optional) → classify → acknowledge.",
    )

    # ------------------------------------------------------------- C: content
    WF_C = "content"
    flows["03-content-drafting.json"] = workflow(
        "EngineVerse · Learning content drafting (human review required)", "content",
        [
            node("Start (after choosing a topic)", WF_C, "n8n-nodes-base.manualTrigger", 1,
                 (-200, 0), {}, notes="Manual on purpose: content is drafted, reviewed by a "
                                       "person, and only then published by hand."),
            code(
                "Brief", WF_C, (20, 0),
                r"""
// A brief the operator edits before running. Nothing is fetched from a private
// account, scraped, or posted automatically.
const brief = $json.brief || {};
return [{
  json: {
    topic: String(brief.topic || "Pointers in C").slice(0, 160),
    audience: String(brief.audience || "first-year engineering students").slice(0, 120),
    platform: String(brief.platform || "blog").slice(0, 40),
    sourceUrl: String(brief.sourceUrl || "").slice(0, 300),
    approvedSourcesOnly: true,
  },
}];
""",
            ),
            http(
                "Draft with model (disabled until reviewed)", WF_C, (240, 0),
                "https://api.openai.com/v1/chat/completions",
                body=("={{ JSON.stringify({ model: 'gpt-4o-mini', messages: ["
                      "{ role: 'system', content: 'You write short, accurate teaching notes for "
                      "engineering students. Use only the facts you are sure of. Mark anything "
                      "uncertain. Output markdown with a title, 3 short sections and one exercise.' },"
                      "{ role: 'user', content: `Topic: ${$json.topic}. Audience: ${$json.audience}.` }"
                      "], temperature: 0.4, max_tokens: 900 }) }}"),
                notes="Disabled by default so a fresh import cannot spend money. Enable after "
                      "reviewing the prompt and the model cost.",
                disabled=True,
                header_auth=True,
            ),
            code(
                "Platform variants", WF_C, (460, 0),
                r"""
// Deterministic formatting per channel, with the lengths the platform allows.
// No hashtag stuffing, no engagement bait, no invented statistics.
const data = $json || {};
const draft = String(data.choices?.[0]?.message?.content || data.output || "").trim();
if (!draft) {
  return [{ json: { ready: false, reason: "No draft yet - enable the model node or paste a draft." } }];
}
const firstLine = draft.split("\n").find((line) => line.trim()) || "EngineVerse";
const clean = (text, max) => (text.length <= max ? text : text.slice(0, max - 1).replace(/\s+\S*$/, "") + "…");
return [{
  json: {
    ready: true,
    blog: { title: firstLine.replace(/^#+\s*/, ""), bodyMarkdown: draft },
    telegram: clean(`${firstLine}\n\n${draft}`.replace(/[#*`]/g, ""), 3800),
    instagram: clean(draft.replace(/[#*`]/g, ""), 2100),
    youtube: { title: clean(firstLine.replace(/^#+\s*/, ""), 95), description: clean(draft, 4500) },
    whatsapp: clean(`${firstLine}\n\n${draft}`.replace(/[#*`]/g, ""), 900),
    reviewChecklist: [
      "A subject teacher has read the draft end to end.",
      "Every claim is checkable, and no citation was invented.",
      "The code example was run and its output matches the text.",
      "Links point at official or primary sources.",
      "The post says EngineVerse is free and open source, without exaggeration.",
    ],
  },
}];
""",
                notes="Platform-specific lengths and a human review checklist. Nothing is published here.",
            ),
            http(
                "Open a review issue (optional)", WF_C, (680, 0),
                "https://api.github.com/repos/sauravprivatelimited369-byte/Engine_Verse/issues",
                body=("={{ JSON.stringify({ title: `Content draft: ${$('Brief').item.json.topic}`.slice(0, 120), "
                      "body: `A draft is ready for human review.\\n\\n\\`\\`\\`\\n${$json.blog.bodyMarkdown.slice(0, 4000)}\\n\\`\\`\\`\\n\\n`"
                      "+ $json.reviewChecklist.map((line) => `- [ ] ${line}`).join('\\n'), "
                      "labels: ['content', 'needs-review'] }) }}"),
                notes="Disabled by default. Uses a GitHub credential with issues:write. "
                      "Review happens on the issue; publishing stays manual.",
                disabled=True,
                header_auth=True,
            ),
            noop("Await human review", WF_C, (900, 0),
                 notes="Deliberate stop. Distribution is a person's decision, not a schedule."),
        ],
        connect(
            ("Start (after choosing a topic)", "Brief", 0),
            ("Brief", "Draft with model (disabled until reviewed)", 0),
            ("Draft with model (disabled until reviewed)", "Platform variants", 0),
            ("Platform variants", "Open a review issue (optional)", 0),
            ("Open a review issue (optional)", "Await human review", 0),
        ),
        notes="A → draft → platform variants → review issue → manual publish. Never auto-posts.",
    )

    # ---------------------------------------------------------- D: onboarding
    WF_D = "onboarding"
    flows["04-onboarding.json"] = workflow(
        "EngineVerse · Student onboarding", "onboarding",
        [
            webhook("Subscribe webhook", WF_D, (-200, 0), "engineverse/subscribe",
                    notes="Only after a student ticks an explicit consent box."),
            code(
                "Validate consent", WF_D, (20, 0),
                r"""
const body = $json.body ?? $json;
const email = String(body.email ?? "").trim().toLowerCase().slice(0, 254);
const consent = body.consent === true || body.consent === "true" || body.consent === "on";
const name = String(body.name ?? "").trim().slice(0, 80);
const valid = consent && /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email);
return [{
  json: {
    valid,
    email,
    name,
    consent,
    // A stable key: one welcome per address, ever, unless they unsubscribe and
    // subscribe again with a new consent timestamp.
    dedupeKey: email,
    consentAt: new Date().toISOString(),
    reason: valid ? "" : "An email address and a ticked consent box are required.",
  },
}];
""",
            ),
            if_node("Valid and consented?", WF_D, (240, 0), "={{ $json.valid }}"),
            postgres(
                "Record subscription (optional)", WF_D, (460, 0),
                """
                INSERT INTO newsletter_subscribers (email, name, consent, consent_at, dedupe_key)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (dedupe_key) DO UPDATE
                  SET consent = EXCLUDED.consent,
                      consent_at = EXCLUDED.consent_at,
                      name = EXCLUDED.name
                RETURNING id, (xmax = 0) AS is_new
                """,
                replacements="={{ $json.email }},{{ $json.name }},{{ $json.consent }},"
                             "{{ $json.consentAt }},{{ $json.dedupeKey }}",
                notes="Disabled until the table exists. `is_new` is what prevents a second "
                      "welcome message; the ON CONFLICT clause makes a re-submit idempotent.",
            ),
            if_node("First time only", WF_D, (680, 0), "={{ $json.is_new === true }}"),
            email(
                "Welcome email", WF_D, (900, 0),
                subject="Welcome to EngineVerse - start with one page",
                body=(
                    "Hi {{ $('Validate consent').item.json.name || 'there' }},\n\n"
                    "Thanks for joining EngineVerse. It is free and open source.\n\n"
                    "Three things worth trying first:\n"
                    "1. Your branch's study hub: /streams\n"
                    "2. Coding practice with a real judge: /practice/problems\n"
                    "3. The study planner: /planner\n\n"
                    "You can unsubscribe at any time with the link below, and we will "
                    "delete your address.\n\n"
                    "EngineVerse is a study aid, not an accredited institution.\n"
                ),
                notes="Disabled until an SMTP credential is selected. Fill in the real "
                      "unsubscribe URL before enabling.",
            ),
            respond("Thank you", WF_D, (1120, 0),
                    "={{ JSON.stringify({ ok: true, message: 'Thanks - check your inbox to confirm.' }) }}"),
            respond("Refused", WF_D, (460, 220),
                    "={{ JSON.stringify({ ok: false, error: $json.reason }) }}",
                    status=400),
        ],
        connect(
            ("Subscribe webhook", "Validate consent", 0),
            ("Validate consent", "Valid and consented?", 0),
            ("Valid and consented?", "Record subscription (optional)", 0),
            ("Valid and consented?", "Refused", 1),
            ("Record subscription (optional)", "First time only", 0),
            ("First time only", "Welcome email", 0),
        ),
        notes="Consent → idempotent record → one welcome message, never a duplicate.",
    )

    # -------------------------------------------------------- E: unsubscribe
    WF_E2 = "unsubscribe"
    flows["05-unsubscribe.json"] = workflow(
        "EngineVerse · Unsubscribe", "unsubscribe",
        [
            webhook("Unsubscribe webhook", WF_E2, (-200, 0), "engineverse/unsubscribe",
                    notes="Linked from every message. Withdrawing consent must be one click."),
            code(
                "Build request", WF_E2, (20, 0),
                r"""
const body = $json.body ?? $json;
const email = String(body.email ?? $json.query?.email ?? "").trim().toLowerCase().slice(0, 254);
const token = String(body.token ?? $json.query?.token ?? "").slice(0, 128);
return [{ json: {
  valid: /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email),
  email, token, requestedAt: new Date().toISOString(),
} }];
""",
            ),
            if_node("Valid?", WF_E2, (240, 0), "={{ $json.valid }}"),
            postgres(
                "Withdraw consent (optional)", WF_E2, (460, 0),
                """
                UPDATE newsletter_subscribers
                   SET consent = false, consent_at = now(), unsubscribed_at = now()
                 WHERE email = $1
                """,
                replacements="={{ $json.email }}",
                notes="Disabled until the table exists. Consent is withdrawn rather than "
                      "deleted so an operator can prove the request was honoured.",
            ),
            respond("Unsubscribed", WF_E2, (680, 0),
                    "={{ JSON.stringify({ ok: true, message: 'You have been unsubscribed.' }) }}"),
            respond("Invalid", WF_E2, (460, 220),
                    "={{ JSON.stringify({ ok: false, error: 'A valid email address is required.' }) }}",
                    status=400),
        ],
        connect(
            ("Unsubscribe webhook", "Build request", 0),
            ("Build request", "Valid?", 0),
            ("Valid?", "Withdraw consent (optional)", 0),
            ("Valid?", "Invalid", 1),
            ("Withdraw consent (optional)", "Unsubscribed", 0),
        ),
    )

    # ---------------------------------------------------------------- F: analytics
    WF_F = "analytics"
    flows["06-analytics-rollup.json"] = workflow(
        "EngineVerse · Growth analytics rollup", "analytics",
        [
            schedule("Daily at 03:00", WF_F, (-200, 0), hours=24,
                     notes="Runs against the EngineVerse database. Never against a "
                           "third-party analytics service."),
            postgres(
                "Assistant metrics", WF_F, (20, 0),
                """
                SELECT
                  date_trunc('day', to_timestamp(created_at / 1000.0)) AS day,
                  count(*) FILTER (WHERE action = 'assistant.asked')        AS questions_answered,
                  count(*) FILTER (WHERE action = 'assistant.failed')       AS failures,
                  count(*) FILTER (WHERE action = 'assistant.limited')      AS rate_limited,
                  round(avg((meta::jsonb ->> 'latency_ms')::numeric)
                        FILTER (WHERE action = 'assistant.asked'), 1)       AS avg_latency_ms
                FROM audit_logs
                WHERE created_at >= (extract(epoch FROM now() - interval '2 days') * 1000)
                GROUP BY 1
                ORDER BY 1 DESC
                """,
                notes="Counts come from EngineVerse's own audit log, which stores "
                      "metadata only. Disabled until a Postgres credential is selected.",
            ),
            postgres(
                "Content and feedback metrics", WF_F, (240, 0),
                """
                SELECT
                  (SELECT count(*) FROM feedback_events
                    WHERE occurred_at >= now() - interval '2 days') AS feedback_rows,
                  (SELECT count(*) FROM newsletter_subscribers
                    WHERE consent AND consent_at >= now() - interval '2 days') AS new_subscribers,
                  (SELECT count(*) FROM users
                    WHERE created_at >= (extract(epoch FROM now() - interval '2 days') * 1000)) AS new_accounts
                """,
                notes="Optional: enable after the feedback/onboarding tables exist.",
            ),
            code(
                "Aggregate", WF_F, (460, 0),
                r"""
// Build a report from measured rows only. Absent data is reported as absent:
// this workflow must never invent traffic, visitors or retention numbers.
const assistantRows = $("Assistant metrics").all().map((item) => item.json).filter(Boolean);
const other = $("Content and feedback metrics").first()?.json || {};
const measured = assistantRows.length > 0;
return [{
  json: {
    generatedAt: new Date().toISOString(),
    measured,
    note: measured
      ? "Counts are from EngineVerse's audit log for the last two complete days."
      : "No database rows were returned - the datastore nodes are disabled or empty. Nothing is estimated.",
    assistant: assistantRows,
    product: other,
    // Deliberately not included: unique visitors, referral sources or retention
    // cohorts. EngineVerse runs no third-party analytics, so these are not
    // measurable here and are not guessed.
    notMeasured: ["unique visitors", "referral sources", "retention cohorts", "conversion rate"],
  },
}];
""",
            ),
            email(
                "Daily digest", WF_F, (680, 0),
                subject="EngineVerse daily numbers (measured only)",
                body=(
                    "Measured run at {{ $json.generatedAt }}\n\n"
                    "Assistant rows: {{ JSON.stringify($json.assistant) }}\n\n"
                    "Product rows: {{ JSON.stringify($json.product) }}\n\n"
                    "Not measured: {{ $json.notMeasured.join(', ') }}\n\n"
                    "{{ $json.note }}\n"
                ),
                notes="Disabled until SMTP is configured.",
            ),
            noop("Done", WF_F, (900, 0)),
        ],
        connect(
            ("Daily at 03:00", "Assistant metrics", 0),
            ("Assistant metrics", "Content and feedback metrics", 0),
            ("Content and feedback metrics", "Aggregate", 0),
            ("Aggregate", "Daily digest", 0),
            ("Daily digest", "Done", 0),
        ),
        notes="Measured metrics only. Unmeasured numbers are named, never estimated.",
    )

    # --------------------------------------------------------------- G: monitoring
    WF_G = "monitoring"
    flows["07-ops-monitoring.json"] = workflow(
        "EngineVerse · Operational monitoring", "monitoring",
        [
            node("On workflow failure", WF_G, "n8n-nodes-base.errorTrigger", 1, (-200, 0), {},
                 notes="Attach to any workflow with the Settings → Error Workflow selector."),
            code(
                "Summarise without secrets", WF_G, (20, 0),
                r"""
// Operational facts only. Error payloads can contain a student's message, an
// API key in a URL, or a credential name, so only the shape is forwarded.
const data = $json || {};
const message = String(data.execution?.error?.message ?? data.error?.message ?? "Unknown error");
const safeMessage = message
  .replace(/sk-[A-Za-z0-9_-]{10,}/g, "[redacted key]")
  .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [redacted]")
  .replace(/https?:\/\/[^\s"']*\?[^\s"']*/g, "[redacted url with query]")
  .slice(0, 500);

const workflowName = String(data.workflow?.name ?? "unknown workflow");
const nodeName = String(data.execution?.lastNodeExecuted ?? "unknown node");
const executionId = String(data.execution?.id ?? "");
const when = new Date().toISOString();

return [{
  json: {
    severity: /credential|auth|401|403/i.test(safeMessage) ? "high" : "medium",
    workflowName,
    nodeName,
    executionId,
    safeMessage,
    when,
    // Coarse dedupe window: one notification per workflow per 15 minutes.
    dedupeKey: `${workflowName}:${Math.floor(Date.now() / 900000)}`,
    action: "Open the n8n execution list, fix the cause, then re-run the failed execution. "
          + "If the assistant is affected, check EngineVerse's /api/assistant/status.",
  },
}];
""",
                notes="Redacts keys, bearer tokens and query strings before notifying.",
            ),
            code(
                "Deduplicate", WF_G, (240, 0),
                r"""
const store = $getWorkflowStaticData("global");
const seen = store.notified || {};
const now = Date.now();
for (const [key, at] of Object.entries(seen)) {
  if (now - at > 86_400_000) delete seen[key];
}
const item = $json;
const duplicate = Boolean(seen[item.dedupeKey]);
if (!duplicate) seen[item.dedupeKey] = now;
store.notified = seen;
return [{ json: { ...item, duplicate } }];
""",
                notes="Static data survives restarts for active workflows; one alert per "
                      "workflow per window instead of an alert storm.",
            ),
            if_node("New problem?", WF_G, (460, 0), "={{ $json.duplicate === false }}"),
            telegram(
                "Notify admin (Telegram)", WF_G, (680, 0),
                "⚠️ {{ $json.workflowName }} failed at {{ $json.nodeName }} ({{ $json.severity }}).\n"
                "{{ $json.safeMessage }}\nExecution: {{ $json.executionId }}\n{{ $json.action }}",
                notes="Disabled until a Telegram credential is selected.",
            ),
            email(
                "Notify admin (email)", WF_G, (680, 200),
                subject="n8n failure: {{ $json.workflowName }}",
                body=("Workflow: {{ $json.workflowName }}\nNode: {{ $json.nodeName }}\n"
                      "Severity: {{ $json.severity }}\nWhen: {{ $json.when }}\n\n"
                      "{{ $json.safeMessage }}\n\n{{ $json.action }}\n"),
                notes="Enable either this or the Telegram node, not both.",
            ),
            noop("Logged", WF_G, (900, 0)),
        ],
        connect(
            ("On workflow failure", "Summarise without secrets", 0),
            ("Summarise without secrets", "Deduplicate", 0),
            ("Deduplicate", "New problem?", 0),
            ("New problem?", "Notify admin (Telegram)", 0),
            ("New problem?", "Notify admin (email)", 1),
            ("Notify admin (Telegram)", "Logged", 0),
            ("Notify admin (email)", "Logged", 0),
        ),
        notes="Error Trigger → redact → dedupe → notify. Alerts carry no student text.",
    )

    return flows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    flows = build()
    for filename, data in flows.items():
        (OUT / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(flows)} workflows to {OUT.relative_to(ROOT)}")
    for filename in sorted(flows):
        print(f"  {filename}: {len(flows[filename]['nodes'])} nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
