import frappe
from urllib.parse import unquote, urlparse
from datetime import datetime
from moodle_integration.scripts.moodle_user_sync import process_moodle_user
from moodle_integration.scripts.moodle_course_sync import process_moodle_course
from moodle_integration.scripts.moodle_category_sync import process_moodle_category

@frappe.whitelist(allow_guest=True)
def handle_moodle_data(**kwargs):
    """
    Punto de entrada optimizado para manejar sincronización de datos entre Moodle y Frappe.
    Identifica la acción y dirige los datos al script correspondiente.
    """

    logs = []
    
    try:
        # Leer datos JSON correctamente desde la solicitud
        request_data = frappe.request.json
        if not request_data:
            logs.append("[ERROR] No se recibieron datos en la solicitud.")
            return {"status": "error", "message": "No se recibieron datos en la solicitud.", "logs": logs}

        # Extraer parámetros de la solicitud
        moodle_url = request_data.get("moodle_url")
        action = request_data.get("action")

        if not moodle_url:
            logs.append("[ERROR] No se proporcionó 'moodle_url'.")
            return {"status": "error", "message": "No se proporcionó 'moodle_url'.", "logs": logs}
        
        if not action:
            logs.append("[ERROR] No se proporcionó 'action'.")
            return {"status": "error", "message": "No se proporcionó 'action'.", "logs": logs}

        # Procesar dominio de la URL de Moodle
        domain = urlparse(unquote(moodle_url).rstrip("/")).netloc.replace("https://", "").replace("http://", "").strip("/")
        logs.append(f"Dominio detectado: {domain}")

        # Obtener instancia de Moodle en una sola consulta SQL
        moodle_instance_data = frappe.db.sql("""
            SELECT name, api_key, site_url 
            FROM `tabMoodle Instance` 
            WHERE LOWER(site_url) LIKE %s
        """, (f"%{domain.lower()}%",), as_dict=True)

        if not moodle_instance_data:
            logs.append(f"[ERROR] No se encontró una Moodle Instance para el dominio: {domain}.")
            return {"status": "error", "message": f"No se encontró una Moodle Instance para el dominio: {domain}.", "logs": logs}

        moodle_instance = moodle_instance_data[0]
        logs.append(f"Instancia de Moodle encontrada: {moodle_instance['name']} ({moodle_instance['site_url']})")

        api_url = f"https://{moodle_instance['site_url'].rstrip('/')}/webservice/rest/server.php"

        # Mapeo de acciones a handlers específicos
        entity_mapping = {
            "_course": {"key": "course_id", "handler": process_moodle_course},
            "_category": {"key": "object_id", "handler": process_moodle_category},
            "_user": {"key": "user_id", "handler": process_moodle_user},
        }

        # Determinar el script adecuado según la acción
        for entity, details in entity_mapping.items():
            if action.endswith(entity):  # Detecta si la acción termina en `_user`, `_course` o `_category`
                entity_id = kwargs.get(details["key"])

                if not entity_id:
                    logs.append(f"Error: No se proporcionó '{details['key']}' en kwargs. Datos recibidos: {kwargs}")
                    return {"status": "error", "message": f"No se proporcionó '{details['key']}'", "logs": logs}

                logs.append(
                    f"Llamando a {details['handler'].__name__} con: "
                    f"moodle_instance={moodle_instance['name']}, {details['key']}={entity_id}, action={action}"
                )

                # Llamar a la función correspondiente con todos los datos correctos
                response = details["handler"](
                    moodle_instance_name=moodle_instance["name"],
                    **{details["key"]: entity_id},
                    api_url=api_url,
                    token=moodle_instance["api_key"],
                    action=action
                )

                logs.append(f"Respuesta de {details['handler'].__name__}: {response}")

                return {**response, "logs": logs}


        logs.append(f"[ERROR] Acción '{action}' no reconocida.")
        return {"status": "error", "message": f"Acción '{action}' no reconocida.", "logs": logs}

    except Exception as e:
        error_message = str(e)
        frappe.log_error(message=f"Error en handle_moodle_data: {error_message}", title="Error en handle_moodle_data")
        logs.append(f"[ERROR] {error_message}")
        return {"status": "error", "message": "Hubo un error al manejar los datos.", "error": error_message, "logs": logs}
