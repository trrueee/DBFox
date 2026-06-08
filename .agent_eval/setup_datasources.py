import os
import sys
from pathlib import Path
from datetime import datetime, UTC

# Add the project root to sys.path so we can import engine modules
sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session
from engine.db import SessionLocal
from engine.models import DataSource, Project
from engine.crypto import encrypt_password
from engine.schema_sync import sync_schema

def setup_datasources():
    print("Setting up datasources in DataBox...")
    db: Session = SessionLocal()
    
    # 1. Ensure the default-project exists
    project = db.query(Project).filter(Project.id == "default-project").first()
    if not project:
        print("Creating default-project workspace...")
        project = Project(
            id="default-project",
            name="Default Workspace",
            description="Auto-created workspace for existing DataBox assets.",
            status="active"
        )
        db.add(project)
        db.commit()

    # 2. Define the datasources
    ds_configs = [
        {
            "id": "ds-spider-concert-singer",
            "name": "Spider Concert Singer",
            "database_name": "spider_concert_singer"
        },
        {
            "id": "ds-spider-pets-1",
            "name": "Spider Pets 1",
            "database_name": "spider_pets_1"
        }
    ]
    
    for config in ds_configs:
        ds_id = config["id"]
        # Check if datasource already exists
        ds = db.query(DataSource).filter(DataSource.id == ds_id).first()
        
        # Encrypt the password 'root'
        pw_cipher, pw_nonce = encrypt_password("root")
        
        if ds:
            print(f"Updating existing datasource: {config['name']}")
            ds.name = config["name"]
            ds.host = "127.0.0.1"
            ds.port = 3307
            ds.database_name = config["database_name"]
            ds.username = "root"
            ds.password_ciphertext = pw_cipher
            ds.password_nonce = pw_nonce
            ds.updated_at = datetime.now(UTC)
        else:
            print(f"Creating new datasource: {config['name']}")
            ds = DataSource(
                id=ds_id,
                project_id="default-project",
                name=config["name"],
                db_type="mysql",
                host="127.0.0.1",
                port=3307,
                database_name=config["database_name"],
                username="root",
                password_ciphertext=pw_cipher,
                password_nonce=pw_nonce,
                password_key_version="v1",
                is_read_only=False,
                env="dev",
                status="active",
                connection_mode="direct"
            )
            db.add(ds)
            
        db.commit()
        
        # 3. Synchronize Schema Catalog
        print(f"Syncing schema for {config['name']}...")
        try:
            res = sync_schema(db, ds_id)
            print(f"Successfully synced schema: {res}\n")
        except Exception as e:
            print(f"Failed to sync schema for {config['name']}: {e}\n")
            
    db.close()
    print("Datasource setup completed.")

if __name__ == "__main__":
    setup_datasources()
