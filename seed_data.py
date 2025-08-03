import asyncio
from decimal import Decimal
import os
import yaml

# Importe o AsyncSessionLocal no topo
from app.database import AsyncSessionLocal
from sqlalchemy import select
from app.models import Asset, User, Role
from app.auth import get_password_hash

async def seed():
    # Leia o config e etc. (como já estava)
    config_path = os.getenv("CONFIG_FILE", os.path.join(os.path.dirname(__file__), "config.yml"))
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    admin_email = cfg.get("roles", {}).get("admin_email")
    admin_password = cfg.get("roles", {}).get("admin_password", "admin123")

    # Crie a sessão dentro da função assíncrona
    async with AsyncSessionLocal() as session:
        # Aqui vão as inserções de assets e do admin user, como já estava
        assets = [
            {"ticker": "ABC", "name": "Acme Blocks Company", "asset_type": "STOCK", "total_shares": 100000},
            {"ticker": "BNK", "name": "Brick Bank", "asset_type": "STOCK", "total_shares": 50000},
            {"ticker": "MCR", "name": "Minecart Rails", "asset_type": "BOND", "total_shares": 20000},
        ]
        for asset in assets:
            result = await session.execute(select(Asset).where(Asset.ticker == asset["ticker"]))
            if result.scalar_one_or_none() is None:
                session.add(Asset(**asset, is_active=True))
        if admin_email:
            res = await session.execute(select(User).where(User.email == admin_email))
            if res.scalar_one_or_none() is None:
                session.add(
                    User(
                        email=admin_email,
                        password_hash=get_password_hash(admin_password),
                        role=Role.ADMIN,
                        mc_nick="Admin",
                        discord_nick="AdminDiscord",
                    )
                )
        await session.commit()

if __name__ == "__main__":
    asyncio.run(seed())
