import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import api from '../services/api';
import SlotMachineComponent from '../components/SlotMachineComponent';
import { toast } from 'react-hot-toast';

/**
 * LiveRafflePage displays a real‑time raffle to the user. It fetches the
 * raffle details, subscribes to live WebSocket events and renders either
 * a spinning wheel or a slot machine depending on the raffle's display
 * type. The page also shows the list of prizes, highlights the current
 * round and indicates the overall connection status.
 */
function LiveRafflePage() {
  const { id } = useParams();
  const navigate = useNavigate();

  // State for raffle metadata and participants
  const [raffle, setRaffle] = useState(null);
  const [participants, setParticipants] = useState([]);
  const [currentRound, setCurrentRound] = useState(null);
  const [winners, setWinners] = useState([]);

  // UI state
  const [isSpinning, setIsSpinning] = useState(false);
  const [socket, setSocket] = useState(null);
  const [countdown, setCountdown] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connectionStatus, setConnectionStatus] = useState('connecting');

  // Fetch raffle and participant data when the page mounts or id changes
  useEffect(() => {
    async function loadRaffleData() {
      try {
        const [raffleRes, participantsRes] = await Promise.all([
          api.get(`/raffles/${id}`),
          api.get(`/raffles/${id}/participants`),
        ]);
        setRaffle(raffleRes.data);
        setParticipants(participantsRes.data);

        // If the raffle is already completed, fetch winners
        if (raffleRes.data.is_completed) {
          const completedRes = await api.get('/raffles/completed?limit=50');
          const completedRaffle = completedRes.data.find((r) => r.id === Number(id));
          if (completedRaffle && completedRaffle.winners) {
            setWinners(completedRaffle.winners);
          }
        }
      } catch (error) {
        console.error('Error loading raffle:', error);
        toast.error('Ошибка загрузки розыгрыша');
      } finally {
        setLoading(false);
      }
    }

    function connectWebSocket() {
      const wsUrl = `${process.env.REACT_APP_WS_URL || 'ws://localhost:8000'}/api/ws/${id}`;
      const ws = new WebSocket(wsUrl);
      setConnectionStatus('connecting');

      ws.onopen = () => {
        setConnectionStatus('connected');
        // Keep the connection alive with periodic pings
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
        ws.pingInterval = pingInterval;
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case 'connection_established':
            if (data.raffle.is_completed) {
              setConnectionStatus('completed');
            }
            break;
          case 'raffle_starting':
            toast.success('Розыгрыш начинается!');
            break;
          case 'slot_start': {
            // формируем список участников от сервера
            let orderedParticipants = [];
            if (data.participants && data.participants.length > 0) {
              orderedParticipants = data.participants;
            }

            // исключаем тех, кто уже выиграл
            const currentWinnerIds = winners.map((w) =>
              w.winner?.id || w.user?.telegram_id || w.user?.id
            );
            const availableParticipants = orderedParticipants.filter(
              (p) => !currentWinnerIds.includes(p.id)
            );

            // находим индекс победителя (для подсветки в таблице, не обязателен)
            const predId = data.predetermined_winner_id;
            let targetWinnerIndex = null;
            const idx = availableParticipants.findIndex(
              (p) => String(p.id) === String(predId)
            );
            targetWinnerIndex = idx >= 0 ? idx : null;

            setCurrentRound({
              position: data.position,
              prize: data.prize,
              participants: availableParticipants,
              predeterminedWinnerId: predId,
              predeterminedWinner: data.predetermined_winner,
              targetWinnerIndex, // необязательное поле для подсветки
            });

            setIsSpinning(true);
            toast(`🎰 Разыгрывается ${data.position} место!`);
            console.log('Round started:', {
              position: data.position,
              winnerId: predId,
              availableParticipants: availableParticipants.map((p) => ({
                id: p.id,
                name: p.username,
              })),
            });
            break;
          }

          case 'winner_confirmed': {
            // Избегаем дубликатов
            const winnerKey = `${data.position}_${data.winner.id}`;
            const processedKey = `processed_winners_${id}`;
            if (!window[processedKey]) {
              window[processedKey] = new Set();
            }
            if (window[processedKey].has(winnerKey)) {
              break;
            }
            window[processedKey].add(winnerKey);
            
            // Обновляем список победителей
            setWinners((prev) => {
              const updated = [...prev];
              const idx = updated.findIndex((w) => w.position === data.position);
              if (idx >= 0) {
                updated[idx] = data;
              } else {
                updated.push(data);
              }
              return updated;
            });
            
            // ВАЖНО: Удаляем победителя из списка участников для следующих раундов
            setParticipants((prev) => prev.filter((p) => p.telegram_id !== data.winner.id));
            
            setIsSpinning(false);
            if (!data.auto_selected) {
              toast.success(`🎉 Победитель ${data.position} места: @${data.winner.username || data.winner.first_name}!`);
            }
            break;
          }
          case 'round_complete': {
            // Reset current round when a round is complete
            setCurrentRound((prev) => {
              if (prev && prev.position === data.position) {
                return null;
              }
              return prev;
            });
            setIsSpinning(false);
            // Remove the winner from the participants list for subsequent rounds
            if (data.winner_id) {
              setParticipants((prev) => prev.filter((p) => p.telegram_id !== data.winner_id));
            }
            break;
          }
          case 'raffle_complete':
            setWinners(data.winners);
            setConnectionStatus('completed');
            setCurrentRound(null);
            setIsSpinning(false);
            toast.success('🎊 Розыгрыш завершен!');
            if (ws.readyState === WebSocket.OPEN) {
              ws.close();
            }
            break;
          case 'countdown':
            setCountdown(data.seconds);
            break;
          case 'error':
            toast.error(data.message);
            break;
          default:
            break;
        }
      };

      ws.onerror = () => {
        setConnectionStatus('error');
        toast.error('Ошибка подключения');
      };

      ws.onclose = () => {
        // Clear ping interval
        if (ws.pingInterval) {
          clearInterval(ws.pingInterval);
        }
        setConnectionStatus('disconnected');
        // Attempt to reconnect if the raffle is not completed
        if (!raffle?.is_completed) {
          setTimeout(() => {
            connectWebSocket();
          }, 5000);
        }
      };

      setSocket(ws);
      // Return the created WebSocket instance so callers can manage its lifecycle.
      return ws;
    }

    // Initial data fetch and socket connection.
    // We avoid capturing `socket` from state in this effect to prevent
    // unnecessary re‑runs when it changes. Instead, we track the WebSocket
    // instance in a local variable and clean it up on unmount.
    loadRaffleData();
    const wsInstance = connectWebSocket();
    // Cleanup on unmount
    return () => {
      if (wsInstance) {
        wsInstance.close();
      }
    };
  }, [id]);

  /**
   * Helper to format a countdown in seconds into mm:ss.
   * @param {number} seconds
   */
  const formatCountdown = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  // Show a loading state while fetching data
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <p className="text-xl font-medium">Загрузка розыгрыша...</p>
      </div>
    );
  }

  // Show a not found message if the raffle doesn't exist
  if (!raffle) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center space-y-4">
        <p className="text-xl font-medium">Розыгрыш не найден</p>
        <button
          onClick={() => navigate('/')}
          className="mt-2 text-blue-600 hover:underline"
        >
          Вернуться на главную
        </button>
      </div>
    );
  }

  // Filter out participants who have already won
  const eliminatedIds = winners.map(
    (w) => w.winner?.id || w.user?.telegram_id || w.user?.id
  );
  const wheelParticipants =
    (currentRound?.participants ||
      participants.map((p) => ({
        id: p.telegram_id,
        username: p.username,
        first_name: p.first_name,
        last_name: p.last_name,
      })))
      .filter((p) => !eliminatedIds.includes(p.id));

  return (
  <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
    <div className="p-4 space-y-6">
      {/* Navigation Header */}
      <div className="flex items-center space-x-2 bg-white/10 backdrop-blur-sm rounded-lg p-3">
        <button
          onClick={() => navigate('/')}
          className="p-2 rounded-lg hover:bg-white/20 transition-colors text-white"
          aria-label="Назад"
        >
          <ArrowLeftIcon className="w-5 h-5" />
        </button>
        <h1 className="text-2xl font-semibold text-white truncate">{raffle?.title}</h1>
        <div className="ml-auto text-sm font-medium px-3 py-1 rounded-full"
             style={{
               backgroundColor: connectionStatus === 'connected' ? '#10b981' : 
                              connectionStatus === 'error' ? '#ef4444' :
                              connectionStatus === 'completed' ? '#6366f1' : '#f59e0b',
               color: 'white'
             }}>
          {connectionStatus === 'connected' ? '🟢 Подключено' :
           connectionStatus === 'error' ? '🔴 Ошибка' :
           connectionStatus === 'completed' ? '✅ Завершен' : '🟡 Подключение...'}
        </div>
      </div>

      {/* Countdown display */}
      {countdown && countdown > 0 && (
        <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
          <p className="text-center text-lg text-white">
            🎰 Розыгрыш начнется через: <strong className="text-2xl text-yellow-300">{formatCountdown(countdown)}</strong>
          </p>
        </div>
      )}

      {/* Wheel/Slot Section */}
      <div className="flex justify-center">
          {wheelParticipants.length > 0 ? (
            <SlotMachineComponent
              participants={wheelParticipants}
              isSpinning={isSpinning}
              onComplete={(winner) => {
                console.log('Winner selected:', winner);
              }}
              currentPrize={
                currentRound
                  ? {
                      position: currentRound.position,
                      prize: currentRound.prize,
                    }
                  : null
              }
              socket={socket}
              raffleId={id}
              wheelSpeed={raffle?.wheel_speed || 'fast'}
              targetWinnerId={currentRound?.predeterminedWinnerId}
            />
          ) : (
          <div className="text-center space-y-2 bg-white/10 backdrop-blur-sm rounded-lg p-6">
            <p className="text-white text-lg">⏳ Ожидание участников...</p>
            <p className="text-white/80">
              Текущее количество участников: <strong className="text-xl">{participants.length}</strong>
              {participants.length < Object.keys(raffle?.prizes || {}).length && (
                <span className="block mt-2 text-yellow-300">
                  Минимум для розыгрыша: {Object.keys(raffle?.prizes || {}).length}
                </span>
              )}
            </p>
          </div>
        )}
      </div>

      {/* Winners Table */}
      <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
        <h2 className="text-xl font-semibold mb-3 text-white">🏆 Призовые места</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <tbody>
              {raffle && Object.entries(raffle.prizes)
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([position, prize]) => {
                  const winner = winners.find((w) => w.position === Number(position));
                  const isCurrentRound = currentRound?.position === Number(position);
                  const medal = position === '1' ? '🥇' : position === '2' ? '🥈' : position === '3' ? '🥉' : '🏅';
                  
                  return (
                    <tr key={position} 
                        className={`border-b border-white/10 ${
                          isCurrentRound ? 'bg-yellow-500/30' : 
                          winner ? 'bg-green-500/20' : ''
                        }`}>
                      <td className="px-3 py-2 font-medium text-white">
                        {medal} {position} место
                      </td>
                      <td className="px-3 py-2 text-white/90">{prize}</td>
                      <td className="px-3 py-2 text-white">
                        {winner ? (
                          <span className="text-green-300 font-semibold">
                            ✅ @{winner.winner?.username || winner.user?.username || 'Победитель'}
                          </span>
                        ) : isCurrentRound ? (
                          <span className="text-yellow-300 animate-pulse">🎰 Разыгрывается...</span>
                        ) : (
                          <span className="text-white/50">Ожидает розыгрыша</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Participants Count */}
      <div className="text-center bg-white/10 backdrop-blur-sm rounded-lg p-3">
        <p className="text-white">
          👥 Всего участников: <strong className="text-xl text-yellow-300">{participants.length}</strong>
        </p>
      </div>

      {/* Completed message */}
      {connectionStatus === 'completed' && (
        <div className="bg-white/10 backdrop-blur-sm rounded-lg p-6 text-center space-y-3">
          <p className="text-2xl text-white font-bold">🎊 Розыгрыш завершен!</p>
          <p className="text-white/90">Поздравляем всех победителей!</p>
          <button
            onClick={() => navigate('/')}
            className="bg-white text-purple-600 px-6 py-2 rounded-lg font-semibold hover:bg-gray-100 transition-colors"
          >
            Вернуться на главную
          </button>
        </div>
      )}
    </div>
  </div>
);
}

export default LiveRafflePage;