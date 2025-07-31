import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Virtuoso } from 'react-virtuoso';
import { gsap } from 'gsap';

const SlotReelComponent = ({ 
  participants, 
  isSpinning, 
  onComplete, 
  currentPrize, 
  socket, 
  raffleId, 
  wheelSpeed = 'fast',
  targetOffset 
}) => {
  const virtuosoRef = useRef(null);
  const containerRef = useRef(null);
  const animationRef = useRef(null);
  const hasNotifiedRef = useRef(false);
  const processedMessagesRef = useRef(new Set());
  const isSendingRef = useRef(false);
  const currentPrizeRef = useRef(null);
  
  const [highlightedIndex, setHighlightedIndex] = useState(null);
  const [error, setError] = useState(false);

  const ITEM_HEIGHT = 60; // Высота одного элемента
  const VISIBLE_ITEMS = 7; // Количество видимых элементов
  const CENTER_OFFSET = Math.floor(VISIBLE_ITEMS / 2) * ITEM_HEIGHT;

  // Сброс состояния при смене приза
  useEffect(() => {
    if (currentPrize && currentPrize !== currentPrizeRef.current) {
      currentPrizeRef.current = currentPrize;
      hasNotifiedRef.current = false;
      processedMessagesRef.current.clear();
      isSendingRef.current = false;
      setError(false);
      console.log('Reset state for new prize:', currentPrize);
    }
  }, [currentPrize]);

  // Основная логика спина
  useEffect(() => {
    if (isSpinning && participants.length > 0 && !error) {
      hasNotifiedRef.current = false;
      startSpin();
    } else if (!isSpinning && animationRef.current) {
      // Остановка анимации
      animationRef.current.kill();
      animationRef.current = null;
    }

    return () => {
      if (animationRef.current) {
        animationRef.current.kill();
      }
    };
  }, [isSpinning, participants, error, targetOffset]);

  const startSpin = useCallback(() => {
    if (!virtuosoRef.current || participants.length === 0) return;

    const speedSettings = {
      fast: { duration: 3, rotations: 6 },
      medium: { duration: 5, rotations: 5 },
      slow: { duration: 7, rotations: 4 }
    };

    const settings = speedSettings[wheelSpeed] || speedSettings.fast;
    
    // Рассчитываем финальную позицию
    const totalHeight = participants.length * ITEM_HEIGHT;
    const rotationDistance = totalHeight * settings.rotations;
    
    // Если есть targetOffset от сервера
    let finalOffset;
    if (targetOffset !== undefined && targetOffset !== null) {
      finalOffset = targetOffset + rotationDistance;
    } else {
      // Fallback на случайный выбор
      const randomIndex = Math.floor(Math.random() * participants.length);
      finalOffset = (randomIndex * ITEM_HEIGHT) + rotationDistance;
    }

    // Создаем GSAP timeline
    const tl = gsap.timeline({
      onComplete: () => handleSpinComplete(finalOffset)
    });

    // Анимация прокрутки
    tl.to(containerRef.current, {
      duration: settings.duration,
      ease: "power3.out",
      onUpdate: function() {
        const progress = this.progress();
        const currentOffset = finalOffset * progress;
        const scrollTo = currentOffset % totalHeight;
        
        virtuosoRef.current?.scrollTo({
          top: scrollTo,
          behavior: 'auto'
        });

        // Подсветка текущего элемента при замедлении
        if (progress > 0.7) {
          const currentIndex = Math.round(scrollTo / ITEM_HEIGHT) % participants.length;
          setHighlightedIndex(currentIndex);
        }
      }
    });

    animationRef.current = tl;
  }, [participants, wheelSpeed, targetOffset]);

  const handleSpinComplete = useCallback((finalOffset) => {
    if (!hasNotifiedRef.current && participants.length > 0 && currentPrize) {
      hasNotifiedRef.current = true;

      // Определяем победителя по финальной позиции
      const totalHeight = participants.length * ITEM_HEIGHT;
      const normalizedOffset = finalOffset % totalHeight;
      const winnerIndex = Math.round(normalizedOffset / ITEM_HEIGHT) % participants.length;
      
      if (winnerIndex < 0 || winnerIndex >= participants.length) {
        console.error('Invalid winner index:', winnerIndex);
        return;
      }

      const winner = participants[winnerIndex];
      const now = Date.now();
      const messageId = `${raffleId}_${currentPrize.position}_${now}`;

      if (processedMessagesRef.current.has(messageId) || isSendingRef.current) {
        console.log('Skipping duplicate message:', messageId);
        return;
      }

      isSendingRef.current = true;
      processedMessagesRef.current.add(messageId);

      console.log('Slot stopped. Winner:', winner, 'Prize:', currentPrize);

      // Финальная подсветка победителя
      setHighlightedIndex(winnerIndex);

      // Объявление для screen readers
      const announcement = `Победитель ${currentPrize.position} места: ${winner.username || winner.first_name}`;
      announceWinner(announcement);

      if (winner && socket && socket.readyState === WebSocket.OPEN) {
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
      }

      setTimeout(() => { 
        isSendingRef.current = false; 
      }, 1000);
      
      onComplete && onComplete(winner);
    }
  }, [participants, currentPrize, raffleId, socket, onComplete]);

  const announceWinner = (text) => {
    const announcement = document.createElement('div');
    announcement.setAttribute('role', 'status');
    announcement.setAttribute('aria-live', 'polite');
    announcement.setAttribute('aria-atomic', 'true');
    announcement.className = 'sr-only';
    announcement.textContent = text;
    document.body.appendChild(announcement);
    
    setTimeout(() => {
      document.body.removeChild(announcement);
    }, 1000);
  };

  const ItemRenderer = ({ index }) => {
    const participant = participants[index];
    const isHighlighted = index === highlightedIndex;
    const displayName = participant.username || 
                       `${participant.first_name || ''} ${participant.last_name || ''}`.trim() ||
                       'Участник';

    return (
      <div
        className={`slot-item ${isHighlighted ? 'highlighted' : ''}`}
        style={{
          height: ITEM_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0 20px',
          backgroundColor: isHighlighted ? '#3B82F6' : index % 2 === 0 ? '#F3F4F6' : '#FFFFFF',
          color: isHighlighted ? '#FFFFFF' : '#1F2937',
          fontWeight: isHighlighted ? 'bold' : 'normal',
          fontSize: isHighlighted ? '20px' : '16px',
          transition: 'all 0.3s ease',
          borderTop: '1px solid #E5E7EB',
          borderBottom: '1px solid #E5E7EB',
          transform: isHighlighted ? 'scale(1.05)' : 'scale(1)',
          willChange: 'transform',
          contain: 'layout style paint'
        }}
      >
        <span className="truncate max-w-full">{displayName}</span>
      </div>
    );
  };

  return (
    <div className="slot-machine-container" style={{ position: 'relative' }}>
      {/* Prize display */}
      {currentPrize && (
        <div className="mb-4 text-center">
          <div className="bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg shadow-lg px-6 py-3">
            <p className="text-sm opacity-90">Разыгрывается:</p>
            <p className="text-xl font-bold">{currentPrize.position} место - {currentPrize.prize}</p>
          </div>
        </div>
      )}

      {/* Slot reel container */}
      <div className="relative bg-gray-900 rounded-lg p-4 shadow-2xl">
        {/* Top gradient overlay */}
        <div className="absolute top-0 left-0 right-0 h-20 bg-gradient-to-b from-gray-900 to-transparent z-10 pointer-events-none" />
        
        {/* Bottom gradient overlay */}
        <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-gray-900 to-transparent z-10 pointer-events-none" />

        {/* Center indicator */}
        <div className="absolute left-0 right-0 z-20 pointer-events-none" style={{ top: '50%', transform: 'translateY(-50%)' }}>
          <div className="flex items-center">
            <div className="w-0 h-0 border-t-[20px] border-t-transparent border-b-[20px] border-b-transparent border-r-[20px] border-r-red-500" />
            <div className="flex-1 h-1 bg-red-500" />
            <div className="w-0 h-0 border-t-[20px] border-t-transparent border-b-[20px] border-b-transparent border-l-[20px] border-l-red-500" />
          </div>
        </div>

        {/* Virtualized list */}
        <div 
          ref={containerRef}
          className="relative"
          style={{ 
            height: VISIBLE_ITEMS * ITEM_HEIGHT,
            overflow: 'hidden',
            borderRadius: '8px',
            backgroundColor: '#F9FAFB'
          }}
        >
          <Virtuoso
            ref={virtuosoRef}
            totalCount={participants.length}
            itemContent={ItemRenderer}
            overscan={5}
            style={{ height: '100%' }}
            scrollerRef={(ref) => {
              if (ref) {
                ref.style.scrollbarWidth = 'none';
                ref.style.msOverflowStyle = 'none';
                ref.style.webkitScrollbar = 'none';
              }
            }}
          />
        </div>
      </div>

      {/* Status display */}
      <div className="mt-4 text-center">
        <p className="text-sm font-semibold text-gray-600">
          {isSpinning ? '🎰 Слот вращается...' : '⏳ Ожидание розыгрыша...'}
        </p>
        {participants.length > 0 && (
          <p className="text-xs text-gray-500 mt-1">
            Участников: {participants.length}
          </p>
        )}
      </div>

      {/* Hidden element for screen readers */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {highlightedIndex !== null && !isSpinning && (
          <span>
            Победитель: {participants[highlightedIndex]?.username || participants[highlightedIndex]?.first_name}
          </span>
        )}
      </div>
    </div>
  );
};

export default SlotReelComponent;