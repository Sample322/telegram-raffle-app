import hashlib
import hmac
import secrets
import time
from typing import Dict, Tuple, Optional
from datetime import datetime, timezone
import json

class ProvablyFairService:
    """Сервис для обеспечения доказуемой честности розыгрышей"""
    
    # Хранилище коммитов и сидов (в продакшене использовать Redis)
    _commits: Dict[str, Dict] = {}
    _revealed: Dict[str, Dict] = {}
    
    @staticmethod
    def generate_server_seed() -> str:
        """Генерация криптостойкого серверного сида"""
        return secrets.token_hex(32)
    
    @staticmethod
    def create_commit(raffle_id: int, position: int, server_seed: str, 
                     participants_count: int) -> Dict:
        """
        Создание коммита для раунда розыгрыша
        Returns: {commit_hash, server_seed, timestamp, participants_count}
        """
        # Создаем данные для хеширования
        commit_data = f"{raffle_id}:{position}:{server_seed}:{participants_count}"
        
        # Генерируем HMAC-SHA256 хеш
        secret_key = secrets.token_bytes(32)  # В продакшене из ENV
        commit_hash = hmac.new(
            secret_key,
            commit_data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Сохраняем коммит
        commit_key = f"{raffle_id}_{position}"
        ProvablyFairService._commits[commit_key] = {
            "commit_hash": commit_hash,
            "server_seed": server_seed,
            "secret_key": secret_key.hex(),
            "participants_count": participants_count,
            "timestamp": int(time.time() * 1000),
            "raffle_id": raffle_id,
            "position": position
        }
        
        return {
            "commit_hash": commit_hash,
            "timestamp": ProvablyFairService._commits[commit_key]["timestamp"],
            "participants_count": participants_count
        }
    
    @staticmethod
    def calculate_winner_index(server_seed: str, client_seed: str, 
                               participants_count: int) -> int:
        """
        Детерминированный расчет индекса победителя
        """
        # Комбинируем сиды
        combined = f"{server_seed}{client_seed}"
        
        # Генерируем SHA256 хеш
        hash_result = hashlib.sha256(combined.encode()).hexdigest()
        
        # Берем первые 8 символов хеша и конвертируем в число
        hash_int = int(hash_result[:8], 16)
        
        # Получаем индекс победителя
        winner_index = hash_int % participants_count
        
        return winner_index
    
    @staticmethod
    def reveal_result(raffle_id: int, position: int, client_seed: str) -> Optional[Dict]:
        """
        Раскрытие результата и проверка
        """
        commit_key = f"{raffle_id}_{position}"
        
        if commit_key not in ProvablyFairService._commits:
            return None
        
        commit_data = ProvablyFairService._commits[commit_key]
        
        # Вычисляем победителя
        winner_index = ProvablyFairService.calculate_winner_index(
            commit_data["server_seed"],
            client_seed,
            commit_data["participants_count"]
        )
        
        # Перепроверяем хеш для доказательства
        commit_string = f"{raffle_id}:{position}:{commit_data['server_seed']}:{commit_data['participants_count']}"
        verification_hash = hmac.new(
            bytes.fromhex(commit_data["secret_key"]),
            commit_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Сохраняем раскрытый результат
        reveal_data = {
            "server_seed": commit_data["server_seed"],
            "client_seed": client_seed,
            "winner_index": winner_index,
            "commit_hash": commit_data["commit_hash"],
            "verification_hash": verification_hash,
            "timestamp_revealed": int(time.time() * 1000)
        }
        
        ProvablyFairService._revealed[commit_key] = reveal_data
        
        return reveal_data
    
    @staticmethod
    def verify_fairness(commit_hash: str, server_seed: str, client_seed: str,
                        participants_count: int, winner_index: int) -> bool:
        """
        Проверка честности результата
        """
        # Пересчитываем индекс победителя
        calculated_index = ProvablyFairService.calculate_winner_index(
            server_seed, client_seed, participants_count
        )
        
        return calculated_index == winner_index