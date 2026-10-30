import { describe, expect, it } from 'vitest';
import { MIN_BAR_N, at, hasBar, labelStyle, sharedScale, stageScale } from './bars';

describe('stage bar scale', () => {
  it('runs from the fastest to the slowest case with a little padding, not from zero', () => {
    const s = stageScale(100, 200);
    expect(s.lo).toBeCloseTo(94);
    expect(s.hi).toBeCloseTo(206);
    expect(at(s, 100)).toBeGreaterThan(0);
    expect(at(s, 200)).toBeLessThan(100);
    expect(at(s, 150)).toBeCloseTo(50);
  });

  it('widens to take in the person’s own day or today when outside', () => {
    const s = stageScale(100, 200, [300]);
    expect(s.hi).toBeGreaterThan(300);
    expect(at(s, 300)).toBeLessThan(100);
    expect(stageScale(100, 200, [150])).toEqual(stageScale(100, 200));
    expect(stageScale(100, 200, [40]).lo).toBeLessThan(40);
  });

  it('pads a stage where every case took the same time', () => {
    const s = stageScale(120, 120);
    expect(s.hi - s.lo).toBeGreaterThan(0);
    expect(at(s, 120)).toBeCloseTo(50);
  });

  it('clamps positions into the bar', () => {
    const s = stageScale(100, 200);
    expect(at(s, -1000)).toBe(0);
    expect(at(s, 1000)).toBe(100);
  });

  it('shares one scale across rows that draw a bar', () => {
    const rows = [
      { n: 9, min: 12, max: 140 },
      { n: 6, min: 30, max: 200 },
      { n: 2, min: 1, max: 900 }, // too few cases: no bar, so it does not stretch the others
      null,
    ];
    expect(sharedScale(rows)).toEqual(stageScale(12, 200));
    expect(sharedScale([null])).toBeNull();
  });

  it('draws a bar only from five cases', () => {
    expect(MIN_BAR_N).toBe(5);
    expect(hasBar({ n: 5 })).toBe(true);
    expect(hasBar({ n: 4 })).toBe(false);
    expect(hasBar(null)).toBe(false);
  });

  it('keeps a label inside the bar however close to an end it sits', () => {
    expect(labelStyle(0)).toEqual({ left: '0%', transform: 'translateX(-0%)' });
    expect(labelStyle(50)).toEqual({ left: '50%', transform: 'translateX(-50%)' });
    expect(labelStyle(100)).toEqual({ left: '100%', transform: 'translateX(-100%)' });
  });
});
