import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { CogIcon } from '@heroicons/react/24/outline';
import api from '../services/api';
import RaffleCard from '../components/RaffleCard';
import CompletedRaffleCard from '../components/CompletedRaffleCard';
import { useAuth } from '../contexts/AuthContext';

function HomePage() {
  const [activeRaffles, setActiveRaffles] = useState([]);
  const [completedRaffles, setCompletedRaffles] = useState([]);
  const [loading, setLoading] = useState(true);
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    loadRaffles();
  }, []);

  const loadRaffles = async () => {
    try {
      const [activeRes, completedRes] = await Promise.all([
        api.get('/raffles/active'),
        api.get('/raffles/completed?limit=10')
      ]);
      
      // Дополнительная фильтрация на клиенте для уверенности
      const now = new Date();
      const filteredActive = activeRes.data.filter(raffle => {
        const endDate = new Date(raffle.end_date);
        return !raffle.is_completed && raffle.is_active && endDate > now;
      });
      
      setActiveRaffles(filteredActive);
      setCompletedRaffles(completedRes.data);
    } catch (error) {
      console.error('Error loading raffles:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">🎉 Розыгрыши</h1>
        
        {/* Кнопка админ-панели */}
        {isAdmin && (
          <button
            onClick={() => navigate('/admin')}
            className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <CogIcon className="h-5 w-5" />
            <span>Админ-панель</span>
          </button>
        )}
      </div>
      
      {/* Active Raffles */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-gray-700 mb-4">Активные розыгрыши</h2>
        {activeRaffles.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {activeRaffles.map(raffle => (
              <RaffleCard key={raffle.id} raffle={raffle} />
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow p-6 text-center">
            <p className="text-gray-500">Нет активных розыгрышей</p>
          </div>
        )}
      </div>

      {/* Completed Raffles */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-700 mb-4">История розыгрышей</h2>
        {completedRaffles.length > 0 ? (
          <div className="space-y-4">
            {completedRaffles.map(raffle => (
              <CompletedRaffleCard key={raffle.id} raffle={raffle} />
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow p-6 text-center">
            <p className="text-gray-500">История розыгрышей пуста</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default HomePage;