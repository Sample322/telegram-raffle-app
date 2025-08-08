// Создайте файл frontend/src/hooks/useContainerSize.js

import { useState, useEffect, useRef, useCallback } from 'react';

export const useContainerSize = (dependencies = []) => {
  const [size, setSize] = useState({ width: 0, height: 0 });
  const containerRef = useRef(null);
  const resizeObserverRef = useRef(null);
  
  const updateSize = useCallback(() => {
    if (containerRef.current) {
      const { width, height } = containerRef.current.getBoundingClientRect();
      setSize({ width, height });
    }
  }, []);
  
  useEffect(() => {
    updateSize();
    
    // Используем ResizeObserver для более точного отслеживания
    if (window.ResizeObserver) {
      resizeObserverRef.current = new ResizeObserver((entries) => {
        for (let entry of entries) {
          const { width, height } = entry.contentRect;
          setSize({ width, height });
        }
      });
      
      if (containerRef.current) {
        resizeObserverRef.current.observe(containerRef.current);
      }
    }
    
    // Fallback на window resize
    const handleResize = () => {
      updateSize();
    };
    
    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleResize);
    
    return () => {
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
      }
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleResize);
    };
  }, dependencies);
  
  return { containerRef, size };
};