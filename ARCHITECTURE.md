# System Architecture & Engineering Specification
## Annapurna Memorial College ERP & Sundarban Ashutosh B.Ed. College

> **Document Version:** 2.0.0 (Production)  
> **Status:** Active & Implemented  
> **Deployment Architecture:** Backend on **Render** (Python ASGI), Admin Panel on **Vercel** (Edge SPA), Persistence on **MongoDB Atlas**  
> **Affiliation:** Baba Saheb Ambedkar Education University (BSAEU / WBUTTEPA) & NCTE Recognized  

---

## 1. Executive Summary & Domain Scope

The **Annapurna Memorial College ERP** is a unified, enterprise-grade Higher Education Institution management engine designed specifically for teacher education colleges (offering B.Ed., D.El.Ed., and Integrated B.A. Education programs) and university colleges. 

The system features:
1. **Three Dedicated Role Portals**:
   - **Teacher / Faculty Screen**: Replicating modern AI-assisted educational ERP layout with live class status, timetable, interactive Homework Submissions Donut chart with fluid movement, Student Performance bar chart, AI Lesson Planner, and student risk alerts.
   - **Super Admin / Principal Executive Screen**: Institutional command center with interactive regional trainee distribution map (South 24 Parganas delta: Kakdwip, Namkhana, Diamond Harbour, Patharpratima, Kulpi), revenue & fee collection rate, and direct 1-click marksheet authorization.
   - **Student / Trainee Screen**: Personal portal with NCTE 75% physical attendance compliance meter, official certified semester marksheet with 1-click PDF download, fee ledger, and study materials repository.
2. **End-to-End Excel Data Import Engine**:
   - Automatic spreadsheet parsing (`.xlsx`, `.xls`, `.csv`) with fuzzy header resolution (`Roll`, `Name`, `Course`, `Session`, `Semester`, `Category`, `Guardian`).
   - One-click import directly into MongoDB and reactive frontend state with pre-configured sample `.xlsx` template generator.
3. **Multi-Stage Marksheet Approval Workflow**: A robust state machine ensuring grade integrity from raw faculty score entries through departmental checks and administrative authorization to official public issuance.
4. **BSAEU & NCTE Compliance Engine**: Automated calculation of SGPA, CGPA, letter grades, attendance eligibility thresholds (minimum 75% rule), and practicum file verification.
5. **Hardware-Accelerated Web Audio Haptic Engine**: Tactile sound effects for button clicks, frequency-glide tab navigation, haptic pulses, and a triumphant harmonic chord upon approving/publishing marksheets, toggleable via the header sound switch.
6. **Resilient Micro-services & Integrations**: Cloudinary document vault with local storage fallback, Resend transactional emails with structured console fallback, and Firebase FCM push notifications with simulated dispatch fallbacks.
7. **Strict No-Emoji Standards**: 100% clean UI built exclusively using official Lucide SVG icons, vector assets, and badge chips.

---

## 2. High-Level System Architecture

