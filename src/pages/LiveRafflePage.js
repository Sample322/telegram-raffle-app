import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import api from '../services/api';
import SlotReelComponent from '../components/SlotReelComponent';
import { toast } from 'react-hot-toast';

function LiveRafflePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [raffle, setRaffle] = useState(null);
  const [participants, setParticipants] = useState([]);
  const [currentRound, setCurrentRound] = useState(null);
  const [winners, setWinners] = useState([]);
  const [isSpinning, setIsSpinning] = useState(false);
  const [socket, setSocket] = useState(null);
  const [countdown, setCountdown] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  useEffect(() => {
    loadRaffleData();
    connectWebSocket();

    return () => {
      if (socket) {
        socket.close();
      }
    };
  }, [id]);

  const loadRaffleData = async () => {
    try {
      const [raffleRes, participantsRes] = await Promise.all([
        api.get(`/raffles/${id}`),
        api.get(`/raffles/${id}/participants`)
      ]);
      
      setRaffle(raffleRes.data);
      setParticipants(participantsRes.data);
      
      // Check if we have any previous winners
      if (raffleRes.data.is_completed) {
        const completedRes = await api.get('/raffles/completed?limit=50');
        const completedRaffle = completedRes.data.find(r => r.id === parseInt(id));
        if (completedRaffle && completedRaffle.winners) {
          setWinners(completedRaffle.winners);
        }
      }
      
      setLoading(false);
    } catch (error) {
      console.error('Error loading raffle:', error);
      toast.error('Ошибка загрузки розыгрыша');
      setLoading(false);
    }
  };

  const connectWebSocket = () => {
  // Убедитесь что используется правильный протокол и путь
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = process.env.REACT_APP_WS_URL 
    ? `${process.env.REACT_APP_WS_URL}/api/ws/${id}`
    : `${protocol}//${window.location.host}/api/ws/${id}`;
    
  console.log('Connecting to WebSocket:', wsUrl);
    
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('Connected to WebSocket');
      setConnectionStatus('connected');
      
      // Send ping every 30 seconds to keep connection alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
      
      ws.pingInterval = pingInterval;
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('WebSocket message:', data);
      
      switch (data.type) {
        case 'connection_established':
          if (data.raffle.is_completed) {
            setConnectionStatus('completed');
          }
          break;
          
        case 'raffle_starting':
          toast.success('Розыгрыш начинается!');
          break;
          
        case 'wheel_start':
          let orderedParticipants = [];
          if (data.participant_order && data.participant_order.length > 0) {
            orderedParticipants = data.participant_order.map(tid => {
              const participant = data.participants.find(p => p.id === tid);
              if (!participant) {
                console.error(`Participant with id ${tid} not found in participants list`);
              }
              return participant;
            }).filter(Boolean);
          } else {
            console.error('No participant_order received from backend!');
            orderedParticipants = data.participants;
          }
          
          console.log('Slot participants order:', orderedParticipants.map(p => ({ id: p.id, username: p.username })));
          console.log('Target offset from server:', data.target_offset);

          setCurrentRound({
            position: data.position,
            prize: data.prize,
            participants: orderedParticipants,
            targetOffset: data.target_offset  // Изменено с targetAngle
          });
          setIsSpinning(true);
          toast(`🎰 Разыгрывается ${data.position} место!`);
          break;
         
        case 'winner_confirmed':
          setWinners(prev => {
            const updated = [...prev];
            const existingIndex = updated.findIndex(w => w.position === data.position);
            if (existingIndex >= 0) {
              updated[existingIndex] = data;
            } else {
              updated.push(data);
            }
            return updated;
          });
          setIsSpinning(false);
          toast.success(`🎉 Победитель ${data.position} места: @${data.winner.username || data.winner.first_name}!`);
          break;
                    // В switch statement для ws.onmessage добавить:
          case 'round_complete':
            console.log(`Round ${data.position} completed`);
            // Обновляем состояние для следующего раунда
          setCurrentRound(prev => {
            if (prev && prev.position === data.position) {
              return null; // Сбрасываем только если это тот же раунд
            }
            return prev;
          });
          setIsSpinning(false);
          // Обновляем участников, исключая победителя
          if (data.winner_id) {
            setParticipants(prev => prev.filter(p => p.telegram_id !== data.winner_id));
          }
            break;
        case 'raffle_complete':
          setWinners(data.winners);
          setConnectionStatus('completed');
          setCurrentRound(null);
          setIsSpinning(false);
          toast.success('🎊 Розыгрыш завершен!');
          // Отключаем WebSocket после завершения
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.close();}
          break;
          
        case 'countdown':
          setCountdown(data.seconds);
          break;
          
        case 'error':
          // останавливаем вращение и очищаем текущий раунд
          setIsSpinning(false);
          setCurrentRound(null);
          setConnectionStatus('error'); // при желании можно отобразить статус "ошибка"
          toast.error(data.message || 'Произошла ошибка');
          break;

          
        default:
          break;
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnectionStatus('error');
      toast.error('Ошибка подключения');
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setConnectionStatus('disconnected');
      
      // Clear ping interval
      if (ws.pingInterval) {
        clearInterval(ws.pingInterval);
      }
      
      // Try to reconnect after 5 seconds if raffle is not completed
      if (!raffle?.is_completed) {
        setTimeout(() => {
          console.log('Attempting to reconnect...');
          connectWebSocket();
        }, 5000);
      }
    };

    setSocket(ws);
  };

  const formatCountdown = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gradient-to-br from-purple-600 to-blue-600">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4"></div>
          <p className="text-white">Загрузка розыгрыша...</p>
        </div>
      </div>
    );
  }

  if (!raffle) {
    return (
      <div className="min-h-screen bg-gray-50 p-4">
        <div className="container mx-auto text-center">
          <p className="text-gray-600">Розыгрыш не найден</p>
          <button
            onClick={() => navigate('/')}
            className="mt-4 text-blue-600 hover:underline"
          >
            Вернуться на главную
          </button>
        </div>
      </div>
    );
  }

  /* -------------------------------------------------------------
   Формируем список участников для колеса,
   исключая тех, кто уже есть в winners.
------------------------------------------------------------- */

  const eliminatedIds = winners.map(
    w => (
      (w.winner?.id) ||          // если winner приходит так
      (w.user?.telegram_id) ||   // или так
      (w.user?.id)               // или так
    )
  );

  const wheelParticipants =
    (currentRound?.participants || participants.map(p => ({
      id: p.telegram_id,
      username: p.username,
      first_name: p.first_name,
      last_name: p.last_name
    })))
    .filter(p => !eliminatedIds.includes(p.id));


  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-600 to-blue-600 text-white">
      {/* Navigation Header */}
      <div className="sticky top-0 z-50 bg-white/10 backdrop-blur-sm">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center">
            <button
              onClick={() => navigate('/')}
              className="p-2 rounded-lg hover:bg-white/20 transition-colors"
              aria-label="Назад"
            >
              <ArrowLeftIcon className="h-5 w-5 text-white" />
            </button>
            <h1 className="ml-3 text-lg font-semibold text-white truncate">{raffle.title}</h1>
          </div>
          
          {/* Connection status indicator */}
          <div className="flex items-center space-x-2">
            <div className={`w-2 h-2 rounded-full ${
              connectionStatus === 'connected' ? 'bg-green-400' : 
              connectionStatus === 'error' ? 'bg-red-400' : 'bg-yellow-400'
            } animate-pulse`}></div>
            <span className="text-xs opacity-75">
              {connectionStatus === 'connected' ? 'Подключено' :
               connectionStatus === 'error' ? 'Ошибка' : 
               connectionStatus === 'completed' ? 'Завершен' : 'Подключение...'}
            </span>
          </div>
        </div>
      </div>

      <div className="container mx-auto p-4">
        {/* Countdown display */}
        {countdown && countdown > 0 && (
          <div className="text-center mb-8 animate-pulse">
            <p className="text-2xl mb-2">🎰 Розыгрыш начнется через:</p>
            <p className="text-6xl font-bold">{formatCountdown(countdown)}</p>
          </div>
        )}

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Slot Machine Section */}
            <div className="lg:col-span-2">
              <div className="bg-white rounded-lg p-8 shadow-2xl">
                {wheelParticipants.length > 0 ? (
                  <SlotReelComponent
                    participants={wheelParticipants}
                    isSpinning={isSpinning}
                    currentPrize={currentRound ? { position: currentRound.position, prize: currentRound.prize } : null}
                    socket={socket}
                    raffleId={id}
                    wheelSpeed={raffle?.wheel_speed || 'fast'}
                    targetOffset={currentRound?.targetOffset}  // Изменено с targetAngle
                    onComplete={(winner) => console.log('Winner selected:', winner)}
                  />
                ) : (
                  <div className="text-center text-gray-600 py-20">
                    <p className="text-xl mb-4">Ожидание участников...</p>
                    <p>Текущее количество участников: {participants.length}</p>
                    {participants.length < Object.keys(raffle.prizes).length && (
                      <p className="text-sm text-red-600 mt-2">
                        Минимум участников для розыгрыша: {Object.keys(raffle.prizes).length}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>

          {/* Winners Table */}
          <div className="bg-white/10 backdrop-blur rounded-lg p-6">
            <h2 className="text-2xl font-semibold mb-4">🏆 Призовые места</h2>
            <div className="space-y-3">
              {Object.entries(raffle.prizes)
                .sort(([a], [b]) => parseInt(a) - parseInt(b)) // Сортируем по возрастанию (1, 2, 3...)
                .map(([position, prize]) => {
                const winner = winners.find(w => w.position === parseInt(position));
                const isCurrentRound = currentRound?.position === parseInt(position);
                
                return (
                  <div 
                    key={position} 
                    className={`p-4 rounded-lg transition-all duration-300 ${
                      winner ? 'bg-green-500/30 scale-105' : 
                      isCurrentRound ? 'bg-yellow-500/30 animate-pulse' : 
                      'bg-white/10'
                    }`}
                  >
                    <div className="font-semibold flex items-center justify-between">
                      <span>{position} место</span>
                      {position === '1' && '🥇'}
                      {position === '2' && '🥈'}
                      {position === '3' && '🥉'}
                    </div>
                    <div className="text-sm opacity-90">{prize}</div>
                    {winner && (
                      <div className="text-lg mt-2 font-bold">
                        🎉 @{winner.winner?.username || winner.user?.username || 'Победитель'}
                      </div>
                    )}
                    {isCurrentRound && !winner && (
                      <div className="text-sm mt-2 animate-pulse">
                        🎰 Разыгрывается сейчас...
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Participants Count */}
        <div className="mt-8 bg-white/10 backdrop-blur rounded-lg p-6 text-center">
          <h3 className="text-2xl font-semibold mb-2">👥 Всего участников</h3>
          <p className="text-4xl font-bold">{participants.length}</p>
        </div>

        {/* Completed message */}
        {connectionStatus === 'completed' && (
          <div className="mt-8 text-center">
            <div className="bg-white/20 backdrop-blur rounded-lg p-8">
              <h2 className="text-3xl font-bold mb-4">🎊 Розыгрыш завершен!</h2>
              <p className="text-xl mb-4">Поздравляем всех победителей!</p>
              <button
                onClick={() => navigate('/')}
                className="bg-white text-purple-600 px-6 py-3 rounded-lg font-semibold hover:bg-gray-100 transition-colors"
              >
                Вернуться на главную
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default LiveRafflePage;