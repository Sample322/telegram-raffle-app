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

        // Check admin status
        try {
          await api.get('/admin/statistics');
          setIsAdmin(true);
        } catch (error) {
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