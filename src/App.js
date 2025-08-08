import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import WebApp from '@twa-dev/sdk';
import { Toaster } from 'react-hot-toast';

// Pages
import HomePage from './pages/HomePage';
import RafflePage from './pages/RafflePage';
import LiveRafflePage from './pages/LiveRafflePage';
import RaffleHistoryPage from './pages/RaffleHistoryPage';
import AdminPanel from './pages/AdminPanel';
import { useTelegramViewport } from './hooks/useTelegramViewport';
// Context
import { AuthProvider } from './contexts/AuthContext';

// Utils
import api from './services/api';

function App() {
  const [isLoading, setIsLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  // Настройка viewport для Telegram
  useTelegramViewport();
  useEffect(() => {
    // Initialize Telegram WebApp
    WebApp.ready();
    WebApp.expand();
    
    // Set up API authorization
    if (WebApp.initData) {
      api.defaults.headers.common['Authorization'] = `Bearer ${WebApp.initData}`;
    }

    // Check if user is admin
    checkAdminStatus();
    
    setIsLoading(false);
  }, []);

  const checkAdminStatus = async () => {
      try {
        // Проверяем админа только если есть initData
        if (!WebApp.initData || WebApp.initData === '') {
          setIsAdmin(false);
          return;
        }
        
        await api.get('/admin/statistics');
        setIsAdmin(true);
      } catch (error) {
        // Не логируем 403/401 ошибки - это нормально для не-админов
        if (error.response?.status !== 403 && error.response?.status !== 401) {
          console.error('Admin check error:', error);
        }
        setIsAdmin(false);
      }
    };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-100">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <AuthProvider>
      <Router>
        <div className="min-h-screen bg-gray-50 telegram-container">
          <Toaster position="top-center" />
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/raffle/:id" element={<RafflePage />} />
            <Route path="/raffle/:id/live" element={<LiveRafflePage />} />
            <Route path="/raffle/:id/history" element={<RaffleHistoryPage />} />
            {isAdmin && <Route path="/admin" element={<AdminPanel />} />}
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </div>
      </Router>
    </AuthProvider>
  );
}

export default App;