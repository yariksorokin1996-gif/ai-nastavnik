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
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      try { tg.disableVerticalSwipes(); } catch {}
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
    <AppRoot>
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
