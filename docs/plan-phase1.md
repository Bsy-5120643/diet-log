# 运动饮食记录网站 · 第一阶段方案（待确认，未开工）

技术栈：Next.js + FastAPI + PostgreSQL（Vercel + Render + Neon 免费层）
第一阶段目标：注册登录 → 设置每日目标 → 搜索食物 → 添加记录 → 查看当日汇总

---

## 0. 范围边界

**做**：邮箱注册登录、每日热量/三大营养素目标设置、食物搜索（含自定义食物）、饮食记录增删改、当日汇总（总量 + 剩余 + 按餐次分布）。

**不做（但模型预留）**：
- 运动消耗记录 —— 产品名带"运动"，但第一阶段只做饮食闭环。`goals` 表预留 `tdee_kcal`、`activity_level`，第二阶段加 `exercise_logs` 表即可，不动现有结构。
- 体脂/体重曲线、历史趋势图、社交/分享、拍照识别、第三方饮食数据 API 对接。
- 邮箱验证、找回密码 —— 上线前必须补，MVP 阶段可后置于「能跑通闭环」之后。

**品牌**：不参考任何现有产品的 Logo/配色/布局。产品名与视觉体系单独定，代号先用 `diet-log`。

---

## 1. 项目目录结构建议

采用**单仓库（monorepo）双应用**，不用 pnpm workspace 的复杂配置，Vercel 与 Render 各自指定 Root Directory 即可：

```
diet-log/
├── apps/
│   ├── web/                        # Next.js 15（App Router + TS + Tailwind）
│   └── api/                        # FastAPI
├── docs/
│   ├── plan-phase1.md              # 本文档
│   └── food-seed.md                # 种子食物数据字段口径说明
├── .github/workflows/ci.yml
├── render.yaml                     # Render Blueprint（后端服务声明）
└── README.md
```

### apps/api（FastAPI）

```
apps/api/
├── app/
│   ├── main.py                     # app 实例、CORS、路由挂载、异常处理器
│   ├── core/
│   │   ├── config.py               # pydantic-settings 读取环境变量
│   │   ├── security.py             # 密码哈希、JWT 签发/校验
│   │   └── deps.py                 # get_db / get_current_user 依赖注入
│   ├── db/
│   │   ├── base.py                 # DeclarativeBase
│   │   ├── session.py              # engine / SessionLocal / pool 参数
│   │   └── seed.py                 # 种子食物导入脚本
│   ├── models/
│   │   ├── user.py  food.py  food_alias.py  food_serving.py
│   │   ├── goal.py  food_log.py  refresh_token.py
│   ├── schemas/                    # Pydantic 出入参模型（与 models 分离）
│   │   ├── auth.py  goal.py  food.py  log.py  summary.py
│   ├── routers/
│   │   ├── auth.py  goals.py  foods.py  logs.py  summary.py
│   └── services/
│       └── nutrition.py            # 营养计算唯一实现处
├── alembic/
│   ├── versions/
│   └── env.py
├── tests/
├── pyproject.toml                  # 用 uv 管理依赖
└── Dockerfile                      # Render 用 Docker 或原生 Python 均可
```

### apps/web（Next.js）

```
apps/web/
├── app/
│   ├── layout.tsx  globals.css
│   ├── page.tsx                    # 落地页（未登录）
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── onboarding/goals/page.tsx   # 首次登录强制引导设置目标
│   ├── (app)/
│   │   ├── layout.tsx              # 底部导航 + 会话校验
│   │   ├── today/page.tsx          # ★ 核心页
│   │   ├── search/page.tsx
│   │   ├── foods/new/page.tsx      # 自定义食物（兜底入口，必须有）
│   │   └── settings/goals/page.tsx
│   └── api/[...path]/route.ts      # BFF 代理：转发 FastAPI，管理 httpOnly Cookie
├── components/
│   ├── ui/                         # 自有设计系统：Button/Input/Sheet/Dialog...
│   ├── nutrition/CalorieRing.tsx  MacroBar.tsx
│   ├── log/MealSection.tsx  LogItem.tsx
│   ├── food/FoodSearchBar.tsx  PortionPicker.tsx
│   └── layout/BottomNav.tsx
├── lib/
│   ├── api/client.ts               # fetch 封装 + 401 自动刷新重试
│   ├── api/{auth,foods,logs,summary}.ts
│   ├── date.ts                     # ★ 本地日期 ⇄ YYYY-MM-DD，全站唯一入口
│   └── nutrition.ts                # 展示层换算与四舍五入
├── types/api.d.ts                  # 由 openapi-typescript 从后端 schema 生成
├── middleware.ts                   # 未登录重定向
└── tailwind.config.ts
```

