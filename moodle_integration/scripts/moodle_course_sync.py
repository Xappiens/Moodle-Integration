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
            
            # Generar identificador único del grupo
            group_identifier = f"{course_doc.name} {group_name}"

            # Verificar si ya existe un grupo con el mismo nombre
            if frappe.db.exists("Moodle Course Group", {"name": group_identifier}):
                logs.append(f"Grupo ya existente: {group_identifier}.")
                group_doc = frappe.get_doc("Moodle Course Group", {"name": group_identifier})
            else:
                # Crear nuevo grupo
                group_doc = frappe.new_doc("Moodle Course Group")
                group_doc.name = group_identifier
                group_doc.update({
                    "group_name": group_name,
                    "group_instance": moodle_instance_name,
                    "group_course": course_doc.name,
                    "group_moodle_id": group_id  # Considerar este campo para garantizar unicidad
                })
                try:
                    group_doc.save(ignore_permissions=True)
                    logs.append(f"Grupo creado: {group_identifier}.")
                except Exception as e:
                    logs.append(f"Error al guardar el grupo: {str(e)}")
                    frappe.log_error(
                        message=f"Error al guardar grupo {group_identifier}: {str(e)}",
                        title="Error de sincronización de grupos"
                    )

            # Actualizar mapeo de grupos
            group_mapping[group_id] = group_doc.name

            # Asociar grupo al curso si no está ya asociado
            if group_doc.name not in [row.course_group for row in course_doc.get("course_groups", [])]:
                course_doc.append("course_groups", {"course_group": group_doc.name})
                logs.append(f"Grupo asociado al curso: {group_doc.name}")


        course_doc.save(ignore_permissions=True)
        logs.append("  Grupos sincronizados correctamente.")

        # Paso 3: Consultar y procesar participantes
        participant_params = {
            "wstoken": token,
            "wsfunction": "core_enrol_get_enrolled_users",
            "moodlewsrestformat": "json",
            "courseid": course_id
        }
        logs.append(f"\n[PARTICIPANTES] Consultando participantes en Moodle:")
        logs.append(f"  Parámetros: {participant_params}")

        try:
            participant_response = requests.get(api_url, params=participant_params, timeout=30)
            if participant_response.status_code != 200:
                logs.append(f"  Error al consultar participantes: {participant_response.text}")
                raise ValueError(f"Error al consultar participantes: {participant_response.status_code}")
            
            participants = participant_response.json()
            if not participants:
                # Log de advertencia si no hay participantes
                warning_message = f"No se encontraron participantes en el curso {course_id}. Esto puede ser normal si el curso aún no tiene inscritos."
                logs.append(f"  [ADVERTENCIA] {warning_message}")
                frappe.log_error(
                    message="\n".join(logs),
                    title=f"Advertencia: Sin participantes en el curso {course_id}"
                )
            else:
                logs.append("  Participantes obtenidos correctamente.")
            
            # Continuar con el procesamiento normal si hay participantes
            for participant in participants:
                # Procesar participantes aquí
                pass

        except Exception as e:
            logs.append(f"  [ERROR] No se pudo obtener participantes: {str(e)}")
            frappe.log_error(
                message="\n".join(logs),
                title=f"Error al consultar participantes en el curso {course_id}"
            )
            raise


        # Diccionarios para mapeo y evitar duplicados
        student_mapping = {}
        teacher_mapping = {}

        for participant in participants:
            user_id = participant.get("username")
            user_name = f"{participant.get('firstname')} {participant.get('lastname')}"
            roles = [role.get("shortname") for role in participant.get("roles", [])]
            logs.append(f"    - Nombre: {user_name}, ID: {user_id}, Roles: {roles}")

            # Obtener o crear el usuario en Moodle User
            user_identifier = f"{moodle_instance_name} {user_id}"
            if frappe.db.exists("Moodle User", {"name": user_identifier}):
                user_doc = frappe.get_doc("Moodle User", user_identifier)
                logs.append(f"      Usuario existente encontrado: {user_identifier}")
            else:
                user_doc = frappe.new_doc("Moodle User")
                user_doc.name = user_identifier
                
                # Obtener roles del usuario desde Moodle
                roles = user_data.get("roles", [])
                if any(role.get("shortname") == "editingteacher" for role in roles):
                    user_type = "Profesor Editor"
                elif any(role.get("shortname") == "teacher" for role in roles):
                    user_type = "Profesor"
                else:
                    user_type = "Estudiante"  # Valor predeterminado

                # Actualizar el documento del usuario con el rol correcto
                user_doc.update({
                    "user_name": user_data.get("firstname"),
                    "user_surname": user_data.get("lastname"),
                    "user_fullname": f"{user_data.get('firstname')} {user_data.get('lastname')}",  # Combina nombre y apellidos.
                    "user_email": user_data.get("email"),
                    "user_instance": moodle_instance_name,
                    "user_type": user_type
                })
                user_doc.save(ignore_permissions=True)
                logs.append(f"      Usuario creado: {user_identifier}")

            # Determinar el último grupo del usuario
            last_group_name = None
            for group in participant.get("groups", []):
                group_id = str(group["id"])
                if group_id in group_mapping:
                    group_name = group_mapping[group_id]
                    if frappe.db.exists("Moodle Course Group", {"name": group_name}):
                        last_group_name = group_name
                        logs.append(f"      Último grupo asociado: {group_name}")
                    else:
                        logs.append(f"      [ADVERTENCIA] Grupo no encontrado en la base de datos: {group_name}")
                else:
                    logs.append(f"      [ADVERTENCIA] Grupo con ID {group_id} no encontrado en el mapeo.")

            # Añadir o actualizar estudiantes
            if "student" in roles:
                existing_student = next((row for row in course_doc.get("course_students", []) if row.user_student == user_doc.name), None)
                if existing_student:
                    existing_student.user_group = last_group_name  # Actualizar último grupo asignado
                    logs.append(f"      Estudiante existente actualizado: {user_identifier}, Último grupo: {last_group_name}")
                else:
                    course_doc.append("course_students", {"user_student": user_doc.name, "user_group": last_group_name})
                    logs.append(f"      Estudiante añadido: {user_identifier}, Último grupo: {last_group_name}")

            # Añadir o actualizar profesores
            if "teacher" in roles or "editingteacher" in roles:
                existing_teacher = next((row for row in course_doc.get("course_teachers", []) if row.user_teacher == user_doc.name), None)
                if not existing_teacher:
                    course_doc.append("course_teachers", {"user_teacher": user_doc.name})
                    logs.append(f"      Profesor añadido: {user_identifier}")
                else:
                    logs.append(f"      Profesor existente encontrado: {user_identifier}, No se requiere acción adicional.")

        # Guardar el documento del curso
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

        # Guardar el documento del curso
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
