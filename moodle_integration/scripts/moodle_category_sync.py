import frappe
import requests

@frappe.whitelist(allow_guest=True)
def process_moodle_category(moodle_instance_name, category_id, api_url, token):
    logs = []
    try:
        logs.append(f"Iniciando sincronización para la categoría {category_id} en {moodle_instance_name}.")

        # Paso 1: Obtener información de la categoría desde Moodle
        category_params = {
            "wstoken": token,
            "wsfunction": "core_course_get_categories",
            "moodlewsrestformat": "json",
            "criteria[0][key]": "id",
            "criteria[0][value]": category_id
        }
        category_response = requests.get(api_url, params=category_params, timeout=30)
        if category_response.status_code != 200:
            raise ValueError(f"Error al consultar la categoría: {category_response.status_code}")
        category_data = category_response.json()
        if not category_data:
            raise ValueError(f"No se encontró ninguna categoría con ID {category_id}")

        category_info = category_data[0]
        logs.append(f"Categoría obtenida: {category_info.get('name')}.")

        # Obtener la categoría padre (si existe)
        parent_category_name = None
        if category_info.get("parent"):
            parent_id = str(category_info["parent"])
            logs.append(f"Buscando categoría padre con ID: {parent_id}.")
            parent_category_doc = frappe.db.get_value(
                "Moodle Course Category", {"coursecat_id": parent_id}, "name"
            )
            if parent_category_doc:
                parent_category_name = parent_category_doc
                logs.append(f"Categoría padre encontrada: {parent_category_name}.")
            else:
                logs.append(f"Advertencia: No se encontró la Categoría Padre con ID {parent_id} en ERPNext.")

        # Crear o Actualizar la categoría en ERPNext
        category_identifier = f"{moodle_instance_name} {category_id}"
        logs.append(f"Verificando existencia de la categoría con identificador: {category_identifier}.")
        if frappe.db.exists("Moodle Course Category", {"name": category_identifier}):
            category_doc = frappe.get_doc("Moodle Course Category", category_identifier)
            logs.append(f"Categoría existente encontrada: {category_identifier}. Actualizando datos.")
        else:
            category_doc = frappe.new_doc("Moodle Course Category")
            category_doc.name = category_identifier
            logs.append(f"Creando nueva categoría: {category_identifier}.")

        category_doc.update({
            "coursecat_id": str(category_info.get("id")),
            "coursecat_name": category_info.get("name"),
            "coursecat_description": category_info.get("description"),
            "coursecat_parent": parent_category_name,
            "coursecat_instance": moodle_instance_name
        })
        category_doc.set("coursecat_subcat", [])
        category_doc.save(ignore_permissions=True)
        logs.append(f"Categoría sincronizada: {category_doc.coursecat_name}.")

        # Paso 2: Sincronizar subcategorías
        logs.append("Iniciando sincronización de subcategorías.")
        subcategories_params = {
            "wstoken": token,
            "wsfunction": "core_course_get_categories",
            "moodlewsrestformat": "json",
            "criteria[0][key]": "parent",
            "criteria[0][value]": category_id
        }
        subcategories_response = requests.get(api_url, params=subcategories_params, timeout=30)
        if subcategories_response.status_code != 200:
            raise ValueError(f"Error al consultar subcategorías: {subcategories_response.status_code}")
        subcategories_data = subcategories_response.json()

        for subcategory in subcategories_data:
            subcat_id = str(subcategory.get("id"))
            subcat_name = subcategory.get("name")

            subcat_identifier = f"{moodle_instance_name} {subcat_id}"
            logs.append(f"Procesando subcategoría: {subcat_name} (ID: {subcat_id}).")
            if frappe.db.exists("Moodle Course Category", {"name": subcat_identifier}):
                subcat_doc = frappe.get_doc("Moodle Course Category", subcat_identifier)
                logs.append(f"Subcategoría existente encontrada: {subcat_identifier}. Actualizando datos.")
            else:
                subcat_doc = frappe.new_doc("Moodle Course Category")
                subcat_doc.name = subcat_identifier
                logs.append(f"Creando nueva subcategoría: {subcat_identifier}.")

            # Validar que la subcategoría no se asocie a sí misma como padre
            if subcat_identifier != category_identifier:
                subcat_doc.update({
                    "coursecat_id": subcat_id,
                    "coursecat_name": subcat_name,
                    "coursecat_description": subcategory.get("description"),
                    "coursecat_parent": category_doc.name,
                    "coursecat_instance": moodle_instance_name
                })
                subcat_doc.save(ignore_permissions=True)
                category_doc.append("coursecat_subcat", {"coursecat_subcat": subcat_doc.name})
                logs.append(f"Subcategoría sincronizada: {subcat_name}.")
            else:
                logs.append(f"Subcategoría {subcat_name} (ID: {subcat_id}) omitida: no puede asociarse a sí misma como padre.")

        category_doc.save(ignore_permissions=True)
        logs.append("Sincronización de subcategorías completada.")

        # Paso 3: Actualizar categoría en cursos existentes
        logs.append("Iniciando actualización de cursos.")
        courses_params = {
            "wstoken": token,
            "wsfunction": "core_course_get_courses_by_field",
            "moodlewsrestformat": "json",
            "field": "category",
            "value": category_id
        }
        courses_response = requests.get(api_url, params=courses_params, timeout=30)
        if courses_response.status_code != 200:
            raise ValueError(f"Error al consultar cursos: {courses_response.status_code}")
        courses_data = courses_response.json().get("courses", [])

        for course in courses_data:
            course_id = str(course.get("id"))
            course_identifier = f"{moodle_instance_name} {course_id}"
            logs.append(f"Procesando curso: {course_identifier}.")
            if frappe.db.exists("Moodle Course", {"name": course_identifier}):
                course_doc = frappe.get_doc("Moodle Course", course_identifier)
                course_doc.update({"course_category": category_doc.name})
                course_doc.save(ignore_permissions=True)
                logs.append(f"Curso actualizado: {course_doc.course_name}.")
            else:
                logs.append(f"Curso con ID {course_id} no encontrado en ERPNext. Omitiendo.")

        logs.append("Sincronización completa para la categoría.")
        frappe.log_error("\n".join(logs), f"Sincronización de Categoría {category_id}")
        return {"status": "success", "message": "Sincronización completada correctamente.", "logs": logs}

    except Exception as e:
        logs.append(f"Error durante la sincronización: {str(e)}")
        frappe.log_error("\n".join(logs), f"Error en Sincronización de Categoría {category_id}")
        return {"status": "error", "message": str(e), "logs": logs}
