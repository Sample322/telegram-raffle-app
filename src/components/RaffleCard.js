// frontend/src/components/RaffleCard.js - ОБНОВЛЕННЫЙ ФАЙЛ

import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Countdown from 'react-countdown';
import { CheckCircleIcon } from '@heroicons/react/24/solid';
import api from '../services/api';
import { formatToMoscowTime } from '../utils/dateUtils';

const RaffleCard = ({ raffle }) => {
  const [isParticipating, setIsParticipating] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkParticipation();
  }, [raffle.id]);

  const checkParticipation = async () => {
    try {
      const response = await api.get(`/raffles/${raffle.id}/check-participation`);
      setIsParticipating(response.data.is_participating);
    } catch (error) {
      console.error('Error checking participation:', error);
    } finally {
      setLoading(false);
    }
  };

  const CountdownRenderer = ({ days, hours, minutes, seconds, completed }) => {
    if (completed) {
      return <span className="text-red-600 font-semibold">Завершен</span>;
    } else {
      return (
        <div className="flex space-x-2 text-sm">
          <div className="text-center">
            <div className="font-bold text-gray-800">{days}</div>
            <div className="text-xs text-gray-600">дней</div>
          </div>
          <div className="text-center">
            <div className="font-bold text-gray-800">{hours}</div>
            <div className="text-xs text-gray-600">часов</div>
          </div>
          <div className="text-center">
            <div className="font-bold text-gray-800">{minutes}</div>
            <div className="text-xs text-gray-600">минут</div>
          </div>
          <div className="text-center">
            <div className="font-bold text-gray-800">{seconds}</div>
            <div className="text-xs text-gray-600">секунд</div>
          </div>
        </div>
      );
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg overflow-hidden hover:shadow-xl transition-shadow duration-300">
      {raffle.photo_url && (
        <div className="h-48 overflow-hidden">
          <img 
            src={raffle.photo_url} 
            alt={raffle.title}
            className="w-full h-full object-cover"
          />
        </div>
      )}
      
      <div className="p-4">
        <h3 className="text-xl font-semibold text-gray-800 mb-2">{raffle.title}</h3>
        
        <div className="mb-3">
          <p className="text-sm text-gray-600 mb-1">Призы:</p>
          <div className="space-y-1">
            {Object.entries(raffle.prizes).slice(0, 3).map(([position, prize]) => (
              <div key={position} className="text-sm">
                <span className="font-medium text-gray-700">{position} место:</span> <span className="text-gray-600">{prize}</span>
              </div>
            ))}
            {Object.keys(raffle.prizes).length > 3 && (
              <p className="text-sm text-gray-500 italic">
                и еще {Object.keys(raffle.prizes).length - 3} приз(ов)...
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-xs text-gray-500">До: {formatToMoscowTime(raffle.end_date)}</p>
            <Countdown 
              date={new Date(raffle.end_date)} 
              renderer={CountdownRenderer}
            />
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-600">Участников:</p>
            <p className="text-lg font-semibold text-gray-800">{raffle.participants_count || 0}</p>
          </div>
        </div>

        {loading ? (
          <div className="h-10 bg-gray-200 animate-pulse rounded"></div>
        ) : (
          <Link 
            to={`/raffle/${raffle.id}`}
            className="block w-full text-center bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 transition-colors duration-200 font-medium"
          >
            {isParticipating ? (
              <span className="flex items-center justify-center space-x-2">
                <CheckCircleIcon className="h-5 w-5" />
                <span>Подробнее (вы участвуете)</span>
              </span>
            ) : (
              'Участвовать'
            )}
          </Link>
        )}
      </div>
    </div>
  );
};

export default RaffleCard;