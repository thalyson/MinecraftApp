"""Routes for portfolio display."""

from __future__ import annotations

from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Position, Asset, Trade
from ..auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/portfolio", response_class=HTMLResponse)
async def portfolio_view(request: Request, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    """Display the user's portfolio holdings and unrealized P/L."""
    # Fetch positions
    pos_stmt = select(Position, Asset).join(Asset, Position.asset_id == Asset.id).where(Position.user_id == current_user.id)
    result = await session.execute(pos_stmt)
    rows = result.all()
    portfolio = []
    for pos, asset in rows:
        # Determine last trade price or fallback to 0
        last_trade_res = await session.execute(
            select(Trade.price).where(Trade.asset_id == asset.id).order_by(Trade.ts.desc()).limit(1)
        )
        last_price = last_trade_res.scalar_one_or_none() or Decimal(0)
        current_value = last_price * pos.qty
        cost_basis = pos.avg_price * pos.qty
        unrealized = current_value - cost_basis
        portfolio.append(
            {
                "ticker": asset.ticker,
                "name": asset.name,
                "qty": pos.qty,
                "avg_price": pos.avg_price,
                "last_price": last_price,
                "unrealized": unrealized,
            }
        )
    return templates.TemplateResponse("portfolio.html", {"request": request, "portfolio": portfolio})