# Developer Guide — FreshMart Supermarket Platform

A comprehensive supermarket and grocery ordering platform: **in-store pickup** (counter QR tokens), **home delivery**
(customer ordering & guest checkout), an **agent** delivery app, and a bespoke **admin** back office —
all on Django + HTMX/Alpine, with real-time updates over Django Channels.

This guide is the map. It tells you what each app does, how a request flows, and —
most importantly — **where to change each common thing** and **which knobs to turn**.

---

## 1. Architecture at a glance

```
Browser (HTMX + Alpine, no SPA)                WebSocket (status feed)
        │  HTTP                                        │
        ▼                                              ▼
config/urls.py ── role-scoped URLconfs        config/asgi.py ── realtime/routing.py
        │                                              │
        ▼                                              ▼
apps/<app>/views*.py   (THIN: parse → call service → render)
        │
        ▼
apps/<app>/services.py (FAT: all business logic, pricing, transitions)
        │
        ▼
apps/<app>/models.py   (DUMB: data + validation only)  ── apps/orders/state.py (workflow table)
```

**The golden rule:** business logic lives in `services.py`; views are thin; models
hold data + validation; templates hold no arithmetic. If you find logic creeping into
a view or template, move it to a service.

### App responsibilities

| App | Responsibility |
|-----|----------------|
| `apps.accounts` | Custom `User` (role: ADMIN/AGENT/CUSTOMER), `AgentProfile` (availability); role login; admin agent/user management (`views_admin.py`). |
| `apps.core` | Cross-cutting primitives: `permissions.py` (RBAC `role_required`), `ratelimits.py` (abuse limits), health check. |
| `apps.menu` | `Category`/`MenuItem`, pricing (`effective_price`), Redis-cached catalog, image compression, admin CRUD. |
| `apps.orders` | The heart: `Order`/`OrderItem`/`OrderEvent`/`Message`; **`services.py`** (create/transition/assign/message) and **`state.py`** (the transition table). Customer, agent, and admin views. |
| `apps.tables` | `Table` (opaque QR token), `TableSession` (one open tab per table); dine-in flow + admin CRUD + QR PNG. |
| `apps.realtime` | Channels consumers + `broadcast()` helper; pushes `order.status` / messages to dashboards, agents, and tracking pages. |
| `apps.analytics` | Settlement analytics, **100% DB-side aggregation** (no Python summing). |

---

## 2. Request & real-time flow

**HTTP (example: dine-in "+ Add"):** `POST /t/<token>/cart/add`
→ `tables.views.cart_add` (thin) → updates the server-side session cart →
renders `tables/partials/cart_bar.html` → HTMX swaps it in. CSRF rides on the
body-level `hx-headers` in the page's base template.

**Placing an order:** `tables.views.place_order` → `orders.services.create_order`
(snapshots `effective_price` server-side, writes the initial `OrderEvent`, then
`broadcast()`s to the admin dashboard).

**Status change:** only ever through `orders.services.transition(order, to_status, actor)`,
which consults `orders/state.py` (`can_transition`), writes an append-only `OrderEvent`,
and broadcasts to the order/agent/table/admin channels.

**Real-time:** `apps/realtime/broadcast.py` sends a tiny JSON envelope to a Channels
group; `static/js/*.js` (external, CSP-safe) receive it and refresh the affected card
via HTMX. The socket is a best-effort notifier — the DB row is the source of truth.

---

## 3. Where to change each common thing

| I want to… | Edit | Notes |
|------------|------|-------|
| Add a menu-item field | `apps/menu/models.py` → `makemigrations` → add to `MenuItemForm.Meta.fields` (`apps/menu/forms.py`) → show it in `templates/menu/admin/dashboard.html` | Pricing lives in `MenuItem.effective_price` — don't duplicate it. |
| Add / change an order status | `apps/orders/models.py:OrderStatus` (the code+label) **and** `apps/orders/state.py:TRANSITIONS` (who may move where) | These two are the ONLY places. Run the state-machine tests. |
| Change who can do a transition | `apps/orders/state.py:TRANSITIONS` only | Pure dict, no logic to rewrite. |
| Add a new role | `apps/accounts/models.py:Role`, then `role_required(...)` guards + `RoleLoginView.get_success_url` | |
| Change a rate limit | `apps/core/ratelimits.py` | Named wrappers; one line each. |
| Change the delivery radius | `apps/orders/services.py:is_within_delivery_radius` (`limit_km` default) | |
| Change what counts as revenue | `apps/analytics/services.py:SETTLED_STATUSES` | One tuple; everything else follows. |
| Change list page sizes | admin `list_per_page` (each `admin.py`); board/agent/session slices (see §5) | |
| Add an admin page to the nav | `templates/partials/admin_nav.html` | Every admin page includes this one partial. |

---

## 4. Tunable knobs (the finetuning surface)

Everything a human is likely to tune lives in one obvious, documented place:

