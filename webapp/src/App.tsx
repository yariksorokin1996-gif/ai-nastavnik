import { useState, useEffect } from 'react';
import { AppRoot } from '@telegram-apps/telegram-ui';
import { Sparkles, TrendingUp, User } from 'lucide-react';
import { HomePage } from './pages/HomePage';
import { ProgressPage } from './pages/ProgressPage';
import { ProfilePage } from './pages/ProfilePage';
import { useUser } from './hooks/useUser';

type Tab = 'home' | 'progress' | 'profile';

const INACTIVE = '#6C6C70';
const ACTIVE = '#FF6B8A';

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('home');
  const [animating, setAnimating] = useState(false);
  const userState = useUser();

  useEffect(() => {
    // Force light theme via JS (highest priority)
    const vars: [string, string][] = [
      ['--tg-theme-bg-color', '#F2F2F7'],
      ['--tg-theme-text-color', '#000000'],
      ['--tg-theme-hint-color', '#6C6C70'],
      ['--tg-theme-link-color', '#FF6B8A'],
      ['--tg-theme-button-color', '#FF6B8A'],
      ['--tg-theme-button-text-color', '#FFFFFF'],
      ['--tg-theme-secondary-bg-color', '#FFFFFF'],
      ['--tg-theme-header-bg-color', '#FFFFFF'],
      ['--tg-theme-section-bg-color', '#FFFFFF'],
      ['--tg-theme-bottom-bar-bg-color', '#FFFFFF'],
    ];
    vars.forEach(([k, v]) => document.documentElement.style.setProperty(k, v, 'important'));
    document.body.style.backgroundColor = '#F2F2F7';
    document.body.style.color = '#000000';

    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      try { tg.disableVerticalSwipes(); } catch {}
      try { tg.setHeaderColor('#FFFFFF'); } catch {}
      try { tg.setBackgroundColor('#F2F2F7'); } catch {}
      try { tg.setBottomBarColor('#FFFFFF'); } catch {}
    }
  }, []);

  const handleTab = (tab: Tab) => {
    if (tab === activeTab) return;
    setAnimating(true);
    setActiveTab(tab);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    setTimeout(() => setAnimating(false), 250);
  };

  return (
    <AppRoot appearance="light">
      {/* Single .page container for correct flex layout + scroll */}
      <div className="page">
        <div style={{ display: activeTab === 'home' ? 'block' : 'none' }}>
          <div className={animating && activeTab === 'home' ? 'animate-in' : ''}>
            <HomePage userState={userState} />
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
    </AppRoot>
  );
}

export default App;
