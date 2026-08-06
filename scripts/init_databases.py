# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import psycopg

from common.config_loader import require


def create_database(db_name: str) -> None:
    host = require("postgres", "host")
    port = int(require("postgres", "port"))
    user = require("postgres", "user")
    password = require("postgres", "password")
    maintenance_db = require("postgres", "maintenance_database")
    with psycopg.connect(host=host, port=port, user=user, password=password, dbname=maintenance_db, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"created database {db_name}")
        else:
            print(f"database {db_name} exists")


if __name__ == "__main__":
    create_database(require("databases", "sync"))