```mermaid
flowchart TD
    subgraph Clients["Presentation Layer (Hosted on Vercel)"]
        TeacherPortal["Teacher / Faculty Dashboard\n(AI Assistant, Timetable, Donut & Bar Charts)"]
        SuperAdminPortal["Super Admin / Principal Console\n(Regional Map, Intake, Marksheet Clearance)"]
        StudentPortal["Student Trainee Portal\n(75% Attendance Meter, Certified Marksheet PDF)"]
        ExcelImportTool["Automated Excel / CSV Importer\n(Fuzzy Header Matching, Bulk Ingestion)"]
    end

    subgraph AudioEngine["Tactile Feedback Layer"]
        WebAudioHaptic["Web Audio API Synthesizer\n(Sine Micro-pops, Triangle Glide, Tactile Haptics)"]
    end

    subgraph CloudHosting["Cloud Infrastructure"]
        VercelEdge["Vercel SPA Hosting (vercel.json)"]
        RenderBackend["Render Web Service (render.yaml / Procfile)\nFastAPI + uv ASGI Server"]
        AtlasMongo[("MongoDB Atlas Cloud Database")]
    end

    subgraph ServiceLayer["Core Domain Services"]
        MarksheetSvc["Marksheet & Grade Engine\n(SGPA / CGPA / ReportLab PDF Generator)"]
        ExcelSvc["Excel Parser & Ingestion Engine\n(xlsx library)"]
        StorageSvc["Storage Service\n(Cloudinary & Local Disk)"]
        EmailSvc["Email Dispatcher\n(Resend API & Console Fallback)"]
        NotifSvc["Push Notification Dispatcher\n(Firebase FCM & Mock Fallback)"]
        AuditSvc["Security Audit Logging Service"]
    end

    TeacherPortal --> VercelEdge
    SuperAdminPortal --> VercelEdge
    StudentPortal --> VercelEdge
    ExcelImportTool --> VercelEdge

    TeacherPortal -.-> WebAudioHaptic
    SuperAdminPortal -.-> WebAudioHaptic
    StudentPortal -.-> WebAudioHaptic

    VercelEdge -->|HTTPS REST API| RenderBackend
    RenderBackend --> ServiceLayer
    ServiceLayer --> AtlasMongo
```

---

## 3. Marksheet Approval State Machine & Pipeline

```mermaid
stateDiagram-v2
    [*] --> DRAFT: Faculty enters raw theory & practical marks
    
    DRAFT --> SUBMITTED_BY_FACULTY: Faculty submits marksheet
    
    SUBMITTED_BY_FACULTY --> DEPARTMENT_VERIFIED: Academic Coordinator verifies internal assessment & attendance
    SUBMITTED_BY_FACULTY --> REJECTED: Discrepancy identified (Mandatory remarks)
    
    DEPARTMENT_VERIFIED --> ADMIN_APPROVED: Principal / Super Admin reviews and gives final approval
    DEPARTMENT_VERIFIED --> REJECTED: Modification required
    
    ADMIN_APPROVED --> PUBLISHED: Official publication to student portal & email broadcast
    ADMIN_APPROVED --> REJECTED: Withheld by administration
    
    REJECTED --> DRAFT: Faculty rectifies scores per rejection remarks
    
    PUBLISHED --> [*]: Certified Digital Marksheet with Tamper-Evident QR Hash
```

---

## 4. End-to-End Excel Ingestion Architecture

```mermaid
flowchart TD
    UserExcel["User uploads .xlsx / .xls / .csv Spreadsheet"]
    FileReader["Browser FileReader (Binary String Buffer)"]
    XLSXEngine["SheetJS (XLSX) Workbook Parser"]
    ColumnNormalizer["Fuzzy Header Normalizer\n(Matches: roll_number, roll no, name, student name, course, etc.)"]
    Validator{"Validation & Type Check"}
    AutoMapping["Row Entity Construction (Student / Marks Record)"]
    DataCommit["Automatic Commit to Database & Local State"]
    HapticSound["Haptic Success Audio Tone Trigger"]

    UserExcel --> FileReader
    FileReader --> XLSXEngine
    XLSXEngine --> ColumnNormalizer
    ColumnNormalizer --> Validator
    Validator -->|Valid| AutoMapping
    Validator -->|Invalid| ErrorList["Display Error List to User"]
    AutoMapping --> DataCommit
    DataCommit --> HapticSound
```

---

## 5. Deployment Topology (Render & Vercel)

