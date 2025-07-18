import React, { useState } from 'react';
import { toast } from 'react-hot-toast';
import {
  EyeIcon,
  XMarkIcon,
  ClockIcon,
  UsersIcon,
  TrashIcon          // ← добавьте эту строку
} from '@heroicons/react/24/outline';
import api from '../../services/api';

const RafflesList = ({ raffles, onUpdate }) => {
  const [loading, setLoading] = useState({});

  const handleEndRaffle = async (raffleId) => {
    if (!window.confirm('Вы уверены, что хотите завершить этот розыгрыш?')) {
      return;
    }

    setLoading(prev => ({ ...prev, [raffleId]: true }));

    try {
      await api.patch(`/admin/raffles/${raffleId}/end`);
      toast.success('Розыгрыш будет завершен в ближайшее время');
      if (onUpdate) onUpdate();
    } catch (error) {
      toast.error('Ошибка при завершении розыгрыша');
    } finally {
      setLoading(prev => ({ ...prev, [raffleId]: false }));
    }
  };

  const handleDeleteRaffle = async (raffleId) => {
  if (!window.confirm('Удалить этот розыгрыш безвозвратно?')) return;

  setLoading(prev => ({ ...prev, [`delete_${raffleId}`]: true }));

  try {
    await api.delete(`/admin/raffles/${raffleId}`);
    toast.success('Розыгрыш удалён');
    onUpdate && onUpdate();
  } catch (e) {
    toast.error('Не удалось удалить розыгрыш');
  } finally {
    setLoading(prev => ({ ...prev, [`delete_${raffleId}`]: false }));
  }
};


  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (raffles.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-8 text-center">
        <p className="text-gray-500">Нет активных розыгрышей</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {raffles.map((raffle) => (
        <div key={raffle.id} className="bg-white rounded-lg shadow-lg p-6">
          <div className="flex justify-between items-start">
            <div className="flex-1">
              <h3 className="text-xl font-semibold text-gray-800 mb-2">
                {raffle.title}
              </h3>
              
              <div className="flex items-center space-x-4 text-sm text-gray-600 mb-3">
                <div className="flex items-center space-x-1">
                  <ClockIcon className="h-4 w-4" />
                  <span>До: {formatDate(raffle.end_date)}</span>
                </div>
                <div className="flex items-center space-x-1">
                  <UsersIcon className="h-4 w-4" />
                  <span>{raffle.participants_count || 0} участников</span>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm">
                  Активен
                </span>
                {raffle.draw_started && (
                  <span className="px-3 py-1 bg-yellow-100 text-yellow-700 rounded-full text-sm">
                    Розыгрыш запущен
                  </span>
                )}
              </div>
            </div>

            <div className="flex space-x-2">
              <a
                href={`/raffle/${raffle.id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                title="Просмотр"
              >
                <EyeIcon className="h-5 w-5" />
              </a>
              <button
                onClick={() => handleEndRaffle(raffle.id)}
                disabled={loading[raffle.id]}
                className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                title="Завершить досрочно"
              >
                
                <XMarkIcon className="h-5 w-5" />
              </button>
              <button
                  onClick={() => handleDeleteRaffle(raffle.id)}
                  disabled={loading['delete_' + raffle.id]}
                  className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                  title="Удалить"
                >
                  <TrashIcon className="h-5 w-5" />
              </button>

            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default RafflesList;