import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { LangContext } from '../i18n';
import { todayIso } from '../lib/dates';
import { DateField, type DateFieldProps } from './DateField';

type HarnessProps = Partial<Omit<DateFieldProps, 'value' | 'onChange'>> & { initial?: string };

function Harness({ initial = '', ...props }: HarnessProps) {
  const [value, setValue] = useState(initial);
  return <DateField label="Дата отправки" {...props} value={value} onChange={setValue} />;
}

const input = () => screen.getByLabelText('Дата отправки');

describe('DateField', () => {
  it('is a native date input with min and max', () => {
    render(<Harness min="2015-01-01" max="2026-10-30" />);
    expect(input()).toHaveAttribute('type', 'date');
    expect(input()).toHaveAttribute('min', '2015-01-01');
    expect(input()).toHaveAttribute('max', '2026-10-30');
  });

  it('opening an empty field fills in today', () => {
    render(<Harness />);
    expect(input()).toHaveValue('');
    fireEvent.focus(input());
    expect(input()).toHaveValue(todayIso());
  });

  it('pulls today into the allowed range', () => {
    const { unmount } = render(<Harness today="2026-10-30" max="2026-01-31" />);
    fireEvent.focus(input());
    expect(input()).toHaveValue('2026-01-31');
    unmount();

    render(<Harness today="2026-10-30" min="2027-02-01" max="2027-12-31" />);
    fireEvent.focus(input());
    expect(input()).toHaveValue('2027-02-01');
  });

  it('leaves a date that is already set alone', () => {
    render(<Harness initial="2025-05-05" today="2026-10-30" />);
    fireEvent.focus(input());
    expect(input()).toHaveValue('2025-05-05');
  });

  it('shows a placeholder while empty', () => {
    render(<Harness />);
    expect(screen.getByText('Выбрать дату')).toBeInTheDocument();
    fireEvent.focus(input());
    expect(screen.queryByText('Выбрать дату')).not.toBeInTheDocument();
  });

  it('puts the clear button to the right of the field, on the same row, with a label', () => {
    render(<Harness initial="2025-05-05" />);
    const clear = screen.getByRole('button', { name: 'Очистить дату' });
    const row = clear.parentElement!;
    expect(row).toHaveClass('date-row');
    expect(row.contains(input())).toBe(true);
    // Same row, and after the field in reading order: right of it in a left-to-right layout.
    expect(input().compareDocumentPosition(clear) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(row.lastElementChild).toBe(clear);
  });

  it('clears the date, and does not refill it until the field is opened again', async () => {
    const user = userEvent.setup();
    render(<Harness initial="2025-05-05" />);
    const clear = screen.getByRole('button', { name: 'Очистить дату' });
    await user.click(clear);
    expect(input()).toHaveValue('');
    expect(clear).toHaveAttribute('aria-disabled', 'true');
    await user.click(clear);
    expect(input()).toHaveValue('');
    fireEvent.focus(input());
    expect(input()).toHaveValue(todayIso());
  });

  it('takes a custom clear label, translates the default and can hide the button', () => {
    const { unmount } = render(<Harness initial="2025-05-05" clearLabel="Убрать дату" />);
    expect(screen.getByRole('button', { name: 'Убрать дату' })).toBeInTheDocument();
    unmount();

    const en = render(
      <LangContext.Provider value="en">
        <Harness initial="2025-05-05" />
      </LangContext.Provider>,
    );
    expect(screen.getByRole('button', { name: 'Clear date' })).toBeInTheDocument();
    en.unmount();

    render(<Harness initial="2025-05-05" clearable={false} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('shows the validation message under the field and links it', () => {
    render(<Harness initial="2999-01-01" error="Эта дата ещё не наступила." hint="когда отправил" />);
    const message = screen.getByRole('alert');
    expect(message).toHaveTextContent('Эта дата ещё не наступила.');
    expect(input()).toHaveAttribute('aria-invalid', 'true');
    expect(input().getAttribute('aria-describedby')!.split(' ')).toContain(message.id);
    const row = input().closest('.date-row')!;
    expect(row.compareDocumentPosition(message) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(row.contains(message)).toBe(false);
    expect(screen.getByText('когда отправил')).toBeInTheDocument();
  });
});
