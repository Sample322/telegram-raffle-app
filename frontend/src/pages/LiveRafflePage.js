import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import api from '../services/api';
import SlotMachineComponent from '../components/SlotMachineComponent';
import { toast } from 'react-hot-toast';

function LiveRafflePage() {
  const { id } = useParams();
  const navigate = useNavigate();

  // состояние для данных розыгрыша
  const [raffle, setRaffle] = useState(null);
  const [initialParticipants, setInitialParticipants] = useState([]);
  const [currentParticipants, setCurrentParticipants] = useState([]);
  const [currentRound, setCurrentRound] = useState(null);
  const [winners, setWinners] = useState([]);

  // состояние UI
  const [isSpinning, setIsSpinning] = useState(false);
  const [socket, setSocket] = useState(null);
  const [countdown, setCountdown] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connectionStatus, setConnectionStatus] = useState('connecting');

  // КРИТИЧЕСКИ ВАЖНО: отслеживание round_seq и очередь событий
  const lastProcessedRoundRef = useRef(0);
  const eventQueueRef = useRef([]);
  const isProcessingRef = useRef(false);
  const processedWinnersRef = useRef(new Set());

  // загрузка деталей розыгрыша
  useEffect(() => {
    async function loadData() {
      try {
        const [raffleRes, participantsRes] = await Promise.all([
          api.get(`/raffles/${id}`),
          api.get(`/raffles/${id}/participants`)
        ]);
        setRaffle(raffleRes.data);
        
        // Сохраняем начальных участников для предпоказа
        const formattedParticipants = participantsRes.data.map(p => ({
          id: p.telegram_id,
          username: p.username,
          first_name: p.first_name,
          last_name: p.last_name
        }));
        
        setInitialParticipants(formattedParticipants);
        setCurrentParticipants(formattedParticipants);

        if (raffleRes.data.is_completed) {
          const completedRes = await api.get('/raffles/completed?limit=50');
          const completedRaffle = completedRes.data.find(r => r.id === Number(id));
          if (completedRaffle && completedRaffle.winners) {
            setWinners(completedRaffle.winners);
          }
        }
      } catch (e) {
        console.error(e);
        toast.error('Ошибка загрузки розыгрыша');
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [id]);

  // НОВОЕ: Последовательная обработка событий из очереди
  const processEventQueue = async () => {
    if (isProcessingRef.current || eventQueueRef.current.length === 0) {
      return;
    }

    isProcessingRef.current = true;
    
    while (eventQueueRef.current.length > 0) {
      const event = eventQueueRef.current.shift();
      
      // Пропускаем устаревшие события
      if (event.round_seq && event.round_seq <= lastProcessedRoundRef.current) {
        console.log(`Skipping outdated event with round_seq ${event.round_seq}`);
        continue;
      }

      await processEvent(event);
      
      // Ждем завершения анимации если она запущена
      if (event.type === 'slot_start') {
        // Ждем пока анимация не завершится
        while (isSpinning) {
          await new Promise(resolve => setTimeout(resolve, 100));
        }
      }
    }
    
    isProcessingRef.current = false;
  };

  // Обработка одного события
  const processEvent = async (data) => {
    console.log(`Processing event: ${data.type}, round_seq: ${data.round_seq}`);
    
    switch (data.type) {
      case 'connection_established':
        if (data.raffle.is_completed) {
          setConnectionStatus('completed');
        }
        // Синхронизируем round_seq при подключении
        if (data.round_seq !== undefined) {
          lastProcessedRoundRef.current = data.round_seq;
        }
        break;

      case 'raffle_starting':
        toast.success('Розыгрыш начинается!');
        // Сбрасываем состояние при начале нового розыгрыша
        lastProcessedRoundRef.current = 0;
        processedWinnersRef.current.clear();
        eventQueueRef.current = [];
        break;

      case 'slot_start': {
        // КРИТИЧЕСКИ ВАЖНО: используем ТОЛЬКО участников из события
        const serverParticipants = Array.isArray(data.participants) ? data.participants : [];
        const participantIds = data.participant_ids || [];
        
        console.log('=== SLOT START EVENT ===');
        console.log('Round seq:', data.round_seq);
        console.log('Position:', data.position);
        console.log('Participants count from server:', serverParticipants.length);
        console.log('Participant IDs from server:', participantIds);
        console.log('Predetermined winner ID:', data.predetermined_winner_id);
        console.log('Predetermined winner index:', data.predetermined_winner_index);
        console.log('========================');

        // ID победителя от сервера
        const winnerId = data.predetermined_winner_id;

        // Проверяем что победитель есть в списке
        const winnerExists = participantIds.includes(winnerId) || 
                            serverParticipants.some(p => String(p.id) === String(winnerId));
        
        if (!winnerExists) {
          console.error('CRITICAL: Winner not in participants list!', {
            winnerId,
            participantIds,
            serverParticipants: serverParticipants.map(p => p.id)
          });
          toast.error('Ошибка синхронизации данных розыгрыша');
          return;
        }

        // Обновляем состояние текущего раунда
        setCurrentRound({
          position: data.position,
          prize: data.prize,
          participants: serverParticipants, // ТОЛЬКО от сервера!
          participant_ids: participantIds,
          predeterminedWinnerId: winnerId,
          predeterminedWinner: data.predetermined_winner,
          predeterminedWinnerIndex: data.predetermined_winner_index,
          round_seq: data.round_seq
        });

        // НЕ обновляем currentParticipants здесь - это будет сделано после winner_confirmed
        
        setIsSpinning(true);
        lastProcessedRoundRef.current = data.round_seq;
        toast(`🎰 Разыгрывается ${data.position} место!`);
        break;
      }

      case 'winner_confirmed': {
        // Дедупликация с учетом round_seq
        const winnerKey = `${data.position}_${data.winner_id || data.winner.id}_${data.round_seq}`;
        if (processedWinnersRef.current.has(winnerKey)) {
          console.log(`Winner ${winnerKey} already processed, skipping`);
          return;
        }
        processedWinnersRef.current.add(winnerKey);

        console.log('=== WINNER CONFIRMED ===');
        console.log('Round seq:', data.round_seq);
        console.log('Position:', data.position);
        console.log('Winner ID:', data.winner_id || data.winner.id);

        // Проверяем что это событие для текущего раунда
        if (currentRound && currentRound.round_seq === data.round_seq) {
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

          // ВАЖНО: Обновляем список участников только после подтверждения победителя
          // и только если это событие соответствует текущему раунду
          setCurrentParticipants((prev) => {
            const winnerId = data.winner_id || data.winner.id;
            const filtered = prev.filter((p) => 
              String(p.id) !== String(winnerId)
            );
            console.log(`Removed winner ${winnerId} from participants, remaining: ${filtered.length}`);
            return filtered;
          });
          
          setIsSpinning(false);
          setCurrentRound(null); // Очищаем текущий раунд
          
          toast.success(`🎉 Победитель ${data.position} места: @${data.winner.username || data.winner.first_name}!`);
        } else {
          console.warn(`Received winner_confirmed for round ${data.round_seq} but current round is ${currentRound?.round_seq}`);
        }
        break;
      }

      case 'raffle_complete':
        setWinners(data.winners);
        setConnectionStatus('completed');
        setCurrentRound(null);
        setIsSpinning(false);
        toast.success('🎊 Розыгрыш завершен!');
        break;

      case 'countdown':
        setCountdown(data.seconds);
        break;

      case 'error':
        setConnectionStatus('error');
        setIsSpinning(false);
        toast.error(data.message || 'Ошибка');
        break;

      default:
        break;
    }
  };

  // подключение WebSocket
  useEffect(() => {
    const wsUrl = `${process.env.REACT_APP_WS_URL || 'ws://localhost:8000'}/api/ws/${id}`;
    const ws = new WebSocket(wsUrl);
    setConnectionStatus('connecting');

    ws.onopen = () => {
      setConnectionStatus('connected');
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
      ws.pingInterval = pingInterval;
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      // Добавляем событие в очередь
      eventQueueRef.current.push(data);
      
      // Запускаем обработку очереди
      processEventQueue();
    };

    ws.onerror = () => setConnectionStatus('error');
    ws.onclose = () => {
      if (ws.pingInterval) clearInterval(ws.pingInterval);
      setConnectionStatus('error');
    };
    setSocket(ws);

    return () => {
      if (ws.pingInterval) clearInterval(ws.pingInterval);
      ws.close();
    };
  }, [id, isSpinning]); // Добавил isSpinning в зависимости

  const formatCountdown = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  // ВАЖНО: Используем участников из currentRound для анимации, иначе currentParticipants для предпоказа
  const slotParticipants = currentRound?.participants || currentParticipants;

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <p className="text-xl font-medium">Загрузка розыгрыша...</p>
      </div>
    );
  }

  if (!raffle) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center space-y-4">
        <p className="text-xl font-medium">Розыгрыш не найден</p>
        <button onClick={() => navigate('/')} className="mt-2 text-blue-600 hover:underline">
          Вернуться на главную
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
      <div className="p-4 space-y-6">
        <div className="flex items-center space-x-2 bg-white/10 backdrop-blur-sm rounded-lg p-3">
          <button
            onClick={() => navigate('/')}
            className="p-2 rounded-lg hover:bg-white/20 transition-colors text-white"
            aria-label="Назад"
          >
            <ArrowLeftIcon className="w-5 h-5" />
          </button>
          <h1 className="text-2xl font-semibold text-white truncate">{raffle?.title}</h1>
          <div
            className="ml-auto text-sm font-medium px-3 py-1 rounded-full"
            style={{
              backgroundColor:
                connectionStatus === 'connected'
                  ? '#10b981'
                  : connectionStatus === 'error'
                  ? '#ef4444'
                  : connectionStatus === 'completed'
                  ? '#6366f1'
                  : '#f59e0b',
              color: 'white'
            }}
          >
            {connectionStatus === 'connected'
              ? '🟢 Подключено'
              : connectionStatus === 'error'
              ? '🔴 Ошибка'
              : connectionStatus === 'completed'
              ? '✅ Завершен'
              : '🟡 Подключение...'}
          </div>
        </div>

        {countdown && countdown > 0 && (
          <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
            <p className="text-center text-lg text-white">
              Розыгрыш начнется через:{' '}
              <strong className="text-2xl text-yellow-300">{formatCountdown(countdown)}</strong>
            </p>
          </div>
        )}

        <div className="flex justify-center">
          {slotParticipants.length > 0 ? (
            <SlotMachineComponent
              participants={slotParticipants}
              isSpinning={isSpinning}
              onComplete={(winner) => {
                console.log('Слот-машина остановилась, победитель:', winner);
                setIsSpinning(false); // Гарантируем сброс флага
              }}
              currentPrize={
                currentRound
                  ? { position: currentRound.position, prize: currentRound.prize }
                  : null
              }
              socket={socket}
              raffleId={id}
              wheelSpeed={raffle?.wheel_speed || 'fast'}
              targetWinnerId={currentRound?.predeterminedWinnerId}
              roundSeq={currentRound?.round_seq}
            />
          ) : (
            <div className="text-center space-y-2 bg-white/10 backdrop-blur-sm rounded-lg p-6">
              <p className="text-white text-lg">⏳ Ожидание участников...</p>
              <p className="text-white/80">
                Текущее количество участников:{' '}
                <strong className="text-xl">{currentParticipants.length}</strong>
                {currentParticipants.length < Object.keys(raffle?.prizes || {}).length && (
                  <span className="block mt-2 text-yellow-300">
                    Минимум для розыгрыша: {Object.keys(raffle?.prizes || {}).length}
                  </span>
                )}
              </p>
            </div>
          )}
        </div>

        <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
          <h2 className="text-xl font-semibold mb-3 text-white">🏆 Призовые места</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <tbody>
                {raffle &&
                  Object.entries(raffle.prizes)
                    .sort(([a], [b]) => Number(a) - Number(b))
                    .map(([position, prize]) => {
                      const winner = winners.find((w) => w.position === Number(position));
                      const isCurrent = currentRound?.position === Number(position);
                      const medal = position === '1' ? '🥇' : position === '2' ? '🥈' : position === '3' ? '🥉' : '🏅';
                      return (
                        <tr
                          key={position}
                          className={`border-b border-white/10 ${
                            isCurrent
                              ? 'bg-yellow-500/30'
                              : winner
                              ? 'bg-green-500/20'
                              : ''
                          }`}
                        >
                          <td className="px-3 py-2 font-medium text-white">
                            {medal} {position} место
                          </td>
                          <td className="px-3 py-2 text-white/90">{prize}</td>
                          <td className="px-3 py-2 text-white">
                            {winner ? (
                              <span className="text-green-300 font-semibold">
                                ✅ @{winner.winner?.username || winner.user?.username || 'Победитель'}
                              </span>
                            ) : isCurrent ? (
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

        <div className="text-center bg-white/10 backdrop-blur-sm rounded-lg p-3">
          <p className="text-white">
            Всего участников:{' '}
            <strong className="text-xl text-yellow-300">{currentParticipants.length}</strong>
          </p>
        </div>

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