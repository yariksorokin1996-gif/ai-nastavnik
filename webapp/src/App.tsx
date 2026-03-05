import { useState, useEffect } from 'react';
import { AppRoot } from '@telegram-apps/telegram-ui';
import { Sparkles, TrendingUp, User } from 'lucide-react';
import { HomePage } from './pages/HomePage';
import { ProgressPage } from './pages/ProgressPage';
import { ProfilePage } from './pages/ProfilePage';
import { useUser } from './hooks/useUser';
import { useTheme } from './hooks/useTheme';
import { trackEvent } from './analytics';

type Tab = 'home' | 'progress' | 'profile';

const INACTIVE = '#6C6C70';
const ACTIVE = '#FF6B8A';
const IS_DEV = !window.Telegram?.WebApp?.initData;

const devWrapperStyle: React.CSSProperties = {
  maxWidth: 430,
  margin: '0 auto',
  minHeight: '100vh',
  boxShadow: '0 0 40px rgba(0,0,0,0.08)',
  position: 'relative' as const,
};

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('home');
  const [animating, setAnimating] = useState(false);
  const userState = useUser();
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      try { tg.disableVerticalSwipes(); } catch {}
    }
    trackEvent({ event_type: 'app_open' });
  }, []);

  const handleTab = (tab: Tab) => {
    if (tab === activeTab) return;
    setAnimating(true);
    setActiveTab(tab);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    trackEvent({ event_type: 'page_view', page: tab });
    setTimeout(() => setAnimating(false), 250);
  };

  return (
    <AppRoot appearance={theme}>
     <div style={IS_DEV ? devWrapperStyle : undefined}>
      {/* Single .page container for correct flex layout + scroll */}
      <div className="page">
        <div style={{ display: activeTab === 'home' ? 'block' : 'none' }}>
          <div className={animating && activeTab === 'home' ? 'animate-in' : ''}>
            <HomePage userState={userState} theme={theme} onToggleTheme={toggleTheme} />
          </div>
        </div>
        <div style={{ display: activeTab === 'progress' ? 'block' : 'none' }}>
          <div className={animating && activeTab === 'progress' ? 'animate-in' : ''}>
            <ProgressPage userState={userState} />
          </div>
        </div>
        <div style={{ display: activeTab === 'profile' ? 'block' : 'none' }}>
          <div className={animating && activeTab === 'profile' ? 'animate-in' : ''}>
            <ProfilePage userState={userState} />
          </div>
        </div>
      </div>

      <div className="tab-bar">
        <button
          className={`tab-item ${activeTab === 'home' ? 'tab-item--active' : ''}`}
          onClick={() => handleTab('home')}
        >
          <Sparkles
            size={24}
            color={activeTab === 'home' ? ACTIVE : INACTIVE}
            strokeWidth={activeTab === 'home' ? 2.5 : 1.5}
          />
          <span className="tab-label">Сегодня</span>
        </button>
        <button
          className={`tab-item ${activeTab === 'progress' ? 'tab-item--active' : ''}`}
          onClick={() => handleTab('progress')}
        >
          <TrendingUp
            size={24}
            color={activeTab === 'progress' ? ACTIVE : INACTIVE}
            strokeWidth={activeTab === 'progress' ? 2.5 : 1.5}
          />
          <span className="tab-label">Мой путь</span>
        </button>
        <button
          className={`tab-item ${activeTab === 'profile' ? 'tab-item--active' : ''}`}
          onClick={() => handleTab('profile')}
        >
          <User
            size={24}
            color={activeTab === 'profile' ? ACTIVE : INACTIVE}
            strokeWidth={activeTab === 'profile' ? 2.5 : 1.5}
          />
          <span className="tab-label">Профиль</span>
        </button>
      </div>
     </div>
    </AppRoot>
  );
}

export default App;
