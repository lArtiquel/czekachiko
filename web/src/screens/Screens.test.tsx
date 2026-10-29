import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { scrubLaunchHash } from '../router';
import { mockApi } from '../test/api';
import { meta, stats } from '../test/fixtures';
import { installTelegram } from '../test/telegram';

function open(hash: string, overrides: Parameters<typeof mockApi>[0] = {}) {
  window.history.replaceState(null, '', `/${hash}`);
  const api = mockApi(overrides);
  const tg = installTelegram();
  render(<App />);
  return { api, tg, user: userEvent.setup() };
}

describe('Home', () => {
  it('shows the case card with its forecast line and links out through Telegram', async () => {
    const { tg, user } = open('#/');
    expect(await screen.findByText(/decyzja: чаще всего около 15\.01\.2026/)).toBeInTheDocument();
    expect(screen.getByText(/📋 Документы: 2\/4/)).toBeInTheDocument();
    expect(tg.webApp.BackButton.show).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '✉️ Написать нам' }));
    expect(tg.webApp.openTelegramLink).toHaveBeenCalledWith('https://t.me/czekachiko_bot?start=feedback');
    expect(tg.webApp.close).toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '📣 Поделиться ботом' }));
    expect(tg.webApp.openTelegramLink).toHaveBeenCalledWith(
      'https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fczekachiko_bot',
    );
    await user.click(screen.getByRole('button', { name: /^Mazowieckie · работа/ }));
    expect(window.location.hash).toBe('#/case/7');
  });
});

describe('Settings', () => {
  it('switches the language and saves it with PATCH /api/me', async () => {
    const { api, tg, user } = open('#/settings', {
      'PATCH /api/me': { body: { tg_id: 42, lang: 'en', reminders: false } },
    });
    await user.click(await screen.findByLabelText('English'));
    expect(await screen.findByText('⚙️ Settings')).toBeInTheDocument();
    expect(api.callsTo('PATCH', '/api/me')[0]!.body).toEqual({ lang: 'en' });
    expect(api.calls.some((c) => c.url.endsWith('/api/meta?lang=en'))).toBe(true);
    expect(tg.webApp.HapticFeedback.notificationOccurred).toHaveBeenCalledWith('success');
  });

  it('explains how it works and what is stored', async () => {
    open('#/settings');
    expect(await screen.findByText(/^Добавь своё дело и отмечай этапы/)).toBeInTheDocument();
    expect(screen.getByText(/^Храню только Telegram ID/)).toBeInTheDocument();
  });

  it('deletes all data after confirmation', async () => {
    const { api, tg, user } = open('#/settings', { 'DELETE /api/me': { status: 204 } });
    await user.click(await screen.findByRole('button', { name: '🗑 Удалить все мои данные' }));
    await waitFor(() => expect(api.callsTo('DELETE', '/api/me')).toHaveLength(1));
    expect(tg.webApp.showConfirm).toHaveBeenCalledWith(
      'Удалить все твои дела и настройки? Это нельзя отменить.',
      expect.any(Function),
    );
    await waitFor(() => expect(window.location.hash).toBe('#/'));
  });

  it('does nothing when the deletion is not confirmed', async () => {
    const { api, tg, user } = open('#/settings');
    tg.state.confirm = false;
    await user.click(await screen.findByRole('button', { name: '🗑 Удалить все мои данные' }));
    expect(api.callsTo('DELETE', '/api/me')).toHaveLength(0);
  });
});

