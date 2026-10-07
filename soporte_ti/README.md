# Soporte T.I. – Comfenalco

## Primera vez
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    copy .env.example .env        (y cambiar SECRET_KEY)

## Ejecutar
    uvicorn main:app --reload --port 8003

- Empleados (formulario sin cuenta): http://127.0.0.1:8003/
- Especialistas: http://127.0.0.1:8003/especialistas

## Login de especialistas
- AUTH_MODE=dev: usuarios de prueba esp1 / esp2, clave dev123.
- AUTH_MODE=ad: Active Directory. Completar AD_SERVIDOR en .env.
  Solo entran cuentas dentro de las OU de ad.py (OUS_PERMITIDAS).
  El especialista se registra solo la primera vez que entra.

## Cambios respecto a tu versión
- ad.py nuevo (login contra AD + filtro por OU + modo dev).
- models.py: Usuario con columna `usuario`, sin password_hash.
- main.py: login-especialista usa AD; se quitó migraciones y bcrypt.
- panel.js / index.html (especialistas): el login pide usuario y clave.
- Se borró crear_especialista.py (ya no hace falta).
- Si ya tenías un soporte.db viejo, bórralo: se crea de nuevo al iniciar.

## Pendiente
Correo con la transcripción, muñequito de escritorio, avisos en tiempo real,
despliegue en el servidor (servicio, HTTPS, copias de seguridad).
