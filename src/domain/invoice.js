const ALLOWED_VAT_RATES = new Set([0, 6, 12, 21]);

function roundMoney(value) {
  return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}

export function validateInvoiceDraft(draft) {
  const errors = [];
  if (!draft || typeof draft !== 'object') return ['draft'];
  if (typeof draft.client !== 'string' || draft.client.trim().length < 2) errors.push('client');
  if (typeof draft.description !== 'string' || draft.description.trim().length < 2) errors.push('description');
  const amount = Number(draft.amount);
  if (!Number.isFinite(amount) || amount <= 0 || amount > 10_000_000) errors.push('amount');
  const vat = Number(draft.vat);
  if (!ALLOWED_VAT_RATES.has(vat)) errors.push('vat');
  return errors;
}

export function calculateInvoiceTotals(draft) {
  const net = roundMoney(Number(draft.amount));
  const vatRate = Number(draft.vat);
  const vatAmount = roundMoney(net * vatRate / 100);
  const gross = roundMoney(net + vatAmount);
  return {
    currency: 'EUR',
    net,
    vatRate,
    vatAmount,
    gross
  };
}

export function nextInvoiceNumber(existingNumbers = [], year = new Date().getFullYear()) {
  const prefix = `FAC-${year}-`;
  const highest = existingNumbers
    .filter(value => typeof value === 'string' && value.startsWith(prefix))
    .map(value => Number(value.slice(prefix.length)))
    .filter(Number.isInteger)
    .reduce((max, value) => Math.max(max, value), 0);
  return `${prefix}${String(highest + 1).padStart(4, '0')}`;
}
