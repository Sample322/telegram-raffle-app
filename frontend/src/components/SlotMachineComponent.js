import React, { useRef, useEffect, useState, useCallback } from 'react';
import { gsap } from 'gsap';
import './SlotMachine.css';

const SlotMachineComponent = ({ 
  participants, 
  isSpinning, 
  onComplete, 
  currentPrize, 
  socket, 
  raffleId, 
  wheelSpeed = 'fast',
  targetWinnerIndex 
}) => {
  const slotRef = useRef(null);
  const stripRef = useRef(null);
  const [currentHighlight, setCurrentHighlight] = useState(null);
  const hasNotifiedRef = useRef(false);
  const currentPrizeRef = useRef(null);
  const processedMessagesRef = useRef(new Set());
  const isSendingRef = useRef(false);
  const animationRef = useRef(null);

  // Константы для анимации
  const ITEM_WIDTH = 200;
  const ITEM_HEIGHT = 80;
  const VISIBLE_ITEMS = 5;
  const DUPLICATION_FACTOR = 10; // Дублируем список для бесконечного скролла

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

    // Очищаем существующий контент
    stripRef.current.innerHTML = '';

    // Дублируем участников для бесконечного скролла
    const duplicatedParticipants = [];
    for (let i = 0; i < DUPLICATION_FACTOR; i++) {
      duplicatedParticipants.push(...participants);
    }

    // Создаем элементы
    duplicatedParticipants.forEach((participant, index) => {
      const item = document.createElement('div');
      item.className = 'slot-item';
      item.dataset.participantId = participant.id;
      item.dataset.originalIndex = index % participants.length;
      
      const nameElement = document.createElement('div');
      nameElement.className = 'participant-name';
      nameElement.textContent = participant.username || 
        `${participant.first_name || ''} ${participant.last_name || ''}`.trim() || 
        'Участник';
      
      item.appendChild(nameElement);
      stripRef.current.appendChild(item);
    });

    // Устанавливаем начальную позицию в центр
    const startPosition = -(DUPLICATION_FACTOR / 2) * participants.length * ITEM_WIDTH;
    gsap.set(stripRef.current, { x: startPosition });
  }, [participants]);

  // Инициализация
  useEffect(() => {
    createParticipantStrip();
  }, [createParticipantStrip]);

  // Анимация слот-машины
  const startSpin = useCallback(() => {
    if (participants.length === 0 || !stripRef.current) return;

    hasNotifiedRef.current = false;

    // Определяем скорость и длительность
    const speedSettings = {
      fast: { duration: 4, ease: "power4.out", spins: 5 },
      medium: { duration: 6, ease: "power3.out", spins: 3 },
      slow: { duration: 8, ease: "power2.out", spins: 2 }
    };

    const settings = speedSettings[wheelSpeed] || speedSettings.fast;

    // Вычисляем финальную позицию
    let finalPosition;
    if (targetWinnerIndex !== undefined && targetWinnerIndex >= 0) {
      // Находим позицию целевого участника в центре видимой области
      const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * ITEM_WIDTH;
      const targetPosition = targetWinnerIndex * ITEM_WIDTH;
      const currentX = gsap.getProperty(stripRef.current, "x");
      
      // Добавляем полные обороты
      const totalDistance = settings.spins * participants.length * ITEM_WIDTH;
      finalPosition = currentX - totalDistance - targetPosition + centerOffset;
    } else {
      // Случайный выбор для обратной совместимости
      const randomIndex = Math.floor(Math.random() * participants.length);
      const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * ITEM_WIDTH;
      const targetPosition = randomIndex * ITEM_WIDTH;
      const currentX = gsap.getProperty(stripRef.current, "x");
      const totalDistance = settings.spins * participants.length * ITEM_WIDTH;
      finalPosition = currentX - totalDistance - targetPosition + centerOffset;
    }

    // Анимация с эффектами
    animationRef.current = gsap.timeline({
      onUpdate: updateHighlight,
      onComplete: () => handleSpinComplete()
    })
    .to(stripRef.current, {
      x: finalPosition,
      duration: settings.duration,
      ease: settings.ease
    })
    .to('.slot-machine', {
      className: '+=spinning',
      duration: 0.1
    }, 0)
    .to('.slot-machine', {
      className: '-=spinning',
      duration: 0.1
    }, '-=0.5');

  }, [participants, wheelSpeed, targetWinnerIndex]);

  // Обновление подсветки текущего элемента
  const updateHighlight = useCallback(() => {
    if (!stripRef.current) return;

    const containerRect = slotRef.current.getBoundingClientRect();
    const centerX = containerRect.left + containerRect.width / 2;

    const items = stripRef.current.querySelectorAll('.slot-item');
    let closestItem = null;
    let minDistance = Infinity;

    items.forEach(item => {
      const rect = item.getBoundingClientRect();
      const itemCenterX = rect.left + rect.width / 2;
      const distance = Math.abs(itemCenterX - centerX);

      if (distance < minDistance) {
        minDistance = distance;
        closestItem = item;
      }

      // Убираем класс active со всех элементов
      item.classList.remove('active');
    });

    if (closestItem && minDistance < ITEM_WIDTH / 2) {
      closestItem.classList.add('active');
      const participantId = parseInt(closestItem.dataset.participantId);
      const participant = participants.find(p => p.id === participantId);
      setCurrentHighlight(participant);
    }
  }, [participants]);

  // Обработка завершения анимации
  const handleSpinComplete = useCallback(() => {
    if (!hasNotifiedRef.current && currentPrize && socket) {
      hasNotifiedRef.current = true;

      // Находим победителя в центре
      const containerRect = slotRef.current.getBoundingClientRect();
      const centerX = containerRect.left + containerRect.width / 2;

      const items = stripRef.current.querySelectorAll('.slot-item');
      let winnerElement = null;
      let minDistance = Infinity;

      items.forEach(item => {
        const rect = item.getBoundingClientRect();
        const itemCenterX = rect.left + rect.width / 2;
        const distance = Math.abs(itemCenterX - centerX);

        if (distance < minDistance) {
          minDistance = distance;
          winnerElement = item;
        }
      });

      if (winnerElement) {
        const participantId = parseInt(winnerElement.dataset.participantId);
        const winner = participants.find(p => p.id === participantId);

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
              messageId: messageId
            };

            console.log('Sending winner to server:', message);
            socket.send(JSON.stringify(message));

            // Добавляем визуальный эффект победы
            winnerElement.classList.add('winner');
            gsap.to(winnerElement, {
              scale: 1.2,
              duration: 0.5,
              yoyo: true,
              repeat: 1,
              ease: "power2.inOut"
            });

            setTimeout(() => { 
              isSendingRef.current = false; 
            }, 1000);
          }

          onComplete && onComplete(winner);
        }
      }
    }
  }, [participants, currentPrize, socket, raffleId, onComplete]);

  // Запуск анимации при изменении isSpinning
  useEffect(() => {
    if (isSpinning && !animationRef.current) {
      startSpin();
    } else if (!isSpinning && animationRef.current) {
      animationRef.current.kill();
      animationRef.current = null;
    }
  }, [isSpinning, startSpin]);

  return (
    <div className="slot-machine-container">
      {/* Текущий участник */}
      {currentHighlight && (
        <div className="current-highlight">
          <p className="text-sm text-gray-600 mb-1">Под прицелом:</p>
          <div className="highlight-name">
            {currentHighlight.username || 
             `${currentHighlight.first_name || ''} ${currentHighlight.last_name || ''}`.trim()}
          </div>
        </div>
      )}

      {/* Информация о призе */}
      {currentPrize && (
        <div className="prize-info">
          <p className="text-sm opacity-90">Разыгрывается:</p>
          <p className="text-xl font-bold">{currentPrize.position} место - {currentPrize.prize}</p>
        </div>
      )}

      {/* Слот-машина */}
      <div className="slot-machine" ref={slotRef}>
        <div className="slot-viewport">
          <div className="slot-strip" ref={stripRef}></div>
          <div className="slot-marker"></div>
          <div className="slot-overlay-left"></div>
          <div className="slot-overlay-right"></div>
        </div>
      </div>

      {/* Статус */}
      <div className="status-display">
        <p className="text-sm font-semibold text-gray-600">
          {isSpinning ? '🎰 Выбираем победителя...' : '⏳ Ожидание розыгрыша...'}
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

export default SlotMachineComponent;