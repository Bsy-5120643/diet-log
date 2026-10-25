# diet-log

运动饮食记录网站。拍照之外，主打「手动记录 → 健康评分 → 榜单 PK」这条留存闭环。

## 功能

| 模块 | 说明 |
|---|---|
| 账号 | 注册 / 登录，JWT + httpOnly Cookie，前端 BFF 代理转发 |
| 目标 | Mifflin-St Jeor 计算 BMR / TDEE，减脂缺口上限 20%（安全兜底） |
| 食物库 | 模糊搜索，同时匹配名称与别名（搜「西红柿」能命中「番茄」） |
| 饮食记录 | 五档餐次（含夜宵），服务端做营养快照与换算 |
| 数据看板 | 热量环、三大营养素进度、近 7 天摄入与体重趋势 |
| 健康指数 | 0-100 分：热量达标 40 + 宏量 30 + 记录习惯 30，**摄入低于 BMR 直接 0 分** |
| 排行榜 | 近 7 天平均分排名，需记录满 3 天才进榜，返回内容已脱敏 |

## 技术栈

- 后端：FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL（Neon）
- 前端：Next.js 15 App Router + Tailwind + SWR + Recharts
- 部署：Vercel（前端）/ Render（后端）/ Neon（数据库）

## 本地启动

### 后端

```bash
cd apps/api
cp .env.example .env          # 填 DATABASE_URL 和 JWT_SECRET
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

接口文档：<http://localhost:8000/docs>

### 前端

```bash
cd apps/web
npm install
echo "BACKEND_API_URL=http://localhost:8000" > .env.local
npm run dev
```

## 测试

```bash
cd apps/api && python -m pytest     # 后端
cd apps/web && npx tsc --noEmit     # 前端类型检查
```

## 设计要点

- 食物库缺失的营养数据一律存 `NULL` 而非 `0`，汇总按 0 计入但 UI 显示为 `-`
  —— 「真实 0」与「数据缺失」必须可区分
- 所有日期计算走用户时区，不用 UTC，避免跨零点记错天
- 营养值统一 `numeric`，杜绝浮点累计误差
- 健康指数评分规则是纯函数（`app/services/health_score.py`），零 IO，可完整单测

## 部署

见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。
