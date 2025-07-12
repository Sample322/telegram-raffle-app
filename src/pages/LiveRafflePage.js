import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import api from '../services/api';
import WheelComponent from '../components/WheelComponent';
import { io } from 'socket.io-client';

function LiveRafflePage() {
  const { id } = useParams();
  const [raffle, setRaffle] = useState(null);
  const [participants, setParticipants] = useState([]);
  const [currentRound, setCurrentRound] = useState(null);
  const [winners, setWinners] = useState([]);
  const [isSpinning, setIsSpinning] = useState(false);
  const [socket, setSocket] = useState(null);
  const [countdown, setCountdown] = useState(null);

  useEffect(() => {
    loadRaffleData();
    connectWebSocket();

    return () => {
      if (socket) {
        socket.disconnect();
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
    } catch (error) {
      console.error('Error loading raffle:', error);
    }
  };

  const connectWebSocket = () => {
    const ws = io(process.env.REACT_APP_WS_URL || 'ws://localhost:8000', {
      path: `/ws/raffle/${id}`
    });

    ws.on('connect', () => {
      console.log('Connected to WebSocket');
    });

    ws.on('wheel_start', (data) => {
      setCurrentRound({
        position: data.position,
        prize: data.prize,
        participants: data.participants
      });
      setIsSpinning(true);
    });

    ws.on('winner_selected', (data) => {
      setWinners(prev => [...prev, data]);
      setIsSpinning(false);
    });

    ws.on('raffle_complete', (data) => {
      setWinners(data.winners);
      // Show completion message
    });

    ws.on('countdown', (data) => {
      setCountdown(data.seconds);
    });

    setSocket(ws);
  };

  if (!raffle) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-600 to-blue-600 text-white p-4">
      <div className="container mx-auto">
        <h1 className="text-4xl font-bold text-center mb-8">{raffle.title}</h1>
        
        {countdown && (
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
              {currentRound && (
                <WheelComponent
                  participants={currentRound.participants}
                  isSpinning={isSpinning}
                  onComplete={(winner) => console.log('Winner:', winner)}
                />
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
                        🎉 @{winner.winner.username}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Participants Count */}
        <div className="text-center mt-8">
          <p className="text-xl">Всего участников: {participants.length}</p>
        </div>
      </div>
    </div>
  );
}

export default LiveRafflePage;