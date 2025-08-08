import React, { useState } from 'react';
import { toast } from 'react-hot-toast';
import { TrashIcon, EyeIcon } from '@heroicons/react/24/outline';
import api from '../../services/api';

const CompletedRafflesList = ({ raffles, onUpdate }) => {
  const [loading, setLoading] = useState({});

  const handleDelete = async (id) => {
    if (!window.confirm('Удалить завершённый розыгрыш?')) return;
    setLoading(prev => ({ ...prev, [id]: true }));
    try {
      await api.delete(`/admin/raffles/${id}`);
      toast.success('Удалён');
      onUpdate && onUpdate();
    } catch {
      toast.error('Ошибка удаления');
    } finally {
      setLoading(prev => ({ ...prev, [id]: false }));
    }
  };

  if (!raffles.length) {
    return <p className="text-gray-500 text-center py-8">Нет завершённых розыгрышей</p>;
  }

  return (
    <div className="space-y-4">
      {raffles.map(r => (
        <div key={r.id} className="bg-white rounded-lg shadow p-6 flex justify-between">
          <div>
            <h3 className="font-semibold text-lg">{r.title}</h3>
            <p className="text-sm text-gray-600">Завершён: {new Date(r.end_date).toLocaleString('ru-RU')}</p>
          </div>
          <div className="flex space-x-2">
            <a
              href={`/raffle/${r.id}/history`}
              className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg"
              title="Смотреть"
              target="_blank"
              rel="noopener noreferrer"
            >
              <EyeIcon className="h-5 w-5" />
            </a>
            <button
              onClick={() => handleDelete(r.id)}
              disabled={loading[r.id]}
              className="p-2 text-red-600 hover:bg-red-50 rounded-lg disabled:opacity-50"
              title="Удалить"
            >
              <TrashIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default CompletedRafflesList;
