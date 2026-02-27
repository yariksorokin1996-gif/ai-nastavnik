import { createRoot } from 'react-dom/client';
import '@telegram-apps/telegram-ui/dist/styles.css';
import './styles/global.css';
import App from './App';

// Force light theme BEFORE React renders (prevents dark flash)
document.documentElement.style.setProperty('--tg-theme-bg-color', '#F2F2F7', 'important');
document.documentElement.style.setProperty('--tg-theme-text-color', '#000000', 'important');
document.documentElement.style.setProperty('--tg-theme-secondary-bg-color', '#FFFFFF', 'important');
document.documentElement.style.setProperty('--tg-theme-bottom-bar-bg-color', '#FFFFFF', 'important');
document.documentElement.style.setProperty('--tg-theme-header-bg-color', '#FFFFFF', 'important');
document.documentElement.style.setProperty('--tg-theme-button-color', '#FF6B8A', 'important');
document.documentElement.style.setProperty('--tg-theme-link-color', '#FF6B8A', 'important');
document.body.style.backgroundColor = '#F2F2F7';
document.body.style.color = '#000000';

createRoot(document.getElementById('root')!).render(<App />);
