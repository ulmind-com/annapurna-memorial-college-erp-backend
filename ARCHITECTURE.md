# System Architecture & Engineering Specification
## Annapurna Memorial College ERP & Sundarban Ashutosh B.Ed. College

> **Document Version:** 1.0.0 (Production)  
> **Status:** Active & Implemented  
> **Author:** Principal Systems Architect & Senior Full-Stack Engineer  
> **Affiliation:** Baba Saheb Ambedkar Education University (BSAEU / WBUTTEPA) & NCTE Recognized  

---

## 1. Executive Summary & Domain Scope

The **Annapurna Memorial College ERP** is a unified, enterprise-grade Higher Education Institution management engine designed specifically for teacher education colleges (offering B.Ed., D.El.Ed., and Integrated B.A. Education programs) and university colleges. 

The system features:
1. **Multi-Stage Marksheet Approval Workflow**: A robust state machine ensuring grade integrity from raw faculty score entries through departmental checks and administrative authorization to official public issuance.
2. **BSAEU & NCTE Compliance Engine**: Automated calculation of SGPA, CGPA, letter grades, attendance eligibility thresholds (minimum 75% rule), and practicum file verification.
3. **Resilient Micro-services & Integrations**: Cloudinary document vault with local storage fallback, Resend transactional emails with structured console fallback, and Firebase FCM push notifications with simulated dispatch fallbacks.
4. **Web Audio Micro-Interaction Synthesizer**: Hardware-accelerated native Web Audio API audio synthesis in the frontend admin panel providing immediate tactile user feedback without external asset latency.

---

## 2. High-Level System Architecture

The following diagram illustrates the structural topology of the application, showing client interfaces, FastAPI backend micro-routers, database persistence, and external service fallbacks.

```mermaid
flowchart TD
    subgraph Clients["Presentation Layer"]
        WebAdmin["React + TypeScript Admin Panel\n(Vite, Tailwind, Web Audio)"]
        MobileApp["Android Mobile App\n(Kotlin / Compose)"]
        PublicVerifier["Third-Party University / Employer\nPublic QR Verifier"]
    end

    subgraph Gateway["API Gateway & Middleware Layer"]
        FastAPIApp["FastAPI REST Application (Uvicorn / ASGI)"]
        CORS["CORS & Origin Filtering"]
        AuthMiddleware["JWT Bearer RBAC Middleware"]
        StaticUploads["Local Static File Fallback (/uploads)"]
    end

    subgraph ServiceLayer["Core Domain Services"]
        MarksheetSvc["Marksheet & Grade Engine\n(SGPA / CGPA / PDF Generator)"]
        StorageSvc["Storage Service\n(Cloudinary & Local Disk)"]
        EmailSvc["Email Dispatcher\n(Resend API & Console Fallback)"]
        NotifSvc["Push Notification Dispatcher\n(Firebase FCM & Mock Fallback)"]
        AuditSvc["Audit Logging Service"]
    end

    subgraph Routers["API Routers (/api/v1)"]
        R_Auth["/auth"]
        R_Students["/students"]
        R_Faculty["/faculty"]
        R_Academics["/academics"]
        R_Attendance["/attendance"]
        R_Exams["/examinations"]
        R_Fees["/fees"]
        R_Notices["/notices"]
        R_Library["/study-materials"]
        R_Audit["/audit"]
    end

    subgraph DataStore["Persistence Layer"]
        MongoLive[("MongoDB Primary\n(Motor Async Client)")]
        LocalFiles[("Local File Vault\n(/uploads directory)")]
    end

    subgraph ExternalServices["Third-Party Providers"]
        CloudinaryCloud["Cloudinary Cloud Storage"]
        ResendAPI["Resend Email Service"]
        FCM["Firebase Cloud Messaging"]
    end

    WebAdmin -->|HTTPS / REST API| FastAPIApp
    MobileApp -->|HTTPS / REST API| FastAPIApp
    PublicVerifier -->|HTTPS / GET /verify/:hash| FastAPIApp

    FastAPIApp --> CORS
    CORS --> AuthMiddleware
    AuthMiddleware --> Routers

    Routers --> ServiceLayer

    StorageSvc -->|Primary| CloudinaryCloud
    StorageSvc -.->|Graceful Fallback| LocalFiles

    EmailSvc -->|Primary| ResendAPI
    EmailSvc -.->|Graceful Fallback| AuditSvc

    NotifSvc -->|Primary| FCM
    NotifSvc -.->|Graceful Fallback| AuditSvc

    MarksheetSvc --> MongoLive
    Routers --> MongoLive
```

