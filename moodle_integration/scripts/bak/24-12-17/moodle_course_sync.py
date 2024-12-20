import frappe
import requests
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def process_moodle_course(moodle_instance_name, course_id, api_url, token):
    logs = []
    try:
        logs.append(f"Iniciando sincronización para el curso {course_id} en {moodle_instance_name}.")

        # Paso 1: Crear o Actualizar el Curso
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

        def convert_unix_to_date(unix_timestamp):
            if unix_timestamp:
                return datetime.utcfromtimestamp(unix_timestamp).strftime('%Y-%m-%d')
            return None

        course_start_date = convert_unix_to_date(course_data.get("startdate"))
        course_end_date = convert_unix_to_date(course_data.get("enddate"))

        course_identifier = f"{moodle_instance_name} {course_id}"

        if frappe.db.exists("Moodle Course", {"name": course_identifier}):
            course_doc = frappe.get_doc("Moodle Course", course_identifier)
            logs.append(f"Curso existente encontrado: {course_identifier}. Actualizando datos.")
        else:
            course_doc = frappe.new_doc("Moodle Course")
            course_doc.name = course_identifier
            logs.append(f"Creando nuevo curso: {course_identifier}.")

        course_doc.update({
            "course_name": course_data.get("fullname"),
            "course_code": course_id,
            "course_instance": moodle_instance_name,
            "course_start_date": course_start_date,
            "course_end_date": course_end_date
        })
        course_doc.set("course_students", [])
        course_doc.set("course_teachers", [])
        course_doc.set("course_groups", [])
        course_doc.save(ignore_permissions=True)

        # Paso 2: Crear o Actualizar Grupos
        group_params = {
            "wstoken": token,
            "wsfunction": "core_group_get_course_groups",
            "moodlewsrestformat": "json",
            "courseid": course_id
        }
        group_response = requests.get(api_url, params=group_params, timeout=30)
        if group_response.status_code != 200:
            raise ValueError(f"Error al consultar grupos del curso: {group_response.status_code}")
        groups = group_response.json()

        group_mapping = {}
        for group in groups:
            group_id = str(group.get("id"))
            group_name = group.get("name")
            group_identifier = f"{moodle_instance_name} {course_id} {group_name}"

            group_doc = frappe.get_doc("Moodle Course Group", {"name": group_identifier}) \
                if frappe.db.exists("Moodle Course Group", {"name": group_identifier}) \
                else frappe.new_doc("Moodle Course Group")
            group_doc.update({
                "group_name": group_name,
                "group_instance": moodle_instance_name,
                "group_course": course_doc.name,
                "group_moodle_id": group_id
            })
            group_doc.save(ignore_permissions=True)

            group_mapping[group_id] = group_name
            if group_name not in [row.course_group for row in course_doc.get("course_groups", [])]:
                course_doc.append("course_groups", {
                    "course_group": group_doc.name
                })

        course_doc.save(ignore_permissions=True)

        # Paso 3: Crear o Actualizar Usuarios y Grupos de Estudiantes
        participant_params = {
            "wstoken": token,
            "wsfunction": "core_enrol_get_enrolled_users",
            "moodlewsrestformat": "json",
            "courseid": course_id
        }
        participant_response = requests.get(api_url, params=participant_params, timeout=30)
        if participant_response.status_code != 200:
            raise ValueError(f"Error al consultar participantes: {participant_response.status_code}")
        participants = participant_response.json()

        for participant in participants:
            user_id = participant.get("username")
            user_moodle_id = participant.get("id")
            user_email = participant.get("email")
            user_name = participant.get("firstname")
            user_surname = participant.get("lastname")
            roles = [role.get("shortname") for role in participant.get("roles", [])]
            user_groups = [group_mapping[str(g_id)] for g_id in participant.get("groups", [])]

            user_doc = frappe.get_doc("Moodle User", {"name": user_moodle_id}) \
                if frappe.db.exists("Moodle User", {"name": user_moodle_id}) \
                else frappe.new_doc("Moodle User")
            user_doc.update({
                "moodle_user_id": user_moodle_id,
                "user_id": user_id,
                "user_email": user_email,
                "user_name": user_name,
                "user_surname": user_surname,
                "user_instance": moodle_instance_name
            })
            user_doc.save(ignore_permissions=True)

            if "student" in roles:
                existing_students = [
                    row.user_student for row in course_doc.get("course_students", [])
                ]
                if user_doc.name not in existing_students:
                    course_doc.append("course_students", {
                        "user_student": user_doc.name,
                        "user_group": ", ".join(user_groups)  # Asigna los grupos del estudiante
                    })

            if "teacher" in roles:
                existing_teachers = [
                    row.user_teacher for row in course_doc.get("course_teachers", [])
                ]
                if user_doc.name not in existing_teachers:
                    course_doc.append("course_teachers", {"user_teacher": user_doc.name})

        course_doc.save(ignore_permissions=True)
        logs.append(f"Sincronización completada para el curso {course_id}.")

        return {"status": "success", "message": "Sincronización completada.", "logs": logs}
    except Exception as e:
        frappe.log_error(message=f"Error en process_moodle_course: {str(e)}", title="Error en process_moodle_course")
        return {"status": "error", "message": str(e), "logs": logs}
