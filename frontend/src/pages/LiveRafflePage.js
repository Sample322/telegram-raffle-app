// frontend/src/pages/LiveRafflePage.js - ИСПРАВЛЕННЫЙ ФАЙЛ

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import api from '../services/api';
import WheelComponent from '../components/WheelComponent';

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
      setLoading(false);
    } catch (error) {
      console.error('Error loading raffle:', error);
      setLoading(false);
    }
  };

  const connectWebSocket = () => {
    const wsUrl = `${process.env.REACT_APP_WS_URL || 'ws://localhost:8000'}/api/ws/${id}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('Connected to WebSocket');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'wheel_start':
          setCurrentRound({
            position: data.position,
            prize: data.prize,
            participants: data.participants
          });
          setIsSpinning(true);
          break;
          
        case 'winner_selected':
          setWinners(prev => [...prev, data]);
          setIsSpinning(false);
          break;
          
        case 'raffle_complete':
          setWinners(data.winners);
          break;
          
        case 'countdown':
          setCountdown(data.seconds);
          break;
          
        default:
          break;
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };

    setSocket(ws);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!raffle) {
    return (
      <div className="min-h-screen bg-gray-50 p-4">
        <div className="container mx-auto">
          <p className="text-center text-gray-600">Розыгрыш не найден</p>
        </div>
      </div>
    );
  }

  // Format participant data for the wheel
  const wheelParticipants = currentRound?.participants || participants.map(p => ({
    id: p.telegram_id,
    username: p.username || `${p.first_name} ${p.last_name || ''}`.trim()
  }));

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-600 to-blue-600 text-white">
      {/* Navigation Header */}
      <div className="sticky top-0 z-50 bg-white/10 backdrop-blur-sm">
        <div className="container mx-auto px-4 py-3 flex items-center">
          <button
            onClick={() => navigate('/')}
            className="p-2 rounded-lg hover:bg-white/20 transition-colors"
            aria-label="Назад"
          >
            <ArrowLeftIcon className="h-5 w-5 text-white" />
          </button>
          <h1 className="ml-3 text-lg font-semibold text-white truncate">{raffle.title}</h1>
        </div>
      </div>

      <div className="container mx-auto p-4">
        {countdown && countdown > 0 && (
          <div className="text-center mb-8">
            <p className="text-2xl">Розыгрыш начнется через:</p>
            <p className="text-6xl font-bold">{countdown}</p>
          </div>
        )}

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Wheel Section */}
          <div className="lg:col-span-2">
            {currentRound && (
              <div className="bg-white/10 backdrop-blur rounded-lg p-6 mb-4">
                <h2 className="text-2xl font-semibold mb-2">
                  Разыгрывается {currentRound.position} место
                </h2>
                <p className="text-xl">Приз: {currentRound.prize}</p>
              </div>
            )}
            
            <div className="bg-white rounded-lg p-8">
              {wheelParticipants.length > 0 ? (
                <WheelComponent
                  participants={wheelParticipants}
                  isSpinning={isSpinning}
                  onComplete={(winner) => console.log('Winner:', winner)}
                />
              ) : (
                <div className="text-center text-gray-600 py-20">
                  <p className="text-xl mb-4">Ожидание участников...</p>
                  <p>Текущее количество участников: {participants.length}</p>
                </div>
              )}
            </div>
          </div>

          {/* Winners Table */}
          <div className="bg-white/10 backdrop-blur rounded-lg p-6">
            <h2 className="text-2xl font-semibold mb-4">🏆 Победители</h2>
            <div className="space-y-3">
              {Object.keys(raffle.prizes).map(position => {
                const winner = winners.find(w => w.position === parseInt(position));
                return (
                  <div key={position} className={`p-3 rounded ${winner ? 'bg-green-500/20' : 'bg-white/5'}`}>
                    <div className="font-semibold">{position} место: {raffle.prizes[position]}</div>
                    {winner && (
                      <div className="text-lg mt-1">
                        🎉 @{winner.winner?.username || winner.user?.username || 'Победитель'}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Participants List */}
        <div className="mt-8 bg-white/10 backdrop-blur rounded-lg p-6">
          <h3 className="text-xl font-semibold mb-4">Участники ({participants.length})</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
            {participants.map((participant) => (
              <div key={participant.id} className="bg-white/5 rounded px-3 py-2 text-sm">
                @{participant.username || `${participant.first_name} ${participant.last_name || ''}`.trim()}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default LiveRafflePage;