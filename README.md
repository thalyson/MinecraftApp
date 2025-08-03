# Minecraft Stock & Bond Exchange

This repository contains a proof‑of‑concept implementation of a stock & bond trading platform for a Minecraft Java server (version ≥ 1.20). The server uses `/pay` for economy transfers while this web application handles custody of deposits, order matching, fee accounting, and distribution of dividends/coupons.

The project is built with **FastAPI** (0.111) for the backend, **HTMX** for dynamic pages, **Alpine.js** and **Tailwind CSS** on the frontend, **SQLAlchemy 2** for data access, **Alembic** for migrations, and **APScheduler** for background jobs. Authentication is handled via email & password with Argon2 hashing and JWTs stored in HTTP‑only cookies.

## Features

* **Registration & Login** – Users sign up with email, password, Minecraft UUID and nickname. Passwords are hashed with Argon2 and JWTs are issued upon login.
* **Deposits & Withdrawals** – Players deposit by executing `/pay BrokerAccount <amount>` in Minecraft and uploading a screenshot. Withdrawals create a pending request for admins.
* **Order Matching** – Users submit limit buy or sell orders. A background matching engine runs every five seconds and executes trades according to price–time priority, applies maker/taker fees, updates positions and cash ledgers, and records trades.
* **Portfolio & Wallet** – Users can view their holdings, average prices, unrealized P/L, cash balance, and transaction history.
* **Admin Console** – Admins have a dashboard summarising KPIs, queues for approving deposits and withdrawals, and a wizard to create new assets (stocks or bonds).
* **WebSockets & HTMX** – The market page uses HTMX to refresh the order book and websockets for live updates (ping messages in this demo).

## Running Locally

1. **Clone the repository** and navigate into it:

   ```bash
   git clone <repo> && cd <repo>
   ```

2. **Install dependencies** (Python 3.12):

   ```bash
   pip install -r requirements.txt
   ```

3. **Run database migrations**:

   ```bash
   alembic upgrade head
   ```

4. **Seed the database** with sample assets and an admin user:

   ```bash
   python seed_data.py
   ```

5. **Start the application**:

   ```bash
   uvicorn app.main:app --reload
   ```

6. Open `http://127.0.0.1:8000/` in your browser. Register a new account or log in with the admin credentials specified in `config.yml`.

## Docker

A `docker-compose.yml` is provided to run the API, PostgreSQL and Nginx in containers. To launch the stack:

```bash
docker compose up --build
```

By default the API will listen on port 8000 and Postgres on 5432.

## IPO Guide (Simplified)

1. **Create an asset** in the admin console (`/admin/assets/new`) specifying the ticker, name, type and total shares.
2. The asset appears in the market once listed. To perform a full IPO process with book building and live matching, further development is required; this demo lays the groundwork.

## Tests

Run the test suite with:

```bash
pytest
```

The tests cover registration, login, depositing funds, placing orders and matching trades.

## Notes

* This application is a prototype and omits many production concerns such as security hardening, CSRF protection, robust WebSocket broadcasting, two‑factor authentication, advertisement integration, and full IPO management.
* See `config.yml` for configurable fees, advertisement toggles and JWT settings.
