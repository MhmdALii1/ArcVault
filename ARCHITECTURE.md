# ArcVault Triage: Architecture

ArcVault receives unstructured customer requests that are sorted by hand and often reach the wrong queue. This workflow classifies, enriches, and routes each message automatically, and sends anything risky or uncertain to a person.

**In one line:** the LLM reads and writes; code makes the decisions.

## 1. System design

```
Webhook → Normalize → Has message? ──no──→ 400 response
                          │ yes
                          ▼
Classify (LLM) → Validate → Enrich (LLM) → Validate → Route & Escalate (code)
                                                            │
Save to queue tab ← Switch ← Build Record ← Summarize (LLM) ┘
       │
       ▼
Webhook response with the full record
```

- **Trigger:** each `POST` to the n8n Cloud webhook starts one run. Any channel can post to this single entry point, so adding one doesn't change the pipeline.
- **LLM:** three calls through the HTTP Request node, with temperature 0, JSON mode, and up to 3 tries.
- **State:** runs share no state. The Google Sheet, with one tab per queue, is the system of record, and n8n's execution log is the debugging trail.

**Why three LLM calls?** Each prompt has one job and its own validation, and the summary runs after routing so it can explain where the ticket went. The cost is latency and tokens: about 9 seconds for one test message.

**Why not an AI Agent node?** The steps never change and there are no tools to choose between, so an agent would add cost and unpredictability without adding capability.

**Model:** `openai/gpt-oss-120b` on Groq's free tier. Accuracy matters more than cost at this volume, so I chose the larger of the two general-purpose models Groq recommends. I did not benchmark it against `gpt-oss-20b`, so this is a judgment call, not a measured result.

**Failure handling:** a failed LLM reply doesn't stop the run. The ticket goes to Human Escalation with a reason code, and a template replaces the summary if needed. This happened for real: a bad credential failed all three LLM calls, and the ticket still reached the escalation tab. A failed sheet write deliberately stops the run so the caller gets an error, but I have not tested that path.

## 2. Routing logic

| Category | Queue | Why |
|---|---|---|
| Bug Report | Engineering | They own product defects |
| Feature Request | Product | They own the roadmap |
| Billing Issue | Billing | They own invoices and contracts |
| Technical Question | IT/Security | The closest fit among the suggested queues for auth and configuration questions |
| Incident/Outage | Engineering (suggested) | They own reliability, but a person reviews first |

Routing is a lookup table in code, so the same facts always produce the same queue, the rules can be tested, and a customer message can't talk the model into a different route.

**Low-confidence fallback:** below 70%, a ticket goes to Human Escalation. Every record keeps `suggested_queue`, so a reviewer can confirm the team instead of starting over.

**Known limitation:** a how-to question about reports doesn't belong with IT/Security. In production I would add a Technical Support queue.

## 3. Escalation logic

Any one of these sends a ticket to Human Escalation, with reason codes recorded:

| Trigger | Why |
|---|---|
| Confidence below 70% | Required by the brief, and the model is admitting doubt |
| Category is Incident/Outage | Sample 5 never says "outage", so keywords alone would miss it |
| Whole-word `outage`, `down for all users`, `down for everyone`, `down for all of us` | A check independent of the LLM, which also resists prompt injection |
| Billing discrepancy above $500 | Material financial risk |
| Large or unconfirmed billing amount with no baseline | A person has to judge the size of the error |
| Invalid LLM output | The ticket can't be trusted to route itself |

Keywords and the LLM category cover each other's blind spots. A message like "is a planned outage scheduled?" will over-escalate, which I accept because a false alarm costs far less than a missed outage.

The billing rule runs whenever enrichment finds a disputed charge, not only for the Billing category, so a misclassified dispute is still caught. Code computes the difference and rejects any amount that isn't literally in the message.

## 4. Assumptions

- **"Billing error > $500" means the disputed difference, not the invoice total.** Sample 3 is $1,240 against $980, a $260 error, so it is not escalated. Using the total would escalate almost every large invoice. If Valsoft reads this differently, it's one rule to change. The $260 also recurs monthly if the rate is wrong, which is a reason to revisit this rule in production.
- **A single user blocked by an error is a Bug Report, not an incident.** Sample 1 stays with Engineering at High priority.
- **Priority and urgency are different fields.** Priority is business importance, and urgency is time pressure. Being a compliance-heavy customer doesn't make a feature request urgent.
- **An empty message isn't a ticket.** It gets a 400 response and never reaches the LLM.

## 5. Results and limits

All 12 cases pass on the final prompts (5 samples and 7 edge cases), and 15 offline tests cover the rules. **This doesn't prove accuracy at scale:** I wrote those 12 cases myself. Confidence is also weakly calibrated: clear messages score 0.94 to 0.96 and the vague case scored 0.55, so it separates obvious cases but isn't a true probability.

## 6. Production-scale changes

- **Reliability:** queue messages before the LLM calls so spikes and Groq outages delay tickets instead of failing them. Add idempotency keys (a repeated message currently creates two rows), webhook authentication (it is currently public), and a dead-letter queue.
- **Cost:** measure whether a smaller model classifies well enough, and keep the large model only where it earns its cost.
- **Latency:** acknowledge the sender immediately and process in the background.
- **Privacy:** redact personal data before the LLM and logs, and replace the Sheet with a ticketing system that has access control.

## 7. Phase 2 (one more week)

1. **Labeled evaluation set:** 200 or more real messages, run on every prompt change. This is the most valuable addition, because it replaces my judgment with measurement.
2. **Confidence calibration:** set the threshold from human corrections rather than the brief's 70%.
3. **Real connectors:** create Jira or Zendesk tickets and page on-call for incidents.
4. **Duplicate detection:** group reports of the same incident into one ticket.
