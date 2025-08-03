"""SQLAlchemy models for the Stock & Bond trading platform.

The models reflect the database schema defined in the specification. Each
entity corresponds to a table. Enums are represented using Python enums and
SQLAlchemy Enum types. Relationships are defined where necessary for ease of
navigation, but they are kept optional because this application is designed
primarily to run asynchronously and avoid heavy eager loading.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Numeric,
    Enum as SQLEnum,
    UniqueConstraint,
    Index,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"
    VIEWER = "VIEWER"


class AssetType(str, enum.Enum):
    STOCK = "STOCK"
    BOND = "BOND"


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    OK = "OK"


class DividendStatus(str, enum.Enum):
    PENDING = "PENDING"
    OK = "OK"
    EXPIRED = "EXPIRED"


class WithdrawalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class IpoPhase(str, enum.Enum):
    BOOK_BUILDING = "BOOK_BUILDING"
    LIVE = "LIVE"
    CLOSED = "CLOSED"


class User(Base):
    """Represents a registered user.

    Attributes:
        id: Primary key.
        email: Email address, unique.
        password_hash: Hashed password (argon2).
        mc_uuid: Minecraft UUID of the player.
        mc_nick: Nickname in Minecraft.
        role: User role (ADMIN/USER/VIEWER).
        created_at: When the user registered.
        last_login_at: Timestamp of last login.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    mc_uuid = Column(String(36), nullable=True)
    mc_nick = Column(String(36), nullable=False)
    discord_nick = Column(String(50), nullable=False)
    role = Column(SQLEnum(Role), default=Role.USER, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    # Relationships
    orders = relationship("Order", back_populates="user", lazy="selectin")
    positions = relationship("Position", back_populates="user", lazy="selectin")
    payments = relationship("Payment", back_populates="user", lazy="selectin")
    cash_ledger_entries = relationship("CashLedger", back_populates="user", lazy="selectin")
    dividends = relationship("Dividend", back_populates="user", lazy="selectin")
    withdrawals = relationship("WithdrawalRequest", back_populates="user", lazy="selectin")


class Asset(Base):
    """Represents an asset (stock or bond) listed on the market."""

    __tablename__ = "assets"

    id = Column(Integer, primary_key=True)
    asset_type = Column(String(20), nullable=False)
    ticker = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    total_shares = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text, default="")
    current_price = Column(Numeric(10, 2), nullable=True)
    market_cap = Column(Numeric(15, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    # Relationships
    orders = relationship("Order", back_populates="asset", lazy="selectin")
    trades = relationship("Trade", back_populates="asset", lazy="selectin")
    positions = relationship("Position", back_populates="asset", lazy="selectin")
    dividends = relationship("Dividend", back_populates="asset", lazy="selectin")
    ipo_entries = relationship("IPOQueue", back_populates="asset", lazy="selectin")


class Order(Base):
    """Limit order to buy or sell an asset."""

    __tablename__ = "order_book"

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    side = Column(SQLEnum(OrderSide), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    qty_open = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="orders")
    asset = relationship("Asset", back_populates="orders")

    __table_args__ = (
        Index("ix_order_asset_side_price", "asset_id", "side", "price"),
    )


class Trade(Base):
    """Represents a matched trade between buyer and seller."""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    qty = Column(Integer, nullable=False)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)

    asset = relationship("Asset", back_populates="trades")
    buyer = relationship("User", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])


class Position(Base):
    """Aggregated user holdings for a particular asset."""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    qty = Column(Integer, nullable=False, default=0)
    avg_price = Column(Numeric(10, 2), nullable=False, default=0)

    user = relationship("User", back_populates="positions")
    asset = relationship("Asset", back_populates="positions")

    __table_args__ = (
        UniqueConstraint("user_id", "asset_id", name="uc_user_asset"),
    )


class Payment(Base):
    """Represents a deposit of funds by a user.

    The user executes `/pay BrokerAccount <amount>` in Minecraft and uploads a screenshot.
    Admin must review and mark the payment as OK before funds become available.
    """

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    proof_url = Column(String(255), nullable=True)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)

    user = relationship("User", back_populates="payments")


class Dividend(Base):
    """Represents dividends or bond coupons credited to a user."""

    __tablename__ = "dividends"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(SQLEnum(DividendStatus), default=DividendStatus.PENDING, nullable=False)

    user = relationship("User", back_populates="dividends")
    asset = relationship("Asset", back_populates="dividends")


class CashLedger(Base):
    """Represents movements in internal cash balances.

    Reasons include DEPOSIT, BUY, SELL, DIVIDEND, WITHDRAW, FEE, ADMIN_WITHDRAW,
    CUSTODY_FEE, EXPIRED_DIV.
    """

    __tablename__ = "cash_ledger"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    delta = Column(Numeric(12, 2), nullable=False)
    reason = Column(String(64), nullable=False)
    ref_id = Column(Integer, nullable=True)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="cash_ledger_entries")


class WithdrawalRequest(Base):
    """Represents a user's request to withdraw funds to their Minecraft account.

    Admin must execute `/pay <nick> <amount>` and upload proof to mark the request as approved.
    """

    __tablename__ = "withdraw_req"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)
    proof_url = Column(String(255), nullable=True)
    status = Column(SQLEnum(WithdrawalStatus), default=WithdrawalStatus.PENDING, nullable=False)

    user = relationship("User", back_populates="withdrawals")


class IPOQueue(Base):
    """Represents IPO book building entries for an asset."""

    __tablename__ = "ipo_queue"

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    phase = Column(SQLEnum(IpoPhase), default=IpoPhase.BOOK_BUILDING, nullable=False)

    asset = relationship("Asset", back_populates="ipo_entries")


class PasswordReset(Base):
    """Represents a one‑time password reset token."""

    __tablename__ = "password_resets"

    token = Column(String(128), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)