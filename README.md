# ArcVault AI Intake & Triage

An n8n workflow that classifies, enriches, and routes unstructured customer requests for ArcVault, a fictional B2B software company. Uncertain or high-risk tickets go to a person. Built for the Valsoft AI Engineer technical assessment.

**The main design choice:** the LLM reads and writes, and code makes the routing and escalation decisions.

## Deliverables

| Brief section | Deliverable | Where |
|---|---|---|
| 4.1 Working workflow | n8n export | [workflow/arcvault-triage.json](workflow/arcvault-triage.json) |
| 4.1 Working workflow | Screenshots of each step | [docs/screenshots/](docs/screenshots/) |
| 4.1 Working workflow | Walkthrough video | *Link in the submission email* |
| 4.2 Structured output | Records for the five samples | [output/results.json](output/results.json) |
| 4.2 Structured output | Queue view, one tab per queue | [Google Sheet](https://docs.google.com/spreadsheets/d/1BUDLOcLnZYHgREFK_GRaC6XAVIAwTXoTr0lv8_EfQto/edit?usp=sharing) |
| 4.3 Prompts | Prompts, reasoning, and what the AI got wrong | [PROMPTS.md](PROMPTS.md) |
| 4.4 Architecture | Design, routing, escalation, production, Phase 2 | [ARCHITECTURE.md](ARCHITECTURE.md) |

## Results for the five samples

| # | Category | Priority | Confidence | Queue | Escalated |
|---|---|---|---|---|---|
| 1 | Bug Report | High | 0.94 | Engineering | No |
| 2 | Feature Request | Low | 0.96 | Product | No |
| 3 | Billing Issue | Medium | 0.95 | Billing | No: the error is $260, under $500 |
| 4 | Technical Question | Low | 0.96 | IT/Security | No |
| 5 | Incident/Outage | High | 0.96 | Human Escalation (suggested: Engineering) | Yes |

I also ran seven edge cases to exercise the escalation paths, including a vague message, a prompt injection attempt, and a non-English message. Six produce records in [output/edge_cases.json](output/edge_cases.json), and the seventh, an empty message, is rejected with a 400 response. All 12 cases pass, but they are a small hand-written set, so [ARCHITECTURE.md](ARCHITECTURE.md) explains what this does and doesn't prove.

## Run it yourself

You need an n8n account, a free [Groq API key](https://console.groq.com/keys), and a Google account.

1. **Create a Google Sheet** with five tabs: `Engineering`, `Billing`, `Product`, `IT-Security`, `Human Escalation`. Paste this into cell A1 of each:
   ```
   =SPLIT("id,source,received_at,category,priority,confidence,core_issue,urgency,account_ids,invoice_numbers,error_codes,other_references,timeframe,billing_discrepancy,suggested_queue,final_queue,escalated,escalation_reasons,summary,raw_message",",")
   ```
2. **Add two n8n credentials:**
   - Header Auth named `Groq API`, with Name `Authorization` and Value `Bearer <your key>`
   - Google Sheets OAuth2 named `Google Sheets`
3. **Point the workflow at your sheet and import it:**
   ```
   python scripts/build_workflow.py --sheet-id <YOUR_SHEET_ID>
   ```
   Import `workflow/arcvault-triage.json` into n8n, select the credentials on the 3 LLM nodes and 5 **Save to...** nodes, then activate it.
4. **Send the test messages:**
   ```
   python scripts/run_cases.py --url <PRODUCTION_WEBHOOK_URL> --cases data/samples.json --out output/results.json
   python scripts/run_cases.py --url <PRODUCTION_WEBHOOK_URL> --cases data/edge_cases.json --out output/edge_cases.json
   ```
5. **Run the offline rule tests,** which need no API key:
   ```
   node --test tests/rules.test.mjs
   ```

To send one message by hand:
```
curl -X POST <PRODUCTION_WEBHOOK_URL> -H "Content-Type: application/json" -d "{\"source\":\"Email\",\"raw_message\":\"Your message here\"}"
```

## Repository layout

| Path | Contents |
|---|---|
| `workflow/arcvault-triage.json` | The n8n workflow, ready to import |
| `workflow/code/` | Logic for the Code nodes |
| `prompts/` | The three LLM prompts |
| `scripts/build_workflow.py` | Builds the workflow file from the prompts and code |
| `scripts/run_cases.py` | Sends test cases to the webhook, then scores and saves the results |
| `data/` | The five samples and the edge cases, with expected results |
| `tests/` | Offline tests for the routing and validation rules |
| `output/` | Generated records |

## Tools

n8n Cloud, Groq (`openai/gpt-oss-120b`), and Google Sheets. All were used on free tiers or a trial. [ARCHITECTURE.md](ARCHITECTURE.md) explains each choice. Built with Claude Code as an AI assistant, as the brief expects; [PROMPTS.md](PROMPTS.md) records what the AI got wrong and how it was fixed.