**关键点**：`lib/date.ts` 是全站唯一处理日期的地方，任何组件禁止直接 `new Date().toISOString()`。

---

## 2. 前后端职责划分

| 职责 | 归属 | 说明 |
|---|---|---|
| 页面渲染、路由、表单交互 | Next.js | App Router，服务端组件做首屏，客户端组件做交互 |
| 表单校验（格式/必填） | 前后端都做 | 前端给即时反馈，后端做权威校验 |
| **营养计算** | **FastAPI 唯一实现** | 服务端算完落库，前端只做展示与四舍五入 |
| **营养快照** | FastAPI | 记录创建时把当时食物的每 100g 营养值写进 log 行 |
| 认证签发/校验、密码哈希 | FastAPI | 密钥只在后端 |
| 会话 Cookie 管理 | Next.js BFF | Cookie 落在前端域，避免跨站第三方 Cookie 被拦截 |
| 数据权限（只能看自己的记录） | FastAPI | 每个查询强制带 `user_id` 过滤 |
| 分页 / 搜索排序 | FastAPI | — |
| 数据库迁移 | Alembic（后端） | 前端不碰 DB |
| 单位换算（1 碗 = 150g） | 前端展示 + 后端权威 | 前端换算后提交克数，后端按克数算 |

**三条硬规则**：
1. 前端所有请求走同域 `/api/...` 由 BFF 代理转发，**不在浏览器里直连 Render 域名**（解决跨站 Cookie + 隐藏后端地址）。
2. 食物库的营养值可以被修改，但**历史记录不能跟着变** —— 用快照字段固化。
3. 所有金额/营养数值用 `numeric`，不用 `float`，避免汇总时小数点漂移。

---

## 3. 第一阶段页面与 API

### 3.1 页面（7 个）

| 路由 | 作用 | 备注 |
|---|---|---|
| `/` | 落地页，未登录可见 | 极简：一句话价值主张 + 注册/登录 CTA |
| `/register` | 邮箱注册 | 邮箱 + 密码 + 昵称 |
| `/login` | 登录 | 记住我（影响 refresh 有效期） |
| `/onboarding/goals` | 首次登录后强制设置目标 | 提供「按体重/活动量自动估算」和「手动填」两种入口 |
| `/today` | ★ 当日记录 + 汇总 | 顶部日期切换（禁止未来日期）、热量环、三大营养素条、按早/午/晚/加餐分组的记录列表、行内改份量与删除、悬浮按钮进搜索 |
| `/search` | 搜索食物并添加 | 防抖搜索、历史/常用置顶、选份量（克 / 常见单位）→ 选餐次 → 提交后回 `/today` |
| `/settings/goals` | 修改每日目标 | 与 onboarding 复用同一套表单组件 |
| `/foods/new` | 自定义食物 | 兜底入口：搜不到时 30 秒内自己建一个 |

### 3.2 API（`/api/v1`，共 15 个）

**认证**
```
POST   /auth/register      {email, password, nickname?}  -> 201 {user}
POST   /auth/login         {email, password}             -> {access_token, refresh_token, user}
POST   /auth/refresh       {refresh_token}               -> {access_token}
POST   /auth/logout        -> 204（服务端吊销 refresh）
GET    /auth/me            -> {user, goal}
```

**目标**
```
GET    /goals/current                  -> 当前生效目标
PUT    /goals/current  {daily_calories, protein_g, fat_g, carb_g, effective_from?}
                                       -> upsert，带生效日期以便历史可追溯
```

**食物**
```
GET    /foods/search?q=&page=&size=    -> {items:[{id,name,brand,kcal_per_100g,...}], total}
GET    /foods/{id}                     -> 详情（含 servings 列表）
GET    /foods/recent?limit=10          -> 我最近/最常记的，进搜索页时置顶
POST   /foods  {name, brand?, kcal_per_100g, protein_g, fat_g, carb_g, servings[]}
                                       -> 创建自定义食物（默认仅自己可见）
```

**饮食记录**
```
GET    /logs?date=YYYY-MM-DD           -> 当日全部记录（含快照与计算值）
POST   /logs  {food_id, meal_type, quantity_g, logged_date, note?}
                                       -> 服务端计算并落库，返回完整 log
PATCH  /logs/{id}  {quantity_g?, meal_type?, note?}
DELETE /logs/{id}                      -> 204
```

**汇总**
```
GET    /summary/daily?date=YYYY-MM-DD
       -> {goals:{...}, consumed:{kcal, protein_g, fat_g, carb_g},
           remaining:{...}, percent:{...}, by_meal:{breakfast:{kcal,count},...}}
```

**统一约定**：错误返回 `{"detail": {"code": "...", "message": "..."}}`；分页统一 `{items, total, page, size}`；token 过期返回 401 + `code=token_expired`（前端据此触发 refresh）。

