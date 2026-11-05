// Keeps only values that really appear in the message, so a made-up ID can't reach a team.
function parseLlmJson(response) {
  try {
    return JSON.parse(response.choices[0].message.content);
  } catch (e) {
    return null;
  }
}

const previous = $('Validate Classification').first().json;
const message = previous.raw_message;
const lowerMessage = message.toLowerCase();
const digitsOnlyMessage = message.replace(/,/g, '');
const parsed = parseLlmJson($input.first().json);

function literalValues(values) {
  if (!Array.isArray(values)) return [];
  const strings = values.filter((v) => typeof v === 'string' && v.trim());
  return [...new Set(strings.filter((v) => lowerMessage.includes(v.toLowerCase())))];
}

// Returns the amount only when that number is in the message (so "1,240" matches 1240).
function verifiedAmount(value) {
  if (value === null || value === undefined) return { amount: null, rejected: false };
  const n = typeof value === 'number' ? value : parseFloat(String(value).replace(/[$,]/g, ''));
  if (!Number.isFinite(n) || n < 0) return { amount: null, rejected: true };
  const pattern = new RegExp(`(^|[^\\d.])${String(n).replace('.', '\\.')}(\\.0+)?(?![\\d])`);
  return pattern.test(digitsOnlyMessage) ? { amount: n, rejected: false } : { amount: null, rejected: true };
}

function buildBilling(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const charged = verifiedAmount(raw.charged_amount);
  const expected = verifiedAmount(raw.expected_amount);
  const stated = verifiedAmount(raw.stated_discrepancy);

  let discrepancy = stated.amount;
  if (discrepancy === null && charged.amount !== null && expected.amount !== null) {
    discrepancy = Math.round(Math.abs(charged.amount - expected.amount) * 100) / 100;
  }
  return {
    charged_amount: charged.amount,
    expected_amount: expected.amount,
    discrepancy,
    amounts_verified: !(charged.rejected || expected.rejected || stated.rejected),
  };
}

const URGENCY = ['Low', 'Medium', 'High'];
const hasIssue = typeof parsed?.core_issue === 'string' && parsed.core_issue.trim().length > 0;
const hasUrgency = URGENCY.includes(parsed?.urgency);
const ids = parsed?.identifiers ?? {};

return [{
  json: {
    ...previous,
    enrichment: {
      core_issue: hasIssue ? parsed.core_issue.trim() : 'Could not be extracted automatically; see the raw message.',
      urgency: hasUrgency ? parsed.urgency : 'Medium',
      urgency_reason: typeof parsed?.urgency_reason === 'string' ? parsed.urgency_reason : '',
      identifiers: {
        account_ids: literalValues(ids.account_ids),
        invoice_numbers: literalValues(ids.invoice_numbers),
        error_codes: literalValues(ids.error_codes),
        other: literalValues(ids.other),
      },
      timeframe: typeof parsed?.timeframe === 'string' && parsed.timeframe.trim() ? parsed.timeframe.trim() : null,
      billing: buildBilling(parsed?.billing),
    },
    enrichment_valid: hasIssue && hasUrgency,
  },
}];
