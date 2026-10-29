import { translate } from '../i18n';
import { BOT_URL } from '../telegram/webapp';

/** Shown in a normal browser. Makes no API calls: there is no Telegram identity to send. */
export function OutsideTelegram() {
  return (
    <div className="app">
      <div className="placeholder outside">
        <div className="brand-mark brand-mark-large" aria-hidden="true">
          🐕
        </div>
        <h1 className="placeholder-title">{translate('ru', 'outside_title')}</h1>
        <div className="placeholder-text">
          <p>{translate('ru', 'outside_text')}</p>
          <p lang="en" className="hint">
            {translate('en', 'outside_title')}
          </p>
        </div>
        <div className="placeholder-action">
          <a className="btn btn-primary" href={BOT_URL} rel="noopener noreferrer">
            <span>{translate('ru', 'outside_link')}</span>
          </a>
        </div>
      </div>
    </div>
  );
}
