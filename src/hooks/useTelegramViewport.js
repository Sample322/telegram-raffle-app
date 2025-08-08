import { useEffect } from 'react';
import WebApp from '@twa-dev/sdk';

export const useTelegramViewport = () => {
  useEffect(() => {
    // Устанавливаем viewport для Telegram
    const setViewport = () => {
      let viewport = document.querySelector('meta[name="viewport"]');
      
      if (!viewport) {
        viewport = document.createElement('meta');
        viewport.name = 'viewport';
        document.head.appendChild(viewport);
      }
      
      // Более строгие настройки viewport
      viewport.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover, shrink-to-fit=no';
      
      // Устанавливаем CSS переменные
      const width = window.innerWidth;
      const height = window.innerHeight;
      
      document.documentElement.style.setProperty('--tg-viewport-width', `${width}px`);
      document.documentElement.style.setProperty('--tg-viewport-height', `${height}px`);
      document.documentElement.style.setProperty('--safe-viewport-width', `${Math.min(width, 500)}px`);
      
      // Принудительно ограничиваем body
      document.body.style.width = '100%';
      document.body.style.maxWidth = '100vw';
      document.body.style.overflowX = 'hidden';
      document.body.style.position = 'relative';
      
      // Для iOS
      if (/iPhone|iPad|iPod/.test(navigator.userAgent)) {
        document.body.style.webkitOverflowScrolling = 'touch';
      }
      
      console.log('Viewport set:', { width, height });
    };

    // Немедленная установка
    setViewport();
    
    // Обработка изменения размера с debounce
    let resizeTimeout;
    const handleResize = () => {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        setViewport();
        // Принудительно обновляем layout
        window.dispatchEvent(new Event('telegram-viewport-change'));
      }, 100);
    };

    // Обработка изменения ориентации
    const handleOrientationChange = () => {
      // Даем время на завершение анимации поворота
      setTimeout(setViewport, 300);
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleOrientationChange);
    
    // Специфичные настройки для Telegram
    if (WebApp.ready) {
      WebApp.ready();
      WebApp.expand();
      
      // Отключаем вертикальный свайп для закрытия
      WebApp.disableVerticalSwipes();
      
      // Устанавливаем цвет фона
      WebApp.setBackgroundColor('#f5f5f5');
      
      // Включаем подтверждение закрытия
      WebApp.enableClosingConfirmation();
    }
    
    // Проверяем и корректируем размеры после загрузки
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', setViewport);
    }
    
    // Финальная проверка после полной загрузки
    window.addEventListener('load', () => {
      setTimeout(setViewport, 100);
    });

    return () => {
      clearTimeout(resizeTimeout);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleOrientationChange);
      document.removeEventListener('DOMContentLoaded', setViewport);
    };
  }, []);
};