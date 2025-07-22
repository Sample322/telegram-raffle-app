import axios from 'axios';
import WebApp from '@twa-dev/sdk';

// Use environment variable or relative path
const API_URL = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth header with Telegram init data
api.interceptors.request.use((config) => {
  if (WebApp.initData) {
    config.headers.Authorization = `Bearer ${WebApp.initData}`;
  }
  return config;
});

// Handle errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized
      WebApp.close();
    }
    return Promise.reject(error);
  }
);

export default api;