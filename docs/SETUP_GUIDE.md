# คู่มือการติดตั้งและตั้งค่า Excel Auto Grader (Production & Local)

## 1. ความต้องการของระบบ
- **Docker & Docker Compose** (แนะนำ — รวม Python 3.12 + LibreOffice Headless + PostgreSQL 16 + Redis 7 + Node.js 22 ครบในชุดเดียว)
- หรือหากรันแบบแยกเครื่อง (Local Dev):
  - Node.js 22+
  - Python 3.12+
  - LibreOffice (`soffice`) สำหรับคำนวณสูตร Excel จริง
  - PostgreSQL 15+ (หรือ Supabase Project)
  - Redis 7+

## 2. การตั้งค่าฐานข้อมูล Supabase (PostgreSQL + RLS)
1. สร้างโปรเจกต์ใน [Supabase](https://supabase.com/)
2. เปิด **SQL Editor** แล้วคัดลอกเนื้อหาจาก `database/schema.sql` ไปรันเพื่อสร้างตารางทั้ง 23 ตารางและเปิด **Row Level Security (RLS)**
3. สร้าง Private Storage Bucket ชื่อ `excel-auto-grader` และเปิด Storage Policy ที่อยู่ในส่วนท้ายของ `database/schema.sql`
4. นำค่า `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` และ `SUPABASE_JWT_SECRET` มาใส่ในไฟล์ `.env`

## 3. การตั้งค่า Google OAuth 2.0 (Google Classroom & Drive API)
1. เข้า [Google Cloud Console](https://console.cloud.google.com/) และสร้างโปรเจกต์ใหม่
2. เปิดใช้งาน APIs:
   - **Google Classroom API**
   - **Google Drive API**
3. ตั้งค่า **OAuth Consent Screen** และเพิ่ม Scopes:
   - `openid`, `email`, `profile`
   - `https://www.googleapis.com/auth/classroom.courses.readonly`
   - `https://www.googleapis.com/auth/classroom.rosters.readonly`
   - `https://www.googleapis.com/auth/classroom.coursework.students.readonly`
   - `https://www.googleapis.com/auth/drive.readonly`
4. สร้าง **OAuth 2.0 Client ID (Web Application)** และกำหนด Authorized Redirect URI เป็น:
   - Local: `http://localhost:8000/api/v1/google-accounts/callback`
   - Production: `https://your-api-domain.com/api/v1/google-accounts/callback`
5. นำ `GOOGLE_CLIENT_ID` และ `GOOGLE_CLIENT_SECRET` ไปใส่ใน `.env`

## 4. การสร้าง Key เข้ารหัส Token
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
นำผลลัพธ์ไปใส่ในตัวแปร `TOKEN_ENCRYPTION_KEY` ในไฟล์ `.env`

## 5. การรันชุดทดสอบอัตโนมัติ (Automated Tests)
```bash
# 1. ทดสอบ Excel Grading Engine (12+ เคสตรวจสูตร ผลลัพธ์ รูปแบบ แผนภูมิ ความปลอดภัย)
pytest excel_engine/tests -v

# 2. ทดสอบ Multi-Teacher Isolation, Multi-Google Accounts, Grading & Exports
pytest backend/tests -v

# 3. ตรวจสอบ TypeScript & Next.js Build
cd frontend && npm ci && npm run typecheck && npm run build
```
