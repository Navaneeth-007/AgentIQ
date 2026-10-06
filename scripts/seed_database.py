"""
Seed the sample SQLite database with realistic business data.

Tables:
  - orders         (order_id, customer_id, product_category, amount, region, order_date, shipped_date)
  - customers      (customer_id, name, region, signup_date, tier)
  - products       (product_id, name, category, unit_price, cost)
  - employees      (employee_id, name, department, hire_date, salary)

This gives the agent interesting questions to answer across sales, ops, and HR.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path("data/sample_db/agentiq.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

REGIONS = ["North", "South", "East", "West", "International"]
CATEGORIES = [
    "Electronics",
    "Clothing",
    "Home & Garden",
    "Sports",
    "Books",
    "Food & Beverage",
]
TIERS = ["Bronze", "Silver", "Gold", "Platinum"]
DEPARTMENTS = ["Engineering", "Sales", "Marketing", "HR", "Finance", "Operations"]

random.seed(42)


def random_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


def seed():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Drop and recreate
    c.executescript("""
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS customers;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS employees;

        CREATE TABLE customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT,
            region TEXT,
            signup_date TEXT,
            tier TEXT
        );

        CREATE TABLE products (
            product_id TEXT PRIMARY KEY,
            name TEXT,
            category TEXT,
            unit_price REAL,
            cost REAL
        );

        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT,
            product_id TEXT,
            product_category TEXT,
            amount REAL,
            quantity INTEGER,
            region TEXT,
            order_date TEXT,
            shipped_date TEXT,
            status TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE employees (
            employee_id TEXT PRIMARY KEY,
            name TEXT,
            department TEXT,
            hire_date TEXT,
            salary REAL,
            is_active INTEGER
        );
    """)

    # Customers
    first_names = [
        "Alice",
        "Bob",
        "Carlos",
        "Diana",
        "Ethan",
        "Fiona",
        "George",
        "Hannah",
        "Ivan",
        "Julia",
        "Kevin",
        "Laura",
        "Mike",
        "Nina",
        "Oscar",
        "Priya",
    ]
    last_names = [
        "Smith",
        "Johnson",
        "Williams",
        "Brown",
        "Jones",
        "Garcia",
        "Miller",
        "Davis",
    ]

    customers = []
    for i in range(1, 201):
        cid = f"CUST{i:04d}"
        name = f"{random.choice(first_names)} {random.choice(last_names)}"
        customers.append(
            (
                cid,
                name,
                random.choice(REGIONS),
                str(random_date(date(2020, 1, 1), date(2023, 12, 31))),
                random.choice(TIERS),
            )
        )
    c.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", customers)

    # Products
    product_data = {
        "Electronics": [
            ("Wireless Headphones", 149.99, 60),
            ("Smart Watch", 299.99, 120),
            ("Bluetooth Speaker", 79.99, 32),
            ("Tablet Stand", 29.99, 8),
        ],
        "Clothing": [
            ("Running Shoes", 89.99, 35),
            ("Winter Jacket", 129.99, 52),
            ("Yoga Pants", 49.99, 18),
            ("Casual T-Shirt", 19.99, 6),
        ],
        "Home & Garden": [
            ("Coffee Maker", 69.99, 28),
            ("Air Purifier", 199.99, 80),
            ("Garden Hose", 39.99, 12),
            ("Throw Pillow", 24.99, 8),
        ],
        "Sports": [
            ("Foam Roller", 34.99, 12),
            ("Resistance Bands", 19.99, 5),
            ("Yoga Mat", 44.99, 18),
            ("Jump Rope", 14.99, 4),
        ],
        "Books": [
            ("Data Science Handbook", 49.99, 10),
            ("Leadership Guide", 24.99, 6),
            ("Python Programming", 39.99, 8),
            ("Business Strategy", 29.99, 7),
        ],
        "Food & Beverage": [
            ("Protein Powder", 54.99, 22),
            ("Green Tea (50pk)", 14.99, 4),
            ("Coffee Beans (1kg)", 22.99, 8),
            ("Vitamin Pack", 29.99, 10),
        ],
    }

    products = []
    for cat, items in product_data.items():
        for i, (name, price, cost) in enumerate(items):
            pid = f"PROD-{cat[:3].upper()}-{i + 1:02d}"
            products.append((pid, name, cat, price, cost))
    c.executemany("INSERT INTO products VALUES (?,?,?,?,?)", products)

    # Orders — 2 years of data
    order_start = date(2023, 1, 1)
    order_end = date(2024, 12, 31)
    orders = []
    for i in range(1, 2001):
        oid = f"ORD{i:06d}"
        cid = random.choice(customers)[0]
        prod = random.choice(products)
        pid, _pname, pcat, unit_price, _ = prod
        qty = random.randint(1, 5)
        amount = round(unit_price * qty * random.uniform(0.9, 1.1), 2)
        region = random.choice(REGIONS)
        odate = random_date(order_start, order_end)
        delay_days = random.choices(
            [1, 2, 3, 5, 7, 10, 14], weights=[30, 25, 20, 10, 8, 5, 2]
        )[0]
        sdate = odate + timedelta(days=delay_days)
        status = random.choices(
            ["delivered", "delivered", "delivered", "returned", "cancelled"],
            weights=[70, 10, 5, 10, 5],
        )[0]
        orders.append(
            (oid, cid, pid, pcat, amount, qty, region, str(odate), str(sdate), status)
        )
    c.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)", orders)

    # Employees
    emp_names = [f"{fn} {ln}" for fn in first_names for ln in last_names[:5]][:80]
    employees = []
    for i, name in enumerate(emp_names, 1):
        eid = f"EMP{i:04d}"
        dept = random.choice(DEPARTMENTS)
        hdate = random_date(date(2018, 1, 1), date(2024, 6, 30))
        base = {
            "Engineering": 120000,
            "Sales": 85000,
            "Marketing": 90000,
            "HR": 75000,
            "Finance": 95000,
            "Operations": 80000,
        }[dept]
        salary = round(base * random.uniform(0.85, 1.3))
        is_active = 1 if random.random() > 0.1 else 0
        employees.append((eid, name, dept, str(hdate), salary, is_active))
    c.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?)", employees)

    conn.commit()
    conn.close()
    print(f"✅ Sample database seeded at {DB_PATH}")
    print(
        f"   Customers: 200 | Products: {len(products)} | Orders: 2000 | Employees: {len(employees)}"
    )


if __name__ == "__main__":
    seed()
