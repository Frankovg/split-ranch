import { describe, expect, it } from 'vitest';
import { computeQuickResult, type QuickResultOk } from './compute';
import {
  addParticipant,
  canRemoveParticipant,
  createQuickEvent,
  migrateEventV1,
  removeParticipant,
  setMe,
  setMode,
  setTotalAmount,
  setTotalPayer,
  setWeight,
  toggleExcluded,
  togglePaid,
  updateParticipant,
  upsertExpense,
} from './model';
import { buildShareText } from './share-text';
import type { QuickEvent } from './types';

const NOW = '2026-11-07T12:00:00.000Z';

function withPeople(title: string, names: string[]): QuickEvent {
  let e = createQuickEvent('ev1', title, NOW);
  for (const n of names) e = addParticipant(e, n.toLowerCase(), n, NOW);
  return e;
}

function ok(e: QuickEvent): QuickResultOk {
  const r = computeQuickResult(e);
  if (r.status !== 'ok') throw new Error(`expected ok, got ${r.reason}`);
  return r;
}

const amounts = (r: QuickResultOk) => Object.fromEntries(r.perPerson.map((p) => [p.name, p.amountCents]));
const transfers = (r: QuickResultOk) => r.transfers.map((t) => [t.fromName, t.toName, t.amountCents]);

describe('mode 1: split a total', () => {
  const dinner = () => {
    let e = withPeople('Cena viernes', ['Ana', 'Bea', 'Carlos', 'Dani']);
    e = setTotalAmount(e, 8750, NOW);
    return setTotalPayer(e, 'carlos', NOW);
  };

  it('dinner 87,50 € paid by Carlos (docs/03 §6)', () => {
    const r = ok(dinner());
    expect(r.totalCents).toBe(8750);
    expect(amounts(r)).toEqual({ Ana: 2188, Bea: 2188, Carlos: 2187, Dani: 2187 });
    expect(r.balances?.map((b) => [b.name, b.netCents])).toEqual([
      ['Ana', -2188],
      ['Bea', -2188],
      ['Carlos', 6563],
      ['Dani', -2187],
    ]);
    expect(transfers(r)).toEqual([
      ['Ana', 'Carlos', 2188],
      ['Bea', 'Carlos', 2188],
      ['Dani', 'Carlos', 2187],
    ]);
  });

  it('builds the WhatsApp text exactly as documented', () => {
    expect(buildShareText('Cena viernes', ok(dinner()))).toBe(
      [
        '🧾 Cena viernes — 87,50 €',
        'Cada uno: Ana 21,88 · Bea 21,88 · Carlos 21,87 · Dani 21,87',
        'Pagos: Ana → Carlos 21,88 €; Bea → Carlos 21,88 €; Dani → Carlos 21,87 €',
        'Hecho con Split Ranch',
      ].join('\n'),
    );
  });

  it('without payer: amounts only, no transfers and no "Pagos" line', () => {
    const r = ok(setTotalPayer(dinner(), null, NOW));
    expect(r.balances).toBeNull();
    expect(r.transfers).toEqual([]);
    expect(buildShareText('Cena', r)).not.toContain('Pagos');
  });

  it('variant: 120,00 € with Dani excluded, then weights 2/1/1', () => {
    let e = withPeople('Var', ['Ana', 'Bea', 'Carlos', 'Dani']);
    e = setTotalAmount(e, 12000, NOW);
    e = toggleExcluded(e, 'dani', NOW);
    expect(amounts(ok(e))).toEqual({ Ana: 4000, Bea: 4000, Carlos: 4000 });
    e = setWeight(e, 'ana', 2, NOW);
    expect(amounts(ok(e))).toEqual({ Ana: 6000, Bea: 3000, Carlos: 3000 });
  });

  it('reports incomplete inputs', () => {
    expect(computeQuickResult(createQuickEvent('x', 'x', NOW))).toEqual({
      status: 'incomplete',
      reason: 'no_participants',
    });
    let e = withPeople('x', ['Ana']);
    expect(computeQuickResult(e)).toMatchObject({ reason: 'no_amount' });
    e = toggleExcluded(setTotalAmount(e, 100, NOW), 'ana', NOW);
    expect(computeQuickResult(e)).toMatchObject({ reason: 'no_included' });
  });
});

