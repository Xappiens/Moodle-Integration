import frappe
from urllib.parse import unquote, urlparse
from moodle_integration.scripts.moodle_user_sync import process_moodle_user
from moodle_integration.scripts.moodle_course_sync import process_moodle_course
from moodle_integration.scripts.moodle_category_sync import process_moodle_category


@frappe.whitelist(allow_guest=True)
def handle_moodle_data(**kwargs):
    """
    Punto de entrada para manejar sincronización de datos entre Moodle y Frappe.
    """
    try:
        # Obtener y validar URL de Moodle
        moodle_url = kwargs.get("moodle_url")
        if not moodle_url:
            return {"status": "error", "message": "No se proporcionó 'moodle_url'."}

        decoded_moodle_url = unquote(moodle_url).rstrip("/")
        parsed_url = urlparse(decoded_moodle_url)
        domain = parsed_url.netloc or parsed_url.path

        # Buscar la Moodle Instance correspondiente
        moodle_instance = frappe.db.get_value(
            "Moodle Instance", {"site_url": domain}, ["name", "api_key", "site_url"], as_dict=True
        )
        if not moodle_instance:
            return {"status": "error", "message": f"No se encontró una Moodle Instance para el dominio: {domain}"}

        moodle_api_url = moodle_instance["site_url"].rstrip("/")
        if not moodle_api_url.startswith(("http://", "https://")):
            moodle_api_url = f"https://{moodle_api_url}"
        api_url = f"{moodle_api_url}/webservice/rest/server.php"

        # Diccionario de redirección
        handlers = {
            "user_id": {
                "function": process_moodle_user,
                "param_key": "user_id"
            },
            "course_id": {
                "function": process_moodle_course,
                "param_key": "course_id"
            },
            "object_id": {
                "function": process_moodle_category,
                "param_key": "category_id",
                "condition": kwargs.get("object_type") == "course_categories"
            }
        }

        # Iterar sobre los handlers para procesar los datos
        for key, handler in handlers.items():
            param_value = kwargs.get(handler["param_key"]) if key != "object_id" else kwargs.get("object_id")
            if param_value and (handler.get("condition", True)):
                response = handler["function"](
                    moodle_instance_name=moodle_instance["name"],
                    **{handler["param_key"]: param_value},  # Cambiar clave a 'category_id'
                    api_url=api_url,
                    token=moodle_instance["api_key"]
                )
                if response.get("status") == "success":
                    return {"status": "success", "message": f"Sincronización completada para {key}: {param_value}"}
                else:
                    return {"status": "error", "message": response.get("message", "Error desconocido durante la sincronización.")}

        return {"status": "error", "message": "No se reconoció un tipo de dato válido para sincronización."}

    except Exception as e:
        frappe.log_error(message=f"Error en handle_moodle_data: {str(e)}", title="Error en handle_moodle_data")
        return {"status": "error", "message": "Hubo un error al manejar los datos.", "error": str(e)}
