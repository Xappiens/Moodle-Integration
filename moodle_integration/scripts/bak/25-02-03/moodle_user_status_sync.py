import frappe
from urllib.parse import unquote, urlparse

@frappe.whitelist(allow_guest=True)
def update_user_connection_status(user_id=None, moodle_url=None, action=None):
    """
    Actualiza el estado de conexión de un usuario de Moodle en Frappe.
    Identifica al usuario usando user_id y construye el name del Moodle User basado en {user_instance} {moodle_user_id}.
    """
    if not moodle_url or not user_id or action not in ["connect", "disconnect"]:
        return {"status": "error", "message": "Parámetros insuficientes."}

    # Procesar el dominio de la URL
    domain = urlparse(unquote(moodle_url).rstrip("/")).netloc.replace("https://", "").replace("http://", "").strip("/")

    # Determinar el estado basado en la acción
    status = "Conectado" if action == "connect" else "Desconectado"

    # Buscar directamente los datos necesarios de Moodle Instance y Moodle User en una sola consulta
    moodle_user_data = frappe.db.sql("""
        SELECT 
            mi.name AS user_instance, 
            mu.moodle_user_id, 
            mu.name AS user_name
        FROM 
            `tabMoodle User` mu
        INNER JOIN 
            `tabMoodle Instance` mi ON mu.user_instance = mi.name
        WHERE 
            mi.site_url LIKE %s
            AND mu.user_id = %s
    """, (f"%{domain}%", user_id), as_dict=True)

    # Validar resultados de la consulta
    if not moodle_user_data:
        return {"status": "error", "message": f"No se encontró una Moodle Instance o Usuario con user_id {user_id} y dominio {domain}."}

    moodle_user = moodle_user_data[0]  # Tomar el único resultado esperado

    # Actualizar el estado de conexión
    frappe.db.set_value("Moodle User", moodle_user["user_name"], "user_connection_status", status)

    # Log opcional para depuración
    frappe.log_error(
        f"Estado actualizado: {moodle_user['user_name']} a '{status}'.",
        f"Estado de Usuario - {moodle_user['user_name']} ({status})"
    )

    return {"status": "success", "message": f"Estado actualizado a '{status}' para {moodle_user['user_name']}."}
