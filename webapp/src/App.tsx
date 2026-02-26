import { useState, useEffect } from 'react';
import { AppRoot, Tabbar } from '@telegram-apps/telegram-ui';
import { Home, BarChart3, Sparkles, User } from 'lucide-react';
import { HomePage } from './pages/HomePage';
import { ProgressPage } from './pages/ProgressPage';
import { AstroPage } from './pages/AstroPage';
import { ProfilePage } from './pages/ProfilePage';

type Tab = 'home' | 'progress' | 'astro' | 'profile';

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('home');

  useEffect(() => {
    // Force light theme via inline styles (highest CSS specificity)
    document.documentElement.style.setProperty('--tg-theme-bg-color', '#F2F2F7', 'important');
    document.documentElement.style.setProperty('--tg-theme-text-color', '#000000', 'important');
    document.documentElement.style.setProperty('--tg-theme-hint-color', '#8E8E93', 'important');
    document.documentElement.style.setProperty('--tg-theme-link-color', '#007AFF', 'important');
    document.documentElement.style.setProperty('--tg-theme-button-color', '#007AFF', 'important');
    document.documentElement.style.setProperty('--tg-theme-button-text-color', '#FFFFFF', 'important');
    document.documentElement.style.setProperty('--tg-theme-secondary-bg-color', '#FFFFFF', 'important');
    document.documentElement.style.setProperty('--tg-theme-header-bg-color', '#FFFFFF', 'important');
    document.documentElement.style.setProperty('--tg-theme-section-bg-color', '#FFFFFF', 'important');
    document.documentElement.style.setProperty('--tg-theme-section-header-text-color', '#8E8E93', 'important');
    document.documentElement.style.setProperty('--tg-theme-subtitle-text-color', '#8E8E93', 'important');
    document.documentElement.style.setProperty('--tg-theme-bottom-bar-bg-color', '#FFFFFF', 'important');
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
      case 'astro': return <AstroPage />;
      case 'profile': return <ProfilePage />;
    }
  };

  return (
    <AppRoot appearance="light">
      <div className="page">
        {renderPage()}
      </div>
      <Tabbar>
        <Tabbar.Item
          selected={activeTab === 'home'}
          text="Главная"
          onClick={() => handleTab('home')}
        >
          <Home size={24} />
        </Tabbar.Item>
        <Tabbar.Item
          selected={activeTab === 'progress'}
          text="Прогресс"
          onClick={() => handleTab('progress')}
        >
          <BarChart3 size={24} />
        </Tabbar.Item>
        <Tabbar.Item
          selected={activeTab === 'astro'}
          text="Астро"
          onClick={() => handleTab('astro')}
        >
          <Sparkles size={24} />
        </Tabbar.Item>
        <Tabbar.Item
          selected={activeTab === 'profile'}
          text="Профиль"
          onClick={() => handleTab('profile')}
        >
          <User size={24} />
        </Tabbar.Item>
      </Tabbar>
    </AppRoot>
  );
}

export default App;
