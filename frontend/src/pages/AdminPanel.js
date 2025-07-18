import React, { useState, useEffect } from 'react';
import { Tab } from '@headlessui/react';
import { toast } from 'react-hot-toast';
import api from '../services/api';
import CreateRaffleForm from '../components/admin/CreateRaffleForm';
import RafflesList from '../components/admin/RafflesList';
import Statistics from '../components/admin/Statistics';

function classNames(...classes) {
  return classes.filter(Boolean).join(' ');
}

const AdminPanel = () => {
  const [statistics, setStatistics] = useState(null);
  const [activeRaffles, setActiveRaffles] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, rafflesRes] = await Promise.all([
        api.get('/admin/statistics'),
        api.get('/raffles/active')
      ]);
      
      setStatistics(statsRes.data);
      setActiveRaffles(rafflesRes.data);
    } catch (error) {
      toast.error('Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    { name: 'Статистика', component: Statistics },
    { name: 'Создать розыгрыш', component: CreateRaffleForm },
    { name: 'Активные розыгрыши', component: RafflesList },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="container mx-auto px-4 py-6">
        <h1 className="text-3xl font-bold text-gray-800 mb-6">Панель администратора</h1>
        
        <Tab.Group>
          <Tab.List className="flex space-x-1 rounded-xl bg-blue-900/20 p-1 mb-6">
            {tabs.map((tab) => (
              <Tab
                key={tab.name}
                className={({ selected }) =>
                  classNames(
                    'w-full rounded-lg py-2.5 text-sm font-medium leading-5',
                    'ring-white ring-opacity-60 ring-offset-2 ring-offset-blue-400 focus:outline-none focus:ring-2',
                    selected
                      ? 'bg-white text-blue-700 shadow'
                      : 'text-blue-100 hover:bg-white/[0.12] hover:text-white'
                  )
                }
              >
                {tab.name}
              </Tab>
            ))}
          </Tab.List>
          
          <Tab.Panels>
            <Tab.Panel>
              <Statistics statistics={statistics} />
            </Tab.Panel>
            <Tab.Panel>
              <CreateRaffleForm onSuccess={loadData} />
            </Tab.Panel>
            <Tab.Panel>
              <RafflesList raffles={activeRaffles} onUpdate={loadData} />
            </Tab.Panel>
          </Tab.Panels>
        </Tab.Group>
      </div>
    </div>
  );
};

export default AdminPanel;