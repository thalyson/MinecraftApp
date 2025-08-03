"""Routes for wallet operations: view cash, deposit, withdraw."""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import CashLedger, Payment, WithdrawalRequest
from ..auth import get_current_user
import yaml

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Load storage config
def _load_storage_config() -> dict:
    config_path = os.getenv("CONFIG_FILE", os.path.join(os.path.dirname(__file__), "..", "config.yml"))
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            conf = yaml.safe_load(f)
            return conf.get("storage", {})
    except FileNotFoundError:
        return {}

storage_conf = _load_storage_config()
PROOFS_DIR = storage_conf.get("proofs_dir", "uploaded_proofs")
os.makedirs(os.path.join(os.path.dirname(__file__), "..", PROOFS_DIR), exist_ok=True)


@router.get("/wallet", response_class=HTMLResponse)
async def wallet_view(request: Request, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    """Display the user's cash ledger and balances."""
    # Compute cash balance
    result = await session.execute(
        select(func.coalesce(func.sum(CashLedger.delta), 0)).where(CashLedger.user_id == current_user.id)
    )
    cash_balance: Decimal = result.scalar_one()
    # Fetch ledger entries
    ledger_stmt = select(CashLedger).where(CashLedger.user_id == current_user.id).order_by(CashLedger.ts.desc()).limit(50)
    ledger = (await session.execute(ledger_stmt)).scalars().all()
    return templates.TemplateResponse(
        "wallet.html",
        {"request": request, "ledger": ledger, "cash_balance": cash_balance},
    )


@router.post("/wallet/deposit")
async def deposit_funds(
    amount: float = Form(...),
    proof: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Handle deposit requests by saving proof and creating a payment record."""
    # Validate screenshot extension
    filename = proof.filename
    if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
        raise HTTPException(status_code=400, detail="Proof must be PNG or JPG")
    # Save file to proofs directory
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    save_path = os.path.join(os.path.dirname(__file__), "..", PROOFS_DIR, unique_name)
    with open(save_path, "wb") as f:
        content = await proof.read()
        f.write(content)
    # Create payment record with status pending
    payment = Payment(
        user_id=current_user.id,
        amount=Decimal(amount),
        proof_url=unique_name,
    )
    session.add(payment)
    await session.commit()
    return RedirectResponse(url="/wallet", status_code=302)


@router.post("/wallet/withdraw")
async def request_withdrawal(
    amount: float = Form(...),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Request a withdrawal. Funds will be locked until admin approves."""
    # Check available cash
    result = await session.execute(
        select(func.coalesce(func.sum(CashLedger.delta), 0)).where(CashLedger.user_id == current_user.id)
    )
    balance: Decimal = result.scalar_one()
    if Decimal(amount) > balance:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    # Lock funds by inserting negative entry (locked until admin approves)
    ledger_entry = CashLedger(user_id=current_user.id, delta=Decimal(-amount), reason="WITHDRAW_LOCK", ref_id=None)
    session.add(ledger_entry)
    withdraw = WithdrawalRequest(user_id=current_user.id, amount=Decimal(amount))
    session.add(withdraw)
    await session.commit()
    return RedirectResponse(url="/wallet", status_code=302)