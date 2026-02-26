import './GoalCard.css';

interface GoalCardProps {
  icon: string;
  sphere: string;
  title: string;
  progress: number;
  currentStep: string;
  compact?: boolean;
}

export function GoalCard({ icon, sphere, title, progress, currentStep, compact }: GoalCardProps) {
  return (
    <div className={`goal-card ${compact ? 'goal-card--compact' : ''}`}>
      <div className="goal-card__header">
        <span className="goal-card__icon">{icon}</span>
        <span className="goal-card__sphere">{sphere}</span>
        <span className="goal-card__percent">{progress}%</span>
      </div>
      {!compact && <p className="goal-card__title">{title}</p>}
      <div className="goal-card__bar">
        <div className="goal-card__fill" style={{ width: `${progress}%` }} />
      </div>
      <p className="goal-card__step">{currentStep}</p>
    </div>
  );
}
