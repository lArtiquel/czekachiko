import './styles.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { scrubLaunchHash } from './router';

const entry = scrubLaunchHash();

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App entry={entry} />
    </StrictMode>,
  );
}
