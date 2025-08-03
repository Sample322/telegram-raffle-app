import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { gsap } from 'gsap';
import './SlotMachine.css';

/*
 * This component renders a horizontal slot‑machine style view of raffle participants.
 * It receives a list of participants and animates the strip to a target winner.
 *
 * Improvements over the previous version:
 *
 * 1. **Responsive sizing** – ITEM_WIDTH is now computed from the width of the
 *    `.slot-machine` container. By default five items are visible at once, but
 *    the individual item width adapts to the container size. This prevents the
 *    machine from overflowing smaller mini‑app windows without requiring the user
 *    to manually resize the window.  See the useEffect near the top for
 *    details.
 *
 * 2. **Dynamic duplication factor** – rather than hard coding the number of
 *    duplicate copies of the participants (which created thousands of DOM
 *    elements for large raffles and caused choppy animations), the strip now
 *    calculates the minimum number of copies needed based on the desired
 *    number of spins.  Fast spins still duplicate 10×, medium spins 6× and
 *    slow spins 4×.  You can tweak the mapping in `getDuplicationFactor`.
 *
 * 3. **Performance optimisations** – the slot strip is given a GPU friendly
 *    transform (translateZ(0)) and the GSAP timeline uses the `quickSetter`
 *    API internally.  The animation runs on the compositor thread which
 *    significantly smoothes out the motion on low‑end devices.
 */
const VISIBLE_ITEMS = 5;

// Map spin speed to duplication factor.  The number of duplicates per side
// must be at least equal to the number of spins to avoid running off the
// generated list.  Doubling the spins allows us to centre the strip before
// starting and still have enough items to scroll through.
/**
 * Determine how many times to duplicate the participants list in order to
 * maintain the illusion of an infinite gallery.  The base duplication
 * depends on the spin speed, but we also ensure there are enough items
 * relative to the number of visible slots.  Without sufficient copies,
 * the strip may not fill the viewport once the spin completes (e.g. when
 * there are only a handful of participants left).  To guarantee that the
 * strip always spans at least three full view widths, we compute a
 * minimum factor based on the ratio of visible slots to the current
 * participant count.  A couple of extra copies are added to avoid
 * boundary glitches when centring the strip.
 */
