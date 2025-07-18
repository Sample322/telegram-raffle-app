import React, { useState } from 'react';
import { toast } from 'react-hot-toast';
import { TrashIcon, EyeIcon } from '@heroicons/react/24/outline';
import api from '../../services/api';

const CompletedRafflesList = ({ raffles, onUpdate }) => {
  const [loading, setLoading] = useState({});

  const handleDeleteRaffle = async (raffleId) => {
    if (!window.confirm('Вы уверены, что хотите удалить этот завершенный розыгрыш?')) {
      return;
    }

    setLoading(prev => ({ ...prev, [raffleId]: true }));

    try {
      await api.delete(`/admin/raffles/${raffleId}`);
      toast.success('Розыгрыш удален');
      if (onUpdate) onUpdate();
    } catch (error) {
      toast.error('Ошибка при удалении розыгрыша');
    } finally {
      setLoading(prev => ({ ...prev, [raffleId]: false }));
    }
  };

  if (raffles.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-8 text-center">
        <p className="text-gray-500">Нет завершенных розыгрышей</p>
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
              <p className="text-sm text-gray-600 mb-2">
                Завершен: {new Date(raffle.end_date).toLocaleString('ru-RU')}
              </p>
              <p className="text-sm text-gray-600">
                Победителей: {raffle.winners?.length || 0} | 
                Участников: {raffle.participants_count || 0}
              </p>
            </div>
            <div className="flex space-x-2">
              <a
                href={`/raffle/${raffle.id}/history`}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                title="Просмотр"
              >
                <EyeIcon className="h-5 w-5" />
              </a>
              <button
                onClick={() => handleDeleteRaffle(raffle.id)}
                disabled={loading[raffle.id]}
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

export default CompletedRafflesList;