import pymysql
import os

os.chdir(r"d:\Project\DataBox\databox-mysql-ssl-test")

db_config = {
    "host": "127.0.0.1",
    "port": 3308,
    "user": "databox_readonly",
    "password": "readonly_pass",
    "database": "databox_ssl",
}

print("=========================================")
print("1. Testing Non-SSL Connection (Expected to FAIL)")
print("=========================================")

try:
    conn = pymysql.connect(**db_config)
    print("[ERROR] Non-SSL connection succeeded! Secure transport might not be enforced.")
    conn.close()
except pymysql.err.OperationalError as e:
    print(f"[SUCCESS] Non-SSL connection failed as expected! Error: {e}")
except Exception as e:
    print(f"[SUCCESS] Non-SSL connection failed as expected with exception: {type(e).__name__}: {e}")


print("\n=========================================")
print("2. Testing SSL Connection with CA Certificate (Expected to SUCCEED)")
print("=========================================")

ssl_config = {
    "ca": os.path.abspath("certs/ca.pem"),
}

try:
    conn = pymysql.connect(
        ssl=ssl_config,
        **db_config
    )
    print("[SUCCESS] SSL connection established successfully!")
    
    with conn.cursor() as cursor:
        # Check SSL details
        cursor.execute("SHOW STATUS LIKE 'Ssl_cipher'")
        cipher = cursor.fetchone()
        
        cursor.execute("SHOW STATUS LIKE 'Ssl_version'")
        version = cursor.fetchone()
        
        cursor.execute("SHOW VARIABLES LIKE 'require_secure_transport'")
        req_secure = cursor.fetchone()
        
        print(f"   -> Ssl_cipher  : {cipher[1] if cipher else 'None'}")
        print(f"   -> Ssl_version : {version[1] if version else 'None'}")
        print(f"   -> require_secure_transport: {req_secure[1] if req_secure else 'None'}")
        
        # Query orders table
        print("\n   Fetching data from orders table:")
        cursor.execute("SELECT id, channel, amount, created_at FROM orders")
        rows = cursor.fetchall()
        for row in rows:
            print(f"   - ID: {row[0]}, Channel: {row[1]}, Amount: {row[2]}, Created At: {row[3]}")
            
    conn.close()
except Exception as e:
    print(f"[ERROR] SSL connection failed: {e}")


print("\n=========================================")
print("3. Testing SSL Connection with Host Identity Verification (Expected to SUCCEED)")
print("=========================================")

try:
    import ssl
    ssl_context = ssl.create_default_context(cafile=os.path.abspath("certs/ca.pem"))
    ssl_context.check_hostname = True
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    
    conn = pymysql.connect(
        ssl=ssl_context,
        **db_config
    )
    print("[SUCCESS] SSL connection with strict server identity verification established successfully!")
    conn.close()
except Exception as e:
    print(f"[ERROR] SSL connection with identity verification failed: {e}")
