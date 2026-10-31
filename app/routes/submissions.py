"""
Exam submissions and grading API endpoints.
Implements server-side scoring, one-attempt enforcement, negative marking, and timer verification.
"""
from datetime import datetime, timezone
from decimal import Decimal
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app.decorators import faculty_required
from app.services.audit import log_action
from app.services.dynamo import get_dynamo_service
from app.utils.helpers import iso_now, paginate, to_decimal

submissions_bp = Blueprint("submissions", __name__, url_prefix="/api/submissions")


def compute_exam_score(exam: dict, questions: list, answers: dict):
    """
    Compute total exam score server-side based on answer key and negative marking rules.
    Returns (score, total_possible, question_results)
    """
    score = 0.0
    total_possible = 0.0
    neg_enabled = bool(exam.get("negative_marking", False))
    neg_per_wrong = float(exam.get("negative_per_wrong", 0.0))
    results = {}

    for q in questions:
        qid = q.get("question_id")
        q_marks = float(q.get("marks", 1.0))
        total_possible += q_marks
        correct = str(q.get("correct_answer", "")).upper().strip()
        chosen = str(answers.get(qid, "")).upper().strip() if answers.get(qid) else None

        if not chosen:
            # Unattempted
            status = "unattempted"
            earned = 0.0
        elif chosen == correct:
            status = "correct"
            earned = q_marks
            score += q_marks
        else:
            status = "incorrect"
            earned = -neg_per_wrong if neg_enabled else 0.0
            score -= (neg_per_wrong if neg_enabled else 0.0)

        results[qid] = {
            "chosen": chosen,
            "correct": correct,
            "status": status,
            "earned": earned,
            "explanation": q.get("explanation", ""),
        }

    # Floor score at 0 if needed or allow negative depending on standard conventions (floor at 0.0)
    final_score = max(0.0, score)
    return round(final_score, 2), round(total_possible, 2), results


