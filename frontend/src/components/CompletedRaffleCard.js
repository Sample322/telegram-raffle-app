import React from 'react';
import { Link } from 'react-router-dom';
import { TrophyIcon, CalendarIcon, UsersIcon } from '@heroicons/react/24/outline';

const CompletedRaffleCard = ({ raffle }) => {
  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric'
    });
  };

  const getWinnerDisplay = (winner, position) => {
    const medals = { 1: '🥇', 2: '🥈', 3: '🥉' };
    return (
      <div key={position} className="flex items-center space-x-2">
        <span className="text-2xl">{medals[position] || '🏅'}</span>
        <div>
          <p className="font-medium">
            @{winner.user.username || `${winner.user.first_name} ${winner.user.last_name || ''}`}
          </p>
          <p className="text-sm text-gray-600">{winner.prize}</p>
        </div>
      </div>
    );
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow duration-300">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between">
        <div className="flex-1">
          <h3 className="text-xl font-semibold text-gray-800 mb-2">{raffle.title}</h3>
          
          <div className="flex items-center space-x-4 text-sm text-gray-600 mb-4">
            <div className="flex items-center space-x-1">
              <CalendarIcon className="h-4 w-4" />
              <span>{formatDate(raffle.end_date)}</span>
            </div>
            <div className="flex items-center space-x-1">
              <UsersIcon className="h-4 w-4" />
              <span>{raffle.participants_count} участников</span>
            </div>
          </div>

          <div className="space-y-2">
            {raffle.winners.slice(0, 3).map((winner) => 
              getWinnerDisplay(winner, winner.position)
            )}
            {raffle.winners.length > 3 && (
              <p className="text-sm text-gray-500 italic flex items-center space-x-1">
                <TrophyIcon className="h-4 w-4" />
                <span>и еще {raffle.winners.length - 3} победителей</span>
              </p>
            )}
          </div>
        </div>

        <div className="mt-4 md:mt-0 md:ml-6">
          <Link
            to={`/raffle/${raffle.id}/history`}
            className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors duration-200"
          >
            Подробнее
          </Link>
        </div>
      </div>
    </div>
  );
};

export default CompletedRaffleCard;