---

## 3. Authentication & RBAC Lifecycle

Authentication uses JSON Web Tokens (JWT) using the `HS256` symmetric signing algorithm with distinct access tokens (60 minutes) and refresh tokens (7 days).

```mermaid
sequenceDiagram
    autonumber
    actor Admin as College Admin / Faculty
    participant Client as Admin Panel UI
    participant API as FastAPI Backend (/auth)
    participant DB as MongoDB (users)
    participant Audit as Audit Logger

    Admin->>Client: Enters Email & Password
    Client->>API: POST /api/v1/auth/login {email, password}
    API->>DB: find_one({email})
    DB-->>API: User record (bcrypt hash, role)
    API->>API: bcrypt.checkpw(plain, hashed)

    alt Invalid Credentials
        API-->>Client: 401 Unauthorized (Invalid credentials)
        Client-->>Admin: Show error shake & trigger alert sound
    else Valid Credentials
        API->>API: Generate Access Token (JWT 60m)
        API->>API: Generate Refresh Token (JWT 7d)
        API->>Audit: Log USER_LOGIN with IP & timestamp
        API-->>Client: 200 OK {access_token, refresh_token, user_profile}
        Client->>Client: Store access_token in localStorage
        Client->>Client: Trigger login success audio chime
        Client-->>Admin: Route to Executive Dashboard
    end

    Note over Client,API: Subsequent requests include: Authorization: Bearer <token>

    Client->>API: GET /api/v1/examinations/marksheets (with token)
    API->>API: decode_token(token) & verify claims
    API->>API: verify role in [ADMIN, SUPER_ADMIN, FACULTY]
    API->>DB: Query marksheets
    DB-->>API: Document collection
    API-->>Client: 200 OK Marksheets payload
```

---

## 4. Marksheet Approval State Machine & Pipeline

The marksheet workflow is an immutable state machine designed to eliminate unauthorized grade alterations and maintain complete auditability:

```mermaid
stateDiagram-v2
    [*] --> DRAFT: Faculty enters raw theory & practical marks
    
    DRAFT --> SUBMITTED_BY_FACULTY: Faculty submits marksheet
    
    SUBMITTED_BY_FACULTY --> DEPARTMENT_VERIFIED: Academic Coordinator verifies internal assessment & attendance
    SUBMITTED_BY_FACULTY --> REJECTED: Discrepancy identified (Remarks required)
    
    DEPARTMENT_VERIFIED --> ADMIN_APPROVED: Principal / Super Admin reviews and gives final approval
    DEPARTMENT_VERIFIED --> REJECTED: Modification required
    
    ADMIN_APPROVED --> PUBLISHED: Official publication to student portal & email broadcast
    ADMIN_APPROVED --> REJECTED: Withheld by administration
    
    REJECTED --> DRAFT: Faculty rectifies scores per rejection remarks
    
    PUBLISHED --> [*]: Certified Digital Marksheet with Tamper-Evident QR Hash
```

### Transition Enforcement Matrix
| Transition | Allowed Roles | Mandatory Conditions | Triggered Event |
| :--- | :--- | :--- | :--- |
| `DRAFT` ➔ `SUBMITTED_BY_FACULTY` | `FACULTY`, `ADMIN`, `SUPER_ADMIN` | All subject scores entered within max limits | Audit log recorded |
| `SUBMITTED_BY_FACULTY` ➔ `DEPARTMENT_VERIFIED` | `ADMIN`, `SUPER_ADMIN` | Attendance prerequisite verified (≥ 75%) | Audit log recorded |
| `DEPARTMENT_VERIFIED` ➔ `ADMIN_APPROVED` | `ADMIN`, `SUPER_ADMIN` (Principal) | Academic committee review complete | Audit log recorded |
| `ADMIN_APPROVED` ➔ `PUBLISHED` | `SUPER_ADMIN` | Final approval from Controller of Examinations | Email sent, QR hash active |
| Any stage ➔ `REJECTED` | Reviewing Role | Mandatory `rejection_reason` / audit notes | Faculty alerted |

