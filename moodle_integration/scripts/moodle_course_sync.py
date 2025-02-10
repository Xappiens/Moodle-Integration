import frappe
import requests
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def process_moodle_course(moodle_instance_name, course_id, api_url, token, action):
    """
    Sincroniza un curso de Moodle con Frappe basado en su ID único de Moodle (course_id).
    Soporta create_course, update_course y delete_course.
    """
    logs = [f"Iniciando {action} para el curso con ID {course_id} en {moodle_instance_name}."]

    try:
        # Generar identificador único del curso
        course_identifier = f"{moodle_instance_name} {course_id}"
        logs.append(f"Identificador del curso: {course_identifier}")

        # Manejo de eliminación de curso
        if action == "delete_course":
            if frappe.db.exists("Moodle Course", {"name": course_identifier}):
                frappe.delete_doc("Moodle Course", course_identifier)
                logs.append(f"Curso {course_identifier} eliminado en ERPNext.")
            else:
                logs.append(f"El curso {course_identifier} no existe en ERPNext, no es necesario eliminarlo.")

            return {"status": "success", "message": "Proceso de eliminación completado.", "logs": logs}

        # Si es create_course o update_course, proceder con la sincronización
        def fetch_data(api_params, description):
            logs.append(f"\n[{description}] Consultando datos:")
            logs.append(f"  Parámetros: {api_params}")
            response = requests.get(api_url, params=api_params, timeout=30)
            if response.status_code != 200:
                logs.append(f"  Error en la consulta: {response.text}")
                raise ValueError(f"Error al consultar {description}: {response.status_code}")
            return response.json()

        def convert_unix_to_date(unix_timestamp):
            return datetime.utcfromtimestamp(unix_timestamp).strftime('%Y-%m-%d') if unix_timestamp else None

        # Paso 1: Obtener datos del curso desde Moodle
        course_params = {
            "wstoken": token,
            "wsfunction": "core_course_get_courses",
            "moodlewsrestformat": "json",
            "options[ids][0]": course_id,
        }
        course_data = fetch_data(course_params, "curso")[0]

        course_start_date = convert_unix_to_date(course_data.get("startdate"))
        course_end_date = convert_unix_to_date(course_data.get("enddate"))

        # Verificar si el curso ya existe en ERPNext
        course_exists = frappe.db.exists("Moodle Course", {"name": course_identifier})

        # Obtener o crear el documento del curso en ERPNext
        course_doc = (
            frappe.get_doc("Moodle Course", course_identifier)
            if course_exists
            else frappe.new_doc("Moodle Course")
        )

        logs.append(
            f"{'Actualizando' if course_exists else 'Creando'} curso en ERPNext: {course_identifier}."
        )

        course_doc.update({
            "course_name": course_data.get("fullname"),
            "course_code": course_id,
            "course_instance": moodle_instance_name,
            "course_start_date": course_start_date,
            "course_end_date": course_end_date,
            "course_students": [],
            "course_teachers": [],
            "course_groups": [],
        })
        course_doc.save(ignore_permissions=True)
        logs.append(f"Datos del curso guardados:\n  {course_doc.as_dict()}")

        # Paso 2: Sincronizar grupos del curso desde Moodle
        group_params = {
            "wstoken": token,
            "wsfunction": "core_group_get_course_groups",
            "moodlewsrestformat": "json",
            "courseid": course_id,
        }
        groups = fetch_data(group_params, "grupos")
        group_mapping = {}

        for group in groups:
            group_id, group_name = str(group["id"]), group["name"]
            group_identifier = f"{course_doc.name} {group_name}"

            group_doc = (
                frappe.get_doc("Moodle Course Group", {"name": group_identifier})
                if frappe.db.exists("Moodle Course Group", {"name": group_identifier})
                else frappe.new_doc("Moodle Course Group")
            )
            group_doc.update({
                "group_name": group_name,
                "group_instance": moodle_instance_name,
                "group_course": course_doc.name,
                "group_moodle_id": group_id,
            })
            group_doc.save(ignore_permissions=True)

            group_mapping[group_id] = group_doc.name
            if group_doc.name not in [row.course_group for row in course_doc.get("course_groups", [])]:
                course_doc.append("course_groups", {"course_group": group_doc.name})

        course_doc.save(ignore_permissions=True)
        logs.append("Grupos sincronizados correctamente.")

        # Paso 3: Sincronizar participantes del curso desde Moodle
        participant_params = {
            "wstoken": token,
            "wsfunction": "core_enrol_get_enrolled_users",
            "moodlewsrestformat": "json",
            "courseid": course_id,
        }
        participants = fetch_data(participant_params, "participantes")

        if not participants:
            logs.append(f"[ADVERTENCIA] No se encontraron participantes en el curso {course_id}.")
        else:
            for participant in participants:
                user_identifier = f"{moodle_instance_name} {participant.get('username')}"
                user_doc = (
                    frappe.get_doc("Moodle User", user_identifier)
                    if frappe.db.exists("Moodle User", {"name": user_identifier})
                    else frappe.new_doc("Moodle User")
                )

                # Definir user_type basado en roles de Moodle
                user_roles = [role["shortname"] for role in participant.get("roles", [])]
                if "editingteacher" in user_roles:
                    user_type = "Profesor Editor"
                elif "teacher" in user_roles:
                    user_type = "Profesor"
                else:
                    user_type = "Estudiante"

                user_doc.update({
                    "user_id": participant.get("id"),
                    "moodle_user_id": participant.get("username"),
                    "user_name": participant.get("firstname"),
                    "user_surname": participant.get("lastname"),
                    "user_fullname": f"{participant.get('firstname')} {participant.get('lastname')}",
                    "user_email": participant.get("email"),
                    "user_dni": participant.get("idnumber"),
                    "user_phone": participant.get("phone"),
                    "user_instance": moodle_instance_name,
                    "user_type": user_type
                })

                user_doc.save(ignore_permissions=True)

                # Vincular usuario a grupos en Moodle
                for group in participant.get("groups", []):
                    group_id = str(group["id"])
                    if group_id in group_mapping:
                        last_group_name = group_mapping[group_id]
                        break
                else:
                    last_group_name = None

                course_doc.append(
                    "course_students" if user_type == "Estudiante" else "course_teachers",
                    {"user_student" if user_type == "Estudiante" else "user_teacher": user_doc.name, "user_group": last_group_name}
                )

            course_doc.save(ignore_permissions=True)
            logs.append("Participantes vinculados correctamente.")

        return {"status": "success", "message": "Sincronización completada.", "logs": logs}

    except Exception as e:
        logs.append(f"[ERROR] {str(e)}")
        return {"status": "error", "message": str(e), "logs": logs}
