import { vi } from 'vitest';
import { cases, caseDetail, me, meta } from './fixtures';

export interface Call {
  method: string;
  path: string;
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

export type Reply = { status?: number; body?: unknown; headers?: Record<string, string> } | Response;
export type Route = Reply | ((call: Call, n: number) => Reply | Promise<Reply>);

export function json(status: number, body?: unknown, headers: Record<string, string> = {}): Response {
  if (status === 204) return new Response(null, { status });
  return new Response(JSON.stringify(body ?? null), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

function toResponse(r: Reply): Response {
  if (r instanceof Response) return r;
  return json(r.status ?? 200, r.body, r.headers);
}

/**
 * Stubs global fetch. Keys are "METHOD /path" without the query string. Unknown routes
 * answer 404 so a test notices unexpected calls.
 */
export function mockApi(overrides: Record<string, Route> = {}) {
  const routes: Record<string, Route> = {
    'GET /api/me': { body: me },
    'GET /api/meta': { body: meta },
    'GET /api/cases': { body: cases },
    [`GET /api/cases/${caseDetail.id}`]: { body: caseDetail },
    ...overrides,
  };
  const calls: Call[] = [];
  const counts: Record<string, number> = {};
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = (init?.method ?? 'GET').toUpperCase();
    const headers = { ...(init?.headers as Record<string, string> | undefined) };
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    const call: Call = { method, path: url.pathname, url: String(input), headers, body };
    calls.push(call);
    const key = `${method} ${url.pathname}`;
    counts[key] = (counts[key] ?? 0) + 1;
    const route = routes[key];
    if (route === undefined) return json(404, { error: 'not_found' });
    const reply = typeof route === 'function' ? await route(call, counts[key]!) : route;
    return toResponse(reply);
  });
  vi.stubGlobal('fetch', fetchMock);
  return {
    fetchMock,
    calls,
    callsTo: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path),
  };
}
