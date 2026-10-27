<div align="center">

<img src=".github/assets/banner.svg" width="100%" alt="Barbershop V1.1 — Remastered"/>

<br/>

<img src="https://img.shields.io/badge/Status-Live-2ECC71?style=flat-square&labelColor=0B1320" alt="Status: Live"/>
<img src="https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=FFFFFF&labelColor=0B1320" alt="FastAPI"/>
<img src="https://img.shields.io/badge/Database-PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=FFFFFF&labelColor=0B1320" alt="PostgreSQL"/>
<img src="https://img.shields.io/badge/Deploy-Render_%7C_Vercel-E63946?style=flat-square&labelColor=0B1320" alt="Deploy: Render and Vercel"/>
<img src="https://img.shields.io/badge/i18n-EN_%7C_PT--BR-1D5FD1?style=flat-square&labelColor=0B1320" alt="EN and PT-BR"/>

<br/><br/>

**A production-ready full-stack barbershop management system.**<br/>
Built with clean architecture, a real database, and modern deployment.

<br/>

<a href="#live-application"><b>Live</b></a> &nbsp;·&nbsp;
<a href="#overview"><b>Overview</b></a> &nbsp;·&nbsp;
<a href="#features"><b>Features</b></a> &nbsp;·&nbsp;
<a href="#architecture"><b>Architecture</b></a> &nbsp;·&nbsp;
<a href="#security"><b>Security</b></a> &nbsp;·&nbsp;
<a href="#tech-stack"><b>Stack</b></a> &nbsp;·&nbsp;
<a href="#project-structure"><b>Structure</b></a> &nbsp;·&nbsp;
<a href="#evolution"><b>Evolution</b></a> &nbsp;·&nbsp;
<a href="#running-locally"><b>Run</b></a> &nbsp;·&nbsp;
<a href="#roadmap"><b>Roadmap</b></a>

</div>

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Live Application

<div align="center">