| Knob | Location | Default |
|------|----------|---------|
| Order workflow (transitions) | `apps/orders/state.py` → `TRANSITIONS` | see file |
| Revenue definition | `apps/analytics/services.py` → `SETTLED_STATUSES` | `("PAID",)` |
| Rate limits (login/checkout/dine-in/messaging) | `apps/core/ratelimits.py` | 5/m, 20/m, 20/m, 10/m |
| Delivery radius | `apps/orders/services.py` → `is_within_delivery_radius(limit_km=3.0)` | 3 km |
| Menu cache key / TTL | `apps/menu/services.py` → `MENU_CACHE_KEY`, `cache.set(..., timeout=3600)` | 1 h |
| Admin URL prefix | `.env` → `ADMIN_URL` | `backoffice/` |
| DB persistent-connection age | `settings/base.py` → `CONN_MAX_AGE` (prod override `CONN_MAX_AGE` env) | 60 s |
| List bounds | board `[:100]`, agent `[:50]`, sessions `[:100]`, admin `list_per_page=50` | see §5 |
| ASGI workers / memory | deploy command (`uvicorn --workers 2 --preload`) — see §5 | 2 |

---

## 5. RAM & performance levers (2-vCPU / 2 GB box)

The app is tuned for a small VPS. The concrete levers already in place:

- **DB-side analytics only** — `apps/analytics/services.py` never pulls Order rows into
  Python; all sums/counts are `aggregate()`/`annotate()`. AOV guards divide-by-zero.
- **No N+1** — hot views use `select_related` (FKs) + `prefetch_related` (reverse/M2M).
  `apps/orders/tests/test_dashboard_queries.py` pins the board to a **constant** query
  count regardless of order volume.
- **Bounded lists** — operational board `[:100]`, agent dashboard `[:50]`, sessions
  `[:100]`, Django-admin `list_per_page = 50`. No unbounded `.all()` is rendered.
- **Cached catalog** — the menu is served from the Redis cache (`get_cached_menu`),
  invalidated on `MenuItem`/`Category` save; degrades gracefully if Redis is down.
- **Lazy Pillow** — `apps/menu/services.py` imports Pillow **inside** `compress_image`,
  so idle web workers don't carry the ~15 MB imaging working set; it loads only on the
  rare admin image upload (already downscaled to 1024px, buffers freed promptly).
- **Cached template loader in prod** — `settings/prod.py` wraps the loaders in
  `cached.Loader`, so templates are parsed once per process (not per render).
- **Persistent DB connections** — `CONN_MAX_AGE=60` avoids per-request reconnects.
- **Redis eviction** — configure `maxmemory` + `allkeys-lru` on the Redis box so the
  cache/channel layer never grows without bound.

**Deploy sizing:** pin ASGI workers to the core count — `uvicorn config.asgi:application
--workers 2 --preload`. `--preload` imports the app once in the parent so forked workers
share memory copy-on-write. Estimated steady-state per worker ≈ **90–120 MB** (Django +
templates + one DB connection; Pillow excluded until an upload). Two workers + Redis fit
comfortably under 2 GB.

---

## 6. Security model (don't regress these)

- **RBAC** on every admin endpoint via `role_required("ADMIN")`; wrong role → 403.
- **IDOR-safe** object access: guest order tracking requires the signed
  `delv_token_<pk>` cookie (`orders/views_customer.py:_may_access_order`); agents are
  scoped with `get_object_or_404(Order, pk=pk, agent=request.user)`. Never fetch by pk
  alone for a protected object.
- **Opaque QR tokens** — the QR encodes `Table.qr_token`, never the id/number.
- **Passwords always hashed** (UserCreationForm / `set_password`); hashes never rendered.
- **CSP** with **no `'unsafe-inline'` on `script-src`** — all JS is external `{% static %}`;
  templates are auto-escaped (no `|safe` on user data).
- **Rate limits** on login/checkout/dine-in/messaging (`core/ratelimits.py`).
- **No SSRF** — `maps_url` is only *built and rendered* as a link; the server never fetches it.
- **Admin off the default URL** (`ADMIN_URL=backoffice/`).

---

## 7. Running it

**Dev (SQLite, no Docker/Redis needed):**
```bash
# .env: DJANGO_SETTINGS_MODULE=config.settings.dev, DATABASE_URL=sqlite:///db.sqlite3
python manage.py migrate
python manage.py createsuperuser        # role defaults to CUSTOMER; set role=ADMIN + is_staff in admin
python manage.py runserver
```
Dev uses in-memory cache + channel layer and disables rate limiting (`settings/dev.py`).

**Prod (Postgres + Redis):** `DJANGO_SETTINGS_MODULE=config.settings.prod`, real
`DATABASE_URL` (postgres) and `REDIS_URL`; serve with `uvicorn ... --workers 2 --preload`.
Security headers (HSTS, secure cookies, SSL redirect) switch on automatically.

**Verification suite:**
```bash
python -m pytest -q         # full test suite (incl. smoke routes + query-count guards)
python -m ruff check .      # lint/format
python manage.py check
```

---

## 8. Conventions

- **Imports** ordered stdlib → third-party → django → local.
- **Structure** is identical across apps: `models / services / views* / urls* / admin / forms / tests`.
- **Docstrings explain WHY**, type hints on public signatures.
- **Money is `Decimal`** everywhere — never `float`.
- Add tests next to the app (`apps/<app>/tests/`); route-level smoke tests live in
  `apps/core/tests/test_smoke_routes.py` and must stay green.
