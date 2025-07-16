import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { toast } from 'react-hot-toast';
import WebApp from '@twa-dev/sdk';
import api from '../services/api';
import Countdown from 'react-countdown';

const RafflePage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [raffle, setRaffle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [participating, setParticipating] = useState(false);
  const [channelStatuses, setChannelStatuses] = useState({});
  const [checkingChannels, setCheckingChannels] = useState(false);

  useEffect(() => {
    loadRaffle();
  }, [id]);

  const loadRaffle = async () => {
    try {
      const response = await api.get(`/raffles/${id}`);
      setRaffle(response.data);
      
      // Check participation status
      const participationRes = await api.get(`/raffles/${id}/check-participation`);
      setParticipating(participationRes.data.is_participating);
    } catch (error) {
      toast.error('Ошибка загрузки розыгрыша');
      navigate('/');
    } finally {
      setLoading(false);
    }
  };

  const checkChannels = async () => {
    setCheckingChannels(true);
    const statuses = {};
    
    for (const channel of raffle.channels) {
      try {
        const isSubscribed = await checkChannelSubscription(channel);
        statuses[channel] = isSubscribed;
      } catch (error) {
        statuses[channel] = false;
      }
    }
    
    setChannelStatuses(statuses);
    setCheckingChannels(false);
    return Object.values(statuses).every(status => status);
  };

  // ──────────────────────────────────────────────
  // Шаг 2: реальная проверка подписки через API
  // ──────────────────────────────────────────────
  const checkChannelSubscription = async (channel) => {
    const { data } = await api.get(
      `/raffles/${id}/check-subscription`,
      { params: { channel } }
    );
    return data.is_subscribed;  // backend возвращает {is_subscribed: true/false}
  };

  const handleParticipate = async () => {
    try {
      // Check username
      const user = WebApp.initDataUnsafe?.user;
      if (!user?.username) {
        toast.error('Для участия необходимо установить имя пользователя (@username) в настройках Telegram');
        return;
      }

      // Check channels
      const allSubscribed = await checkChannels();
      if (!allSubscribed) {
        toast.error('Необходимо подписаться на все каналы');
        return;
      }

      // Participate
      const response = await api.post(`/raffles/${id}/participate`);
      if (response.data.status === 'success') {
        toast.success('Вы успешно зарегистрированы!');
        
        // Show success animation
        WebApp.HapticFeedback.notificationOccurred('success');
        
        // Redirect to home after 2 seconds
        setTimeout(() => {
          navigate('/');
        }, 2000);
      }
    } catch (error) {
      if (error.response?.data?.detail) {
        toast.error(error.response.data.detail);
      } else {
        toast.error('Ошибка при регистрации');
      }
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!raffle) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header Image */}
      {raffle.photo_url && (
        <div className="h-64 overflow-hidden">
          <img 
            src={raffle.photo_url} 
            alt={raffle.title}
            className="w-full h-full object-cover"
          />
        </div>
      )}

      <div className="container mx-auto px-4 py-6">
        <h1 className="text-3xl font-bold text-gray-800 mb-4">{raffle.title}</h1>
        
        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Описание</h2>
          <p className="text-gray-700 whitespace-pre-wrap">{raffle.description}</p>
        </div>

        {/* Prizes */}
        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">🏆 Призы</h2>
          <div className="space-y-3">
            {Object.entries(raffle.prizes).map(([position, prize]) => (
              <div key={position} className="flex items-center space-x-3 p-3 bg-gray-50 rounded-lg">
                <div className="text-2xl">
                  {position === '1' && '🥇'}
                  {position === '2' && '🥈'}
                  {position === '3' && '🥉'}
                  {parseInt(position) > 3 && '🏅'}
                </div>
                <div>
                  <p className="font-semibold">{position} место</p>
                  <p className="text-gray-700">{prize}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Conditions */}
        {raffle.channels.length > 0 && (
          <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">📋 Условия участия</h2>
            <p className="text-gray-700 mb-4">
              Для участия в розыгрыше необходимо быть подписанным на следующие каналы:
            </p>
            <div className="space-y-2">
              {raffle.channels.map((channel) => (
                <div key={channel} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <a 
                    href={`https://t.me/${channel.replace('@', '')}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline font-medium"
                  >
                    {channel}
                  </a>
                  {channelStatuses[channel] !== undefined && (
                    channelStatuses[channel] ? (
                      <CheckIcon className="h-5 w-5 text-green-600" />
                    ) : (
                      <XMarkIcon className="h-5 w-5 text-red-600" />
                    )
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* End Date */}
        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">⏰ До окончания розыгрыша</h2>
          <Countdown
            date={new Date(raffle.end_date)}
            renderer={({ days, hours, minutes, seconds, completed }) => {
              if (completed) {
                return <p className="text-2xl text-red-600 font-bold">Розыгрыш завершен</p>;
              }
              return (
                <div className="flex space-x-4">
                  <div className="text-center">
                    <div className="text-3xl font-bold text-blue-600">{days}</div>
                    <div className="text-sm text-gray-600">дней</div>
                  </div>
                  <div className="text-center">
                    <div className="text-3xl font-bold text-blue-600">{hours}</div>
                    <div className="text-sm text-gray-600">часов</div>
                  </div>
                  <div className="text-center">
                    <div className="text-3xl font-bold text-blue-600">{minutes}</div>
                    <div className="text-sm text-gray-600">минут</div>
                  </div>
                  <div className="text-center">
                    <div className="text-3xl font-bold text-blue-600">{seconds}</div>
                    <div className="text-sm text-gray-600">секунд</div>
                  </div>
                </div>
              );
            }}
          />
        </div>

        {/* Participate Button */}
        {!participating ? (
          <button
            onClick={handleParticipate}
            disabled={checkingChannels}
            className="w-full bg-blue-600 text-white py-4 px-6 rounded-lg font-semibold text-lg hover:bg-blue-700 transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {checkingChannels ? 'Проверка подписок...' : 'Участвовать'}
          </button>
        ) : (
          <div className="w-full bg-green-100 text-green-700 py-4 px-6 rounded-lg font-semibold text-lg text-center">
            ✅ Вы уже участвуете в этом розыгрыше
          </div>
        )}
      </div>
    </div>
  );
};

export default RafflePage;
