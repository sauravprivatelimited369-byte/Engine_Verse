# n8n workflows

Importable configurations for the EngineVerse study assistant and the
automation around it. **They import inactive, with credential slots marked
`REPLACE_WITH_…`,** so importing one cannot spend money or message anyone until
you choose a credential and enable a node.

| File | What it is |
|---|---|
| `01-student-copilot.json` | Chat Trigger → validate/limit → OpenAI-compatible model → reply. The assistant EngineVerse's `/assistant` page expects. |
| `01b-student-copilot-agent.json` | The same, built on the AI Agent node with 10-turn memory per session. Pick one variant. |
| `02-feedback-intake.json` | Consent-aware feedback capture with simple, explainable categories. |
| `03-content-drafting.json` | Drafts a lesson and platform variants, then stops for a person to review. |
| `04-onboarding.json` | One welcome message per subscriber, never a duplicate. |
| `05-unsubscribe.json` | Withdraws consent in one click. |
| `06-analytics-rollup.json` | Reports measured metrics only, and names what it cannot measure. |
| `07-ops-monitoring.json` | Error Trigger → redact → dedupe → notify an admin. |

## Quick start

1. In n8n: **Workflows → Import from File**, choose `01-student-copilot.json`.
2. Open the Chat Trigger: **Make Chat Publicly Available** on, **Mode: Embedded
   Chat**, **Allowed Origins**: `https://sauravprivatelimited369-byte.github.io,http://localhost:8000`.
3. Open the model node and choose your own credential. Set a spend cap in your
   provider's dashboard.
4. **Activate**, then copy the node's **Chat URL**.
5. In EngineVerse, set `ENGINEVERSE_ASSISTANT_URL` to that URL (self-hosted) or
   the repository variable `ENGINEVERSE_ASSISTANT_PUBLIC_URL` (GitHub Pages).
6. Verify with one real message:

   ```bash
   python scripts/verify_assistant.py
   ```

Full detail — what each node does, the optional tables, retention, costs and the
manual checklist — is in [`docs/N8N_AUTOMATION.md`](../docs/N8N_AUTOMATION.md).

## Changing a workflow

The JSON here is generated. Edit `scripts/build_n8n_workflows.py` and run:

```bash
python scripts/build_n8n_workflows.py
python scripts/check_n8n_workflows.py
```

The checker validates structure, connections, trigger configuration, credential
placeholders and — when Node is installed — parses the JavaScript inside every
Code node. It cannot replace importing into n8n: node parameter schemas are
version-specific, and the editor is the authority on those.
