import subprocess
import os

os.chdir(r"d:\Project\DataBox\databox-mysql-ssl-test")

# 1. Create server.cnf
cnf_content = """[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = localhost

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
"""

with open("server.cnf", "w", encoding="utf-8") as f:
    f.write(cnf_content)

# Set environment variable for OpenSSL config path
os.environ["OPENSSL_CONF"] = os.path.abspath("server.cnf")

# 2. Run openssl commands
cmds = [
    ["openssl", "genrsa", "2048"], # output to certs/ca-key.pem
    ["openssl", "req", "-new", "-x509", "-nodes", "-days", "3650", "-key", "certs/ca-key.pem", "-out", "certs/ca.pem", "-subj", "/CN=DataBox Test CA", "-config", "server.cnf"],
    ["openssl", "genrsa", "2048"], # output to certs/server-key.pem
    ["openssl", "req", "-new", "-key", "certs/server-key.pem", "-out", "certs/server-req.pem", "-subj", "/CN=localhost", "-config", "server.cnf"],
    ["openssl", "x509", "-req", "-in", "certs/server-req.pem", "-days", "3650", "-CA", "certs/ca.pem", "-CAkey", "certs/ca-key.pem", "-set_serial", "01", "-out", "certs/server-cert.pem", "-extensions", "v3_req", "-extfile", "server.cnf"],
    ["openssl", "genrsa", "2048"], # output to certs/client-key.pem
    ["openssl", "req", "-new", "-key", "certs/client-key.pem", "-out", "certs/client-req.pem", "-subj", "/CN=databox-client", "-config", "server.cnf"],
    ["openssl", "x509", "-req", "-in", "certs/client-req.pem", "-days", "3650", "-CA", "certs/ca.pem", "-CAkey", "certs/ca-key.pem", "-set_serial", "02", "-out", "certs/client-cert.pem"]
]

# Command 1: ca-key.pem
with open("certs/ca-key.pem", "wb") as f:
    subprocess.run(["openssl", "genrsa", "2048"], stdout=f, check=True)

# Command 2: ca.pem
subprocess.run(cmds[1], check=True)

# Command 3: server-key.pem
with open("certs/server-key.pem", "wb") as f:
    subprocess.run(["openssl", "genrsa", "2048"], stdout=f, check=True)

# Command 4: server-req.pem
subprocess.run(cmds[3], check=True)

# Command 5: server-cert.pem
subprocess.run(cmds[4], check=True)

# Command 6: client-key.pem
with open("certs/client-key.pem", "wb") as f:
    subprocess.run(["openssl", "genrsa", "2048"], stdout=f, check=True)

# Command 7: client-req.pem
subprocess.run(cmds[6], check=True)

# Command 8: client-cert.pem
subprocess.run(cmds[7], check=True)

print("Certificates generated successfully!")
