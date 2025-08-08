import time
from typing import Dict, List
from collections import deque
from datetime import datetime, timezone

class TimeSyncService:
    """Сервис синхронизации времени между клиентом и сервером"""
    
    # Хранилище RTT измерений для каждого клиента
    _client_rtts: Dict[str, deque] = {}
    
    @staticmethod
    def handle_ping(client_id: str, client_timestamp: int) -> Dict:
        """
        Обработка ping от клиента для измерения RTT
        """
        server_time = int(time.time() * 1000)
        
        return {
            "type": "pong",
            "client_timestamp": client_timestamp,
            "server_timestamp": server_time
        }
    
    @staticmethod
    def record_rtt(client_id: str, rtt: int):
        """
        Запись RTT измерения для клиента
        """
        if client_id not in TimeSyncService._client_rtts:
            TimeSyncService._client_rtts[client_id] = deque(maxlen=10)
        
        TimeSyncService._client_rtts[client_id].append(rtt)
    
    @staticmethod
    def get_average_rtt(client_id: str) -> int:
        """
        Получение среднего RTT для клиента
        """
        if client_id not in TimeSyncService._client_rtts:
            return 100  # Default 100ms
        
        rtts = TimeSyncService._client_rtts[client_id]
        if not rtts:
            return 100
        
        return int(sum(rtts) / len(rtts))
    
    @staticmethod
    def calculate_animation_duration(end_timestamp: int, client_id: str,
                                    wheel_speed: str = 'fast') -> Dict:
        """
        Расчет параметров анимации с учетом синхронизации
        """
        current_time = int(time.time() * 1000)
        avg_rtt = TimeSyncService.get_average_rtt(client_id)
        
        # Учитываем RTT/2 для более точной синхронизации
        adjusted_current = current_time + (avg_rtt // 2)
        
        # Время до финиша
        time_until_finish = max(0, end_timestamp - adjusted_current)
        
        # Базовые длительности анимации
        base_durations = {
            'fast': 3000,
            'medium': 5000,
            'slow': 7000
        }
        
        base_duration = base_durations.get(wheel_speed, 3000)
        
        # Корректируем длительность под доступное время
        if time_until_finish < base_duration:
            # Ускоряем анимацию
            animation_duration = max(1000, time_until_finish - 200)  # 200ms буфер
        else:
            animation_duration = base_duration
        
        return {
            "animation_duration": animation_duration,
            "time_until_finish": time_until_finish,
            "avg_rtt": avg_rtt,
            "server_time": current_time,
            "end_timestamp": end_timestamp
        }