# Smart Inventory Management & Stock Alert System

A web application for small shops to **sell at the counter, keep stock accurate, and get an alert before any product runs out**.

**Course:** CSE 0613316 — Software Project Design and Development, UITS
**Developed by:** Group 9

**Live demo:** https://hasan1083.pythonanywhere.com  (login: `admin` / `admin123`, sample data only)

> The repository includes the database (`db.sqlite3`) with sample products and sales, so the project runs with real data right after download. If it does not run on your computer, see the [screenshots](#screenshots) below.

---

## Main features

- **Stock alerts (core feature):** every product has its own low-stock level; low products get a red badge and appear on the dashboard.
- **Reorder plan:** suggests how many units to buy, based on how fast each product sells.
- **Point of Sale:** barcode scan or search, cart, customer, discount, Cash / Card / bKash-Nagad, printable receipt.
- **Automatic stock update:** every sale, stock-in and adjustment changes stock and is saved in a stock history (ledger). Stock can never go below zero.
- **Real profit:** uses the buy price at the time of each sale.
- **Reports:** any period, profit and margin, top products, categories, dead stock; export to CSV or send to Telegram.
- Products, categories, suppliers, customers, staff accounts, 3 themes, global search (Ctrl+K).
- Works **offline** — no internet needed.

## Tech stack

| Part | Technology |
|---|---|
| Backend | Python, Django 5.2 LTS |
| Database | SQLite (Django ORM) |
| Frontend | HTML, CSS, JavaScript, Chart.js, Bootstrap Icons |
| Testing | Django test framework (72 tests), coverage.py, Playwright (10 browser tests) |
| CI | GitHub Actions (runs all tests on every push) |
| Hosting | PythonAnywhere |

---

## How to run

**Requirement:** Python 3.10 or newer.

### 1. Download
Click **Code → Download ZIP** on this page and unzip it, or:
```bash
git clone <this repository's URL>
cd smart-inventory
```

### 2. Create a virtual environment and install Django

**Windows**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run
```bash
python manage.py migrate
python manage.py runserver
```
Open **http://127.0.0.1:8000** in the browser.

### 4. Login
| Username | Password |
|---|---|
| `admin` | `admin123` |

> If the login does not work, run `python manage.py createsu` to create the admin account again.

### Run the tests (optional)
```bash
python manage.py test inventory
```
Browser system tests (needs Node.js; start the server first):
```bash
npm install playwright
node e2e/system_tests.js
```

---

## Project structure

```
smart-inventory/
├── manage.py
├── db.sqlite3            # database with sample data
├── requirements.txt
├── smartinventory/       # settings and main URLs
├── inventory/            # main app
│   ├── models.py         # database tables
│   ├── services.py       # stock logic: checkout, stock in, adjustment
│   ├── reports.py        # profit, reorder plan, dead stock
│   ├── views/            # pages: dashboard, pos, stock, products, reports …
│   └── tests.py, tests_lab.py
├── templates/            # HTML pages
├── static/               # CSS, JavaScript, Chart.js
└── screenshots/          # screenshots used below
```

---

## Screenshots

### Login
![Login](screenshots/01-login.jpg)

### Dashboard
![Dashboard](screenshots/02-dashboard.jpg)

### Point of Sale
![POS cart](screenshots/03-pos-cart.jpg)

![Sale completed](screenshots/04-pos-done.jpg)

### Receipt
<img src="screenshots/05-receipt.jpg" alt="Receipt" width="320">

### Products
![Products](screenshots/06-products.jpg)

### Low-stock alert (core feature)
![Low stock](screenshots/07-lowstock.jpg)

### Product detail and stock history
![Product detail](screenshots/08-detail.jpg)

### Stock In
![Stock In](screenshots/09-stock.jpg)

### Stock adjustment
![Adjustment](screenshots/10-stock-adjust.jpg)

### Stock history (ledger)
![Stock history](screenshots/11-stock-history.jpg)

### Sales
![Sales](screenshots/12-sales.jpg)

### Reports
![Reports](screenshots/13-reports.jpg)

![Top products and categories](screenshots/14-reports-lower.jpg)

### Reorder plan and dead stock
![Reorder plan](screenshots/15-reports-reorder.jpg)

### Customers
![Customers](screenshots/16-customers.jpg)

### Suppliers
![Suppliers](screenshots/17-suppliers.jpg)

### Settings
![Settings](screenshots/18-settings.jpg)

### Global search (Ctrl+K)
![Search](screenshots/19-palette.jpg)

### Dark theme
![Dark theme](screenshots/20-dashboard-dark.jpg)
