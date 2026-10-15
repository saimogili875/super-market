# Restaurant Ordering System — Architecture & Audit Closing Report (`REVIEW.md`)

## 1. Architecture Overview

The system is a production-ready, bespoke full-stack Django 5.2 application designed for a dual-channel modern dining platform: **QR Dine-In Ordering** and **Customer Delivery Ordering**, supported by dedicated workflows for **Delivery Agents**, **Kitchen/Staff Management**, and **Financial Analytics**.

### Core Domain Models & Data Arc
- **`apps.accounts`**: Custom user management extending Django's auth model with explicit role-based access (`ADMIN`, `AGENT`, `CUSTOMER`). Includes `AgentProfile` for tracking real-time delivery agent availability.
- **`apps.menu`**: High-performance catalog (`Category`, `MenuItem`) with automated on-the-fly image compression (`compress_image`), pricing truth (`effective_price`), and optimized query paths (`available_menu()`).
- **`apps.tables`**: Physical table representation (`Table`) protected against IDOR via unguessable 32-character opaque tokens (`qr_token`). Lifecycle tracking is enforced via `TableSession` with a database-enforced partial unique constraint guaranteeing exactly one active session per table (`closed_at__isnull=True`).
- **`apps.orders`**: State-machine-governed ordering (`Order`, `OrderItem`, `OrderEvent`). Separates channel models: Dine-in orders bind to `TableSession` and `Table`; Delivery orders bind to signed cookies and assigned `Agent`s.
- **`apps.analytics`**: Settlement analytics engine operating completely database-side (`SETTLED_STATUSES = [OrderStatus.PAID]`) using Django ORM aggregations (`Sum`, `Count`, `Avg`) over indexed status and timestamp fields.

### State Machine Arc (`apps.orders.state`)
All order transitions flow strictly through `apps.orders.services.transition()`, which validates channel constraints and role permissions:
- **Dine-In Arc**: `PLACED` -> `APPROVED` -> `IN_KITCHEN` -> `READY` -> `PAID` (or `CANCELLED`).
- **Delivery Arc**: `PLACED` -> `APPROVED` -> `IN_KITCHEN` -> `READY` -> `DISPATCHED` -> `ARRIVED` -> `COLLECTED` -> `PAID` (or `CANCELLED`).
  (Status codes stored in the DB: `PLACED, APPROVED, KITCHEN, READY, DISPATCH, ARRIVED, COLLECT, PAID, CANCEL` — see `apps/orders/models.py:OrderStatus` and the authoritative transition table in `apps/orders/state.py`.)
Every transition appends an immutable audit log (`OrderEvent`) and emits real-time WebSocket notifications via Django Channels/Redis (`apps.realtime`).

---

## 2. Optimization Audit Findings & Proof

| Optimization Item | Implementation Details | Status & Proof |
| :--- | :--- | :--- |
| **A.1 N+1 Queries** | All list views (`dashboard`, `assign_order`, `track_order`) and Django Admin classes (`OrderAdmin`, `TableSessionAdmin`, `MenuItemAdmin`) explicitly use `.select_related()` and `.prefetch_related()`. | Verified via `pytest` query assertion suites (`test_menu_query.py` confirming exact 2-query catalog loading). |
| **A.2 Unneeded Fields** | Catalog queries defer heavy text/image columns where unnecessary, utilizing `.only("id", "category_id", "name", "description", "price", "prep_minutes", "offer_percent", "image", "is_available")`. | Verified via `available_menu()` unit test assertions. |
| **A.3 Pagination / Slicing** | Agent dashboards slice hot lists (`[:50]`) and Admin listings enforce `list_per_page = 50` to prevent unbounded memory consumption. | Verified across `views_agent.py` and `admin.py`. |
| **A.4 Caching Layer** | Implemented `get_cached_menu()` backed by Django's cache subsystem (`RedisCache` with fallback) and hooked into model `save()` / `delete()` methods on `Category` and `MenuItem` via `invalidate_menu_cache()`. | Verified graceful degradation if cache store is unreachable. |
| **A.5 Static Compression** | Images uploaded to `MenuItem` are downscaled to 1024px and compressed in-place (`compress_image()`) to optimize client payload size. | Verified via `apps/menu/services.py`. |
| **A.6 Database Indexes** | Composite indexes created for hot query patterns: `Order` (`status`, `created_at`), (`agent`, `status`), (`status`, `updated_at`); `MenuItem` (`category`, `is_available`). | Verified in model `Meta.indexes` definitions. |
| **A.7 Financial Analytics** | Zero Python-loop aggregation; all revenue and order metrics computed in DB (`analytics/services.py`) using `status__in=SETTLED_STATUSES` (`("PAID",)`). | Verified via `test_settlement_analytics.py`. |

