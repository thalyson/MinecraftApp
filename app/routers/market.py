"""Routes related to market view and orders."""

from __future__ import annotations

from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc, desc

from ..database import get_session
from ..models import Asset, Order, OrderSide, Trade
from ..schemas import OrderCreate
from ..auth import get_current_user
from ..dependencies import enforce_order_rate_limit
from ..tasks import match_all

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/market/{ticker}", response_class=HTMLResponse)
async def market_view(ticker: str, request: Request, session: AsyncSession = Depends(get_session)):
    """Render the market page for a given ticker."""
    # Fetch asset
    result = await session.execute(select(Asset).where(Asset.ticker == ticker))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return templates.TemplateResponse(
        "market.html",
        {
            "request": request,
            "ticker": ticker,
            "asset_name": asset.name,
        },
    )


@router.get("/api/market/{ticker}/orders")
async def market_orders(ticker: str, session: AsyncSession = Depends(get_session)):
    """Return the current order book for a given ticker as JSON for HTMX."""
    # Resolve asset
    result = await session.execute(select(Asset).where(Asset.ticker == ticker))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    # Fetch top 5 buys and sells
    buy_stmt = (
        select(Order).where(Order.asset_id == asset.id, Order.side == OrderSide.BUY).order_by(desc(Order.price)).limit(5)
    )
    sell_stmt = (
        select(Order).where(Order.asset_id == asset.id, Order.side == OrderSide.SELL).order_by(asc(Order.price)).limit(5)
    )
    buy_orders = (await session.execute(buy_stmt)).scalars().all()
    sell_orders = (await session.execute(sell_stmt)).scalars().all()
    # Build a simple HTML fragment; in production you may want to use a template
    buy_rows = "".join(
        f"<tr><td>{o.price}</td><td>{o.qty_open}</td></tr>" for o in buy_orders
    )
    sell_rows = "".join(
        f"<tr><td>{o.price}</td><td>{o.qty_open}</td></tr>" for o in sell_orders
    )
    html = f"""
    <div class='flex'>
      <div class='w-1/2 p-2'>
        <h3 class='font-bold'>Buy Orders</h3>
        <table class='min-w-full text-sm'><thead><tr><th>Price</th><th>Qty</th></tr></thead><tbody>{buy_rows}</tbody></table>
      </div>
      <div class='w-1/2 p-2'>
        <h3 class='font-bold'>Sell Orders</h3>
        <table class='min-w-full text-sm'><thead><tr><th>Price</th><th>Qty</th></tr></thead><tbody>{sell_rows}</tbody></table>
      </div>
    </div>
    """
    return HTMLResponse(html)


@router.post("/market/{ticker}/order")
async def submit_order(
    ticker: str,
    side: OrderSide = Form(...),
    price: float = Form(...),
    quantity: int = Form(...),
    current_user = Depends(enforce_order_rate_limit),
    session: AsyncSession = Depends(get_session),
):
    """Submit a limit order for a given ticker."""
    # Resolve asset
    result = await session.execute(select(Asset).where(Asset.ticker == ticker))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    # Check user cash or holdings (for simplicity, we rely on matching engine later). We'll skip pre-check here.
    order = Order(
        asset_id=asset.id,
        side=side,
        price=Decimal(price),
        qty_open=quantity,
        user_id=current_user.id,
    )
    session.add(order)
    await session.commit()
    # Kick off matching quickly (optional)
    await match_all(session)
    return RedirectResponse(url=f"/market/{ticker}", status_code=302)


@router.websocket("/ws/market/{ticker}")
async def market_ws(websocket: WebSocket, ticker: str):
    """WebSocket endpoint for live market updates.

    For demonstration, we simply accept the connection and keep it open. In a
    real implementation, you would broadcast trade and order events via a
    publisher (e.g., Redis pub/sub) to all connected clients.
    """
    await websocket.accept()
    try:
        while True:
            # For demonstration, ping the client periodically
            await websocket.send_text("ping")
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return