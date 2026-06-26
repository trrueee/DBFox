from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from typing import Any

from engine.models import SchemaColumn

CHINESE_SURNAMES = ["赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈", "褚", "卫", "蒋", "沈", "韩", "杨", "朱", "秦", "尤", "许", "何", "吕", "施", "张", "孔", "曹", "严", "华", "金", "魏", "陶", "姜"]
CHINESE_MALE_NAMES = ["伟", "强", "磊", "洋", "勇", "军", "杰", "涛", "超", "明", "刚", "平", "辉", "帅", "毅", "俊", "立", "贤", "文", "博", "思", "志", "国", "宇", "鹏", "豪", "航", "翔", "浩", "然"]
CHINESE_FEMALE_NAMES = ["芳", "娟", "敏", "静", "秀", "丽", "艳", "华", "慧", "巧", "美", "娜", "欣", "晨", "佳", "莹", "婷", "莉", "雅", "倩", "蕊", "雪", "琳", "璐", "涵", "怡", "婕", "萱", "悦"]
ENGLISH_FIRST_NAMES = ["James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica", "Sarah", "Karen"]
ENGLISH_LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]
DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "163.com", "qq.com", "example.com"]
CITIES_CN = ["北京市朝阳区", "上海市浦东新区", "广州市天河区", "深圳市南山区", "杭州市西湖区", "成都市武侯区", "武汉市洪山区", "南京市玄武区", "西安市雁塔区"]
STREETS_CN = ["人民路", "中山路", "建设路", "解放路", "青年路", "东风路", "科苑南路", "中关村大街", "南京东路"]
STATUSES = ["active", "inactive", "pending", "completed", "cancelled", "delivered", "success", "failed", "refunded"]
ROLES = ["user", "admin", "editor", "guest", "operator"]


def generate_random_name(lang: str = "zh") -> str:
    if lang == "zh":
        surname = random.choice(CHINESE_SURNAMES)
        name_list = CHINESE_MALE_NAMES if random.choice([True, False]) else CHINESE_FEMALE_NAMES
        name_len = random.choice([1, 2])
        return f"{surname}{''.join(random.sample(name_list, name_len))}"
    first = random.choice(ENGLISH_FIRST_NAMES)
    last = random.choice(ENGLISH_LAST_NAMES)
    return f"{first} {last}"


def generate_random_phone(lang: str = "zh") -> str:
    if lang == "zh":
        prefix = random.choice([
            "134", "135", "136", "137", "138", "139", "150", "151", "152", "158",
            "159", "182", "183", "187", "188", "178", "130", "131", "132", "155",
            "156", "185", "186", "176", "133", "153", "180", "181", "189", "177",
        ])
        suffix = "".join(str(random.randint(0, 9)) for _ in range(8))
        return f"{prefix}{suffix}"
    return f"+1 ({random.randint(200, 999)}) 555-{random.randint(1000, 9999)}"


def generate_random_email(name: str, lang: str = "zh") -> str:
    if lang == "zh":
        prefix = "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(5)) + str(random.randint(10, 99))
    else:
        prefix = name.lower().replace(" ", ".") + str(random.randint(10, 99))
    return f"{prefix}@{random.choice(DOMAINS)}"


def generate_random_address(lang: str = "zh") -> str:
    if lang == "zh":
        return f"{random.choice(CITIES_CN)}{random.choice(STREETS_CN)}{random.randint(1, 999)}号"
    return f"{random.randint(100, 9999)} Broadway Ave, New York, NY {random.randint(10001, 10292)}"


def get_field_type_hint(col_name: str, col_type: str) -> str:
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


def generate_rows(
    columns: list[SchemaColumn],
    row_count: int,
    language: str,
    fk_mappings: dict[str, list[Any]],
) -> list[dict[str, Any]]:
    generated_rows: list[dict[str, Any]] = []
    for _idx in range(row_count):
        row_data: dict[str, Any] = {}
        row_fullname = ""
        for column in columns:
            col_name = str(column.column_name)
            col_type = str(column.column_type or "varchar")
            type_lower = col_type.lower()

            if column.is_primary_key:
                if "int" in type_lower:
                    continue
                if "char" in type_lower or "text" in type_lower or "uuid" in type_lower:
                    row_data[col_name] = str(uuid.uuid4())
                continue

            if column.is_foreign_key and col_name in fk_mappings:
                row_data[col_name] = random.choice(fk_mappings[col_name])
                continue

            hint = get_field_type_hint(col_name, col_type)
            if hint == "name":
                row_fullname = generate_random_name(language)
                row_data[col_name] = row_fullname
            elif hint == "username":
                row_data[col_name] = (
                    row_fullname.lower().replace(" ", "_") + str(random.randint(10, 99))
                    if row_fullname and language == "en"
                    else "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(5)) + str(random.randint(10, 99))
                )
            elif hint == "email":
                row_data[col_name] = generate_random_email(row_fullname or "user", language)
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
                value = round(random.uniform(9.9, 2999.0), 2)
                row_data[col_name] = int(value) if "int" in type_lower else value
            elif hint == "stock":
                row_data[col_name] = random.randint(0, 500)
            elif hint == "datetime":
                dt = datetime.now() - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23), minutes=random.randint(0, 59))
                row_data[col_name] = dt.strftime("%Y-%m-%d") if "date" in type_lower and "time" not in type_lower else dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                row_data[col_name] = _generate_default_value(col_name, type_lower, row_fullname, language)
        generated_rows.append(row_data)
    return generated_rows


def _generate_default_value(col_name: str, type_lower: str, row_fullname: str, language: str) -> Any:
    if "int" in type_lower or "bit" in type_lower or "bool" in type_lower:
        return random.choice([0, 1]) if "tinyint" in type_lower or "bool" in type_lower else random.randint(1, 1000)
    if "decimal" in type_lower or "float" in type_lower or "double" in type_lower or "numeric" in type_lower:
        return round(random.uniform(1.0, 100.0), 2)
    if "date" in type_lower or "time" in type_lower or "timestamp" in type_lower:
        dt = datetime.now() - timedelta(days=random.randint(0, 10))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    if "char" in type_lower or "text" in type_lower:
        if "sku" in col_name.lower():
            return f"SKU-{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))}"
        if "desc" in col_name.lower() or "comment" in col_name.lower() or "remark" in col_name.lower():
            if language == "zh":
                return f"这是关于 {row_fullname or '数据记录'} 的智能描述和测试批注。"
            return "High quality realistic mock description for testing purposes."
        return "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=8))
    return None
