import React, { useEffect, useRef, useState } from 'react';

const WheelComponent = ({ participants, isSpinning, onComplete, currentPrize, socket, raffleId, wheelSpeed = 'fast' }) => {
  const canvasRef = useRef(null);
  const angleRef = useRef(0);
  const velocityRef = useRef(0);
  const animationRef = useRef(null);
  const [currentParticipant, setCurrentParticipant] = useState(null);
  const hasNotifiedRef = useRef(false);
  const lastNotificationTimeRef = useRef(0);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    
    // Set canvas size
    canvas.width = 500;
    canvas.height = 500;
    
    drawWheel();
    // Set initial participant
    updateCurrentParticipant();
  }, [participants]);

  useEffect(() => {
    if (isSpinning && participants.length > 0) {
      hasNotifiedRef.current = false; // Сброс флага
      velocityRef.current = 0; // Сброс скорости
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current); // Отмена предыдущей анимации
      }
      startSpin();
    }
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isSpinning, participants]);

  const getCurrentSegmentIndex = () => {
    if (participants.length === 0) return -1;

    // угол колеса в диапазоне [0‥2π)
    const normalized = ((angleRef.current % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);

    // «угол, куда смотрит стрелка»  =  3π/2  −  угол колеса
    const pointerAngle = (3 * Math.PI / 2 - normalized + 2 * Math.PI) % (2 * Math.PI);

    const segmentAngle = (2 * Math.PI) / participants.length;
    return Math.floor(pointerAngle / segmentAngle);
  };

  const updateCurrentParticipant = () => {
    const index = getCurrentSegmentIndex();
    if (index >= 0 && index < participants.length) {
      const participant = participants[index];
      setCurrentParticipant(participant);
    }
  };

  const drawWheel = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = 200;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (participants.length === 0) {
      // Draw empty wheel
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
      ctx.strokeStyle = '#e5e7eb';
      ctx.lineWidth = 3;
      ctx.stroke();
      
      ctx.fillStyle = '#6b7280';
      ctx.font = '16px Arial';
      ctx.textAlign = 'center';
      ctx.fillText('Нет участников', centerX, centerY);
      return;
    }

    // Draw wheel segments
    const segmentAngle = (2 * Math.PI) / participants.length;
    
    participants.forEach((participant, index) => {
      const startAngle = angleRef.current + (index * segmentAngle);
      const endAngle = startAngle + segmentAngle;
      
      // Draw segment
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.arc(centerX, centerY, radius, startAngle, endAngle);
      ctx.closePath();
      
      // Alternate colors with more vibrant palette
      const colors = ['#3B82F6', '#8B5CF6', '#10B981', '#F59E0B', '#EF4444', '#EC4899', '#14B8A6', '#6366F1'];
      ctx.fillStyle = colors[index % colors.length];
      ctx.fill();
      
      // Draw border
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 3;
      ctx.stroke();
      
      // Draw text
      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.rotate(startAngle + segmentAngle / 2);
      ctx.textAlign = 'left';
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 14px Arial';
      
      // Get display name
      const displayName = participant.username || 
                         `${participant.first_name || ''} ${participant.last_name || ''}`.trim() ||
                         'Участник';
      
      // Truncate long names
      const maxLength = 15;
      const truncatedName = displayName.length > maxLength 
        ? displayName.substring(0, maxLength - 3) + '...' 
        : displayName;
      
      ctx.fillText(truncatedName, radius * 0.3, 5);
      ctx.restore();
    });

    // Draw center circle
    ctx.beginPath();
    ctx.arc(centerX, centerY, 30, 0, 2 * Math.PI);
    ctx.fillStyle = '#1F2937';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Draw pointer triangle at top
    ctx.beginPath();
    ctx.moveTo(centerX - 20, 30);
    ctx.lineTo(centerX + 20, 30);
    ctx.lineTo(centerX, 60);
    ctx.closePath();
    ctx.fillStyle = '#EF4444';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.stroke();
  };

  const startSpin = () => {
    if (participants.length === 0) return;

    // Скорость в зависимости от настройки
    const speedSettings = {
      fast: { base: 0.3, random: 0.2, friction: 0.985 },
      medium: { base: 0.1, random: 0.066, friction: 0.990 },
      slow: { base: 0.05, random: 0.033, friction: 0.992 }
    };
    
    const settings = speedSettings[wheelSpeed] || speedSettings.fast;
    
    // Начальная скорость
    velocityRef.current = settings.base + Math.random() * settings.random;
    
    // Сохраняем коэффициент трения для анимации
    velocityRef.friction = settings.friction;

    animate();
  };

  const animate = () => {
    velocityRef.current *= velocityRef.friction || 0.985;
    angleRef.current += velocityRef.current;
    
    drawWheel();
    updateCurrentParticipant();

    if (velocityRef.current > 0.001) {
      animationRef.current = requestAnimationFrame(animate);
    } else {
      velocityRef.current = 0;
      
      if (!hasNotifiedRef.current && participants.length > 0) {
        hasNotifiedRef.current = true;
        
        drawWheel();
        updateCurrentParticipant();
        
        setTimeout(() => {
          const winnerIndex = getCurrentSegmentIndex();
          const winner = participants[winnerIndex];
          
          // Защита от множественных отправок
          const now = Date.now();
          if (now - lastNotificationTimeRef.current < 1000) {
            console.log('Skipping duplicate notification');
            return;
          }
          lastNotificationTimeRef.current = now;
          
          console.log('Wheel stopped. Winner:', winner);
          
          if (winner && socket && socket.readyState === WebSocket.OPEN && currentPrize) {
            const message = {
              type: 'winner_selected',
              winner: winner,
              position: currentPrize.position,
              prize: currentPrize.prize,
              timestamp: now,
              // Добавляем уникальный ID для дедупликации на сервере
              messageId: `${raffleId}_${currentPrize.position}_${now}`
            };
            console.log('Sending winner to server:', message);
            socket.send(JSON.stringify(message));
          }
          
          onComplete && onComplete(winner);
        }, 500);
      }
    }
  };

  return (
    <div className="relative flex flex-col items-center">
      {/* Current participant display */}
      {currentParticipant && participants.length > 0 && (
        <div className="mb-4 text-center">
          <p className="text-sm text-gray-600 mb-1">Сейчас под стрелкой:</p>
          <div className="bg-white rounded-lg shadow-lg px-6 py-3">
            <p className="text-xl font-bold text-gray-800">
              {currentParticipant.username || 
               `${currentParticipant.first_name || ''} ${currentParticipant.last_name || ''}`.trim()}
            </p>
          </div>
        </div>
      )}

      {/* Prize display */}
      {currentPrize && (
        <div className="mb-4 text-center">
          <div className="bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg shadow-lg px-6 py-3">
            <p className="text-sm opacity-90">Разыгрывается:</p>
            <p className="text-xl font-bold">{currentPrize.position} место - {currentPrize.prize}</p>
          </div>
        </div>
      )}

      {/* Wheel canvas */}
      <canvas 
        ref={canvasRef} 
        className="mx-auto" 
        style={{ maxWidth: '100%', height: 'auto' }}
      />
      
      {/* Status display */}
      <div className="mt-4 text-center">
        <p className="text-sm font-semibold text-gray-600">
          {isSpinning ? '🎰 Колесо вращается...' : '⏳ Ожидание розыгрыша...'}
        </p>
        {participants.length > 0 && (
          <p className="text-xs text-gray-500 mt-1">
            Участников: {participants.length}
          </p>
        )}
      </div>
    </div>
  );
};

export default WheelComponent;