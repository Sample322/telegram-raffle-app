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
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadRaffle();
  }, [id]);

  const loadRaffle = async () => {
    try {
      const response = await api.get(`/raffles/${id}`);
      setRaffle(response.data);
      
      // Check participation status
      try {
        const participationRes = await api.get(`/raffles/${id}/check-participation`);
        setParticipating(participationRes.data.is_participating);
      } catch (error) {
        // Если ошибка авторизации, значит пользователь не участвует
        setParticipating(false);
      }
    } catch (error) {
      toast.error('Ошибка загрузки розыгрыша');
      navigate('/');
    } finally {
      setLoading(false);
    }
  };

  const handleParticipate = async () => {
    if (submitting) return;
    
    setSubmitting(true);
    
    try {
      // Check username
      const user = WebApp.initDataUnsafe?.user;
      if (!user?.username) {
        WebApp.showPopup({
          title: 'Требуется username',
          message: 'Для участия в розыгрыше необходимо установить имя пользователя (@username) в настройках Telegram',
          buttons: [{ type: 'ok' }]
        });
        setSubmitting(false);
        return;
      }

      // Participate
      const response = await api.post(`/raffles/${id}/participate`);
      if (response.data.status === 'success') {
        toast.success('Вы успешно зарегистрированы!');
        setParticipating(true);
        
        // Show success animation
        WebApp.HapticFeedback.notificationOccurred('success');
      }
    } catch (error) {
      if (error.response?.data?.detail) {
        const errorDetail = error.response.data.detail;
        
        // Проверяем разные типы ошибок
        if (errorDetail.includes('must be subscribed')) {
          // Извлекаем название канала из ошибки
          const channel = errorDetail.match(/@\w+/)?.[0] || 'канал';
          WebApp.showPopup({
            title: 'Требуется подписка',
            message: `Для участия необходимо подписаться на ${channel}`,
            buttons: [
              { id: 'subscribe', type: 'default', text: 'Подписаться' },
              { type: 'cancel' }
            ]
          }, (buttonId) => {
            if (buttonId === 'subscribe') {
              const channelName = channel.replace('@', '');
              WebApp.openTelegramLink(`https://t.me/${channelName}`);
            }
          });
        } else if (errorDetail.includes('Already participating')) {
          toast.info('Вы уже участвуете в этом розыгрыше');
          setParticipating(true);
        } else {
          toast.error(errorDetail);
        }
      } else {
        toast.error('Ошибка при регистрации');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const formatImageUrl = (url) => {
    if (!url) return '';
    // Если URL начинается с /uploads, добавляем базовый URL API
    if (url.startsWith('/uploads')) {
      const baseUrl = process.env.REACT_APP_API_URL.replace('/api', '');
      return `${baseUrl}${url}`;
    }
    return url;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="spinner"></div>
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
        <div className="h-64 overflow-hidden bg-gray-100">
          <img 
            src={formatImageUrl(raffle.photo_url)} 
            alt={raffle.title}
            className="w-full h-full object-cover"
            onError={(e) => {
              e.target.style.display = 'none';
              e.target.parentElement.style.display = 'none';
            }}
          />
        </div>
      )}

      <div className="container mx-auto px-4 py-6">
        <h1 className="text-3xl font-bold text-gray-800 mb-4">{raffle.title}</h1>
        
        <div className="card mb-6">
          <h2 className="text-xl font-semibold mb-4">Описание</h2>
          <p className="text-gray-700 whitespace-pre-wrap">{raffle.description}</p>
        </div>

        {/* Prizes */}
        <div className="card mb-6">
          <h2 className="text-xl font-semibold mb-4">🏆 Призы</h2>
          <div className="space-y-2">
            {Object.entries(raffle.prizes).map(([position, prize]) => (
              <div key={position} className="prize-item">
                <div className="prize-position">
                  {position === '1' && <span className="medal-gold">🥇</span>}
                  {position === '2' && <span className="medal-silver">🥈</span>}
                  {position === '3' && <span className="medal-bronze">🥉</span>}
                  {parseInt(position) > 3 && position}
                </div>
                <div className="prize-details">
                  <div className="prize-name">{prize}</div>
                  <div className="prize-description">{position} место</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Conditions */}
        {raffle.channels && raffle.channels.length > 0 && (
          <div className="card mb-6">
            <h2 className="text-xl font-semibold mb-4">📋 Условия участия</h2>
            <p className="text-gray-700 mb-4">
              Для участия в розыгрыше необходимо быть подписанным на следующие каналы:
            </p>
            <div className="space-y-2">
              {raffle.channels.map((channel) => (
                <a 
                  key={channel}
                  href={`https://t.me/${channel.replace('@', '')}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <span className="text-blue-600 font-medium">{channel}</span>
                  <span className="text-sm text-gray-500">Нажмите для перехода →</span>
                </a>
              ))}
            </div>
          </div>
        )}

        {/* End Date */}
        <div className="card mb-6">
          <h2 className="text-xl font-semibold mb-4">⏰ До окончания розыгрыша</h2>
          <Countdown
            date={new Date(raffle.end_date)}
            renderer={({ days, hours, minutes, seconds, completed }) => {
              if (completed) {
                return <p className="text-2xl text-red-600 font-bold">Розыгрыш завершен</p>;
              }
              return (
                <div className="flex justify-center space-x-4">
                  <div className="text-center">
                    <div className="text-3xl font-bold text-primary">{days}</div>
                    <div className="text-sm text-gray-600">дней</div>
                  </div>
                  <div className="text-center">
                    <div className="text-3xl font-bold text-primary">{hours}</div>
                    <div className="text-sm text-gray-600">часов</div>
                  </div>
                  <div className="text-center">
                    <div className="text-3xl font-bold text-primary">{minutes}</div>
                    <div className="text-sm text-gray-600">минут</div>
                  </div>
                  <div className="text-center">
                    <div className="text-3xl font-bold text-primary">{seconds}</div>
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
            disabled={submitting || new Date(raffle.end_date) < new Date()}
            className="btn btn-accent btn-block"
          >
            {submitting ? (
              <>
                <div className="spinner mr-2" style={{width: '20px', height: '20px'}}></div>
                Проверка...
              </>
            ) : (
              'Участвовать'
            )}
          </button>
        ) : (
          <div className="success-message text-center">
            ✅ Вы успешно участвуете в этом розыгрыше!
          </div>
        )}
      </div>
    </div>
  );
};

export default RafflePage;