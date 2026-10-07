
import os
import re

from dotenv import load_dotenv
from ldap3 import Server, Connection, SIMPLE
from ldap3.core.exceptions import LDAPSocketOpenError
from ldap3.utils.conv import escape_filter_chars

load_dotenv()

AUTH_MODE = os.getenv("AUTH_MODE", "ad")
AD_SERVIDOR = os.getenv("AD_SERVIDOR", "")
AD_DOMINIO = os.getenv("AD_DOMINIO", "comfenalco.com.co")
AD_BASE = os.getenv("AD_BASE", "DC=comfenalco,DC=com,DC=co")

OUS_PERMITIDAS = [
    "OU=Informatica,OU=Sede Principal,DC=comfenalco,DC=com,DC=co",
    "OU=Domain Controllers,DC=comfenalco,DC=com,DC=co",
]


MOTIVOS_AD = {
    "52e": "usuario o clave incorrectos",
    "525": "el usuario no existe",
    "775": "la cuenta está BLOQUEADA",
    "533": "la cuenta está deshabilitada",
    "532": "la clave venció",
    "773": "debe cambiar la clave antes de entrar",
    "701": "la cuenta expiró",
}


def _log(usuario: str, motivo: str) -> None:
    """Solo para el administrador: sale en la terminal del servidor, nunca en la pantalla del usuario."""
    print(f"[AD] {usuario}: {motivo}", flush=True)


def _motivo(mensaje: str) -> str:
    m = re.search(r"data ([0-9a-f]{3})", mensaje)
    return MOTIVOS_AD.get(m.group(1), mensaje) if m else mensaje


def _normalizar(usuario: str) -> tuple[str, str]:
    """Acepta 'jperez', 'jperez@comfenalco.com.co' o 'COMFENALCO\\jperez'.
    Devuelve (identidad_para_bind, nombre_corto).
    """
    u = usuario.strip().lower()

    if "\\" in u:
        sam = u.split("\\", 1)[1]
        return u, sam

    if "@" in u:
        return u, u.split("@", 1)[0]

    return f"{u}@{AD_DOMINIO}", u


def autenticar_ad(usuario: str, password: str) -> dict | None:
    """Devuelve {usuario, nombre, correo} si la clave es correcta y la persona
    está en una OU permitida. En cualquier otro caso devuelve None
    (y deja el motivo en el log).
    """

    # DIAGNÓSTICO: confirma que esta función realmente está siendo ejecutada
    print(f"[AD] Intentando autenticar usuario: {usuario}", flush=True)

    usuario = usuario.strip().lower()

    if not password:
        _log(usuario, "clave vacía")
        return None

    upn, sam = _normalizar(usuario)

    print(f"[AD] UPN utilizado: {upn}", flush=True)
    print(f"[AD] SAM utilizado: {sam}", flush=True)
    print(f"[AD] Servidor utilizado: {AD_SERVIDOR}", flush=True)

    try:
        servidor = Server(
            AD_SERVIDOR,
            connect_timeout=5
        )

        conn = Connection(
            servidor,
            user=upn,
            password=password,
            authentication=SIMPLE
        )

        if not conn.bind():

            # DIAGNÓSTICO IMPORTANTE:
            # muestra la respuesta completa que devuelve Active Directory
            print(f"[AD] RESULTADO COMPLETO: {conn.result}", flush=True)

            _log(
                sam,
                "el AD rechazó el acceso: " +
                _motivo(str(conn.result.get("message", "")))
            )

            return None

        print("[AD] Autenticación contra AD exitosa", flush=True)

        conn.search(
            AD_BASE,
            f"(|(sAMAccountName={escape_filter_chars(sam)})"
            f"(userPrincipalName={escape_filter_chars(upn)}))",
            attributes=[
                "distinguishedName",
                "displayName",
                "mail"
            ],
        )

        if not conn.entries:
            _log(
                sam,
                f"la clave es correcta pero no se encontró al usuario "
                f"dentro de {AD_BASE}"
            )
            conn.unbind()
            return None

        e = conn.entries[0]

        dn = e.distinguishedName.value

        datos = {
            "usuario": sam,
            "nombre": e.displayName.value or sam,
            "correo": e.mail.value or "",
        }

        print(f"[AD] Usuario encontrado: {dn}", flush=True)

        conn.unbind()

    except LDAPSocketOpenError as err:
        _log(
            sam,
            f"no se pudo conectar al servidor AD "
            f"({AD_SERVIDOR}): {err}"
        )
        return None

    except Exception as err:
        _log(
            sam,
            f"error inesperado: {type(err).__name__}: {err}"
        )
        return None

    # La clave es correcta; ahora se revisa que sea de T.I.
    if not any(
        dn.lower().endswith("," + ou.lower())
        for ou in OUS_PERMITIDAS
    ):
        _log(
            sam,
            f"clave correcta, pero su cuenta NO está en una OU permitida. "
            f"Su ruta es: {dn}"
        )
        return None

    print(f"[AD] Usuario autorizado correctamente: {sam}", flush=True)

    return datos


