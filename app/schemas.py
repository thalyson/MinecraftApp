"""Pydantic schemas used for validation and serialization.

We keep the schemas lean to avoid exposing sensitive fields like password hashes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from .models import OrderSide


class UserBase(BaseModel):
    email: EmailStr
    mc_uuid: Optional[str] = None
    mc_nick: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserOut(UserBase):
    id: int
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: int
    role: str
    exp: datetime


class OrderCreate(BaseModel):
    ticker: str
    side: OrderSide
    price: float
    quantity: int = Field(gt=0)


class OrderOut(BaseModel):
    id: int
    ticker: str
    side: str
    price: float
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentRequest(BaseModel):
    amount: float


class WithdrawalRequestIn(BaseModel):
    amount: float


class AssetCreate(BaseModel):
    type: str
    ticker: str
    name: str
    total_shares: int
    description: Optional[str] = None


class AssetOut(BaseModel):
    id: int
    type: str
    ticker: str
    name: str
    total_shares: int
    listed: bool

    class Config:
        from_attributes = True