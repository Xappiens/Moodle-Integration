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

        # Procesar fechas
        def convert_unix_to_date(unix_timestamp):
            if unix_timestamp:
                return datetime.utcfromtimestamp(unix_timestamp).strftime('%Y-%m-%d')
            return None

        course_start_date = convert_unix_to_date(course_data.get("startdate"))
        course_end_date = convert_unix_to_date(course_data.get("enddate"))

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
        course_doc.set("course_groups", [])
        course_doc.save(ignore_permissions=True)
        logs.append(f"Curso sincronizado: {course_doc.course_name}.")

        # Paso 2: Crear o Actualizar los Grupos
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

            # Crear o actualizar grupo en `Moodle Course Group`
            group_doc = frappe.get_doc("Moodle Course Group", {"group_moodle_id": group_id}) \
                if frappe.db.exists("Moodle Course Group", {"group_moodle_id": group_id}) \
                else frappe.new_doc("Moodle Course Group")
            group_doc.update({
                "group_name": group_name,
                "group_instance": moodle_instance_name,
                "group_course": course_doc.name,
                "group_moodle_id": group_id
            })
            group_doc.save(ignore_permissions=True)

            # Mapear group_id a group_name
            group_mapping[group_id] = group_doc.group_name
            logs.append(f"Grupo registrado: ID {group_id}, Nombre '{group_name}'")

            # Agregar grupo a la tabla `course_groups` si no existe
            existing_groups = [row.course_group for row in course_doc.get("course_groups", [])]
            if group_name not in existing_groups:
                course_doc.append("course_groups", {"course_group": group_name})
                logs.append(f"Grupo '{group_name}' agregado a la tabla de grupos del curso.")
        course_doc.save(ignore_permissions=True)

        # Paso 3: Crear o Actualizar Participantes
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

        # Paso 4: Crear o Actualizar Usuarios y Colocar Participantes en Tablas
        for participant in participants:
            user_id = participant.get("username")
            user_moodle_id = participant.get("id")
            user_email = participant.get("email")
            user_name = participant.get("firstname")
            user_surname = participant.get("lastname")
            roles = [role.get("shortname") for role in participant.get("roles", [])]
            group_objects = participant.get("groups", [])  # Obtener lista de grupos como objetos

            # Crear o Actualizar Usuario
            user_doc = frappe.get_doc("Moodle User", {"moodle_user_id": user_moodle_id}) \
                if frappe.db.exists("Moodle User", {"moodle_user_id": user_moodle_id}) \
                else frappe.new_doc("Moodle User")
            user_doc.update({
                "moodle_user_id": user_moodle_id,
                "user_id": user_id,
                "user_email": user_email,
                "user_name": user_name,
                "user_surname": user_surname,
                "user_fullname": f"{user_name} {user_surname}",
                "user_instance": moodle_instance_name
            })
            user_doc.save(ignore_permissions=True)
            logs.append(f"Usuario sincronizado: {user_name} {user_surname} ({user_id})")

            # Extraer IDs de grupos
            group_ids = [str(group["id"]) for group in group_objects if isinstance(group, dict) and "id" in group]

            # Validar y asociar grupos
            group_names = []
            for gid in group_ids:
                if gid in group_mapping:
                    group_names.append(group_mapping[gid])
                else:
                    logs.append(f"Advertencia: Grupo no encontrado para ID {gid}")

            group_display = ", ".join(group_names) if group_names else ""
            logs.append(f"Estudiante '{user_id}' pertenece a grupos: {group_display}")

            if "teacher" in roles:
                course_doc.append("course_teachers", {"user_teacher": user_id, "teacher_role": "Profesor"})
            else:
                course_doc.append("course_students", {"user_student": user_id, "user_group": group_display})
        course_doc.save(ignore_permissions=True)
        logs.append("Participantes colocados en tablas correctamente.")

        # Consolidar logs en ERPNext
        frappe.log_error("\n".join(logs), f"Sincronización Completa: Curso {course_id}")
        return {"status": "success", "message": "Sincronización completada correctamente.", "logs": logs}

    except Exception as e:
        logs.append(f"Error durante la sincronización: {str(e)}")
        frappe.log_error("\n".join(logs), f"Error en Sincronización: Curso {course_id}")
        return {"status": "error", "message": str(e), "logs": logs}
