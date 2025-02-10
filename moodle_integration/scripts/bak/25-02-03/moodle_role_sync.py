import frappe
import requests
from urllib.parse import unquote, urlparse

@frappe.whitelist(allow_guest=True)
def sync_roles(moodle_url):
    """
    Sincroniza roles desde una instancia de Moodle al Doctype Moodle User Role.
    Recibe el `moodle_url` desde Moodle, valida la instancia y consulta los roles.
    """
    logs = []
    try:
        logs.append("Iniciando sincronización de roles...")

        # Validar URL de Moodle
        if not moodle_url:
            logs.append("No se proporcionó 'moodle_url'.")
            frappe.log_error("\n".join(logs), "Error en Sincronización de Roles")
            return {"status": "error", "message": "No se proporcionó 'moodle_url'."}

        # Decodificar y procesar la URL
        decoded_moodle_url = unquote(moodle_url).rstrip("/")
        parsed_url = urlparse(decoded_moodle_url)
        domain = parsed_url.netloc or parsed_url.path

        # Buscar la instancia de Moodle correspondiente
        moodle_instance = frappe.db.get_value(
            "Moodle Instance", {"site_url": domain}, ["name", "api_key", "site_url"], as_dict=True
        )
        if not moodle_instance:
            logs.append(f"No se encontró una Moodle Instance para el dominio: {domain}")
            frappe.log_error("\n".join(logs), "Error en Sincronización de Roles")
            return {"status": "error", "message": f"No se encontró una Moodle Instance para el dominio: {domain}"}

        # Construir la URL de la API
        moodle_api_url = moodle_instance["site_url"].rstrip("/")
        if not moodle_api_url.startswith(("http://", "https://")):
            moodle_api_url = f"https://{moodle_api_url}"
        api_url = f"{moodle_api_url}/webservice/rest/server.php"

        # Parámetros para obtener todos los roles
        role_params = {
            "wstoken": moodle_instance["api_key"],
            "wsfunction": "local_wsgetroles_get_roles",
            "moodlewsrestformat": "json"
        }

        # Solicitar roles desde Moodle
        response = requests.get(api_url, params=role_params, timeout=10)
        if response.status_code != 200:
            logs.append(f"Error al consultar roles en Moodle: {response.status_code}")
            frappe.log_error("\n".join(logs), "Error en Sincronización de Roles")
            return {"status": "error", "message": "Error al consultar los roles desde Moodle."}

        roles_data = response.json()
        logs.append(f"Roles obtenidos desde Moodle: {roles_data}")

        # Sincronizar roles en el Doctype Moodle User Role
        for role in roles_data:
            role_id = role.get("id")
            role_name = role.get("name", f"Rol Sin Nombre ({role_id})").strip()
            role_shortname = role.get("shortname", f"unknown_{role_id}")
            role_description = role.get("description", "Descripción no disponible")

            # Validar datos mínimos
            if not role_id or not role_shortname:
                logs.append(f"Rol ignorado: ID {role_id} no tiene datos mínimos requeridos.")
                continue

            # Verificar si el rol ya existe
            existing_role = frappe.db.exists("Moodle User Role", {"role_id": role_id})
            if existing_role:
                moodle_role = frappe.get_doc("Moodle User Role", existing_role)
                logs.append(f"Actualizando rol existente: {role_shortname}")
            else:
                moodle_role = frappe.new_doc("Moodle User Role")
                moodle_role.role_id = role_id
                logs.append(f"Creando nuevo rol: {role_shortname}")

            # Actualizar datos del rol
            moodle_role.update({
                "role_name": role_name,
                "role_shortname": role_shortname,
                "role_description": role_description,
                "role_instance": moodle_instance["name"]
            })

            # Guardar cambios
            moodle_role.save(ignore_permissions=True)

        logs.append("Sincronización de roles completada con éxito.")
        frappe.log_error("\n".join(logs), "Sincronización de Roles Completada")
        return {"status": "success", "message": "Sincronización de roles completada correctamente."}

    except Exception as e:
        logs.append(f"Error encontrado: {str(e)}")
        frappe.log_error("\n".join(logs), "Error en Sincronización de Roles")
        return {"status": "error", "message": "Ocurrió un error durante la sincronización de roles.", "error": str(e)}
