"""Background tasks such as the matching engine and dividend distribution.

The matching engine runs periodically and matches buy and sell limit orders
according to price–time priority. When orders are matched, positions and
cash ledgers are updated accordingly, fees are applied, and trades are
recorded. WebSocket events are emitted to notify connected clients (not
implemented yet).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Optional
from app.database import AsyncSessionLocal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from sqlalchemy import select, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .models import Order, Asset, Trade, Position, CashLedger, User, OrderSide, Role
from . import auth

import yaml
import os

# Load fee configuration
def _load_fee_config() -> dict:
    config_path = os.getenv("CONFIG_FILE", os.path.join(os.path.dirname(__file__), "..", "config.yml"))
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            conf = yaml.safe_load(f)
            return conf.get("fees", {})
    except FileNotFoundError:
        return {}

fee_conf = _load_fee_config()
MAKER_FEE = Decimal(str(fee_conf.get("maker_fee", 0))) / Decimal(100)
TAKER_FEE = Decimal(str(fee_conf.get("taker_fee", 0))) / Decimal(100)


async def match_all(session: AsyncSession) -> None:
    """Run the matching engine once across all assets."""
    # Fetch list of asset ids with open orders
    asset_ids_result = await session.execute(select(Order.asset_id).distinct())
    asset_ids = [row[0] for row in asset_ids_result.all()]
    for asset_id in asset_ids:
        await match_asset_orders(session, asset_id)

    await session.commit()


async def match_asset_orders(session: AsyncSession, asset_id: int) -> None:
    """Match orders for a single asset.

    Orders are matched until the best buy price is less than the best sell price.
    Price–time priority is ensured by ordering price and timestamp.
    """
    while True:
        # Fetch best buy and sell orders
        buy_stmt = (
            select(Order)
            .where(Order.asset_id == asset_id, Order.side == OrderSide.BUY)
            .order_by(desc(Order.price), asc(Order.created_at))
            .limit(1)
        )
        sell_stmt = (
            select(Order)
            .where(Order.asset_id == asset_id, Order.side == OrderSide.SELL)
            .order_by(asc(Order.price), asc(Order.created_at))
            .limit(1)
        )
        buy_res = await session.execute(buy_stmt)
        sell_res = await session.execute(sell_stmt)
        buy_order: Optional[Order] = buy_res.scalar_one_or_none()
        sell_order: Optional[Order] = sell_res.scalar_one_or_none()
        if not buy_order or not sell_order:
            break
        # Check match condition
        if buy_order.price < sell_order.price:
            break
        qty = min(buy_order.qty_open, sell_order.qty_open)
        price = sell_order.price  # price priority
        await execute_trade(session, buy_order, sell_order, qty, price)
        # Loop continues to attempt additional matches


async def execute_trade(session: AsyncSession, buy_order: Order, sell_order: Order, qty: int, price: Decimal) -> None:
    """Execute a trade between two orders and apply cash/asset transfers and fees."""
    # Compute trade amount
    amount = price * qty
    # Determine fees (simplified: both pay taker fee on total)
    maker_fee = amount * MAKER_FEE
    taker_fee = amount * TAKER_FEE
    # Update positions: buyer increases, seller decreases
    await update_position(session, buy_order.user_id, buy_order.asset_id, qty, price, is_buy=True)
    await update_position(session, sell_order.user_id, sell_order.asset_id, qty, price, is_buy=False)
    # Cash transfer: buyer pays, seller receives
    # Buyer: debit amount + fee
    await insert_cash_entry(session, buy_order.user_id, -(amount + taker_fee), reason="BUY", ref_id=buy_order.id)
    # Seller: credit amount - fee
    await insert_cash_entry(session, sell_order.user_id, (amount - maker_fee), reason="SELL", ref_id=sell_order.id)
    # Accrue fees to admin user (id=1) or system (could be config)
    admin_user_id = await get_admin_user_id(session)
    fee_total = maker_fee + taker_fee
    await insert_cash_entry(session, admin_user_id, fee_total, reason="FEE", ref_id=None)
    # Decrease order quantities
    buy_order.qty_open -= qty
    sell_order.qty_open -= qty
    # Create trade record
    trade = Trade(
        asset_id=buy_order.asset_id,
        price=price,
        qty=qty,
        buyer_id=buy_order.user_id,
        seller_id=sell_order.user_id,
    )
    session.add(trade)
    # If orders filled, remove them
    if buy_order.qty_open <= 0:
        await session.delete(buy_order)
    if sell_order.qty_open <= 0:
        await session.delete(sell_order)


async def update_position(session: AsyncSession, user_id: int, asset_id: int, qty: int, price: Decimal, is_buy: bool) -> None:
    """Update or create a position for a user when a trade occurs."""
    stmt = select(Position).where(Position.user_id == user_id, Position.asset_id == asset_id)
    res = await session.execute(stmt)
    position = res.scalar_one_or_none()
    if position is None:
        position = Position(user_id=user_id, asset_id=asset_id, qty=0, avg_price=Decimal(0))
        session.add(position)
    if is_buy:
        # Weighted average price
        total_cost = position.avg_price * position.qty + price * qty
        position.qty += qty
        position.avg_price = total_cost / position.qty if position.qty > 0 else Decimal(0)
    else:
        position.qty -= qty
        if position.qty < 0:
            position.qty = 0


async def insert_cash_entry(session: AsyncSession, user_id: int, delta: Decimal, reason: str, ref_id: Optional[int]) -> None:
    """Insert a cash ledger entry."""
    entry = CashLedger(user_id=user_id, delta=delta, reason=reason, ref_id=ref_id)
    session.add(entry)


async def get_admin_user_id(session: AsyncSession) -> int:
    """Return an admin user id; if none exists, create one from config."""
    # We assume the first user with admin role acts as the broker/admin.
    result = await session.execute(select(User).where(User.role == Role.ADMIN).order_by(User.id))
    admin_user = result.scalars().first()
    if admin_user:
        return admin_user.id
    # Fallback: create a synthetic admin user
    admin_user = User(email="admin@local", password_hash=auth.get_password_hash("changeme"), role=Role.ADMIN)
    session.add(admin_user)
    await session.flush()
    return admin_user.id


def start_scheduler() -> AsyncIOScheduler:
    """Start APScheduler for background jobs."""
    scheduler = AsyncIOScheduler()
    # Run matching engine every 5 seconds
    scheduler.add_job(
        match_all_wrapper, IntervalTrigger(seconds=5), id="matching_engine", replace_existing=True
    )
    scheduler.start()
    return scheduler


async def match_all_wrapper() -> None:
    """Wrapper to obtain a database session for the matching engine."""
    async with AsyncSessionLocal() as session:
        await match_all(session)