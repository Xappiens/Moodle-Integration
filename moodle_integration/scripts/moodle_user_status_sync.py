import frappe
from urllib.parse import unquote, urlparse

@frappe.whitelist(allow_guest=True)
def update_user_connection_status(user_id=None, moodle_url=None, action=None, real_user_id=None, object_id=None):
    if not moodle_url or action not in ["connect", "disconnect"]:
        return {"status": "error", "message": "Parámetros insuficientes."}
    
    # Identificar al usuario
    identified_user_id = user_id or real_user_id or object_id
    if not identified_user_id:
        return {"status": "error", "message": "Usuario no identificado."}

    # Decodificar y procesar el dominio
    domain = urlparse(unquote(moodle_url).rstrip("/")).netloc
    domain = domain.replace("https://", "").replace("http://", "").strip("/")

    # Determinar estado basado en acción
    status = "Conectado" if action == "connect" else "Desconectado"

    # Optimizar consultas: Buscar Moodle Instance y Usuario
    moodle_instance = frappe.db.get_value(
        "Moodle Instance", {"site_url": ["like", f"%{domain}%"]}, ["name", "site_url"], as_dict=True
    )
    if not moodle_instance:
        return {"status": "error", "message": f"No se encontró una Moodle Instance para el dominio {domain}."}

    # Construir identificador del usuario
    user_identifier = f"{moodle_instance['name']} {identified_user_id}"
    user_exists = frappe.db.exists("Moodle User", {"name": user_identifier})
    if not user_exists:
        return {"status": "error", "message": f"Usuario no encontrado: {user_identifier}."}

    # Actualizar estado de conexión directamente
    frappe.db.set_value("Moodle User", user_identifier, "user_connection_status", status)

    # Opcional: Log de estado actualizado (deshabilitar si no se requiere)
    frappe.log_error(
        f"Estado actualizado: {user_identifier} a '{status}'.",
        f"Estado de Usuario - {user_identifier} ({status})"
    )
    
    return {"status": "success", "message": f"Estado actualizado a '{status}' para {user_identifier}."}
 