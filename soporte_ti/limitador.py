import time
from collections import defaultdict, deque

from fastapi import HTTPException


class Limitador:
    """Limita cuántas veces puede ocurrir algo en una ventana de tiempo (en memoria)."""

    def __init__(self, maximo: int, ventana: int, mensaje: str):
        self.maximo = maximo
        self.ventana = ventana  # segundos
        self.mensaje = mensaje
        self.registros: dict[str, deque] = defaultdict(deque)

    def _purgar(self, clave: str, ahora: float) -> deque:
        q = self.registros[clave]
        while q and ahora - q[0] > self.ventana:
            q.popleft()
        if not q:
            self.registros.pop(clave, None)
            q = self.registros[clave]
        return q

    def _bloquear(self, q: deque, ahora: float):
        minutos = int((self.ventana - (ahora - q[0])) // 60) + 1
        raise HTTPException(429, f"{self.mensaje} Intenta de nuevo en {minutos} min.")

    def bloqueado(self, clave: str):
        """Lanza 429 si la clave ya llegó al máximo (no cuenta como intento)."""
        ahora = time.monotonic()
        q = self._purgar(clave, ahora)
        if len(q) >= self.maximo:
            self._bloquear(q, ahora)

    def fallo(self, clave: str):
        """Registra un intento fallido."""
        self.registros[clave].append(time.monotonic())

    def registrar(self, clave: str):
        """Revisa y cuenta el intento de una vez."""
        self.bloqueado(clave)
        self.fallo(clave)

    def limpiar(self, clave: str):
        self.registros.pop(clave, None)