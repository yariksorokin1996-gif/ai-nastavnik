import { useState, useEffect } from 'react';
import { AppRoot } from '@telegram-apps/telegram-ui';
import { Sparkles, TrendingUp, User } from 'lucide-react';
import { HomePage } from './pages/HomePage';
import { ProgressPage } from './pages/ProgressPage';
import { ProfilePage } from './pages/ProfilePage';

type Tab = 'home' | 'progress' | 'profile';

const INACTIVE = '#8A8A8E';
const ACTIVE = '#FF6B8A';

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('home');

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
    setActiveTab(tab);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
  };

  const renderPage = () => {
    switch (activeTab) {
      case 'home': return <HomePage />;
      case 'progress': return <ProgressPage />;
      case 'profile': return <ProfilePage />;
    }
  };

  return (
    <AppRoot appearance="light">
      <div className="page">
        {renderPage()}
      </div>

      <div className="tab-bar">
        <button
          className={`tab-item ${activeTab === 'home' ? 'tab-item--active' : ''}`}
          onClick={() => handleTab('home')}
        >
          <Sparkles size={24} color={activeTab === 'home' ? ACTIVE : INACTIVE} />
          <span className="tab-label">Сегодня</span>
        </button>
        <button
          className={`tab-item ${activeTab === 'progress' ? 'tab-item--active' : ''}`}
          onClick={() => handleTab('progress')}
        >
          <TrendingUp size={24} color={activeTab === 'progress' ? ACTIVE : INACTIVE} />
          <span className="tab-label">Мой путь</span>
        </button>
        <button
          className={`tab-item ${activeTab === 'profile' ? 'tab-item--active' : ''}`}
          onClick={() => handleTab('profile')}
        >
          <User size={24} color={activeTab === 'profile' ? ACTIVE : INACTIVE} />
          <span className="tab-label">Профиль</span>
        </button>
      </div>
    </AppRoot>
  );
}

export default App;
