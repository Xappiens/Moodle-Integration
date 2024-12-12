import frappe
import requests

@frappe.whitelist(allow_guest=True)
def process_moodle_user(moodle_instance_name, user_id, api_url, token):
    """
    Procesa datos relacionados con un user_id para la Moodle Instance especificada.
    """
    try:
        # Validar entrada
        if not moodle_instance_name or not user_id or not api_url or not token:
            return {"status": "error", "message": "Faltan parámetros obligatorios."}

        # Parámetros para la consulta de usuario en la API de Moodle
        check_user_params = {
            "wstoken": token,
            "wsfunction": "core_user_get_users",
            "moodlewsrestformat": "json",
            "criteria[0][key]": "id",
            "criteria[0][value]": user_id
        }

        # Realizar la solicitud a la API
        response = requests.get(api_url, params=check_user_params, timeout=10)
        if response.status_code != 200:
            return {"status": "error", "message": "Error al consultar la API de Moodle"}

        # Procesar la respuesta de la API
        response_data = response.json()
        users = response_data.get("users", [])
        if not users:
            return {"status": "error", "message": f"No se encontró el usuario con ID: {user_id}"}

        # Actualizar el Moodle User en Frappe
        moodle_user = frappe.get_doc("Moodle User", user_id)
        moodle_user_data = users[0]
        moodle_user.update({
            "user_name": moodle_user_data.get("firstname"),
            "user_surname": moodle_user_data.get("lastname"),
            "user_fullname": moodle_user_data.get("fullname"),
            "user_dni": moodle_user_data.get("idnumber"),
            "user_phone": moodle_user_data.get("phone1"),
            "user_email": moodle_user_data.get("email"),
            "user_role": "Estudiante (student)",
            "custom_fields": frappe.as_json(moodle_user_data.get("customfields", [])),
            "profile_image_url": moodle_user_data.get("profileimageurl"),
            "profile_image_url_small": moodle_user_data.get("profileimageurlsmall"),
        })

        # Guardar los cambios
        moodle_user.save(ignore_permissions=True)

        # Retornar éxito
        return {"status": "success", "message": f"Usuario actualizado correctamente: {user_id}"}

    except Exception as e:
        frappe.log_error(message=f"Error en process_moodle_user: {str(e)}", title="Error en process_moodle_user")
        return {"status": "error", "message": "Hubo un error al procesar los datos.", "error": str(e)}
