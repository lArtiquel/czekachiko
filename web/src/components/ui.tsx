import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';
import { Icon, type IconName } from './icons';

/** Small building blocks styled in styles.css. Colours come from Telegram's theme. */

export function Page({ children }: { children: ReactNode }) {
  return <main className="page">{children}</main>;
}

export function Group({
  title,
  aside,
  footer,
  children,
  plain = false,
  className,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  /** No card surface: for controls that carry their own (segmented, fields, buttons). */
  plain?: boolean;
  className?: string;
}) {
  return (
    <section className={className ? `group ${className}` : 'group'}>
      {title || aside ? (
        <div className="group-head">
          {title ? <h2 className="group-title">{title}</h2> : null}
          {aside ? <span className="group-aside">{aside}</span> : null}
        </div>
      ) : null}
      {plain ? children : <div className="card">{children}</div>}
      {footer ? <div className="group-foot">{footer}</div> : null}
    </section>
  );
}

type Tone = 'accent' | 'danger' | 'default';

/** A full-width tappable row: icon tile, label, optional detail and a trailing glyph. */
export function RowButton({
  icon,
  tone = 'default',
  trailing = 'chevronRight',
  children,
  detail,
  after,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: IconName;
  tone?: Tone;
  trailing?: IconName | null;
  detail?: ReactNode;
  /** Short text before the trailing glyph, e.g. "change". */
  after?: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`row row-button tone-${tone}${icon ? ' has-tile' : ''}${className ? ` ${className}` : ''}`}
      {...rest}
    >
      {icon ? (
        <span className="tile" aria-hidden="true">
          <Icon name={icon} size={18} />
        </span>
      ) : null}
      <span className="row-main">
        <span className="row-title">{children}</span>
        {detail ? <span className="row-detail">{detail}</span> : null}
      </span>
      {after ? <span className="row-after">{after}</span> : null}
      {trailing ? <Icon name={trailing} size={18} className="row-trailing" /> : null}
    </button>
  );
}

type Variant = 'primary' | 'tinted' | 'plain' | 'danger';

export function Button({
  variant = 'tinted',
  icon,
  wide = false,
  small = false,
  children,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; icon?: IconName; wide?: boolean; small?: boolean }) {
  const cls = ['btn', `btn-${variant}`, wide ? 'btn-wide' : '', small ? 'btn-small' : '', className ?? '']
    .filter(Boolean)
    .join(' ');
  return (
    <button type="button" className={cls} {...rest}>
      {icon ? <Icon name={icon} size={small ? 16 : 18} /> : null}
      <span>{children}</span>
    </button>
  );
}

/** An icon-only button. `label` is its accessible name. */
export function IconButton({
  icon,
  label,
  className,
  ...rest
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> & { icon: IconName; label: string }) {
  return (
    <button type="button" className={className ? `icon-btn ${className}` : 'icon-btn'} aria-label={label} title={label} {...rest}>
      <Icon name={icon} size={18} />
    </button>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

export function Placeholder({
  mark,
  title,
  text,
  action,
}: {
  mark?: ReactNode;
  title?: ReactNode;
  text?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="placeholder">
      {mark ? (
        <div className="placeholder-mark" aria-hidden="true">
          {mark}
        </div>
      ) : null}
      {title ? <h1 className="placeholder-title">{title}</h1> : null}
      {text ? <div className="placeholder-text">{text}</div> : null}
      {action ? <div className="placeholder-action">{action}</div> : null}
    </div>
  );
}

/** A radio option as a list row. The label wraps the input, so the text names it. */
export function RadioRow({
  label,
  className,
  ...input
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { label: ReactNode }) {
  return (
    <label className={className ? `row choice ${className}` : 'row choice'}>
      <input type="radio" className="choice-input" {...input} />
      <span className="radio-mark" aria-hidden="true" />
      <span className="row-main">
        <span className="row-title">{label}</span>
      </span>
    </label>
  );
}

/** A themed checkbox: the native input stays focusable and carries the accessible name. */
export function Check(props: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  return (
    <span className="check">
      <input type="checkbox" className="check-input" {...props} />
      <span className="check-mark" aria-hidden="true">
        <Icon name="check" size={16} />
      </span>
    </span>
  );
}

/** A toggle chip backed by a checkbox. */
export function Chip({ label, ...input }: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { label: string }) {
  return (
    <label className={`chip${input.disabled ? ' is-disabled' : ''}`}>
      <input type="checkbox" className="chip-input" {...input} />
      <span className="chip-face">
        <Icon name="check" size={14} className="chip-check" />
        {label}
      </span>
    </label>
  );
}

export interface SegmentOption {
  value: string;
  label: string;
  lang?: string;
}

/** Two or three mutually exclusive options side by side, as radio inputs. */
export function Segmented({
  name,
  label,
  options,
  value,
  onChange,
  disabled,
}: {
  name: string;
  label: string;
  options: SegmentOption[];
  value: string | null;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <label key={o.value} className="segment">
          <input
            type="radio"
            className="segment-input"
            name={name}
            value={o.value}
            checked={value === o.value}
            disabled={disabled}
            onChange={() => onChange(o.value)}
          />
          <span className="segment-face" lang={o.lang}>
            {o.label}
          </span>
        </label>
      ))}
    </div>
  );
}

export function TextField({
  icon,
  invalid,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { icon?: IconName; invalid?: boolean }) {
  return (
    <div className={`field${invalid ? ' is-invalid' : ''}`}>
      {icon ? <Icon name={icon} size={18} className="field-icon" /> : null}
      <input className="field-input" aria-invalid={invalid || undefined} {...input} />
    </div>
  );
}

export function SelectField({ children, ...select }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="field field-select">
      <select className="field-input" {...select}>
        {children}
      </select>
      <Icon name="chevronDown" size={18} className="field-chevron" />
    </div>
  );
}

/** A thin progress bar. Decorative: the numbers are always in nearby text. */
export function Progress({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <span className="progress" aria-hidden="true">
      <span className="progress-fill" style={{ width: `${pct}%` }} />
    </span>
  );
}
