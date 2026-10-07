import os
import getpass
from dotenv import load_dotenv
from ldap3 import Server, Connection, SIMPLE

load_dotenv()
usuario = input("Usuario de red: ")
clave = getpass.getpass("Clave: ")   # no se muestra al escribir

servidor = Server(os.getenv("AD_SERVIDOR"), connect_timeout=5)
conn = Connection(servidor, user=f"{usuario}@{os.getenv('AD_DOMINIO')}",
                  password=clave, authentication=SIMPLE, auto_bind=True)
print("Conexión correcta")

conn.search(os.getenv("AD_BASE"), f"(sAMAccountName={usuario})",
            attributes=["distinguishedName", "displayName", "mail"])
for e in conn.entries:
    print(e.distinguishedName.value)
    print(e.displayName.value, e.mail.value)