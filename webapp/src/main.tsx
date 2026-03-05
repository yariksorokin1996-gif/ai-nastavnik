import { createRoot } from 'react-dom/client';
import '@telegram-apps/telegram-ui/dist/styles.css';
import './styles/global.css';
import App from './App';
import { getInitialTheme } from './hooks/useTheme';

// Set theme BEFORE React renders (prevents flash of wrong theme)
const initialTheme = getInitialTheme();
document.documentElement.setAttribute('data-theme', initialTheme);
document.body.style.backgroundColor = initialTheme === 'dark' ? '#1C1C1E' : '#F2F2F7';
document.body.style.color = initialTheme === 'dark' ? '#FFFFFF' : '#000000';

createRoot(document.getElementById('root')!).render(<App />);
