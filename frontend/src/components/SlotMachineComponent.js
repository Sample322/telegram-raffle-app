import React, { useRef, useEffect, useState, useCallback } from 'react';
import { gsap } from 'gsap';
import './SlotMachine.css';

const VISIBLE_ITEMS = 5;
// ITEM_MARGIN теперь будет динамическим. Используйте функцию getItemMargin() вместо этой константы.

/**
 * Returns the margin for each item based on the current window width.
 * At widths ≤ 400px, the margin is 4px (2px on each side). Between 401px and
 * 768px, the margin is 6px (3px on each side). For widths above 768px
 * the margin remains 6px by default. This allows the slot machine to
 * dynamically adjust spacing based on responsive breakpoints.
 */
const getItemMargin = () => {
  const width = window.innerWidth;
  if (width <= 400) {
    return 4; // 2px с каждой стороны
  } else if (width <= 768) {
    return 6; // 3px с каждой стороны
  }
  return 6; // По умолчанию 3px с каждой стороны
};

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
  const isAnimatingRef = useRef(false);

  // Расчет ширины элемента с обработкой resize
  useEffect(() => {
    function calculateItemWidth() {
      if (!containerRef.current || !slotRef.current || isAnimatingRef.current) return;
      
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
      
      // Используем динамический margin для расчета общей ширины отступов
      const totalMargins = VISIBLE_ITEMS * getItemMargin();
      const calculatedItemWidth = Math.floor((availableWidth - totalMargins) / VISIBLE_ITEMS);
      
      const minWidth = 60;
      const maxWidth = 120;
      const finalWidth = Math.max(minWidth, Math.min(maxWidth, calculatedItemWidth));
      
      // Проверяем, изменилась ли ширина значительно
      if (Math.abs(finalWidth - lastWidthRef.current) > 2) {
        lastWidthRef.current = finalWidth;
        setItemWidth(finalWidth);
        document.documentElement.style.setProperty('--item-width', `${finalWidth}px`);
        
        // Если не анимируем, пересоздаем полосу
        if (!isAnimatingRef.current && stripRef.current) {
          isResizingRef.current = true;
          const currentX = gsap.getProperty(stripRef.current, 'x') || 0;
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
      if (!isAnimatingRef.current) {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(calculateItemWidth, 150);
      }
    };
    
    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleResize);
    
    let resizeObserver;
    if (window.ResizeObserver && containerRef.current) {
      resizeObserver = new ResizeObserver(() => {
        if (!isAnimatingRef.current) {
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
  
  stripRef.current.setAttribute('data-gsap-animated', 'true');
  stripRef.current.innerHTML = '';
  
  const duplicationFactor = getDuplicationFactor(wheelSpeed, participants.length);
  const duplicatedParticipants = [];
  
  for (let i = 0; i < duplicationFactor; i++) {
    duplicatedParticipants.push(...participants);
  }
  
  // Определяем динамический margin в зависимости от ширины экрана
  const currentMargin = getItemMargin();
  const itemFullWidth = itemWidth + currentMargin;
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
    const oldItemWidth = lastWidthRef.current || itemWidth;
    const ratio = itemWidth / oldItemWidth;
    startPosition = currentX * ratio;
  } else {
    // Центрируем полосу так, чтобы первый участник среднего дубликата был под маркером
    const middleGroupStart = Math.floor(duplicationFactor / 2) * participants.length;
    const viewportCenter = slotRef.current ? slotRef.current.offsetWidth / 2 : 0;
    startPosition = -(middleGroupStart * itemFullWidth) + viewportCenter;
  }
  
  // Используем GSAP для установки начальной позиции
  gsap.set(stripRef.current, { 
    x: startPosition,
    opacity: 1,
    visibility: 'visible'
  });
  
  if (preservePosition) {
    setTimeout(() => {
      updateHighlight();
      isResizingRef.current = false;
    }, 50);
  }
  
}, [participants, wheelSpeed, itemWidth, slotRef]);

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
  
  // Получаем актуальную ширину элемента из CSS переменной
  const computedStyle = window.getComputedStyle(document.documentElement);
  const currentItemWidth = parseFloat(computedStyle.getPropertyValue('--item-width')) || itemWidth;

  // Используем динамический margin вместо константы
  const currentMargin = getItemMargin();

  // Получаем текущую позицию полосы
  const currentX = gsap.getProperty(stripRef.current, 'x') || 0;

  // Полная ширина одного элемента (включая margins)
  const itemFullWidth = currentItemWidth + currentMargin;

  // Позиция центра viewport
  const viewportWidth = slotRef.current ? slotRef.current.offsetWidth : 0;
  const viewportCenter = viewportWidth / 2;

  // Абсолютная позиция для расчета (инвертируем X так как полоса движется влево)
  const absolutePosition = -currentX + viewportCenter;

  // Находим индекс элемента под центральным маркером
  let targetIndex = Math.floor(absolutePosition / itemFullWidth);

  // Получаем индекс участника с учетом цикличности
  let participantIndex = targetIndex % participants.length;

  // Обрабатываем отрицательные индексы
  while (participantIndex < 0) {
    participantIndex += participants.length;
  }

  const participant = participants[participantIndex];

  // Отладочная информация
  if (process.env.NODE_ENV === 'development') {
    console.log('Highlight calculation:', {
      currentX,
      viewportCenter,
      absolutePosition,
      targetIndex,
      participantIndex,
      itemFullWidth,
      currentItemWidth,
      participant: participant?.username || participant?.first_name
    });
  }

  if (participant && participant.id !== lastHighlightIdRef.current) {
    lastHighlightIdRef.current = participant.id;
    setCurrentHighlight(participant);
  }
}, [participants, itemWidth, slotRef]);

  // Запуск вращения
  const startSpin = useCallback(() => {
  if (participants.length === 0 || !stripRef.current || isAnimatingRef.current) return;
  
  console.log('Starting spin animation...');
  hasNotifiedRef.current = false;
  isAnimatingRef.current = true;
  
  const speedSettings = {
    fast: { duration: 4, ease: 'power4.out', spins: 8 },
    medium: { duration: 6, ease: 'power3.out', spins: 5 },
    slow: { duration: 8, ease: 'power2.out', spins: 3 },
  };
  
  const settings = speedSettings[wheelSpeed] || speedSettings.fast;
  
  // Получаем актуальную ширину элемента
  const computedStyle = window.getComputedStyle(document.documentElement);
  const currentItemWidth = parseFloat(computedStyle.getPropertyValue('--item-width')) || itemWidth;
  // Используем динамический margin вместо константы
  const currentMargin = getItemMargin();
  const itemFullWidth = currentItemWidth + currentMargin;
  
  const currentX = gsap.getProperty(stripRef.current, 'x') || 0;
  const viewportCenter = slotRef.current ? slotRef.current.offsetWidth / 2 : 0;
  
  let targetIndex;
  if (targetWinnerIndex !== undefined && targetWinnerIndex >= 0) {
    targetIndex = targetWinnerIndex;
  } else {
    targetIndex = Math.floor(Math.random() * participants.length);
  }
  
  // Расчет финальной позиции
  const spinsDistance = settings.spins * participants.length * itemFullWidth;
  
  // Находим ближайшую позицию целевого элемента впереди
  const currentAbsolutePos = -currentX + viewportCenter;
  const currentElementIndex = Math.floor(currentAbsolutePos / itemFullWidth);
  
  // Сколько элементов нужно прокрутить до целевого
  let elementsToTarget = targetIndex - (currentElementIndex % participants.length);
  if (elementsToTarget <= 0) {
    elementsToTarget += participants.length;
  }
  
  // Финальная позиция
  const targetDistance = spinsDistance + (elementsToTarget * itemFullWidth);
  const finalPosition = currentX - targetDistance + viewportCenter;
  
  console.log('Spin parameters:', {
    targetIndex,
    currentX,
    finalPosition,
    distance: targetDistance,
    viewportCenter,
    currentItemWidth,
    duration: settings.duration
  });
  
  // Убиваем предыдущую анимацию если есть
  if (animationRef.current) {
    animationRef.current.kill();
  }
  
  // Создаем новую анимацию
  animationRef.current = gsap.to(stripRef.current, {
    x: finalPosition,
    duration: settings.duration,
    ease: settings.ease,
    onUpdate: updateHighlight,
    onComplete: () => {
      console.log('Animation completed');
      isAnimatingRef.current = false;
      animationRef.current = null;
      handleSpinComplete();
    },
    onStart: () => {
      console.log('Animation started');
      if (slotRef.current) {
        slotRef.current.classList.add('spinning');
      }
    }
  });
  
}, [participants, wheelSpeed, targetWinnerIndex, itemWidth, updateHighlight, slotRef]);

  // Обработка завершения вращения
  const handleSpinComplete = useCallback(() => {
    console.log('Handling spin complete...');
    
    // Убираем класс spinning
    if (slotRef.current) {
      slotRef.current.classList.remove('spinning');
    }
    
    if (!hasNotifiedRef.current && currentPrize && socket && socket.readyState === WebSocket.OPEN) {
      hasNotifiedRef.current = true;
      
      // Финальное обновление позиции
      updateHighlight();
      
      const winner = currentHighlight || participants[0];
      
      if (winner) {
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
          
          // Подсвечиваем победителя
          const winnerElements = stripRef.current.querySelectorAll(`[data-participant-id="${winner.id}"]`);
          winnerElements.forEach(el => el.classList.add('winner'));
          
          // Вызываем callback после отправки
          if (onComplete) {
            onComplete(winner);
          }
          
          // Сбрасываем флаг отправки через небольшую задержку
          setTimeout(() => {
            isSendingRef.current = false;
          }, 1000);
        }
      }
    }
  }, [participants, currentPrize, socket, raffleId, onComplete, currentHighlight, updateHighlight]);

  // Управление анимацией
  useEffect(() => {
    if (isSpinning && !isAnimatingRef.current) {
      startSpin();
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
  // Добавьте этот useEffect в SlotMachineComponent после других useEffect:

// Отслеживание изменения размера окна для пересчета margin
  useEffect(() => {
    let lastWidth = window.innerWidth;
    
    const handleResize = () => {
      const currentWidth = window.innerWidth;
      
      // Проверяем, перешли ли мы через breakpoint
      const wasSmall = lastWidth <= 400;
      const isSmall = currentWidth <= 400;
      const wasMedium = lastWidth > 400 && lastWidth <= 768;
      const isMedium = currentWidth > 400 && currentWidth <= 768;
      
      if (wasSmall !== isSmall || wasMedium !== isMedium) {
        // Margin изменился, нужно пересоздать полосу
        console.log('Margin breakpoint crossed, recreating strip');
        lastWidth = currentWidth;
        
        if (!isAnimatingRef.current && stripRef.current) {
          const currentX = gsap.getProperty(stripRef.current, 'x') || 0;
          createParticipantStrip(true, currentX);
          // Обновляем подсветку после пересоздания
          setTimeout(updateHighlight, 50);
        }
      }
    };
    
    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleResize);
    
    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleResize);
    };
  }, [createParticipantStrip, updateHighlight, isAnimatingRef]);
};

export default SlotMachineComponent;