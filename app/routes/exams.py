"""
Exams management API endpoints.
Provides exam lifecycle management, status changes, and secure exam initiation for students.
"""
import copy
import random
from datetime import datetime, timezone
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app.decorators import faculty_required
from app.services.audit import log_action
from app.services.dynamo import get_dynamo_service
from app.sockets.events import emit_exam_status_changed
from app.utils.helpers import generate_id, iso_now, paginate, to_decimal
from app.utils.validators import validate_exam_payload

exams_bp = Blueprint("exams", __name__, url_prefix="/api/exams")


@exams_bp.route("", methods=["GET"])
@login_required
def list_exams():
    """
    List exams.
    Students see only 'open' exams (or 'closed' if finished).
    Faculty and Admins see all exams (draft, open, closed).
    """
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")

    status_filter = request.args.get("status")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))

    try:
        # If student, restrict to 'open' status by default unless specifically asking for closed
        if current_user.role == "student":
            status_query = status_filter if status_filter in ("open", "closed") else "open"
            from boto3.dynamodb.conditions import Key
            items = dynamo.query(
                table_name=table_name,
                index_name="StatusTimeIndex",
                key_condition_expression=Key("status").eq(status_query),
            )
        elif status_filter:
            from boto3.dynamodb.conditions import Key
            items = dynamo.query(
                table_name=table_name,
                index_name="StatusTimeIndex",
                key_condition_expression=Key("status").eq(status_filter),
            )
        else:
            items = dynamo.scan(table_name=table_name)

        items.sort(key=lambda x: x.get("start_time", ""), reverse=True)
        result = paginate(items, page=page, page_size=page_size)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@exams_bp.route("/<string:exam_id>", methods=["GET"])