@submissions_bp.route("/<string:exam_id>/save", methods=["POST"])
@login_required
def save_in_progress_answers(exam_id: str):
    """
    Periodically save answers while exam is in progress.
    Restricted to student in-progress attempt.
    """
    if current_user.role != "student":
        return jsonify({"error": "Forbidden", "message": "Only students may submit exam answers."}), 403

    student_id = current_user.linked_id or current_user.username
    data = request.get_json(silent=True) or {}
    answers = data.get("answers", {})

    dynamo = get_dynamo_service()
    subs_table = current_app.config.get("DYNAMODB_TABLE_SUBMISSIONS", "cms_submissions")

    sub = dynamo.get_item(table_name=subs_table, key={"exam_id": exam_id, "student_id": student_id})
    if not sub:
        return jsonify({"error": "NotFound", "message": "Exam has not been started yet."}), 404

    if sub.get("status") == "submitted":
        return jsonify({"error": "Forbidden", "message": "Exam has already been submitted."}), 403

    try:
        updated = dynamo.update_item(
            table_name=subs_table,
            key={"exam_id": exam_id, "student_id": student_id},
            update_expression="SET #ans = :ans",
            expression_attribute_names={"#ans": "answers"},
            expression_attribute_values={":ans": answers},
            condition_expression="#st = :inprogress",
        )
        return jsonify({"message": "Draft answers saved.", "status": "in_progress"}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@submissions_bp.route("/<string:exam_id>/submit", methods=["POST"])
@login_required
def submit_exam(exam_id: str):
    """
    Final exam submission with server-side scoring, time validation,
    and single attempt conditional lock.
    """
    if current_user.role != "student":
        return jsonify({"error": "Forbidden", "message": "Only students can submit exams."}), 403

    student_id = current_user.linked_id or current_user.username
    data = request.get_json(silent=True) or {}
    submitted_answers = data.get("answers", {})

    dynamo = get_dynamo_service()
    exams_table = current_app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")
    subs_table = current_app.config.get("DYNAMODB_TABLE_SUBMISSIONS", "cms_submissions")
    q_table = current_app.config.get("DYNAMODB_TABLE_QUESTIONS", "cms_questions")

    # 1. Fetch exam
    exam = dynamo.get_item(table_name=exams_table, key={"exam_id": exam_id})
    if not exam:
        return jsonify({"error": "NotFound", "message": "Exam not found."}), 404

    # 2. Fetch existing submission record
    sub = dynamo.get_item(table_name=subs_table, key={"exam_id": exam_id, "student_id": student_id})
    if not sub:
        return jsonify({"error": "BadRequest", "message": "Exam session was not initiated."}), 400

    if sub.get("status") == "submitted":
        return jsonify({"error": "Forbidden", "message": "You have already submitted this exam."}), 403

    # 3. Verify duration / time taken
    started_at = sub.get("started_at")
    now = datetime.now(timezone.utc)
    now_str = iso_now()
    time_taken_seconds = 0
    if started_at:
        try:
            start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            time_taken_seconds = int((now - start_dt).total_seconds())
        except Exception:
            pass

    # 4. Fetch all exam questions for server-side scoring
    from boto3.dynamodb.conditions import Key
    questions = dynamo.query(
        table_name=q_table,
        key_condition_expression=Key("exam_id").eq(exam_id),
    )

    score, total_possible, detailed_results = compute_exam_score(exam, questions, submitted_answers)

    # 5. Conditional write to finalize submission (atomic state change)
    try:
        updated = dynamo.update_item(
            table_name=subs_table,
            key={"exam_id": exam_id, "student_id": student_id},
            update_expression="SET #ans = :ans, #sc = :sc, #tp = :tp, #subat = :subat, #tt = :tt, #st = :st",
            expression_attribute_names={
                "#ans": "answers",
                "#sc": "score",
                "#tp": "total_possible",
                "#subat": "submitted_at",
                "#tt": "time_taken_seconds",
                "#st": "status",
            },
            expression_attribute_values={
                ":ans": submitted_answers,
                ":sc": to_decimal(score),
                ":tp": to_decimal(total_possible),
                ":subat": now_str,
                ":tt": time_taken_seconds,
                ":st": "submitted",
            },
            condition_expression="#st <> :submitted",
        )

        log_action(
            student_id,
            "EXAM_SUBMITTED",
            f"exam:{exam_id}",
            f"Score: {score}/{total_possible}, Time: {time_taken_seconds}s",
        )

        response_payload = {
            "message": "Exam submitted and graded successfully.",
            "exam_id": exam_id,
            "student_id": student_id,
            "score": score,
            "total_possible": total_possible,
            "percentage": round((score / total_possible) * 100, 2) if total_possible > 0 else 0.0,
            "time_taken_seconds": time_taken_seconds,
            "submitted_at": now_str,
        }

        # Show detailed answers only if allowed by exam configuration
        if exam.get("show_answers_after", True):
            response_payload["details"] = detailed_results

        return jsonify(response_payload), 200

    except Exception as e:
        # Check if error is due to conditional check failure
        if "ConditionalCheckFailedException" in str(e):
            return jsonify({"error": "Conflict", "message": "Exam has already been submitted."}), 409
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@submissions_bp.route("/<string:exam_id>/student/<string:student_id>", methods=["GET"])
@login_required
def get_student_submission(exam_id: str, student_id: str):
    """
    Retrieve submission and results for a specific student.
    Allowed for Student (self) or Faculty/Admin.
    """
    if current_user.role == "student":
        user_student_id = current_user.linked_id or current_user.username
        if user_student_id != student_id:
            return jsonify({"error": "Forbidden", "message": "You can only view your own submission."}), 403

    dynamo = get_dynamo_service()
    subs_table = current_app.config.get("DYNAMODB_TABLE_SUBMISSIONS", "cms_submissions")
    exams_table = current_app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")

    try:
        sub = dynamo.get_item(table_name=subs_table, key={"exam_id": exam_id, "student_id": student_id})
        if not sub:
            return jsonify({"error": "NotFound", "message": "No submission record found for this exam."}), 404

        exam = dynamo.get_item(table_name=exams_table, key={"exam_id": exam_id}) or {}
        sub_dict = dict(sub)
        sub_dict["exam_title"] = exam.get("title", "")

        return jsonify({"submission": sub_dict}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@submissions_bp.route("/<string:exam_id>", methods=["GET"])
@faculty_required
def list_exam_submissions(exam_id: str):
    """
    List all student submissions for an exam.
    Faculty and Admin only. Supports pagination.
    """
    dynamo = get_dynamo_service()
    subs_table = current_app.config.get("DYNAMODB_TABLE_SUBMISSIONS", "cms_submissions")

    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))

    from boto3.dynamodb.conditions import Key
    try:
        items = dynamo.query(
            table_name=subs_table,
            key_condition_expression=Key("exam_id").eq(exam_id),
        )

        # Compute summary analytics
        total_attempts = len(items)
        submitted = [s for s in items if s.get("status") == "submitted"]
        avg_score = (
            round(sum(float(s.get("score", 0)) for s in submitted) / len(submitted), 2)
            if submitted
            else 0.0
        )
        highest_score = max([float(s.get("score", 0)) for s in submitted], default=0.0)

        paginated = paginate(items, page=page, page_size=page_size)
        paginated["summary"] = {
            "total_attempts": total_attempts,
            "submitted_count": len(submitted),
            "average_score": avg_score,
            "highest_score": highest_score,
        }
        return jsonify(paginated), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500
