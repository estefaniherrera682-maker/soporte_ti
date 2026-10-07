import asyncio
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_

import models
from limitador import Limitador
from database import engine, Base, SessionLocal
from ad import autenticar_ad
from seguridad import crear_token, solo_especialista, leer_token

Base.metadata.create_all(bind=engine)

CATEGORIAS_INICIALES = [
    "Falla de red", "Seven", "Kactus", "Falla global", "Office",
    "Falla computador", "Athena", "Aranda", "Impresora", "Falla de correo",
]


def cargar_categorias():
    db = SessionLocal()
    try:
        if db.query(models.Categoria).count() == 0:
            db.add_all(models.Categoria(nombre=n) for n in CATEGORIAS_INICIALES)
            db.commit()
    finally:
        db.close()


cargar_categorias()

ALIAS_ESPECIALISTA = "Especialista T.I."

app = FastAPI(title="Soporte T.I.")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Límites contra abuso: 5 claves fallidas y 5 solicitudes cada 10 minutos por equipo
intentos_login = Limitador(maximo=5, ventana=600, mensaje="Demasiados intentos fallidos.")
limite_solicitudes = Limitador(maximo=5, ventana=600, mensaje="Enviaste muchas solicitudes seguidas.")


def ip_de(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def codigo_valido(s: models.Solicitud, codigo: str) -> bool:
    return secrets.compare_digest(s.codigo.encode(), codigo.encode())


class SolicitudIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    correo:str = Field(min_length=5, max_length=100)
    dependencia: str = Field(min_length=2, max_length=100)
    categoria_id: int
    observacion: str = Field(min_length=3, max_length=1000)
    especialista_id: int | None = None
    equipo: str | None = Field(default=None, max_length=100)
    usuario_win: str | None = Field(default=None, max_length=100)


class CancelarIn(BaseModel):
    codigo: str = Field(max_length=100)


class LoginEspecialistaIn(BaseModel):
    usuario: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    correo: str = Field(
        min_length=6,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse("static/index.html")


@app.get("/especialistas", include_in_schema=False)
def pagina_especialistas():
    return FileResponse("especialistas/index.html")


@app.get("/especialistas/panel.js", include_in_schema=False)
def js_especialistas():
    return FileResponse("especialistas/panel.js")


@app.get("/api/categorias")
def listar_categorias():
    db = SessionLocal()
    try:
        return [{"id": c.id, "nombre": c.nombre} for c in db.query(models.Categoria).all()]
    finally:
        db.close()


@app.post("/api/login-especialista")
def login_especialista(datos: LoginEspecialistaIn, request: Request):
    print("========== LOGIN ENDPOINT EJECUTADO ==========", flush=True)
    print(f"Usuario recibido: {datos.usuario}", flush=True)

    ip = ip_de(request)
    intentos_login.bloqueado(ip)

    info = autenticar_ad(datos.usuario, datos.password)

    if not info:
        intentos_login.fallo(ip)
        raise HTTPException(401, "Usuario o clave incorrectos")

    intentos_login.limpiar(ip)

    db = SessionLocal()
    try:
        u = db.query(models.Usuario).filter_by(usuario=info["usuario"]).first()

        if not u:
            u = models.Usuario(
                usuario=info["usuario"],
                nombre=info["nombre"],
                rol="especialista"
            )
            db.add(u)

        u.nombre = info["nombre"]
        u.correo = datos.correo.strip().lower()

        db.commit()
        db.refresh(u)

        return {
            "token": crear_token(u.id, u.rol),
            "nombre": u.nombre,
            "rol": u.rol
        }

    finally:
        db.close()






def solicitud_a_dict(s: models.Solicitud) -> dict:
    return {
        "id": s.id,
        "solicitante": s.nombre,
        "dependencia": s.dependencia,
        "categoria": s.categoria.nombre,
        "categoria_id": s.categoria_id,
        "observacion": s.observacion,
        "estado": s.estado,
        "especialista": s.especialista.nombre if s.especialista else None,
        "creada_en": s.creada_en.isoformat(),
        "equipo": s.equipo,
        "usuario_win": s.usuario_win,
        "ip": s.ip,
    }


@app.post("/api/solicitudes")
def crear_solicitud(datos: SolicitudIn, request: Request):
    if not (datos.nombre.strip() and datos.dependencia.strip() and datos.observacion.strip()):
        raise HTTPException(400, "Completa todos los campos")
    
    limite_solicitudes.registrar(ip_de(request))
    db = SessionLocal()
    try:
        if not db.get(models.Categoria, datos.categoria_id):
            raise HTTPException(404, "Categoría no existe")
        if datos.especialista_id:
            esp = db.get(models.Usuario, datos.especialista_id)
            if not esp or esp.rol != "especialista":
                raise HTTPException(404, "Especialista no existe")
        s = models.Solicitud(
            nombre=datos.nombre.strip(),
            correo=datos.correo.strip(),
            dependencia=datos.dependencia.strip(),
            categoria_id=datos.categoria_id,
            observacion=datos.observacion.strip(),
            especialista_id=datos.especialista_id,
            codigo=secrets.token_urlsafe(16),
            equipo=datos.equipo,
            usuario_win=datos.usuario_win,
            ip=ip_de(request),
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return {"id": s.id, "codigo": s.codigo,
                "mensaje": "En unos momentos lo atenderá uno de nuestros especialistas"}
    finally:
        db.close()


@app.get("/api/solicitudes/pendientes")
def solicitudes_pendientes(usuario: dict = Depends(solo_especialista)):
    db = SessionLocal()
    try:
        filas = (
            db.query(models.Solicitud)
            .filter(
                models.Solicitud.estado == "pendiente",
                or_(models.Solicitud.especialista_id.is_(None),
                    models.Solicitud.especialista_id == usuario["id"]),
            )
            .order_by(models.Solicitud.creada_en)
            .all()
        )
        return [solicitud_a_dict(s) for s in filas]
    finally:
        db.close()


@app.get("/api/solicitudes/{solicitud_id}/estado")
def estado_solicitud(solicitud_id: int, codigo: str):
    db = SessionLocal()
    try:
        s = db.get(models.Solicitud, solicitud_id)
        if not s or not codigo_valido(s, codigo):
            raise HTTPException(404, "Solicitud no encontrada")
        return {"estado": s.estado,
                "especialista": alias_especialista() if s.especialista_id and s.estado != "pendiente" else None}
    finally:
        db.close()


@app.post("/api/solicitudes/{solicitud_id}/aceptar")
def aceptar_solicitud(solicitud_id: int, usuario: dict = Depends(solo_especialista)):
    db = SessionLocal()
    try:
        tomadas = (
            db.query(models.Solicitud)
            .filter(
                models.Solicitud.id == solicitud_id,
                models.Solicitud.estado == "pendiente",
                or_(models.Solicitud.especialista_id.is_(None),
                    models.Solicitud.especialista_id == usuario["id"]),
            )
            .update({"estado": "aceptada", "especialista_id": usuario["id"]}, synchronize_session=False)
        )
        db.commit()
        if tomadas == 0:
            raise HTTPException(409, "Esta solicitud ya fue tomada o no está disponible para ti")
        return {"mensaje": "Solicitud aceptada"}
    finally:
        db.close()


# ---------------- Chat ----------------
class GestorChat:
    def __init__(self):
        self.salas: dict[int, list[WebSocket]] = {}

    async def conectar(self, sid: int, ws: WebSocket):
        await ws.accept()
        self.salas.setdefault(sid, []).append(ws)

    def quitar(self, sid: int, ws: WebSocket):
        if ws in self.salas.get(sid, []):
            self.salas[sid].remove(ws)

    async def enviar(self, sid: int, datos: dict):
        for ws in list(self.salas.get(sid, [])):
            try:
                await ws.send_json(datos)
            except Exception:
                self.quitar(sid, ws)

    async def cerrar_sala(self, sid: int):
        for ws in self.salas.pop(sid, []):
            try:
                await ws.close()
            except Exception:
                pass


gestor = GestorChat()


def alias_especialista() -> str:
    """El empleado nunca ve quién lo atiende: todos los especialistas se muestran igual."""
    return ALIAS_ESPECIALISTA


def mensaje_a_dict(m: models.Mensaje, alias: str | None = None) -> dict:
    # En la base se guarda el nombre real; al empleado se le muestra el alias
    autor = alias if (alias and m.rol == "especialista") else m.autor
    return {"tipo": "mensaje", "autor": autor, "rol": m.rol, "texto": m.texto, "hora": m.enviado_en.isoformat()}


def enviar_transcripcion(datos: dict) -> None:
    servidor_smtp = os.getenv("SMTP_HOST", "").strip()
    usuario_smtp = os.getenv("SMTP_USER", "").strip()
    remitente = os.getenv("SMTP_FROM", usuario_smtp).strip()
    destinatarios = list(dict.fromkeys(
        correo.strip()
        for correo in (datos["correo_usuario"], datos["correo_especialista"])
        if correo and parseaddr(correo.strip())[1] == correo.strip()
    ))

    if not servidor_smtp or not remitente or not destinatarios:
        print("[CORREO] Transcripción no enviada: falta configuración SMTP o destinatarios.", flush=True)
        return

    mensaje = EmailMessage()
    mensaje["Subject"] = f"Transcripción del caso #{datos['id']} - Soporte T.I."
    mensaje["From"] = remitente
    mensaje["To"] = ", ".join(destinatarios)
    conversacion = "\n\n".join(
        f"[{item['hora']}] {item['autor']} ({item['rol']}):\n{item['texto']}"
        for item in datos["mensajes"]
    ) or "No hay mensajes en el chat."
    mensaje.set_content(
        f"Caso #{datos['id']} resuelto\n"
        f"Solicitante: {datos['nombre']}\n"
        f"Categoría: {datos['categoria']}\n"
        f"Especialista: {datos['especialista']}\n\n"
        f"Transcripción del chat:\n\n{conversacion}\n"
    )

    try:
        puerto = int(os.getenv("SMTP_PORT", "587"))
        contexto = ssl.create_default_context()
        if os.getenv("SMTP_SSL", "false").lower() in ("1", "true", "si", "sí"):
            with smtplib.SMTP_SSL(servidor_smtp, puerto, context=contexto, timeout=20) as smtp:
                if usuario_smtp:
                    smtp.login(usuario_smtp, os.getenv("SMTP_PASSWORD", ""))
                smtp.send_message(mensaje)
        else:
            with smtplib.SMTP(servidor_smtp, puerto, timeout=20) as smtp:
                if os.getenv("SMTP_STARTTLS", "true").lower() in ("1", "true", "si", "sí"):
                    smtp.starttls(context=contexto)
                if usuario_smtp:
                    smtp.login(usuario_smtp, os.getenv("SMTP_PASSWORD", ""))
                smtp.send_message(mensaje)
        print(f"[CORREO] Transcripción del caso #{datos['id']} enviada.", flush=True)
    except Exception as error:
        print(f"[CORREO] No se pudo enviar el caso #{datos['id']}: {type(error).__name__}: {error}", flush=True)


@app.get("/api/solicitudes/mis-casos")
def mis_casos(usuario: dict = Depends(solo_especialista)):
    db = SessionLocal()
    try:
        filas = (
            db.query(models.Solicitud)
            .filter_by(estado="aceptada", especialista_id=usuario["id"])
            .order_by(models.Solicitud.creada_en)
            .all()
        )
        return [solicitud_a_dict(s) for s in filas]
    finally:
        db.close()


@app.post("/api/solicitudes/{solicitud_id}/resolver")
async def resolver_solicitud(solicitud_id: int, usuario: dict = Depends(solo_especialista)):
    db = SessionLocal()
    datos_correo = None
    try:
        n = (
            db.query(models.Solicitud)
            .filter_by(id=solicitud_id, estado="aceptada", especialista_id=usuario["id"])
            .update({"estado": "resuelta"})
        )
        db.commit()
        if n == 0:
            raise HTTPException(409, "No puedes resolver esta solicitud")
        solicitud = db.get(models.Solicitud, solicitud_id)
        especialista = solicitud.especialista
        mensajes = (
            db.query(models.Mensaje)
            .filter_by(solicitud_id=solicitud_id)
            .order_by(models.Mensaje.id)
            .all()
        )
        datos_correo = {
            "id": solicitud.id,
            "nombre": solicitud.nombre,
            "correo_usuario": solicitud.correo,
            "categoria": solicitud.categoria.nombre,
            "especialista": especialista.nombre if especialista else "",
            "correo_especialista": especialista.correo if especialista else None,
            "mensajes": [
                {
                    "hora": mensaje.enviado_en.isoformat(),
                    "autor": mensaje.autor,
                    "rol": mensaje.rol,
                    "texto": mensaje.texto,
                }
                for mensaje in mensajes
            ],
        }
    finally:
        db.close()
    await asyncio.to_thread(enviar_transcripcion, datos_correo)
    await gestor.enviar(solicitud_id, {"tipo": "resuelta"})
    return {"mensaje": "Solicitud resuelta"}


@app.websocket("/ws/chat/{solicitud_id}")
async def chat(ws: WebSocket, solicitud_id: int, token: str = "", codigo: str = ""):
    rol = autor = alias = None
    db = SessionLocal()
    try:
        s = db.get(models.Solicitud, solicitud_id)
        if s and s.estado == "aceptada":
            datos = leer_token(token) if token else None
            if datos and int(datos["sub"]) == s.especialista_id:
                rol, autor = "especialista", s.especialista.nombre
            elif codigo and codigo_valido(s, codigo):
                rol, autor = "solicitante", s.nombre
        if not rol:
            await ws.close(code=1008)
            return
        alias = alias_especialista()
        historial = [
            mensaje_a_dict(m, alias)
            for m in db.query(models.Mensaje).filter_by(solicitud_id=solicitud_id).order_by(models.Mensaje.id)
        ]
    finally:
        db.close()

    await gestor.conectar(solicitud_id, ws)
    await ws.send_json({"tipo": "historial", "mensajes": historial})
    try:
        while True:
            texto = (await ws.receive_text()).strip()[:2000]
            if not texto:
                continue
            db = SessionLocal()
            try:
                m = models.Mensaje(solicitud_id=solicitud_id, autor=autor, rol=rol, texto=texto)
                db.add(m)
                db.commit()
                db.refresh(m)
                nuevo = mensaje_a_dict(m, alias)
            finally:
                db.close()
            await gestor.enviar(solicitud_id, nuevo)
    except WebSocketDisconnect:
        gestor.quitar(solicitud_id, ws)


# ---------------- Historial ----------------
@app.get("/api/solicitudes/resueltas")
def solicitudes_resueltas(usuario: dict = Depends(solo_especialista)):
    db = SessionLocal()
    try:
        filas = (
            db.query(models.Solicitud)
            .filter_by(estado="resuelta", especialista_id=usuario["id"])
            .order_by(desc(models.Solicitud.creada_en))
            .limit(30)
            .all()
        )
        return [solicitud_a_dict(s) for s in filas]
    finally:
        db.close()


@app.get("/api/solicitudes/{solicitud_id}/conversacion")
def conversacion(solicitud_id: int, usuario: dict = Depends(solo_especialista)):
    db = SessionLocal()
    try:
        s = db.get(models.Solicitud, solicitud_id)
        if not s or s.especialista_id != usuario["id"]:
            raise HTTPException(404, "Solicitud no encontrada")
        mensajes = db.query(models.Mensaje).filter_by(solicitud_id=solicitud_id).order_by(models.Mensaje.id)
        return {"solicitud": solicitud_a_dict(s), "mensajes": [mensaje_a_dict(m) for m in mensajes]}
    finally:
        db.close()


# ---------------- Cancelar y devolver ----------------
@app.post("/api/solicitudes/{solicitud_id}/cancelar")
async def cancelar_solicitud(solicitud_id: int, datos: CancelarIn):
    db = SessionLocal()
    try:
        s = db.get(models.Solicitud, solicitud_id)
        if not s or not codigo_valido(s, datos.codigo):
            raise HTTPException(404, "Solicitud no encontrada")
        if s.estado not in ("pendiente", "aceptada"):
            raise HTTPException(409, "Esta solicitud ya no se puede cancelar")
        s.estado = "cancelada"
        db.commit()
    finally:
        db.close()
    await gestor.enviar(solicitud_id, {"tipo": "cancelada"})
    await gestor.cerrar_sala(solicitud_id)
    return {"mensaje": "Solicitud cancelada"}


@app.post("/api/solicitudes/{solicitud_id}/devolver")
async def devolver_solicitud(solicitud_id: int, usuario: dict = Depends(solo_especialista)):
    db = SessionLocal()
    try:
        n = (
            db.query(models.Solicitud)
            .filter_by(id=solicitud_id, estado="aceptada", especialista_id=usuario["id"])
            .update({"estado": "pendiente", "especialista_id": None})
        )
        db.commit()
        if n == 0:
            raise HTTPException(409, "No puedes devolver esta solicitud")
    finally:
        db.close()
    await gestor.enviar(solicitud_id, {"tipo": "devuelta"})
    await gestor.cerrar_sala(solicitud_id)
    return {"mensaje": "Solicitud devuelta a la cola"}