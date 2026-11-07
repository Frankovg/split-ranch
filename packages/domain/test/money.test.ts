import { describe, expect, it } from 'vitest';

import { formatAmount, parseMoney } from '../src';

describe('parseMoney', () => {
  it.each([
    ['12', 1200],
    ['12,5', 1250],
    ['12,50', 1250],
    ['12.50', 1250],
    ['0,01', 1],
    ['1.234,56', 123456],
    ['1,234.56', 123456],
    ['1.234', 123400],
    ['87,50 €', 8750],
    [' 3 ', 300],
  ])('parses %s', (input, expected) => {
    expect(parseMoney(input)).toBe(expected);
  });

  it.each(['', 'abc', '12,345,6', '1,2,3', '12.345,678', '-5', '1.23.4', '10000000,01'])(
    'rejects %s',
    (input) => {
      expect(parseMoney(input)).toBeNull();
    },
  );
});

describe('formatAmount', () => {
  it('formats with comma decimals in es-ES', () => {
    expect(formatAmount(2188)).toBe('21,88');
  });
});
