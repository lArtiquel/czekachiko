import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { mockApi } from './test/api';
import { FAKE_INIT_DATA, installTelegram } from './test/telegram';

describe('Telegram-only gate', () => {
  it('outside Telegram: shows the open-in-Telegram screen and calls nothing', () => {
    const api = mockApi();
    render(<App />);
    expect(screen.getByText('Откройте Czekachiko в Telegram')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /czekachiko_bot/ })).toHaveAttribute('href', 'https://t.me/czekachiko_bot');
    expect(api.fetchMock).not.toHaveBeenCalled();
  });

  it('Telegram script loaded but no initData (plain browser): same screen, no calls', () => {
    const api = mockApi();
    installTelegram({ initData: '' });
    render(<App />);
    expect(screen.getByText('Откройте Czekachiko в Telegram')).toBeInTheDocument();
    expect(api.fetchMock).not.toHaveBeenCalled();
  });

  it('inside Telegram: boots, authenticates with initData and shows home', async () => {
    const api = mockApi();
    const tg = installTelegram();
    render(<App />);
    expect(await screen.findByText('Mazowieckie · работа')).toBeInTheDocument();
    expect(tg.webApp.ready).toHaveBeenCalled();
    expect(tg.webApp.expand).toHaveBeenCalled();
    expect(api.calls.length).toBeGreaterThan(0);
    for (const call of api.calls) {
      expect(call.headers.Authorization).toBe(`tma ${FAKE_INIT_DATA}`);
      expect(call.url).not.toContain(FAKE_INIT_DATA);
    }
    expect(screen.queryByText('Откройте Czekachiko в Telegram')).not.toBeInTheDocument();
  });

  it('a 401 replaces the app with a re-open hint', async () => {
    mockApi({ 'GET /api/me': { status: 401, body: { error: 'unauthorized' } } });
    installTelegram();
    render(<App />);
    expect(await screen.findByText('Сессия устарела')).toBeInTheDocument();
  });

  it('uses the saved language from /api/me', async () => {
    mockApi({ 'GET /api/me': { body: { tg_id: 42, lang: 'en', reminders: false } } });
    installTelegram({ languageCode: 'ru' });
    render(<App />);
    // Section headers re-create their <h1> on each render, so check a stable button instead.
    expect(await screen.findByText('📊 Timelines by voivodeship')).toBeInTheDocument();
    expect(screen.getByText('📂 My cases')).toBeInTheDocument();
  });
});
