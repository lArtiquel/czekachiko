import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import type { CaseDetail } from '../api/types';
import { todayIso } from '../lib/dates';
import { mockApi } from '../test/api';
import { caseDetail } from '../test/fixtures';
import { installTelegram } from '../test/telegram';

const withDecision: CaseDetail = {
  ...caseDetail,
  dates: { ...caseDetail.dates, decision: '2025-09-01' },
  forecast: { ...caseDetail.forecast!, target: 'card' },
};

async function openCase(overrides: Parameters<typeof mockApi>[0] = {}, popupChoice: string | null = 'ok') {
  window.history.replaceState(null, '', '/#/case/7');
  const api = mockApi(overrides);
  const tg = installTelegram({ popupChoice });
  render(<App />);
  await screen.findByText('Wniosek');
  return { api, tg, user: userEvent.setup() };
}

describe('Case screen', () => {
  it('renders the timeline chain from the contract', async () => {
    await openCase();
    expect(screen.getByText('Mazowieckie · работа')).toBeInTheDocument();
    expect(screen.getByText('01.03.2025 · 50 дн.')).toBeInTheDocument();
    expect(screen.getByText('обычно: в среднем 61 дн. (мин 12, макс 140) (дел: 23)')).toBeInTheDocument();
    expect(screen.getByText('обычно: в среднем 301 дн. (мин 180, макс 420) (дел: 6)')).toBeInTheDocument();
    expect(screen.getByText('данных пока нет (дел: 0)')).toBeInTheDocument();
  });

  it('renders the forecast with its disclaimer', async () => {
    await openCase();
    expect(screen.getByText('Прогноз: decyzja')).toBeInTheDocument();
    expect(screen.getByText('обычно между 02.11.2025 и 30.04.2026, чаще всего около 15.01.2026')).toBeInTheDocument();
    expect(screen.getByText('по 11 завершённым делам (Mazowieckie, работа), которые ждали не меньше тебя')).toBeInTheDocument();
    expect(screen.getByText('быстрее всех: 120 дн. · дольше всех: 410 дн.')).toBeInTheDocument();
    expect(screen.getByText(/^ℹ️ Дата в письме urzędu — не прогноз/)).toBeInTheDocument();
  });

  it('renders documents, with the owner’s names as plain text', async () => {
    await openCase();
    expect(screen.getByText('📋 Документы · отправлено 2 из 4')).toBeInTheDocument();
    expect(screen.getByText('✅ Отправлен 10.01.2025')).toBeInTheDocument();
    expect(screen.getAllByText('⬜ Ещё не отмечен')).toHaveLength(2);
    expect(screen.getByText('<img src=x onerror=alert(1)> Zaświadczenie')).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByRole('checkbox', { name: 'Wniosek' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Zdjęcia' })).not.toBeChecked();
  });

  it('outlier: asks to check the dates, then retries with confirm_outlier', async () => {
    const { api, tg, user } = await openCase({
      'PUT /api/cases/7/milestones/decision': (call) =>
        (call.body as { confirm_outlier?: boolean }).confirm_outlier
          ? { body: withDecision }
          : { status: 409, body: { error: 'outlier', typical: { p10: 150.2, p90: 300 }, value: 104 } },
    });
    await user.click(screen.getByRole('button', { name: /^decyzja/ }));
    fireEvent.change(screen.getByLabelText('decyzja'), { target: { value: '2025-09-01' } });
    await tg.clickMain();

    await waitFor(() => expect(api.callsTo('PUT', '/api/cases/7/milestones/decision')).toHaveLength(2));
    const [first, second] = api.callsTo('PUT', '/api/cases/7/milestones/decision');
    expect(first!.body).toEqual({ date: '2025-09-01' });
    expect(second!.body).toEqual({ date: '2025-09-01', confirm_outlier: true });
    const popup = tg.webApp.showPopup.mock.calls[0]![0] as { title: string; message: string; buttons: { text: string }[] };
    expect(popup.title).toBe('Проверь даты');
    expect(popup.message).toContain('150–300 дней');
    expect(popup.message).toContain('104');
    expect(popup.buttons.map((b) => b.text)).toEqual(['✅ Всё верно', '✏️ Исправить']);
    await waitFor(() => expect(tg.mainButtonVisible()).toBe(false));
    expect(screen.getByText('01.09.2025 · 234 дн.')).toBeInTheDocument();
    expect(tg.webApp.HapticFeedback.notificationOccurred).toHaveBeenCalledWith('success');
  });

  it('outlier: "fix" keeps the editor open and sends nothing more', async () => {
    const { api, tg, user } = await openCase(
      {
        'PUT /api/cases/7/milestones/decision': {
          status: 409,
          body: { error: 'outlier', typical: { p10: 150, p90: 300 }, value: 104 },
        },
      },
      'fix',
    );
    await user.click(screen.getByRole('button', { name: /^decyzja/ }));
    fireEvent.change(screen.getByLabelText('decyzja'), { target: { value: '2025-09-01' } });
    await tg.clickMain();
    await waitFor(() => expect(tg.webApp.showPopup).toHaveBeenCalled());
    expect(api.callsTo('PUT', '/api/cases/7/milestones/decision')).toHaveLength(1);
    expect(screen.getByLabelText('decyzja')).toBeInTheDocument();
    expect(tg.mainButtonVisible()).toBe(true);
  });

  it('checks the milestone order locally', async () => {
    const { api, tg, user } = await openCase();
    await user.click(screen.getByRole('button', { name: /^decyzja/ }));
    fireEvent.change(screen.getByLabelText('decyzja'), { target: { value: '2025-04-01' } });
    await tg.clickMain();
    expect(screen.getByText('Порядок этапов нарушен: отпечатки сданы → decyzja → карта.')).toBeInTheDocument();
    expect(api.callsTo('PUT', '/api/cases/7/milestones/decision')).toHaveLength(0);
  });

  it('clears a milestone date', async () => {
    const cleared = { ...caseDetail, dates: { filed: '2025-01-10', fingerprints: '2025-05-20' } };
    const { api, user } = await openCase({ 'DELETE /api/cases/7/milestones/case_number': { body: cleared } });
    await user.click(screen.getByRole('button', { name: /^номер дела/ }));
    await user.click(screen.getByRole('button', { name: '🗑 Убрать дату' }));
    await waitFor(() => expect(api.callsTo('DELETE', '/api/cases/7/milestones/case_number')).toHaveLength(1));
  });

  it('ticks a standard document with today’s date', async () => {
    const { api, user } = await openCase({ 'PUT /api/cases/7/documents/std/zdjecia': { body: caseDetail } });
    await user.click(screen.getByRole('checkbox', { name: 'Zdjęcia' }));
    await waitFor(() => expect(api.callsTo('PUT', '/api/cases/7/documents/std/zdjecia')).toHaveLength(1));
    expect(api.callsTo('PUT', '/api/cases/7/documents/std/zdjecia')[0]!.body).toEqual({ date: todayIso() });
  });

  it('adds, renames and deletes the owner’s own documents', async () => {
    const { api, tg, user } = await openCase({
      'POST /api/cases/7/documents': { status: 201, body: caseDetail },
      'PATCH /api/cases/7/documents/205': { body: caseDetail },
      'DELETE /api/cases/7/documents/205': { body: caseDetail },
    });

    await user.click(screen.getByRole('button', { name: '➕ Добавить документ' }));
    await user.type(screen.getByLabelText('Название документа'), '   ');
    await tg.clickMain();
    expect(screen.getByText('Название пустое. Напиши, как называется документ.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Название документа'), '  Umowa   najmu ');
    await tg.clickMain();
    await waitFor(() => expect(api.callsTo('POST', '/api/cases/7/documents')).toHaveLength(1));
    expect(api.callsTo('POST', '/api/cases/7/documents')[0]!.body).toEqual({ name: 'Umowa najmu', date: null });

    await user.click(screen.getByRole('button', { name: '<img src=x onerror=alert(1)> Zaświadczenie' }));
    const name = screen.getByLabelText('Название документа');
    await user.clear(name);
    await user.type(name, 'Zaświadczenie o niekaralności');
    await tg.clickMain();
    await waitFor(() => expect(api.callsTo('PATCH', '/api/cases/7/documents/205')).toHaveLength(1));
    expect(api.callsTo('PATCH', '/api/cases/7/documents/205')[0]!.body).toEqual({
      name: 'Zaświadczenie o niekaralności',
      date: '2025-02-01',
    });

    await user.click(screen.getByRole('button', { name: '<img src=x onerror=alert(1)> Zaświadczenie' }));
    await user.click(screen.getByRole('button', { name: '🗑 Удалить' }));
    expect(tg.webApp.showConfirm).toHaveBeenCalledWith(
      'Удалить «<img src=x onerror=alert(1)> Zaświadczenie» из списка?',
      expect.any(Function),
    );
    await waitFor(() => expect(api.callsTo('DELETE', '/api/cases/7/documents/205')).toHaveLength(1));
  });

  it('sends the case to a chat via inline mode', async () => {
    const { tg, user } = await openCase({ 'GET /api/share/case/7': { body: { query: 'c:7' } } });
    await user.click(screen.getByRole('button', { name: '📤 Отправить в чат' }));
    await waitFor(() =>
      expect(tg.webApp.switchInlineQuery).toHaveBeenCalledWith('c:7', ['users', 'groups', 'channels']),
    );
  });

  it('deletes the case after confirmation and goes home', async () => {
    const { api, tg, user } = await openCase({ 'DELETE /api/cases/7': { status: 204 } });
    await user.click(screen.getByRole('button', { name: '🗑 Удалить дело' }));
    expect(tg.webApp.showConfirm).toHaveBeenCalledWith(
      'Удалить это дело? Его данные исчезнут из статистики и календаря.',
      expect.any(Function),
    );
    await waitFor(() => expect(window.location.hash).toBe('#/'));
    expect(api.callsTo('DELETE', '/api/cases/7')).toHaveLength(1);
  });
});
