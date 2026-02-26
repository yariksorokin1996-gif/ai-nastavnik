import { Home, BarChart3, Sparkles, User } from 'lucide-react';
import './TabBar.css';

interface TabBarProps {
  active: string;
  onNavigate: (tab: string) => void;
}

const tabs = [
  { id: 'home', label: 'Главная', icon: Home },
  { id: 'progress', label: 'Прогресс', icon: BarChart3 },
  { id: 'astro', label: 'Астро', icon: Sparkles },
  { id: 'profile', label: 'Профиль', icon: User },
];

export function TabBar({ active, onNavigate }: TabBarProps) {
  return (
    <nav className="tabbar">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = active === tab.id;
        return (
          <button
            key={tab.id}
            className={`tabbar-item ${isActive ? 'active' : ''}`}
            onClick={() => onNavigate(tab.id)}
          >
            <Icon size={24} strokeWidth={isActive ? 2 : 1.5} />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
