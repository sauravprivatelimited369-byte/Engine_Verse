"""The n8n automation templates shipped in ``automation/n8n``.

These files are imported by the operator rather than executed by EngineVerse, so
the tests here check the things a bad import would break:

* every file is valid JSON with the keys n8n expects;
* every connection points at a node that exists, and node names are unique;
* nothing embeds a credential, a real webhook URL or a token;
* the copilot workflow responds through a Respond-to-Webhook node (otherwise
  the website's 45-second server timeout would wait for a response n8n never
  sends), and its system message keeps the honesty rules the UI claims.

What this does **not** prove is that an import into a specific n8n version
renders correctly: that needs the operator's instance, and
``scripts/check_assistant.py`` plus a real message is the only honest check.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AUTOMATION = ROOT / "automation" / "n8n"
FILES = sorted(AUTOMATION.glob("*.json"))


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_the_templates_are_present():
    names = {path.name for path in FILES}
    assert {
        "01-student-copilot.json",
        "02-feedback-intake.json",
        "03-student-onboarding.json",
        "05-monitoring.json",
        "06-uptime-check.json",
    } <= names


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_each_file_is_an_importable_inactive_workflow(path):
    data = _load(path)
    assert data["name"].startswith("EngineVerse · ")
    assert data["active"] is False, "nothing may activate itself on import"
    assert isinstance(data["nodes"], list) and data["nodes"]
    assert isinstance(data["connections"], dict)

    names = [node["name"] for node in data["nodes"]]
    ids = [node["id"] for node in data["nodes"]]
    assert len(set(names)) == len(names), f"{path.name} repeats a node name"
    assert len(set(ids)) == len(ids), f"{path.name} repeats a node id"

    for node in data["nodes"]:
        assert node["type"].startswith(("n8n-nodes-base.", "@n8n/n8n-nodes-langchain.")), node["type"]
        assert isinstance(node["typeVersion"], (int, float))
        assert len(node["position"]) == 2
        assert isinstance(node["parameters"], dict)

    for source, outputs in data["connections"].items():
        assert source in names, f"{path.name}: connection from unknown node {source}"
        for channel, groups in outputs.items():
            assert isinstance(groups, list)
            for group in groups:
                for link in group:
                    assert link["node"] in names, f"{path.name}: link to unknown node {link['node']}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_credential_or_real_endpoint_is_embedded(path):
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    for node in data["nodes"]:
        assert "credentials" not in node, f"{path.name}: {node['name']} embeds a credential reference"
    assert "n8n.cloud" not in raw
    assert "authorsauravkushwaha" not in raw
    for secret in re.findall(r"\b(?:sk|ghp|xox[bp])-[A-Za-z0-9_-]{8,}", raw):
        pytest.fail(f"{path.name} contains something shaped like a credential: {secret[:6]}…")


def test_the_copilot_contract_matches_the_server_bridge():
    data = _load(AUTOMATION / "01-student-copilot.json")
    by_type = {node["type"]: node for node in data["nodes"]}

    webhook = by_type["n8n-nodes-base.webhook"]
    assert webhook["parameters"]["httpMethod"] == "POST"
    assert webhook["parameters"]["responseMode"] == "responseNode"
    assert webhook["parameters"]["authentication"] == "headerAuth", (
        "the bridge sends a shared secret header; the webhook must require it"
    )

    respond = [node for node in data["nodes"] if node["type"] == "n8n-nodes-base.respondToWebhook"]
    assert respond, "a responseNode webhook without a Respond node would time out"

    agent = by_type["@n8n/n8n-nodes-langchain.agent"]
    system = agent["parameters"]["options"]["systemMessage"]
    # Claims the interface makes to a student, checked against what the model is
    # told. If one of these is removed from the prompt, the UI is overstating.
    lowered = system.lower()
    for claim in ("not a person", "cannot run code", "browse the internet", "hindi", "never invent"):
        assert claim in lowered, claim
    assert "do not ask for or repeat passwords" in lowered


def test_the_monitoring_workflow_redacts_before_notifying():
    raw = (AUTOMATION / "05-monitoring.json").read_text(encoding="utf-8")
    assert "redacted" in raw
    assert "no student question or reply" in raw


def test_the_onboarding_schema_makes_a_repeat_subscription_a_no_op():
    sql = (AUTOMATION / "feedback.sql").read_text(encoding="utf-8")
    assert "email" in sql and "UNIQUE" in sql
    onboarding = (AUTOMATION / "03-student-onboarding.json").read_text(encoding="utf-8")
    assert "ON CONFLICT (email) DO NOTHING" in onboarding
    assert "revoked_at" in sql, "an unsubscribe path needs a way to record withdrawal"
    # The consent rule is enforced in the workflow, not only in the form.
    assert "consent === true" in onboarding


def test_the_feedback_workflow_stores_no_answer_text():
    raw = (AUTOMATION / "02-feedback-intake.json").read_text(encoding="utf-8")
    assert "answer" not in raw.lower() or "answer text" in raw.lower()
    assert "contactConsent" in raw
    assert "queryReplacement" in raw, "values must be parameterised, not interpolated into SQL"
