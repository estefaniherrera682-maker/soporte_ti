from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(unique=True)


class Usuario(Base):
    """Solo los especialistas de T.I. tienen cuenta. Se crean solos la primera vez
    que entran con su usuario de Active Directory (la clave nunca se guarda aquí)."""
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario: Mapped[str] = mapped_column(unique=True)  # nombre de red, ej: jperez
    nombre: Mapped[str]
    correo: Mapped[Optional[str]]
    dependencia: Mapped[Optional[str]]
    rol: Mapped[str] = mapped_column(default="especialista")


class Solicitud(Base):
    __tablename__ = "solicitudes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str]
    dependencia: Mapped[str]
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    observacion: Mapped[Optional[str]] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(default="pendiente")  
    codigo: Mapped[str]  
    especialista_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"))
    creada_en: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    equipo: Mapped[Optional[str]]
    usuario_win: Mapped[Optional[str]]
    ip: Mapped[Optional[str]]
    correo: Mapped[Optional[str]]  # correo del solicitante, para enviarle el comprobante

    especialista: Mapped[Optional["Usuario"]] = relationship()
    categoria: Mapped["Categoria"] = relationship()


class Mensaje(Base):
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes.id"))
    autor: Mapped[str]
    rol: Mapped[str]  
    texto: Mapped[str] = mapped_column(Text)
    enviado_en: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Correo(Base):
    """Cola de correos: se guardan aquí y se envían cuando hay conexión."""
    __tablename__ = "correos"

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes.id"))
    destinatarios: Mapped[str]
    asunto: Mapped[str]
    cuerpo_html: Mapped[str]
    estado: Mapped[str] = mapped_column(default="pendiente")  # pendiente | enviado
    intentos: Mapped[int] = mapped_column(default=0)
    error: Mapped[Optional[str]]
    creado_en: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    enviado_en: Mapped[Optional[datetime]]