"""Authentication routes for registration, login, logout and password resets."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_session
from ..models import User, Role, PasswordReset
from ..schemas import UserCreate
from ..auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
)

templates = Jinja2Templates(directory="app/templates")

router = APIRouter()


@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    """Serve the HTML registration form."""
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
async def register_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    mc_uuid: str = Form(None),
    mc_nick: str = Form(...),
    discord_nick: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    # Verificação de campos obrigatórios
    if not mc_nick or not discord_nick:
        # Recarrega a página de registro com mensagem de erro e dados preenchidos
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Minecraft Nick e Discord Nick são obrigatórios.",
                "email": email,
                "mc_uuid": mc_uuid,
                "mc_nick": mc_nick,
                "discord_nick": discord_nick,
            },
            status_code=400,
        )
    
    # Verifica se o e‑mail já está cadastrado
    result = await session.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Este e‑mail já está registrado.",
                "email": email,
                "mc_uuid": mc_uuid,
                "mc_nick": mc_nick,
                "discord_nick": discord_nick,
            },
            status_code=400,
        )

    # Cria o usuário com todos os campos
    user = User(
        email=email,
        password_hash=get_password_hash(password),
        mc_uuid=mc_uuid,
        mc_nick=mc_nick,
        discord_nick=discord_nick,
        role=Role.USER,
    )
    session.add(user)
    await session.commit()
    # Auto login after registration
    access_token = create_access_token(data={"user_id": user.id, "role": user.role})
    response = RedirectResponse(url="/portfolio", status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    """Serve the HTML login form."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_user(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    """Handle login via form submission."""
    user = await authenticate_user(session, email, password)
    if not user:
        # Em vez de levantar exceção, volta a página de login com erro
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Credenciais inválidas. Tente novamente.",
                "email": email,
            },
            status_code=400,
        )
    access_token = create_access_token(data={"user_id": user.id, "role": user.role})
    response = RedirectResponse(url="/portfolio", status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return response



@router.get("/logout")
async def logout_user():
    """Log out the current user by clearing the cookie."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response