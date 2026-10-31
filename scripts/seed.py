"""
Database seeding script for College Management System.
Provisions DynamoDB tables locally and populates sample users, students, courses, exams, and questions.
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.models.user import User
from app.services.dynamo import get_dynamo_service
from app.utils.helpers import iso_now, to_decimal
from scripts.create_tables import create_tables

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("seed")


def seed_data():
    """Seed sample data for development and testing environments."""
    logger.info("Initializing database tables...")
    create_tables()

    app = create_app("development")
    with app.app_context():
        dynamo = get_dynamo_service()

        # 1. Seed Users (Admin, Faculty, Student)
        logger.info("Seeding system users...")
        users_to_seed = [
            {
                "username": "admin",
                "email": "admin@college.edu",
                "password": "Admin@12345",
                "role": "admin",
                "full_name": "System Administrator",
                "linked_id": "ADM001",
            },
            {
                "username": "faculty1",
                "email": "faculty1@college.edu",
                "password": "Faculty@12345",
                "role": "faculty",
                "full_name": "Dr. Alan Turing",
                "linked_id": "FAC001",
            },
            {
                "username": "student1",
                "email": "student1@college.edu",
                "password": "Student@12345",
                "role": "student",
                "full_name": "Grace Hopper",
                "linked_id": "STU001",
            },
        ]

        for u in users_to_seed:
            existing = User.get_by_username(u["username"])
            if not existing:
                User.create(
                    username=u["username"],
                    email=u["email"],
                    password=u["password"],
                    role=u["role"],
                    full_name=u["full_name"],
                    linked_id=u.get("linked_id"),
                )
                logger.info("Created user: %s (%s)", u["username"], u["role"])
            else:
                logger.info("User '%s' already exists.", u["username"])

        # 2. Seed Student Profile
        logger.info("Seeding student profiles...")
        students_tbl = app.config.get("DYNAMODB_TABLE_STUDENTS", "cms_students")
        student_item = {
            "student_id": "STU001",
            "full_name": "Grace Hopper",
            "email": "student1@college.edu",
            "phone": "+1-555-0199",
            "department": "Computer Science",
            "year": "3",
            "semester": "5",
            "enrollment_date": "2024-08-15",
            "status": "active",
        }
        dynamo.put_item(students_tbl, student_item)
        logger.info("Seeded student profile for STU001")

        # 3. Seed Attendance Records
        logger.info("Seeding attendance records...")
        attendance_tbl = app.config.get("DYNAMODB_TABLE_ATTENDANCE", "cms_attendance")
        attendance_records = [
            {
                "student_id": "STU001",
                "date_course": "2026-10-20#CS301",
                "course_id": "CS301",
                "date": "2026-10-20",
                "status": "present",
                "course_name": "Data Structures & Algorithms",
                "semester": "5",
                "marked_by": "faculty1",
                "marked_at": "2026-10-20T09:30:00Z",
            },
            {
                "student_id": "STU001",
                "date_course": "2026-10-21#CS302",
                "course_id": "CS302",
                "date": "2026-10-21",
                "status": "present",
                "course_name": "Database Systems",
                "semester": "5",
                "marked_by": "faculty1",
                "marked_at": "2026-10-21T11:00:00Z",
            },
            {
                "student_id": "STU001",
                "date_course": "2026-10-22#CS303",
                "course_id": "CS303",
                "date": "2026-10-22",
                "status": "late",
                "course_name": "Operating Systems",
                "semester": "5",
                "marked_by": "faculty1",
                "marked_at": "2026-10-22T14:15:00Z",
            },
        ]
        for att in attendance_records:
            dynamo.put_item(attendance_tbl, att)
        logger.info("Seeded %d attendance records", len(attendance_records))

        # 4. Seed Academic Results
        logger.info("Seeding academic results...")
        results_tbl = app.config.get("DYNAMODB_TABLE_RESULTS", "cms_results")
        results = [
            {
                "student_id": "STU001",
                "sem_subject": "4#CS201",
                "semester": "4",
                "subject_code": "CS201",
                "subject_name": "Object Oriented Programming",
                "marks_obtained": 88.0,
                "max_marks": 100.0,
                "grade": "A",
                "sgpa": 9.0,
                "pass_fail": "PASS",
                "added_by": "faculty1",
                "added_at": "2026-06-15T10:00:00Z",
            },
            {
                "student_id": "STU001",
                "sem_subject": "4#CS202",
                "semester": "4",
                "subject_code": "CS202",
                "subject_name": "Discrete Mathematics",
                "marks_obtained": 94.0,
                "max_marks": 100.0,
                "grade": "A+",
                "sgpa": 10.0,
                "pass_fail": "PASS",
                "added_by": "faculty1",
                "added_at": "2026-06-15T10:00:00Z",
            },
        ]
        for res in results:
            dynamo.put_item(results_tbl, res)
        logger.info("Seeded %d academic results", len(results))

        # 5. Seed Open Exam
        logger.info("Seeding sample exam and questions...")
        exams_tbl = app.config.get("DYNAMODB_TABLE_EXAMS", "cms_exams")
        now = datetime.now(timezone.utc)
        start_time = (now - timedelta(days=1)).isoformat()
        end_time = (now + timedelta(days=10)).isoformat()

        exam_id = "exam_sample_cs101"
        sample_exam = {
            "exam_id": exam_id,
            "title": "CS101: Fundamentals of Computing Midterm",
            "course_id": "CS101",
            "course_name": "Computer Science Fundamentals",
            "duration_minutes": 60,
            "start_time": start_time,
            "end_time": end_time,
            "total_marks": 20.0,
            "negative_marking": True,
            "negative_per_wrong": 1.0,
            "status": "open",
            "created_by": "faculty1",
            "created_at": iso_now(),
            "show_answers_after": True,
        }
        dynamo.put_item(exams_tbl, sample_exam)

        # 6. Seed Questions
        questions_tbl = app.config.get("DYNAMODB_TABLE_QUESTIONS", "cms_questions")
        questions = [
            {
                "exam_id": exam_id,
                "question_id": "q1",
                "question_text": "What is the time complexity of searching in a balanced Binary Search Tree (BST)?",
                "option_a": "O(1)",
                "option_b": "O(log n)",
                "option_c": "O(n)",
                "option_d": "O(n log n)",
                "correct_answer": "B",
                "marks": 5.0,
                "explanation": "In a balanced BST, tree height is log(n), making search O(log n).",
                "order": 1,
            },
            {
                "exam_id": exam_id,
                "question_id": "q2",
                "question_text": "Which data structure follows the First In, First Out (FIFO) principle?",
                "option_a": "Stack",
                "option_b": "Queue",
                "option_c": "Heap",
                "option_d": "Graph",
                "correct_answer": "B",
                "marks": 5.0,
                "explanation": "Queues process items in FIFO order, whereas stacks are LIFO.",
                "order": 2,
            },
            {
                "exam_id": exam_id,
                "question_id": "q3",
                "question_text": "In relational algebra, which operation filters rows based on a condition?",
                "option_a": "Projection",
                "option_b": "Selection",
                "option_c": "Cartesian Product",
                "option_d": "Join",
                "correct_answer": "B",
                "marks": 5.0,
                "explanation": "Selection (sigma) retrieves rows that satisfy a predicate condition.",
                "order": 3,
            },
            {
                "exam_id": exam_id,
                "question_id": "q4",
                "question_text": "Which HTTP status code signifies that a resource was created successfully?",
                "option_a": "200 OK",
                "option_b": "201 Created",
                "option_c": "204 No Content",
                "option_d": "301 Moved Permanently",
                "correct_answer": "B",
                "marks": 5.0,
                "explanation": "HTTP 201 Created is the standard response for successful resource generation.",
                "order": 4,
            },
        ]
        for q in questions:
            dynamo.put_item(questions_tbl, q)
        logger.info("Seeded %d questions for exam %s", len(questions), exam_id)

        logger.info("Seeding completed successfully!")


if __name__ == "__main__":
    seed_data()
