import test from 'node:test';
import assert from 'node:assert/strict';
import { calculateInvoiceTotals, nextInvoiceNumber, validateInvoiceDraft } from '../src/domain/invoice.js';

test('calculates 21% VAT with cent rounding', () => {
  assert.deepEqual(calculateInvoiceTotals({ amount: 99.99, vat: 21 }), {
    currency: 'EUR', net: 99.99, vatRate: 21, vatAmount: 21, gross: 120.99
  });
});

test('accepts zero VAT', () => {
  assert.deepEqual(calculateInvoiceTotals({ amount: 125, vat: 0 }).gross, 125);
});

test('rejects malformed invoice draft', () => {
  assert.deepEqual(
    validateInvoiceDraft({ client: '', description: 'x', amount: -1, vat: 19 }),
    ['client', 'description', 'amount', 'vat']
  );
});

test('accepts a valid invoice draft', () => {
  assert.deepEqual(validateInvoiceDraft({ client: 'Client SA', description: 'Conseil', amount: 500, vat: 21 }), []);
});

test('generates next invoice number without reusing an existing number', () => {
  assert.equal(nextInvoiceNumber(['FAC-2026-0001', 'FAC-2026-0007', 'FAC-2025-0099'], 2026), 'FAC-2026-0008');
});
