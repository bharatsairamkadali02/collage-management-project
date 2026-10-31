"""
Exam Rules & Security Test Suite.
Verifies time window enforcement, single-attempt protection, answer sanitization, and server-side grading.
"""
from datetime import datetime, timedelta, timezone
import pytest


def test_exam_security_answers_never_sent_to_student(faculty_client, student_client):
    """Ensure correct answers and explanations are stripped when a student starts an exam."""
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(hours=1)).isoformat()
    end_time = (now + timedelta(hours=2)).isoformat()

    # 1. Faculty creates exam
    exam_payload = {
        "title": "Algorithms Quiz",
        "course_id": "CS201",
        "course_name": "Algorithms",
        "duration_minutes": 30,
        "start_time": start_time,
        "end_time": end_time,
        "total_marks": 10,
        "status": "open",
    }
    create_res = faculty_client.post("/api/exams", json=exam_payload)
    assert create_res.status_code == 201
    exam_id = create_res.get_json()["exam"]["exam_id"]

    # 2. Faculty adds questions with confidential answer keys
    q1 = {
        "exam_id": exam_id,
        "question_text": "What is 2 + 2?",
        "option_a": "3",
        "option_b": "4",
        "option_c": "5",
        "option_d": "6",
        "correct_answer": "B",
        "marks": 5,
        "explanation": "Fundamental arithmetic.",
    }
    faculty_client.post("/api/questions", json=q1)

    # 3. Student starts exam
    start_res = student_client.post(f"/api/exams/{exam_id}/start")
    assert start_res.status_code == 200
    data = start_res.get_json()

    # Verify questions are present but sanitized
    assert "questions" in data
    assert len(data["questions"]) == 1
    received_q = data["questions"][0]

    assert "correct_answer" not in received_q, "CRITICAL SECURITY BREACH: correct_answer leaked to client!"
    assert "explanation" not in received_q, "CRITICAL SECURITY BREACH: explanation leaked to client!"
    assert received_q["option_b"] == "4"


def test_exam_time_window_enforcement(faculty_client, student_client):
    """Students cannot start exams before start_time or after end_time."""
    now = datetime.now(timezone.utc)

    # 1. Future Exam (not started)
    future_exam = {
        "title": "Future Exam",
        "course_id": "CS999",
        "course_name": "Future Topics",
        "duration_minutes": 30,
        "start_time": (now + timedelta(days=2)).isoformat(),
        "end_time": (now + timedelta(days=3)).isoformat(),
        "status": "open",
    }
    res = faculty_client.post("/api/exams", json=future_exam)
    future_id = res.get_json()["exam"]["exam_id"]

    start_future = student_client.post(f"/api/exams/{future_id}/start")
    assert start_future.status_code == 400
    assert "not started yet" in start_future.get_json()["message"]

    # 2. Past Exam (expired)
    past_exam = {
        "title": "Past Exam",
        "course_id": "CS998",
        "course_name": "History of Computing",
        "duration_minutes": 30,
        "start_time": (now - timedelta(days=3)).isoformat(),
        "end_time": (now - timedelta(days=1)).isoformat(),
        "status": "open",
    }
    res2 = faculty_client.post("/api/exams", json=past_exam)
    past_id = res2.get_json()["exam"]["exam_id"]

    start_past = student_client.post(f"/api/exams/{past_id}/start")
    assert start_past.status_code == 400
    assert "concluded" in start_past.get_json()["message"]


def test_exam_one_attempt_enforcement(faculty_client, student_client):
    """Students are restricted to exactly one attempt per exam."""
    now = datetime.now(timezone.utc)
    exam_payload = {
        "title": "Single Attempt Exam",
        "course_id": "CS102",
        "course_name": "CS102",
        "duration_minutes": 45,
        "start_time": (now - timedelta(hours=1)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "total_marks": 10,
        "status": "open",
    }
    res = faculty_client.post("/api/exams", json=exam_payload)
    exam_id = res.get_json()["exam"]["exam_id"]

    # Add 1 question
    faculty_client.post("/api/questions", json={
        "exam_id": exam_id,
        "question_text": "Is Python interpreted?",
        "option_a": "Yes",
        "option_b": "No",
        "option_c": "Maybe",
        "option_d": "Never",
        "correct_answer": "A",
        "marks": 10,
    })

    # Start and submit
    student_client.post(f"/api/exams/{exam_id}/start")
    submit_res = student_client.post(f"/api/submissions/{exam_id}/submit", json={"answers": {}})
    assert submit_res.status_code == 200

    # Attempt to start again -> 403 Forbidden
    second_start = student_client.post(f"/api/exams/{exam_id}/start")
    assert second_start.status_code == 403

    # Attempt to submit again -> 403 Forbidden
    second_submit = student_client.post(f"/api/submissions/{exam_id}/submit", json={"answers": {}})
    assert second_submit.status_code in (403, 409)


def test_server_side_scoring_with_negative_marking(faculty_client, student_client):
    """Accurately computes score, applying negative penalties and ignoring unattempted questions."""
    now = datetime.now(timezone.utc)
    exam_payload = {
        "title": "Scoring Test Exam",
        "course_id": "MATH101",
        "course_name": "Calculus",
        "duration_minutes": 60,
        "start_time": (now - timedelta(hours=1)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "total_marks": 15,
        "negative_marking": True,
        "negative_per_wrong": 1.0,
        "status": "open",
    }
    res = faculty_client.post("/api/exams", json=exam_payload)
    exam_id = res.get_json()["exam"]["exam_id"]

    # Q1: 5 marks, correct = A
    q1_res = faculty_client.post("/api/questions", json={
        "exam_id": exam_id,
        "question_text": "Question 1",
        "option_a": "Correct",
        "option_b": "Wrong",
        "option_c": "Wrong",
        "option_d": "Wrong",
        "correct_answer": "A",
        "marks": 5,
    })
    q1_id = q1_res.get_json()["question"]["question_id"]

    # Q2: 5 marks, correct = B
    q2_res = faculty_client.post("/api/questions", json={
        "exam_id": exam_id,
        "question_text": "Question 2",
        "option_a": "Wrong",
        "option_b": "Correct",
        "option_c": "Wrong",
        "option_d": "Wrong",
        "correct_answer": "B",
        "marks": 5,
    })
    q2_id = q2_res.get_json()["question"]["question_id"]

    # Q3: 5 marks, correct = C
    q3_res = faculty_client.post("/api/questions", json={
        "exam_id": exam_id,
        "question_text": "Question 3",
        "option_a": "Wrong",
        "option_b": "Wrong",
        "option_c": "Correct",
        "option_d": "Wrong",
        "correct_answer": "C",
        "marks": 5,
    })
    q3_id = q3_res.get_json()["question"]["question_id"]

    # Student starts exam
    student_client.post(f"/api/exams/{exam_id}/start")

    # Student answers:
    # Q1: A (Correct -> +5)
    # Q2: C (Incorrect -> -1 penalty)
    # Q3: None (Unattempted -> 0)
    # Expected total score = 5 - 1 + 0 = 4.0
    answers = {
        q1_id: "A",
        q2_id: "C",
    }
    submit_res = student_client.post(f"/api/submissions/{exam_id}/submit", json={"answers": answers})
    assert submit_res.status_code == 200
    data = submit_res.get_json()

    assert data["score"] == 4.0
    assert data["total_possible"] == 15.0
