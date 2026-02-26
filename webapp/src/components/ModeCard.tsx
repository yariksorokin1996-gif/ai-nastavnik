import './ModeCard.css';

interface ModeCardProps {
  icon: string;
  label: string;
  description: string;
  isActive?: boolean;
  onClick: () => void;
}

export function ModeCard({ icon, label, description, isActive, onClick }: ModeCardProps) {
  return (
    <button
      className={`mode-card ${isActive ? 'mode-card--active' : ''}`}
      onClick={onClick}
    >
      <span className="mode-card__icon">{icon}</span>
      <span className="mode-card__label">{label}</span>
      <span className="mode-card__desc">{description}</span>
    </button>
  );
}