---

## 5. Entity-Relationship Data Model (ERD)

The MongoDB document schema models collegiate relationships between students, faculty, examinations, marksheets, attendance sessions, and financial ledgers:

```mermaid
erDiagram
    USERS ||--o{ AUDIT_LOGS : performs
    USERS ||--o| STUDENTS : credentials_of
    USERS ||--o| FACULTY : credentials_of
    
    COURSES ||--|{ SUBJECTS : contains
    COURSES ||--|{ STUDENTS : enrolls
    COURSES ||--|{ FEE_STRUCTURES : defines
    
    FACULTY ||--o{ SUBJECTS : teaches
    FACULTY ||--o{ ATTENDANCE_RECORDS : takes
    
    STUDENTS ||--|{ ATTENDANCE_ITEMS : recorded_in
    STUDENTS ||--|{ MARKSHEETS : receives
    STUDENTS ||--|{ INVOICES : billed_to
    
    EXAMINATIONS ||--|{ MARKSHEETS : contains
    
    INVOICES ||--o{ PAYMENTS : settles

    STUDENTS {
        string id PK
        string roll_number UK
        string registration_number UK
        string full_name
        string email
        string course_code FK
        int semester
        string status
    }

    MARKSHEETS {
        string id PK
        string exam_id FK
        string student_id FK
        float total_marks_obtained
        float overall_percentage
        float sgpa
        string letter_grade
        string status
        string qr_code_hash UK
    }

    INVOICES {
        string id PK
        string invoice_number UK
        string student_id FK
        float amount_due
        float amount_paid
        float balance
        string status
    }

    ATTENDANCE_RECORDS {
        string id PK
        date date
        string course_code FK
        int semester
        string subject_code FK
        int present_count
        int total_students
    }
```

---

## 6. Resilient Third-Party Integration Architecture

```mermaid
flowchart TD
    subgraph UploadPipeline["Media & Document Storage Pipeline"]
        UploadReq["File Upload Request (e.g. Student Document / Syllabus)"]
        CheckCloudinary{"Cloudinary Keys Configured?"}
        CloudinaryUpload["Upload to Cloudinary via SDK"]
        LocalDiskFallback["Write to Local static uploads/ directory"]
        ReturnURL["Return Storage URL (/uploads/... or cloudinary.com)"]

        UploadReq --> CheckCloudinary
        CheckCloudinary -->|Yes| CloudinaryUpload
        CheckCloudinary -->|No / Failed| LocalDiskFallback
        CloudinaryUpload --> ReturnURL
        LocalDiskFallback --> ReturnURL
    end

    subgraph EmailPipeline["Transactional Email Pipeline"]
        EmailReq["Email Request (Password Reset / Marksheet Published)"]
        CheckResend{"Resend API Key Configured?"}
        ResendSend["Dispatch via Resend API"]
        ConsoleFallback["Simulate Email: Output to Structured Log"]

        EmailReq --> CheckResend
        CheckResend -->|Yes| ResendSend
        CheckResend -->|No / Failed| ConsoleFallback
    end

    subgraph PushPipeline["FCM Push Notification Pipeline"]
        PushReq["Push Alert (Urgent Notice / Exam Announcement)"]
        CheckFirebase{"Firebase Credentials Present?"}
        FCMSend["Dispatch Multicast via Firebase Admin SDK"]
        MockPushFallback["Simulate Push Notification to Log"]

        PushReq --> CheckFirebase
        CheckFirebase -->|Yes| FCMSend
        CheckFirebase -->|No / Failed| MockPushFallback
    end
```

---

## 7. Web Audio Micro-Interaction Synthesizer Architecture

The Admin Panel includes a zero-dependency sound synthesizer implemented natively through the browser's `AudioContext`.

