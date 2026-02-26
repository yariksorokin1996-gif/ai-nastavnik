import { createRoot } from 'react-dom/client';
import '@telegram-apps/telegram-ui/dist/styles.css';
import './styles/global.css';
import App from './App';

createRoot(document.getElementById('root')!).render(<App />);
