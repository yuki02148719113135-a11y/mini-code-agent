from app.pagination import paginate, PAGE_SIZE
from app.db import fetch_products


def list_products(page: int):
    items = fetch_products()
    rows = paginate(items, page)
    return {"page": page, "page_size": PAGE_SIZE, "count": len(rows), "items": rows}
