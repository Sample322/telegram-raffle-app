from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict, Optional

class UserBase(BaseModel):
    telegram_id: int
    username: Optional[str]
    first_name: str
    last_name: Optional[str]

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    notifications_enabled: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class RaffleBase(BaseModel):
    title: str
    description: str
    photo_url: Optional[str]
    channels: List[str]
    prizes: Dict[int, str]
    end_date: datetime
    draw_delay_minutes: int = 5

class RaffleCreate(RaffleBase):
    pass

class Raffle(RaffleBase):
    id: int
    is_active: bool
    is_completed: bool
    draw_started: bool
    start_date: datetime
    participants_count: Optional[int] = 0
    
    class Config:
        from_attributes = True

class ParticipantCreate(BaseModel):
    raffle_id: int
    user_id: int

class WinnerInfo(BaseModel):
    position: int
    user: User
    prize: str

class RaffleWithWinners(Raffle):
    winners: List[WinnerInfo]

class TelegramInitData(BaseModel):
    query_id: str
    user: dict
    auth_date: int
    hash: str