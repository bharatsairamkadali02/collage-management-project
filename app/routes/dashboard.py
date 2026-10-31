"""
Dashboard API endpoints providing role-tailored operational and academic intelligence.
"""
from datetime import datetime, timezone
from flask import Blueprint, current_app, jsonify
from flask_login import current_user, login_required

from app.decorators import faculty_required
from app.services.audit import get_audit_service
from app.services.dynamo import get_dynamo_service
from app.sockets.events import emit_dashboard_stats, get_online_users_stats
from app.utils.helpers import format_date

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.route("", methods=["GET"])
@login_required
def get_dashboard_data():
    """
    Return role-tailored dashboard metrics:
    - Admin: system overview, user counts, exam stats, recent audit logs
    - Faculty: courses, assigned exams, student totals, recent attendance
    - Student: personal attendance %, open exams, GPA summary
    """
    dynamo = get_dynamo_service()
    users_tbl = current_app.config.get("DYNAMODB_TABLE_USERS", "cms_users")
    students_tbl = current_app.config.get("DYNAMODB_TABLE_STUDENTS", "cms_students")
    attendance_tbl = current_app.config.get("DYNAMODB_TABLE_ATTENDANCE", "cms_attendance")
    results_tbl = current_app.config.get("DYNAMODB_TABLE_RESULTS", "cms_results")
    exams_tbl = current_app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")
    subs_tbl = current_app.config.get("DYNAMODB_TABLE_SUBMISSIONS", "cms_submissions")

    role = current_user.role

    try:
        if role == "admin":
            # Admin Dashboard
            users = dynamo.scan(table_name=users_tbl)
            students = dynamo.scan(table_name=students_tbl)
            exams = dynamo.scan(table_name=exams_tbl)

            user_counts = {"admin": 0, "faculty": 0, "student": 0, "active": 0, "disabled": 0}
            for u in users:
                r = u.get("role", "student")
                if r in user_counts:
                    user_counts[r] += 1
                if u.get("status") == "active":
                    user_counts["active"] += 1
                else:
                    user_counts["disabled"] += 1

            exam_counts = {"draft": 0, "open": 0, "closed": 0, "total": len(exams)}
            for e in exams:
                st = e.get("status", "draft")
                if st in exam_counts:
                    exam_counts[st] += 1

            today_date = format_date(datetime.now(timezone.utc))
            audit_service = get_audit_service()
            recent_logs = audit_service.get_logs_by_date(today_date, limit=10)

            return jsonify({
                "role": "admin",
                "stats": {
                    "total_users": len(users),
                    "total_students": len(students),
                    "user_breakdown": user_counts,
                    "exam_breakdown": exam_counts,
                    "online_users": get_online_users_stats(),
                },
                "recent_audit_logs": recent_logs,
            }), 200

        elif role == "faculty":
            # Faculty Dashboard
            students = dynamo.scan(table_name=students_tbl)
            exams = dynamo.scan(table_name=exams_tbl)

            faculty_exams = [e for e in exams if e.get("created_by") == current_user.username]
            open_exams = [e for e in faculty_exams if e.get("status") == "open"]

            return jsonify({
                "role": "faculty",
                "stats": {
                    "total_students_enrolled": len(students),
                    "my_total_exams": len(faculty_exams),
                    "my_open_exams": len(open_exams),
                    "online_users": get_online_users_stats(),
                },
                "exams": faculty_exams[:5],
            }), 200

        else:
            # Student Dashboard
            student_id = current_user.linked_id or current_user.username
            from boto3.dynamodb.conditions import Key

            attendance = dynamo.query(
                table_name=attendance_tbl,
                key_condition_expression=Key("student_id").eq(student_id),
            )
            results = dynamo.query(
                table_name=results_tbl,
                key_condition_expression=Key("student_id").eq(student_id),
            )

            # Open exams
            exams = dynamo.scan(table_name=exams_tbl)
            open_exams = [e for e in exams if e.get("status") == "open"]

            total_att = len(attendance)
            present_att = sum(1 for a in attendance if a.get("status") == "present")
            att_percentage = (
                round((present_att / total_att) * 100, 2) if total_att > 0 else 100.0
            )

            total_results = len(results)
            gpa = (
                round(sum(float(r.get("sgpa", 0)) for r in results) / total_results, 2)
                if total_results > 0
                else 0.0
            )

            return jsonify({
                "role": "student",
                "student_id": student_id,
                "summary": {
                    "attendance_percentage": att_percentage,
                    "cumulative_gpa": gpa,
                    "total_subjects_completed": total_results,
                    "open_exams_available": len(open_exams),
                },
                "upcoming_exams": [
                    {
                        "exam_id": e.get("exam_id"),
                        "title": e.get("title"),
                        "course_name": e.get("course_name"),
                        "duration_minutes": e.get("duration_minutes"),
                        "start_time": e.get("start_time"),
                        "end_time": e.get("end_time"),
                    }
                    for e in open_exams[:5]
                ],
            }), 200

    except Exception as e:
        return jsonify({"error": "InternalServerError", "message": str(e)}), 500


@dashboard_bp.route("/broadcast", methods=["POST"])
@faculty_required
def broadcast_stats():
    """Trigger real-time Socket.IO dashboard update event."""
    stats = get_online_users_stats()
    emit_dashboard_stats(stats)
    return jsonify({"message": "Dashboard stats broadcasted successfully.", "stats": stats}), 200
