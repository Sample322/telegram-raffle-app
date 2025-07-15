from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from datetime import datetime, timezone

from ..database import get_db
from ..models import Raffle, Participant, User, Winner
from ..schemas import Raffle as RaffleSchema, RaffleWithWinners
from ..services.telegram import TelegramService
from ..utils.auth import get_current_user

router = APIRouter()

@router.get("/active", response_model=List[RaffleSchema])
async def get_active_raffles(db: AsyncSession = Depends(get_db)):
    """Get all active raffles - PUBLIC ENDPOINT"""
    result = await db.execute(
        select(Raffle).where(
            Raffle.is_active == True,
            Raffle.is_completed == False
        ).order_by(Raffle.created_at.desc())
    )
    raffles = result.scalars().all()
    
    # Add participants count
    for raffle in raffles:
        count_result = await db.execute(
            select(func.count(Participant.id)).where(Participant.raffle_id == raffle.id)
        )
        raffle.participants_count = count_result.scalar()
    
    return raffles

@router.get("/completed", response_model=List[RaffleWithWinners])
async def get_completed_raffles(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Get completed raffles with winners"""
    result = await db.execute(
        select(Raffle).where(
            Raffle.is_completed == True
        ).order_by(Raffle.end_date.desc()).limit(limit).offset(offset)
    )
    raffles = result.scalars().all()
    
    raffles_with_winners = []
    for raffle in raffles:
        # Get winners
        winners_result = await db.execute(
            select(Winner, User).join(User).where(
                Winner.raffle_id == raffle.id
            ).order_by(Winner.position)
        )
        winners_data = winners_result.all()
        
        winners = []
        for winner, user in winners_data:
            winners.append({
                "position": winner.position,
                "user": user,
                "prize": winner.prize
            })
        
        raffles_with_winners.append({
            **raffle.__dict__,
            "winners": winners
        })
    
    return raffles_with_winners

@router.get("/{raffle_id}", response_model=RaffleSchema)
async def get_raffle(raffle_id: int, db: AsyncSession = Depends(get_db)):
    """Get raffle details - PUBLIC ENDPOINT"""
    result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
    raffle = result.scalar_one_or_none()
    
    if not raffle:
        raise HTTPException(status_code=404, detail="Raffle not found")
    
    # Add participants count
    count_result = await db.execute(
        select(func.count(Participant.id)).where(Participant.raffle_id == raffle_id)
    )
    raffle.participants_count = count_result.scalar()
    
    return raffle

@router.post("/{raffle_id}/participate")
async def participate_in_raffle(
    raffle_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Participate in a raffle"""
    # Check if user has username
    if not current_user.username:
        raise HTTPException(
            status_code=400, 
            detail="You need to have a public username (@username) to participate"
        )
    
    # Get raffle
    result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
    raffle = result.scalar_one_or_none()
    
    if not raffle:
        raise HTTPException(status_code=404, detail="Raffle not found")
    
    if not raffle.is_active or raffle.is_completed:
        raise HTTPException(status_code=400, detail="Raffle is not active")
    
    if datetime.now(timezone.utc) > raffle.end_date:
        raise HTTPException(status_code=400, detail="Raffle has ended")
    
    # Check channels subscription
    for channel in raffle.channels:
        is_subscribed = await TelegramService.check_channel_subscription(
            current_user.telegram_id, 
            channel
        )
        if not is_subscribed:
            raise HTTPException(
                status_code=400, 
                detail=f"You must be subscribed to {channel}"
            )
    
    # Check if already participating
    existing = await db.execute(
        select(Participant).where(
            Participant.raffle_id == raffle_id,
            Participant.user_id == current_user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already participating")
    
    # Add participant
    participant = Participant(raffle_id=raffle_id, user_id=current_user.id)
    db.add(participant)
    await db.commit()
    
    return {"status": "success", "message": "Successfully joined the raffle!"}

@router.get("/{raffle_id}/participants")
async def get_participants(
    raffle_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get raffle participants"""
    result = await db.execute(
        select(User).join(Participant).where(
            Participant.raffle_id == raffle_id
        )
    )
    participants = result.scalars().all()
    
    return participants

@router.get("/{raffle_id}/check-participation")
async def check_participation(
    raffle_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check if current user is participating"""
    result = await db.execute(
        select(Participant).where(
            Participant.raffle_id == raffle_id,
            Participant.user_id == current_user.id
        )
    )
    participant = result.scalar_one_or_none()
    
    return {"is_participating": participant is not None}