"""Admin routes secured behind an admin role check."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_admin
from ..database import get_session
from ..models import (
    Payment,
    WithdrawalRequest,
    CashLedger,
    Asset,
    Order,
    Trade,
    Role,
)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session), admin=Depends(get_current_admin)):
    """Admin dashboard summarising key performance indicators."""
    # Pending payments count
    pending_payments = (await session.execute(select(func.count()).select_from(Payment).where(Payment.status == "PENDING"))).scalar_one()
    # Pending withdrawals
    pending_withdrawals = (await session.execute(select(func.count()).select_from(WithdrawalRequest).where(WithdrawalRequest.status == "PENDING"))).scalar_one()
    # Volume last 24h
    since = datetime.utcnow() - timedelta(hours=24)
    volume_res = await session.execute(select(func.coalesce(func.sum(Trade.qty * Trade.price), 0)).where(Trade.ts >= since))
    volume_24h: Decimal = volume_res.scalar_one()
    # Monthly profit (sum of fees) last 30 days from CashLedger reason 'FEE'
    month_since = datetime.utcnow() - timedelta(days=30)
    profit_res = await session.execute(
        select(func.coalesce(func.sum(CashLedger.delta), 0)).where(CashLedger.reason == "FEE", CashLedger.ts >= month_since)
    )
    profit_30d: Decimal = profit_res.scalar_one()
    # Free cash: admin free to withdraw = sum of cash ledger of admin user (positive)
    admin_balance_res = await session.execute(
        select(func.coalesce(func.sum(CashLedger.delta), 0)).where(CashLedger.user_id == admin.id)
    )
    free_cash: Decimal = admin_balance_res.scalar_one()
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "pending_payments": pending_payments,
            "pending_withdrawals": pending_withdrawals,
            "volume_24h": volume_24h,
            "profit_30d": profit_30d,
            "free_cash": free_cash,
        },
    )


@router.get("/payments", response_class=HTMLResponse)
async def payments_queue(request: Request, session: AsyncSession = Depends(get_session), admin=Depends(get_current_admin)):
    """List pending payments for admin review."""
    pending = (await session.execute(select(Payment).where(Payment.status == "PENDING").order_by(Payment.ts))).scalars().all()
    return templates.TemplateResponse(
        "admin/payments.html",
        {"request": request, "payments": pending},
    )


@router.post("/payments/{payment_id}/approve")
async def approve_payment(payment_id: int, session: AsyncSession = Depends(get_session), admin=Depends(get_current_admin)):
    payment = (await session.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not payment or payment.status != "PENDING":
        raise HTTPException(status_code=404, detail="Payment not found")
    payment.status = "OK"
    # Credit user cash ledger
    entry = CashLedger(user_id=payment.user_id, delta=payment.amount, reason="DEPOSIT", ref_id=payment.id)
    session.add(entry)
    await session.commit()
    return RedirectResponse(url="/admin/payments", status_code=302)


@router.post("/payments/{payment_id}/deny")
async def deny_payment(payment_id: int, session: AsyncSession = Depends(get_session), admin=Depends(get_current_admin)):
    payment = (await session.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not payment or payment.status != "PENDING":
        raise HTTPException(status_code=404, detail="Payment not found")
    payment.status = "OK"  # mark as processed; do not credit
    await session.commit()
    return RedirectResponse(url="/admin/payments", status_code=302)


@router.get("/withdrawals", response_class=HTMLResponse)
async def withdrawals_queue(request: Request, session: AsyncSession = Depends(get_session), admin=Depends(get_current_admin)):
    """List pending withdrawals."""
    pending = (
        await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.status == "PENDING").order_by(WithdrawalRequest.ts))
    ).scalars().all()
    return templates.TemplateResponse(
        "admin/withdrawals.html",
        {"request": request, "withdrawals": pending},
    )


@router.post("/withdrawals/{withdraw_id}/approve")
async def approve_withdrawal(
    withdraw_id: int,
    session: AsyncSession = Depends(get_session),
    admin=Depends(get_current_admin),
):
    """Admin marks withdrawal as approved and unlocks funds from admin cash ledger."""
    withdraw = (await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == withdraw_id))).scalar_one_or_none()
    if not withdraw or withdraw.status != "PENDING":
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    withdraw.status = "APPROVED"
    # Transfer funds to admin ledger: subtract from admin free cash
    # Insert ledger entry reversing the lock; funds already deducted from user when requested
    # In this simple model, the admin uses real /pay command outside the system
    await session.commit()
    return RedirectResponse(url="/admin/withdrawals", status_code=302)


@router.post("/withdrawals/{withdraw_id}/deny")
async def deny_withdrawal(
    withdraw_id: int,
    session: AsyncSession = Depends(get_session),
    admin=Depends(get_current_admin),
):
    withdraw = (await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == withdraw_id))).scalar_one_or_none()
    if not withdraw or withdraw.status != "PENDING":
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    withdraw.status = "REJECTED"
    # Refund locked cash: insert positive ledger entry
    refund = CashLedger(user_id=withdraw.user_id, delta=withdraw.amount, reason="WITHDRAW_REFUND", ref_id=withdraw.id)
    session.add(refund)
    await session.commit()
    return RedirectResponse(url="/admin/withdrawals", status_code=302)


@router.get("/assets/new", response_class=HTMLResponse)
async def new_asset_form(request: Request, admin=Depends(get_current_admin)):
    return templates.TemplateResponse("admin/new_asset.html", {"request": request})


@router.post("/assets/new")
async def create_asset(
    request: Request,
    type: str = Form(...),
    ticker: str = Form(...),
    name: str = Form(...),
    total_shares: int = Form(...),
    description: str = Form(""),
    session: AsyncSession = Depends(get_session),
    admin=Depends(get_current_admin),
):
    asset = Asset(type=type, ticker=ticker.upper(), name=name, total_shares=total_shares, description=description)
    session.add(asset)
    await session.commit()
    return RedirectResponse(url="/admin", status_code=302)