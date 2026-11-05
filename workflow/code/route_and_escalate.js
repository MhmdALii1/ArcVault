// Deterministic on purpose: the same facts always give the same queue, and a customer
// message can't talk the model into a route. Thresholds live here, in one place.
const CONFIDENCE_THRESHOLD = 0.7;
const BILLING_ESCALATION_USD = 500;
const ESCALATION_QUEUE = 'Human Escalation';

const QUEUE_BY_CATEGORY = {
  'Bug Report': 'Engineering',
  'Feature Request': 'Product',
  'Billing Issue': 'Billing',
  'Technical Question': 'IT/Security',
  'Incident/Outage': 'Engineering',
};

// Whole words only, so "download" doesn't match "down".
const OUTAGE_PHRASES = /\boutage\b|\bdown for (all users|everyone|all of us)\b/i;

const record = $input.first().json;
const { classification, enrichment, raw_message: message } = record;
const billing = enrichment.billing;
const reasons = [];

if (!record.classification_valid) reasons.push('classification_invalid');
if (!record.enrichment_valid) reasons.push('enrichment_invalid');

if (record.classification_valid && classification.confidence < CONFIDENCE_THRESHOLD) {
  reasons.push('low_confidence');
}
if (classification.category === 'Incident/Outage') reasons.push('incident_category');
if (OUTAGE_PHRASES.test(message)) reasons.push('outage_language');

if (billing) {
  if (billing.discrepancy !== null && billing.discrepancy > BILLING_ESCALATION_USD) {
    reasons.push('billing_discrepancy_over_500');
  } else if (
    billing.discrepancy === null &&
    (!billing.amounts_verified || (billing.charged_amount ?? 0) > BILLING_ESCALATION_USD)
  ) {
    // No baseline to compare against, so a person has to judge the size of the error.
    reasons.push('billing_amount_unverified');
  }
}

const suggestedQueue = QUEUE_BY_CATEGORY[classification.category] ?? 'Unassigned';
const escalated = reasons.length > 0;

return [{
  json: {
    ...record,
    routing: {
      suggested_queue: suggestedQueue,
      final_queue: escalated ? ESCALATION_QUEUE : suggestedQueue,
      escalated,
      escalation_reasons: reasons,
    },
  },
}];
