import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import api from '../services/api';
import { formatToMoscowTime } from '../utils/dateUtils';
const RaffleHistoryPage = () => {
  const { id } = useParams();
  const [raffle, setRaffle] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRaffleHistory();
  }, [id]);

  const loadRaffleHistory = async () => {
    try {
      // Get completed raffles and find the one we need
      const response = await api.get('/raffles/completed');
      const foundRaffle = response.data.find(r => r.id === parseInt(id));
      setRaffle(foundRaffle);
    } catch (error) {
      console.error('Error loading raffle history:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString) => {
  return formatToMoscowTime(dateString);
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
      <div className="container mx-auto px-4 py-6">
        <p className="text-center text-gray-500">Розыгрыш не найден</p>
      </div>
    );
  }

  const getMedalEmoji = (position) => {
    const medals = { 1: '🥇', 2: '🥈', 3: '🥉' };
    return medals[position] || '🏅';
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm">
        <div className="container mx-auto px-4 py-4">
          <Link 
            to="/" 
            className="inline-flex items-center text-blue-600 hover:text-blue-800"
          >
            <ArrowLeftIcon className="h-5 w-5 mr-2" />
            Назад к розыгрышам
          </Link>
        </div>
      </div>

      {/* Content */}
      <div className="container mx-auto px-4 py-6">
        {/* Raffle Info */}
        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
          <h1 className="text-3xl font-bold text-gray-800 mb-4">{raffle.title}</h1>
          
          {raffle.photo_url && (
            <img 
              src={raffle.photo_url} 
              alt={raffle.title}
              className="w-full max-w-2xl mx-auto h-64 object-cover rounded-lg mb-6"
            />
          )}

          <div className="grid md:grid-cols-2 gap-6 mb-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-2">Информация о розыгрыше</h3>
              <p className="text-gray-600">
                <span className="font-medium">Дата проведения:</span> {formatDate(raffle.end_date)}
              </p>
              <p className="text-gray-600">
                <span className="font-medium">Количество участников:</span> {raffle.participants_count}
              </p>
              <p className="text-gray-600">
                <span className="font-medium">Количество призов:</span> {raffle.winners.length}
              </p>
            </div>

            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-2">Описание</h3>
              <p className="text-gray-600 whitespace-pre-wrap">{raffle.description}</p>
            </div>
          </div>
        </div>

        {/* Winners List */}
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h2 className="text-2xl font-bold text-gray-800 mb-6">🏆 Победители розыгрыша</h2>
          
          <div className="space-y-4">
            {raffle.winners.map((winner) => (
              <div 
                key={winner.position} 
                className="flex items-center space-x-4 p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <div className="text-4xl">
                  {getMedalEmoji(winner.position)}
                </div>
                
                <div className="flex-1">
                  <div className="flex items-center space-x-2">
                    <span className="text-lg font-semibold text-gray-800">
                      {winner.position} место
                    </span>
                    <span className="text-gray-600">•</span>
                    <span className="text-gray-700 font-medium">
                      {winner.prize}
                    </span>
                  </div>
                  
                  <div className="mt-1">
                    <a 
                      href={`https://t.me/${winner.user.username}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline"
                    >
                      @{winner.user.username}
                    </a>
                    <span className="text-gray-600 ml-2">
                      ({winner.user.first_name} {winner.user.last_name || ''})
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Statistics */}
          <div className="mt-6 bg-blue-50 rounded-lg p-6 text-center">
            <p className="text-3xl font-bold text-blue-600">{raffle.participants_count}</p>
            <p className="text-lg text-gray-700">участников</p>
          </div>
      </div>
    </div>
  );
};

export default RaffleHistoryPage;