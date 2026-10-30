import type { Meta, Milestone } from '../api/types';
import type { Key, TFn } from '../i18n';

/**
 * Filing channels and the order milestones happen in for each. Mirrors
 * `CHANNEL_PATHS` in src/czekachiko/domain.py; the case timeline and the stats chain follow it.
 */
export const CHANNELS = ['in_person', 'post', 'mos'] as const;
export type Channel = (typeof CHANNELS)[number];

export interface PathStep {
  milestone: Milestone;
  /** May never happen: a call (wezwanie) in an in-person case. */
  optional?: boolean;
  /** Usually happens on the filing day: fingerprints at the counter. */
  atFiling?: boolean;
}

const CALLED: PathStep[] = [
  { milestone: 'filed' },
  { milestone: 'case_number' },
  { milestone: 'braki' },
  { milestone: 'fingerprints' },
  { milestone: 'decision' },
  { milestone: 'card' },
];

export const PATHS: Record<Channel, PathStep[]> = {
  in_person: [
    { milestone: 'filed' },
    { milestone: 'fingerprints', atFiling: true },
    { milestone: 'case_number' },
    { milestone: 'braki', optional: true },
    { milestone: 'decision' },
    { milestone: 'card' },
  ],
  post: CALLED,
  mos: CALLED,
};

export const isChannel = (code: string): code is Channel => (CHANNELS as readonly string[]).includes(code);

/** The channel's path; anything else (an imported `unknown`, an older server's value) gets the post path. */
export const pathOf = (channel: string): PathStep[] => (isChannel(channel) ? PATHS[channel] : PATHS.post);

/** The channel of the most recently added case, else post. */
export function defaultChannel(cases: { id: number; channel: string }[] | null): Channel {
  const latest = [...(cases ?? [])].sort((a, b) => b.id - a.id)[0];
  return latest && isChannel(latest.channel) ? latest.channel : 'post';
}

/** Servers from before the channel split list `mos` and `paper` and ignore `channel=` in stats. */
export const hasChannels = (meta: Meta) => meta.channels.some((c) => c.code === 'in_person');

const SHORT = { in_person: 'ch_short_in_person', post: 'ch_short_post', mos: 'ch_short_mos' } as const satisfies Record<
  Channel,
  Key
>;

/** Short name for tabs: «Лично», «Почта/e-Doręczenia», «MOS»; `fallback` for other codes. */
export const channelShort = (t: TFn, channel: string, fallback: string) =>
  isChannel(channel) ? t(SHORT[channel]) : fallback;

/** The short name inside a sentence: lowercased unless it is an acronym such as MOS. */
export const channelInText = (t: TFn, channel: string, fallback: string) => {
  const name = channelShort(t, channel, fallback);
  return /^\p{Lu}\p{Ll}/u.test(name) ? name.charAt(0).toLowerCase() + name.slice(1) : name;
};
