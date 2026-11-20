"""Multi-Teacher Isolation, Multi-Google Account, Grading, Confirmation & Export API Tests."""

from __future__ import annotations

import io
from pathlib import Path
import openpyxl

from backend.app.core.security import encrypt_secret
from backend.app.models.models import GoogleClassroom, GoogleConnection


def _make_excel_bytes(sum_formula: str = "=SUM(B2:B4)") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Scores"
    ws["A1"] = "ชื่อ"
    ws["B1"] = "คะแนน"
    ws["A2"], ws["B2"] = "สมชาย", 80
    ws["A3"], ws["B3"] = "สมหญิง", 90
    ws["A4"], ws["B4"] = "วิชัย", 70
    ws["B5"] = sum_formula
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _register_and_auth(client, email: str, name: str) -> tuple[dict[str, str], str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPassword123!", "full_name": name},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["teacher_id"]


def test_multi_teacher_strict_data_isolation(client):
    http, SessionLocal = client
    headers_a, teacher_a_id = _register_and_auth(http, "teacher_a@school.ac.th", "ครูสมชาย")
    headers_b, teacher_b_id = _register_and_auth(http, "teacher_b@school.ac.th", "ครูสมหญิง")
    assert teacher_a_id != teacher_b_id

    # Teacher A creates a class, student, assignment, and rubric
    cls_res = http.post(
        "/api/v1/classes",
        headers=headers_a,
        json={"name": "ม.4/1 คอมพิวเตอร์", "subject_code": "ว31101", "semester": "1", "academic_year": "2569"},
    )
    assert cls_res.status_code == 201
    class_a_id = cls_res.json()["id"]

    st_res = http.post(
        "/api/v1/students",
        headers=headers_a,
        json={
            "student_code": "69001",
            "first_name": "เด็กชายกอ",
            "last_name": "ไก่",
            "room": "ม.4/1",
            "seat_number": 1,
            "class_id": class_a_id,
        },
    )
    assert st_res.status_code == 201

    assign_res = http.post(
        "/api/v1/assignments",
        headers=headers_a,
        json={"title": "ใบงานที่ 1 สูตร SUM", "class_id": class_a_id, "max_score": 10.0, "pass_score": 5.0},
    )
    assert assign_res.status_code == 201
    assign_a_id = assign_res.json()["id"]

    rubric_res = http.post(
        "/api/v1/rubrics",
        headers=headers_a,
        json={
            "assignment_id": assign_a_id,
            "name": "เกณฑ์ใบงานที่ 1",
            "total_points": 10.0,
            "items": [
                {
                    "title": "สูตร SUM",
                    "category": "formula",
                    "sheet_name": "Scores",
                    "target_cell": "B5",
                    "rule_config": {"expected_formula": "=SUM(B2:B4)", "required_functions": ["SUM"]},
                    "max_points": 10.0,
                }
            ],
        },
    )
    assert rubric_res.status_code == 201
    rubric_a_id = rubric_res.json()["id"]

    # Teacher B must see ZERO classes, students, assignments, or rubrics from Teacher A
    assert http.get("/api/v1/classes", headers=headers_b).json() == []
    assert http.get("/api/v1/students", headers=headers_b).json() == []
    assert http.get("/api/v1/assignments", headers=headers_b).json() == []
    assert http.get("/api/v1/rubrics", headers=headers_b).json() == []

    # Teacher B cannot modify or delete Teacher A's resources
    assert http.delete(f"/api/v1/classes/{class_a_id}", headers=headers_b).status_code == 404
    assert http.get(f"/api/v1/rubrics/{rubric_a_id}", headers=headers_b).status_code == 404
    assert http.get(f"/api/v1/reports/assignments/{assign_a_id}", headers=headers_b).status_code == 404

    # Multiple Google Accounts for Teacher A (encrypted tokens), isolated from Teacher B
    db = SessionLocal()
    try:
        conn1 = GoogleConnection(
            owner_user_id=teacher_a_id,
            google_user_id="g-uid-1",
            google_email="teacher1@gmail.com",
            display_name="Teacher One",
            encrypted_access_token=encrypt_secret("secret-access-1"),
            encrypted_refresh_token=encrypt_secret("secret-refresh-1"),
            status="connected",
            is_default=True,
        )
        conn2 = GoogleConnection(
            owner_user_id=teacher_a_id,
            google_user_id="g-uid-2",
            google_email="school-account@school.ac.th",
            display_name="School Account",
            encrypted_access_token=encrypt_secret("secret-access-2"),
            encrypted_refresh_token=encrypt_secret("secret-refresh-2"),
            status="connected",
            is_default=False,
        )
        db.add_all([conn1, conn2])
        db.flush()
        # Verify token is encrypted, never plaintext
        assert conn1.encrypted_refresh_token != "secret-refresh-1"

        db.add(
            GoogleClassroom(
                owner_user_id=teacher_a_id,
                google_connection_id=conn1.id,
                google_course_id="course-101",
                name="Excel 101 (Account 1)",
            )
        )
        db.add(
            GoogleClassroom(
                owner_user_id=teacher_a_id,
                google_connection_id=conn2.id,
                google_course_id="course-202",
                name="Excel 202 (School Account)",
            )
        )
        db.commit()
        conn1_id = conn1.id
    finally:
        db.close()

    # Teacher A sees 2 Google accounts & can filter classrooms by account
    accs_a = http.get("/api/v1/google-accounts", headers=headers_a).json()["accounts"]
    assert len(accs_a) == 2
    assert "encrypted_access_token" not in accs_a[0]
    courses_filtered = http.get(
        f"/api/v1/classroom/courses?google_connection_id={conn1_id}", headers=headers_a
    ).json()
    assert len(courses_filtered) == 1
    assert courses_filtered[0]["name"] == "Excel 101 (Account 1)"

    # Teacher B sees 0 Google accounts & 0 classrooms
    assert http.get("/api/v1/google-accounts", headers=headers_b).json()["accounts"] == []
    assert http.get("/api/v1/classroom/courses", headers=headers_b).json() == []


def test_full_upload_grade_adjust_confirm_and_export_flow(client):
    http, _ = client
    headers, _ = _register_and_auth(http, "grader@school.ac.th", "ครูผู้ตรวจ")

    assign_id = http.post(
        "/api/v1/assignments",
        headers=headers,
        json={"title": "งานตรวจอัตโนมัติ", "max_score": 10.0, "pass_score": 5.0},
    ).json()["id"]

    rubric_id = http.post(
        "/api/v1/rubrics",
        headers=headers,
        json={
            "assignment_id": assign_id,
            "name": "เกณฑ์สูตร SUM",
            "total_points": 10.0,
            "items": [
                {
                    "title": "สูตร SUM",
                    "category": "formula",
                    "sheet_name": "Scores",
                    "target_cell": "B5",
                    "rule_config": {"expected_formula": "=SUM(B2:B4)"},
                    "max_points": 10.0,
                }
            ],
        },
    ).json()["id"]

    # Upload 2 student files (one correct, one duplicate of correct)
    good_xlsx = _make_excel_bytes("=SUM(B2:B4)")
    up_res = http.post(
        "/api/v1/submissions/upload",
        headers=headers,
        data={"assignment_id": assign_id},
        files=[
            ("files", ("69001_good.xlsx", good_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ("files", ("69002_dup.xlsx", good_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
        ],
    )
    assert up_res.status_code == 200
    uploaded = up_res.json()["files"]
    assert uploaded[0]["is_duplicate"] is False
    assert uploaded[1]["is_duplicate"] is True

    # Run automatic grading
    run_res = http.post(
        "/api/v1/grading/run",
        headers=headers,
        json={"assignment_id": assign_id, "rubric_id": rubric_id},
    )
    assert run_res.status_code == 200
    result_id = run_res.json()["result_ids"][0]

    detail = http.get(f"/api/v1/grading/results/{result_id}", headers=headers).json()
    assert detail["final_score"] == 10.0

    # Teacher adjusts score & confirms
    adj = http.put(
        f"/api/v1/grading/results/{result_id}/adjust",
        headers=headers,
        json={"new_score": 8.5, "reason": "หักคะแนนส่งช้า"},
    )
    assert adj.status_code == 200
    assert adj.json()["final_score"] == 8.5

    conf = http.post(f"/api/v1/grading/results/{result_id}/confirm", headers=headers)
    assert conf.status_code == 200

    # Re-running grading MUST NOT overwrite confirmed score!
    http.post("/api/v1/grading/run", headers=headers, json={"assignment_id": assign_id, "rubric_id": rubric_id})
    after_regrade = http.get(f"/api/v1/grading/results/{result_id}", headers=headers).json()
    assert after_regrade["final_score"] == 8.5
    assert after_regrade["is_confirmed"] is True

    # Verify Excel, CSV, and PDF exports return real binary payloads
    xlsx_exp = http.get(f"/api/v1/reports/assignments/{assign_id}/export/excel", headers=headers)
    assert xlsx_exp.status_code == 200
    assert xlsx_exp.content.startswith(b"PK\x03\x04")

    csv_exp = http.get(f"/api/v1/reports/assignments/{assign_id}/export/csv", headers=headers)
    assert csv_exp.status_code == 200
    assert "คะแนนที่ได้" in csv_exp.content.decode("utf-8-sig")

    pdf_exp = http.get(f"/api/v1/reports/results/{result_id}/export/pdf", headers=headers)
    assert pdf_exp.status_code == 200
    assert pdf_exp.content.startswith(b"%PDF")
