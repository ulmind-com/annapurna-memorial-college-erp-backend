# Annapurna Memorial College ERP Backend API
**Sundarban Ashutosh B.Ed. College & Annapurna Memorial College**
*Production-grade Higher Education Enterprise Resource Planning (ERP) Engine*

---

## 🌟 Key Features
- **Architecture**: Modular FastAPI + Python 3.13 + `uv` package manager + Motor async MongoDB.
- **Security & RBAC**: JWT Access & Refresh token rotation, bcrypt password hashing, granular role-based permissions (`SUPER_ADMIN`, `ADMIN`, `FACULTY`, `STUDENT`, `STAFF`).
- **Marksheet Approval Pipeline**:
  - Multi-stage state machine: `DRAFT` ➔ `SUBMITTED_BY_FACULTY` ➔ `DEPARTMENT_VERIFIED` ➔ `ADMIN_APPROVED` ➔ `PUBLISHED` (with rejection audit trail).
  - BSAEU / NCTE grading scale (SGPA, CGPA, letter grades, distinction classifications).
  - Cryptographic verification hash (`qr_code_hash`) for tamper-evident validation.
  - On-the-fly downloadable PDF generation via `ReportLab`.
- **Admissions & Student Management**:
  - Full student profile tracking, roll number indexing, document attachment vault.
- **Academic Management**:
  - Courses (B.Ed., D.El.Ed., B.A. Ed.), Semesters, Subjects, Faculty course allocation.
- **Attendance System**:
  - Daily & subject-wise attendance taking, automated low-attendance warnings (<75% threshold).
- **Fees & Accounts**:
  - Semester fee structures, automated invoice generation, payment reconciliation, outstanding fee ledger.
- **Resilient Third-Party Integrations**:
  - **Cloudinary**: Media & document storage with local storage fallback.
  - **Resend**: Transactional emails with structured console fallback.
  - **Firebase Admin FCM**: Push notifications with graceful mock fallback.
- **Auditing**: Immutable audit logging across all critical institutional actions.

---

## 🚀 Quickstart Guide

### 1. Requirements
- Python `>= 3.13`
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- MongoDB running on `mongodb://localhost:27017`

### 2. Install Dependencies
```bash
uv sync
```

### 3. Seed Realistic Database
Populate courses, faculty, students, attendance, fees, marksheets, and default superadmin:
```bash
uv run python -m annapurna_memorial_college_erp_backend.seed
```

Default SuperAdmin Credentials:
- **Email**: `admin@annapurnacollege.org`
- **Password**: `Admin@123456`

### 4. Run Development Server
```bash
uv run uvicorn annapurna_memorial_college_erp_backend.main:app --reload --port 8000
```
Interactive Swagger API documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
ReDoc documentation: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 5. Run Test Suite
```bash
uv run pytest
```

---

## 📡 API Routing Overview
| Prefix | Description |
| :--- | :--- |
| `/health` | Live system and database health check |
| `/api/v1/auth` | Login, token refresh, password recovery, `/me` |
| `/api/v1/users` | User management and role provisioning |
| `/api/v1/students` | Student admission, records, document uploads |
| `/api/v1/faculty` | Faculty directory and department assignment |
| `/api/v1/academics` | Courses, semesters, subjects, sessions |
| `/api/v1/attendance` | Take attendance, view sheets, analytics |
| `/api/v1/examinations` | Exam scheduling, mark entry, approval pipeline, PDF |
| `/api/v1/fees` | Fee structures, invoices, payment receipts |
| `/api/v1/notices` | Circulars, push alerts, email broadcast |
| `/api/v1/study-materials` | Digital library and syllabus notes repository |
| `/api/v1/audit` | Security audit trail logs |
| `/api/v1/seed` | On-demand database seeding |
