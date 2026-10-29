import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { todayIso } from '../lib/dates';
import { mockApi, type Call } from '../test/api';
import { cases } from '../test/fixtures';
import { installTelegram } from '../test/telegram';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

async function openForm(overrides: Parameters<typeof mockApi>[0] = {}) {
  window.history.replaceState(null, '', '/#/add');
  const api = mockApi(overrides);
  const tg = installTelegram();
  render(<App />);
  await screen.findByText('В каком воеводстве подано дело?');
  return { api, tg, user: userEvent.setup() };
}

async function fillValid(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Поиск воеводства'), 'krak');
  expect(screen.queryByLabelText('Mazowieckie')).not.toBeInTheDocument();
  await user.click(screen.getByLabelText('Małopolskie'));
  await user.click(screen.getByLabelText('Работа (art. 114)'));
  await user.click(screen.getByLabelText('MOS (онлайн)'));
  fireEvent.change(screen.getByLabelText('Дата подачи wniosku'), { target: { value: '2025-03-14' } });
}

describe('Add case', () => {
  it('uses Telegram buttons: back to home, main button to save', async () => {
    const { tg } = await openForm();
    expect(tg.webApp.BackButton.show).toHaveBeenCalled();
    expect(tg.mainButtonVisible()).toBe(true);
    expect(tg.webApp.MainButton.setParams).toHaveBeenCalledWith(expect.objectContaining({ text: 'Сохранить' }));
  });

  it('bounds the native date input to 2015-01-01 … today', async () => {
    await openForm();
    const input = screen.getByLabelText('Дата подачи wniosku');
    expect(input).toHaveAttribute('type', 'date');
    expect(input).toHaveAttribute('min', '2015-01-01');
    expect(input).toHaveAttribute('max', todayIso());
  });

  it('tapping the empty filing date starts it at today; the clear button sits beside it', async () => {
    const { user } = await openForm();
    const input = screen.getByLabelText('Дата подачи wniosku');
    fireEvent.focus(input);
    expect(input).toHaveValue(todayIso());
    const clear = screen.getByRole('button', { name: 'Очистить дату' });
    expect(clear.closest('.date-row')).toBe(input.closest('.date-row'));
    await user.click(clear);
    expect(input).toHaveValue('');
  });

  it('shows inline errors for missing fields and sends nothing', async () => {
    const { api, tg } = await openForm();
    await tg.clickMain();
    expect(screen.getAllByText('Выбери вариант.')).toHaveLength(3);
    expect(screen.getByText('Укажи дату.')).toBeInTheDocument();
    expect(api.callsTo('POST', '/api/cases')).toHaveLength(0);
    expect(tg.webApp.HapticFeedback.notificationOccurred).toHaveBeenCalledWith('error');
  });

  it('rejects a future filing date before calling the API', async () => {
    const { api, tg, user } = await openForm();
    await fillValid(user);
    fireEvent.change(screen.getByLabelText('Дата подачи wniosku'), { target: { value: '2999-01-01' } });
    await tg.clickMain();
    expect(screen.getByText('Эта дата ещё не наступила. Выбери прошедший день.')).toBeInTheDocument();
    expect(api.callsTo('POST', '/api/cases')).toHaveLength(0);
  });

  it('saves with a client token, then opens the new case', async () => {
    const { api, tg, user } = await openForm({ 'POST /api/cases': { status: 201, body: cases[0] } });
    await fillValid(user);
    expect(screen.getByText('Małopolskie')).toBeInTheDocument(); // the list collapsed to the choice
    await tg.clickMain();
    await waitFor(() => expect(window.location.hash).toBe('#/case/7'));
    const [post] = api.callsTo('POST', '/api/cases');
    expect(post!.body).toEqual({
      voivodeship: 'malopolskie',
      purpose: 'praca',
      channel: 'mos',
      filed: '2025-03-14',
      client_token: expect.stringMatching(UUID),
    });
    expect(tg.webApp.HapticFeedback.notificationOccurred).toHaveBeenCalledWith('success');
  });

  it('a double tap sends one request, and a retry reuses the same token', async () => {
    let release: (() => void) | undefined;
    let n = 0;
    const { api, tg, user } = await openForm({
      'POST /api/cases': async (_c: Call) => {
        n += 1;
        if (n === 1) throw new TypeError('offline');
        await new Promise<void>((r) => (release = r));
        return { status: 201, body: cases[0] };
      },
    });
    await fillValid(user);
    await tg.clickMain(); // network error
    expect(tg.webApp.showAlert).toHaveBeenCalledWith(expect.stringContaining('Нет связи'), expect.any(Function));
    await tg.clickMain(); // second attempt, held open
    await tg.clickMain(); // double tap while in flight
    expect(api.callsTo('POST', '/api/cases')).toHaveLength(2);
    release?.();
    await waitFor(() => expect(window.location.hash).toBe('#/case/7'));
    const tokens = api.callsTo('POST', '/api/cases').map((c) => (c.body as { client_token: string }).client_token);
    expect(tokens[0]).toBe(tokens[1]);
  });

  it('maps server field errors inline', async () => {
    const { tg, user } = await openForm({
      'POST /api/cases': { status: 422, body: { error: 'invalid', fields: { filed: ['before_2015'] } } },
    });
    await fillValid(user);
    await tg.clickMain();
    expect(await screen.findByText('Дата подачи не может быть раньше 2015 года.')).toBeInTheDocument();
  });

  it('starts over with a new token if the server says it is taken', async () => {
    const { api, tg, user } = await openForm({
      'POST /api/cases': (_c: Call, n: number) =>
        n === 1
          ? { status: 422, body: { error: 'invalid', fields: { client_token: 'taken' } } }
          : { status: 201, body: cases[0] },
    });
    await fillValid(user);
    await tg.clickMain();
    expect(tg.webApp.showAlert).toHaveBeenCalledWith('Не получилось сохранить. Попробуй ещё раз.', expect.any(Function));
    await tg.clickMain();
    await waitFor(() => expect(window.location.hash).toBe('#/case/7'));
    const [a, b] = api.callsTo('POST', '/api/cases').map((c) => (c.body as { client_token: string }).client_token);
    expect(a).not.toBe(b);
  });

  it('explains the five-case limit', async () => {
    const { tg, user } = await openForm({ 'POST /api/cases': { status: 409, body: { error: 'too_many_cases' } } });
    await fillValid(user);
    await tg.clickMain();
    await waitFor(() =>
      expect(tg.webApp.showAlert).toHaveBeenCalledWith(expect.stringContaining('не больше 5 дел'), expect.any(Function)),
    );
  });
});
