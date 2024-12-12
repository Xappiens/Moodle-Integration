import frappe
import requests

@frappe.whitelist(allow_guest=True)
def process_moodle_course(moodle_instance_name, course_id, api_url, token):
    logs = []
    try:
        logs.append("Iniciando proceso para sincronizar curso...")

        # Log inmediato para asegurar que el método se está ejecutando
        frappe.log_error("\n".join(logs), "Debugging: Inicio de process_moodle_course")

        # Validación básica de parámetros
        if not moodle_instance_name or not course_id or not api_url or not token:
            logs.append("Error: Faltan parámetros obligatorios.")
            frappe.log_error("\n".join(logs), "Error de parámetros")
            return {"status": "error", "message": "Faltan parámetros obligatorios."}

        logs.append(f"Parámetros: moodle_instance_name={moodle_instance_name}, course_id={course_id}, api_url={api_url}")

        # Preparar consulta a la API
        check_course_params = {
            "wstoken": token,
            "wsfunction": "core_course_get_courses",
            "moodlewsrestformat": "json",
            "options[ids][0]": course_id
        }
        logs.append(f"Consulta a la API con parámetros: {check_course_params}")

        # Realizar la solicitud
        response = requests.get(api_url, params=check_course_params, timeout=10)
        logs.append(f"Respuesta de la API (status {response.status_code}): {response.text}")

        # Si la respuesta no es 200, loguearlo
        if response.status_code != 200:
            logs.append("Error: La API devolvió un estado inesperado.")
            frappe.log_error("\n".join(logs), f"Error API: {response.status_code}")
            raise ConnectionError("Error al consultar la API de Moodle")

        # Procesar la respuesta
        response_data = response.json()
        logs.append(f"Datos procesados desde la API: {response_data}")

        # Asegurarse de que hay al menos un curso
        if not response_data or not isinstance(response_data, list):
            logs.append(f"No se encontraron cursos para course_id={course_id}. Respuesta: {response_data}")
            raise ValueError("No se encontraron cursos.")

        course_data = response_data[0]
        logs.append(f"Curso procesado: {course_data}")

        # Verificar si el curso ya existe en Frappe
        if frappe.db.exists("Moodle Course", {"course_code": course_id}):
            course_doc = frappe.get_doc("Moodle Course", {"course_code": course_id})
            logs.append(f"Curso existente encontrado: {course_doc.name}")
        else:
            course_doc = frappe.new_doc("Moodle Course")
            course_doc.course_code = course_id
            logs.append("Creando un nuevo curso en Frappe.")

        # Actualizar datos del curso
        course_doc.update({
            "course_name": course_data.get("fullname"),
            "course_start_date": frappe.utils.formatdate(
                course_data.get("startdate"), "yyyy-MM-dd"
            ) if course_data.get("startdate") else None,
            "course_end_date": frappe.utils.formatdate(
                course_data.get("enddate"), "yyyy-MM-dd"
            ) if course_data.get("enddate") else None,
            "course_instance": moodle_instance_name,
        })
        course_doc.save(ignore_permissions=True)
        logs.append(f"Curso guardado: {course_doc.name}")

        # Registrar éxito en logs
        logs.append("Sincronización completada con éxito.")
        frappe.log_error("\n".join(logs), "Proceso Completado")
        return {"status": "success", "message": f"Curso sincronizado: {course_id}"}

    except Exception as e:
        logs.append(f"Error encontrado: {str(e)}")
        frappe.log_error("\n".join(logs), "Error General")
        return {"status": "error", "message": "Ocurrió un error al procesar el curso.", "error": str(e)}
