"""端到端闭环演示：搜索 -> 添加 -> 汇总 -> 累加 -> 别名搜索。

用法（cwd = apps/api，DATABASE_URL 指向已建表的库）：
    python scripts/_e2e_demo.py
"""

from fastapi.testclient import TestClient

import app.models  # noqa: F401
from app.core import security
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.user import User

db = SessionLocal()
user = User(
    email="e2e@example.com",
    password_hash=security.hash_password("Password123"),
    timezone="Asia/Shanghai",
)
db.add(user)
db.commit()
db.refresh(user)

app.dependency_overrides[get_db] = lambda: db
client = TestClient(app)

token = client.post(
    "/api/v1/auth/login",
    json={"email": "e2e@example.com", "password": "Password123"},
).json()["tokens"]["access_token"]
headers = {"Authorization": "Bearer " + token}

print()
print("=== 1. 搜索「鸡胸肉」===")
result = client.get("/api/v1/foods?q=鸡胸肉", headers=headers).json()
item = result["items"][0]
print("  命中", result["total"], "条:", item["name"], item["energy_kcal"], "kcal/100g")
food_id = item["id"]

print()
print("=== 2. 添加 150g 到午餐 ===")
entry = client.post(
    "/api/v1/food-entries",
    json={"food_id": food_id, "meal_type": "lunch", "quantity_g": 150},
    headers=headers,
).json()
print(
    "  ",
    entry["food_name"],
    str(entry["quantity_g"]) + "g ->",
    entry["energy_kcal"], "kcal / 蛋白",
    entry["protein_g"],
)

print()
print("=== 3. 当日汇总 ===")
summary = client.get("/api/v1/summary", headers=headers).json()
print("  热量", summary["consumed"]["energy_kcal"], "| 蛋白", summary["consumed"]["protein_g"])
print("  记录数", summary["entry_count"], "| 午餐", summary["by_meal"]["lunch"])
print("  不完整字段", summary["incomplete_fields"])

print()
print("=== 4. 再加一份，验证累加 ===")
client.post(
    "/api/v1/food-entries",
    json={"food_id": food_id, "meal_type": "lunch", "quantity_g": 150},
    headers=headers,
)
summary2 = client.get("/api/v1/summary", headers=headers).json()
print(
    "  热量",
    summary2["consumed"]["energy_kcal"],
    "(预期 399.0) | 蛋白",
    summary2["consumed"]["protein_g"],
)

print()
print("=== 5. 别名搜索「西红柿」===")
alias_result = client.get("/api/v1/foods?q=西红柿", headers=headers).json()
names = [i["name"] for i in alias_result["items"]]
print("  命中", names)
if alias_result["items"]:
    hit = alias_result["items"][0]
    print("  match_on =", hit["match_on"], "| matched_alias =", hit["matched_alias"])

print()
print("=== 6. 删除一条后汇总回落 ===")
entries = client.get("/api/v1/food-entries", headers=headers).json()["items"]
client.delete("/api/v1/food-entries/" + entries[0]["id"], headers=headers)
summary3 = client.get("/api/v1/summary", headers=headers).json()
print("  剩余记录数", summary3["entry_count"], "| 热量", summary3["consumed"]["energy_kcal"])
