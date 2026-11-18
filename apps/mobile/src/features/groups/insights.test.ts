import { describe, expect, it } from 'vitest';
import { buildPie, percentOf, REST_COLOR, REST_KEY } from './insights';

const total = (key: string, cents: number) => ({ key, label: key.toUpperCase(), cents });

describe('buildPie', () => {
  it('keeps every category as a slice when they fit, largest first', () => {
    const pie = buildPie(
      [total('a', 100), total('b', 300), total('none', 200)],
      ['a', 'b', 'none'],
      'Rest',
    );
    expect(pie.slices.map((s) => s.key)).toEqual(['b', 'none', 'a']);
    expect(pie.totalCents).toBe(600);
    expect(pie.rows).toHaveLength(3);
  });

  it('colours by category order, not by rank', () => {
    const order = ['a', 'b'];
    const march = buildPie([total('a', 100), total('b', 300)], order, 'Rest');
    const april = buildPie([total('a', 500), total('b', 300)], order, 'Rest');
    const color = (pie: typeof march, key: string) => pie.slices.find((s) => s.key === key)?.color;
    expect(color(march, 'a')).toBe('chart-1');
    expect(color(april, 'a')).toBe('chart-1');
    expect(color(march, 'b')).toBe('chart-2');
  });

  it('folds everything past the fifth largest into one rest slice', () => {
    const keys = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];
    const pie = buildPie(
      keys.map((k, i) => total(k, (i + 1) * 100)),
      keys,
      'Rest',
    );
    expect(pie.slices).toHaveLength(6);
    const rest = pie.slices[5]!;
    expect(rest).toMatchObject({ key: REST_KEY, label: 'Rest', cents: 300, color: REST_COLOR });
    // The ranked list still shows each category, the folded ones in the rest colour.
    expect(pie.rows.map((r) => r.key)).toEqual(['g', 'f', 'e', 'd', 'c', 'b', 'a']);
    expect(pie.rows.slice(5).every((r) => r.color === REST_COLOR)).toBe(true);
    expect(new Set(pie.slices.slice(0, 5).map((s) => s.color)).size).toBe(5);
  });

  it('drops categories with nothing spent', () => {
    const pie = buildPie([total('a', 0), total('b', 100)], ['a', 'b'], 'Rest');
    expect(pie.slices.map((s) => s.key)).toEqual(['b']);
  });
});

describe('percentOf', () => {
  it('rounds to whole percent and survives an empty total', () => {
    expect(percentOf(1, 3)).toBe(33);
    expect(percentOf(5, 0)).toBe(0);
  });
});
