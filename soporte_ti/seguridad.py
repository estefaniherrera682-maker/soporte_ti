import os
import secrets as _secrets
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
   
    SECRET_KEY = _secrets.token_hex(32)
    print("AVISO: no hay SECRET_KEY en .env; se usa una clave temporal.")

ALGORITMO = "HS256"
MINUTOS_EXPIRA = 480  # 8 horas

esquema_oauth = OAuth2PasswordBearer(tokenUrl="/api/login-form")


def crear_token(usuario_id: int, rol: str) -> str:
    expira = datetime.utcnow() + timedelta(minutes=MINUTOS_EXPIRA)
    datos = {"sub": str(usuario_id), "rol": rol, "exp": expira}
    return jwt.encode(datos, SECRET_KEY, algorithm=ALGORITMO)


def leer_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITMO])
    except JWTError:
        return None


def usuario_actual(token: str = Depends(esquema_oauth)) -> dict:
    datos = leer_token(token)
    if datos is None:
        raise HTTPException(401, "Token inválido o expirado")
    return {"id": int(datos["sub"]), "rol": datos["rol"]}


def solo_especialista(usuario: dict = Depends(usuario_actual)) -> dict:
    if usuario["rol"] != "especialista":
        raise HTTPException(403, "Solo para especialistas de T.I.")
    return usuario