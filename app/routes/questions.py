"""
Exam questions management API endpoints.
Provides question authoring, answer key configuration, and CSV bulk question upload.
"""
import csv
import io
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user

from app.decorators import faculty_required
from app.services.audit import log_action
from app.services.dynamo import get_dynamo_service
from app.utils.helpers import generate_id, to_decimal
from app.utils.validators import validate_question_payload

questions_bp = Blueprint("questions", __name__, url_prefix="/api/questions")


@questions_bp.route("/exam/<string:exam_id>", methods=["GET"])
@faculty_required
def list_questions(exam_id: str):
    """
    Retrieve all questions for an exam, including answer keys.
    Restricted strictly to Faculty and Admin.
    """
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_QUESTIONS", "cms_questions")

    from boto3.dynamodb.conditions import Key
    try:
        items = dynamo.query(
            table_name=table_name,
            key_condition_expression=Key("exam_id").eq(exam_id),
        )
        items.sort(key=lambda x: x.get("order", 0))
        return jsonify({"exam_id": exam_id, "count": len(items), "questions": items}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@questions_bp.route("", methods=["POST"])
@faculty_required
def create_question():
    """Add a question to an exam."""
    data = request.get_json(silent=True) or {}
    exam_id = data.get("exam_id")
    if not exam_id:
        return jsonify({"error": "BadRequest", "message": "exam_id is required."}), 400

    is_valid, err_msg = validate_question_payload(data)
    if not is_valid:
        return jsonify({"error": "ValidationError", "message": err_msg}), 400

    question_id = generate_id("q")
    order = int(data.get("order", 1))
    marks = float(data.get("marks", 1.0))

    item = {
        "exam_id": exam_id.strip(),
        "question_id": question_id,
        "question_text": data["question_text"].strip(),
        "option_a": data["option_a"].strip(),
        "option_b": data["option_b"].strip(),
        "option_c": data["option_c"].strip(),
        "option_d": data["option_d"].strip(),
        "correct_answer": str(data["correct_answer"]).upper().strip(),
        "marks": marks,
        "explanation": data.get("explanation", "").strip(),
        "order": order,
    }

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_QUESTIONS", "cms_questions")

    try:
        dynamo.put_item(table_name=table_name, item=item)
        log_action(current_user.username, "QUESTION_CREATED", f"exam:{exam_id}:q:{question_id}", "Added question")
        return jsonify({"message": "Question created successfully.", "question": item}), 201
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@questions_bp.route("/<string:exam_id>/<string:question_id>", methods=["PUT"])
@faculty_required
def update_question(exam_id: str, question_id: str):
    """Update question contents or answer key."""
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_QUESTIONS", "cms_questions")

    existing = dynamo.get_item(table_name=table_name, key={"exam_id": exam_id, "question_id": question_id})
    if not existing:
        return jsonify({"error": "NotFound", "message": "Question not found."}), 404

    data = request.get_json(silent=True) or {}
    updatable = ["question_text", "option_a", "option_b", "option_c", "option_d", "correct_answer", "marks", "explanation", "order"]

    update_parts = []
    expr_names = {}
    expr_vals = {}

    for field in updatable:
        if field in data and data[field] is not None:
            update_parts.append(f"#{field} = :{field}")
            expr_names[f"#{field}"] = field
            val = data[field]
            if field == "correct_answer":
                expr_vals[f":{field}"] = str(val).upper().strip()
            elif field == "marks":
                expr_vals[f":{field}"] = to_decimal(float(val))
            elif field == "order":
                expr_vals[f":{field}"] = int(val)
            else:
                expr_vals[f":{field}"] = str(val).strip()

    if not update_parts:
        return jsonify({"message": "No changes specified.", "question": existing}), 200

    try:
        updated = dynamo.update_item(
            table_name=table_name,
            key={"exam_id": exam_id, "question_id": question_id},
            update_expression="SET " + ", ".join(update_parts),
            expression_attribute_names=expr_names,
            expression_attribute_values=expr_vals,
        )
        log_action(current_user.username, "QUESTION_UPDATED", f"exam:{exam_id}:q:{question_id}", "Updated question")
        return jsonify({"message": "Question updated successfully.", "question": updated}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@questions_bp.route("/<string:exam_id>/<string:question_id>", methods=["DELETE"])
@faculty_required
def delete_question(exam_id: str, question_id: str):
    """Delete a question from an exam."""
    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_QUESTIONS", "cms_questions")

    existing = dynamo.get_item(table_name=table_name, key={"exam_id": exam_id, "question_id": question_id})
    if not existing:
        return jsonify({"error": "NotFound", "message": "Question not found."}), 404

    try:
        dynamo.delete_item(table_name=table_name, key={"exam_id": exam_id, "question_id": question_id})
        log_action(current_user.username, "QUESTION_DELETED", f"exam:{exam_id}:q:{question_id}", "Deleted question")
        return jsonify({"message": "Question deleted successfully."}), 200
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@questions_bp.route("/exam/<string:exam_id>/bulk-csv", methods=["POST"])
@faculty_required
def bulk_upload_questions(exam_id: str):
    """
    Bulk upload questions from CSV.
    CSV Columns: question_text,option_a,option_b,option_c,option_d,correct_answer,marks,explanation
    """
    csv_text = ""
    if "file" in request.files:
        file = request.files["file"]
        csv_text = file.read().decode("utf-8")
    elif request.is_json and "csv_data" in request.json:
        csv_text = request.json["csv_data"]
    elif request.data:
        csv_text = request.data.decode("utf-8")
    else:
        return jsonify({"error": "BadRequest", "message": "CSV data or file is required."}), 400

    dynamo = get_dynamo_service()
    table_name = current_app.config.get("DYNAMODB_TABLE_QUESTIONS", "cms_questions")

    reader = csv.DictReader(io.StringIO(csv_text))
    items_to_add = []
    errors = []

    for idx, row in enumerate(reader, start=1):
        q_text = row.get("question_text", "").strip()
        opt_a = row.get("option_a", "").strip()
        opt_b = row.get("option_b", "").strip()
        opt_c = row.get("option_c", "").strip()
        opt_d = row.get("option_d", "").strip()
        ans = row.get("correct_answer", "").strip().upper()

        if not (q_text and opt_a and opt_b and opt_c and opt_d and ans):
            errors.append(f"Row {idx}: missing required question or option fields.")
            continue

        if ans not in ("A", "B", "C", "D"):
            errors.append(f"Row {idx}: invalid correct_answer '{ans}'. Must be A, B, C, or D.")
            continue

        try:
            marks = float(row.get("marks", 1.0))
        except (ValueError, TypeError):
            marks = 1.0

        item = {
            "exam_id": exam_id,
            "question_id": generate_id("q"),
            "question_text": q_text,
            "option_a": opt_a,
            "option_b": opt_b,
            "option_c": opt_c,
            "option_d": opt_d,
            "correct_answer": ans,
            "marks": marks,
            "explanation": row.get("explanation", "").strip(),
            "order": idx,
        }
        items_to_add.append(item)

    if not items_to_add:
        return jsonify({
            "error": "ValidationError",
            "message": "No valid question rows found.",
            "errors": errors,
        }), 400

    try:
        count = dynamo.batch_write(table_name=table_name, items=items_to_add)
        log_action(current_user.username, "QUESTIONS_CSV_UPLOAD", f"exam:{exam_id}", f"Uploaded {count} questions")
        return jsonify({
            "message": f"Successfully uploaded {count} questions to exam {exam_id}.",
            "uploaded_count": count,
            "errors": errors,
        }), 201
    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500
