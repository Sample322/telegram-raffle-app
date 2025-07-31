import asyncio
import os
from sqlalchemy import text
from app.database import engine
from dotenv import load_dotenv

load_dotenv()

async def add_constraints():
    """Add missing constraints to existing database"""
    async with engine.begin() as conn:
        # Проверяем существование constraint
        result = await conn.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'winners' 
            AND constraint_type = 'UNIQUE'
        """))
        
        existing = result.fetchall()
        constraint_exists = any('_raffle_position_uc' in row[0] for row in existing)
        
        if not constraint_exists:
            print("Adding unique constraint to winners table...")
            await conn.execute(text("""
                ALTER TABLE winners 
                ADD CONSTRAINT _raffle_position_uc 
                UNIQUE (raffle_id, position)
            """))
            print("Constraint added successfully!")
        else:
            print("Constraint already exists")

if __name__ == "__main__":
    asyncio.run(add_constraints())