---

## 3. Security Audit (OWASP / Enterprise Compliance)

| Security Domain | Defense Layer & Verification | Status |
| :--- | :--- | :--- |
| **B.1 Authentication & Roles** | Strict role separation via custom `@role_required` decorator. Delivery Agents log in via `RoleLoginView` (`/login/`) without requiring `is_staff` or Django Admin permissions. | Passed (`test_role_login.py`, `test_role_redirect.py`). |
| **B.2 IDOR Defenses** | Table QR orders require valid `qr_token` (no sequential IDs). Customer delivery tracking requires cryptographic signed cookie verification (`_TRACKING_SALT`). Agent endpoints scope strict ownership (`order.agent == request.user`). | Passed (`test_agent_scope.py`, `test_tracking.py`). |
| **B.3 Input Validation** | All order mutations enforce business validation before commit. Messaging escapes user inputs and enforces non-empty payload rules. | Passed (`test_messaging.py`). |
| **B.4 State Integrity** | Status transitions reject illegal jumps (`403 Forbidden` on skipping workflow steps) and maintain atomic transactions (`transaction.atomic`). | Passed (`test_state_machine.py`). |
| **B.5 Rate Limiting** | Endpoints protected with `django-ratelimit` (`checkout`, `messaging`, `dine_in_order`) preventing abuse and brute-force flooding. | Passed (`test_ratelimits.py`). |
| **B.6 Content Security Policy** | Enforced strict CSP headers (`django-csp`). Zero inline script blocks in HTML templates; all interactive components loaded from static scripts (`order-tracker.js`, `table-status.js`) reading CSP-safe JSON script blocks. | Passed (`test_views_customer.py`). |
| **B.7 Dependency Audit** | Upgraded virtual environment dependencies (`gitpython`, `idna`, `msgpack`, `pip`, `pyjwt`, `pytest`, `tornado`, `urllib3`) to current secure versions. | Passed (`pip-audit` reports 0 known vulnerabilities). |
| **B.8 Deployment Readiness** | Django system check verified (`python manage.py check --deploy`). | Passed (`0 issues identified`). |

---

## 4. Local & Production Hosting Instructions

### Local Host Development (`localhost:8000`)
To run the platform locally on your machine:
1. **Activate Virtual Environment**:
   ```powershell
   .\.venv\Scripts\activate
   ```
2. **Apply Database Migrations**:
   ```powershell
   python manage.py migrate
   ```
3. **Start Development Server**:
   ```powershell
   python manage.py runserver 127.0.0.1:8000
   ```
4. **Access Front Doors**:
   - **Front-Door Role Login (Admin, Agents & Customers)**: `http://127.0.0.1:8000/accounts/login/` (redirects each role to its home: ADMIN → `/backoffice/orders/dashboard/`, AGENT → `/agent/`, CUSTOMER → `/order/menu/`)
   - **Admin Operational Dashboard**: `http://127.0.0.1:8000/backoffice/orders/dashboard/`
   - **Django Admin (fallback CRUD)**: `http://127.0.0.1:8000/backoffice/`
   - **Delivery Menu (guest)**: `http://127.0.0.1:8000/order/menu/`
   - **Dine-in (guest, QR)**: `http://127.0.0.1:8000/t/<qr_token>/`

### Production Deployment Notes
When deploying to a staging or production server:
- Set `DEBUG = False` and configure a secret `SECRET_KEY` via environment variables (`.env`).
- Enable HSTS and Secure Cookies: `SECURE_SSL_REDIRECT = True`, `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`.
- Run ASGI application via `daphne` or `uvicorn` with an external Redis broker configured in `CHANNEL_LAYERS`.

---

## 5. Known Follow-Ups & Future Roadmap
- **Payment Gateway Integration**: Currently, checkout creates orders in `PLACED` status immediately. Future phases should attach webhook handlers for Stripe/Razorpay before order confirmation.
- **Push Notifications**: Integrate Web Push API / FCM for offline background alerts to Delivery Agents when new orders are dispatched.
- **Automated Agent Dispatch Algorithm**: Replace manual backoffice assignment (`assign_order`) with round-robin or geo-proximity auto-dispatching.
