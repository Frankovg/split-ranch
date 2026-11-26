import { describe, expect, it } from 'vitest';
import { computeQuickResult, type QuickResultOk } from './compute';
import {
  addParticipant,
  canRemoveParticipant,
  createQuickEvent,
  migrateEventV1,
  migrateEventV2,
  payerAmountsGap,
  removeParticipant,
  setMe,
  setMode,
  setMultiplePayers,
  setPayerAmount,
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
        '🧾 *Cena viernes*',
        'Total: 87,50 €',
        'Pagado por: Carlos',
        '',
        '👥 *Lo que le toca a cada uno*',
        '• Ana: 21,88 €',
        '• Bea: 21,88 €',
        '• Carlos: 21,87 €',
        '• Dani: 21,87 €',
        '',
        '💸 *Quién paga a quién*',
        '• Ana → Carlos: 21,88 €',
        '• Bea → Carlos: 21,88 €',
        '• Dani → Carlos: 21,87 €',
      ].join('\n'),
    );
  });

  it('without payer: shares only, no "paid by" and no payments section', () => {
    const r = ok(setTotalPayer(dinner(), null, NOW));
    expect(r.balances).toBeNull();
    expect(r.transfers).toEqual([]);
    const text = buildShareText('Cena', r);
    expect(text).not.toContain('Pagado por');
    expect(text).not.toContain('Quién paga a quién');
    expect(text).not.toContain('Split Ranch');
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

describe('mode 1: several payers', () => {
  const dinner = () => {
    let e = withPeople('Cena viernes', ['Ana', 'Bea', 'Carlos', 'Dani']);
    e = setMultiplePayers(setTotalAmount(e, 8750, NOW), NOW);
    e = setPayerAmount(e, 'ana', 5000, NOW);
    return setPayerAmount(e, 'carlos', 3750, NOW);
  };

  it('shares stay the same; paid and transfers follow what each one put in', () => {
    const r = ok(dinner());
    expect(r.totalCents).toBe(8750);
    expect(amounts(r)).toEqual({ Ana: 2188, Bea: 2188, Carlos: 2187, Dani: 2187 });
    expect(r.balances?.map((b) => [b.name, b.paidCents, b.owedCents, b.netCents])).toEqual([
      ['Ana', 5000, 2188, 2812],
      ['Bea', 0, 2188, -2188],
      ['Carlos', 3750, 2187, 1563],
      ['Dani', 0, 2187, -2187],
    ]);
    expect(transfers(r)).toEqual([
      ['Bea', 'Ana', 2188],
      ['Dani', 'Carlos', 1563],
      ['Dani', 'Ana', 624],
    ]);
    expect(buildShareText('Cena viernes', r).split('\n')[2]).toBe('Pagado por: Ana (50,00 €), Carlos (37,50 €)');
  });

  it('is incomplete until the amounts add up to the total', () => {
    let e = setPayerAmount(dinner(), 'carlos', 3000, NOW);
    expect(payerAmountsGap(e)).toBe(750);
    expect(computeQuickResult(e)).toMatchObject({ reason: 'payers_mismatch' });
    e = setPayerAmount(e, 'bea', 1000, NOW);
    expect(payerAmountsGap(e)).toBe(-250);
    e = setPayerAmount(e, 'bea', 750, NOW);
    expect(payerAmountsGap(e)).toBe(0);
    expect(ok(e).balances?.find((b) => b.name === 'Bea')?.paidCents).toBe(750);
  });

  it('starts from the single payer and goes back to one payer', () => {
    let e = setTotalPayer(setTotalAmount(withPeople('x', ['Ana', 'Bea']), 1000, NOW), 'bea', NOW);
    e = setMultiplePayers(e, NOW);
    expect(e.total).toMatchObject({ payerId: null, payerAmounts: { bea: 1000 } });
    expect(setPayerAmount(e, 'ghost', 10, NOW)).toBe(e);
    e = setPayerAmount(e, 'bea', 0, NOW);
    expect(e.total.payerAmounts).toEqual({});
    e = setTotalPayer(e, 'ana', NOW);
    expect(e.total).toMatchObject({ payerId: 'ana', payerAmounts: null });
    expect(payerAmountsGap(e)).toBeNull();
  });

  it('migrates v2 events: adds payerAmounts', () => {
    const v2 = withPeople('x', ['Ana']) as unknown as { total: Record<string, unknown> };
    delete v2.total.payerAmounts;
    expect(migrateEventV2(v2).total.payerAmounts).toBeNull();
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

describe('mode 2: several payers in one expense', () => {
  const trip = () => {
    let e = setMode(withPeople('Viaje', ['Ana', 'Bea', 'Carlos']), 'itemised', NOW);
    const all = ['ana', 'bea', 'carlos'];
    e = upsertExpense(
      e,
      { id: 'h', description: 'Hotel', amountCents: 30000, payerId: '', payerAmounts: { ana: 20000, bea: 10000 }, participantIds: all },
      NOW,
    );
    return upsertExpense(e, { id: 'd', description: 'Cena', amountCents: 9000, payerId: 'carlos', participantIds: all }, NOW);
  };

  it('each payer is credited with their part', () => {
    const r = ok(trip());
    expect(r.totalCents).toBe(39000);
    expect(amounts(r)).toEqual({ Ana: 13000, Bea: 13000, Carlos: 13000 });
    expect(r.balances?.map((b) => [b.name, b.paidCents, b.netCents])).toEqual([
      ['Ana', 20000, 7000],
      ['Bea', 10000, -3000],
      ['Carlos', 9000, -4000],
    ]);
    expect(transfers(r)).toEqual([
      ['Carlos', 'Ana', 4000],
      ['Bea', 'Ana', 3000],
    ]);
  });

  it('skips the expense when the parts do not add up', () => {
    const e = upsertExpense(
      trip(),
      { id: 'x', description: 'Taxi', amountCents: 2000, payerId: '', payerAmounts: { ana: 500 }, participantIds: ['ana'] },
      NOW,
    );
    const r = ok(e);
    expect(r.skippedExpenseIds).toEqual(['x']);
    expect(r.totalCents).toBe(39000);
  });

  it('protects every payer of the expense from removal', () => {
    const e = trip();
    expect(canRemoveParticipant(e, 'bea')).toBe(false);
    expect(canRemoveParticipant(e, 'ana')).toBe(false);
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
    expect(e.total).toEqual({ amountCents: null, excludedIds: [], weights: {}, payerId: null, payerAmounts: null });
  });

  it('removal drops what they paid in "several payers" mode', () => {
    let e = setMultiplePayers(withPeople('x', ['Ana', 'Bea']), NOW);
    e = setPayerAmount(setPayerAmount(e, 'ana', 500, NOW), 'bea', 300, NOW);
    e = removeParticipant(e, 'bea', NOW);
    expect(e.total.payerAmounts).toEqual({ ana: 500 });
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
    expect(text.split('\n').slice(-2)).toEqual(['• Bea → Ana: 10,00 € ✅ pagado', '• Carlos → Ana: 10,00 €']);
  });

  it('lists what each payer paid when there are several', () => {
    let e = setMode(withPeople('Viaje', ['Ana', 'Bea']), 'itemised', NOW);
    e = upsertExpense(e, { id: 'h', description: 'Hotel', amountCents: 3000, payerId: 'ana', participantIds: ['ana', 'bea'] }, NOW);
    e = upsertExpense(e, { id: 'c', description: 'Cena', amountCents: 1000, payerId: 'bea', participantIds: ['ana', 'bea'] }, NOW);
    const text = buildShareText(e.title, ok(e));
    expect(text.split('\n')[2]).toBe('Pagado por: Ana (30,00 €), Bea (10,00 €)');
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
