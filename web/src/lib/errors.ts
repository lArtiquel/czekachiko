import { isApiError } from '../api/client';
import { isKey, type Params, type TFn } from '../i18n';

/** Message for one validation code, e.g. `future` → err_future; unknown codes get a generic line. */
export function codeMessage(t: TFn, code: string, params?: Params): string {
  const key = `err_${code}`;
  return isKey(key) ? t(key, params) : t('err_invalid');
}

/** A short, human message for any failure. */
export function errorMessage(t: TFn, err: unknown, params?: Params): string {
  if (!isApiError(err)) return t('err_server');
  switch (err.kind) {
    case 'network':
      return t('err_network');
    case 'rate_limited':
      return t('err_rate_limited');
    case 'unauthorized':
      return t('reopen_text');
    case 'forbidden':
      return t('err_forbidden');
    case 'not_found':
      return t('err_not_found');
    case 'invalid': {
      const code = err.codes[0] ?? Object.values(err.fields)[0]?.[0];
      return code ? codeMessage(t, code, params) : t('err_invalid');
    }
    default:
      return t('err_server');
  }
}

/** First 422 code per field, as messages. */
export function fieldErrors(t: TFn, err: unknown, params?: Params): Record<string, string> {
  if (!isApiError(err) || err.kind !== 'invalid') return {};
  const out: Record<string, string> = {};
  for (const [field, codes] of Object.entries(err.fields)) {
    if (codes[0]) out[field] = codeMessage(t, codes[0], params);
  }
  return out;
}
