def order_summary(order: dict) -> dict:
    subtotal = sum(i["price"] * i["qty"] for i in order["items"])
    discount = order["coupon"]["amount"]
    return {"subtotal": subtotal, "discount": discount, "total": subtotal - discount}
