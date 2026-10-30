import { describe, expect, it, vi } from 'vitest';
import { json } from '../test/api';
import { DEFAULT_API_URL, apiBase } from './base';
import { ApiClient, ApiError } from './client';

const INIT = 'query_id=X&user=%7B%22id%22%3A1%7D&auth_date=1&hash=h';

function client(reply: Response | (() => Promise<Response>), onUnauthorized = vi.fn()) {
  const fetchImpl = vi.fn<typeof fetch>(typeof reply === 'function' ? reply : async () => reply.clone());
  const api = new ApiClient({ baseUrl: 'https://api.example/', initData: INIT, fetchImpl, onUnauthorized });
  return { api, fetchImpl, onUnauthorized };
}

async function failure(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(ApiError);
    return e as ApiError;
  }
  throw new Error('expected the request to fail');
}

describe('ApiClient requests', () => {
  it('sends the tma Authorization header and keeps initData out of the URL', async () => {
    const { api, fetchImpl } = client(json(200, { tg_id: 1, lang: 'ru', reminders: false }));
    await api.me();
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe('https://api.example/api/me');
    expect(String(url)).not.toContain('hash=');
    const headers = init!.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`tma ${INIT}`);
    expect(headers['Content-Type']).toBeUndefined();
    expect(init!.credentials).toBe('omit');
  });

  it('sends JSON bodies with a content type on writes', async () => {
    const { api, fetchImpl } = client(json(200, {}));
    await api.setMilestone(7, 'decision', '2025-06-01', true);
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe('https://api.example/api/cases/7/milestones/decision');
    expect(init!.method).toBe('PUT');
    expect((init!.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(JSON.parse(init!.body as string)).toEqual({ date: '2025-06-01', confirm_outlier: true });
  });

  it('omits confirm_outlier unless confirming', async () => {
    const { api, fetchImpl } = client(json(200, {}));
    await api.setMilestone(7, 'card', '2025-06-01');
    expect(JSON.parse(fetchImpl.mock.calls[0]![1]!.body as string)).toEqual({ date: '2025-06-01' });
  });

  it('builds query strings for meta, stats and share', async () => {
    const { api, fetchImpl } = client(json(200, {}));
    await api.meta('en');
    await api.stats('mazowieckie', { purposes: ['praca'] });
    await api.stats(null, { group: 'temporary' });
    await api.stats('slaskie', { purposes: ['praca', 'jdg'] });
    await api.shareStats({ purposes: ['jdg'] }, ['slaskie', 'pomorskie']);
    await api.shareStats({ group: 'temporary' }, ['all', 'slaskie']);
    const urls = fetchImpl.mock.calls.map((c) => String(c[0]));
    expect(urls).toEqual([
      'https://api.example/api/meta?lang=en',
      'https://api.example/api/stats?purpose=praca&voivodeship=mazowieckie',
      'https://api.example/api/stats?group=temporary',
      'https://api.example/api/stats?purpose=praca%2Cjdg&voivodeship=slaskie',
      'https://api.example/api/share/stats?purpose=jdg&voivodeships=slaskie%2Cpomorskie',
      'https://api.example/api/share/stats?group=temporary&voivodeships=all%2Cslaskie',
    ]);
  });

  it('returns undefined for 204', async () => {
    const { api } = client(json(204));
    await expect(api.deleteMe()).resolves.toBeUndefined();
  });

  it('defaults the base URL and trims trailing slashes', () => {
    expect(apiBase(undefined)).toBe(DEFAULT_API_URL);
    expect(apiBase('  ')).toBe(DEFAULT_API_URL);
    expect(apiBase('https://x.example///')).toBe('https://x.example');
  });
});

describe('ApiClient error mapping', () => {
  it('401 → unauthorized and notifies the app', async () => {
    const { api, onUnauthorized } = client(json(401, { error: 'unauthorized' }));
    const e = await failure(api.cases());
    expect(e.kind).toBe('unauthorized');
    expect(onUnauthorized).toHaveBeenCalledOnce();
    expect(e.message).not.toContain(INIT);
  });

  it('403 (page served from a foreign origin) → forbidden', async () => {
    const e = await failure(client(json(403, { error: 'forbidden' })).api.cases());
    expect(e.kind).toBe('forbidden');
  });

  it('404 → not_found', async () => {
    const e = await failure(client(json(404, { error: 'not_found' })).api.caseDetail(9));
    expect(e.kind).toBe('not_found');
  });

  it('409 outlier → outlier with typical range and value', async () => {
    const body = { error: 'outlier', typical: { p10: 30.5, p90: 90 }, value: 400 };
    const e = await failure(client(json(409, body)).api.setMilestone(1, 'decision', '2025-01-01'));
    expect(e.kind).toBe('outlier');
    expect(e.outlier).toEqual({ typical: { p10: 30.5, p90: 90 }, value: 400 });
  });

  it('409 other → conflict with the error code', async () => {
    const e = await failure(client(json(409, { error: 'too_many_cases' })).api.cases());
    expect(e.kind).toBe('conflict');
    expect(e.code).toBe('too_many_cases');
  });

  it('422 normalises fields and codes', async () => {
    const body = { error: 'invalid', fields: { filed: 'future', name: ['doc_name_long'] }, codes: ['order'] };
    const e = await failure(client(json(422, body)).api.cases());
    expect(e.kind).toBe('invalid');
    expect(e.fields).toEqual({ filed: ['future'], name: ['doc_name_long'] });
    expect(e.codes).toEqual(['order']);
  });

  it('429 → rate_limited with Retry-After', async () => {
    const e = await failure(client(json(429, { error: 'rate_limited' }, { 'Retry-After': '7' })).api.cases());
    expect(e.kind).toBe('rate_limited');
    expect(e.retryAfter).toBe(7);
  });

  it('5xx and non-JSON bodies → server', async () => {
    const e = await failure(client(new Response('<html>oops</html>', { status: 502 })).api.cases());
    expect(e.kind).toBe('server');
    expect(e.status).toBe(502);
  });

  it('a rejected fetch → network', async () => {
    const e = await failure(
      client(async () => {
        throw new TypeError('Failed to fetch');
      }).api.cases(),
    );
    expect(e.kind).toBe('network');
    expect(e.status).toBe(0);
  });
});
