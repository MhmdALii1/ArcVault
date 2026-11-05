#!/usr/bin/env python3
"""Builds workflow/arcvault-triage.json from prompts/ and workflow/code/.

Keeping prompts and node logic in plain files lets them be reviewed in Git and unit-tested.
Usage: python scripts/build_workflow.py --sheet-id <GOOGLE_SHEET_ID>
"""
import argparse
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "openai/gpt-oss-120b"
PROMPT_VERSION = "1.2"
WORKFLOW_VERSION = "1.0"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Queue name -> Google Sheet tab ("/" is avoided in tab names).
QUEUES = {
    "Engineering": "Engineering",
    "Billing": "Billing",
    "Product": "Product",
    "IT/Security": "IT-Security",
    "Human Escalation": "Human Escalation",
}
SHEET_COLUMNS = [
    "id", "source", "received_at", "category", "priority", "confidence", "core_issue",
    "urgency", "account_ids", "invoice_numbers", "error_codes", "other_references",
    "timeframe", "billing_discrepancy", "suggested_queue", "final_queue", "escalated",
    "escalation_reasons", "summary", "raw_message",
]
FILTER_OPTIONS = {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2}


def node_id(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"arcvault/{name}"))


def node(name, node_type, version, position, parameters, **extra):
    return {
        "id": node_id(name), "name": name, "type": f"n8n-nodes-base.{node_type}",
        "typeVersion": version, "position": position, "parameters": parameters, **extra,
    }


def code_node(name, filename, position):
    code = (ROOT / "workflow" / "code" / filename).read_text(encoding="utf-8")
    return node(name, "code", 2, position, {"jsCode": code})


def config_code():
    prompts = {p: (ROOT / "prompts" / f"{p}.md").read_text(encoding="utf-8").strip()
               for p in ("classify", "enrich", "summarize")}
    config = {"model": MODEL, "prompt_version": PROMPT_VERSION,
              "workflow_version": WORKFLOW_VERSION, "prompts": prompts}
    return ("// The model and all prompts, in one place. Generated from prompts/*.md.\n"
            f"return [{{ json: {json.dumps(config, indent=2)} }}];\n")


def llm_node(name, prompt_key, user_expression, position):
    # Written so "}}" never appears inside the expression, because n8n would read it as the end.
    body = (
        "={{ JSON.stringify({ "
        "model: $('Prompts & Config').first().json.model, "
        "temperature: 0, "
        "reasoning_effort: 'low', "
        "max_completion_tokens: 1500, "
        "response_format: { type: 'json_object' }, "
        "messages: ["
        f"{{ role: 'system', content: $('Prompts & Config').first().json.prompts.{prompt_key} }}, "
        f"{{ role: 'user', content: {user_expression} }}"
        "] }) }}"
    )
    return node(
        name, "httpRequest", 4.2, position,
        {
            "method": "POST", "url": GROQ_URL,
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendBody": True, "specifyBody": "json", "jsonBody": body,
            "options": {"timeout": 60000},
        },
        credentials={"httpHeaderAuth": {"name": "Groq API"}},
        retryOnFail=True, maxTries=3, waitBetweenTries=3000,
        # A failed call continues so the validators can send the ticket to a human.
        onError="continueRegularOutput",
    )


def sheet_node(queue, tab, sheet_id, position):
    return node(
        f"Save to {queue}".replace("/", "-"), "googleSheets", 4.5, position,
        {
            "operation": "append",
            "documentId": {"__rl": True, "mode": "id", "value": sheet_id},
            "sheetName": {"__rl": True, "mode": "name", "value": tab},
            "columns": {
                "mappingMode": "defineBelow",
                "value": {c: f"={{{{ $json.{c} }}}}" for c in SHEET_COLUMNS},
                "matchingColumns": [],
                "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False,
                            "display": True, "type": "string", "canBeUsedToMatch": True}
                           for c in SHEET_COLUMNS],
                "attemptToConvertTypes": False, "convertFieldsToString": False,
            },
            "options": {},
        },
        credentials={"googleSheetsOAuth2Api": {"name": "Google Sheets"}},
        retryOnFail=True, maxTries=3, waitBetweenTries=3000,
        # Deliberately no onError: if a ticket can't be saved, the caller must get an error.
    )


