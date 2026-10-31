"""
Academic Results API endpoints.
Provides grade management, SGPA calculation, real-time result events, and S3 presigned report downloads.
"""
import io
import json
from decimal import Decimal
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app.decorators import faculty_required
from app.services.audit import log_action
from app.services.dynamo import get_dynamo_service
from app.services.s3_service import get_s3_service
from app.sockets.events import emit_result_update
from app.utils.helpers import iso_now, paginate, to_decimal
from app.utils.validators import validate_result_payload

results_bp = Blueprint("results", __name__, url_prefix="/api/results")


def calculate_grade_and_status(marks: float, max_marks: float):
    """Calculate letter grade, pass/fail status, and grade point from marks."""
    percentage = (marks / max_marks) * 100
    if percentage >= 90:
        grade = "A+"
        points = 10.0
    elif percentage >= 80:
        grade = "A"
        points = 9.0
    elif percentage >= 70:
        grade = "B"
        points = 8.0
    elif percentage >= 60:
        grade = "C"
        points = 7.0
    elif percentage >= 50:
        grade = "D"
        points = 6.0
    elif percentage >= 40:
        grade = "E"
        points = 5.0
    else:
        grade = "F"
        points = 0.0

    pass_fail = "PASS" if percentage >= 40 else "FAIL"
    return grade, points, pass_fail


@results_bp.route("", methods=["GET"])
@faculty_required
def list_results():
    """List all results with pagination and optional student filter. Faculty/Admin only."""
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_RESULTS", "cms_results")

    student_id = request.args.get("student_id")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))

    try:
        if student_id:
            from boto3.dynamodb.conditions import Key
            items = dynamo.query(
                table_name=table_name,
                key_condition_expression=Key("student_id").eq(student_id),
            )
        else:
            items = dynamo.scan(table_name=table_name)

        result = paginate(items, page=page, page_size=page_size)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@results_bp.route("/student/<string:student_id>", methods=["GET"])
@login_required
def get_student_results(student_id: str):
    """
    Retrieve all results for a student.
    Allowed for Student (self only), Faculty, or Admin.
    """
    if current_user.role == "student":
        user_student_id = current_user.linked_id or current_user.username
        if user_student_id != student_id:
            return jsonify({
                "error": "Forbidden",
                "message": "You can only view your own academic results.",
            }), 403

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_RESULTS", "cms_results")

    from boto3.dynamodb.conditions import Key
    try:
        items = dynamo.query(
            table_name=table_name,
            key_condition_expression=Key("student_id").eq(student_id),
        )

        # Calculate GPA / summary
        total_subjects = len(items)
        passed_subjects = sum(1 for i in items if i.get("pass_fail") == "PASS")
        avg_sgpa = (
            round(sum(float(i.get("sgpa", 0)) for i in items) / total_subjects, 2)
            if total_subjects > 0
            else 0.0
        )

        return jsonify({
            "student_id": student_id,
            "total_subjects": total_subjects,
            "passed_subjects": passed_subjects,
            "cumulative_gpa": avg_sgpa,
            "results": items,
        }), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@results_bp.route("", methods=["POST"])
