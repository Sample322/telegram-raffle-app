import React, { useRef, useEffect, useState, useCallback } from 'react';
import { gsap } from 'gsap';
import './SlotMachine.css';

const VISIBLE_ITEMS = 5;
const ITEM_MARGIN = 6; // 3px с каждой стороны

function getDuplicationFactor(speed, participantsLength) {
  const baseMap = {
    fast: 20,
    medium: 15,
    slow: 12,
  };
  const base = baseMap[speed] || baseMap.fast;
  const len = participantsLength || 1;
  const minFactor = Math.max(10, Math.ceil((VISIBLE_ITEMS * 5) / len) + 5);
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
  const [itemWidth, setItemWidth] = useState(80);
  const hasNotifiedRef = useRef(false);
  const currentPrizeRef = useRef(null);
  const processedMessagesRef = useRef(new Set());
  const isSendingRef = useRef(false);
  const animationRef = useRef(null);
  const lastWidthRef = useRef(0);
  const isResizingRef = useRef(false);

  // Расчет ширины элемента с обработкой resize
  useEffect(() => {
    function calculateItemWidth() {
      if (!containerRef.current || !slotRef.current) return;
      
      const containerRect = containerRef.current.getBoundingClientRect();
      const containerWidth = containerRect.width;
      
      const containerStyle = window.getComputedStyle(containerRef.current);
      const containerPadding = parseFloat(containerStyle.paddingLeft) + parseFloat(containerStyle.paddingRight);
      
      const slotRect = slotRef.current.getBoundingClientRect();
      const slotWidth = slotRect.width;
      
      const availableWidth = Math.min(
        slotWidth,
        containerWidth - containerPadding,
        window.innerWidth - 32
      );
      
      const totalMargins = VISIBLE_ITEMS * ITEM_MARGIN;
      const calculatedItemWidth = Math.floor((availableWidth - totalMargins) / VISIBLE_ITEMS);
      
      const minWidth = 60;
      const maxWidth = 120;
      const finalWidth = Math.max(minWidth, Math.min(maxWidth, calculatedItemWidth));
      
      // Проверяем, изменилась ли ширина значительно
      if (Math.abs(finalWidth - lastWidthRef.current) > 2) {
        console.log('Item width changed:', {
          old: lastWidthRef.current,
          new: finalWidth,
          containerWidth,
          slotWidth
        });
        
        lastWidthRef.current = finalWidth;
        setItemWidth(finalWidth);
        document.documentElement.style.setProperty('--item-width', `${finalWidth}px`);
        
        // Если не анимируем, пересоздаем полосу
        if (!animationRef.current && stripRef.current) {
          isResizingRef.current = true;
          // Сохраняем текущую позицию перед пересозданием
          const currentX = gsap.getProperty(stripRef.current, 'x');
          createParticipantStrip(true, currentX);
        }
      }
    }
    
    calculateItemWidth();
    
    const timeouts = [
      setTimeout(calculateItemWidth, 100),
      setTimeout(calculateItemWidth, 300),
      setTimeout(calculateItemWidth, 500)
    ];
    
    let resizeTimer;
    const handleResize = () => {
      if (!animationRef.current) { // Не обрабатываем resize во время анимации
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(calculateItemWidth, 150);
      }
    };
    
    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleResize);
    
    let resizeObserver;
    if (window.ResizeObserver && containerRef.current) {
      resizeObserver = new ResizeObserver(() => {
        if (!animationRef.current) {
          handleResize();
        }
      });
      resizeObserver.observe(containerRef.current);
    }
    
    return () => {
      timeouts.forEach(clearTimeout);
      clearTimeout(resizeTimer);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleResize);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
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
  const createParticipantStrip = useCallback((preservePosition = false, currentX = null) => {
    if (!stripRef.current || participants.length === 0) return;
    
    // Маркируем strip для GSAP
    stripRef.current.setAttribute('data-gsap-animated', 'true');
    
    stripRef.current.innerHTML = '';
    
    const duplicationFactor = getDuplicationFactor(wheelSpeed, participants.length);
    const duplicatedParticipants = [];
    
    for (let i = 0; i < duplicationFactor; i++) {
      duplicatedParticipants.push(...participants);
    }
    
    const itemFullWidth = itemWidth + ITEM_MARGIN;
    const totalWidth = duplicatedParticipants.length * itemFullWidth;
    
    duplicatedParticipants.forEach((participant, index) => {
      const item = document.createElement('div');
      item.className = 'slot-item';
      item.dataset.participantId = participant.id;
      item.dataset.originalIndex = index % participants.length;
      item.dataset.absoluteIndex = index;
      
      const nameElement = document.createElement('div');
      nameElement.className = 'participant-name';
      nameElement.textContent =
        participant.username ||
        `${participant.first_name || ''} ${participant.last_name || ''}`.trim() ||
        'Участник';
      
      item.appendChild(nameElement);
      stripRef.current.appendChild(item);
    });
    
    stripRef.current.style.width = `${totalWidth}px`;
    
    let startPosition;
    if (preservePosition && currentX !== null) {
      // Пересчитываем позицию с учетом новой ширины элементов
      const oldItemWidth = lastWidthRef.current || itemWidth;
      const ratio = itemWidth / oldItemWidth;
      startPosition = currentX * ratio;
    } else {
      const middlePosition = Math.floor(duplicationFactor / 2) * participants.length * itemFullWidth;
      const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemFullWidth;
      startPosition = -middlePosition + centerOffset;
    }
    
    gsap.set(stripRef.current, { 
      x: startPosition,
      force3D: true,
      transform: `translateX(${startPosition}px) translateZ(0)`,
      opacity: 1,
      visibility: 'visible'
    });
    
    // Обновляем подсветку после пересоздания
    if (preservePosition) {
      setTimeout(() => {
        updateHighlight();
        isResizingRef.current = false;
      }, 50);
    }
    
  }, [participants, wheelSpeed, itemWidth]);

  // Инициализация полосы
  useEffect(() => {
    if (!isResizingRef.current) {
      createParticipantStrip();
      setTimeout(() => updateHighlight(), 50);
    }
  }, [createParticipantStrip]);

  // Обновление подсвеченного участника
  const updateHighlight = useCallback(() => {
    if (!stripRef.current || participants.length === 0) return;
    
    const currentX = -gsap.getProperty(stripRef.current, 'x');
    const itemFullWidth = itemWidth + ITEM_MARGIN;
    const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemFullWidth;
    
    const absoluteIndex = Math.round((currentX + centerOffset) / itemFullWidth);
    const participantIndex = ((absoluteIndex % participants.length) + participants.length) % participants.length;
    
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
    
    // Убеждаемся, что strip видим
    gsap.set(stripRef.current, {
      opacity: 1,
      visibility: 'visible'
    });
    
    const speedSettings = {
      fast: { duration: 4, ease: 'power4.out', spins: 8 },
      medium: { duration: 6, ease: 'power3.out', spins: 5 },
      slow: { duration: 8, ease: 'power2.out', spins: 3 },
    };
    
    const settings = speedSettings[wheelSpeed] || speedSettings.fast;
    const itemFullWidth = itemWidth + ITEM_MARGIN;
    
    const currentX = gsap.getProperty(stripRef.current, 'x');
    
    let targetIndex;
    if (targetWinnerIndex !== undefined && targetWinnerIndex >= 0) {
      targetIndex = targetWinnerIndex;
    } else {
      targetIndex = Math.floor(Math.random() * participants.length);
    }
    
    const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemFullWidth;
    const spinsDistance = settings.spins * participants.length * itemFullWidth;
    
    // Находим ближайший элемент с нужным индексом впереди
    const currentAbsolutePos = -currentX;
    let distanceToTarget = 0;
    let testPos = currentAbsolutePos;
    
    while (distanceToTarget < spinsDistance) {
      const testIndex = Math.floor((testPos + centerOffset) / itemFullWidth) % participants.length;
      if (testIndex === targetIndex && distanceToTarget > itemFullWidth * participants.length) {
        break;
      }
      testPos += itemFullWidth;
      distanceToTarget += itemFullWidth;
    }
    
    const finalPosition = currentX - distanceToTarget;
    
    console.log('Starting spin:', {
      targetIndex,
      currentX,
      finalPosition,
      distance: distanceToTarget
    });
    
    if (animationRef.current) {
      animationRef.current.kill();
    }
    
    animationRef.current = gsap.timeline({ 
      onUpdate: updateHighlight, 
      onComplete: () => {
        animationRef.current = null;
        handleSpinComplete();
      }
    })
    .set(stripRef.current, {
      opacity: 1,
      visibility: 'visible'
    })
    .to(stripRef.current, {
      x: finalPosition,
      duration: settings.duration,
      ease: settings.ease,
      force3D: true,
      onStart: () => {
        console.log('Animation started');
      }
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
      
      updateHighlight();
      
      const winner = currentHighlight || participants[0];
      
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
          
          const winnerElements = stripRef.current.querySelectorAll(`[data-participant-id="${winner.id}"]`);
          winnerElements.forEach(el => el.classList.add('winner'));
          
          setTimeout(() => {
            isSendingRef.current = false;
          }, 1000);
        }
        
        onComplete && onComplete(winner);
      }
    }
  }, [participants, currentPrize, socket, raffleId, onComplete, currentHighlight, updateHighlight]);

  // Управление анимацией
  useEffect(() => {
    if (isSpinning && !animationRef.current) {
      startSpin();
    } else if (!isSpinning && animationRef.current) {
      animationRef.current.kill();
      animationRef.current = null;
    }
  }, [isSpinning, startSpin]);

  // Проверка видимости при монтировании
  useEffect(() => {
    if (stripRef.current) {
      gsap.set(stripRef.current, {
        opacity: 1,
        visibility: 'visible'
      });
    }
  }, []);

  return (
    <div className="slot-machine-container" ref={containerRef}>
      {/* Current participant */}
      {currentHighlight && (
        <div className="current-highlight">
          <p className="text-sm text-gray-300 mb-1">Под прицелом:</p>
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
          <p className="text-lg font-bold">
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
        <p className="text-sm font-semibold">
          {isSpinning ? '🎰 Выбираем победителя...' : '⏳ Ожидание розыгрыша...'}
        </p>
        {participants.length > 0 && (
          <p className="text-xs opacity-75">
            Участников: {participants.length}
          </p>
        )}
      </div>
    </div>
  );
};

export default SlotMachineComponent;