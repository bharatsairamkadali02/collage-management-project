# Test Credentials & Role-by-Role Verification Checklist

This document provides default test account credentials and a verification checklist covering all three user roles (**Admin**, **Faculty**, and **Student**) in the College Management System (CMS).

---

## 1. Test Credentials

The database seed script (`scripts/seed.py`) populates the system with three standard test accounts:

| Role | Username / Email | Password | Primary Permissions |
|---|---|---|---|
| **Admin** | `admin@college.edu` | `Admin@123456` | Full system administration, user management, audit logging, S3 exports |
| **Faculty** | `faculty@college.edu` | `Faculty@123456` | Course attendance recording, grade entry, exam creation & grading |
| **Student** | `student@college.edu` | `Student@123456` | Attendance inspection, grade viewing, exam taking & submission |

> [!NOTE]
> Passwords in DynamoDB are salted and hashed using `bcrypt`. All sessions are authenticated via JWT stored in HTTP-only secure cookies or Authorization bearer tokens.

---

## 2. Role-by-Role Test Checklist

### 2.1 Admin Role Verification
Log in as `admin@college.edu` / `Admin@123456`:

- [ ] **Dashboard Metrics**: Confirm dashboard displays live aggregate statistics: total active students, faculty count, registered courses, and today's attendance rate.
- [ ] **Add Student**: Navigate to `Student Management` > `Add Student`. Fill in name, department, year, roll number, and email. Verify the new student record appears in the student list table.
- [ ] **Edit Student**: Select the created student, change their contact number or department, save, and confirm that DynamoDB updates immediately and changes appear on screen.
- [ ] **Delete Student**: Delete the test student. Verify confirmation modal appears and the student record is permanently removed from `cms_students`.
- [ ] **Create Faculty User**: Navigate to `User Management` > `Add User`. Assign role `faculty`, input name and email. Confirm user record is created in `cms_users`.
- [ ] **Account Disable Test**: In `User Management`, toggle status to **Disabled** for a test account. Open an incognito browser tab and attempt login with that account; verify login fails with `"Account has been disabled"`.
- [ ] **Audit Trail**: Navigate to `Audit Logs`. Confirm all recent actions (student creation, updates, deletes, login attempts) are chronologically logged with exact timestamp, IP address, and actor ID.
- [ ] **Export to S3**: Click `Export Students CSV`. Confirm the background worker uploads the file to S3 prefix `exports/` and the browser successfully triggers download via a generated presigned URL.
- [ ] **Real-Time Active Users**: Open a second browser window with a student login. Verify the "Online Users" counter badge on the Admin dashboard increments in real-time via WebSocket without page refresh.

---

### 2.2 Faculty Role Verification
Log in as `faculty@college.edu` / `Faculty@123456`:

- [ ] **Faculty Dashboard**: Verify dashboard lists assigned courses, scheduled exams, and quick action shortcuts.
- [ ] **Mark Attendance**: Navigate to `Attendance` > select Course (e.g., `CS301`) and current date. Mark students as Present/Absent. Save and verify a real-time toast alert is emitted over WebSocket to active sessions.
- [ ] **Edit Attendance**: Re-open the saved attendance sheet for `CS301`. Change a student status from Present to Absent. Save and confirm the record is correctly updated in `cms_attendance`.
- [ ] **Enter Semester Grades**: Navigate to `Results` > select Course and Semester. Enter internal marks, exam score, and letter grade for a student. Confirm grade reflects in `cms_results`.
- [ ] **Create MCQ Exam**: Navigate to `Exams` > `Create Exam`. Fill in Exam Title, Course, Duration (e.g., 30 mins), Total Marks, and Passing Score. Save and confirm status is `draft`.
- [ ] **Add Questions (Manual)**: In the exam builder, add 3 multiple choice questions with 4 options each and designate the correct answer key.
- [ ] **Add Questions (Bulk CSV)**: Download the CSV template, populate with 5 questions, and upload. Verify all 5 questions are parsed and inserted into `cms_questions`.
- [ ] **Publish Exam**: Click `Open Exam`. Verify exam status transitions to `open` in `cms_exams`.
- [ ] **View Submissions**: After a student submits an exam, open `Submissions`. Confirm the student's submission, score, time taken, and question breakdown are visible.
- [ ] **Access Control - Admin Pages**: Manually type URL `/admin/users` into the browser bar. Confirm access is denied with `HTTP 403 Forbidden`.
- [ ] **Access Control - Audit Logs**: Manually navigate to `/admin/audit-logs`. Confirm access is blocked with `HTTP 403 Forbidden`.