---

## 4. 数据库表设计（7 张）

### `users`
```
id              uuid PK default gen_random_uuid()
email           text NOT NULL UNIQUE      -- 落库前统一 lower()
password_hash   text NOT NULL
nickname        text
timezone        text NOT NULL default 'Asia/Shanghai'   -- 为跨时区/旅行预留
is_active       boolean NOT NULL default true
created_at      timestamptz NOT NULL default now()
updated_at      timestamptz NOT NULL default now()
```

### `goals`（历史可追溯，不覆盖写）
```
id               uuid PK
user_id          uuid FK -> users(id) ON DELETE CASCADE
effective_from   date NOT NULL                -- 生效日期
daily_calories   numeric(7,1) NOT NULL
protein_g        numeric(6,1) NOT NULL
fat_g            numeric(6,1) NOT NULL
carb_g           numeric(6,1) NOT NULL
tdee_kcal        numeric(7,1)                 -- 预留：加运动模块后用作基准
activity_level   text                         -- 预留
created_at       timestamptz
UNIQUE (user_id, effective_from)
INDEX (user_id, effective_from DESC)
```
> 取「某天生效的目标」= `effective_from <= :date ORDER BY effective_from DESC LIMIT 1`。

### `foods`（统一「每 100g 可食部」口径）
```
id             uuid PK
name           text NOT NULL
brand          text
kcal_per_100g  numeric(7,2) NOT NULL
protein_g      numeric(6,2) NOT NULL   -- 以下均为每 100g
fat_g          numeric(6,2) NOT NULL
carb_g         numeric(6,2) NOT NULL
source         text NOT NULL            -- 'seed' | 'usda' | 'user'
created_by     uuid FK -> users(id)     -- 自定义食物归属，公共数据为 NULL
is_public      boolean NOT NULL default false
created_at / updated_at
INDEX (name)                            -- 另建 pg_trgm GIN 索引加速模糊搜索
```

### `food_aliases`（口语名 / 同义词，搜索命中的关键）
```
id       uuid PK
food_id  uuid FK -> foods(id) ON DELETE CASCADE
alias    text NOT NULL
UNIQUE (food_id, alias)
INDEX (alias)
```
> 例：番茄 ← 西红柿 / 圣女果 / cherry tomato。

### `food_servings`（常见份量单位）
```
id         uuid PK
food_id    uuid FK -> foods(id) ON DELETE CASCADE
unit_name  text NOT NULL      -- '个' | '碗' | '杯' | '份' | '片'
grams      numeric(8,2) NOT NULL
is_default boolean default false
```
> 例：米饭 1 碗 = 150g；鸡蛋 1 个 = 50g。这条直接决定录入体验。

### `food_logs`（核心，含快照）
```
id                       uuid PK
user_id                  uuid FK -> users(id) ON DELETE CASCADE
food_id                  uuid FK -> foods(id) ON DELETE RESTRICT
logged_date              date NOT NULL          -- ★ 冗余存"用户本地日期"，不做时区转换
meal_type                text NOT NULL          -- CHECK IN ('breakfast','lunch','dinner','snack')
quantity_g               numeric(8,2) NOT NULL
-- 快照：记录当时的每 100g 营养值
snapshot_kcal_per_100g   numeric(7,2) NOT NULL
snapshot_protein_g       numeric(6,2) NOT NULL
snapshot_fat_g           numeric(6,2) NOT NULL
snapshot_carb_g          numeric(6,2) NOT NULL
-- 计算结果：落库，便于汇总与审计
kcal                     numeric(8,2) NOT NULL
protein_g                numeric(7,2) NOT NULL
fat_g                    numeric(7,2) NOT NULL
carb_g                   numeric(7,2) NOT NULL
note                     text
created_at / updated_at
INDEX (user_id, logged_date)            -- 最高频查询
INDEX (user_id, food_id)
```

### `refresh_tokens`
```
id          uuid PK
user_id     uuid FK -> users(id) ON DELETE CASCADE
token_hash  text NOT NULL UNIQUE
expires_at  timestamptz NOT NULL
revoked     boolean NOT NULL default false
user_agent  text
created_at  timestamptz
```

**计算口径**：`kcal = snapshot_kcal_per_100g * quantity_g / 100`，保留 2 位；汇总时 `SUM` 后再四舍五入到 1 位展示。

---

## 5. 最容易出错的 3 个点

### 坑 1：日期与时区 ——「今天」到底是哪一天