```mermaid
flowchart LR
    subgraph UIEvent["User Interaction"]
        BtnClick["Button Click"]
        TabChange["Tab Transition"]
        ApproveAction["Marksheet Approval"]
        AlertEvent["Validation Discrepancy"]
    end

    subgraph SoundEngine["Web Audio Synthesizer (audio.ts)"]
        CheckPref{"User Sound FX Enabled?"}
        AudioCtx["AudioContext Instance"]
        Oscillator["OscillatorNode (Sine / Triangle / Sawtooth)"]
        GainNode["GainNode (Exponential Ramp Envelope)"]
        Speaker["Hardware Audio Destination"]
    end

    BtnClick --> CheckPref
    TabChange --> CheckPref
    ApproveAction --> CheckPref
    AlertEvent --> CheckPref

    CheckPref -->|Enabled| AudioCtx
    CheckPref -->|Disabled| Mute["Silent No-Op"]

    AudioCtx --> Oscillator
    Oscillator --> GainNode
    GainNode --> Speaker
```

### Micro-interaction Acoustic Specs:
1. **Click Pop**: Sine wave frequency ramp from $880\text{ Hz} \to 320\text{ Hz}$ with exponential decay over $45\text{ ms}$.
2. **Tab Transition**: Triangle wave sweep $440\text{ Hz} \to 720\text{ Hz}$ over $80\text{ ms}$.
3. **Success Chime**: Major third harmonic progression ($C_5 = 523.25\text{ Hz} \to E_5 = 659.25\text{ Hz} \to G_5 = 783.99\text{ Hz}$) cascaded across $250\text{ ms}$.
4. **Official Marksheet Approval Chord**: Full A-Major resonant chord ($A_4 = 440\text{ Hz}, C\#_5 = 554.37\text{ Hz}, E_5 = 659.25\text{ Hz}, A_5 = 880\text{ Hz}$) sustained over $400\text{ ms}$.
5. **Rejection Alert**: Low frequency sawtooth drop $260\text{ Hz} \to 180\text{ Hz}$ over $130\text{ ms}$.

---

## 8. Deployment, Scalability & Security Topology

```mermaid
flowchart TD
    subgraph Internet["Public Network"]
        ClientsNet["Admin Users / Trainees / University Evaluators"]
    end

    subgraph Edge["Edge Infrastructure"]
        Nginx["Nginx Reverse Proxy / Cloudflare CDN"]
        SSL["TLS 1.3 Termination & DDoS Mitigation"]
    end

    subgraph AppCluster["Application Tier"]
        Uvicorn1["FastAPI Instance 1 (Worker 1)"]
        Uvicorn2["FastAPI Instance 2 (Worker 2)"]
        Uvicorn3["FastAPI Instance 3 (Worker 3)"]
    end

    subgraph DataTier["Data Tier"]
        MongoPrimary[("MongoDB Replica Set Primary")]
        MongoSecondary[("MongoDB Replica Set Secondary")]
    end

    ClientsNet --> SSL
    SSL --> Nginx
    Nginx -->|Load Balanced HTTP/2| Uvicorn1
    Nginx -->|Load Balanced HTTP/2| Uvicorn2
    Nginx -->|Load Balanced HTTP/2| Uvicorn3

    Uvicorn1 --> MongoPrimary
    Uvicorn2 --> MongoPrimary
    Uvicorn3 --> MongoPrimary

    MongoPrimary -.->|Async Replication| MongoSecondary
```

---

## 9. Verification & Quality Assurance Runbook

### Backend Verification
- Package Management: `uv`
- Dependency Resolution: Fast lockfile synchronization (`uv sync`)
- Test Coverage: Pytest async suite (`uv run pytest`)
  - Authentication & Token Claims
  - Student Admission CRUD
  - Marksheet Pipeline State Machine Transitions & Rejection Rules
  - ReportLab PDF Generation
  - Public Cryptographic Hash Verification
  - Fee Ledger Invoicing & Payments

### Frontend Verification
- TypeScript Strict Mode Compilation (`tsc`)
- Vite Bundle Production Build (`vite build`)
- Cross-browser Web Audio compatibility with audio resume gesture handler
- Zero missing module imports or CSS class collisions
