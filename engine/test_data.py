import logging
import random
import uuid
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from engine.models import SchemaTable, SchemaColumn, DataSource
from engine.executor import execute_query
from engine.errors import DataBoxError

logger = logging.getLogger("databox.test_data")

# High fidelity preset data lists for generating premium realistic test data
CHINESE_SURNAMES = ["赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈", "褚", "卫", "蒋", "沈", "韩", "杨", "朱", "秦", "尤", "许", "何", "吕", "施", "张", "孔", "曹", "严", "华", "金", "魏", "陶", "姜"]
CHINESE_MALE_NAMES = ["伟", "强", "磊", "洋", "勇", "军", "杰", "涛", "超", "明", "刚", "平", "辉", "帅", "毅", "俊", "立", "贤", "文", "博", "思", "志", "国", "宇", "鹏", "豪", "航", "翔", "浩", "然"]
CHINESE_FEMALE_NAMES = ["芳", "娟", "敏", "静", "秀", "丽", "艳", "华", "慧", "巧", "美", "娜", "欣", "晨", "佳", "莹", "婷", "莉", "雅", "倩", "蕊", "雪", "琳", "璐", "涵", "怡", "婕", "萱", "悦"]

ENGLISH_FIRST_NAMES = ["James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica", "Sarah", "Karen"]
ENGLISH_LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]

DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "163.com", "qq.com", "example.com"]
PRODUCTS = ["iPhone 15 Pro", "MacBook Pro M3", "iPad Air", "AirPods Pro", "Apple Watch Ultra", "Sony WH-1000XM5", "Dell XPS 13", "Nintendo Switch", "PlayStation 5", "Logitech MX Master 3S"]
CITIES_CN = ["北京市朝阳区", "上海市浦东新区", "广州市天河区", "深圳市南山区", "杭州市西湖区", "成都市武侯区", "武汉市洪山区", "南京市玄武区", "西安市雁塔区"]
STREETS_CN = ["人民路", "中山路", "建设路", "解放路", "青年路", "东风路", "科苑南路", "中关村大街", "南京东路"]

STATUSES = ["active", "inactive", "pending", "completed", "cancelled", "delivered", "success", "failed", "refunded"]
ROLES = ["user", "admin", "editor", "guest", "operator"]

def generate_random_name(lang: str = "zh") -> str:
    if lang == "zh":
        surname = random.choice(CHINESE_SURNAMES)
        is_male = random.choice([True, False])
        name_list = CHINESE_MALE_NAMES if is_male else CHINESE_FEMALE_NAMES
        name_len = random.choice([1, 2])
        given_name = "".join(random.sample(name_list, name_len))
        return f"{surname}{given_name}"
    else:
        first = random.choice(ENGLISH_FIRST_NAMES)
        last = random.choice(ENGLISH_LAST_NAMES)
        return f"{first} {last}"

def generate_random_phone(lang: str = "zh") -> str:
    if lang == "zh":
        prefix = random.choice(["134", "135", "136", "137", "138", "139", "150", "151", "152", "158", "159", "182", "183", "187", "188", "178", "130", "131", "132", "155", "156", "185", "186", "176", "133", "153", "180", "181", "189", "177"])
        suffix = "".join(str(random.randint(0, 9)) for _ in range(8))
        return f"{prefix}{suffix}"
    else:
        return f"+1 ({random.randint(200, 999)}) 555-{random.randint(1000, 9999)}"

def generate_random_email(name: str, lang: str = "zh") -> str:
    if lang == "zh":
        # Convert simple pinyin prefix
        prefix = "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(5)) + str(random.randint(10, 99))
    else:
        prefix = name.lower().replace(" ", ".") + str(random.randint(10, 99))
    return f"{prefix}@{random.choice(DOMAINS)}"

def generate_random_address(lang: str = "zh") -> str:
    if lang == "zh":
        return f"{random.choice(CITIES_CN)}{random.choice(STREETS_CN)}{random.randint(1, 999)}号"
    else:
        return f"{random.randint(100, 9999)} Broadway Ave, New York, NY {random.randint(10001, 10292)}"

def get_field_type_hint(col_name: str, col_type: str) -> str:
    """Helper to guess the semantic field type from its name and SQL column type"""
    name_lower = col_name.lower()
    type_lower = col_type.lower()
    
    if "email" in name_lower:
        return "email"
    if "phone" in name_lower or "mobile" in name_lower or "tel" in name_lower:
        return "phone"
    if "username" in name_lower or "login" in name_lower:
        return "username"
    if "name" in name_lower:
        return "name"
    if "address" in name_lower or "location" in name_lower:
        return "address"
    if "status" in name_lower or "state" in name_lower:
        return "status"
    if "role" in name_lower:
        return "role"
    if "price" in name_lower or "amount" in name_lower or "cost" in name_lower or "revenue" in name_lower:
        return "price"
    if "stock" in name_lower or "inventory" in name_lower or "quantity" in name_lower or "qty" in name_lower:
        return "stock"
    if "password" in name_lower:
        return "password"
    if "created" in name_lower or "updated" in name_lower or "date" in name_lower or "time" in name_lower or "at" in name_lower:
        if "varchar" in type_lower or "char" in type_lower or "date" in type_lower or "time" in type_lower or "timestamp" in type_lower:
            return "datetime"
    return "default"

