import frappe
import requests
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def process_moodle_user(moodle_instance_name, user_id, api_url, token, action):
    """
    Sincroniza un usuario de Moodle con ERPNext basado en su ID único de Moodle (user_id).
    Soporta create_user, update_user y delete_user.
    """
    logs = [f"Iniciando {action} para el usuario con ID {user_id} en {moodle_instance_name}."]

    try:
        # **Paso 1: Consultar datos del usuario en Moodle**
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
            raise ValueError(f"Error en la consulta a Moodle: {response.text}")

        user_data_list = response.json().get("users", [])

        if not user_data_list or not isinstance(user_data_list, list) or not user_data_list[0]:
            raise ValueError(f"No se encontró el usuario con ID {user_id} en Moodle.")

        user_data = user_data_list[0]
        logs.append(f"Datos del usuario recuperados: {user_data}")

        moodle_user_id = user_data.get("username")
        if not moodle_user_id:
            raise ValueError(f"No se encontró un 'username' para el usuario con ID {user_id}.")

        logs.append(f"Username recuperado: {moodle_user_id}")

        # **Paso 2: Generar identificador único del usuario**
        user_identifier = f"{moodle_instance_name} {moodle_user_id}"
        logs.append(f"Identificador del usuario: {user_identifier}")

        # **Paso 3: Manejo de eliminación de usuario**
        if action == "delete_user":
            if frappe.db.exists("Moodle User", {"name": user_identifier}):
                frappe.delete_doc("Moodle User", user_identifier)
                logs.append(f"Usuario {user_identifier} eliminado en ERPNext.")
            else:
                logs.append(f"El usuario {user_identifier} no existe en ERPNext, no es necesario eliminarlo.")
            return {"status": "success", "message": "Proceso de eliminación completado.", "logs": logs}

        # **Paso 4: Verificar si el usuario ya existe en ERPNext**
        user_exists = frappe.db.exists("Moodle User", {"name": user_identifier})

        # **Paso 5: Obtener o crear el documento del usuario en ERPNext**
        if user_exists:
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

        # **Paso 6: Actualizar los datos del usuario**
        user_doc.update({
            "user_id": user_id,
            "moodle_user_id": moodle_user_id,
            "user_name": user_data.get("firstname", ""),
            "user_surname": user_data.get("lastname", ""),
            "user_fullname": f"{user_data.get('firstname', '')} {user_data.get('lastname', '')}".strip(),
            "user_email": user_data.get("email", ""),
            "user_dni": user_data.get("idnumber", ""),
            "user_phone": user_data.get("phone1", ""),
            "user_instance": moodle_instance_name,
        })

        # **Paso 7: Restaurar el rol existente si el usuario ya existía**
        if user_exists:
            user_doc.user_type = current_user_type

        # **Paso 8: Guardar el usuario en ERPNext**
        user_doc.save(ignore_permissions=True)
        logs.append(f"Datos guardados en ERPNext:\n    {user_doc.as_dict()}")

        return {"status": "success", "message": "Usuario sincronizado correctamente.", "logs": logs}

    except Exception as e:
        logs.append(f"[ERROR] {str(e)}")
        return {"status": "error", "message": str(e), "logs": logs}
