import { useEffect } from 'react';
import WebApp from '@twa-dev/sdk';

export const useTelegramViewport = () => {
  useEffect(() => {
    // Устанавливаем viewport для Telegram
    const setViewport = () => {
      const viewport = document.querySelector('meta[name="viewport"]');
      if (viewport) {
        viewport.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover';
      }
      
      // Устанавливаем CSS переменные
      document.documentElement.style.setProperty('--tg-viewport-width', `${window.innerWidth}px`);
      document.documentElement.style.setProperty('--tg-viewport-height', `${window.innerHeight}px`);
    };

    setViewport();
    
    // Обработка изменения размера
    const handleResize = () => {
      setViewport();
      // Принудительно обновляем layout
      document.body.style.width = '100%';
      document.body.style.maxWidth = '100vw';
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleResize);
    
    // Telegram-specific
    if (WebApp.ready) {
      WebApp.ready();
      WebApp.expand();
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleResize);
    };
  }, []);
};