"""
RBAC Access Control Test Suite.
Verifies that routes strictly enforce permissions per role (Admin, Faculty, Student, Anonymous).
"""
import pytest
from tests.conftest import login_as


def test_unauthenticated_requests_return_401(client):
    """Unauthenticated access to protected routes returns 401."""
    routes = [
        "/api/auth/me",
        "/api/users",
        "/api/students",
        "/api/attendance",
        "/api/results",
        "/api/exams",
        "/api/dashboard",
    ]
    for route in routes:
        res = client.get(route)
        assert res.status_code == 401, f"Expected 401 on {route}, got {res.status_code}"


def test_user_management_rbac(admin_client, faculty_client, student_client):
    """Only Admin can list, create, update, or delete users."""
    # 1. Admin gets 200
    res = admin_client.get("/api/users")
    assert res.status_code == 200

    # 2. Faculty gets 403
    res = faculty_client.get("/api/users")
    assert res.status_code == 403

    # 3. Student gets 403
    res = student_client.get("/api/users")
    assert res.status_code == 403


def test_students_management_rbac(admin_client, faculty_client, student_client):
    """Admin and Faculty can list/create students; Student cannot list students."""
    # Admin and Faculty can list students
    assert admin_client.get("/api/students").status_code == 200
    assert faculty_client.get("/api/students").status_code == 200

    # Student cannot list all students
    assert student_client.get("/api/students").status_code == 403

    # Faculty can create student
    new_student = {
        "student_id": "STU999",
        "full_name": "Test Student",
        "email": "teststu999@test.edu",
        "department": "Physics",
        "year": "1",
        "semester": "1",
    }
    create_res = faculty_client.post("/api/students", json=new_student)
    assert create_res.status_code == 201

    # Student cannot create student
    assert student_client.post("/api/students", json=new_student).status_code == 403


def test_student_self_profile_access(student_client):
    """Student can view their own profile, but is forbidden from viewing other students' profiles."""
    # student_user has linked_id STU001
    own_res = student_client.get("/api/students/STU001")
    assert own_res.status_code == 200

    # Attempting to view STU002
    other_res = student_client.get("/api/students/STU002")
    assert other_res.status_code == 403


def test_attendance_rbac(admin_client, faculty_client, student_client):
    """Faculty can mark attendance; student cannot mark attendance."""
    att_payload = {
        "student_id": "STU001",
        "date": "2026-10-30",
        "course_id": "CS101",
        "status": "present",
    }

    # Faculty marks attendance -> 201
    res = faculty_client.post("/api/attendance", json=att_payload)
    assert res.status_code == 201

    # Student attempts to mark attendance -> 403
    res_student = student_client.post("/api/attendance", json=att_payload)
    assert res_student.status_code == 403

    # Student views own attendance -> 200
    assert student_client.get("/api/attendance/student/STU001").status_code == 200

    # Student views other's attendance -> 403
    assert student_client.get("/api/attendance/student/STU002").status_code == 403


def test_results_rbac(admin_client, faculty_client, student_client):
    """Faculty can add results; student cannot add results, but can view own."""
    result_payload = {
        "student_id": "STU001",
        "semester": "1",
        "subject_code": "CS101",
        "subject_name": "Programming 101",
        "marks_obtained": 85,
        "max_marks": 100,
    }

    # Faculty adds result -> 201
    res = faculty_client.post("/api/results", json=result_payload)
    assert res.status_code == 201

    # Student attempts to add result -> 403
    res_student = student_client.post("/api/results", json=result_payload)
    assert res_student.status_code == 403

    # Student views own results -> 200
    assert student_client.get("/api/results/student/STU001").status_code == 200

    # Student views other's results -> 403
    assert student_client.get("/api/results/student/STU002").status_code == 403


def test_questions_rbac(faculty_client, student_client):
    """Faculty can view question answer keys; students cannot access questions authoring endpoint."""
    res_fac = faculty_client.get("/api/questions/exam/exam_mock")
    assert res_fac.status_code == 200

    res_stu = student_client.get("/api/questions/exam/exam_mock")
    assert res_stu.status_code == 403
