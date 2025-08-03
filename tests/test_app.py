"""Basic integration tests for the Stock & Bond platform."""

import asyncio
import json
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.main import app
from app.database import Base, engine, get_session
from app.models import User, Asset, Order, OrderSide, CashLedger, Position
from app.auth import get_password_hash


@pytest.fixture(scope="module")
async def setup_db():
    # Create tables in a temporary SQLite database in memory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Drop tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_register_and_login(setup_db):
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Register
        res = await client.post(
            "/register",
            data={"email": "test@example.com", "password": "secret"},
            follow_redirects=False,
        )
        assert res.status_code == 302
        # Cookie should be set in response
        assert "access_token" in res.cookies
        # Access portfolio
        res2 = await client.get("/portfolio", cookies=res.cookies)
        assert res2.status_code == 200


@pytest.mark.asyncio
async def test_deposit_and_order_matching(setup_db, tmp_path):
    # Use new client for second user
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Register user 1 (buyer)
        res = await client.post(
            "/register",
            data={"email": "buyer@example.com", "password": "secret"},
            follow_redirects=False,
        )
        buyer_cookies = res.cookies
        # Register user 2 (seller)
        res = await client.post(
            "/register",
            data={"email": "seller@example.com", "password": "secret"},
            follow_redirects=False,
        )
        seller_cookies = res.cookies
        # Admin create asset
        # We bypass UI by directly inserting into DB
        async with get_session() as session:
            # Create asset ABC
            asset = Asset(ticker="TST", name="TestCo", type="STOCK", total_shares=1000, listed=True)
            session.add(asset)
            await session.commit()
        # Seller deposit funds (to receive when sells) - deposit not required to sell but to hold negative? we skip
        # Buyer deposit funds to have cash
        test_file_path = tmp_path / "proof.png"
        test_file_path.write_bytes(b"fakeimagecontent")
        with open(test_file_path, "rb") as f:
            files = {"proof": ("proof.png", f, "image/png")}
            res = await client.post(
                "/wallet/deposit",
                data={"amount": "1000"},
                files=files,
                cookies=buyer_cookies,
            )
        assert res.status_code in (200, 302)
        # Admin approve deposit
        async with get_session() as session:
            payment = (await session.execute(
                select(CashLedger).join(User).where(User.email == "buyer@example.com")
            )).first()
        # Place buy order for 10 shares at price 10
        res = await client.post(
            "/market/TST/order",
            data={"side": "BUY", "price": "10", "quantity": "10"},
            cookies=buyer_cookies,
            follow_redirects=False,
        )
        # Seller place sell order
        res = await client.post(
            "/market/TST/order",
            data={"side": "SELL", "price": "9", "quantity": "10"},
            cookies=seller_cookies,
            follow_redirects=False,
        )
        # Wait for matching engine to run
        await asyncio.sleep(1)
        # Check positions: buyer should have 10 shares
        async with get_session() as session:
            result = await session.execute(select(Position).join(User).where(User.email == "buyer@example.com"))
            pos = result.scalars().first()
            assert pos is not None
            assert pos.qty == 10