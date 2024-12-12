import frappe
import requests
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def process_moodle_course(moodle_instance_name, course_id, api_url, token):
    logs = []
    try:
        logs.append(f"Inicio de sincronización para el curso {course_id} en {moodle_instance_name}.")

        # Obtener información del curso
        course_params = {
            "wstoken": token,
            "wsfunction": "core_course_get_courses",
            "moodlewsrestformat": "json",
            "options[ids][0]": course_id
        }
        course_response = requests.get(api_url, params=course_params, timeout=30)
        if course_response.status_code != 200:
            raise ValueError(f"Error al consultar el curso: {course_response.status_code}")
        course_data = course_response.json()[0]

        # Extraer fechas y convertirlas
        def convert_unix_to_date(unix_timestamp):
            if unix_timestamp:
                return datetime.utcfromtimestamp(unix_timestamp).strftime('%Y-%m-%d')
            return None

        course_start_date = convert_unix_to_date(course_data.get("startdate"))
        course_end_date = convert_unix_to_date(course_data.get("enddate"))

        # Crear o actualizar el curso
        course_doc = frappe.get_doc("Moodle Course", {"course_code": course_id}) \
            if frappe.db.exists("Moodle Course", {"course_code": course_id}) \
            else frappe.new_doc("Moodle Course")
        course_doc.update({
            "course_name": course_data.get("fullname"),
            "course_code": course_id,
            "course_instance": moodle_instance_name,
            "course_start_date": course_start_date,
            "course_end_date": course_end_date
        })
        course_doc.set("course_students", [])
        course_doc.set("course_teachers", [])

        # Obtener participantes
        participant_params = {
            "wstoken": token,
            "wsfunction": "core_enrol_get_enrolled_users",
            "moodlewsrestformat": "json",
            "courseid": course_id
        }
        participant_response = requests.get(api_url, params=participant_params, timeout=30)
        if participant_response.status_code != 200:
            raise ValueError(f"Error al consultar participantes del curso: {participant_response.status_code}")
        participants = participant_response.json()

        # Procesar estudiantes y profesores
        for participant in participants:
            user_id = participant.get("username")
            name = participant.get("firstname")
            surname = participant.get("lastname")
            email = participant.get("email")
            roles = [role.get("shortname") for role in participant.get("roles", [])]

            if not all([user_id, name, surname, email]):
                logs.append(f"Participante omitido por datos incompletos: {participant}")
                continue

            # Determinar el tipo de usuario
            user_type = "Estudiante"
            if "editingteacher" in roles:
                user_type = "Profesor Editor"
            elif "teacher" in roles:
                user_type = "Profesor"

            # Crear o actualizar usuario en Frappe
            user_doc = frappe.get_doc("Moodle User", {"moodle_user_id": participant.get("id")}) \
                if frappe.db.exists("Moodle User", {"moodle_user_id": participant.get("id")}) \
                else frappe.new_doc("Moodle User")
            user_doc.update({
                "moodle_user_id": participant.get("id"),
                "user_id": user_id,
                "user_name": name,
                "user_surname": surname,
                "user_fullname": f"{name} {surname}",
                "user_email": email,
                "user_instance": moodle_instance_name,
                "user_type": user_type
            })
            user_doc.save(ignore_permissions=True)

            # Asignar a la tabla correspondiente
            if user_type == "Estudiante":
                course_doc.append("course_students", {"user_student": user_id})
            else:
                course_doc.append("course_teachers", {"user_teacher": user_id, "teacher_role": user_type})

        course_doc.save(ignore_permissions=True)
        logs.append(f"Sincronización completada para el curso {course_doc.course_name}.")

        return {"status": "success", "message": "Sincronización completada correctamente.", "logs": logs}

    except Exception as e:
        logs.append(f"Error durante la sincronización: {str(e)}")
        frappe.log_error("\n".join(logs), "Sincronización de Curso: Error")
        return {"status": "error", "message": str(e), "logs": logs}
