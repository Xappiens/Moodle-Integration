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
        logs.append(f"\n[CURSO] Consultando curso en Moodle:")
        logs.append(f"  Parámetros: {course_params}")
        course_response = requests.get(api_url, params=course_params, timeout=30)
        if course_response.status_code != 200:
            logs.append(f"  Error al consultar el curso: {course_response.text}")
            raise ValueError(f"Error al consultar el curso: {course_response.status_code}")
        course_data = course_response.json()[0]
        logs.append(f"  Datos obtenidos: {course_data.get('fullname')}, Inicio: {datetime.utcfromtimestamp(course_data.get('startdate')).strftime('%Y-%m-%d') if course_data.get('startdate') else 'N/A'}, Fin: {datetime.utcfromtimestamp(course_data.get('enddate')).strftime('%Y-%m-%d') if course_data.get('enddate') else 'N/A'}")

        def convert_unix_to_date(unix_timestamp):
            if unix_timestamp:
                return datetime.utcfromtimestamp(unix_timestamp).strftime('%Y-%m-%d')
            return None

        course_start_date = convert_unix_to_date(course_data.get("startdate"))
        course_end_date = convert_unix_to_date(course_data.get("enddate"))

        course_identifier = f"{moodle_instance_name} {course_id}"
        if frappe.db.exists("Moodle Course", {"name": course_identifier}):
            course_doc = frappe.get_doc("Moodle Course", course_identifier)
            logs.append(f"  Curso existente encontrado: {course_identifier}. Actualizando datos.")
        else:
            course_doc = frappe.new_doc("Moodle Course")
            course_doc.name = course_identifier
            logs.append(f"  Creando nuevo curso: {course_identifier}.")

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

        logs.append(f"  Datos guardados en ERPNext:\n    {course_doc.as_dict()}")

        # Paso 2: Crear o Actualizar los Grupos
        group_params = {
            "wstoken": token,
            "wsfunction": "core_group_get_course_groups",
            "moodlewsrestformat": "json",
            "courseid": course_id
        }
        logs.append(f"\n[GRUPOS] Consultando grupos en Moodle:")
        logs.append(f"  Parámetros: {group_params}")
        group_response = requests.get(api_url, params=group_params, timeout=30)
        if group_response.status_code != 200:
            logs.append(f"  Error al consultar grupos: {group_response.text}")
            raise ValueError(f"Error al consultar grupos del curso: {group_response.status_code}")
        groups = group_response.json()
        logs.append("  Grupos obtenidos:")
        group_mapping = {}
        for group in groups:
            group_id = str(group.get("id"))
            group_name = group.get("name")
            logs.append(f"    - ID: {group_id}, Nombre: {group_name}")
            group_identifier = f"{moodle_instance_name} {course_id} {group_name}"

            if frappe.db.exists("Moodle Course Group", {"name": group_identifier}):
                group_doc = frappe.get_doc("Moodle Course Group", {"name": group_identifier})
                logs.append(f"      Existente: {group_identifier}")
            else:
                group_doc = frappe.new_doc("Moodle Course Group")
                group_doc.name = group_identifier
                group_doc.update({
                    "group_name": group_name,
                    "group_instance": moodle_instance_name,
                    "group_course": course_doc.name,
                    "group_moodle_id": group_id
                })
                group_doc.save(ignore_permissions=True)
                logs.append(f"      Creado: {group_identifier}")

            group_mapping[group_id] = group_doc.name
            if group_doc.name not in [row.course_group for row in course_doc.get("course_groups", [])]:
                course_doc.append("course_groups", {"course_group": group_doc.name})
                logs.append(f"      Asociado al curso.")

        course_doc.save(ignore_permissions=True)
        logs.append("  Grupos sincronizados correctamente.")

        # Paso 3: Crear o Actualizar Participantes
        participant_params = {
            "wstoken": token,
            "wsfunction": "core_enrol_get_enrolled_users",
            "moodlewsrestformat": "json",
            "courseid": course_id
        }
        logs.append(f"\n[PARTICIPANTES] Consultando participantes en Moodle:")
        logs.append(f"  Parámetros: {participant_params}")
        participant_response = requests.get(api_url, params=participant_params, timeout=30)
        if participant_response.status_code != 200:
            logs.append(f"  Error al consultar participantes: {participant_response.text}")
            raise ValueError(f"Error al consultar participantes: {participant_response.status_code}")
        participants = participant_response.json()
        logs.append("  Participantes obtenidos:")

        # Validar y guardar estudiantes con grupos
        for participant in participants:
            user_id = participant.get("username")
            user_name = f"{participant.get('firstname')} {participant.get('lastname')}"
            roles = [role.get("shortname") for role in participant.get("roles", [])]
            logs.append(f"    - Nombre: {user_name}, ID: {user_id}, Roles: {roles}")

            user_identifier = f"{moodle_instance_name} {user_id}"
            if frappe.db.exists("Moodle User", {"name": user_identifier}):
                user_doc = frappe.get_doc("Moodle User", user_identifier)
                logs.append(f"      Usuario existente encontrado: {user_identifier}")
            else:
                user_doc = frappe.new_doc("Moodle User")
                user_doc.name = user_identifier
                user_doc.update({
                    "moodle_user_id": participant.get("id"),
                    "user_id": user_id,
                    "user_email": participant.get("email"),
                    "user_name": participant.get("firstname"),
                    "user_surname": participant.get("lastname"),
                    "user_instance": moodle_instance_name
                })
                user_doc.save(ignore_permissions=True)
                logs.append(f"      Usuario creado: {user_identifier}")

            # Validar grupos asignados
            valid_groups = []
            for group in participant.get("groups", []):
                group_id = str(group["id"])
                if group_id in group_mapping:
                    group_name = group_mapping[group_id]
                    if frappe.db.exists("Moodle Course Group", {"name": group_name}):
                        valid_groups.append(group_name)
                        logs.append(f"      Asociado al grupo: {group_name}")
                    else:
                        logs.append(f"      [ADVERTENCIA] Grupo no encontrado en la base de datos: {group_name}")
                else:
                    logs.append(f"      [ADVERTENCIA] Grupo con ID {group_id} no encontrado en el mapeo.")

            # Crear entradas individuales para cada grupo si necesario
            if valid_groups:
                for group_name in valid_groups:
                    student_entry = {
                        "user_student": user_doc.name,
                        "user_group": group_name
                    }
                    course_doc.append("course_students", student_entry)
                    logs.append(f"      Estudiante añadido: {user_identifier}, Grupo: {group_name}")
            else:
                logs.append(f"      [ADVERTENCIA] Sin grupos válidos asignados para {user_identifier}")

            # Agregar roles de profesor si aplica
            if "teacher" in roles or "editingteacher" in roles:
                if user_doc.name not in [row.user_teacher for row in course_doc.get("course_teachers", [])]:
                    course_doc.append("course_teachers", {"user_teacher": user_doc.name})
                    logs.append(f"      Profesor añadido: {user_identifier}")

        # Guardar el documento del curso con validación
        try:
            course_doc.save(ignore_permissions=True)
            logs.append("  Participantes sincronizados correctamente.")
        except Exception as save_error:
            logs.append(f"  [ERROR] No se pudo guardar el curso: {str(save_error)}")
            frappe.log_error(
                message="\n".join(logs),
                title=f"Error al guardar participantes en el curso {course_id}"
            )
            raise


        # Registrar log final
        frappe.log_error(
            message="\n".join(logs),
            title=f"Sincronización para el curso {course_id}"
        )
        return {"status": "success", "message": "Sincronización completada.", "logs": logs}

    except Exception as e:
        error_message = f"Error en process_moodle_course: {str(e)}"
        logs.append(f"\n[ERROR] {error_message}")
        frappe.log_error(
            message="\n".join(logs),
            title=f"Error en la sincronización del curso {course_id}"
        )
        return {"status": "error", "message": str(e), "logs": logs}
