import { useState, useEffect } from 'react';
import { TabBar } from './components/TabBar';
import { HomePage } from './pages/HomePage';
import { ProgressPage } from './pages/ProgressPage';
import { AstroPage } from './pages/AstroPage';
import { ProfilePage } from './pages/ProfilePage';
import './styles/global.css';

function App() {
  const [activeTab, setActiveTab] = useState('home');

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      try { tg.disableVerticalSwipes(); } catch {}
    }
  }, []);

  const renderPage = () => {
    switch (activeTab) {
      case 'home': return <HomePage />;
      case 'progress': return <ProgressPage />;
      case 'astro': return <AstroPage />;
      case 'profile': return <ProfilePage />;
      default: return <HomePage />;
    }
  };

  return (
    <div className="ambient-bg">
      {renderPage()}
      <TabBar active={activeTab} onNavigate={setActiveTab} />
    </div>
  );
}

export default App;
