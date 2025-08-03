import React, { useRef, useEffect, useState, useCallback } from 'react';
import { gsap } from 'gsap';
import './SlotMachine.css';

const VISIBLE_ITEMS = 5;
const ITEM_MARGIN = 10; // 5px с каждой стороны

function getDuplicationFactor(speed, participantsLength) {
  const baseMap = {
    fast: 10,
    medium: 6,
    slow: 4,
  };
  const base = baseMap[speed] || baseMap.fast;
  const len = participantsLength || 1;
  const minFactor = Math.ceil((VISIBLE_ITEMS * 3) / len) + 2;
  return Math.max(base, minFactor);
}

const SlotMachineComponent = ({
  participants,
  isSpinning,
  onComplete,
  currentPrize,
  socket,
  raffleId,
  wheelSpeed = 'fast',
  targetWinnerIndex,
}) => {
  const slotRef = useRef(null);
  const stripRef = useRef(null);
  const containerRef = useRef(null);
  const [currentHighlight, setCurrentHighlight] = useState(null);
  const lastHighlightIdRef = useRef(null);
  const [itemWidth, setItemWidth] = useState(200);
  const hasNotifiedRef = useRef(false);
  const currentPrizeRef = useRef(null);
  const processedMessagesRef = useRef(new Set());
  const isSendingRef = useRef(false);
  const animationRef = useRef(null);

  // Более точный расчет ширины элемента
  useEffect(() => {
    function calculateItemWidth() {
      if (!containerRef.current) return;
      
      // Получаем реальную ширину контейнера
      const containerWidth = containerRef.current.offsetWidth;
      
      // Учитываем padding контейнера
      const containerStyle = window.getComputedStyle(containerRef.current);
      const containerPadding = parseFloat(containerStyle.paddingLeft) + parseFloat(containerStyle.paddingRight);
      
      // Доступная ширина для слот-машины
      const availableWidth = containerWidth - containerPadding;
      
      // Ширина самой слот-машины (с учетом максимума)
      const slotMachineWidth = Math.min(availableWidth, 600); // max-width из CSS
      
      // Вычисляем ширину одного элемента
      const calculatedItemWidth = (slotMachineWidth - (VISIBLE_ITEMS * ITEM_MARGIN)) / VISIBLE_ITEMS;
      
      // Устанавливаем ширину (минимум 80px для читабельности)
      const finalWidth = Math.max(80, Math.floor(calculatedItemWidth));
      
      setItemWidth(finalWidth);
      
      // Устанавливаем CSS переменную для использования в стилях
      document.documentElement.style.setProperty('--item-width', `${finalWidth}px`);
    }
    
    // Немедленный расчет
    calculateItemWidth();
    
    // Отложенный расчет после полной загрузки
    const timeoutId = setTimeout(calculateItemWidth, 200);
    
    // Обработчик изменения размера с debounce
    let resizeTimer;
    const handleResize = () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(calculateItemWidth, 150);
    };
    
    window.addEventListener('resize', handleResize);
    
    return () => {
      clearTimeout(timeoutId);
      clearTimeout(resizeTimer);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  // Сброс состояния при смене приза
  useEffect(() => {
    if (currentPrize && currentPrize !== currentPrizeRef.current) {
      currentPrizeRef.current = currentPrize;
      hasNotifiedRef.current = false;
      processedMessagesRef.current.clear();
      isSendingRef.current = false;
    }
  }, [currentPrize]);

  // Создание полосы участников
  const createParticipantStrip = useCallback(() => {
    if (!stripRef.current || participants.length === 0) return;
    
    stripRef.current.innerHTML = '';
    
    const duplicationFactor = getDuplicationFactor(wheelSpeed, participants.length);
    const duplicatedParticipants = [];
    
    for (let i = 0; i < duplicationFactor; i++) {
      duplicatedParticipants.push(...participants);
    }
    
    // Устанавливаем общую ширину полосы
    const totalWidth = duplicatedParticipants.length * (itemWidth + ITEM_MARGIN);
    stripRef.current.style.width = `${totalWidth}px`;
    document.documentElement.style.setProperty('--strip-width', `${totalWidth}px`);
    
    duplicatedParticipants.forEach((participant, index) => {
      const item = document.createElement('div');
      item.className = 'slot-item';
      item.dataset.participantId = participant.id;
      item.dataset.originalIndex = index % participants.length;
      
      const nameElement = document.createElement('div');
      nameElement.className = 'participant-name';
      nameElement.textContent =
        participant.username ||
        `${participant.first_name || ''} ${participant.last_name || ''}`.trim() ||
        'Участник';
      
      item.appendChild(nameElement);
      stripRef.current.appendChild(item);
    });
    
    // Центрируем полосу
    const middleGroup = Math.floor(duplicationFactor / 2);
    const startPosition = -middleGroup * participants.length * (itemWidth + ITEM_MARGIN);
    
    // Используем set вместо to для мгновенного позиционирования
    gsap.set(stripRef.current, { 
      x: startPosition,
      force3D: true // Форсируем GPU ускорение
    });
    
  }, [participants, wheelSpeed, itemWidth]);

  // Инициализация полосы
  useEffect(() => {
    createParticipantStrip();
    // Обновляем подсветку после создания
    requestAnimationFrame(() => updateHighlight());
  }, [createParticipantStrip]);

  // Обновление подсвеченного участника
  const updateHighlight = useCallback(() => {
    if (!stripRef.current || participants.length === 0) return;
    
    const currentX = -gsap.getProperty(stripRef.current, 'x');
    const itemFullWidth = itemWidth + ITEM_MARGIN;
    const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemFullWidth;
    
    const rawIndex = Math.round((currentX + centerOffset) / itemFullWidth);
    const len = participants.length;
    
    if (len === 0) return;
    
    let participantIndex = rawIndex % len;
    if (participantIndex < 0) participantIndex += len;
    
    const participant = participants[participantIndex];
    
    if (participant && participant.id !== lastHighlightIdRef.current) {
      lastHighlightIdRef.current = participant.id;
      setCurrentHighlight(participant);
    }
  }, [participants, itemWidth]);

  // Запуск вращения
  const startSpin = useCallback(() => {
    if (participants.length === 0 || !stripRef.current) return;
    
    hasNotifiedRef.current = false;
    
    const speedSettings = {
      fast: { duration: 4, ease: 'power4.out', spins: 5 },
      medium: { duration: 6, ease: 'power3.out', spins: 3 },
      slow: { duration: 8, ease: 'power2.out', spins: 2 },
    };
    
    const settings = speedSettings[wheelSpeed] || speedSettings.fast;
    const itemFullWidth = itemWidth + ITEM_MARGIN;
    
    let finalPosition;
    
    if (targetWinnerIndex !== undefined && targetWinnerIndex >= 0) {
      const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemFullWidth;
      const targetPosition = targetWinnerIndex * itemFullWidth;
      const currentX = gsap.getProperty(stripRef.current, 'x');
      const totalDistance = settings.spins * participants.length * itemFullWidth;
      finalPosition = currentX - totalDistance - targetPosition + centerOffset;
    } else {
      const randomIndex = Math.floor(Math.random() * participants.length);
      const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemFullWidth;
      const targetPosition = randomIndex * itemFullWidth;
      const currentX = gsap.getProperty(stripRef.current, 'x');
      const totalDistance = settings.spins * participants.length * itemFullWidth;
      finalPosition = currentX - totalDistance - targetPosition + centerOffset;
    }
    
    // Убиваем предыдущую анимацию
    if (animationRef.current) {
      animationRef.current.kill();
    }
    
    animationRef.current = gsap.timeline({ 
      onUpdate: updateHighlight, 
      onComplete: handleSpinComplete 
    })
    .to(stripRef.current, {
      x: finalPosition,
      duration: settings.duration,
      ease: settings.ease,
      force3D: true, // GPU ускорение
      rotation: 0.01 // Хак для принудительного GPU
    })
    .to('.slot-machine', {
      className: '+=spinning',
      duration: 0.1,
    }, 0)
    .to('.slot-machine', {
      className: '-=spinning',
      duration: 0.1,
    }, '-=0.5');
    
  }, [participants, wheelSpeed, targetWinnerIndex, itemWidth, updateHighlight]);

  // Обработка завершения вращения
  const handleSpinComplete = useCallback(() => {
    if (!hasNotifiedRef.current && currentPrize && socket) {
      hasNotifiedRef.current = true;
      
      // Находим победителя по центральной позиции
      const currentX = -gsap.getProperty(stripRef.current, 'x');
      const itemFullWidth = itemWidth + ITEM_MARGIN;
      const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemFullWidth;
      
      const winnerIndex = Math.round((currentX + centerOffset) / itemFullWidth) % participants.length;
      const winner = participants[winnerIndex < 0 ? winnerIndex + participants.length : winnerIndex];
      
      if (winner && socket.readyState === WebSocket.OPEN) {
        const now = Date.now();
        const messageId = `${raffleId}_${currentPrize.position}_${now}`;
        
        if (!processedMessagesRef.current.has(messageId) && !isSendingRef.current) {
          isSendingRef.current = true;
          processedMessagesRef.current.add(messageId);
          
          const message = {
            type: 'winner_selected',
            winner: winner,
            position: currentPrize.position,
            prize: currentPrize.prize,
            timestamp: now,
            messageId: messageId,
          };
          
          console.log('Sending winner to server:', message);
          socket.send(JSON.stringify(message));
          
          // Находим и подсвечиваем элемент победителя
          const winnerElements = stripRef.current.querySelectorAll(`[data-participant-id="${winner.id}"]`);
          winnerElements.forEach(el => el.classList.add('winner'));
          
          setTimeout(() => {
            isSendingRef.current = false;
          }, 1000);
        }
        
        onComplete && onComplete(winner);
      }
    }
  }, [participants, currentPrize, socket, raffleId, onComplete, itemWidth]);

  // Управление анимацией
  useEffect(() => {
    if (isSpinning && !animationRef.current) {
      startSpin();
    } else if (!isSpinning && animationRef.current) {
      animationRef.current.kill();
      animationRef.current = null;
    }
  }, [isSpinning, startSpin]);

  return (
    <div className="slot-machine-container" ref={containerRef}>
      {/* Current participant */}
      {currentHighlight && (
        <div className="current-highlight">
          <p className="text-sm text-gray-600 mb-1">Под прицелом:</p>
          <div className="highlight-name">
            {currentHighlight.username ||
              `${currentHighlight.first_name || ''} ${currentHighlight.last_name || ''}`.trim()}
          </div>
        </div>
      )}
      
      {/* Prize info */}
      {currentPrize && (
        <div className="prize-info">
          <p className="text-sm opacity-90">Разыгрывается:</p>
          <p className="text-xl font-bold">
            {currentPrize.position} место - {currentPrize.prize}
          </p>
        </div>
      )}
      
      {/* Slot machine */}
      <div className="slot-machine" ref={slotRef}>
        <div className="slot-viewport">
          <div className="slot-strip" ref={stripRef}></div>
          <div className="slot-marker"></div>
          <div className="slot-overlay-left"></div>
          <div className="slot-overlay-right"></div>
        </div>
      </div>
      
      {/* Status display */}
      <div className="status-display">
        <p className="text-sm font-semibold text-gray-600">
          {isSpinning ? '🎰 Выбираем победителя...' : '⏳ Ожидание розыгрыша...'}
        </p>
        {participants.length > 0 && (
          <p className="text-xs text-gray-500 mt-1">Участников: {participants.length}</p>
        )}
      </div>
    </div>
  );
};

export default SlotMachineComponent;