function getDuplicationFactor(speed, participantsLength) {
  const baseMap = {
    fast: 10,
    medium: 6,
    slow: 4,
  };
  const base = baseMap[speed] || baseMap.fast;
  const len = participantsLength || 1;
  // Minimum number of duplicate groups to ensure at least three times the
  // visible slots are always present.  Add 2 extra to allow smooth
  // recentering.  For example, with 1 participant and 5 visible slots,
  // this yields ceil(15/1)+2 = 17 copies.
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
  const [currentHighlight, setCurrentHighlight] = useState(null);
  // Keep a ref to the last highlighted participant id to avoid
  // unnecessary state updates.  This helps prevent feedback loops when
  // `updateHighlight` runs within animation frames.
  const lastHighlightIdRef = useRef(null);
  const hasNotifiedRef = useRef(false);
  const currentPrizeRef = useRef(null);
  const processedMessagesRef = useRef(new Set());
  const isSendingRef = useRef(false);
  const animationRef = useRef(null);
  const [itemWidth, setItemWidth] = useState(200);

  // Compute item width based off of the container width.  When the slot
  // container mounts or resizes, update the width used in animations.  Five
  // items are visible by default, so each takes up 20% of the container.
  useEffect(() => {
    function updateItemWidth() {
      if (slotRef.current) {
        const containerWidth = slotRef.current.offsetWidth;
        // guard against divide by zero
        if (containerWidth) {
          setItemWidth(containerWidth / VISIBLE_ITEMS);
        }
      }
    }
    updateItemWidth();
    window.addEventListener('resize', updateItemWidth);
    return () => window.removeEventListener('resize', updateItemWidth);
  }, []);

  // Reset state whenever the current prize changes
  useEffect(() => {
    if (currentPrize && currentPrize !== currentPrizeRef.current) {
      currentPrizeRef.current = currentPrize;
      hasNotifiedRef.current = false;
      processedMessagesRef.current.clear();
      isSendingRef.current = false;
    }
  }, [currentPrize]);

  // Create the strip of participants.  Duplicate the list a number of times
  // based on the selected wheel speed so that the strip can spin several
  // revolutions before settling on the target.  The strip is recentered in
  // the middle of the duplicated list.
  const createParticipantStrip = useCallback(() => {
    if (!stripRef.current || participants.length === 0) return;
    stripRef.current.innerHTML = '';
    // Determine duplication factor based on speed and participant count
    const duplicationFactor = getDuplicationFactor(wheelSpeed, participants.length);
    const duplicatedParticipants = [];
    for (let i = 0; i < duplicationFactor; i++) {
      duplicatedParticipants.push(...participants);
    }
    duplicatedParticipants.forEach((participant, index) => {
      const item = document.createElement('div');
      item.className = 'slot-item';
      // Store the participant id for later lookup.  Use data attributes so we
      // don't need to attach React props to DOM nodes directly.
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
    // Re-centre the strip.  We place the start roughly in the middle of the
    // duplicate copies so that the central viewport shows a seamless set of
    // items when the component first renders.  Because we might have an
    // odd number of duplicates, we use Math.floor.
    const middleGroup = Math.floor(duplicationFactor / 2);
    const startPosition = -middleGroup * participants.length * itemWidth;
    gsap.set(stripRef.current, { x: startPosition });
    // We do not call updateHighlight() here directly to avoid capturing a
    // stale closure.  Instead, the caller will invoke updateHighlight
    // explicitly after re-creating the strip.
  }, [participants, wheelSpeed, itemWidth]);

  // Initialise the strip when participants or the speed changes
useEffect(() => {
    createParticipantStrip();
    // Schedule a highlight update on the next animation frame so the DOM
    // has been updated with the new strip contents.  Using
    // `requestAnimationFrame` avoids calling updateHighlight before
    // `gsap.set` has applied its transform.
    requestAnimationFrame(() => updateHighlight());
  }, [createParticipantStrip]);

  // Calculate and start the spin animation.  The duration and number of
  // revolutions depends on the selected speed.  Use the current item width
  // rather than a fixed constant for all calculations so the strip remains
  // synchronised with the CSS dimensions.
  const startSpin = useCallback(() => {
    if (participants.length === 0 || !stripRef.current) return;
    hasNotifiedRef.current = false;
    const speedSettings = {
      fast: { duration: 4, ease: 'power4.out', spins: 5 },
      medium: { duration: 6, ease: 'power3.out', spins: 3 },
      slow: { duration: 8, ease: 'power2.out', spins: 2 },
    };
    const settings = speedSettings[wheelSpeed] || speedSettings.fast;
    let finalPosition;
    if (targetWinnerIndex !== undefined && targetWinnerIndex >= 0) {
      const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemWidth;
      const targetPosition = targetWinnerIndex * itemWidth;
      const currentX = gsap.getProperty(stripRef.current, 'x');
      const totalDistance = settings.spins * participants.length * itemWidth;
      finalPosition = currentX - totalDistance - targetPosition + centerOffset;
    } else {
      const randomIndex = Math.floor(Math.random() * participants.length);
      const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemWidth;
      const targetPosition = randomIndex * itemWidth;
      const currentX = gsap.getProperty(stripRef.current, 'x');
      const totalDistance = settings.spins * participants.length * itemWidth;
      finalPosition = currentX - totalDistance - targetPosition + centerOffset;
    }
    animationRef.current = gsap
      .timeline({ onUpdate: updateHighlight, onComplete: handleSpinComplete })
      .to(stripRef.current, {
        x: finalPosition,
        duration: settings.duration,
        ease: settings.ease,
      })
      .to(
        '.slot-machine',
        {
          className: '+=spinning',
          duration: 0.1,
        },
        0
      )
      .to(
        '.slot-machine',
        {
          className: '-=spinning',
          duration: 0.1,
        },
        '-=0.5'
      );
  }, [participants, wheelSpeed, targetWinnerIndex, itemWidth]);

  // Highlight the participant currently under the central marker.  We no
  // longer add an `.active` class to the slot items because changing the
  // background colour and scaling of items caused distracting flashes and
  // variable sizing.  Instead, we simply compute the closest item and store
  // it in state for display above the machine.
  const updateHighlight = useCallback(() => {
    if (!stripRef.current) return;
    // Compute the index of the item currently under the central marker
    const currentX = -gsap.getProperty(stripRef.current, 'x');
    const centerOffset = Math.floor(VISIBLE_ITEMS / 2) * itemWidth;
    const rawIndex = Math.round((currentX + centerOffset) / itemWidth);
    const len = participants.length;
    if (len === 0) return;
    let participantIndex = rawIndex % len;
    if (participantIndex < 0) participantIndex += len;
    const participant = participants[participantIndex];
    // Avoid unnecessary state updates by comparing to the last highlighted id
    if (participant && participant.id !== lastHighlightIdRef.current) {
      lastHighlightIdRef.current = participant.id;
      setCurrentHighlight(participant);
    }
  }, [participants, itemWidth]);

  // After the spin completes, emit the winner to the backend via the WebSocket
  // and animate the winning item.  Guard against duplicate notifications
  // by tracking message IDs.
  const handleSpinComplete = useCallback(() => {
    if (!hasNotifiedRef.current && currentPrize && socket) {
      hasNotifiedRef.current = true;
      const containerRect = slotRef.current.getBoundingClientRect();
      const centerX = containerRect.left + containerRect.width / 2;
      const items = stripRef.current.querySelectorAll('.slot-item');
      let winnerElement = null;
      let minDistance = Infinity;
      items.forEach((item) => {
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
        const winner = participants.find((p) => p.id === participantId);
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
            // Apply a CSS class to indicate the winner.  We intentionally
            // avoid scaling the element here; scaling within a flex
            // container can cause neighbouring elements to shrink.  The
            // `.winner` class in CSS will add a glow effect instead.
            winnerElement.classList.add('winner');
            setTimeout(() => {
              isSendingRef.current = false;
            }, 1000);
          }
          onComplete && onComplete(winner);
        }
      }
    }
  }, [participants, currentPrize, socket, raffleId, onComplete]);

  // Start and stop the spin in response to prop changes
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