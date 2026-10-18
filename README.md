# FreshMart — Online Supermarket & Grocery Platform

FreshMart is a production-ready online supermarket web platform inspired by the shopping flow and value-first design of **DMart India**, featuring original branding, deep green and leaf aesthetic, full-page security-check authentication modeled after **srinri.in/login/**, and complete role-based operations.

---

## 🛒 Brand & Visual Identity
- **Name:** FreshMart
- **Tagline:** *"Fresh food. Everyday low prices."*
- **Palette:** Deep green (`#14532d`), leaf green (`#22a05a`), cream (`#fbf7ef`), tomato red accent (`#e8532f`).
- **Typography:** `Fraunces` (warm, trustworthy editorial headings) & `Inter` (high-readability UI and pricing numbers).

---

## 🌟 Key Features

1. **DMart-Style Home Experience (`/`):**
   - **Announcement Bar:** Live everyday offers, delivery countdown, and customer hotline.
   - **Sticky Navigation:** Branded logo, location/pincode switcher (Hyderabad, Bengaluru, Mumbai, Delhi NCR, Chennai, Pune), DMart category filter dropdown with live search, dedicated Wishlist, direct full-page Login button, and live cart counter badge.
   - **3-Offer Banner Carousel:** Interactive auto-advancing banners highlighting mega grocery savings, farm-fresh produce, and household essentials.
   - **Category Quick Strip:** 10 curated supermarket aisles with visual badges and deal counts.
   - **Today's Best Deals:** Supermarket product cards featuring MRP strike-throughs, FreshMart everyday low price, discount percentage badges, absolute rupee savings tags, and live quantity steppers.
   - **Department Rails:** Dedicated rows for Staples & Groceries, Fruits & Vegetables, Dairy & Bakery, and Household & Cleaning.
   - **Value Pillars & Trust Badges:** Why FreshMart (Everyday Low Prices, 100% Quality Check, Express Delivery, Safe Payments), How it Works 4-step guide, Swecha AI shopping assistant preview, verified customer testimonials, and an interactive FAQ accordion.
   - **Supermarket Footer:** DMart-style categorized directory, accepted payment modes, customer grievance details, and copyright.

2. **Full-Page Security Check Login (`/login/` & `/accounts/login/`):**
   - **Split Screen Architecture (modeled after `https://www.srinri.in/login/`):**
     - **Left Panel:** Immersive branded visual hero banner with FreshMart identity, tagline, value metrics, and daily benefits.
     - **Right Panel:** Elevated login card with "Welcome back" greeting and dashboard access.
   - **Credentials Support:** Login with either standard username or registered 10-digit mobile number.
   - **Password Field:** Interactive eye toggle to show or hide plain text password.
   - **Security Check Captcha:** Dynamic session-backed SVG distortion captcha with noise lines and randomized character transforms, plus a "Try another captcha" link to refresh codes on demand.
   - **Progressive Security Lockout:** Rate limiting, IP tracking, and escalating lockout schedule (1 min, 5 min, 15 min, 1 hr, 24 hr) against brute-force attacks (`LoginAttempt`).
   - **Manual Typing Notice:** Strict `autocomplete="off"` compliance with notification: *"Please type your credentials manually. Autofill is not allowed."*
   - **Quick Demo Account Selector:** 1-click test fill buttons for Admin, Manager, Agent, and Customer accounts.

3. **Role-Based Redirect Matrix:**
   | Role | After Login Destination | Description |
   |---|---|---|
   | **Customer** | `/order/menu/` | Customer shopping portal with live cart, order history, and saved addresses |
   | **Delivery Agent** | `/agent/` | Delivery partner portal with order assignments, GPS navigation, and active status toggle |
   | **Store Manager / Staff** | `/manager/` | Staff and manager operations for stock, shifts, order queues, and inventory |
   | **Super Admin** | `/<ADMIN_URL>/orders/dashboard/` | Full administrative control, sales analytics, audit logs, and catalog management |

4. **Cart, Coupons & Checkout Flow:**
   - Real-time cart calculations with discounts.
   - Coupon engine (e.g. `FRESH20` for 20% off, `SAVE100` for ₹100 flat off, `DMART50`).
   - Multi-address checkout with customer session bridge.
   - Live order tracking with customer-friendly status timeline: Placed → Packed → Out for Delivery → Delivered.

---

## 👥 Demo Credentials

Run `python manage.py seed_freshmart` to seed the database with 10 categories, 42 products, 3 coupons, and demo accounts:

| Role | Username | Phone | Password | Post-Login URL |
|---|---|---|---|---|
| **Customer** | `customer_sneha` | `9876543210` | `Pass1234!` | `/order/menu/` |
| **Delivery Agent** | `agent_kiran` | `9876543211` | `Pass1234!` | `/agent/` |
| **Store Manager** | `manager_ravi` | `9876543212` | `Pass1234!` | `/manager/` |
| **Admin** | `admin` | `9876543200` | `Admin1234!` | `/backoffice/orders/dashboard/` |

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Python 3.11+
- Virtual environment (venv / conda)
- Optional: PostgreSQL 15+ / Redis 7+ (or default SQLite for local development)

### 2. Installation
```bash
# Clone the repository and enter directory
cd resturant-main-main

# Install dependencies
pip install -r requirements/dev.txt

# Apply migrations
python manage.py migrate

# Seed FreshMart catalog (10 categories, 42 products, coupons, and demo accounts)
python manage.py seed_freshmart

# Run development server
python manage.py runserver 8000
```

Access the application in your browser:
- **Home Page:** http://127.0.0.1:8000/
- **Login Page:** http://127.0.0.1:8000/login/
- **Customer Catalog:** http://127.0.0.1:8000/order/menu/
- **Agent Dashboard:** http://127.0.0.1:8000/agent/
- **Manager Dashboard:** http://127.0.0.1:8000/manager/
- **Admin Dashboard:** http://127.0.0.1:8000/backoffice/orders/dashboard/

---

## 🧪 Testing

Run the automated test suite across all portals and security mechanisms:
```bash
# Run FreshMart end-to-end tests
pytest apps/orders/tests/test_freshmart_portal.py -v

# Run authentication and progressive lockout tests
pytest apps/accounts/tests/ -v

# Run complete test suite (328+ tests)
pytest
```

---

## ☁️ Deployment on Render (with Neon / Supabase PostgreSQL)

The project includes `render.yaml` configured for zero-downtime deployment:

1. **Connect Repository on Render:**
   - Link your GitHub repository at [dashboard.render.com](https://dashboard.render.com).
   - Select **Blueprints** and point to `render.yaml`.
2. **Environment Variables:**
   - `DJANGO_SETTINGS_MODULE`: `config.settings.prod`
   - `DATABASE_URL`: Connection string from Neon Postgres or Supabase Postgres (`postgres://user:pass@host/dbname?sslmode=require`)
   - `SECRET_KEY`: High-entropy 50-character random key
   - `ALLOWED_HOSTS`: `.onrender.com,freshmart.yourdomain.com`
   - `ADMIN_URL`: `backoffice/` (or your chosen secure prefix)
3. **Build & Release Commands:**
   - **Build Command:** `pip install -r requirements/base.txt && python manage.py collectstatic --noinput && python manage.py migrate && python manage.py seed_freshmart`
   - **Start Command:** `uvicorn config.asgi:application --host 0.0.0.0 --port $PORT`