describe('Stats', () => {
  it('loads each picked voivodeship, caps the pick at six and shares the selection', async () => {
    const { api, tg, user } = open('#/stats', {
      'GET /api/stats': { body: stats },
      'GET /api/share/stats': { body: { query: 's:praca:6,5' } },
    });
    await user.click(await screen.findByLabelText('Mazowieckie'));
    await user.click(screen.getByLabelText('Małopolskie'));
    await user.click(screen.getByRole('button', { name: 'Готово' }));

    expect(await screen.findByText('Mazowieckie · работа')).toBeInTheDocument();
    expect(screen.getByText('Małopolskie · работа')).toBeInTheDocument();
    expect(screen.getAllByText('🖐 Сейчас на отпечатки вызывают подавшихся ≈ март 2025 – апрель 2025.')).toHaveLength(2);
    expect(screen.getAllByText('данных пока нет (дел: 0)')).toHaveLength(2);
    expect(api.callsTo('GET', '/api/stats').map((c) => new URL(c.url).searchParams.get('voivodeship'))).toEqual([
      'mazowieckie',
      'malopolskie',
    ]);

    await user.click(screen.getByRole('button', { name: '📤 Отправить в чат' }));
    await waitFor(() =>
      expect(tg.webApp.switchInlineQuery).toHaveBeenCalledWith('s:praca:6,5', ['users', 'groups', 'channels']),
    );
    const share = api.callsTo('GET', '/api/share/stats')[0]!;
    expect(new URL(share.url).searchParams.get('voivodeships')).toBe('mazowieckie,malopolskie');

    await user.click(screen.getByRole('button', { name: /Mazowieckie, Małopolskie/ }));
    for (const v of meta.voivodeships.slice(0, 5)) await user.click(screen.getByLabelText(v.label));
    expect(screen.getByText('Можно выбрать не больше 6')).toBeInTheDocument();
    expect(screen.getByLabelText('Zachodniopomorskie')).toBeDisabled();
  });
});

describe('Stats opened from inline mode', () => {
  const LAUNCH = '#/stats?tgWebAppData=query_id%3DTEST%26hash%3Ddeadbeef&tgWebAppVersion=8.0&tgWebAppPlatform=ios';

  async function pickAndShare(chatType?: 'private') {
    window.history.replaceState(null, '', `/${LAUNCH}`);
    const entry = scrubLaunchHash();
    const api = mockApi({
      'GET /api/stats': { body: stats },
      'GET /api/share/stats': { body: { query: 's:praca:6' } },
    });
    const tg = installTelegram(chatType ? { chatType } : {});
    render(<App entry={entry} />);
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText('Mazowieckie'));
    await user.click(screen.getByRole('button', { name: 'Готово' }));
    await user.click(await screen.findByRole('button', { name: '📤 Отправить в чат' }));
    await waitFor(() => expect(tg.webApp.switchInlineQuery).toHaveBeenCalled());
    return { api, tg, entry };
  }

  it('opens at #/stats without a back button and sends the card back into the same chat', async () => {
    const { tg, entry } = await pickAndShare();
    expect(entry).toBe('/stats');
    expect(window.location.hash).toBe('#/stats');
    expect(window.location.href).not.toContain('tgWebAppData');
    expect(tg.webApp.BackButton.show).not.toHaveBeenCalled();
    expect(tg.webApp.switchInlineQuery.mock.calls).toEqual([['s:praca:6']]);
  });

  it('opened at #/stats from a chat, it still asks which chat to send to', async () => {
    const { tg } = await pickAndShare('private');
    expect(tg.webApp.switchInlineQuery.mock.calls).toEqual([['s:praca:6', ['users', 'groups', 'channels']]]);
  });

  it('a normal launch keeps the back button on stats', async () => {
    open('#/stats');
    await screen.findByLabelText('Mazowieckie');
    expect(window.Telegram!.WebApp.BackButton.show).toHaveBeenCalled();
  });
});

describe('Calendars', () => {
  it('opens a voivodeship calendar with openLink', async () => {
    const url = 'https://calendar.google.com/calendar/embed?src=abc';
    const { tg, user } = open('#/calendars', {
      'GET /api/calendars': { body: [{ voivodeship: 'slaskie', label: 'Śląskie', url }] },
    });
    await user.click(await screen.findByRole('button', { name: /Śląskie/ }));
    expect(tg.webApp.openLink).toHaveBeenCalledWith(url);
  });
});