@login_required
def get_exam(exam_id: str):
    """Retrieve details for a single exam."""
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")

    try:
        exam = dynamo.get_item(table_name=table_name, key={"exam_id": exam_id})
        if not exam:
            return jsonify({"error": "NotFound", "message": f"Exam '{exam_id}' not found."}), 404

        if current_user.role == "student" and exam.get("status") == "draft":
            return jsonify({"error": "Forbidden", "message": "Draft exams cannot be viewed by students."}), 403

        return jsonify({"exam": exam}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@exams_bp.route("", methods=["POST"])
@faculty_required
def create_exam():
    """Create a new examination (Faculty/Admin)."""
    data = request.get_json(silent=True) or {}
    is_valid, err_msg = validate_exam_payload(data, is_update=False)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    exam_id = generate_id("exam")
    now_str = iso_now()

    item = {
        "exam_id": exam_id,
        "title": data["title"].strip(),
        "course_id": data["course_id"].strip(),
        "course_name": data["course_name"].strip(),
        "duration_minutes": int(data["duration_minutes"]),
        "start_time": data["start_time"].strip(),
        "end_time": data["end_time"].strip(),
        "total_marks": float(data.get("total_marks", 100)),
        "negative_marking": bool(data.get("negative_marking", False)),
        "negative_per_wrong": float(data.get("negative_per_wrong", 0.0)),
        "status": data.get("status", "draft").strip().lower(),
        "show_answers_after": bool(data.get("show_answers_after", True)),
        "created_by": current_user.username,
        "created_at": now_str,
    }

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")

    try:
        dynamo.put_item(table_name=table_name, item=item)
        log_action(current_user.username, "EXAM_CREATED", f"exam:{exam_id}", f"Title: {item['title']}")
        return jsonify({"message": "Exam created successfully.", "exam": item}), 201
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@exams_bp.route("/<string:exam_id>", methods=["PUT"])
@faculty_required
def update_exam(exam_id: str):
    """Update exam parameters."""
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")

    existing = dynamo.get_item(table_name=table_name, key={"exam_id": exam_id})
    if not existing:
        return jsonify({"error": "NotFound", "message": f"Exam '{exam_id}' not found."}), 404

    data = request.get_json(silent=True) or {}
    is_valid, err_msg = validate_exam_payload(data, is_update=True)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    updatable = [
        "title", "course_id", "course_name", "duration_minutes",
        "start_time", "end_time", "total_marks", "negative_marking",
        "negative_per_wrong", "status", "show_answers_after"
    ]
    update_parts = []
    expr_names = {}
    expr_vals = {}

    status_changed = False
    new_status = None

    for field in updatable:
        if field in data and data[field] is not None:
            update_parts.append(f"#{field} = :{field}")
            expr_names[f"#{field}"] = field
            val = data[field]
            if field == "status":
                status_changed = True
                new_status = str(val).lower()
                expr_vals[f":{field}"] = new_status
            elif field in ("total_marks", "negative_per_wrong"):
                expr_vals[f":{field}"] = to_decimal(float(val))
            elif field == "duration_minutes":
                expr_vals[f":{field}"] = int(val)
            elif field in ("negative_marking", "show_answers_after"):
                expr_vals[f":{field}"] = bool(val)
            else:
                expr_vals[f":{field}"] = str(val).strip()

    if not update_parts:
        return jsonify({"message": "No updates supplied.", "exam": existing}), 200

    try:
        updated = dynamo.update_item(
            table_name=table_name,
            key={"exam_id": exam_id},
            update_expression="SET " + ", ".join(update_parts),
            expression_attribute_names=expr_names,
            expression_attribute_values=expr_vals,
        )

        if status_changed:
            emit_exam_status_changed({"exam_id": exam_id, "status": new_status, "title": existing.get("title")})

        log_action(current_user.username, "EXAM_UPDATED", f"exam:{exam_id}", "Updated exam attributes")
        return jsonify({"message": "Exam updated successfully.", "exam": updated}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@exams_bp.route("/<string:exam_id>", methods=["DELETE"])
@faculty_required
def delete_exam(exam_id: str):
    """Delete an exam."""
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")

    existing = dynamo.get_item(table_name=table_name, key={"exam_id": exam_id})
    if not existing:
        return jsonify({"error": "NotFound", "message": f"Exam '{exam_id}' not found."}), 404

    try:
        dynamo.delete_item(table_name=table_name, key={"exam_id": exam_id})
        log_action(current_user.username, "EXAM_DELETED", f"exam:{exam_id}", "Deleted exam")
        return jsonify({"message": f"Exam '{exam_id}' deleted successfully."}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@exams_bp.route("/<string:exam_id>/start", methods=["POST"])
@login_required
def start_exam(exam_id: str):
    """
    Start an exam for the currently logged-in student.
    Enforces time window validation, single attempt check,
    shuffles questions per student seed, and STRIPS correct answers!
    """
    if current_user.role != "student":
        return jsonify({"error": "Forbidden", "message": "Only students may start and attempt exams."}), 403

    student_id = current_user.linked_id or current_user.username
    dynamo = get_dynamo_service()

    exams_table = current_app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")
    subs_table = current_app.config.get("DYNAMODB_TABLE_SUBMISSIONS", "cms_submissions")
    q_table = current_app.config.get("DYNAMODB_TABLE_QUESTIONS", "cms_questions")

    # 1. Fetch exam
    exam = dynamo.get_item(table_name=exams_table, key={"exam_id": exam_id})
    if not exam:
        return jsonify({"error": "NotFound", "message": "Exam not found."}), 404

    if exam.get("status") != "open":
        return jsonify({"error": "BadRequest", "message": f"Exam is not currently open (status: {exam.get('status')})."}), 400

    # 2. Time Window Enforcement
    now = datetime.now(timezone.utc)
    try:
        start_dt = datetime.fromisoformat(exam["start_time"].replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(exam["end_time"].replace("Z", "+00:00"))
        if now < start_dt:
            return jsonify({"error": "BadRequest", "message": "Exam has not started yet."}), 400
        if now > end_dt:
            return jsonify({"error": "BadRequest", "message": "Exam has already concluded."}), 400
    except (ValueError, KeyError) as e:
        # If dates are in YYYY-MM-DDTHH:MM:SS format
        pass

    # 3. Check if submission already exists (One attempt rule)
    existing_sub = dynamo.get_item(table_name=subs_table, key={"exam_id": exam_id, "student_id": student_id})
    if existing_sub:
        if existing_sub.get("status") == "submitted":
            return jsonify({
                "error": "Forbidden",
                "message": "You have already completed and submitted this exam.",
            }), 403
        # If already in progress, return existing session
        started_at = existing_sub.get("started_at")
    else:
        # Record initial in_progress attempt
        now_str = iso_now()
        started_at = now_str
        initial_sub = {
            "exam_id": exam_id,
            "student_id": student_id,
            "answers": {},
            "score": 0.0,
            "total_possible": float(exam.get("total_marks", 0)),
            "started_at": started_at,
            "submitted_at": None,
            "time_taken_seconds": 0,
            "status": "in_progress",
        }
        try:
            dynamo.put_item(
                table_name=subs_table,
                item=initial_sub,
                condition_expression="attribute_not_exists(exam_id) AND attribute_not_exists(student_id)",
            )
            log_action(student_id, "EXAM_STARTED", f"exam:{exam_id}", "Student started exam attempt")
        except Exception as e:
            # Conditional check failed -> already started by another request
            pass

    # 4. Fetch questions and secure them (NEVER send correct_answer or explanation)
    from boto3.dynamodb.conditions import Key
    raw_questions = dynamo.query(
        table_name=q_table,
        key_condition_expression=Key("exam_id").eq(exam_id),
    )

    if not raw_questions:
        return jsonify({"error": "NotFound", "message": "No questions have been configured for this exam."}), 404

    # Shuffle questions per student using deterministic seed (student_id + exam_id)
    student_seed = f"{student_id}_{exam_id}"
    rng = random.Random(student_seed)
    questions = copy.deepcopy(raw_questions)
    rng.shuffle(questions)

    sanitized_questions = []
    for q in questions:
        sanitized_questions.append({
            "question_id": q.get("question_id"),
            "question_text": q.get("question_text"),
            "option_a": q.get("option_a"),
            "option_b": q.get("option_b"),
            "option_c": q.get("option_c"),
            "option_d": q.get("option_d"),
            "marks": q.get("marks", 1),
            # STRICT SECURITY: correct_answer & explanation are NOT included!
        })

    return jsonify({
        "exam_id": exam_id,
        "title": exam.get("title"),
        "duration_minutes": exam.get("duration_minutes"),
        "started_at": started_at,
        "total_questions": len(sanitized_questions),
        "questions": sanitized_questions,
    }), 200
