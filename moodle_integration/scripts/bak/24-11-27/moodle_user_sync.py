import frappe
import requests

@frappe.whitelist(allow_guest=True)
def process_moodle_user(moodle_instance_name, user_id, api_url, token):
    """
    Sincroniza un usuario de Moodle con Frappe. El campo 'user_type' tiene como valor predeterminado 'Estudiante'.
    """
    logs = []
    try:
        logs.append("Iniciando sincronización de usuario...")

        if not moodle_instance_name or not user_id or not api_url or not token:
            logs.append("Error: Faltan parámetros obligatorios.")
            frappe.log_error("\n".join(logs), "Error en parámetros de entrada")
            return {"status": "error", "message": "Faltan parámetros obligatorios."}

        # Obtener datos del usuario desde Moodle
        user_params = {
            "wstoken": token,
            "wsfunction": "core_user_get_users",
            "moodlewsrestformat": "json",
            "criteria[0][key]": "id",
            "criteria[0][value]": user_id
        }
        response = requests.get(api_url, params=user_params, timeout=30)
        if response.status_code != 200:
            logs.append(f"Error al consultar datos del usuario: {response.status_code}")
            frappe.log_error("\n".join(logs), "Error API Moodle")
            return {"status": "error", "message": "Error al consultar los datos del usuario."}

        response_data = response.json()
        users = response_data.get("users", [])
        if not users:
            logs.append(f"No se encontró el usuario con ID: {user_id}")
            frappe.log_error("\n".join(logs), "Usuario no encontrado")
            return {"status": "error", "message": f"No se encontró el usuario con ID: {user_id}"}

        user_data = users[0]
        logs.append(f"Datos del usuario recuperados: {user_data}")

        # Verificar si el usuario ya existe en Frappe
        existing_user = frappe.db.exists("Moodle User", {"moodle_user_id": user_id})
        if existing_user:
            moodle_user = frappe.get_doc("Moodle User", {"moodle_user_id": user_id})
            logs.append(f"Usuario existente encontrado: {moodle_user.name}")
        else:
            moodle_user = frappe.new_doc("Moodle User")
            moodle_user.moodle_user_id = user_id
            logs.append(f"Creando un nuevo usuario en Frappe con moodle_user_id: {user_id}")

        # Actualizar o establecer datos del usuario
        moodle_user.update({
            "user_name": user_data.get("firstname"),
            "user_surname": user_data.get("lastname"),
            "user_fullname": user_data.get("fullname"),
            "user_dni": user_data.get("idnumber"),
            "user_phone": user_data.get("phone1"),
            "user_email": user_data.get("email"),
            "user_instance": moodle_instance_name,
            "user_type": "Estudiante"  # Valor predeterminado
        })

        # Guardar el documento
        moodle_user.save(ignore_permissions=True)
        logs.append(f"Usuario sincronizado exitosamente: {moodle_user.name}")

        # Registrar logs y retornar éxito
        frappe.log_error("\n".join(logs), "Sincronización de Usuario Completada")
        return {"status": "success", "message": "Usuario sincronizado correctamente."}

    except Exception as e:
        logs.append(f"Error encontrado: {str(e)}")
        frappe.log_error("\n".join(logs), "Error en Sincronización de Usuario")
        return {"status": "error", "message": "Ocurrió un error al procesar el usuario.", "error": str(e)}
