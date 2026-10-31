"""
Attendance management API endpoints.
Provides attendance marking, bulk entry, historical tracking, and real-time Socket.IO broadcasts.
"""
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app.decorators import faculty_required
from app.services.audit import log_action
from app.services.dynamo import get_dynamo_service
from app.sockets.events import emit_attendance_update
from app.utils.helpers import format_date, iso_now, paginate
from app.utils.validators import validate_attendance_payload

attendance_bp = Blueprint("attendance", __name__, url_prefix="/api/attendance")


@attendance_bp.route("", methods=["GET"])
@faculty_required
def list_all_attendance():
    """
    List attendance records across students with pagination.
    Accessible to Faculty and Admin.
    """
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_ATTENDANCE", "cms_attendance")

    date_filter = request.args.get("date")
    course_filter = request.args.get("course_id")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))

    try:
        if course_filter:
            from boto3.dynamodb.conditions import Key
            if date_filter:
                key_cond = Key("course_id").eq(course_filter) & Key("date").eq(date_filter)
            else:
                key_cond = Key("course_id").eq(course_filter)

            items = dynamo.query(
                table_name=table_name,
                index_name="CourseDateIndex",
                key_condition_expression=key_cond,
            )
        else:
            items = dynamo.scan(table_name=table_name)
            if date_filter:
                items = [i for i in items if i.get("date") == date_filter]

        result = paginate(items, page=page, page_size=page_size)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@attendance_bp.route("/student/<string:student_id>", methods=["GET"])
@login_required
def get_student_attendance(student_id: str):
    """
    Retrieve attendance history for a specific student.
    Allowed for Student (self only), Faculty, or Admin.
    """
    if current_user.role == "student":
        user_student_id = current_user.linked_id or current_user.username
        if user_student_id != student_id:
            return jsonify({
                "error": "Forbidden",
                "message": "You can only view your own attendance records.",
            }), 403

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_ATTENDANCE", "cms_attendance")

    from boto3.dynamodb.conditions import Key
    try:
        items = dynamo.query(
            table_name=table_name,
            key_condition_expression=Key("student_id").eq(student_id),
            scan_index_forward=False,
        )

        total_records = len(items)
        present_count = sum(1 for i in items if i.get("status") == "present")
        late_count = sum(1 for i in items if i.get("status") == "late")
        absent_count = sum(1 for i in items if i.get("status") == "absent")
        attendance_percentage = (
            round(((present_count + late_count * 0.5) / total_records) * 100, 2)
            if total_records > 0
            else 0.0
        )

        return jsonify({
            "student_id": student_id,
            "total_records": total_records,
            "summary": {
                "present": present_count,
                "late": late_count,
                "absent": absent_count,
                "percentage": attendance_percentage,
            },
            "records": items,
        }), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@attendance_bp.route("/course/<string:course_id>", methods=["GET"])
@faculty_required
def get_course_attendance(course_id: str):
    """
    Query attendance records by course_id and optional date using CourseDateIndex GSI.
    """
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_ATTENDANCE", "cms_attendance")

    date_filter = request.args.get("date")
    from boto3.dynamodb.conditions import Key

    try:
        if date_filter:
            cond = Key("course_id").eq(course_id) & Key("date").eq(date_filter)
        else:
            cond = Key("course_id").eq(course_id)

        items = dynamo.query(
            table_name=table_name,
            index_name="CourseDateIndex",
            key_condition_expression=cond,
        )
        return jsonify({"course_id": course_id, "count": len(items), "records": items}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@attendance_bp.route("", methods=["POST"])
@faculty_required
def mark_attendance():
    """
    Mark or bulk-mark attendance.
    Accepts a single object or an array of attendance objects under 'entries'.
    """
    data = request.get_json(silent=True) or {}
    entries = data.get("entries") if isinstance(data.get("entries"), list) else [data]

    if not entries or len(entries) == 0:
        return jsonify({"error": "BadRequest", "message": "At least one attendance record is required."}), 400

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_ATTENDANCE", "cms_attendance")

    marked_items = []
    errors = []
    now_str = iso_now()

    for idx, entry in enumerate(entries):
        is_valid, err = validate_attendance_payload(entry)
        if not is_valid:
            errors.append(f"Entry {idx + 1}: {err}")
            continue

        student_id = entry["student_id"].strip()
        course_id = entry["course_id"].strip()
        date_str = entry["date"].strip()
        status_val = entry["status"].lower().strip()
        date_course = f"{date_str}#{course_id}"

        item = {
            "student_id": student_id,
            "date_course": date_course,
            "course_id": course_id,
            "date": date_str,
            "status": status_val,
            "course_name": entry.get("course_name", ""),
            "semester": str(entry.get("semester", "")),
            "marked_by": current_user.username,
            "marked_at": now_str,
        }

        try:
            dynamo.put_item(table_name=table_name, item=item)
            marked_items.append(item)
        except Exception as e:
            errors.append(f"Student {student_id}: {str(e)}")

    if marked_items:
        # Broadcast real-time Socket.IO event
        emit_attendance_update({
            "count": len(marked_items),
            "marked_by": current_user.username,
            "timestamp": now_str,
            "sample": marked_items[0] if marked_items else None,
        })
        log_action(
            current_user.username,
            "ATTENDANCE_MARKED",
            "attendance",
            f"Marked attendance for {len(marked_items)} entries",
        )

    return jsonify({
        "message": f"Successfully processed {len(marked_items)} attendance records.",
        "marked_count": len(marked_items),
        "errors": errors,
        "items": marked_items,
    }), 201 if marked_items else 400


@attendance_bp.route("/<string:student_id>", methods=["PUT"])
@faculty_required
def update_attendance_record(student_id: str):
    """
    Update an individual attendance record.
    Requires date and course_id in request body.
    """
    data = request.get_json(silent=True) or {}
    date_str = data.get("date")
    course_id = data.get("course_id")
    new_status = data.get("status", "").lower().strip()

    if not date_str or not course_id:
        return jsonify({"error": "BadRequest", "message": "date and course_id are required to identify record."}), 400
    if new_status not in ("present", "absent", "late"):
        return jsonify({"error": "ValidationError", "message": "status must be present, absent, or late."}), 400

    date_course = f"{date_str}#{course_id}"
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_ATTENDANCE", "cms_attendance")

    try:
        updated = dynamo.update_item(
            table_name=table_name,
            key={"student_id": student_id, "date_course": date_course},
            update_expression="SET #st = :st, #mb = :mb, #ma = :ma",
            expression_attribute_names={"#st": "status", "#mb": "marked_by", "#ma": "marked_at"},
            expression_attribute_values={
                ":st": new_status,
                ":mb": current_user.username,
                ":ma": iso_now(),
            },
        )
        emit_attendance_update({"action": "update", "item": updated})
        log_action(current_user.username, "ATTENDANCE_EDITED", f"attendance:{student_id}", f"Status updated to {new_status}")
        return jsonify({"message": "Attendance record updated successfully.", "record": updated}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500
