# Excel Auto Grader — Multi-Teacher SaaS Platform

ระบบ Web Application สำหรับครูผู้สอน ใช้จัดการชั้นเรียน ตรวจสอบไฟล์ Microsoft Excel ของนักเรียน ให้คะแนนอัตโนมัติตามเกณฑ์ละเอียด 7 หมวด และจัดทำรายงานผลการเรียน รองรับทั้งการอัปโหลดไฟล์หลายไฟล์พร้อมกัน และการเชื่อมต่อ **Google Classroom หลายบัญชี** ต่อครู 1 คน

---

## ความสามารถหลักของระบบ

1. **Multi-Teacher SaaS & Strict Isolation**
   - สมัครสมาชิก เข้าสู่ระบบ ออกจากระบบ รีเซ็ตรหัสผ่าน แก้ไขโปรไฟล์ เปลี่ยนรูปโปรไฟล์ และเปลี่ยนรหัสผ่าน
   - แยกข้อมูลครูทุกตารางด้วย `owner_user_id` และ PostgreSQL **Row Level Security (RLS)**
   - แยกโฟลเดอร์ไฟล์ใน Private Storage เป็น `/users/{user_id}/references/`, `/submissions/`, `/reports/`, `/exports/`
   - Backend ตรวจสอบ Session JWT ทุก Endpoint โดยไม่เชื่อถือ Teacher ID จาก Frontend

2. **Multiple Google Accounts & Google Classroom Wizard 8 ขั้น**
   - ครู 1 คนสามารถเชื่อมต่อบัญชี Google ได้หลายบัญชี (เช่น บัญชีส่วนตัว + บัญชีโรงเรียน)
   - เข้ารหัส OAuth Access/Refresh Token ด้วย **Fernet (AES-128-CBC + HMAC-SHA256)** ก่อนบันทึกลงฐานข้อมูล ไม่เก็บ Token ใน Local Storage
   - ดึงรายวิชา งาน รายชื่อนักเรียน สถานะการส่งงาน และไฟล์แนบจาก **Google Classroom API & Google Drive API จริง**
   - หน้า Workflow แบบ **8-Step Wizard** พร้อม Progress Indicator และย้อนกลับแก้ไขได้ทุกขั้น

3. **Excel Grading Engine (`excel_engine/`)**
   - ตรวจสอบความปลอดภัยไฟล์ก่อนเปิด: Magic Bytes, ขนาดไฟล์, ป้องกัน Zip Bomb, ป้องกัน Path Traversal และตรวจจับ Macro (VBA) โดย **ไม่รัน Macro**
   - คำนวณสูตรใหม่ในสภาพแวดล้อมแยกด้วย **LibreOffice Headless** (`soffice --headless --norestore`)
   - แยกการตรวจ **สูตรจริง (`data_only=False`)** ออกจาก **ผลลัพธ์ (`data_only=True`)**
   - รองรับ 7 หมวดการตรวจ: สูตร (SUM, AVERAGE, MAX, MIN, COUNT, COUNTA, IF ซ้อน, SUMIF, COUNTIF, VLOOKUP, Relative/Absolute `$`, ข้าม Sheet), ผลลัพธ์ (Tolerance, ข้อผิดพลาด `#VALUE!`, `#DIV/0!`, `#REF!`, `#NAME?`), ตำแหน่งเซลล์, รูปแบบเซลล์, โครงสร้าง Worksheet, แผนภูมิ และความครบถ้วน
   - รองรับคะแนนบางส่วน (Partial Credit), กำหนดผิดได้ 0 ทันที, เก็บเวอร์ชันเกณฑ์ (`rubric_versions`) และ **ไม่เขียนทับคะแนนที่ครูยืนยันแล้วโดยอัตโนมัติ**

4. **รายงานและส่งออก**
   - รายงานผลรายบุคคลพร้อมตารางเปรียบเทียบสูตรเฉลยกับสูตรนักเรียน และคำแนะนำภาษาไทย
   - รายงานทั้งห้องพร้อมกราฟกระจายคะแนน และส่งออกเป็น **Excel (.xlsx)**, **CSV (UTF-8 BOM)** และ **PDF**

---

## โครงสร้างโปรเจกต์ (Monorepo)

```
excel-auto-grader/
├── frontend/          # Next.js 15 + React 19 + TypeScript + Tailwind (Pastel UI) + Lucide + Recharts
├── backend/           # FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Multi-Tenant API + Tests
├── excel_engine/      # Standalone Excel Grading Engine (openpyxl + LibreOffice + 12+ Tests)
├── workers/           # Celery + Redis Background Worker
├── database/          # PostgreSQL + Supabase RLS schema.sql & ER Diagram (erd.md)
├── docker/            # Dockerfiles (Backend + LibreOffice, Worker, Frontend)
├── docs/              # คู่มือติดตั้งและคู่มือการใช้งานสำหรับครู
├── docker-compose.yml
└── .env.example
```

---

## การเริ่มต้นใช้งานอย่างรวดเร็ว (Docker Compose)

1. คัดลอกไฟล์ตั้งค่าสภาพแวดล้อม:
   ```bash
   cp .env.example .env
   ```
2. กรอกค่าสำคัญใน `.env` (เช่น `APP_SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SUPABASE_*`)
3. รันทั้งระบบด้วย Docker Compose:
   ```bash
   docker compose up --build
   ```
4. เปิดใช้งาน:
   - **Frontend**: `http://localhost:3000`
   - **Backend API Docs (Swagger)**: `http://localhost:8000/docs`

ดูรายละเอียดเพิ่มเติมได้ที่ [คู่มือการติดตั้ง (SETUP_GUIDE.md)](docs/SETUP_GUIDE.md) และ [คู่มือครูผู้สอน (TEACHER_MANUAL.md)](docs/TEACHER_MANUAL.md)