**症状**：晚上 8 点后记的一餐，刷新后跑到"明天"去了；或者跨天时当日汇总突然少一条。
**根因**：Vercel / Render / Neon 默认都是 UTC。前端 `new Date().toISOString()` 会先转 UTC 再截断，东八区 10/25 20:00 得到的是 `2026-10-25T12:00:00Z` 还算对，但 10/26 07:00 会变成 `2026-10-25T23:00:00Z` —— 直接记到前一天。后端若再用 `now()::date` 判定"今天"，时区跟着 DB session 走，二次漂移。
**对策**：
- 前端 `lib/date.ts` 唯一出口：用 `getFullYear/getMonth/getDate` 拼 `YYYY-MM-DD`，**禁用 `toISOString().slice(0,10)`**。
- 后端所有接口收 `date` 字符串，直接存 `DATE` 列；**禁止在业务查询里用 `now()` 判定"今天"**。
- `users.timezone` 预留，第二阶段做跨时区旅行场景。
**验收**：系统时区分别设为 UTC 和 Asia/Shanghai 各跑一遍；手动构造 23:30 与 00:10 两条记录，确认归属日期正确。

### 坑 2：食物数据与中文搜索 —— 冷启动就劝退

**症状**：搜"西红柿"搜不到"番茄"；搜"鸡胸肉"出来一堆无关结果；用户想记的食物大半搜不到，用一次就走。
**根因**：Postgres 默认全文检索不支持中文分词（`to_tsvector` 对中文基本失效）；种子数据只有学名、没有别名和常见份量；外部数据源口径混乱（有的按份、有的按 100g，可食部 vs 生重）。
**对策**：
- 种子数据统一「每 100g 可食部」，先手工准备 300–800 条中国常见食物（主食、家常菜、外卖常见项、水果、乳制品、蛋白来源），先覆盖长尾搜索。
- `food_aliases` 打底：口语名、别名、常见写法；搜索时 `name ILIKE '%q%' OR EXISTS(alias ILIKE '%q%')`。
- 索引用 `pg_trgm` + GIN，别一上来就搞中文分词插件（zhparser / pg_jieba 在 Neon 免费层不一定装得上）。
- **必须有「自定义食物」兜底**，且入口要显眼（搜索无结果时直接引导创建）。
**验收**：准备 20 条高频搜索词清单，逐条验证能搜到且目标结果排在前 3。

### 坑 3：部署与鉴权链路 —— 本地好使，上线 401

**症状**：本地登录一切正常，部署到 Vercel + Render 后一直 401 或无限刷新；数据库隔几分钟第一次请求必然超时。
**根因**：
- Vercel（`*.vercel.app`）与 Render（`*.onrender.com`）是不同站，后端 `Set-Cookie` 属于第三方 Cookie，Safari/Firefox 直接拦、Chrome 也在收紧。
- CORS 配错：`allow_origins=['*']` 与 `allow_credentials=True` 不能同时用。
- Neon 免费层：连接数有限，且计算实例空闲后会缩容到 0（冷启动 1–3 秒）；SQLAlchemy 默认连接池会拿到已被服务端关闭的死连接。
**对策**：
- 走 Next.js BFF 代理（`/app/api/[...path]/route.ts`），Cookie 落在前端自己的域上，天然同站；后端 CORS 只允许 Vercel 域。
- JWT 密钥、DB URL 全走环境变量；密码用 bcrypt（注意 passlib 与 bcrypt 4.x 的兼容告警、以及 72 字节输入上限）。
- Neon 用 **pooled** 连接串 + `sslmode=require`；SQLAlchemy 设 `pool_pre_ping=True`、`pool_recycle=300`、`pool_size` 调小。
**验收**：无痕窗口完整走一遍「注册 → 登录 → 刷新页面 → 加一条记录」；Render 冷启动后连续发两次请求确认第二次不报错。

---

## 6. 建议的落地顺序

1. 后端骨架 + Alembic 建表 + 种子食物脚本
2. 认证全链路（注册/登录/刷新/登出） + BFF 代理打通
3. 目标设置（onboarding + settings）
4. 食物搜索 + 自定义食物
5. 记录增删改 + 当日汇总

每一步都可独立验证，避免最后一次性联调。

---

## 7. 需要你确认的几个决策点

1. **登录方式**：第一阶段只做邮箱+密码，还是直接上第三方（微信/Google）？
2. **目标设置**：只做「手动填具体数值」，还是也要「输入身高体重活动量 → 自动估算」？后者体验好但要多写一套 BMR/TDEE 逻辑。
3. **食物数据来源**：我们自己整理种子 CSV（300–800 条），还是你已有数据源？
4. **项目名与视觉基调**：定下来我就不再用代号。
5. 上述第 5 节三个坑的对策，是否有你想换的走法（尤其是 BFF 代理 vs 直接用自定义域名让前后端同站）。
