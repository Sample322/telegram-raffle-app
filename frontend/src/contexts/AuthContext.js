import React, { createContext, useContext, useState, useEffect } from 'react';
import WebApp from '@twa-dev/sdk';
import api from '../services/api';

const AuthContext = createContext({});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    initializeAuth();
  }, []);

  const initializeAuth = async () => {
    try {
      // Get user data from Telegram WebApp
      const telegramUser = WebApp.initDataUnsafe?.user;
      
      if (telegramUser) {
        setUser({
          id: telegramUser.id,
          username: telegramUser.username,
          firstName: telegramUser.first_name,
          lastName: telegramUser.last_name,
          photoUrl: telegramUser.photo_url
        });

        try {
          // Проверяем админский статус только если есть пользователь
          if (telegramUser) {
            const response = await api.get('/admin/statistics');
            if (response.status === 200) {
              setIsAdmin(true);
            }
          }
        } catch (error) {
          // Молча игнорируем 403/401 ошибки - это нормально для обычных пользователей
          if (error.response?.status !== 403 && error.response?.status !== 401) {
            console.error('Admin check error:', error);
          }
          setIsAdmin(false);
        }
      }
    } catch (error) {
      console.error('Auth initialization error:', error);
    } finally {
      setLoading(false);
    }
  };

  const value = {
    user,
    isAdmin,
    loading,
    isAuthenticated: !!user
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};