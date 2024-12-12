import frappe
import requests

@frappe.whitelist(allow_guest=True)
def process_moodle_user(moodle_instance_name, user_id, api_url, token):
    """
    Procesa datos relacionados con un user_id para la Moodle Instance especificada.
    """
    logs = []
    try:
        logs.append("Iniciando sincronización de usuario...")

        if not moodle_instance_name or not user_id or not api_url or not token:
            logs.append("Error: Faltan parámetros obligatorios.")
            frappe.log_error("\n".join(logs), "Error en parámetros de entrada")
            return {"status": "error", "message": "Faltan parámetros obligatorios."}

        # Preparar consulta para obtener datos del usuario
        check_user_params = {
            "wstoken": token,
            "wsfunction": "core_user_get_users",
            "moodlewsrestformat": "json",
            "criteria[0][key]": "id",
            "criteria[0][value]": user_id
        }
        logs.append(f"Consulta a la API con parámetros: {check_user_params}")

        # Realizar la solicitud para obtener los datos del usuario
        response = requests.get(api_url, params=check_user_params, timeout=10)
        if response.status_code != 200:
            logs.append(f"Error al consultar la API: {response.status_code}")
            frappe.log_error("\n".join(logs), "Error API Moodle")
            return {"status": "error", "message": "Error al consultar la API de Moodle."}

        # Procesar respuesta del usuario
        response_data = response.json()
        users = response_data.get("users", [])
        if not users:
            logs.append(f"No se encontró el usuario con ID: {user_id}")
            frappe.log_error("\n".join(logs), "Usuario no encontrado")
            return {"status": "error", "message": f"No se encontró el usuario con ID: {user_id}"}

        user_data = users[0]
        logs.append(f"Datos del usuario recuperados: {user_data}")

        # Obtener roles del usuario desde la API usando local_wsgetroles_get_roles
        role_params = {
            "wstoken": token,
            "wsfunction": "local_wsgetroles_get_roles",
            "moodlewsrestformat": "json",
            "userid": user_id
        }
        role_response = requests.get(api_url, params=role_params, timeout=10)
        if role_response.status_code != 200:
            logs.append(f"Error al consultar roles: {role_response.status_code}")
            frappe.log_error("\n".join(logs), "Error en consulta de roles")
            user_role = "Estudiante (student)"  # Valor por defecto
        else:
            role_data = role_response.json()
            logs.append(f"Datos de roles recuperados: {role_data}")

            # Determinar el rol basado en los datos de roles
            role_mapping = {
                1: "Gestor (manager)",
                2: "Creador de curso (coursecreator)",
                3: "Profesor con permiso de edición (editingteacher)",
                4: "Profesor (teacher)",
                5: "Estudiante (student)",
                6: "Invitado (guest)"
            }

            # Si roles existen, toma el primero, si no, asigna por defecto
            if role_data and isinstance(role_data, list):
                role_id = role_data[0].get("roleid", 5)  # Default al ID de estudiante
                user_role = role_mapping.get(role_id, "Estudiante (student)")
            else:
                user_role = "Estudiante (student)"

        # Verificar si el usuario ya existe en Frappe
        existing_user = frappe.db.exists("Moodle User", {"moodle_user_id": user_id})
        if existing_user:
            moodle_user = frappe.get_doc("Moodle User", {"moodle_user_id": user_id})
            logs.append(f"Usuario existente encontrado: {moodle_user.name}")
        else:
            moodle_user = frappe.new_doc("Moodle User")
            moodle_user.moodle_user_id = user_id  # Asignar explícitamente el moodle_user_id
            logs.append(f"Creando un nuevo usuario en Frappe con moodle_user_id: {user_id}")

        # Actualizar o establecer otros datos del usuario
        moodle_user.update({
            "user_name": user_data.get("firstname"),
            "user_surname": user_data.get("lastname"),
            "user_fullname": user_data.get("fullname"),
            "user_dni": user_data.get("idnumber"),
            "user_phone": user_data.get("phone1"),
            "user_email": user_data.get("email"),
            "user_role": user_role,  # Asignar el rol calculado
            "custom_fields": frappe.as_json(user_data.get("customfields", [])),
            "profile_image_url": user_data.get("profileimageurl"),
            "profile_image_url_small": user_data.get("profileimageurlsmall"),
            "user_instance": moodle_instance_name,
        })

        # Guardar el documento
        moodle_user.save(ignore_permissions=True)
        logs.append(f"Usuario sincronizado exitosamente: {moodle_user.name}")

        # Registrar logs y retornar éxito
        frappe.log_error("\n".join(logs), "Sincronización de Usuario Completada")
        return {"status": "success", "message": f"Usuario sincronizado correctamente: {user_id}"}

    except Exception as e:
        logs.append(f"Error encontrado: {str(e)}")
        frappe.log_error("\n".join(logs), "Error en Sincronización de Usuario")
        return {"status": "error", "message": "Ocurrió un error al procesar el usuario.", "error": str(e)}
