import React, { useRef, useEffect, useState, useCallback } from 'react';
import { gsap } from 'gsap';
import './SlotMachine.css';

const VISIBLE_ITEMS = 5;

/**
 * Возвращает размер margin в зависимости от ширины окна.
 */
const getItemMargin = () => {
  const width = window.innerWidth;
  if (width <= 400) {
    return 4;
  } else if (width <= 768) {
    return 6;
  }
  return 6;
};

function getDuplicationFactor(speed, participantsLength) {
  const baseMap = { fast: 20, medium: 15, slow: 12 };
  const base = baseMap[speed] || baseMap.fast;
  const len = participantsLength || 1;
  const minFactor = Math.max(10, Math.ceil((VISIBLE_ITEMS * 5) / len) + 5);
  return Math.max(base, minFactor);
}

const SlotMachineComponent = ({
  participants = [],
  isSpinning,
  onComplete,
  currentPrize,
  socket,
  raffleId,
  wheelSpeed = 'fast',
  targetWinnerIndex,
}) => {
  // безопасная копия списка участников
  const validParticipants = Array.isArray(participants) ? participants : [];

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

  // рассчитываем ширину одного элемента и отслеживаем resize
  useEffect(() => {
    function calculateItemWidth() {
      if (!containerRef.current || !slotRef.current || isAnimatingRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const containerWidth = containerRect.width;
      const containerStyle = window.getComputedStyle(containerRef.current);
      const containerPadding = parseFloat(containerStyle.paddingLeft) + parseFloat(containerStyle.paddingRight);
      const slotRect = slotRef.current.getBoundingClientRect();
      const slotWidth = slotRect.width;
      const availableWidth = Math.min(slotWidth, containerWidth - containerPadding, window.innerWidth - 32);
      const totalMargins = VISIBLE_ITEMS * getItemMargin();
      const calculatedItemWidth = Math.floor((availableWidth - totalMargins) / VISIBLE_ITEMS);
      const finalWidth = Math.max(60, Math.min(120, calculatedItemWidth));
      if (Math.abs(finalWidth - lastWidthRef.current) > 2) {
        lastWidthRef.current = finalWidth;
        setItemWidth(finalWidth);
        document.documentElement.style.setProperty('--item-width', `${finalWidth}px`);
        // если не анимируем, пересоздаем полосу
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

  // при смене приза сбрасываем состояние
  useEffect(() => {
    if (currentPrize && currentPrize !== currentPrizeRef.current) {
      currentPrizeRef.current = currentPrize;
      hasNotifiedRef.current = false;
      processedMessagesRef.current.clear();
      isSendingRef.current = false;
    }
  }, [currentPrize]);

  // создаём полосу дублированных участников
  const createParticipantStrip = useCallback((preservePosition = false, currentX = null) => {
    if (!stripRef.current || validParticipants.length === 0) return;

    stripRef.current.setAttribute('data-gsap-animated', 'true');
    stripRef.current.innerHTML = '';

    const duplicationFactor = getDuplicationFactor(wheelSpeed, validParticipants.length);
    const duplicatedParticipants = [];

    for (let i = 0; i < duplicationFactor; i++) {
      duplicatedParticipants.push(...validParticipants);
    }

    const currentMargin = getItemMargin();
    const itemFullWidth = itemWidth + currentMargin;
    const totalWidth = duplicatedParticipants.length * itemFullWidth;

    duplicatedParticipants.forEach((participant, index) => {
      const item = document.createElement('div');
      item.className = 'slot-item';
      item.dataset.participantId = participant.id;
      item.dataset.originalIndex = index % validParticipants.length;
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
      const middleGroupStart = Math.floor(duplicationFactor / 2) * validParticipants.length;
      const viewportCenter = slotRef.current ? slotRef.current.offsetWidth / 2 : 0;
      startPosition = -(middleGroupStart * itemFullWidth) + viewportCenter;
    }

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
  }, [validParticipants, wheelSpeed, itemWidth, slotRef]);

  // инициализируем полосу при монтировании и при изменении списка участников
  useEffect(() => {
    if (!isResizingRef.current) {
      createParticipantStrip();
      setTimeout(() => updateHighlight(), 50);
    }
  }, [createParticipantStrip]);

  // вычисляем участника под центральным маркером
  const updateHighlight = useCallback(() => {
    if (!stripRef.current || validParticipants.length === 0) return;

    const computedStyle = window.getComputedStyle(document.documentElement);
    const currentItemWidth = parseFloat(computedStyle.getPropertyValue('--item-width')) || itemWidth;
    const currentMargin = getItemMargin();
    const currentX = gsap.getProperty(stripRef.current, 'x') || 0;
    const itemFullWidth = currentItemWidth + currentMargin;
    const viewportWidth = slotRef.current ? slotRef.current.offsetWidth : 0;
    const viewportCenter = viewportWidth / 2;
    const absolutePosition = -currentX + viewportCenter;
    let targetIndex = Math.floor(absolutePosition / itemFullWidth);
    let participantIndex = targetIndex % validParticipants.length;

    while (participantIndex < 0) {
      participantIndex += validParticipants.length;
    }

    const participant = validParticipants[participantIndex];

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
  }, [validParticipants, itemWidth, slotRef]);

  // запускаем анимацию спина
  const startSpin = useCallback(() => {
    if (validParticipants.length === 0 || !stripRef.current || isAnimatingRef.current) return;

    console.log('Starting spin animation...');
    hasNotifiedRef.current = false;
    isAnimatingRef.current = true;

    const speedSettings = {
      fast: { duration: 4, ease: 'power4.out', spins: 8 },
      medium: { duration: 6, ease: 'power3.out', spins: 5 },
      slow: { duration: 8, ease: 'power2.out', spins: 3 },
    };
    const settings = speedSettings[wheelSpeed] || speedSettings.fast;

    const computedStyle = window.getComputedStyle(document.documentElement);
    const currentItemWidth = parseFloat(computedStyle.getPropertyValue('--item-width')) || itemWidth;
    const currentMargin = getItemMargin();
    const itemFullWidth = currentItemWidth + currentMargin;

    const currentX = gsap.getProperty(stripRef.current, 'x') || 0;
    const viewportCenter = slotRef.current ? slotRef.current.offsetWidth / 2 : 0;

    // если сервер прислал индекс победителя — используем его
    let targetIndex;
    if (targetWinnerIndex !== undefined && targetWinnerIndex >= 0) {
      targetIndex = targetWinnerIndex;
      console.log('Using server-provided winner index:', targetIndex);
    } else {
      // fallback (для тестов)
      targetIndex = Math.floor(Math.random() * participants.length);
      console.warn('No server winner index, using random:', targetIndex);
    }

    const spinsDistance = settings.spins * validParticipants.length * itemFullWidth;
    const currentAbsolutePos = -currentX + viewportCenter;
    const currentElementIndex = Math.floor(currentAbsolutePos / itemFullWidth);
    let elementsToTarget = targetIndex - (currentElementIndex % validParticipants.length);
    if (elementsToTarget <= 0) {
      elementsToTarget += validParticipants.length;
    }

    const targetDistance = spinsDistance + (elementsToTarget * itemFullWidth);
    const finalPosition = currentX - targetDistance + viewportCenter;

    console.log('Animation to predetermined winner:', {
      targetIndex,
      winnerName: validParticipants[targetIndex]?.username || validParticipants[targetIndex]?.first_name,
      finalPosition
    });

    if (animationRef.current) {
      animationRef.current.kill();
    }

    animationRef.current = gsap.to(stripRef.current, {
      x: finalPosition,
      duration: settings.duration,
      ease: settings.ease,
      onUpdate: updateHighlight,
      onComplete: () => {
        console.log('Animation completed - winner predetermined by server');
        isAnimatingRef.current = false;
        animationRef.current = null;
        handleSpinComplete();
      },
      onStart: () => {
        if (slotRef.current) {
          slotRef.current.classList.add('spinning');
        }
      }
    });
  }, [validParticipants, wheelSpeed, targetWinnerIndex, itemWidth, updateHighlight, handleSpinComplete]);

  const handleSpinComplete = useCallback(() => {
    console.log('Animation completed');
    if (slotRef.current) {
      slotRef.current.classList.remove('spinning');
    }
    updateHighlight();
    if (onComplete) {
      const winner = currentHighlight || validParticipants[0];
      onComplete(winner);
    }
  }, [validParticipants, currentHighlight, updateHighlight, onComplete]);

  // запускаем спин при изменении isSpinning
  useEffect(() => {
    if (isSpinning && !isAnimatingRef.current) {
      startSpin();
    }
  }, [isSpinning, startSpin]);

  // при монтировании делаем полосу видимой
  useEffect(() => {
    if (stripRef.current) {
      gsap.set(stripRef.current, {
        opacity: 1,
        visibility: 'visible'
      });
    }
  }, []);

  // отслеживаем изменение брейкпоинтов и пересоздаём полосу при изменении margin
  useEffect(() => {
    let lastWidth = window.innerWidth;
    const handleResize = () => {
      const currentWidth = window.innerWidth;
      const wasSmall = lastWidth <= 400;
      const isSmall = currentWidth <= 400;
      const wasMedium = lastWidth > 400 && lastWidth <= 768;
      const isMedium = currentWidth > 400 && currentWidth <= 768;
      if (wasSmall !== isSmall || wasMedium !== isMedium) {
        console.log('Margin breakpoint crossed, recreating strip');
        lastWidth = currentWidth;
        if (!isAnimatingRef.current && stripRef.current) {
          const currentX = gsap.getProperty(stripRef.current, 'x') || 0;
          createParticipantStrip(true, currentX);
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
  }, [createParticipantStrip, updateHighlight]);

  return (
    <div className="slot-machine-container" ref={containerRef}>
      {/* Текущий участник под маркером */}
      {currentHighlight && (
        <div className="current-highlight">
          <p className="text-sm text-gray-300 mb-1">Под прицелом:</p>
          <div className="highlight-name">
            {currentHighlight.username ||
              `${currentHighlight.first_name || ''} ${currentHighlight.last_name || ''}`.trim()}
          </div>
        </div>
      )}

      {/* Информация о текущем разыгрываемом месте */}
      {currentPrize && (
        <div className="prize-info">
          <p className="text-sm opacity-90">Разыгрывается:</p>
          <p className="text-lg font-bold">
            {currentPrize.position} место - {currentPrize.prize}
          </p>
        </div>
      )}

      {/* Полоса слот‑машины */}
      <div className="slot-machine" ref={slotRef}>
        <div className="slot-viewport">
          <div className="slot-strip" ref={stripRef}></div>
          <div className="slot-marker"></div>
          <div className="slot-overlay-left"></div>
          <div className="slot-overlay-right"></div>
        </div>
      </div>

      {/* Статус анимации */}
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
