// Assembles the final record. If the summary step fails, a template keeps the record usable.
const triage = $('Route & Escalate').first().json;
const config = $('Prompts & Config').first().json;

function parseSummary(response) {
  try {
    const summary = JSON.parse(response.choices[0].message.content).summary;
    return typeof summary === 'string' && summary.trim() ? summary.trim() : null;
  } catch (e) {
    return null;
  }
}

// Keeps only named text fields, never the whole error object, because that can hold request
// headers and therefore the API key.
function llmError(nodeName) {
  const error = $(nodeName).first().json.error;
  if (!error) return null;
  const parts = typeof error === 'string'
    ? [error]
    : [error.httpCode, error.message, error.description, error.error?.message];
  const text = parts.filter(Boolean).join(' | ');
  return (text || safeDump(error)).slice(0, 500);
}

// For errors with no named fields: drops anything that could carry credentials, then redacts keys.
function safeDump(error) {
  const dropped = /header|config|request|auth|token|key|secret|cookie/i;
  const json = JSON.stringify(error, (name, value) => (dropped.test(name) ? undefined : value));
  return (json ?? 'unknown error').replace(/gsk_\w+/g, '[redacted]').replace(/Bearer\s+\S+/gi, '[redacted]');
}

const { classification, enrichment, routing } = triage;
const llmSummary = parseSummary($input.first().json);
const fallbackSummary =
  `${enrichment.core_issue} Classified as ${classification.category} with ${classification.priority} priority. ` +
  (routing.escalated
    ? `A person must review this ticket: ${routing.escalation_reasons.join(', ')}.`
    : `Please review it in the ${routing.final_queue} queue.`);

const record = {
  id: triage.id,
  source: triage.source,
  received_at: triage.received_at,
  raw_message: triage.raw_message,
  classification,
  enrichment,
  routing,
  summary: llmSummary ?? fallbackSummary,
  metadata: {
    model: config.model,
    prompt_version: config.prompt_version,
    workflow_version: config.workflow_version,
    summary_source: llmSummary ? 'llm' : 'template_fallback',
    llm_errors: {
      classify: llmError('Classify (LLM)'),
      enrich: llmError('Enrich (LLM)'),
      summarize: llmError('Summarize (LLM)'),
    },
    processed_at: new Date().toISOString(),
  },
};

const ids = enrichment.identifiers;
const row = {
  id: record.id,
  source: record.source,
  received_at: record.received_at,
  category: classification.category,
  priority: classification.priority,
  confidence: classification.confidence,
  core_issue: enrichment.core_issue,
  urgency: enrichment.urgency,
  account_ids: ids.account_ids.join(', '),
  invoice_numbers: ids.invoice_numbers.join(', '),
  error_codes: ids.error_codes.join(', '),
  other_references: ids.other.join(', '),
  timeframe: enrichment.timeframe ?? '',
  billing_discrepancy: enrichment.billing?.discrepancy ?? '',
  suggested_queue: routing.suggested_queue,
  final_queue: routing.final_queue,
  escalated: routing.escalated,
  escalation_reasons: routing.escalation_reasons.join(', '),
  summary: record.summary,
  raw_message: record.raw_message,
};

return [{ json: { ...row, record } }];
