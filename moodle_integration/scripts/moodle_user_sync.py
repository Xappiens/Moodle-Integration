import frappe
import requests
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def process_moodle_user(moodle_instance_name, user_id, api_url, token):
    """
    Sincroniza un usuario de Moodle con Frappe basado en el enfoque exitoso de 'process_moodle_course'.
    """
    logs = []
    try:
        logs.append(f"Iniciando sincronización para el usuario {user_id} en {moodle_instance_name}.")

        # Paso 1: Consultar datos del usuario desde Moodle
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
        users = response_data.get("users", [])
        if not users:
            raise ValueError(f"No se encontró el usuario con ID {user_id} en Moodle.")

        user_data = users[0]
        logs.append(f"Datos del usuario recuperados: {user_data}")

        # Paso 2: Generar identificador único para el usuario
        user_identifier = f"{moodle_instance_name} {user_id}"
        logs.append(f"Identificador del usuario: {user_identifier}")

        # Paso 3: Crear o actualizar el usuario
        if frappe.db.exists("Moodle User", {"name": user_identifier}):
            moodle_user = frappe.get_doc("Moodle User", user_identifier)
            logs.append(f"Usuario existente encontrado: {user_identifier}. Actualizando datos.")
        else:
            moodle_user = frappe.new_doc("Moodle User")
            moodle_user.name = user_identifier
            moodle_user.user_connection_status = "Desconectado"  # Valor inicial
            logs.append(f"Creando nuevo usuario: {user_identifier}.")

        # Actualizar los datos del usuario
        moodle_user.update({
            "moodle_user_id": user_data.get("id"),
            "user_id": user_id,  # Asegurar que se asigna correctamente el user_id
            "user_name": user_data.get("firstname"),
            "user_surname": user_data.get("lastname"),
            "user_fullname": f"{user_data.get('firstname')} {user_data.get('lastname')}",  # Combina nombre y apellidos.
            "user_dni": user_data.get("username"),  # Suposición: 'username' contiene el DNI
            "user_phone": user_data.get("phone1"),
            "user_email": user_data.get("email"),
            "user_instance": moodle_instance_name,
            "user_type": "Estudiante"  # Valor predeterminado
        })

        # Guardar el usuario
        moodle_user.save(ignore_permissions=True)
        logs.append(f"Datos guardados en ERPNext:\n    {moodle_user.as_dict()}")

        # Registrar log final
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