def switch_node(position):
    rules = [{
        "conditions": {
            "options": FILTER_OPTIONS, "combinator": "and",
            "conditions": [{
                "id": node_id(f"rule-{queue}"), "leftValue": "={{ $json.final_queue }}",
                "rightValue": queue, "operator": {"type": "string", "operation": "equals"},
            }],
        },
        "renameOutput": True, "outputKey": queue,
    } for queue in QUEUES]
    return node("Route to Queue", "switch", 3.2, position, {"rules": {"values": rules}, "options": {}})


def build(sheet_id):
    normalized = "$('Normalize Input').first().json.prompt_message"
    message = f"'<customer_message>\\n' + {normalized} + '\\n</customer_message>'"
    enrich_user = f"'Category: ' + $json.classification.category + '\\n' + {message}"
    triage = ("JSON.stringify({ category: $json.classification.category, "
              "priority: $json.classification.priority, "
              "confidence: $json.classification.confidence, "
              "enrichment: $json.enrichment, routing: $json.routing })")
    summary_user = f"{message} + '\\n<triage>\\n' + {triage} + '\\n</triage>'"

    nodes = [
        node("Receive Message", "webhook", 2, [0, 300],
             {"httpMethod": "POST", "path": "arcvault/intake", "responseMode": "responseNode", "options": {}},
             webhookId=node_id("webhook")),
        code_node("Normalize Input", "normalize_input.js", [220, 300]),
        node("Has Message?", "if", 2.2, [440, 300], {
            "conditions": {
                "options": FILTER_OPTIONS, "combinator": "and",
                "conditions": [{
                    "id": node_id("has-message"), "leftValue": "={{ $json.valid }}", "rightValue": "",
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
            },
            "options": {},
        }),
        node("Reject Empty Message", "respondToWebhook", 1.1, [660, 520], {
            "respondWith": "json",
            "responseBody": '={{ JSON.stringify({ error: "raw_message is required" }) }}',
            "options": {"responseCode": 400},
        }),
        node("Prompts & Config", "code", 2, [660, 300], {"jsCode": config_code()}),
        llm_node("Classify (LLM)", "classify", message, [880, 300]),
        code_node("Validate Classification", "validate_classification.js", [1100, 300]),
        llm_node("Enrich (LLM)", "enrich", enrich_user, [1320, 300]),
        code_node("Validate Enrichment", "validate_enrichment.js", [1540, 300]),
        code_node("Route & Escalate", "route_and_escalate.js", [1760, 300]),
        llm_node("Summarize (LLM)", "summarize", summary_user, [1980, 300]),
        code_node("Build Record", "build_record.js", [2200, 300]),
        switch_node([2420, 300]),
    ]
    sheet_nodes = [sheet_node(q, tab, sheet_id, [2640, 60 + i * 120])
                   for i, (q, tab) in enumerate(QUEUES.items())]
    nodes += sheet_nodes
    nodes.append(node("Respond with Record", "respondToWebhook", 1.1, [2860, 300], {
        "respondWith": "json",
        "responseBody": "={{ JSON.stringify($('Build Record').first().json.record) }}",
        "options": {"responseCode": 200},
    }))

    def link(target):
        return {"node": target, "type": "main", "index": 0}

    chain = ["Receive Message", "Normalize Input", "Has Message?", "Prompts & Config", "Classify (LLM)",
             "Validate Classification", "Enrich (LLM)", "Validate Enrichment", "Route & Escalate",
             "Summarize (LLM)", "Build Record", "Route to Queue"]
    connections = {a: {"main": [[link(b)]]} for a, b in zip(chain, chain[1:])}
    connections["Has Message?"] = {"main": [[link("Prompts & Config")], [link("Reject Empty Message")]]}
    connections["Route to Queue"] = {"main": [[link(n["name"])] for n in sheet_nodes]}
    for n in sheet_nodes:
        connections[n["name"]] = {"main": [[link("Respond with Record")]]}

    return {"name": "ArcVault Intake & Triage", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet-id", default="PASTE_GOOGLE_SHEET_ID")
    args = parser.parse_args()
    out = ROOT / "workflow" / "arcvault-triage.json"
    out.write_text(json.dumps(build(args.sheet_id), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
