"""
Validation helpers for incoming request payloads across all API routes.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
VALID_ROLES = {"admin", "faculty", "student"}
VALID_USER_STATUS = {"active", "disabled"}
VALID_STUDENT_STATUS = {"active", "graduated", "suspended", "inactive"}
VALID_ATTENDANCE_STATUS = {"present", "absent", "late"}
VALID_EXAM_STATUS = {"draft", "open", "closed"}
VALID_OPTIONS = {"A", "B", "C", "D"}


def validate_email(email: Optional[str]) -> bool:
    """Validate standard email format."""
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_password(password: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Validate password strength: minimum 8 characters, at least one letter and one number.
    """
    if not password or not isinstance(password, str):
        return False, "Password is required."
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must contain at least one letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number."
    return True, None


def validate_role(role: Optional[str]) -> bool:
    """Validate role against accepted roles."""
    if not role or not isinstance(role, str):
        return False
    return role.lower().strip() in VALID_ROLES


def validate_user_payload(data: Dict[str, Any], is_update: bool = False) -> Tuple[bool, Optional[str]]:
    """Validate user registration or update payload."""
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object."

    if not is_update:
        if not data.get("username") or not isinstance(data["username"], str) or not data["username"].strip():
            return False, "Username is required and cannot be empty."
        if len(data["username"].strip()) < 3:
            return False, "Username must be at least 3 characters long."

        if not validate_email(data.get("email")):
            return False, "A valid email address is required."

        is_valid_pw, pw_err = validate_password(data.get("password"))
        if not is_valid_pw:
            return False, pw_err

        if not validate_role(data.get("role")):
            return False, f"Role must be one of: {', '.join(sorted(VALID_ROLES))}."

        if not data.get("full_name") or not isinstance(data["full_name"], str) or not data["full_name"].strip():
            return False, "Full name is required."
    else:
        if "email" in data and not validate_email(data["email"]):
            return False, "Invalid email address format."
        if "role" in data and not validate_role(data["role"]):
            return False, f"Role must be one of: {', '.join(sorted(VALID_ROLES))}."
        if "status" in data and data["status"] not in VALID_USER_STATUS:
            return False, f"Status must be one of: {', '.join(sorted(VALID_USER_STATUS))}."

    return True, None


def validate_student_payload(data: Dict[str, Any], is_update: bool = False) -> Tuple[bool, Optional[str]]:
    """Validate student creation or update payload."""
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object."

    required_fields = ["student_id", "full_name", "email", "department", "year", "semester"]
    if not is_update:
        for field in required_fields:
            if not data.get(field):
                return False, f"Field '{field}' is required."

        if not validate_email(data.get("email")):
            return False, "Invalid email format."
    else:
        if "email" in data and not validate_email(data["email"]):
            return False, "Invalid email format."
        if "status" in data and data["status"] not in VALID_STUDENT_STATUS:
            return False, f"Status must be one of: {', '.join(sorted(VALID_STUDENT_STATUS))}."

    return True, None


def validate_attendance_payload(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate single attendance entry payload."""
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object."

    required = ["student_id", "date", "course_id", "status"]
    for field in required:
        if not data.get(field):
            return False, f"Field '{field}' is required."

    if data.get("status") not in VALID_ATTENDANCE_STATUS:
        return False, f"Status must be one of: {', '.join(sorted(VALID_ATTENDANCE_STATUS))}."

    # Validate date format YYYY-MM-DD
    date_str = data.get("date", "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return False, "Date must be in YYYY-MM-DD format."

    return True, None


def validate_result_payload(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate result entry payload."""
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object."

    required = ["student_id", "semester", "subject_code", "subject_name", "marks_obtained", "max_marks"]
    for field in required:
        if field not in data or data[field] is None or data[field] == "":
            return False, f"Field '{field}' is required."

    try:
        marks = float(data["marks_obtained"])
        max_marks = float(data["max_marks"])
        if marks < 0 or max_marks <= 0 or marks > max_marks:
            return False, "Marks obtained must be between 0 and max marks."
    except (ValueError, TypeError):
        return False, "Marks must be numeric values."

    return True, None


def validate_exam_payload(data: Dict[str, Any], is_update: bool = False) -> Tuple[bool, Optional[str]]:
    """Validate exam creation or update payload."""
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object."

    if not is_update:
        required = ["title", "course_id", "course_name", "duration_minutes", "start_time", "end_time"]
        for field in required:
            if not data.get(field):
                return False, f"Field '{field}' is required."

        try:
            duration = int(data["duration_minutes"])
            if duration <= 0:
                return False, "duration_minutes must be a positive integer."
        except (ValueError, TypeError):
            return False, "duration_minutes must be an integer."

    if "status" in data and data["status"] not in VALID_EXAM_STATUS:
        return False, f"Status must be one of: {', '.join(sorted(VALID_EXAM_STATUS))}."

    return True, None


def validate_question_payload(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate question creation or update payload."""
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object."

    required = ["question_text", "option_a", "option_b", "option_c", "option_d", "correct_answer"]
    for field in required:
        if not data.get(field):
            return False, f"Field '{field}' is required."

    ans = str(data.get("correct_answer", "")).upper().strip()
    if ans not in VALID_OPTIONS:
        return False, f"correct_answer must be one of: {', '.join(sorted(VALID_OPTIONS))}."

    return True, None
