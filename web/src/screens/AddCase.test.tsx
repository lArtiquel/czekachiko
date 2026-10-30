import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { todayIso } from '../lib/dates';
import { mockApi, type Call } from '../test/api';
import { cases, legacyMeta } from '../test/fixtures';
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

  it('offers three filing channels; in person, fingerprints at filing start switched on', async () => {
    const { api, tg, user } = await openForm({ 'POST /api/cases': { status: 201, body: cases[0] } });
    const channels = screen.getByRole('radiogroup', { name: 'Как подавал?' });
    expect(within(channels).getAllByRole('radio').map((r) => (r as HTMLInputElement).value)).toEqual([
      'in_person',
      'post',
      'mos',
    ]);
    expect(screen.queryByLabelText('Отпечатки сдал(а) при подаче')).not.toBeInTheDocument();

    await fillValid(user);
    await user.click(screen.getByLabelText('Лично в urzędzie'));
    const toggle = screen.getByLabelText('Отпечатки сдал(а) при подаче');
    expect(toggle).toBeChecked();
    await tg.clickMain();
    await waitFor(() => expect(api.callsTo('POST', '/api/cases')).toHaveLength(1));
    expect(api.callsTo('POST', '/api/cases')[0]!.body).toMatchObject({
      channel: 'in_person',
      fingerprints_at_filing: true,
    });
  });

  it('the fingerprints toggle can be switched off, and leaves with the channel', async () => {
    const { api, tg, user } = await openForm({ 'POST /api/cases': { status: 201, body: cases[0] } });
    await fillValid(user);
    await user.click(screen.getByLabelText('Лично в urzędzie'));
    await user.click(screen.getByLabelText('Отпечатки сдал(а) при подаче'));
    expect(screen.getByLabelText('Отпечатки сдал(а) при подаче')).not.toBeChecked();
    await user.click(screen.getByLabelText('Почта или e-Doręczenia'));
    expect(screen.queryByLabelText('Отпечатки сдал(а) при подаче')).not.toBeInTheDocument();
    await user.click(screen.getByLabelText('Лично в urzędzie'));
    await user.click(screen.getByLabelText('Отпечатки сдал(а) при подаче')); // on again → off
    await tg.clickMain();
    await waitFor(() => expect(api.callsTo('POST', '/api/cases')).toHaveLength(1));
    expect(api.callsTo('POST', '/api/cases')[0]!.body).toMatchObject({
      channel: 'in_person',
      fingerprints_at_filing: false,
    });
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

  it('asks for the permit type first; temporary needs a basis, the others set it', async () => {
    const { api, tg, user } = await openForm({ 'POST /api/cases': { status: 201, body: cases[0] } });
    expect(screen.getByLabelText('Временный побыт (pobyt czasowy)')).toBeChecked();
    expect(screen.getByRole('radiogroup', { name: 'Основание' })).toBeInTheDocument();
    expect(screen.getByLabelText('Blue Card (Niebieska Karta UE)')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Постоянный побыт (pobyt stały)'));
    expect(screen.queryByRole('radiogroup', { name: 'Основание' })).not.toBeInTheDocument();
    await user.click(screen.getByLabelText('Поиск воеводства'));
    await user.click(screen.getByLabelText('Mazowieckie'));
    await user.click(screen.getByLabelText('Почта или e-Doręczenia'));
    fireEvent.change(screen.getByLabelText('Дата подачи wniosku'), { target: { value: '2025-03-14' } });
    await tg.clickMain();
    await waitFor(() => expect(api.callsTo('POST', '/api/cases')).toHaveLength(1));
    expect((api.callsTo('POST', '/api/cases')[0]!.body as { purpose: string }).purpose).toBe('staly');
  });

  it('offers the unknown basis under its own heading', async () => {
    const { api, tg, user } = await openForm({ 'POST /api/cases': { status: 201, body: cases[0] } });
    const types = screen.getByRole('radiogroup', { name: 'Тип разрешения' });
    await user.click(within(types).getByLabelText('Другое основание / не указано'));
    expect(screen.queryByRole('radiogroup', { name: 'Основание' })).not.toBeInTheDocument();
    await user.click(screen.getByLabelText('Mazowieckie'));
    await user.click(screen.getByLabelText('MOS (онлайн)'));
    fireEvent.change(screen.getByLabelText('Дата подачи wniosku'), { target: { value: '2025-03-14' } });
    await tg.clickMain();
    await waitFor(() => expect(api.callsTo('POST', '/api/cases')).toHaveLength(1));
    expect((api.callsTo('POST', '/api/cases')[0]!.body as { purpose: string }).purpose).toBe('nieznane');
  });

  it('switching back to temporary clears the basis', async () => {
    const { api, tg, user } = await openForm();
    await user.click(screen.getByLabelText('Резидент ЕС (rezydent długoterminowy UE)'));
    await user.click(screen.getByLabelText('Временный побыт (pobyt czasowy)'));
    await tg.clickMain();
    expect(screen.getAllByText('Выбери вариант.')).toHaveLength(3);
    expect(api.callsTo('POST', '/api/cases')).toHaveLength(0);
  });

  it('shows the flat purpose list when the server has no permit types', async () => {
    const { api, tg, user } = await openForm({
      'GET /api/meta': { body: legacyMeta },
      'POST /api/cases': { status: 201, body: cases[0] },
    });
    expect(screen.queryByText('Тип разрешения')).not.toBeInTheDocument();
    expect(screen.getByRole('radiogroup', { name: 'Цель пребывания' })).toBeInTheDocument();
    await fillValid(user);
    await tg.clickMain();
    await waitFor(() => expect(window.location.hash).toBe('#/case/7'));
    expect((api.callsTo('POST', '/api/cases')[0]!.body as { purpose: string }).purpose).toBe('praca');
  });
});
