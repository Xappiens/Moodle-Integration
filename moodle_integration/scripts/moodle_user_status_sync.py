import frappe
from urllib.parse import unquote, urlparse
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def update_user_connection_status(user_id=None, moodle_url=None, action=None):
    """
    Actualiza el estado de conexión de un usuario de Moodle en Frappe.
    Guarda la fecha y hora de la conexión en el campo `user_connection_status` del usuario en Moodle User.
    """
    if not moodle_url or not user_id or action != "connect":
        return {"status": "error", "message": "Parámetros insuficientes o acción no permitida."}

    # Procesar el dominio de la URL
    domain = urlparse(unquote(moodle_url).rstrip("/")).netloc.replace("https://", "").replace("http://", "").strip("/")

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

    # Registrar la fecha y hora actuales en `user_connection_status`
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    frappe.db.set_value("Moodle User", moodle_user["user_name"], "user_connection_status", now)

    # Log opcional para depuración
    frappe.log_error(
        f"Estado actualizado: {moodle_user['user_name']} a '{now}'.",
        f"Estado de Usuario - {moodle_user['user_name']} (Conectado)"
    )

    return {"status": "success", "message": f"Estado actualizado a '{now}' para {moodle_user['user_name']}."}
