import { describe, expect, it } from 'vitest';
import { MILESTONES } from '../api/types';
import { CHANNELS, PATHS, defaultChannel, hasChannels, pathOf } from './channels';
import { legacyMeta, meta } from '../test/fixtures';

describe('filing channels', () => {
  it('offers the three channels the API takes, in picker order', () => {
    expect(CHANNELS).toEqual(['in_person', 'post', 'mos']);
  });

  it('in person: fingerprints at filing, the call is optional', () => {
    const path = PATHS.in_person;
    expect(path.map((s) => s.milestone)).toEqual(['filed', 'fingerprints', 'case_number', 'braki', 'decision', 'card']);
    expect(path.filter((s) => s.atFiling).map((s) => s.milestone)).toEqual(['fingerprints']);
    expect(path.filter((s) => s.optional).map((s) => s.milestone)).toEqual(['braki']);
  });

  it('post and MOS: a call, then fingerprints', () => {
    for (const c of ['post', 'mos'] as const) {
      expect(PATHS[c].map((s) => s.milestone)).toEqual([...MILESTONES]);
      expect(PATHS[c].some((s) => s.optional || s.atFiling)).toBe(false);
    }
  });

  it('anything else (unknown, a legacy value) gets the post path', () => {
    expect(pathOf('unknown')).toBe(PATHS.post);
    expect(pathOf('paper')).toBe(PATHS.post);
    expect(pathOf('in_person')).toBe(PATHS.in_person);
  });

  it('defaults to the latest case’s channel, else post', () => {
    const c = (id: number, channel: string) => ({ id, channel });
    expect(defaultChannel([c(1, 'mos'), c(4, 'in_person'), c(2, 'post')])).toBe('in_person');
    expect(defaultChannel([c(3, 'unknown')])).toBe('post');
    expect(defaultChannel([])).toBe('post');
    expect(defaultChannel(null)).toBe('post');
  });

  it('knows whether the server splits by channel', () => {
    expect(hasChannels(meta)).toBe(true);
    expect(hasChannels(legacyMeta)).toBe(false);
  });
});