def generate_smart_test_data(
    db: Session,
    datasource_id: str,
    table_name: str,
    row_count: int = 10,
    language: str = "zh"
) -> Dict[str, Any]:
    """
    Main engine for generating linked high-fidelity database mock records.
    Ensures smart FK mapping by pre-querying parent tables dynamically.
    """
    start_time = datetime.now()
    
    # 1. Fetch source datasource and schema table
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise DataBoxError("DATASOURCE_NOT_FOUND", "数据源不存在")
        
    table = db.query(SchemaTable).filter(
        SchemaTable.data_source_id == datasource_id,
        SchemaTable.table_name == table_name
    ).first()
    
    if not table:
        raise DataBoxError("TABLE_NOT_FOUND", f"表 `{table_name}` 尚未同步，请先同步 Schema")

    columns: List[SchemaColumn] = table.columns
    if not columns:
        raise DataBoxError("NO_COLUMNS", f"表 `{table_name}` 没有定义字段，请重新检查表结构")

    # 2. Analyze FK dependencies and preload parent values
    fk_mappings: Dict[str, List[Any]] = {}  # col_name -> list of values
    
    for col in columns:
        if col.is_foreign_key and col.foreign_table_id:
            # Find the parent table name
            parent_table = db.query(SchemaTable).filter(SchemaTable.id == col.foreign_table_id).first()
            if not parent_table:
                continue
            
            parent_column_name = "id"  # Default fallback
            if col.foreign_column_id:
                parent_col_obj = db.query(SchemaColumn).filter(SchemaColumn.id == col.foreign_column_id).first()
                if parent_col_obj:
                    parent_column_name = parent_col_obj.column_name

            # Query existing parent table records to ensure referential integrity
            try:
                logger.info(f"Querying parent keys from table {parent_table.table_name} col {parent_column_name}")
                parent_query_sql = f"SELECT `{parent_column_name}` FROM `{parent_table.table_name}` LIMIT 200"
                parent_res = execute_query(db, datasource_id, parent_query_sql)
                
                if parent_res["success"] and parent_res["rows"]:
                    parent_ids = [row[parent_column_name] for row in parent_res["rows"]]
                    fk_mappings[col.column_name] = parent_ids
                else:
                    # If parent is empty, warn and enforce user action
                    raise DataBoxError(
                        "REFERENTIAL_INTEGRITY_VIOLATION",
                        f"关联的外键主表 `{parent_table.table_name}` 尚无数据！请先为其生成或录入数据，再为此子表造数据。"
                    )
            except DataBoxError:
                raise
            except Exception as e:
                logger.error(f"Failed to query parent keys: {e}")
                # Create a generic dummy value just in case
                fk_mappings[col.column_name] = [1, 2, 3]

    # 3. Generate high fidelity fake data row by row
    generated_rows: List[Dict[str, Any]] = []
    
    for idx in range(row_count):
        row_data: Dict[str, Any] = {}
        
        # Track names generated in this row for sensible dependencies
        row_fullname = ""
        
        for col in columns:
            col_name = col.column_name
            col_type = col.column_type or "varchar"
            
            # Skip auto-increment columns
            # Wait, how to know if columns are auto-increment? SchemaColumn has a column_default or similar,
            # or in general, column named 'id' that is PK and an integer can be skipped or let MySQL handle it.
            if col.is_primary_key:
                type_lower = col_type.lower()
                # If primary key is text/char/varchar, it might be a UUID, generate one.
                # If it's integer and NOT auto_increment (or we can't tell), we can let database auto_increment handle it,
                # or generate incrementing numbers. In MySQL, if is PK and auto_increment is default, let database do it!
                if "int" in type_lower:
                    # If we don't supply it, MySQL will auto increment it. We skip!
                    continue
                elif "char" in type_lower or "text" in type_lower or "uuid" in type_lower:
                    row_data[col_name] = str(uuid.uuid4())
                    continue
                else:
                    # Skip for safety
                    continue

            # Check if this column is a foreign key
            if col.is_foreign_key and col_name in fk_mappings:
                row_data[col_name] = random.choice(fk_mappings[col_name])
                continue

            # Heuristics based on field name and type
            hint = get_field_type_hint(col_name, col_type)
            type_lower = col_type.lower()
            
            if hint == "name":
                name = generate_random_name(language)
                row_fullname = name
                row_data[col_name] = name
            elif hint == "username":
                if row_fullname and language == "en":
                    row_data[col_name] = row_fullname.lower().replace(" ", "_") + str(random.randint(10, 99))
                else:
                    row_data[col_name] = "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(5)) + str(random.randint(10, 99))
            elif hint == "email":
                name_ref = row_fullname if row_fullname else "user"
                row_data[col_name] = generate_random_email(name_ref, language)
            elif hint == "phone":
                row_data[col_name] = generate_random_phone(language)
            elif hint == "address":
                row_data[col_name] = generate_random_address(language)
            elif hint == "status":
                row_data[col_name] = random.choice(STATUSES)
            elif hint == "role":
                row_data[col_name] = random.choice(ROLES)
            elif hint == "password":
                row_data[col_name] = "pbkdf2:sha256:260000$randomSaltStringValue"
            elif hint == "price":
                # decimal / float / double
                val = round(random.uniform(9.9, 2999.0), 2)
                if "int" in type_lower:
                    row_data[col_name] = int(val)
                else:
                    row_data[col_name] = val
            elif hint == "stock":
                row_data[col_name] = random.randint(0, 500)
            elif hint == "datetime":
                # Generate random datetime in last 30 days
                days_back = random.randint(0, 30)
                hours_back = random.randint(0, 23)
                mins_back = random.randint(0, 59)
                dt = datetime.now() - timedelta(days=days_back, hours=hours_back, minutes=mins_back)
                if "date" in type_lower and "time" not in type_lower:
                    row_data[col_name] = dt.strftime("%Y-%m-%d")
                else:
                    row_data[col_name] = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                # Default fallback generation by SQL types
                if "int" in type_lower or "bit" in type_lower or "bool" in type_lower:
                    if "tinyint" in type_lower or "bool" in type_lower:
                        row_data[col_name] = random.choice([0, 1])
                    else:
                        row_data[col_name] = random.randint(1, 1000)
                elif "decimal" in type_lower or "float" in type_lower or "double" in type_lower or "numeric" in type_lower:
                    row_data[col_name] = round(random.uniform(1.0, 100.0), 2)
                elif "date" in type_lower or "time" in type_lower or "timestamp" in type_lower:
                    dt = datetime.now() - timedelta(days=random.randint(0, 10))
                    row_data[col_name] = dt.strftime("%Y-%m-%d %H:%M:%S")
                elif "char" in type_lower or "text" in type_lower:
                    if "sku" in col_name.lower():
                        row_data[col_name] = f"SKU-{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))}"
                    elif "desc" in col_name.lower() or "comment" in col_name.lower() or "remark" in col_name.lower():
                        if language == "zh":
                            row_data[col_name] = f"这是关于 {row_fullname or '数据记录'} 的智能描述和测试批注。"
                        else:
                            row_data[col_name] = f"High quality realistic mock description for testing purposes."
                    else:
                        row_data[col_name] = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=8))
                else:
                    row_data[col_name] = None
        
        generated_rows.append(row_data)

    # 4. Perform database batch insertion
    inserted_count = 0
    sql_statements = []
    
    for row in generated_rows:
        cols_str = ", ".join(f"`{k}`" for k in row.keys())
        
        # Format values properly for standard MySQL SQL
        vals_list = []
        for v in row.values():
            if v is None:
                vals_list.append("NULL")
            elif isinstance(v, (int, float)):
                vals_list.append(str(v))
            elif isinstance(v, bool):
                vals_list.append("1" if v else "0")
            else:
                # Escape single quotes
                escaped = str(v).replace("'", "\\'")
                vals_list.append(f"'{escaped}'")
                
        vals_str = ", ".join(vals_list)
        insert_sql = f"INSERT INTO `{table_name}` ({cols_str}) VALUES ({vals_str})"
        sql_statements.append(insert_sql)

    # Execute transactions sequentially or in one batch
    try:
        for sql in sql_statements:
            res = execute_query(db, datasource_id, sql, bypass_guardrail=True)
            if not res["success"]:
                raise DataBoxError(
                    "BATCH_INSERT_FAILED",
                    f"批量插入测试数据失败，SQL: {sql}, 错误: {res.get('error_message', '未知错误')}"
                )
            inserted_count += 1
            
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Automatically update metastore row count estimate
        table.row_count_estimate = (table.row_count_estimate or 0) + inserted_count
        db.commit()
        
        return {
            "success": True,
            "tableName": table_name,
            "insertedRows": inserted_count,
            "latencyMs": latency_ms,
            "message": f"成功为表 `{table_name}` 智能注入 {inserted_count} 条高保真测试数据！"
        }
    except Exception as e:
        db.rollback()
        logger.exception("Failed to insert mockup test data")
        if isinstance(e, DataBoxError):
            raise
        raise DataBoxError(
            "TEST_DATA_GENERATION_FAILED",
            f"智能测试数据生成或写入失败: {str(e)}"
        )