---

### 2.3 Student Role Verification
Log in as `student@college.edu` / `Student@123456`:

- [ ] **Student Dashboard**: Verify dashboard renders attendance progress ring, upcoming exams banner, and latest GPA card.
- [ ] **View Attendance Breakdown**: Navigate to `My Attendance`. Verify course-by-course breakdown displays total classes held, attended, and current percentage.
- [ ] **Low-Attendance Warning**: If attendance in any subject is below `75%`, verify that a high-visibility warning alert banner is displayed.
- [ ] **View Semester Results**: Navigate to `My Results`. Switch between semester tabs (Sem 1, Sem 2, etc.) and verify course codes, credit hours, and grades.
- [ ] **Download Grade Sheet**: Click `Download Grade Sheet PDF`. Confirm that S3 generates a time-limited presigned URL and the PDF downloads with valid student credentials.
- [ ] **Available Exams**: Navigate to `My Exams`. Verify the exam published by Faculty appears under `Open Exams` with countdown timer.
- [ ] **Start Exam**: Click `Start Exam`. Verify exam interface loads with fullscreen timer countdown, question palette (1 to N), and question description.
- [ ] **Auto-Save Verification**: Select an answer for Question 1. Open Browser DevTools > Network Tab. Confirm an asynchronous POST/WebSocket ping is sent to save the current selection immediately.
- [ ] **Submit Exam**: Complete remaining questions and click `Submit Exam`. Confirm confirmation dialog appears, final score and percentage are calculated and displayed immediately.
- [ ] **Single Attempt Enforcement**: Attempt to click `Start Exam` again on the same exam. Confirm user is blocked with message `"You have already submitted this exam"`.
- [ ] **Access Control - Mark Attendance**: Attempt to access `/attendance/mark` directly. Verify `HTTP 403 Forbidden`.
- [ ] **Access Control - Edit Results**: Attempt to send a PUT/POST request to `/api/results`. Verify API returns `HTTP 403 Forbidden`.

---

## 3. Automated API Smoke Test Suite

To rapidly validate API health and role separation from the terminal, execute:

```bash
# Set base target
BASE_URL="http://localhost"

# 1. Health check
curl -s "${BASE_URL}/health" | grep -q '"status":"healthy"' && echo "PASS: Health Endpoint" || echo "FAIL: Health Endpoint"

# 2. Student unauthorized access check
STUDENT_TOKEN=$(curl -s -X POST "${BASE_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"student@college.edu","password":"Student@123456"}' | jq -r '.token')

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${STUDENT_TOKEN}" "${BASE_URL}/api/admin/users")
if [ "${HTTP_CODE}" -eq 403 ]; then
  echo "PASS: Student blocked from Admin API (HTTP 403)"
else
  echo "FAIL: Student accessed Admin API (HTTP ${HTTP_CODE})"
fi

# 3. Faculty unauthorized access check
FACULTY_TOKEN=$(curl -s -X POST "${BASE_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"faculty@college.edu","password":"Faculty@123456"}' | jq -r '.token')

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${FACULTY_TOKEN}" "${BASE_URL}/api/admin/audit-logs")
if [ "${HTTP_CODE}" -eq 403 ]; then
  echo "PASS: Faculty blocked from Audit Logs (HTTP 403)"
else
  echo "FAIL: Faculty accessed Audit Logs (HTTP ${HTTP_CODE})"
fi
```
