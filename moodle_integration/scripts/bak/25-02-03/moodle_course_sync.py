import frappe
import requests
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def process_moodle_course(moodle_instance_name, course_id, api_url, token):
    # Inicializar un registro de logs para registrar el proceso
    logs = [
        f"Iniciando sincronización para el curso {course_id} en {moodle_instance_name}."
    ]
    
    try:
        # Función auxiliar para realizar solicitudes HTTP al API de Moodle
        def fetch_data(api_params, description):
            logs.append(f"\n[{description}] Consultando datos:")
            logs.append(f"  Parámetros: {api_params}")
            response = requests.get(api_url, params=api_params, timeout=30)
            if response.status_code != 200:
                logs.append(f"  Error en la consulta: {response.text}")
                raise ValueError(
                    f"Error al consultar {description}: {response.status_code}"
                )
            return response.json()

        # Función auxiliar para convertir un timestamp Unix a una fecha legible
        def convert_unix_to_date(unix_timestamp):
            return (
                datetime.utcfromtimestamp(unix_timestamp).strftime('%Y-%m-%d')
                if unix_timestamp
                else None
            )

        # Paso 1: Obtener datos del curso desde Moodle
        course_params = {
            "wstoken": token,
            "wsfunction": "core_course_get_courses",
            "moodlewsrestformat": "json",
            "options[ids][0]": course_id,
        }
        course_data = fetch_data(course_params, "curso")[0]

        # Convertir fechas de inicio y fin del curso
        course_start_date = convert_unix_to_date(course_data.get("startdate"))
        course_end_date = convert_unix_to_date(course_data.get("enddate"))
        course_identifier = f"{moodle_instance_name} {course_id}"

        # Crear o actualizar el documento del curso en ERPNext
        course_doc = (
            frappe.get_doc("Moodle Course", course_identifier)
            if frappe.db.exists("Moodle Course", {"name": course_identifier})
            else frappe.new_doc("Moodle Course")
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
        group_mapping = {}  # Mapear IDs de Moodle a nombres de grupos en ERPNext

        for group in groups:
            group_id, group_name = str(group["id"]), group["name"]
            group_identifier = f"{course_doc.name} {group_name}"

            # Crear o actualizar el documento del grupo en ERPNext
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

            # Actualizar el mapeo y asociar el grupo al curso
            group_mapping[group_id] = group_doc.name
            if group_doc.name not in [
                row.course_group for row in course_doc.get("course_groups", [])
            ]:
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
                user_id = participant.get("id")  # Identificador numérico único de Moodle
                moodle_user_id = participant.get("username")  # Nombre de usuario en Moodle
                first_name = participant.get("firstname")
                last_name = participant.get("lastname")
                email = participant.get("email")
                dni = participant.get("idnumber")  # DNI proporcionado por Moodle
                birthdate = participant.get("birthdate")  # Fecha de nacimiento (puede requerir conversión de UNIX)
                phone = participant.get("phone")  # Teléfono, si está disponible
                user_identifier = f"{moodle_instance_name} {moodle_user_id}"  # Formato del name basado en `moodle_user_id`

                # Verificar si ya existe un usuario basado en el name o el user_id
                existing_user = frappe.db.exists("Moodle User", {"name": user_identifier}) or \
                                frappe.db.exists("Moodle User", {"user_id": user_id})

                if existing_user:
                    user_doc = frappe.get_doc("Moodle User", existing_user)
                    logs.append(f"[INFO] Usuario encontrado y actualizado: {user_doc.name}")
                else:
                    user_doc = frappe.new_doc("Moodle User")
                    user_doc.name = user_identifier  # Asignar el formato correcto del name
                    logs.append(f"[INFO] Nuevo usuario creado: {user_identifier}")

                # Actualizar campos del usuario
                user_doc.update({
                    "user_id": user_id,  # Identificador numérico único de Moodle
                    "moodle_user_id": moodle_user_id,  # Nombre de usuario en Moodle
                    "user_name": first_name,
                    "user_surname": last_name,
                    "user_fullname": f"{first_name} {last_name}",
                    "user_email": email,
                    "user_dni": dni,
                    "user_birthdate": datetime.utcfromtimestamp(birthdate).strftime('%Y-%m-%d') if birthdate else None,
                    "user_phone": phone,
                    "user_instance": moodle_instance_name,
                    "user_type": (
                        "Profesor Editor" if any(role["shortname"] == "editingteacher" for role in participant.get("roles", []))
                        else "Profesor" if any(role["shortname"] == "teacher" for role in participant.get("roles", []))
                        else "Estudiante"
                    ),
                })

                # Guardar el usuario
                try:
                    user_doc.save(ignore_permissions=True)
                except frappe.ValidationError as e:
                    logs.append(f"[ERROR] No se pudo guardar el usuario {user_identifier}: {str(e)}")
                    continue

                # Vincular al curso y grupo
                last_group_name = next(
                    (
                        group_mapping[str(group["id"])]
                        for group in participant.get("groups", [])
                        if str(group["id"]) in group_mapping
                    ),
                    None,
                )
                if user_doc.user_type == "Estudiante":
                    course_doc.append(
                        "course_students",
                        {"user_student": user_doc.name, "user_group": last_group_name},
                    )
                elif user_doc.user_type.startswith("Profesor"):
                    course_doc.append(
                        "course_teachers", {"user_teacher": user_doc.name}
                    )

            # Guardar el curso
            course_doc.save(ignore_permissions=True)
            logs.append("Participantes vinculados correctamente.")


        # Registrar los logs como mensaje en ERPNext
        frappe.log_error("\n".join(logs), f"Sincronización para el curso {course_id}")
        return {"status": "success", "message": "Sincronización completada.", "logs": logs}

    except Exception as e:
        # Manejar errores y registrar logs
        error_message = f"Error en process_moodle_course: {str(e)}"
        logs.append(f"[ERROR] {error_message}")
        frappe.log_error("\n".join(logs), f"Error en la sincronización del curso {course_id}")
        return {"status": "error", "message": str(e), "logs": logs}