@faculty_required
def add_result():
    """Add a new academic result entry for a student."""
    data = request.get_json(silent=True) or {}
    is_valid, err_msg = validate_result_payload(data)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    student_id = data["student_id"].strip()
    semester = str(data["semester"]).strip()
    subject_code = data["subject_code"].strip().upper()
    sem_subject = f"{semester}#{subject_code}"

    marks = float(data["marks_obtained"])
    max_marks = float(data["max_marks"])
    grade, sgpa, pass_fail = calculate_grade_and_status(marks, max_marks)

    now_str = iso_now()
    item = {
        "student_id": student_id,
        "sem_subject": sem_subject,
        "semester": semester,
        "subject_code": subject_code,
        "subject_name": data.get("subject_name", "").strip(),
        "marks_obtained": marks,
        "max_marks": max_marks,
        "grade": grade,
        "sgpa": sgpa,
        "pass_fail": pass_fail,
        "added_by": current_user.username,
        "added_at": now_str,
    }

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_RESULTS", "cms_results")

    try:
        dynamo.put_item(table_name=table_name, item=item)
        emit_result_update(item)
        log_action(
            current_user.username,
            "RESULT_ADDED",
            f"result:{student_id}:{sem_subject}",
            f"Marks: {marks}/{max_marks}, Grade: {grade}",
        )
        return jsonify({"message": "Result added successfully.", "result": item}), 201
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@results_bp.route("/<string:student_id>", methods=["PUT"])
@faculty_required
def update_result(student_id: str):
    """
    Update marks for a specific student and subject.
    Requires semester and subject_code in payload.
    """
    data = request.get_json(silent=True) or {}
    semester = str(data.get("semester", "")).strip()
    subject_code = str(data.get("subject_code", "")).strip().upper()

    if not semester or not subject_code:
        return jsonify({"error": "BadRequest", "message": "semester and subject_code are required."}), 400

    sem_subject = f"{semester}#{subject_code}"
    marks = float(data.get("marks_obtained", 0))
    max_marks = float(data.get("max_marks", 100))
    grade, sgpa, pass_fail = calculate_grade_and_status(marks, max_marks)

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_RESULTS", "cms_results")

    try:
        updated = dynamo.update_item(
            table_name=table_name,
            key={"student_id": student_id, "sem_subject": sem_subject},
            update_expression="SET #mo = :mo, #mm = :mm, #gr = :gr, #sg = :sg, #pf = :pf, #ab = :ab, #aa = :aa",
            expression_attribute_names={
                "#mo": "marks_obtained",
                "#mm": "max_marks",
                "#gr": "grade",
                "#sg": "sgpa",
                "#pf": "pass_fail",
                "#ab": "added_by",
                "#aa": "added_at",
            },
            expression_attribute_values={
                ":mo": to_decimal(marks),
                ":mm": to_decimal(max_marks),
                ":gr": grade,
                ":sg": to_decimal(sgpa),
                ":pf": pass_fail,
                ":ab": current_user.username,
                ":aa": iso_now(),
            },
        )
        emit_result_update(updated)
        log_action(
            current_user.username,
            "RESULT_UPDATED",
            f"result:{student_id}:{sem_subject}",
            f"Updated marks to {marks}/{max_marks}",
        )
        return jsonify({"message": "Result updated successfully.", "result": updated}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@results_bp.route("/student/<string:student_id>/download", methods=["GET"])
@login_required
def download_marksheet_url(student_id: str):
    """
    Generate student marksheet, upload to S3 under results/{student_id}/...,
    and return an S3 presigned download URL valid for 1 hour.
    """
    if current_user.role == "student":
        user_student_id = current_user.linked_id or current_user.username
        if user_student_id != student_id:
            return jsonify({
                "error": "Forbidden",
                "message": "You can only download your own transcript.",
            }), 403

    dynamo = get_dynamo_service()
    results_table = current_app.config.get("DYNAMODB_TABLE_RESULTS", "cms_results")
    students_table = current_app.config.get("DYNAMODB_TABLE_STUDENTS", "cms_students")

    from boto3.dynamodb.conditions import Key
    try:
        student = dynamo.get_item(table_name=students_table, key={"student_id": student_id}) or {}
        items = dynamo.query(
            table_name=results_table,
            key_condition_expression=Key("student_id").eq(student_id),
        )

        # Generate a structured JSON transcript
        transcript_data = {
            "college": "College Management System",
            "report_title": "Official Academic Transcript",
            "generated_at": iso_now(),
            "student_id": student_id,
            "student_name": student.get("full_name", "N/A"),
            "department": student.get("department", "N/A"),
            "academic_records": items,
        }

        s3 = get_s3_service()
        object_key = f"results/{student_id}/transcript_{student_id}.json"
        body_bytes = json.dumps(transcript_data, indent=2).encode("utf-8")

        s3.upload_file(
            file_obj=body_bytes,
            object_key=object_key,
            content_type="application/json",
            metadata={"student_id": student_id},
        )

        presigned_url = s3.generate_presigned_url(object_key=object_key, expiration=3600)
        log_action(current_user.username, "TRANSCRIPT_GENERATED", f"student:{student_id}", f"S3 key: {object_key}")

        return jsonify({
            "message": "Presigned download URL generated successfully.",
            "download_url": presigned_url,
            "expires_in_seconds": 3600,
            "s3_key": object_key,
        }), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500
