ORDER_STATUSES = {
    "received": "دریافت شده",
    "in_repair": "در حال تعمیر",
    "waiting_parts": "در انتظار قطعه",
    "sent_external": "ارسال به تعمیرگاه دیگر",
    "ready": "آماده تحویل",
    "delivered": "تحویل شده",
    "cancelled": "لغو شده",
}

PART_STATUSES = {
    "needed": "نیازمند سفارش",
    "ordered": "سفارش داده شده",
    "received": "رسیده",
}

SALE_TYPES = {
    "cash": "نقد",
    "credit": "نسیه",
    "installment": "اقساط",
}

RELATION_TYPES = ["مشتری عادی", "آشنا", "دوست", "خویشاوند", "همکار", "سایر"]

DEFAULT_INVENTORY_ITEMS = [
    ("کارتریج", "cartridge", "عدد"),
    ("کابل برق پرینتر", "power_cable", "عدد"),
    ("کابل دیتای پرینتر", "data_cable", "عدد"),
    ("کاغذ A4", "a4_paper", "بسته"),
    ("جوهر اپسون", "epson_ink", "بطری"),
    ("ریبون", "ribbon", "عدد"),
]
