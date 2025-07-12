import React from 'react';
import { 
  UsersIcon, 
  BellIcon, 
  TrophyIcon, 
  ChartBarIcon 
} from '@heroicons/react/24/outline';

const Statistics = ({ statistics }) => {
  if (!statistics) return null;

  const stats = [
    {
      name: 'Всего пользователей',
      value: statistics.total_users,
      icon: UsersIcon,
      color: 'bg-blue-500'
    },
    {
      name: 'С уведомлениями',
      value: statistics.active_users,
      icon: BellIcon,
      color: 'bg-green-500'
    },
    {
      name: 'Всего розыгрышей',
      value: statistics.total_raffles,
      icon: TrophyIcon,
      color: 'bg-purple-500'
    },
    {
      name: 'Активных розыгрышей',
      value: statistics.active_raffles,
      icon: ChartBarIcon,
      color: 'bg-yellow-500'
    }
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {stats.map((stat) => (
        <div key={stat.name} className="bg-white rounded-lg shadow-lg p-6">
          <div className="flex items-center">
            <div className={`p-3 rounded-lg ${stat.color}`}>
              <stat.icon className="h-6 w-6 text-white" />
            </div>
            <div className="ml-4">
              <p className="text-sm text-gray-600">{stat.name}</p>
              <p className="text-2xl font-semibold text-gray-800">{stat.value}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default Statistics;