import { AppRoot, Button, Placeholder } from '@telegram-apps/telegram-ui';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiBase } from './api/base';
import { ApiClient, isApiError } from './api/client';
import type { Lang, Meta } from './api/types';
import { AppContext, CaseCache, makeLabels, useApp, type AppServices } from './app/context';
import { Loading, LoadError } from './components/common';
import { LangContext, guessLang, translate, type Params } from './i18n';
import { errorMessage } from './lib/errors';
import { navigate, useRoute } from './router';
import { AddCase } from './screens/AddCase';
import { Calendars } from './screens/Calendars';
import { CaseScreen } from './screens/CaseScreen';
import { Home } from './screens/Home';
import { OutsideTelegram } from './screens/OutsideTelegram';
import { Settings } from './screens/Settings';
import { Stats } from './screens/Stats';
import { useBackButton, useColorScheme } from './telegram/hooks';
import { alertDialog, applyColorScheme, boot, getWebApp, haptic, type WebApp } from './telegram/webapp';

const API_URL = apiBase(import.meta.env.VITE_API_URL);

/** Telegram only: without signed initData there is nothing to show and nothing to call. */
export function App() {
  const tg = getWebApp();
  if (!tg || !tg.initData) return <OutsideTelegram />;
  return <TelegramApp tg={tg} />;
}

type BootState =
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'ready'; lang: Lang; meta: Meta };

function TelegramApp({ tg }: { tg: WebApp }) {
  const scheme = useColorScheme(tg);
  useEffect(() => applyColorScheme(scheme), [scheme]);
  const [authFailed, setAuthFailed] = useState(false);
  const api = useMemo(
    () => new ApiClient({ baseUrl: API_URL, initData: tg.initData, onUnauthorized: () => setAuthFailed(true) }),
    [tg],
  );
  const guess = guessLang(tg.initDataUnsafe?.user?.language_code);
  const [state, setState] = useState<BootState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const cache = useMemo(() => new CaseCache(), []);

  useEffect(() => boot(tg), [tg]);

  useEffect(() => {
    let live = true;
    setState({ status: 'loading' });
    (async () => {
      // The saved language wins; Telegram's language_code is the fallback.
      const [me, guessedMeta] = await Promise.all([api.me(), api.meta(guess)]);
      const lang: Lang = me.lang === 'en' || me.lang === 'ru' ? me.lang : guess;
      const meta = lang === guess ? guessedMeta : await api.meta(lang);
      if (live) setState({ status: 'ready', lang, meta });
    })().catch((error: unknown) => {
      if (live) setState({ status: 'error', error });
    });
    return () => {
      live = false;
    };
  }, [api, guess, attempt]);

  const lang = state.status === 'ready' ? state.lang : guess;
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const changeLang = useCallback(
    async (next: Lang) => {
      const [, meta] = await Promise.all([api.updateMe({ lang: next }), api.meta(next)]);
      setState({ status: 'ready', lang: next, meta });
    },
    [api],
  );

  const services = useMemo<AppServices | null>(() => {
    if (state.status !== 'ready') return null;
    const t = (key: Parameters<typeof translate>[1], params?: Params) => translate(state.lang, key, params);
    return {
      tg,
      api,
      lang: state.lang,
      meta: state.meta,
      labels: makeLabels(state.meta),
      t,
      cache,
      changeLang,
      fail(err, params) {
        if (isApiError(err) && err.kind === 'unauthorized') return; // the re-open screen takes over
        haptic(tg, 'error');
        void alertDialog(tg, errorMessage(t, err, params));
      },
    };
  }, [state, tg, api, cache, changeLang]);

  let body;
  if (authFailed) body = <Reopen tg={tg} />;
  else if (state.status === 'loading') body = <Loading />;
  else if (state.status === 'error') body = <LoadError error={state.error} onRetry={() => setAttempt((n) => n + 1)} />;
  else
    body = (
      <AppContext.Provider value={services}>
        <Routes />
      </AppContext.Provider>
    );

  return (
    <LangContext.Provider value={lang}>
      <AppRoot appearance={scheme} className="app">
        {body}
      </AppRoot>
    </LangContext.Provider>
  );
}

const goHome = () => navigate('/');

function Routes() {
  const { tg } = useApp();
  const route = useRoute();
  const key = route.name === 'case' ? `case/${route.id}` : route.name;
  useBackButton(tg, route.name === 'home' ? null : goHome);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [key]);

  switch (route.name) {
    case 'add':
      return <AddCase key={key} />;
    case 'case':
      return <CaseScreen key={key} id={route.id} />;
    case 'stats':
      return <Stats key={key} />;
    case 'calendars':
      return <Calendars key={key} />;
    case 'settings':
      return <Settings key={key} />;
    default:
      return <Home key={key} />;
  }
}

function Reopen({ tg }: { tg: WebApp }) {
  return (
    <LangContext.Consumer>
      {(lang) => (
        <Placeholder
          header={translate(lang, 'reopen_title')}
          description={translate(lang, 'reopen_text')}
          action={
            <Button size="m" mode="bezeled" onClick={() => tg.close()}>
              {translate(lang, 'btn_close')}
            </Button>
          }
        />
      )}
    </LangContext.Consumer>
  );
}
