import React, { useEffect, useRef, useState } from 'react';

const WheelComponent = ({ participants, isSpinning, onComplete, currentPrize, predeterminedWinnerIndex }) => {
  const canvasRef = useRef(null);
  const angleRef = useRef(0);
  const velocityRef = useRef(0);
  const animationRef = useRef(null);
  const [currentParticipant, setCurrentParticipant] = useState(null);
  const selectedWinnerRef = useRef(null);
  const targetWinnerIndexRef = useRef(null);
  const easeProgressRef     = useRef(0);   // таймлайн анимации
  const animationStartTimeRef = useRef(0); // для плавного расчёта
  const initialAngleRef       = useRef(0); // угол в момент старта

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
    targetWinnerIndexRef.current = predeterminedWinnerIndex;
    startSpin();
  }
}, [isSpinning, participants, predeterminedWinnerIndex]);

 /**
 * Какой сектор сейчас под красной стрелкой
 * (стрелка смотрит на угол 3π/2 = 270°).
 */
const getCurrentSegmentIndex = () => {
  if (participants.length === 0) return -1;

  // угол колеса в диапазоне [0‥2π)
  const normalized = ((angleRef.current % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);

  // «угол, куда смотрит стрелка»  =  3π/2  −  угол колеса
  const pointerAngle = (3 * Math.PI / 2 - normalized + 2 * Math.PI) % (2 * Math.PI);

  const segmentAngle = (2 * Math.PI) / participants.length;
  return Math.floor(pointerAngle / segmentAngle);
};


 const updateCurrentParticipant = () => {
  const index = getCurrentSegmentIndex();
  if (index >= 0 && index < participants.length) {
    const participant = participants[index];
    if (!currentParticipant || participant.id !== currentParticipant.id) {
      console.log('Current participant:', participant.username || participant.first_name, 'Index:', index); // Для отладки
      setCurrentParticipant(participant);
    }
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

    // Update current participant display
    updateCurrentParticipant();
  };

  const startSpin = () => {
  if (participants.length === 0) return;

  selectedWinnerRef.current = null;   // стираем прошлый результат
  easeProgressRef.current   = 0;      // сброс анимации
  animationStartTimeRef.current = Date.now();
  initialAngleRef.current   = angleRef.current;

  if (targetWinnerIndexRef.current !== null &&
      targetWinnerIndexRef.current >= 0) {

    // вычисляем полный угол, чтобы сделать 5‑8 оборотов
    const segAngle = (2 * Math.PI) / participants.length;
    const centerOfTarget =
      targetWinnerIndexRef.current * segAngle + segAngle / 2;

    const fullTurns   = 5 + Math.random() * 3;   // 5–8 оборотов
    const totalRotate =
      fullTurns * 2 * Math.PI + (3 * Math.PI / 2 - centerOfTarget);

    velocityRef.current = totalRotate;           // «стартовая скорость»
  } else {
    velocityRef.current = (20 + Math.random() * 10) * 2 * Math.PI;
  }

  animate();
};


 const animate = () => {
  /* 1. плавное замедление (ease‑out‑quart) */
  const DURATION = 6500;                 // мс
  const STEP_MS  = 16;                   // ~60 FPS

  easeProgressRef.current += STEP_MS;
  const t          = Math.min(easeProgressRef.current / DURATION, 1);
  const easeQuart  = (x) => 1 - Math.pow(1 - x, 4);
  const eased      = easeQuart(t);

  /* 2. сдвигаем колесо и постепенно тормозим */
  angleRef.current += (velocityRef.current / DURATION) * STEP_MS;
  velocityRef.current *= 0.985;          // коэффициент торможения

  /* 3. в последние 10 % плавно «прижимаемся» к нужному сектору */
  if (targetWinnerIndexRef.current !== null && t > 0.9) {
    const seg = (2 * Math.PI) / participants.length;
    const mustBe =
      3 * Math.PI / 2 -
      (targetWinnerIndexRef.current * seg + seg / 2);

    const now = ((angleRef.current % (2 * Math.PI)) + 2 * Math.PI) %
                (2 * Math.PI);

    angleRef.current += (mustBe - now) * 0.1;    // мягкая подгонка
  }

  /* 4. рисуем и обновляем подпись */
  drawWheel();
  updateCurrentParticipant();

  if (velocityRef.current > 0.05) {
    animationRef.current = requestAnimationFrame(animate);
  } else {
    /* финальный «щёлк» точно на сектор */
    if (targetWinnerIndexRef.current !== null) {
      const seg = (2 * Math.PI) / participants.length;
      angleRef.current =
        3 * Math.PI / 2 -
        (targetWinnerIndexRef.current * seg + seg / 2);
    }

    const wi = getCurrentSegmentIndex();
    const winner = participants[wi];
    onComplete && onComplete(winner);
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