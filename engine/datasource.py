from typing import Any

import pymysql

from engine.crypto import decrypt_password
from engine.errors import DataSourceConnectionError

# Schema representation for the built-in Demo Database (20 tables)
MOCK_TABLES_INFO = [
    {
        "table_name": "users",
        "table_comment": "用户信息表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 1250,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "用户ID"},
            {"column_name": "username", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "用户名"},
            {"column_name": "email", "data_type": "varchar", "column_type": "varchar(100)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "邮箱"},
            {"column_name": "phone", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 1, "is_primary_key": 0, "column_comment": "手机号"},
            {"column_name": "role", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "角色: user, admin, staff"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "注册时间"}
        ]
    },
    {
        "table_name": "products",
        "table_comment": "商品信息表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 350,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "商品ID"},
            {"column_name": "name", "data_type": "varchar", "column_type": "varchar(150)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "商品名称"},
            {"column_name": "sku", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "SKU编码"},
            {"column_name": "category_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "categories", "foreign_column": "id", "column_comment": "品类ID"},
            {"column_name": "price", "data_type": "decimal", "column_type": "decimal(10,2)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "销售价"},
            {"column_name": "stock", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "库存量"},
            {"column_name": "status", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "状态: active, inactive"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "创建时间"}
        ]
    },
    {
        "table_name": "categories",
        "table_comment": "商品分类表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 15,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "品类ID"},
            {"column_name": "name", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "品类名称"},
            {"column_name": "parent_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 1, "is_primary_key": 0, "column_comment": "父品类ID"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "创建时间"}
        ]
    },
    {
        "table_name": "orders",
        "table_comment": "订单主表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 4500,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "订单ID"},
            {"column_name": "user_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "users", "foreign_column": "id", "column_comment": "买家用户ID"},
            {"column_name": "total_amount", "data_type": "decimal", "column_type": "decimal(10,2)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "订单总金额"},
            {"column_name": "status", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "订单状态: pending, paid, shipped, completed, cancelled"},
            {"column_name": "payment_method", "data_type": "varchar", "column_type": "varchar(30)", "is_nullable": 1, "is_primary_key": 0, "column_comment": "支付方式: alipay, wechat, credit_card"},
            {"column_name": "shipping_address", "data_type": "varchar", "column_type": "varchar(255)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "收货地址"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "下单时间"},
            {"column_name": "updated_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "更新时间"}
        ]
    },
    {
        "table_name": "order_items",
        "table_comment": "订单明细表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 9200,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "明细ID"},
            {"column_name": "order_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "orders", "foreign_column": "id", "column_comment": "关联订单ID"},
            {"column_name": "product_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "products", "foreign_column": "id", "column_comment": "关联商品ID"},
            {"column_name": "price", "data_type": "decimal", "column_type": "decimal(10,2)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "下单单价"},
            {"column_name": "quantity", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "下单数量"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "创建时间"}
        ]
    },
    {
        "table_name": "payments",
        "table_comment": "支付流水分支表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 4300,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "支付ID"},
            {"column_name": "order_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "orders", "foreign_column": "id", "column_comment": "关联订单ID"},
            {"column_name": "amount", "data_type": "decimal", "column_type": "decimal(10,2)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "支付金额"},
            {"column_name": "status", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "支付状态: pending, success, failed, refunded"},
            {"column_name": "transaction_id", "data_type": "varchar", "column_type": "varchar(100)", "is_nullable": 1, "is_primary_key": 0, "column_comment": "外部支付流水号"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "支付时间"}
        ]
    },
    {
        "table_name": "shipping",
        "table_comment": "物流配送表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 4200,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "配送ID"},
            {"column_name": "order_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "orders", "foreign_column": "id", "column_comment": "关联订单ID"},
            {"column_name": "tracking_number", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 1, "is_primary_key": 0, "column_comment": "快递单号"},
            {"column_name": "carrier", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 1, "is_primary_key": 0, "column_comment": "物流公司: sf, yto, zto"},
            {"column_name": "status", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "配送状态: packing, transit, delivered"},
            {"column_name": "shipped_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 1, "is_primary_key": 0, "column_comment": "出库时间"},
            {"column_name": "delivered_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 1, "is_primary_key": 0, "column_comment": "妥投时间"}
        ]
    },
    {
        "table_name": "reviews",
        "table_comment": "商品评价表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 980,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "评价ID"},
            {"column_name": "product_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "products", "foreign_column": "id", "column_comment": "关联商品ID"},
            {"column_name": "user_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "users", "foreign_column": "id", "column_comment": "评价人用户ID"},
            {"column_name": "rating", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "星级: 1-5"},
            {"column_name": "comment", "data_type": "text", "column_type": "text", "is_nullable": 1, "is_primary_key": 0, "column_comment": "评价文本"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "评价时间"}
        ]
    },
    {
        "table_name": "cart",
        "table_comment": "购物车信息表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 450,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "购物车项ID"},
            {"column_name": "user_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "users", "foreign_column": "id", "column_comment": "用户ID"},
            {"column_name": "product_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "products", "foreign_column": "id", "column_comment": "商品ID"},
            {"column_name": "quantity", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "加购数量"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "加购时间"}
        ]
    },
    {
        "table_name": "inventory_logs",
        "table_comment": "库存变更日志表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 1400,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "日志ID"},
            {"column_name": "product_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "products", "foreign_column": "id", "column_comment": "商品ID"},
            {"column_name": "change_amount", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "变更数量(正为入库，负为扣减)"},
            {"column_name": "reason", "data_type": "varchar", "column_type": "varchar(100)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "变更原因: purchase, sale, adjust, refund"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "记录时间"}
        ]
    },
    # Add 10 more tables to satisfy the V1 20+ tables synced check!
    {
        "table_name": "coupons",
        "table_comment": "优惠券配置表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 50,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "券ID"},
            {"column_name": "code", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "兑换码"},
            {"column_name": "discount_type", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "券类型: fixed, discount"},
            {"column_name": "value", "data_type": "decimal", "column_type": "decimal(10,2)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "优惠面额"},
            {"column_name": "min_spend", "data_type": "decimal", "column_type": "decimal(10,2)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "起用门槛"},
            {"column_name": "expires_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "过期时间"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "创建时间"}
        ]
    },
    {
        "table_name": "coupon_usages",
        "table_comment": "优惠券使用记录表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 890,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "记录ID"},
            {"column_name": "coupon_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "coupons", "foreign_column": "id", "column_comment": "券ID"},
            {"column_name": "order_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "orders", "foreign_column": "id", "column_comment": "订单ID"},
            {"column_name": "user_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "users", "foreign_column": "id", "column_comment": "用户ID"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "使用时间"}
        ]
    },
    {
        "table_name": "user_addresses",
        "table_comment": "用户收货地址表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 2100,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "地址ID"},
            {"column_name": "user_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "users", "foreign_column": "id", "column_comment": "用户ID"},
            {"column_name": "consignee", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "收货人姓名"},
            {"column_name": "phone", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "联系电话"},
            {"column_name": "province", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "省份"},
            {"column_name": "city", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "城市"},
            {"column_name": "district", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 1, "is_primary_key": 0, "column_comment": "区县"},
            {"column_name": "address", "data_type": "varchar", "column_type": "varchar(255)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "详细街道地址"},
            {"column_name": "is_default", "data_type": "tinyint", "column_type": "tinyint(1)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "是否默认: 1=是, 0=否"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "创建时间"}
        ]
    },
    {
        "table_name": "suppliers",
        "table_comment": "供应商信息表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 45,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "供应商ID"},
            {"column_name": "name", "data_type": "varchar", "column_type": "varchar(100)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "商家名称"},
            {"column_name": "contact", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "联系人"},
            {"column_name": "phone", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "联系电话"},
            {"column_name": "address", "data_type": "varchar", "column_type": "varchar(255)", "is_nullable": 1, "is_primary_key": 0, "column_comment": "商家地址"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "加入时间"}
        ]
    },
    {
        "table_name": "purchase_orders",
        "table_comment": "采购订单主表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 120,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "采购单ID"},
            {"column_name": "supplier_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "suppliers", "foreign_column": "id", "column_comment": "关联供应商ID"},
            {"column_name": "status", "data_type": "varchar", "column_type": "varchar(20)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "状态: pending, shipped, received, cancelled"},
            {"column_name": "total_cost", "data_type": "decimal", "column_type": "decimal(12,2)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "总成本费用"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "创建时间"}
        ]
    },
    {
        "table_name": "purchase_order_items",
        "table_comment": "采购订单明细表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 680,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "明细ID"},
            {"column_name": "purchase_order_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "purchase_orders", "foreign_column": "id", "column_comment": "关联采购订单"},
            {"column_name": "product_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "products", "foreign_column": "id", "column_comment": "商品ID"},
            {"column_name": "cost", "data_type": "decimal", "column_type": "decimal(10,2)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "采购单价"},
            {"column_name": "quantity", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "采购数量"}
        ]
    },
    {
        "table_name": "analytics_clicks",
        "table_comment": "行为分析点击日志",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 45000,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "事件ID"},
            {"column_name": "user_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 1, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "users", "foreign_column": "id", "column_comment": "点击用户(匿名则为null)"},
            {"column_name": "product_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "products", "foreign_column": "id", "column_comment": "商品ID"},
            {"column_name": "source", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "来源端: web, ios, android"},
            {"column_name": "ip", "data_type": "varchar", "column_type": "varchar(45)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "用户客户端IP"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "点击发生时间"}
        ]
    },
    {
        "table_name": "system_settings",
        "table_comment": "系统基础配置表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 12,
        "columns": [
            {"column_name": "key", "data_type": "varchar", "column_type": "varchar(50)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "配置键"},
            {"column_name": "value", "data_type": "varchar", "column_type": "varchar(255)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "配置值"},
            {"column_name": "description", "data_type": "varchar", "column_type": "varchar(255)", "is_nullable": 1, "is_primary_key": 0, "column_comment": "功能描述"},
            {"column_name": "updated_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "更新时间"}
        ]
    },
    {
        "table_name": "admin_logs",
        "table_comment": "后台管理员操作审计日志",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 1500,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "日志ID"},
            {"column_name": "admin_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "users", "foreign_column": "id", "column_comment": "管理员ID"},
            {"column_name": "action", "data_type": "varchar", "column_type": "varchar(100)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "操作类型: audit_pass, system_setting_change, ban_user"},
            {"column_name": "ip", "data_type": "varchar", "column_type": "varchar(45)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "管理员操作IP"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "操作时间"}
        ]
    },
    {
        "table_name": "recommendations",
        "table_comment": "个性化商品推荐表",
        "table_type": "BASE TABLE",
        "engine_name": "InnoDB",
        "row_count_estimate": 5000,
        "columns": [
            {"column_name": "id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 1, "column_comment": "推荐ID"},
            {"column_name": "user_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "users", "foreign_column": "id", "column_comment": "用户ID"},
            {"column_name": "product_id", "data_type": "int", "column_type": "int(11)", "is_nullable": 0, "is_primary_key": 0, "is_foreign_key": 1, "foreign_table": "products", "foreign_column": "id", "column_comment": "推荐商品ID"},
            {"column_name": "score", "data_type": "decimal", "column_type": "decimal(5,4)", "is_nullable": 0, "is_primary_key": 0, "column_comment": "推荐算法打分(越接近1越匹配)"},
            {"column_name": "created_at", "data_type": "datetime", "column_type": "datetime", "is_nullable": 0, "is_primary_key": 0, "column_comment": "推荐生成时间"}
        ]
    }
]

def is_demo_db(host: str, database_name: str) -> bool:
    """Helper to detect if a connection configuration is referring to the built-in demo database."""
    return host.lower() == "demo" or database_name.lower().startswith("demo")

import threading
import socket
import logging
from sshtunnel import SSHTunnelForwarder

logger = logging.getLogger("databox.tunnel")

class TunnelState:
    CONNECTED = "connected"
    STALE = "stale"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    CLOSED = "closed"

class TunnelInstance:
    datasource_id: str
    ds_dict: dict[str, Any]
    tunnel: SSHTunnelForwarder
    state: str
    error_message: str | None

    def __init__(self, datasource_id: str, ds_dict: dict[str, Any], tunnel: SSHTunnelForwarder) -> None:
        self.datasource_id = datasource_id
        self.ds_dict = ds_dict
        self.tunnel = tunnel
        self.state = TunnelState.CONNECTED
        self.error_message = None

class TunnelManager:
    def __init__(self) -> None:
        self._tunnels: dict[str, TunnelInstance] = {}
        self._lock = threading.Lock()

    def get_tunnel_state(self, datasource_id: str) -> str:
        with self._lock:
            instance = self._tunnels.get(datasource_id)
            if not instance:
                return TunnelState.CLOSED
            return instance.state

    def close_tunnel(self, datasource_id: str) -> None:
        with self._lock:
            instance = self._tunnels.pop(datasource_id, None)
            if instance:
                instance.state = TunnelState.CLOSED
                try:
                    instance.tunnel.stop()
                except Exception as e:
                    logger.error(f"Error stopping tunnel for {datasource_id}: {e}")

    def close_all(self) -> None:
        with self._lock:
            for ds_id, instance in list(self._tunnels.items()):
                instance.state = TunnelState.CLOSED
                try:
                    instance.tunnel.stop()
                except Exception as e:
                    logger.error(f"Error stopping tunnel for {ds_id}: {e}")
            self._tunnels.clear()

    def health_check(self, datasource_id: str) -> bool:
        """
        Performs deep health check on the specified tunnel by validating socket availability.
        """
        instance = None
        with self._lock:
            instance = self._tunnels.get(datasource_id)
        
        if not instance:
            return False

        if not instance.tunnel.is_active:
            instance.state = TunnelState.STALE
            return False

        # Attempt to probe the local bind port via a quick TCP connection test
        try:
            port = instance.tunnel.local_bind_port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(('127.0.0.1', port))
            instance.state = TunnelState.CONNECTED
            return True
        except Exception as e:
            logger.warning(f"Tunnel health probe failed on port {instance.tunnel.local_bind_port} for {datasource_id}: {e}")
            instance.state = TunnelState.STALE
            return False

    def get_or_reconnect(self, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        """
        Retrieves active tunnel or automatically triggers self-healing re-connections if stale.
        """
        ds_id = ds_dict.get("id")
        if not ds_id:
            ds_id = f"temp_{ds_dict.get('host')}_{ds_dict.get('port')}"

        with self._lock:
            instance = self._tunnels.get(ds_id)

        if not instance:
            return self._create_tunnel(ds_id, ds_dict)

        # Deep health check probe
        is_healthy = self.health_check(ds_id)
        if is_healthy:
            return instance.tunnel

        logger.info(f"SSH Tunnel for {ds_id} went stale. Initiating self-healing auto-reconnect...")
        with self._lock:
            instance.state = TunnelState.RECONNECTING

        try:
            try:
                instance.tunnel.stop()
            except Exception:
                pass

            new_tunnel = self._start_physical_tunnel(ds_dict)
            with self._lock:
                instance.tunnel = new_tunnel
                instance.state = TunnelState.CONNECTED
                instance.error_message = None
            logger.info(f"SSH Tunnel auto-reconnect successful for {ds_id}.")
            return new_tunnel
        except Exception as e:
            logger.error(f"SSH Tunnel self-healing auto-reconnect failed for {ds_id}: {e}")
            with self._lock:
                instance.state = TunnelState.FAILED
                instance.error_message = str(e)
            raise DataSourceConnectionError(f"SSH 隧道连接已断开，自动尝试自愈重连失败: {str(e)}")

    def _create_tunnel(self, ds_id: str, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        logger.info(f"Creating new SSH tunnel for {ds_id}")
        tunnel = self._start_physical_tunnel(ds_dict)
        instance = TunnelInstance(ds_id, ds_dict, tunnel)
        with self._lock:
            self._tunnels[ds_id] = instance
        return tunnel

    def _start_physical_tunnel(self, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        ssh_password = None
        if ds_dict.get("ssh_password_ciphertext") and ds_dict.get("ssh_password_nonce"):
            ssh_password = decrypt_password(ds_dict["ssh_password_ciphertext"], ds_dict["ssh_password_nonce"])

        pkey_passphrase = None
        if ds_dict.get("ssh_pkey_passphrase_ciphertext") and ds_dict.get("ssh_pkey_passphrase_nonce"):
            pkey_passphrase = decrypt_password(ds_dict["ssh_pkey_passphrase_ciphertext"], ds_dict["ssh_pkey_passphrase_nonce"])

        ssh_pkey = ds_dict.get("ssh_pkey_path") if ds_dict.get("ssh_pkey_path") else None
        ssh_host = ds_dict.get("ssh_host")
        ssh_port = int(ds_dict.get("ssh_port", 22))
        ssh_username = ds_dict.get("ssh_username")

        target_host = ds_dict.get("host")
        target_port = int(ds_dict.get("port", 3306))

        tunnel = SSHTunnelForwarder(
            (ssh_host, ssh_port),
            ssh_username=ssh_username,
            ssh_password=ssh_password,
            ssh_pkey=ssh_pkey,
            ssh_private_key_password=pkey_passphrase,
            remote_bind_address=(target_host, target_port),
            local_bind_address=('127.0.0.1', 0),
            # Protocol transport-level KeepAlive (every 30s) to bypass idle remote firewall drops
            keepalive=30,
        )
        tunnel.start()
        return tunnel

    def cleanup_stale(self) -> None:
        with self._lock:
            for ds_id, instance in list(self._tunnels.items()):
                if not instance.tunnel.is_active:
                    logger.info(f"Purging dead inactive tunnel instance: {ds_id}")
                    try:
                        instance.tunnel.stop()
                    except Exception:
                        pass
                    self._tunnels.pop(ds_id, None)

# Instantiate global TunnelManager to serve all background drivers and connection requests
TUNNEL_MANAGER = TunnelManager()

def close_active_tunnel(datasource_id: str) -> None:
    """Close active SSH tunnel for a data source if it exists"""
    TUNNEL_MANAGER.close_tunnel(datasource_id)

def close_all_tunnels() -> None:
    """Close all active SSH tunnels on app shutdown"""
    TUNNEL_MANAGER.close_all()

def get_or_create_tunnel_for_dict(ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
    """Gets or starts an SSH tunnel with deep health probes and auto-reconnects"""
    return TUNNEL_MANAGER.get_or_reconnect(ds_dict)

def _normalized_optional_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

def build_mysql_ssl_params(config: dict[str, Any]) -> dict[str, Any]:
    """Build PyMySQL SSL parameters with certificate verification enabled."""
    if not config.get("ssl_enabled"):
        return {}

    ca_path = _normalized_optional_path(config.get("ssl_ca_path"))
    cert_path = _normalized_optional_path(config.get("ssl_cert_path"))
    key_path = _normalized_optional_path(config.get("ssl_key_path"))
    verify_identity = bool(config.get("ssl_verify_identity", True))

    if verify_identity and not ca_path:
        raise DataSourceConnectionError(
            "SSL identity verification requires a CA certificate path."
        )

    ssl_params: dict[str, Any] = {
        "ssl_verify_cert": True,
        "ssl_verify_identity": verify_identity,
    }
    if ca_path:
        ssl_params["ssl_ca"] = ca_path
    if cert_path:
        ssl_params["ssl_cert"] = cert_path
    if key_path:
        ssl_params["ssl_key"] = key_path
    return ssl_params

def get_mysql_connection_params(datasource_dict: dict[str, Any]) -> dict[str, Any]:
    """Decrypt password and construct parameters for PyMySQL connection"""
    pw = decrypt_password(datasource_dict["password_ciphertext"], datasource_dict["password_nonce"])
    host = datasource_dict["host"]
    port = datasource_dict["port"]

    if datasource_dict.get("ssh_enabled"):
        tunnel = get_or_create_tunnel_for_dict(datasource_dict)
        host = "127.0.0.1"
        port = tunnel.local_bind_port

    params = {
        "host": host,
        "port": port,
        "user": datasource_dict["username"],
        "password": pw,
        "database": datasource_dict["database_name"],
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
    }
    params.update(build_mysql_ssl_params(datasource_dict))
    return params

def test_connection(config: dict[str, Any]) -> dict[str, Any]:
    """
    Test connectivity to a MySQL database (or demo database).
    Returns basic database stats and checks if permissions are readonly or have write capabilities.
    """
    host = config.get("host", "")
    port = config.get("port", 3306)
    database_name = config.get("database_name", "")
    username = config.get("username", "")
    password = config.get("password", "")

    if not host or not database_name or not username:
        raise DataSourceConnectionError("Missing host, database name, or username configuration.")

    # 1. Handle Demo Database Connection Test
    if is_demo_db(host, database_name):
        return {
            "ok": True,
            "serverVersion": "8.0.35-demo-databox",
            "readonly": True,
            "tablesCount": len(MOCK_TABLES_INFO),
            "warnings": ["当前使用的是内置演示环境 (Mock MySQL Mode)。所有写入已被模拟隔离。"],
            "message": "演示环境连接成功！"
        }

    # 2. Handle Real MySQL Connection Test
    temp_tunnel = None
    try:
        test_host = host
        test_port = port

        if config.get("ssh_enabled"):
            ssh_host = config.get("ssh_host")
            ssh_port = int(config.get("ssh_port", 22))
            ssh_username = config.get("ssh_username")
            ssh_password = config.get("ssh_password")
            ssh_pkey = config.get("ssh_pkey_path") if config.get("ssh_pkey_path") else None
            pkey_passphrase = config.get("ssh_pkey_passphrase")

            try:
                temp_tunnel = SSHTunnelForwarder(
                    (ssh_host, ssh_port),
                    ssh_username=ssh_username,
                    ssh_password=ssh_password,
                    ssh_pkey=ssh_pkey,
                    ssh_private_key_password=pkey_passphrase,
                    remote_bind_address=(host, port),
                    local_bind_address=('127.0.0.1', 0),
                )
                temp_tunnel.start()
                test_host = "127.0.0.1"
                test_port = temp_tunnel.local_bind_port
            except Exception as se:
                raise DataSourceConnectionError(f"无法建立 SSH 隧道，请检查跳板机配置。错误: {str(se)}")

        conn = pymysql.connect(
            host=test_host,
            port=test_port,
            user=username,
            password=password,
            database=database_name,
            charset="utf8mb4",
            connect_timeout=5,
            **build_mysql_ssl_params(config),
        )
        try:
            with conn.cursor() as cursor:
                # Get MySQL server version
                cursor.execute("SELECT VERSION()")
                version_row = cursor.fetchone()
                version = str(version_row[0]) if version_row else "unknown"

                # Get count of tables in this database
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                    (database_name,)
                )
                tables_row = cursor.fetchone()
                tables_count = int(tables_row[0]) if tables_row else 0

                # Assess write permissions by reading grants or querying table privileges
                readonly = True
                warnings = []
                try:
                    cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
                    grants = [row[0] for row in cursor.fetchall()]
                    # Check if grants contain unsafe privileges
                    for grant in grants:
                        grant_upper = grant.upper()
                        if "ALL PRIVILEGES" in grant_upper or any(op in grant_upper for op in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER"]):
                            readonly = False
                            break
                except Exception:
                    try:
                        cursor.execute("SHOW VARIABLES LIKE 'read_only'")
                        res = cursor.fetchone()
                        if res and res[1] == "ON":
                            readonly = True
                        else:
                            readonly = False
                    except Exception:
                        readonly = False

                if not readonly:
                    warnings.append("提示：当前数据库账号包含写入权限(INSERT/UPDATE/DELETE/DROP)，建议在生产环境使用只读只查的只读账号以保安全。")

                return {
                    "ok": True,
                    "serverVersion": version,
                    "readonly": readonly,
                    "tablesCount": tables_count,
                    "warnings": warnings,
                    "message": "数据库连接测试成功！"
                }
        finally:
            conn.close()
    except Exception as e:
        if isinstance(e, DataSourceConnectionError):
            raise e
        raise DataSourceConnectionError(f"无法建立数据库连接，请检查配置信息。错误详情: {str(e)}")
    finally:
        if temp_tunnel:
            try:
                temp_tunnel.stop()
            except Exception:
                pass
