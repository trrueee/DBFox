import logging
import subprocess
import socket
import time
import pymysql
from datetime import datetime, timedelta

logger = logging.getLogger("databox.demo_mysql")

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) NOT NULL,
        email VARCHAR(150) NOT NULL UNIQUE,
        phone VARCHAR(50),
        role VARCHAR(50) NOT NULL DEFAULT 'user',
        created_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS categories (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        parent_id INT,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (parent_id) REFERENCES categories (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        sku VARCHAR(100) NOT NULL UNIQUE,
        category_id INT NOT NULL,
        price DECIMAL(10,2) NOT NULL,
        stock INT NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'active',
        created_at DATETIME NOT NULL,
        FOREIGN KEY (category_id) REFERENCES categories (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        total_amount DECIMAL(10,2) NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'pending',
        payment_method VARCHAR(50),
        shipping_address VARCHAR(255) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS order_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        order_id INT NOT NULL,
        product_id INT NOT NULL,
        price DECIMAL(10,2) NOT NULL,
        quantity INT NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS payments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        order_id INT NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'pending',
        transaction_id VARCHAR(100),
        created_at DATETIME NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS shipping (
        id INT AUTO_INCREMENT PRIMARY KEY,
        order_id INT NOT NULL,
        tracking_number VARCHAR(100),
        carrier VARCHAR(50),
        status VARCHAR(50) NOT NULL DEFAULT 'packing',
        shipped_at DATETIME,
        delivered_at DATETIME,
        FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS reviews (
        id INT AUTO_INCREMENT PRIMARY KEY,
        product_id INT NOT NULL,
        user_id INT NOT NULL,
        rating INT NOT NULL,
        comment TEXT,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS cart (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        product_id INT NOT NULL,
        quantity INT NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS inventory_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        product_id INT NOT NULL,
        change_amount INT NOT NULL,
        reason VARCHAR(100) NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS coupons (
        id INT AUTO_INCREMENT PRIMARY KEY,
        code VARCHAR(100) NOT NULL UNIQUE,
        discount_type VARCHAR(50) NOT NULL,
        value DECIMAL(10,2) NOT NULL,
        min_spend DECIMAL(10,2) NOT NULL,
        expires_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS coupon_usages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coupon_id INT NOT NULL,
        order_id INT NOT NULL,
        user_id INT NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (coupon_id) REFERENCES coupons (id) ON DELETE CASCADE,
        FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS user_addresses (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        consignee VARCHAR(100) NOT NULL,
        phone VARCHAR(50) NOT NULL,
        province VARCHAR(100) NOT NULL,
        city VARCHAR(100) NOT NULL,
        district VARCHAR(100),
        address VARCHAR(255) NOT NULL,
        is_default INT NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS suppliers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        contact VARCHAR(100) NOT NULL,
        phone VARCHAR(50) NOT NULL,
        address VARCHAR(255),
        created_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_orders (
        id INT AUTO_INCREMENT PRIMARY KEY,
        supplier_id INT NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'pending',
        total_cost DECIMAL(12,2) NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_order_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        purchase_order_id INT NOT NULL,
        product_id INT NOT NULL,
        cost DECIMAL(10,2) NOT NULL,
        quantity INT NOT NULL,
        FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders (id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS analytics_clicks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        product_id INT NOT NULL,
        source VARCHAR(50) NOT NULL,
        ip VARCHAR(50) NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS system_settings (
        `key` VARCHAR(100) PRIMARY KEY,
        value VARCHAR(255) NOT NULL,
        description VARCHAR(255),
        updated_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        admin_id INT NOT NULL,
        action VARCHAR(100) NOT NULL,
        ip VARCHAR(50) NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (admin_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        product_id INT NOT NULL,
        score DECIMAL(5,4) NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
]

def check_docker_available() -> bool:
    try:
        res = subprocess.run(["docker", "--version"], capture_output=True, text=True, check=True)
        return "Docker version" in res.stdout
    except Exception:
        return False

def check_demo_container_status() -> str:
    """Returns 'running', 'stopped', or 'none'"""
    try:
        res = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=databox-demo-mysql", "--format", "{{.State}}"],
            capture_output=True, text=True, check=True
        )
        status = res.stdout.strip()
        if not status:
            return "none"
        return "running" if "running" in status else "stopped"
    except Exception:
        return "none"

def launch_demo_container() -> bool:
    status = check_demo_container_status()
    if status == "running":
        logger.info("Demo container already running.")
        return True
    
    if status == "stopped":
        logger.info("Starting existing stopped demo container.")
        subprocess.run(["docker", "start", "databox-demo-mysql"], check=True)
        return True
    
    logger.info("Creating and running a new demo container.")
    # Standard non-SSL container on port 3309
    cmd = [
        "docker", "run", "-d",
        "--name", "databox-demo-mysql",
        "-p", "3309:3306",
        "-e", "MYSQL_ROOT_PASSWORD=demo_root",
        "-e", "MYSQL_DATABASE=databox_demo",
        "-e", "MYSQL_USER=databox_demo_user",
        "-e", "MYSQL_PASSWORD=demo_pass",
        "mysql:8.0"
    ]
    subprocess.run(cmd, check=True)
    return True

def wait_for_mysql_port(timeout: int = 40) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(("127.0.0.1", 3309))
                logger.info("MySQL port 3309 is open.")
                # Give the database a brief moment to complete setup in active running state
                time.sleep(4.0)
                return True
        except Exception:
            time.sleep(1.5)
    return False

def populate_demo_data() -> None:
    now = datetime.now()
    
    # Connect as root to ensure full permissions to load structure and bypass checks
    conn = pymysql.connect(
        host="127.0.0.1",
        port=3309,
        user="root",
        password="demo_root",
        database="databox_demo",
        charset="utf8mb4"
    )
    
    try:
        with conn.cursor() as cursor:
            # 1. Disable FK checks to allow schema setup and arbitrary insert order
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            
            # 2. Drop existing tables if any to guarantee a clean slate
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            for (tbl,) in tables:
                cursor.execute(f"DROP TABLE IF EXISTS `{tbl}`")
            
            # 3. Create all tables
            for ddl in DDL_STATEMENTS:
                cursor.execute(ddl)
                
            # 4. Insert users
            users_data = [
                ("admin", "admin@databox.local", "13800000000", "admin", (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("staff_jack", "jack@databox.local", "13800000001", "staff", (now - timedelta(days=80)).strftime('%Y-%m-%d %H:%M:%S')),
                ("staff_lucy", "lucy@databox.local", "13800000002", "staff", (now - timedelta(days=80)).strftime('%Y-%m-%d %H:%M:%S')),
                ("zhangsan", "zhangsan@outlook.com", "13911112222", "user", (now - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')),
                ("lisi", "lisi@gmail.com", "13933334444", "user", (now - timedelta(days=55)).strftime('%Y-%m-%d %H:%M:%S')),
                ("wangwu", "wangwu@qq.com", "13566667777", "user", (now - timedelta(days=50)).strftime('%Y-%m-%d %H:%M:%S')),
                ("zhaoliu", "zhaoliu@163.com", "13788889999", "user", (now - timedelta(days=45)).strftime('%Y-%m-%d %H:%M:%S')),
                ("qianqi", "qianqi@foxmail.com", "18600001111", "user", (now - timedelta(days=40)).strftime('%Y-%m-%d %H:%M:%S')),
                ("sunba", "sunba@yahoo.com", "18622223333", "user", (now - timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S')),
                ("zhoujiu", "zhoujiu@hotmail.com", "18544445555", "user", (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')),
                ("wushi", "wushi@databox.com", "17788889999", "user", (now - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO users (username, email, phone, role, created_at) VALUES (%s, %s, %s, %s, %s)",
                users_data
            )
            
            # Categories
            categories_data = [
                ("数码电器", None, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("智能手机", 1, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("便携电脑", 1, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("精品男装", None, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("潮流外套", 4, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("休闲裤装", 4, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("食品饮料", None, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("生鲜水果", 7, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("休闲零食", 7, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("图书办公", None, (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO categories (name, parent_id, created_at) VALUES (%s, %s, %s)",
                categories_data
            )
            
            # Products
            products_data = [
                ("iPhone 15 Pro", "SKU_IPHONE_15_PRO", 2, 7999.00, 120, "active", (now - timedelta(days=80)).strftime('%Y-%m-%d %H:%M:%S')),
                ("Xiaomi 14 Ultra", "SKU_XIAOMI_14_U", 2, 6499.00, 85, "active", (now - timedelta(days=70)).strftime('%Y-%m-%d %H:%M:%S')),
                ("MacBook Pro 14", "SKU_MBP_14", 3, 12999.00, 45, "active", (now - timedelta(days=80)).strftime('%Y-%m-%d %H:%M:%S')),
                ("ThinkPad X1 Carbon", "SKU_TP_X1_C", 3, 10999.00, 30, "active", (now - timedelta(days=75)).strftime('%Y-%m-%d %H:%M:%S')),
                ("时尚无帽冲锋衣", "SKU_JACKET_001", 5, 299.00, 500, "active", (now - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')),
                ("复古工装休闲裤", "SKU_PANTS_002", 6, 179.00, 350, "active", (now - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')),
                ("烟台红富士苹果 5kg", "SKU_FRUIT_APPLE", 8, 59.90, 800, "active", (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')),
                ("泰国进口金枕头榴莲 2-3kg", "SKU_FRUIT_DURIAN", 8, 159.00, 150, "active", (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')),
                ("手撕牛肉干 250g", "SKU_SNACK_BEEF", 9, 45.00, 1200, "active", (now - timedelta(days=50)).strftime('%Y-%m-%d %H:%M:%S')),
                ("算法导论 (原书第3版)", "SKU_BOOK_ALGO", 10, 128.00, 200, "active", (now - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')),
                ("设计模式的艺术", "SKU_BOOK_DESIGN", 10, 69.00, 0, "inactive", (now - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO products (name, sku, category_id, price, stock, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                products_data
            )
            
            # Orders
            orders_data = [
                (4, 8058.90, "completed", "alipay", "北京市海淀区中关村南大街1号", (now - timedelta(days=25)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=25)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, 6499.00, "completed", "wechat", "上海市浦东新区张江高科技园区20号", (now - timedelta(days=22)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=22)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, 478.00, "completed", "credit_card", "广东省深圳市南山区腾讯大厦", (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')),
                (7, 128.00, "paid", "alipay", "浙江省杭州市余杭区阿里巴巴西溪园区", (now - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')),
                (8, 299.00, "shipped", "wechat", "四川省成都市武侯区科华北路99号", (now - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=4)).strftime('%Y-%m-%d %H:%M:%S')),
                (9, 218.90, "completed", "alipay", "湖北省武汉市东湖高新区光谷广场", (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')),
                (4, 159.00, "pending", None, "北京市海淀区中关村南大街1号", (now - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')),
                (10, 45.00, "cancelled", None, "陕西省西安市雁塔区小寨东路", (now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, 12999.00, "completed", "credit_card", "上海市浦东新区张江高科技园区20号", (now - timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, 59.90, "completed", "wechat", "广东省深圳市南山区腾讯大厦", (now - timedelta(days=12)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=12)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO orders (user_id, total_amount, status, payment_method, shipping_address, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                orders_data
            )
            
            # Order Items
            order_items_data = [
                (1, 1, 7999.00, 1, (now - timedelta(days=25)).strftime('%Y-%m-%d %H:%M:%S')),
                (1, 7, 59.90, 1, (now - timedelta(days=25)).strftime('%Y-%m-%d %H:%M:%S')),
                (2, 2, 6499.00, 1, (now - timedelta(days=22)).strftime('%Y-%m-%d %H:%M:%S')),
                (3, 5, 299.00, 1, (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')),
                (3, 6, 179.00, 1, (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')),
                (4, 10, 128.00, 1, (now - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, 5, 299.00, 1, (now - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, 7, 59.90, 1, (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, 8, 159.00, 1, (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')),
                (7, 8, 159.00, 1, (now - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')),
                (8, 9, 45.00, 1, (now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S')),
                (9, 3, 12999.00, 1, (now - timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S')),
                (10, 7, 59.90, 1, (now - timedelta(days=12)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO order_items (order_id, product_id, price, quantity, created_at) VALUES (%s, %s, %s, %s, %s)",
                order_items_data
            )
            
            # Payments
            payments_data = [
                (1, 8058.90, "success", "TXN_ALIPAY_89410328", (now - timedelta(days=25)).strftime('%Y-%m-%d %H:%M:%S')),
                (2, 6499.00, "success", "TXN_WECHAT_77189204", (now - timedelta(days=22)).strftime('%Y-%m-%d %H:%M:%S')),
                (3, 478.00, "success", "TXN_CC_6619028", (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')),
                (4, 128.00, "success", "TXN_ALIPAY_2290481", (now - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, 299.00, "success", "TXN_WECHAT_0019283", (now - timedelta(days=4)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, 218.90, "success", "TXN_ALIPAY_55681920", (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')),
                (7, 159.00, "pending", None, (now - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')),
                (8, 45.00, "failed", None, (now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S')),
                (9, 12999.00, "success", "TXN_CC_98910283", (now - timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S')),
                (10, 59.90, "success", "TXN_WECHAT_10283948", (now - timedelta(days=12)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO payments (order_id, amount, status, transaction_id, created_at) VALUES (%s, %s, %s, %s, %s)",
                payments_data
            )
            
            # Shipping
            shipping_data = [
                (1, "SF1489028340", "sf", "delivered", (now - timedelta(days=24)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=23)).strftime('%Y-%m-%d %H:%M:%S')),
                (2, "YT8819208340", "yto", "delivered", (now - timedelta(days=21)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')),
                (3, "ZT2009384910", "zto", "delivered", (now - timedelta(days=19)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=18)).strftime('%Y-%m-%d %H:%M:%S')),
                (4, "SF1002938490", "sf", "delivered", (now - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=13)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, "YT2009182390", "yto", "transit", (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S'), None),
                (6, "ZT9083948293", "zto", "delivered", (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')),
                (9, "SF1892839482", "sf", "delivered", (now - timedelta(days=34)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=33)).strftime('%Y-%m-%d %H:%M:%S')),
                (10, "YT9828394819", "yto", "delivered", (now - timedelta(days=11)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO shipping (order_id, tracking_number, carrier, status, shipped_at, delivered_at) VALUES (%s, %s, %s, %s, %s, %s)",
                shipping_data
            )
            
            # Reviews
            reviews_data = [
                (1, 4, 5, "太棒了！屏幕非常清晰，系统非常流畅，苹果品质没得说！", (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')),
                (2, 5, 5, "Xiaomi 14 Ultra 拍照太绝了，徕卡专业光学镜头就是不一样！", (now - timedelta(days=18)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, 6, 4, "冲锋衣面料还算舒适，防风效果也可以，就是快递稍微慢了点。", (now - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')),
                (10, 4, 5, "算法导论的圣经！买一本收藏，虽然看起来非常烧脑，但极力推荐！", (now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO reviews (product_id, user_id, rating, comment, created_at) VALUES (%s, %s, %s, %s, %s)",
                reviews_data
            )
            
            # Cart
            cart_data = [
                (4, 9, 2, (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, 1, 1, (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, 10, 1, (now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO cart (user_id, product_id, quantity, created_at) VALUES (%s, %s, %s, %s)",
                cart_data
            )
            
            # Inventory Logs
            inv_logs_data = [
                (1, 200, "purchase", (now - timedelta(days=80)).strftime('%Y-%m-%d %H:%M:%S')),
                (1, -80, "sale", (now - timedelta(days=70)).strftime('%Y-%m-%d %H:%M:%S')),
                (2, 100, "purchase", (now - timedelta(days=70)).strftime('%Y-%m-%d %H:%M:%S')),
                (3, 50, "purchase", (now - timedelta(days=80)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, 500, "purchase", (now - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')),
                (11, 20, "purchase", (now - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')),
                (11, -20, "adjust", (now - timedelta(days=40)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO inventory_logs (product_id, change_amount, reason, created_at) VALUES (%s, %s, %s, %s)",
                inv_logs_data
            )
            
            # Coupons
            coupons_data = [
                ("HAPPY_NEW_YEAR", "fixed", 50.00, 300.00, (now + timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')),
                ("DOUBLE_11_SALE", "discount", 0.90, 100.00, (now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')),
                ("VIP_EXCLUSIVES", "fixed", 100.00, 500.00, (now + timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S'), (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO coupons (code, discount_type, value, min_spend, expires_at, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                coupons_data
            )
            
            # Coupon Usages
            coupon_usages_data = [
                (1, 1, 4, (now - timedelta(days=25)).strftime('%Y-%m-%d %H:%M:%S')),
                (3, 9, 5, (now - timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO coupon_usages (coupon_id, order_id, user_id, created_at) VALUES (%s, %s, %s, %s)",
                coupon_usages_data
            )
            
            # User Addresses
            addresses_data = [
                (4, "张三", "13911112222", "北京市", "北京市", "海淀区", "中关村南大街1号", 1, (now - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, "李四", "13933334444", "上海市", "上海市", "浦东新区", "张江高科技园区20号", 1, (now - timedelta(days=55)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, "王五", "13566667777", "广东省", "深圳市", "南山区", "腾讯大厦", 1, (now - timedelta(days=50)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, "王小五", "13566667778", "湖北省", "武汉市", "洪山区", "光谷步行街", 0, (now - timedelta(days=40)).strftime('%Y-%m-%d %H:%M:%S')),
                (7, "赵六", "13788889999", "浙江省", "杭州市", "余杭区", "阿里巴巴西溪园区", 1, (now - timedelta(days=45)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO user_addresses (user_id, consignee, phone, province, city, district, address, is_default, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                addresses_data
            )
            
            # Suppliers
            suppliers_data = [
                ("华强北数码供应联盟", "刘经理", "18999990001", "广东省深圳市福田区华强北路", (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("北京红星图书出版社", "陈老师", "18999990002", "北京市朝阳区红星街8号", (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("南粤生鲜贸易行", "张掌柜", "18999990003", "广东省广州市荔湾区农贸市场", (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO suppliers (name, contact, phone, address, created_at) VALUES (%s, %s, %s, %s, %s)",
                suppliers_data
            )
            
            # Purchase Orders
            purchase_orders_data = [
                (1, "received", 85000.00, (now - timedelta(days=50)).strftime('%Y-%m-%d %H:%M:%S')),
                (2, "received", 12000.00, (now - timedelta(days=45)).strftime('%Y-%m-%d %H:%M:%S')),
                (3, "pending", 3500.00, (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO purchase_orders (supplier_id, status, total_cost, created_at) VALUES (%s, %s, %s, %s)",
                purchase_orders_data
            )
            
            # Purchase Order Items
            po_items_data = [
                (1, 1, 5500.00, 10),
                (1, 2, 4500.00, 10),
                (2, 10, 80.00, 150),
                (3, 7, 35.00, 100),
            ]
            cursor.executemany(
                "INSERT INTO purchase_order_items (purchase_order_id, product_id, cost, quantity) VALUES (%s, %s, %s, %s)",
                po_items_data
            )
            
            # Analytics Clicks
            clicks_data = [
                (4, 1, "ios", "192.168.1.10", (now - timedelta(days=1, hours=3)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, 2, "android", "192.168.1.11", (now - timedelta(days=1, hours=2)).strftime('%Y-%m-%d %H:%M:%S')),
                (None, 5, "web", "202.108.22.45", (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, 10, "web", "110.12.184.2", (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')),
                (7, 3, "ios", "220.181.108.9", (now - timedelta(days=4)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO analytics_clicks (user_id, product_id, source, ip, created_at) VALUES (%s, %s, %s, %s, %s)",
                clicks_data
            )
            
            # System Settings
            settings_data = [
                ("site_name", "DataBox Premium Shop", "在线商城显示名称", (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("maintenance_mode", "false", "系统维护开关", (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
                ("points_ratio", "10", "消费返积分比例(百分比)", (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO system_settings (`key`, value, description, updated_at) VALUES (%s, %s, %s, %s)",
                settings_data
            )
            
            # Admin Logs
            admin_logs_data = [
                (1, "system_setting_change", "192.168.1.100", (now - timedelta(days=88)).strftime('%Y-%m-%d %H:%M:%S')),
                (1, "audit_pass", "192.168.1.100", (now - timedelta(days=80)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO admin_logs (admin_id, action, ip, created_at) VALUES (%s, %s, %s, %s)",
                admin_logs_data
            )
            
            # Recommendations
            recs_data = [
                (4, 2, 0.9850, (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')),
                (4, 5, 0.8820, (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')),
                (5, 1, 0.9540, (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')),
                (6, 3, 0.9120, (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')),
            ]
            cursor.executemany(
                "INSERT INTO recommendations (user_id, product_id, score, created_at) VALUES (%s, %s, %s, %s)",
                recs_data
            )
            
            # Re-enable FK checks after population
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            
        conn.commit()
    finally:
        conn.close()
