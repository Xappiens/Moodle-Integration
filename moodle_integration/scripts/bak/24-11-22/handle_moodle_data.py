import frappe
from urllib.parse import unquote, urlparse
from moodle_integration.scripts.moodle_user_sync import process_moodle_user
from moodle_integration.scripts.moodle_course_sync import process_moodle_course

@frappe.whitelist(allow_guest=True)
def handle_moodle_data(**kwargs):
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

        # Procesar datos de usuario
        user_id = kwargs.get("user_id")
        if user_id:
            return process_moodle_user(
                moodle_instance_name=moodle_instance["name"],
                user_id=user_id,
                api_url=api_url,
                token=moodle_instance["api_key"]
            )
        
        # Procesar datos de curso
        course_id = kwargs.get("course_id")
        if course_id:
            return process_moodle_course(
                moodle_instance_name=moodle_instance["name"],
                course_id=course_id,
                api_url=api_url,
                token=moodle_instance["api_key"]
            )

        return {"status": "error", "message": "Tipo de dato no reconocido."}

    except Exception as e:
        frappe.log_error(message=f"Error en handle_moodle_data: {str(e)}", title="Error en handle_moodle_data")
        return {"status": "error", "message": "Hubo un error al manejar los datos.", "error": str(e)}

