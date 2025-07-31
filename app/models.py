from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, ForeignKey, Float, BigInteger, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True)  # Изменено на BigInteger
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    notifications_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    participations = relationship("Participant", back_populates="user")
    wins = relationship("Winner", back_populates="user")

class Raffle(Base):
    __tablename__ = "raffles"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(Text)
    photo_url = Column(String)
    channels = Column(JSON)  # List of channel usernames
    prizes = Column(JSON)  # {1: "iPhone 15", 2: "AirPods", 3: "Gift Card"}
    start_date = Column(DateTime(timezone=True), server_default=func.now())
    end_date = Column(DateTime(timezone=True))
    draw_delay_minutes = Column(Integer, default=5)  # Delay before wheel starts
    wheel_speed = Column(String, default="fast")  # НОВОЕ ПОЛЕ: fast, medium, slow
    post_channels = Column(JSON, default=list)  # НОВОЕ ПОЛЕ: каналы для публикации
    is_active = Column(Boolean, default=True)
    is_completed = Column(Boolean, default=False)
    draw_started = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    participants = relationship("Participant", back_populates="raffle")
    winners = relationship("Winner", back_populates="raffle")


class Participant(Base):
    __tablename__ = "participants"
    
    id = Column(Integer, primary_key=True, index=True)
    raffle_id = Column(Integer, ForeignKey("raffles.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    
    raffle = relationship("Raffle", back_populates="participants")
    user = relationship("User", back_populates="participations")

class Winner(Base):
    __tablename__ = "winners"
    __table_args__ = (
        UniqueConstraint('raffle_id', 'position', name='_raffle_position_uc'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    raffle_id = Column(Integer, ForeignKey("raffles.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    position = Column(Integer)
    prize = Column(String)
    won_at = Column(DateTime(timezone=True), server_default=func.now())
    
    raffle = relationship("Raffle", back_populates="winners")
    user = relationship("User", back_populates="wins")

class Admin(Base):
    __tablename__ = "admins"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True)  # Изменено на BigInteger
    username = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())