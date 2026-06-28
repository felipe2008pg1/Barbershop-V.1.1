<h1 align="center">💈 Barbershop V1.1 — Remastered</h1>

<p align="center">
  <b>A production-ready full-stack barbershop management system</b><br/>
  Built with clean architecture, real database, and modern deployment.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Live-2ECC71?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/API-FastAPI-009688?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Database-PostgreSQL-4169E1?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Deploy-Render%20%7C%20Vercel-000000?style=for-the-badge"/>
</p>

---

## 🌐 Live Application

<p align="center">
  🔗 <b>Frontend:</b> <a href="#">Access App</a> <br/>
  ⚙️ <b>API:</b> <a href="#">View Docs</a>
</p>

---

## 🧠 Project Overview

This project is a **complete remaster** of a previous barbershop system, rebuilt from scratch with a focus on:

* scalability
* maintainability
* real-world architecture
* production deployment

Unlike the previous version, this system uses a **real cloud infrastructure**, replacing local storage with a robust and persistent database.

---

## ⚙️ Core Features

### 👤 Authentication & Roles

* Admin, Barber, and Client access control
* Protected routes via token validation

### 📅 Scheduling System

* Smart appointment creation
* Conflict prevention (date & time validation)
* Past-date blocking

### 🔄 Appointment Management

* Rescheduling system
* Cancellation flow
* Unique confirmation code tracking

### 🌍 Internationalization

* Full support for **English** and **Portuguese (BR)**

### 🎨 User Experience

* Light / Dark mode
* Clean and modern UI
* Responsive layout

---

## 🏗️ Architecture

* Modular FastAPI routers
* Separation of concerns (routes, services, validation)
* Environment-based configuration
* Clean and scalable project structure

---

## 🛠️ Tech Stack

<p>
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=FFD43B"/>
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=FFFFFF"/>
  <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=FFFFFF"/>
  <img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=000000"/>
  <img src="https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=FFFFFF"/>
  <img src="https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=FFFFFF"/>
</p>

---

## 🔐 Security

* Input validation (phone, dates, etc.)
* Protected admin access
* Rate limiting (anti-spam)
* Sanitized user input
* Error handling with structured responses

---

## 📂 Project Structure

```bash
app/
├── routers/
│   ├── __init__.py
│   ├── admin.py
│   ├── barber.py
│   └── public.py
├── services/
│   ├── __init__.py
│   ├── appointment_service.py
│   ├── audit_service.py
│   └── barber_rate_guard.py
├── __init__.py
├── auth.py
├── config.py
├── exceptions.py
├── logging_config.py
├── main.py
├── models.py
├── rate_limit.py
└── service_translations.py
│
static/
├── css/
│   └── style.css
├── favicon/
│   ├── android-chrome-192x192.png
│   ├── android-chrome-512x512.png
│   ├── apple-touch-icon.png
│   ├── favicon-16x16.png
│   ├── favicon-32x32.png
│   ├── favicon-48x48.png
│   ├── favicon.ico
│   └── validadot
└── js/
│   ├── admin.js
│   ├── barber.js
│   ├── config.js
│   ├── i18n.js
│   ├── public.js
│   └── theme.js
│
templates/
├── admin.html
├── barber.html
└── index.html
│
├── .env.example
├── .gitignore
├── README.md
├── render.yaml
├── requirements.txt
└── supabase_schema.sql
```
## 🔄 System Evolution — V1.0 vs V1.1

<table width="100%">

<tr>
<th width="50%">💈 V1.0 — Initial</th>
<th width="50%">🚀 V1.1 — Remastered</th>
</tr>

<tr>
<td>
<b>☁️ Infrastructure</b><br>
• Localhost only<br>
• No deployment
</td>
<td>
<b>☁️ Infrastructure</b><br>
• Render + Vercel<br>
• Public & global
</td>
</tr>

<tr>
<td>
<b>💾 Data Storage</b><br>
• JSON files<br>
• No persistence guarantee
</td>
<td>
<b>🗄️ Data Storage</b><br>
• PostgreSQL (Supabase)<br>
• Persistent & reliable
</td>
</tr>

<tr>
<td>
<b>🔐 Authentication</b><br>
• No login system<br>
• No roles
</td>
<td>
<b>🔐 Authentication</b><br>
• Admin / Barber / Client<br>
• Protected routes
</td>
</tr>

<tr>
<td>
<b>🏗️ Architecture</b><br>
• Monolithic structure<br>
• Hard to maintain
</td>
<td>
<b>🧱 Architecture</b><br>
• Modular FastAPI<br>
• Scalable design
</td>
</tr>

<tr>
<td>
<b>⚙️ Backend</b><br>
• Basic logic<br>
• Minimal validation
</td>
<td>
<b>⚙️ Backend</b><br>
• Strong validation<br>
• Logging & error handling
</td>
</tr>

<tr>
<td>
<b>🎨 Frontend</b><br>
• Simple UI<br>
• No theme system
</td>
<td>
<b>🎨 Frontend</b><br>
• Modern UI<br>
• Light / Dark mode
</td>
</tr>

<tr>
<td>
<b>📅 Scheduling</b><br>
• Basic booking<br>
• No conflict validation
</td>
<td>
<b>📅 Scheduling</b><br>
• Conflict prevention<br>
• Rescheduling system
</td>
</tr>

<tr>
<td>
<b>🌍 Internationalization</b><br>
• Not supported
</td>
<td>
<b>🌍 Internationalization</b><br>
• EN / PT-BR support
</td>
</tr>

</table>




---

## ⚡ Running Locally

```bash
git clone https://github.com/felipe2008pg1/Barbershop-V.1.1
cd Barbershop-V.1.0

pip install -r requirements.txt
uvicorn main:app --reload
```

---

## 🚀 Future Version (V2)

* JWT authentication
* Payment integration
* Admin dashboard with analytics
* Multi-location support

---

## 👨‍💻 Author
<b>Felipe Gonzalez</b>
| Full Stack Python Developer
