import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, Users, Calendar, Trophy, Clock } from 'lucide-react';

// Компонент навигационной шапки
export const NavigationHeader = ({ title, showBack = true, onBack }) => {
  const navigate = useNavigate();
  
  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      navigate(-1);
    }
  };
  
  return (
    <div className="nav-header">
      {showBack && (
        <button className="nav-back" onClick={handleBack}>
          <ChevronLeft size={24} />
        </button>
      )}
      <h1 className="nav-title">{title}</h1>
    </div>
  );
};

// Улучшенная карточка розыгрыша
export const RaffleCard = ({ raffle, onClick }) => {
  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'long',
      hour: '2-digit',
      minute: '2-digit'
    });
  };
  
  const getStatus = () => {
    if (raffle.is_completed) return { text: 'Завершен', class: 'status-completed' };
    if (raffle.is_active) return { text: 'Активен', class: 'status-active' };
    return { text: 'Ожидает', class: 'status-pending' };
  };
  
  const status = getStatus();
  
  return (
    <div className="card raffle-card" onClick={() => onClick(raffle.id)}>
      {raffle.photo_url && (
        <img 
          src={raffle.photo_url} 
          alt={raffle.title}
          className="raffle-image"
          onError={(e) => {
            e.target.style.display = 'none';
          }}
        />
      )}
      
      <div className="raffle-content">
        <div className="raffle-header">
          <h3 className="text-primary">{raffle.title}</h3>
          <span className={`status-badge ${status.class}`}>
            {status.text}
          </span>
        </div>
        
        <p className="text-secondary raffle-description">
          {raffle.description}
        </p>
        
        <div className="raffle-info">
          <div className="participants-count">
            <Users size={16} />
            <span>{raffle.participants_count || 0} участников</span>
          </div>
          
          <div className="raffle-date">
            <Calendar size={16} />
            <span>{formatDate(raffle.end_date)}</span>
          </div>
        </div>
        
        {raffle.prizes && (
          <div className="raffle-prizes">
            <Trophy size={16} />
            <span>{Object.keys(raffle.prizes).length} призов</span>
          </div>
        )}
      </div>
    </div>
  );
};

// Компонент таймера обратного отсчета
export const CountdownTimer = ({ endDate }) => {
  const [timeLeft, setTimeLeft] = React.useState('');
  
  React.useEffect(() => {
    const calculateTimeLeft = () => {
      const difference = new Date(endDate) - new Date();
      
      if (difference > 0) {
        const days = Math.floor(difference / (1000 * 60 * 60 * 24));
        const hours = Math.floor((difference / (1000 * 60 * 60)) % 24);
        const minutes = Math.floor((difference / 1000 / 60) % 60);
        const seconds = Math.floor((difference / 1000) % 60);
        
        let timeString = '';
        if (days > 0) timeString += `${days}д `;
        if (hours > 0) timeString += `${hours}ч `;
        if (minutes > 0) timeString += `${minutes}м `;
        timeString += `${seconds}с`;
        
        setTimeLeft(timeString);
      } else {
        setTimeLeft('Завершен');
      }
    };
    
    calculateTimeLeft();
    const timer = setInterval(calculateTimeLeft, 1000);
    
    return () => clearInterval(timer);
  }, [endDate]);
  
  return (
    <div className="countdown">
      <div className="countdown-label">
        <Clock size={20} />
        <span>До завершения розыгрыша:</span>
      </div>
      <div className="countdown-value">{timeLeft}</div>
    </div>
  );
};