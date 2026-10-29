import { AppRoot, Placeholder } from '@telegram-apps/telegram-ui';
import { translate } from '../i18n';
import { BOT_URL } from '../telegram/webapp';

/** Shown in a normal browser. Makes no API calls: there is no Telegram identity to send. */
export function OutsideTelegram() {
  return (
    <AppRoot className="app">
      <Placeholder
        header={translate('ru', 'outside_title')}
        description={
          <>
            {translate('ru', 'outside_text')}
            <br />
            <span lang="en" className="hint">
              {translate('en', 'outside_title')}
            </span>
          </>
        }
        action={
          <a className="link-button" href={BOT_URL} rel="noopener noreferrer">
            {translate('ru', 'outside_link')}
          </a>
        }
      >
        <div className="hero" aria-hidden="true">
          🐕
        </div>
      </Placeholder>
    </AppRoot>
  );
}