describe('mode 2: itemised expenses', () => {
  const trip = () => {
    let e = setMode(withPeople('Viaje', ['Ana', 'Bea', 'Carlos']), 'itemised', NOW);
    const all = ['ana', 'bea', 'carlos'];
    e = upsertExpense(e, { id: 'h', description: 'Hotel', amountCents: 30000, payerId: 'ana', participantIds: all }, NOW);
    e = upsertExpense(e, { id: 'f', description: 'Gasolina', amountCents: 5000, payerId: 'bea', participantIds: ['bea', 'ana'] }, NOW);
    e = upsertExpense(e, { id: 'd', description: 'Cena', amountCents: 9100, payerId: 'carlos', participantIds: all }, NOW);
    return e;
  };

  it('trip example (docs/03 §6)', () => {
    const r = ok(trip());
    expect(r.totalCents).toBe(44100);
    expect(amounts(r)).toEqual({ Ana: 15534, Bea: 15533, Carlos: 13033 });
    expect(r.balances?.map((b) => b.netCents)).toEqual([14466, -10533, -3933]);
    expect(transfers(r)).toEqual([
      ['Bea', 'Ana', 10533],
      ['Carlos', 'Ana', 3933],
    ]);
  });

  it('skips incomplete expenses and protects payers from removal', () => {
    let e = trip();
    e = upsertExpense(e, { id: 'z', description: '', amountCents: 500, payerId: 'ana', participantIds: [] }, NOW);
    expect(ok(e).skippedExpenseIds).toEqual(['z']);
    expect(canRemoveParticipant(e, 'carlos')).toBe(false);
    expect(removeParticipant(e, 'carlos', NOW)).toBe(e);
  });
});

describe('participants', () => {
  it('keeps creation order and rejects empty or duplicate names', () => {
    let e = withPeople('x', ['Zoe', 'Ana']);
    e = addParticipant(e, 'dup', '  ana ', NOW);
    e = addParticipant(e, 'empty', '   ', NOW);
    expect(e.participants.map((p) => p.name)).toEqual(['Zoe', 'Ana']);
  });

  it('removal cleans payer, exclusions and weights', () => {
    let e = withPeople('x', ['Ana', 'Bea']);
    e = setTotalPayer(setWeight(toggleExcluded(e, 'bea', NOW), 'bea', 3, NOW), 'bea', NOW);
    e = removeParticipant(e, 'bea', NOW);
    expect(e.total).toEqual({ amountCents: null, excludedIds: [], weights: {}, payerId: null });
  });
});

describe('me and paid status', () => {
  it('marks one participant as me and toggles paid by hand', () => {
    let e = withPeople('x', ['Ana', 'Bea']);
    e = setMe(e, 'bea', NOW);
    expect(e.meId).toBe('bea');
    expect(setMe(e, 'ghost', NOW)).toBe(e);
    e = togglePaid(togglePaid(e, 'ana', NOW), 'bea', NOW);
    expect(e.paidIds).toEqual(['ana', 'bea']);
    e = togglePaid(e, 'ana', NOW);
    expect(e.paidIds).toEqual(['bea']);
  });

  it('keeps the paid status when amounts or names change', () => {
    let e = setTotalPayer(setTotalAmount(withPeople('x', ['Ana', 'Bea']), 1000, NOW), 'ana', NOW);
    e = togglePaid(e, 'bea', NOW);
    e = updateParticipant(setTotalAmount(e, 2000, NOW), 'bea', { name: 'Beatriz' }, NOW);
    expect(e.paidIds).toEqual(['bea']);
    expect(e.participants[1]?.name).toBe('Beatriz');
  });

  it('removing a participant clears me and paid', () => {
    let e = togglePaid(setMe(withPeople('x', ['Ana', 'Bea']), 'bea', NOW), 'bea', NOW);
    e = removeParticipant(e, 'bea', NOW);
    expect(e.meId).toBeNull();
    expect(e.paidIds).toEqual([]);
  });

  it('ticks paid debtors in the share text', () => {
    let e = setTotalPayer(setTotalAmount(withPeople('Cena', ['Ana', 'Bea', 'Carlos']), 3000, NOW), 'ana', NOW);
    e = togglePaid(e, 'bea', NOW);
    const text = buildShareText(e.title, ok(e), undefined, 'es-ES', e.paidIds);
    expect(text.split('\n')[2]).toMatch(/^Pagos: Bea → Ana 10,00\s€ ✓; Carlos → Ana 10,00\s€$/);
  });

  it('migrates v1 events: adds me/paid and drops payment handles', () => {
    const v1 = { ...withPeople('x', ['Ana']), meId: undefined, paidIds: undefined } as Record<string, unknown>;
    (v1.participants as Record<string, unknown>[])[0]!.paypalMe = 'ana';
    const e = migrateEventV1(v1);
    expect(e.meId).toBeNull();
    expect(e.paidIds).toEqual([]);
    expect(e.participants[0]).toEqual({ id: 'ana', name: 'Ana' });
  });
});
