import { Button, Cell, Placeholder, Spinner, Title } from '@telegram-apps/telegram-ui';
import type { KeyboardEvent, ReactNode } from 'react';
import { useT } from '../i18n';
import { errorMessage } from '../lib/errors';

export function Loading() {
  const t = useT();
  return (
    <div className="center" role="status" aria-live="polite">
      <Spinner size="l" />
      <span className="visually-hidden">{t('loading')}</span>
    </div>
  );
}

export function LoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const t = useT();
  return (
    <Placeholder
      header="🐕"
      description={errorMessage(t, error)}
      action={
        <Button size="m" mode="bezeled" onClick={onRetry}>
          {t('btn_retry')}
        </Button>
      }
    />
  );
}

export function PageTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <header className="page-title">
      <Title level="2" weight="1">
        {children}
      </Title>
      {sub ? <p className="hint">{sub}</p> : null}
    </header>
  );
}

export function FieldError({ message, id }: { message: string | undefined; id?: string }) {
  if (!message) return null;
  return (
    <div className="field-error" role="alert" id={id}>
      {message}
    </div>
  );
}

type CellProps = Parameters<typeof Cell>[0];

/** A tappable cell that is also reachable and usable from a keyboard. */
export function TapCell({ onClick, ...rest }: Omit<CellProps, 'onClick'> & { onClick: () => void }) {
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick();
    }
  };
  return <Cell role="button" tabIndex={0} onClick={onClick} onKeyDown={onKeyDown} {...rest} />;
}