```mermaid
flowchart LR
    subgraph VercelApp["Frontend: Vercel Edge"]
        VercelCDN["Vercel Global Edge CDN"]
        SPA["React 18 + TS Vite Single Page App"]
        VercelConfig["vercel.json (SPA Rewrites, Asset Caching)"]
    end

    subgraph RenderApp["Backend: Render Web Service"]
        RenderGateway["Render Reverse Proxy"]
        ProcfileEntry["Procfile: uv run uvicorn main:app"]
        RenderYaml["render.yaml (Automated Build & Python 3.13)"]
        FastAPIWorker["FastAPI ASGI Application"]
    end

    subgraph DatabaseCloud["Persistence & Third-Party"]
        MongoDBAtlas[("MongoDB Atlas Cloud Cluster")]
        CloudinaryVault["Cloudinary Media Store"]
        ResendMail["Resend Email Provider"]
        FirebaseFCM["Firebase Cloud Messaging"]
    end

    VercelCDN --> SPA
    SPA -->|HTTPS JSON API| RenderGateway
    RenderGateway --> FastAPIWorker
    FastAPIWorker --> MongoDBAtlas
    FastAPIWorker -.-> CloudinaryVault
    FastAPIWorker -.-> ResendMail
    FastAPIWorker -.-> FirebaseFCM
```

---

## 6. Mobile Push Notification Architecture (Firebase Cloud Messaging - FCM)

```mermaid
sequenceDiagram
    autonumber
    actor Trainee as Trainee / Faculty (Android Mobile)
    participant MobileApp as Android Mobile App (Untouched)
    participant GoogleFCM as Google Firebase FCM Server
    participant Backend as FastAPI Backend (Render)
    participant AtlasDB as MongoDB Atlas (device_tokens)
    actor Admin as Principal / Super Admin (Admin Panel)

    Note over MobileApp,GoogleFCM: 1. Mobile Device Token Generation
    MobileApp->>GoogleFCM: Request FCM Token on App Startup
    GoogleFCM-->>MobileApp: Return unique FCM Registration Token

    Note over MobileApp,Backend: 2. Device Token Registration
    MobileApp->>Backend: POST /api/v1/notifications/register-device<br/>(Bearer Token + fcm_token + platform: android)
    Backend->>AtlasDB: Upsert into db.device_tokens {user_id, fcm_token, platform, updated_at}
    Backend-->>MobileApp: 200 OK (Registration Recorded)

    Note over Admin,Backend: 3. Notification Trigger (Notice / Marksheet / Fees)
    Admin->>Backend: POST /api/v1/notices (or /examinations/{id}/publish)
    Backend->>AtlasDB: Query target user FCM tokens (or target audience topic)
    AtlasDB-->>Backend: Return list of active FCM tokens
    
    Note over Backend,GoogleFCM: 4. Firebase Admin SDK Dispatch
    Backend->>GoogleFCM: firebase_admin.messaging.send_multicast() / send()
    GoogleFCM-->>Backend: 200 OK (Batch Response with Success Count)
    GoogleFCM->>MobileApp: Native Android System Tray Push Notification
    MobileApp->>Trainee: Displays heads-up banner & rings phone
```

### Firebase Setup & Deployment Guide:
1. **Google Firebase Console Setup**:
   - Go to [Firebase Console](https://console.firebase.google.com/) and create/select project `annapurna-memorial-college-erp`.
   - **For Mobile (`annapurna-memorial-college-erp-app`)**:
     - Register Android app with Package Name (e.g. `com.annapurnacollege.erp`).
     - Download `google-services.json` and place it in the Android project `app/` directory.
   - **For Backend (`annapurna-memorial-college-erp-backend`)**:
     - Go to **Project Settings** ➔ **Service accounts** ➔ **Firebase Admin SDK**.
     - Click **Generate new private key** and download the JSON file.
     - Save this file locally in `annapurna-memorial-college-erp-backend/` as `firebase-service-account.json`.
     - In `.env` (already pre-configured): `FIREBASE_CREDENTIALS_PATH="firebase-service-account.json"`.
     - *Security Guarantee:* `firebase-service-account*.json` is protected in `.gitignore` and will never be pushed to GitHub.
   - **For Render Deployment**:
     - On Render.com backend dashboard, add an **Environment Secret File** named `firebase-service-account.json` containing the contents of your downloaded service account JSON.
     - Set the environment variable `FIREBASE_CREDENTIALS_PATH=/etc/secrets/firebase-service-account.json` (or relative path).

