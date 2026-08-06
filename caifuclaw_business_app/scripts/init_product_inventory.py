# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime, timezone
from pathlib import Path
import sys

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, SessionLocal, engine
from app.product_models import Product, ProductInventory


def main() -> None:
    Base.metadata.create_all(bind=engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created = 0
    updated_names = 0
    with SessionLocal() as db:
        products = db.scalars(select(Product).order_by(Product.id)).all()
        existing = {
            row.product_id: row
            for row in db.scalars(select(ProductInventory)).all()
        }
        for product in products:
            inventory = existing.get(product.id)
            if inventory:
                if inventory.product_name != product.internal_name:
                    inventory.product_name = product.internal_name
                    inventory.updated_at = now
                    updated_names += 1
                continue
            db.add(
                ProductInventory(
                    product_id=product.id,
                    product_name=product.internal_name,
                    stock_qty=0,
                    last_count_qty=0,
                    remark="",
                    updated_by="init_script",
                    created_at=now,
                    updated_at=now,
                )
            )
            created += 1
        db.commit()
    print(f"products={len(products)} created={created} updated_names={updated_names}")


if __name__ == "__main__":
    main()
