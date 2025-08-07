import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import api from '../services/api';
import WheelComponent from '../components/WheelComponent';
import { toast } from 'react-hot-toast';
import SlotMachineComponent from '../components/SlotMachineComponent';

/**
 * ErrorBoundary отлавливает ошибки в потомках и
 * показывает пользователю дружественное сообщение вместо сломанной страницы.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('LiveRafflePage error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-gray-50 p-4 flex items-center justify-center">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-red-600 mb-4">Произошла ошибка</h2>
            <p className="text-gray-600 mb-4">{this.state.error?.message || 'Неизвестная ошибка'}</p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Перезагрузить страницу
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

/**
 * Страница живого розыгрыша. Подключается к WebSocket для получения событий,
 * запускает слот‑машину и отображает список победителей.
 */
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

  // при монтировании загружаем данные и подключаемся к WebSocket
  useEffect(() => {
    loadRaffleData();
    connectWebSocket();
    return () => {
      if (socket) {
        socket.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // запрос на сервер за данными розыгрыша и участниками
  const loadRaffleData = async () => {
    try {
      const [raffleRes, participantsRes] = await Promise.all([
        api.get(`/raffles/${id}`),
        api.get(`/raffles/${id}/participants`),
      ]);
      setRaffle(raffleRes.data);
      setParticipants(participantsRes.data);
      // если розыгрыш завершён — подгружаем победителей
      if (raffleRes.data.is_completed) {
        const completedRes = await api.get('/raffles/completed?limit=50');
        const completedRaffle = completedRes.data.find((r) => r.id === parseInt(id));
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

  // подключение к WebSocket и обработка входящих сообщений
  const connectWebSocket = () => {
    console.log('Starting WebSocket connection for raffle:', id);
    const wsUrl = `${process.env.REACT_APP_WS_URL || 'ws://localhost:8000'}/api/ws/${id}`;
    console.log('WebSocket URL:', wsUrl);
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => {
      console.log('Connected to WebSocket');
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
      console.log('WebSocket message:', data);
      // каждый case оборачиваем в {}, чтобы переменные не «утекали»
      switch (data.type) {
        case 'connection_established': {
          if (data.raffle.is_completed) {
            setConnectionStatus('completed');
          }
          break;
        }
        case 'raffle_starting': {
          toast.success('Розыгрыш начинается!');
          break;
        }
        case 'wheel_start': {
          const orderedParticipants = data.participants || [];
          const predeterminedIndex = data.predetermined_winner_index;
          const predeterminedWinner = data.predetermined_winner;
          console.log('Wheel start data:', {
            position: data.position,
            participantsCount: orderedParticipants.length,
            predeterminedIndex,
            predeterminedWinner,
          });
          if (orderedParticipants.length === 0) {
            console.error('No participants received from server');
            toast.error('Ошибка: нет участников');
            break;
          }
          setCurrentRound({
            position: data.position,
            prize: data.prize,
            participants: orderedParticipants,
            targetWinnerIndex: predeterminedIndex !== undefined ? predeterminedIndex : 0,
            predeterminedWinner: predeterminedWinner,
          });
          setIsSpinning(true);
          toast(`🎰 Разыгрывается ${data.position} место!`);
          break;
        }
        case 'winner_confirmed': {
          const winnerKey = `${data.position}_${data.winner.id}`;
          const processedWinnersKey = `processed_winners_${id}`;
          if (!window[processedWinnersKey]) {
            window[processedWinnersKey] = new Set();
          }
          if (window[processedWinnersKey].has(winnerKey)) {
            console.log('Duplicate winner notification ignored:', winnerKey);
            break;
          }
          window[processedWinnersKey].add(winnerKey);
          setWinners((prev) => {
            const updated = [...prev];
            const existingIndex = updated.findIndex((w) => w.position === data.position);
            if (existingIndex >= 0) {
              updated[existingIndex] = data;
            } else {
              updated.push(data);
            }
            return updated;
          });
          setIsSpinning(false);
          if (!data.auto_selected) {
            toast.success(
              `🎉 Победитель ${data.position} места: @${data.winner.username || data.winner.first_name}!`
            );
          }
          break;
        }
        case 'round_complete': {
          console.log(`Round ${data.position} completed`);
          setCurrentRound((prev) => {
            if (prev && prev.position === data.position) {
              return null;
            }
            return prev;
          });
          setIsSpinning(false);
          if (data.winner_id) {
            setParticipants((prev) => prev.filter((p) => p.telegram_id !== data.winner_id));
          }
          break;
        }
        case 'raffle_complete': {
          setWinners(data.winners);
          setConnectionStatus('completed');
          setCurrentRound(null);
          setIsSpinning(false);
          toast.success('🎊 Розыгрыш завершен!');
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.close();
          }
          break;
        }
        case 'countdown': {
          setCountdown(data.seconds);
          break;
        }
        case 'error': {
          toast.error(data.message);
          break;
        }
        default: {
          break;
        }
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
      if (ws.pingInterval) {
        clearInterval(ws.pingInterval);
      }
      if (!raffle?.is_completed) {
        setTimeout(() => {
          console.log('Attempting to reconnect...');
          connectWebSocket();
        }, 5000);
      }
    };
    setSocket(ws);
  };

  // форматируем обратный отсчёт
  const formatCountdown = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  // отображаем спиннер во время загрузки
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
  // если розыгрыш не найден
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

  // формируем список участников (исключаем победителей)
  const eliminatedIds = winners.map((w) => (w.winner?.id) || (w.user?.telegram_id) || (w.user?.id));
  const wheelParticipants = (
    currentRound?.participants ||
    participants.map((p) => ({
      id: p.telegram_id,
      username: p.username,
      first_name: p.first_name,
      last_name: p.last_name,
    }))
  ).filter((p) => !eliminatedIds.includes(p.id));

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-600 to-blue-600 text-white">
      {/* Хедер с навигацией и статусом соединения */}
      <div className="sticky top-0 z-50 bg-white/10 backdrop-blur-sm">
        <div className="container mx-auto px-2 py-3 flex items-center justify-between">
          <div className="flex items-center">
            <button
              onClick={() => navigate('/')}
              className="p-2 rounded-lg hover:bg-white/20 transition-colors"
              aria-label="Назад"
            >
              <ArrowLeftIcon className="h-5 w-5 text-white" />
            </button>
            <h1 className="ml-3 text-lg font-semibold text-white truncate max-w-[200px]">
              {raffle.title}
            </h1>
          </div>
          {/* индикатор подключения */}
          <div className="flex items-center space-x-1">
            <div
              className={`w-2 h-2 rounded-full ${
                connectionStatus === 'connected'
                  ? 'bg-green-400'
                  : connectionStatus === 'error'
                  ? 'bg-red-400'
                  : connectionStatus === 'completed'
                  ? 'bg-purple-400'
                  : 'bg-yellow-400'
              } animate-pulse`}
            ></div>
            <span className="text-xs opacity-75 hidden sm:inline">
              {connectionStatus === 'connected'
                ? 'Подключено'
                : connectionStatus === 'error'
                ? 'Ошибка'
                : connectionStatus === 'completed'
                ? 'Завершен'
                : 'Подключение...'}
            </span>
          </div>
        </div>
      </div>
      <div className="container mx-auto px-2 py-4 max-w-7xl">
        {countdown && countdown > 0 && (
          <div className="text-center mb-6 animate-pulse">
            <p className="text-xl mb-2">🎰 Розыгрыш начнется через:</p>
            <p className="text-5xl font-bold">{formatCountdown(countdown)}</p>
          </div>
        )}
        <div className="grid lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <div
              className="bg-white rounded-lg shadow-2xl"
              style={{ width: '100%', maxWidth: '100%', overflow: 'visible' }}
            >
              {wheelParticipants.length > 0 ? (
                raffle?.display_type === 'slot' ? (
                  <SlotMachineComponent
                    participants={currentRound?.participants || wheelParticipants}
                    isSpinning={isSpinning}
                    currentPrize={
                      currentRound
                        ? { position: currentRound.position, prize: currentRound.prize }
                        : null
                    }
                    socket={socket}
                    raffleId={id}
                    wheelSpeed={raffle?.wheel_speed || 'fast'}
                    targetWinnerIndex={currentRound?.targetWinnerIndex}
                    onComplete={(winner) => {
                      console.log('Animation complete, winner:', winner);
                      setIsSpinning(false);
                    }}
                  />
                ) : (
                  <div className="p-4 md:p-6">
                    <WheelComponent
                      participants={currentRound?.participants || wheelParticipants}
                      isSpinning={isSpinning}
                      currentPrize={
                        currentRound
                          ? { position: currentRound.position, prize: currentRound.prize }
                          : null
                      }
                      socket={socket}
                      raffleId={id}
                      wheelSpeed={raffle?.wheel_speed || 'fast'}
                      targetAngle={currentRound?.targetAngle}
                      onComplete={(winner) => {
                        console.log('Animation complete, winner:', winner);
                        setIsSpinning(false);
                      }}
                    />
                  </div>
                )
              ) : (
                <div className="text-center text-gray-600 py-20 px-4">
                  <p className="text-xl mb-4">Ожидание участников...</p>
                  <p>Текущее количество участников: {participants.length}</p>
                  {participants.length < Object.keys(raffle.prizes || {}).length && (
                    <p className="text-sm text-red-600 mt-2">
                      Минимум участников для розыгрыша: {Object.keys(raffle.prizes || {}).length}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
          {/* список призов и победителей */}
          <div className="bg-white/10 backdrop-blur rounded-lg p-4">
            <h2 className="text-xl font-semibold mb-3">🏆 Призовые места</h2>
            <div className="space-y-2">
              {Object.entries(raffle.prizes)
                .sort(([a], [b]) => parseInt(a) - parseInt(b))
                .map(([position, prize]) => {
                  const winner = winners.find((w) => w.position === parseInt(position));
                  const isCurrentRound = currentRound?.position === parseInt(position);
                  return (
                    <div
                      key={position}
                      className={`p-3 rounded-lg transition-all duration-300 ${
                        winner
                          ? 'bg-green-500/30 scale-105'
                          : isCurrentRound
                          ? 'bg-yellow-500/30 animate-pulse'
                          : 'bg-white/10'
                      }`}
                    >
                      <div className="font-semibold flex items-center justify-between text-sm">
                        <span>{position} место</span>
                        {position === '1' && '🥇'}
                        {position === '2' && '🥈'}
                        {position === '3' && '🥉'}
                      </div>
                      <div className="text-xs opacity-90 mt-1">{prize}</div>
                      {winner && (
                        <div className="text-base mt-2 font-bold">
                          🎉 @{winner.winner?.username || winner.user?.username || 'Победитель'}
                        </div>
                      )}
                      {isCurrentRound && !winner && (
                        <div className="text-xs mt-2 animate-pulse">🎰 Разыгрывается...</div>
                      )}
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
        <div className="mt-6 bg-white/10 backdrop-blur rounded-lg p-4 text-center">
          <h3 className="text-xl font-semibold mb-2">👥 Всего участников</h3>
          <p className="text-3xl font-bold">{participants.length}</p>
        </div>
        {connectionStatus === 'completed' && (
          <div className="mt-6 text-center">
            <div className="bg-white/20 backdrop-blur rounded-lg p-6">
              <h2 className="text-2xl font-bold mb-3">🎊 Розыгрыш завершен!</h2>
              <p className="text-lg mb-4">Поздравляем всех победителей!</p>
              <button
                onClick={() => navigate('/')}
                className="bg-white text-purple-600 px-6 py-2 rounded-lg font-semibold hover:bg-gray-100 transition-colors"
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

// экспортируем страницу, обёрнутую в ErrorBoundary
export default function LiveRafflePageWithErrorBoundary(props) {
  return (
    <ErrorBoundary>
      <LiveRafflePage {...props} />
    </ErrorBoundary>
  );
}
