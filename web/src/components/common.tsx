import type { ReactNode } from 'react';
import { useT } from '../i18n';
import { errorMessage } from '../lib/errors';
import { Button, Placeholder, Spinner } from './ui';

export function Loading() {
  const t = useT();
  return (
    <div className="center" role="status" aria-live="polite">
      <Spinner />
      <span className="visually-hidden">{t('loading')}</span>
    </div>
  );
}

export function LoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const t = useT();
  return (
    <Placeholder
      mark="🐕"
      text={<p role="alert">{errorMessage(t, error)}</p>}
      action={
        <Button icon="refresh" onClick={onRetry}>
          {t('btn_retry')}
        </Button>
      }
    />
  );
}

export function PageTitle({ children, sub, aside }: { children: ReactNode; sub?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="page-title">
      <h1>{children}</h1>
      {sub || aside ? (
        <div className="page-sub">
          {sub ? <p>{sub}</p> : null}
          {aside}
        </div>
      ) : null}
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
