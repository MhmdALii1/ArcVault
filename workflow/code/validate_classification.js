// Never trust LLM output: check every field. Invalid output is marked, then sent to a human.
const CATEGORIES = ['Bug Report', 'Feature Request', 'Billing Issue', 'Technical Question', 'Incident/Outage'];
const PRIORITIES = ['Low', 'Medium', 'High'];

function parseLlmJson(response) {
  try {
    return JSON.parse(response.choices[0].message.content);
  } catch (e) {
    return null;
  }
}

function normalizeConfidence(value) {
  const isPercent = typeof value === 'string' && value.includes('%');
  const n = typeof value === 'number' ? value : parseFloat(value);
  if (!Number.isFinite(n) || n < 0 || n > 100) return null;
  return isPercent || n > 1 ? n / 100 : n;
}

const parsed = parseLlmJson($input.first().json);
const category = CATEGORIES.find((c) => c === parsed?.category);
const priority = PRIORITIES.find((p) => p === parsed?.priority);
const confidence = normalizeConfidence(parsed?.confidence);
const valid = Boolean(category && priority && confidence !== null);

return [{
  json: {
    ...$('Normalize Input').first().json,
    classification: {
      category: valid ? category : 'Unclassified',
      priority: valid ? priority : 'Medium',
      confidence: valid ? confidence : 0,
      reasoning: typeof parsed?.reasoning === 'string' ? parsed.reasoning : '',
    },
    classification_valid: valid,
  },
}];
