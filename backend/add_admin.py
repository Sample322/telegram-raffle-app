import asyncio
import os
from sqlalchemy import select
from app.database import async_session_maker, init_db
from app.models import Admin
from dotenv import load_dotenv

load_dotenv()

async def add_admin():
    """Add admin to database"""
    await init_db()
    
    admin_ids = os.getenv("ADMIN_IDS", "").split(",")
    
    async with async_session_maker() as session:
        for admin_id in admin_ids:
            if admin_id.strip():
                telegram_id = int(admin_id.strip())
                
                # Check if admin already exists
                result = await session.execute(
                    select(Admin).where(Admin.telegram_id == telegram_id)
                )
                existing_admin = result.scalar_one_or_none()
                
                if not existing_admin:
                    admin = Admin(
                        telegram_id=telegram_id,
                        username="admin"
                    )
                    session.add(admin)
                    print(f"Added admin with ID: {telegram_id}")
                else:
                    print(f"Admin with ID {telegram_id} already exists")
        
        await session.commit()
    
    print("Done!")

if __name__ == "__main__":
    asyncio.run(add_admin())