import { useId } from 'react';
import type { IsoDate } from '../api/types';
import { useT } from '../i18n';
import { clampDate, todayIso } from '../lib/dates';
import { FieldError } from './common';
import { Icon } from './icons';
import { IconButton } from './ui';

export interface DateFieldProps {
  /** Accessible name; shown above the field unless `labelHidden`. */
  label: string;
  labelHidden?: boolean;
  /** A line of help between the label and the field. */
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  min?: IsoDate;
  max?: IsoDate;
  error?: string;
  /** Show the clear button to the right of the field. */
  clearable?: boolean;
  clearLabel?: string;
  /** Injected in tests; defaults to the device's date. */
  today?: IsoDate;
}

/**
 * The one date input in the app: the OS's own picker, themed for light and dark.
 *
 * - Opening an empty field fills in today, pulled into [min, max], so the picker starts there.
 * - The clear button sits to the right of the field on the same row.
 * - Validation messages appear under the field.
 */
export function DateField({
  label,
  labelHidden = false,
  hint,
  value,
  onChange,
  min,
  max,
  error,
  clearable = true,
  clearLabel,
  today,
}: DateFieldProps) {
  const t = useT();
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const empty = value === '';
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;

  const openEmpty = () => {
    if (empty) onChange(clampDate(today ?? todayIso(), min, max));
  };

  return (
    <div className="date-field">
      <label htmlFor={id} className={labelHidden ? 'visually-hidden' : 'field-label'}>
        {label}
      </label>
      {hint ? (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      <div className="date-row">
        <div className={`field date-box${empty ? ' is-empty' : ''}${error ? ' is-invalid' : ''}`}>
          <Icon name="calendar" size={18} className="field-icon" />
          <input
            id={id}
            type="date"
            className="field-input date-input"
            value={value}
            min={min}
            max={max}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            onFocus={openEmpty}
            onChange={(e) => onChange(e.target.value)}
          />
          {empty ? (
            <span className="date-placeholder" aria-hidden="true">
              {t('date_pick')}
            </span>
          ) : null}
        </div>
        {clearable ? (
          <IconButton
            icon="close"
            className="date-clear"
            label={clearLabel ?? t('btn_clear_date')}
            aria-disabled={empty || undefined}
            onClick={() => {
              if (!empty) onChange('');
            }}
          />
        ) : null}
      </div>
      <FieldError message={error} id={errorId} />
    </div>
  );
}
