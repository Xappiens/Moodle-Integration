import frappe
import requests
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def process_moodle_user(moodle_instance_name, user_id, api_url, token):
    """
    Sincroniza un único usuario de Moodle con Frappe basado en su ID único de Moodle (user_id).
    """
    logs = []
    try:
        logs.append(f"Iniciando sincronización para el usuario con ID {user_id} en {moodle_instance_name}.")

        # Paso 1: Consultar datos del usuario desde Moodle usando user_id
        user_params = {
            "wstoken": token,
            "wsfunction": "core_user_get_users",
            "moodlewsrestformat": "json",
            "criteria[0][key]": "id",
            "criteria[0][value]": user_id
        }
        logs.append(f"Consultando usuario en Moodle con parámetros: {user_params}")
        response = requests.get(api_url, params=user_params, timeout=30)
        if response.status_code != 200:
            raise ValueError(f"Error al consultar datos del usuario: {response.text}")

        response_data = response.json()
        user_data = response_data.get("users", [None])[0]  # Recuperar el único usuario o None si no existe
        if not user_data:
            raise ValueError(f"No se encontró el usuario con ID {user_id} en Moodle.")
        logs.append(f"Datos del usuario recuperados: {user_data}")

        # Paso 2: Obtener el moodle_user_id
        moodle_user_id = user_data.get("username")  # Nombre de usuario en Moodle
        if not moodle_user_id:
            raise ValueError(f"No se encontró un 'username' para el usuario con ID {user_id}.")
        logs.append(f"Username recuperado: {moodle_user_id}")

        # Paso 3: Generar identificador único para el usuario
        user_identifier = f"{moodle_instance_name} {moodle_user_id}"
        logs.append(f"Identificador del usuario: {user_identifier}")

        # Paso 4: Crear o actualizar el usuario en Frappe
        if frappe.db.exists("Moodle User", {"name": user_identifier}):
            user_doc = frappe.get_doc("Moodle User", user_identifier)
            logs.append(f"Usuario existente encontrado: {user_identifier}. Actualizando datos.")

            # Preservar el rol del usuario existente
            current_user_type = user_doc.get("user_type")
            logs.append(f"Rol actual del usuario: {current_user_type}")
        else:
            user_doc = frappe.new_doc("Moodle User")
            user_doc.name = user_identifier
            user_doc.user_type = "Estudiante"  # Rol predeterminado para nuevos usuarios
            logs.append(f"Creando nuevo usuario: {user_identifier}.")

        # Actualizar campos del usuario excepto el rol si ya existe
        user_doc.update({
            "user_id": user_id,  # ID numérico único en Moodle
            "moodle_user_id": moodle_user_id,  # Username en Moodle
            "user_name": user_data.get("firstname"),
            "user_surname": user_data.get("lastname"),
            "user_fullname": f"{user_data.get('firstname')} {user_data.get('lastname')}",
            "user_email": user_data.get("email"),
            "user_dni": user_data.get("idnumber"),
            "user_phone": user_data.get("phone1"),
            "user_instance": moodle_instance_name,
        })

        # Restaurar el rol existente si es un usuario actualizado
        if frappe.db.exists("Moodle User", {"name": user_identifier}):
            user_doc.user_type = current_user_type

        # Guardar usuario en ERPNext
        user_doc.save(ignore_permissions=True)
        logs.append(f"Datos guardados en ERPNext:\n    {user_doc.as_dict()}")

        # Paso 5: Log Final
        frappe.log_error(
            message="\n".join(logs),
            title=f"Sincronización de Usuario Completada: {user_identifier}"
        )
        return {"status": "success", "message": "Usuario sincronizado correctamente.", "logs": logs}

    except Exception as e:
        error_message = f"Error en process_moodle_user: {str(e)}"
        logs.append(f"[ERROR] {error_message}")
        frappe.log_error(
            message="\n".join(logs),
            title=f"Error en la sincronización del usuario {user_id}"
        )
        return {"status": "error", "message": error_message, "logs": logs}