| 🔗 Frontend | ⚙️ API |
|:---:|:---:|
| [**Access App**](#) | [**View Docs**](#) |

</div>

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Overview

> [!IMPORTANT]
> This project is a **complete remaster** of a previous barbershop system, rebuilt from scratch.
> Unlike the previous version, it runs on **real cloud infrastructure**, replacing local storage with a robust and persistent database.

<div align="center">

| 📈 Scalability | 🧩 Maintainability | 🏛️ Real-world architecture | 🚀 Production deployment |
|:---:|:---:|:---:|:---:|
| Persistent cloud database | Modular FastAPI codebase | Routers · Services · Security | Render + Vercel |

</div>

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Features

_The service menu:_

| | Service | What you get |
|:---:|---|---|
| 👤 | **Authentication & Roles** | Admin, Barber, and Client access control · Protected routes via token validation |
| 📅 | **Scheduling System** | Smart appointment creation · Conflict prevention (date & time validation) · Past-date blocking |
| 🔄 | **Appointment Management** | Rescheduling system · Cancellation flow · Unique confirmation code tracking |
| 🌍 | **Internationalization** | Full support for **English** and **Portuguese (BR)** |
| 🎨 | **User Experience** | Light / Dark mode · Clean and modern UI · Responsive layout |

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Architecture

**How a booking travels through the system:**

```mermaid
sequenceDiagram
    autonumber
    actor C as Client
    participant F as Frontend
    participant A as FastAPI
    participant D as PostgreSQL

    C->>F: Pick service, date and time
    F->>A: POST appointment
    A->>A: Validate input (phone, dates) and rate limit
    A->>D: Check conflicts for date and time
    D-->>A: Slot status
    alt Slot is free
        A->>D: Save appointment
        A-->>F: Confirmation code
        F-->>C: Booking confirmed
    else Conflict or past date
        A-->>F: Structured error response
        F-->>C: Choose another time
    end
```

**How the layers connect:**

```mermaid
flowchart LR
    UI["Frontend<br/>static/ · templates/"] --> MW["Middleware<br/>Request ID · HTTPS/CORS<br/>Cloudflare origin · Security"]
    MW --> R["Routers<br/>public · barber · admin"]
    R --> S["Services<br/>appointments · audit<br/>barber rate guard"]
    R --> SEC["Security<br/>crypto · login guard<br/>MFA · password policy"]
    S --> DB[("PostgreSQL<br/>Supabase")]
```

**Layers:**

| Layer | Location | Responsibility |
|---|---|---|
| Routers | `app/routers/` | Modular endpoints: `public`, `barber`, `admin` |
| Services | `app/services/` | Business logic: appointments, audit, barber rate guard |
| Security | `app/security/` | Crypto, login guard, MFA, password policy |
| Middleware | `app/middleware/` | Request ID, HTTPS / CORS, Cloudflare origin, security layer |
| Data | `app/models.py` · `supabase_schema.sql` | Models and PostgreSQL schema |
| Config | `app/config.py` · `.env.example` | Environment-based configuration |

Separation of concerns (routes, services, validation) keeps the structure clean and scalable.

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Security

| | Protection |
|:---:|---|
| ✅ | **Input validation** (phone, dates, etc.) |
| 🛡️ | **Protected admin access** |
| 🚦 | **Rate limiting** (anti-spam) |
| 🧼 | **Sanitized user input** |
| 🧯 | **Error handling** with structured responses |

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Tech Stack

<div align="center">

<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=FFD43B" alt="Python"/>
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=FFFFFF" alt="FastAPI"/>
<img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=FFFFFF" alt="PostgreSQL"/>
<img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=000000" alt="JavaScript"/>
<img src="https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=FFFFFF" alt="HTML5"/>
<img src="https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=FFFFFF" alt="CSS3"/>

</div>

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Project Structure

<details>
<summary><b>Expand file tree</b></summary>

```bash
Barbershop-V.1.1/
├── .github/
│   ├── assets/
│   │   ├── banner.svg
│   │   └── divider.svg
│   └── workflows/
│       └── supabase-backup.yml
├── app/
│   ├── middleware/
│   │   ├── cloudflare_origin.py
│   │   ├── https_cors.py
│   │   ├── request_id.py
│   │   ├── security_middleware.py
│   │   └── __init__.py
│   ├── routers/
│   │   ├── admin.py
│   │   ├── barber.py
│   │   ├── public.py
│   │   └── __init__.py
│   ├── security/
│   │   ├── crypto.py
│   │   ├── __init__.py
│   │   ├── login_guard.py
│   │   ├── mfa.py
│   │   └── password_policy.py
│   ├── services/
│   │   ├── appointment_service.py
│   │   ├── audit_service.py
│   │   ├── barber_rate_guard.py
│   │   └── __init__.py
│   ├── auth.py
│   ├── config.py
│   ├── exceptions.py
│   ├── logging_config.py
│   ├── main.py
│   ├── models.py
│   ├── rate_limit.py
│   ├── service_translations.py
│   └── __init__.py
├── scripts/
│   └── backfill_encryption.py
├── static/
│   ├── css/
│   │   └── style.css
│   ├── favicon/
│   │   ├── android-chrome-192x192.png
│   │   ├── android-chrome-512x512.png
│   │   ├── apple-touch-icon.png
│   │   ├── favicon-16x16.png
│   │   ├── favicon-32x32.png
│   │   ├── favicon-48x48.png
│   │   ├── favicon.ico
│   │   └── validadot
│   └── js/
│       ├── admin.js
│       ├── barber.js
│       ├── config.js
│       ├── i18n.js
│       ├── public.js
│       └── theme.js
├── templates/
│   ├── admin.html
│   ├── barber.html
│   ├── index.html
│   └── privacy.html
├── .env.example
├── .gitignore
├── README.md
├── render.yaml
├── requirements-lock.txt
├── requirements.txt
└── supabase_schema.sql
```

</details>

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Evolution

_V1.0 → V1.1: what changed in the remaster._

| Area | 💈 V1.0 — Initial | 🚀 V1.1 — Remastered |
|---|---|---|
| ☁️ **Infrastructure** | Localhost only · No deployment | Render + Vercel · Public & global |
| 🗄️ **Data Storage** | JSON files · No persistence guarantee | PostgreSQL (Supabase) · Persistent & reliable |
| 🔐 **Authentication** | No login system · No roles | Admin / Barber / Client · Protected routes |
| 🧱 **Architecture** | Monolithic structure · Hard to maintain | Modular FastAPI · Scalable design |
| ⚙️ **Backend** | Basic logic · Minimal validation | Strong validation · Logging & error handling |
| 🎨 **Frontend** | Simple UI · No theme system | Modern UI · Light / Dark mode |
| 📅 **Scheduling** | Basic booking · No conflict validation | Conflict prevention · Rescheduling system |
| 🌍 **Internationalization** | Not supported | EN / PT-BR support |

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Running Locally

```bash
git clone https://github.com/felipe2008pg1/Barbershop-V.1.1
cd Barbershop-V.1.1

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env             # then fill in your own values

uvicorn app.main:app --reload
```

> [!NOTE]
> Never commit `.env`. Use `requirements-lock.txt` for reproducible installs.

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

## Roadmap

**Future version (V2)**

- [ ] 🔑 JWT authentication
- [ ] 💳 Payment integration
- [ ] 📊 Admin dashboard with analytics
- [ ] 📍 Multi-location support

<img src=".github/assets/divider.svg" width="100%" height="10" alt=""/>

<div align="center">

**Felipe Gonzalez** &nbsp;·&nbsp; Full Stack Python Developer

<sub>💈 Clean cuts, clean code.</sub>

</div>
