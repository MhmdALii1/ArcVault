// Accepts { id?, source?, raw_message } from any channel and produces one clean message.
const body = $input.first().json.body ?? {};
const raw = typeof body.raw_message === 'string' ? body.raw_message.trim() : '';

return [{
  json: {
    id: body.id ?? `ARC-${$execution.id}`,
    source: typeof body.source === 'string' && body.source.trim() ? body.source.trim() : 'Unknown',
    received_at: new Date().toISOString(),
    raw_message: raw,
    // Stops a customer from closing the delimiter tag that marks their text as data.
    prompt_message: raw.replace(/<\/?customer_message>/gi, ''),
    valid: raw.length > 0,
  },
}];
