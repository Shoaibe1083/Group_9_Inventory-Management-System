SMART INVENTORY MANAGEMENT & STOCK ALERT SYSTEM
Django + SQLite  |  Login: admin / admin123
================================================

HOW TO RUN — MAC
----------------
Open this folder in VS Code, open the terminal (Ctrl + `), then run one by one:

  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  python manage.py migrate
  python manage.py runserver

Open in browser:  http://127.0.0.1:8000


HOW TO RUN — WINDOWS (university PC)
------------------------------------
  python -m venv venv
  venv\Scripts\activate
  pip install -r requirements.txt
  python manage.py migrate
  python manage.py runserver


NEXT TIME (after the first setup)
---------------------------------
  Mac:      source venv/bin/activate   then   python manage.py runserver
  Windows:  venv\Scripts\activate      then   python manage.py runserver


USEFUL EXTRA COMMANDS
---------------------
  python manage.py createsu   -> creates admin / admin123 if it is missing
  python manage.py seed       -> fills an EMPTY database with sample products, customers,
                                 suppliers and 60 days of sales / purchases / adjustments.
  python manage.py import_catalog   -> adds 150 real Shwapno products (15 categories,
                                       shelf prices from shwapno.com, 2 Nov 2026) to the
                                       database; skips names that already exist.
                                       Add --demo-sales 30 to also simulate 30 days of sales.
  python manage.py test inventory   -> runs the automated tests

Themes: Navy (default), Midnight (dark) and Sage. Switch from the palette button in
the top bar or Settings -> Appearance. Press Ctrl+K (Cmd+K on Mac) anywhere to search
products, customers and pages.

Sign in with the username OR the email address. Change your email/password in
Settings -> My account. Admins can add more admin/staff accounts in
Settings -> Admins & staff.

No internet needed: charts, icons and fonts are bundled inside static/vendor.
(Only "Send to Telegram" needs internet.)
If an old "venv" folder came from another computer, delete it and create a new one.


FEATURES
--------
  1. Dashboard — today's sales, profit, transactions (vs yesterday), stock alerts,
     14-day trend chart, best sellers, recent sales, stock value, quick actions
  2. Point of Sale — USB barcode scanner box, name/SKU search, quick-pick buttons,
     cart with +/- quantity, customer lookup by phone/name (new customers saved
     automatically), discount, Cash / Card / bKash-Nagad, change calculator,
     printable receipt. Shortcuts: F2 scan, F3 search, F4 customer, F9 complete
  3. Sales — every receipt, filter by period / payment / customer / product, CSV export
  4. Stock — Stock In (multi-product purchase from a supplier, updates buy price),
     Adjustment (stock count, damaged, expired, lost, customer return, other),
     History (full movement ledger with filters and CSV export)
  5. Reports — Today / 7 / 30 / 90 days / custom range; sales, profit, margin,
     transactions vs previous period; daily sales & profit chart; top products;
     sales by category; payment methods; reorder suggestions; dead stock;
     CSV export; send summary to Telegram
  6. Products — SKU + barcode (auto-generated if empty), buy/sell price, margin,
     low-stock alerts, movement history per product, CSV export
  7. Customers, Suppliers, Categories
  8. Settings — My account (name, username, email, password), Store (shop name,
     address, phone, receipt footer, alert defaults), Admins & staff (add, edit,
     reset password, disable, delete; staff cannot open admin settings), Telegram


DATABASE TABLES (SQLite: db.sqlite3)
------------------------------------
  Category  (1) ---- (N) Product
  Supplier  (1) ---- (N) Product
  Customer  (1) ---- (N) Order          (one POS checkout / receipt)
  Order     (1) ---- (N) Sale           (one product line of a receipt)
  Product   (1) ---- (N) StockMovement  (ledger: every stock change)
  Product   (1) ---- (N) StockIn        (purchase records, per supplier)
  StoreSettings (single row)
  + Django's built-in User table for login
