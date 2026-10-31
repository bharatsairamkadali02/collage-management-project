"""
Student management API endpoints.
Provides CRUD operations, departmental queries, and CSV bulk import.
"""
import csv
import io
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app.decorators import faculty_required, roles_required
from app.services.audit import log_action
from app.services.dynamo import get_dynamo_service
from app.utils.helpers import iso_now, paginate
from app.utils.validators import validate_student_payload

students_bp = Blueprint("students", __name__, url_prefix="/api/students")


@students_bp.route("", methods=["GET"])
@faculty_required
def list_students():
    """
    List students with optional filtering by department, year, or status.
    Uses DeptYearIndex GSI if department is supplied.
    """
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_STUDENTS", "cms_students")

    department = request.args.get("department")
    year = request.args.get("year")
    status_filter = request.args.get("status")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))

    try:
        if department:
            from boto3.dynamodb.conditions import Key
            if year:
                key_cond = Key("department").eq(department) & Key("year").eq(year)
            else:
                key_cond = Key("department").eq(department)

            items = dynamo.query(
                table_name=table_name,
                index_name="DeptYearIndex",
                key_condition_expression=key_cond,
            )
        else:
            items = dynamo.scan(table_name=table_name)

        if status_filter:
            items = [s for s in items if s.get("status") == status_filter.lower()]

        items.sort(key=lambda x: x.get("student_id", ""))
        result = paginate(items, page=page, page_size=page_size)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@students_bp.route("/<string:student_id>", methods=["GET"])
@login_required
def get_student(student_id: str):
    """
    Retrieve single student profile.
    Accessible to Faculty, Admin, or the student themselves.
    """
    # Enforce self-access check for student role
    if current_user.role == "student":
        user_student_id = current_user.linked_id or current_user.username
        if user_student_id != student_id:
            return jsonify({
                "error": "Forbidden",
                "message": "You can only view your own student profile.",
            }), 403

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_STUDENTS", "cms_students")

    try:
        student = dynamo.get_item(table_name=table_name, key={"student_id": student_id})
        if not student:
            return jsonify({"error": "NotFound", "message": f"Student '{student_id}' not found."}), 404

        return jsonify({"student": student}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@students_bp.route("", methods=["POST"])
@faculty_required
def create_student():
    """Create a new student record."""
    data = request.get_json(silent=True) or {}
    is_valid, err_msg = validate_student_payload(data, is_update=False)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    student_id = data["student_id"].strip()
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_STUDENTS", "cms_students")

    # Check if student_id already exists
    existing = dynamo.get_item(table_name=table_name, key={"student_id": student_id})
    if existing:
        return jsonify({"error": "Conflict", "message": f"Student ID '{student_id}' already exists."}), 409

    item = {
        "student_id": student_id,
        "full_name": data["full_name"].strip(),
        "email": data["email"].strip().lower(),
        "phone": data.get("phone", "").strip(),
        "department": data["department"].strip(),
        "year": str(data["year"]).strip(),
        "semester": str(data["semester"]).strip(),
        "enrollment_date": data.get("enrollment_date", iso_now()[:10]),
        "status": data.get("status", "active"),
    }

    try:
        dynamo.put_item(
            table_name=table_name,
            item=item,
            condition_expression="attribute_not_exists(student_id)",
        )
        log_action(current_user.username, "STUDENT_CREATED", f"student:{student_id}", f"Dept: {item['department']}")
        return jsonify({"message": "Student created successfully.", "student": item}), 201
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@students_bp.route("/<string:student_id>", methods=["PUT"])
@faculty_required
def update_student(student_id: str):
    """Update student profile attributes."""
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_STUDENTS", "cms_students")

    existing = dynamo.get_item(table_name=table_name, key={"student_id": student_id})
    if not existing:
        return jsonify({"error": "NotFound", "message": f"Student '{student_id}' not found."}), 404

    data = request.get_json(silent=True) or {}
    is_valid, err_msg = validate_student_payload(data, is_update=True)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    updatable = ["full_name", "email", "phone", "department", "year", "semester", "status"]
    update_parts = []
    expr_names = {}
    expr_vals = {}

    for field in updatable:
        if field in data and data[field] is not None:
            update_parts.append(f"#{field} = :{field}")
            expr_names[f"#{field}"] = field
            expr_vals[f":{field}"] = str(data[field]).strip()

    if not update_parts:
        return jsonify({"message": "No updates supplied.", "student": existing}), 200

    try:
        updated = dynamo.update_item(
            table_name=table_name,
            key={"student_id": student_id},
            update_expression="SET " + ", ".join(update_parts),
            expression_attribute_names=expr_names,
            expression_attribute_values=expr_vals,
        )
        log_action(current_user.username, "STUDENT_UPDATED", f"student:{student_id}", "Updated student details")
        return jsonify({"message": "Student updated successfully.", "student": updated}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@students_bp.route("/<string:student_id>", methods=["DELETE"])
@faculty_required
def delete_student(student_id: str):
    """Delete a student record."""
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_STUDENTS", "cms_students")

    existing = dynamo.get_item(table_name=table_name, key={"student_id": student_id})
    if not existing:
        return jsonify({"error": "NotFound", "message": f"Student '{student_id}' not found."}), 404

    try:
        dynamo.delete_item(table_name=table_name, key={"student_id": student_id})
        log_action(current_user.username, "STUDENT_DELETED", f"student:{student_id}", "Student record deleted")
        return jsonify({"message": f"Student '{student_id}' deleted successfully."}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@students_bp.route("/import-csv", methods=["POST"])
@faculty_required
def import_students_csv():
    """
    Import students from a CSV file upload or raw CSV string.
    CSV header format: student_id,full_name,email,phone,department,year,semester,status
    """
    csv_content = ""
    if "file" in request.files:
        file = request.files["file"]
        csv_content = file.read().decode("utf-8")
    elif request.is_json and "csv_data" in request.json:
        csv_content = request.json["csv_data"]
    elif request.data:
        csv_content = request.data.decode("utf-8")
    else:
        return jsonify({
            "error": "BadRequest",
            "message": "CSV data required. Upload a file or provide 'csv_data' string.",
        }), 400

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_STUDENTS", "cms_students")

    reader = csv.DictReader(io.StringIO(csv_content))
    created_items = []
    errors = []

    for idx, row in enumerate(reader, start=1):
        sid = row.get("student_id", "").strip()
        full_name = row.get("full_name", "").strip()
        email = row.get("email", "").strip()
        dept = row.get("department", "").strip()
        year = row.get("year", "").strip()
        sem = row.get("semester", "").strip()

        if not (sid and full_name and email and dept and year and sem):
            errors.append(f"Row {idx}: missing required fields for student {sid or 'unknown'}.")
            continue

        item = {
            "student_id": sid,
            "full_name": full_name,
            "email": email.lower(),
            "phone": row.get("phone", "").strip(),
            "department": dept,
            "year": str(year),
            "semester": str(sem),
            "enrollment_date": row.get("enrollment_date", iso_now()[:10]),
            "status": row.get("status", "active").strip().lower(),
        }
        created_items.append(item)

    if not created_items:
        return jsonify({
            "error": "ValidationError",
            "message": "No valid student rows found to import.",
            "errors": errors,
        }), 400

    try:
        count = dynamo.batch_write(table_name=table_name, items=created_items)
        log_action(current_user.username, "STUDENTS_CSV_IMPORT", "students", f"Imported {count} students")
        return jsonify({
            "message": f"Successfully imported {count} students.",
            "imported_count": count,
            "error_count": len(errors),
            "errors": errors,
        }), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500
