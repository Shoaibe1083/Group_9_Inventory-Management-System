from .alerts import alert_export, alert_list
from .analytics import report, report_export, report_telegram
from .dashboard import dashboard
from .people import (
    category_delete, category_list, category_update,
    customer_create, customer_delete, customer_detail, customer_list, customer_update,
    supplier_create, supplier_delete, supplier_list, supplier_update,
)
from .pos import api_customer_search, order_list, order_receipt, pos, pos_checkout, sale_receipt, sales_export
from .products import (
    api_product_lookup, api_product_search, product_create, product_delete, product_detail,
    product_list, product_update, products_export, stock_in, stock_out,
)
from .settings_page import (
    settings_page, settings_telegram_test, settings_user_create, settings_user_delete, settings_user_edit,
)
from .stock import stock, stock_adjust, stock_history_export, stock_receive
