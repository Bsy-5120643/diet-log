# 部署指南

目标架构：

```
浏览器 ──▶ Vercel（Next.js）
              │
              └─ /api/* 路由（BFF 代理，服务端转发）
                     │
                     ▼
              Render / Railway（FastAPI）
                     │
                     ▼
                   Neon（PostgreSQL）
```

三个组件都从同一个 Git 仓库的不同子目录部署。

---

## 0. 部署前自检

在推代码之前，本地先确认这几件事：

```bash
cd apps/api
python -m pytest            # 应全绿
python -m alembic heads     # 应只有一个 head

cd ../web
npx tsc --noEmit            # 应无输出
npm run build               # 应 Compiled successfully
```

确认 `.gitignore` 已包含：

```
.env
.env.local
.tmp_import_artifacts/
__pycache__/
*.db
node_modules/
.next/
```

> ⚠️ **`.env` 绝对不能提交**。仓库里只有 `.env.example`。

---

## 1. Neon 数据库

### 1.1 创建项目

1. 注册 [Neon](https://neon.tech) → 新建 Project
2. Region 选离目标用户近的（国内用户可选 Singapore；Neon 目前没有中国大陆节点）
3. 建好后拿到连接串

### 1.2 ⚠️ 必须用 **Pooled** 连接串

Neon 控制台会给出两种连接串：

| 类型 | 主机名特征 | 用途 |
|---|---|---|
| **Pooled**（要用这个） | 含 `-pooler` | 应用运行时连接 |
| Direct | 不含 `-pooler` | 迁移 / 一次性维护 |

```bash
# ✅ 正确
DATABASE_URL=postgresql+psycopg://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require

# ❌ 错误：用了 direct，连接数容易打满
# ❌ 错误：缺 sslmode=require，Neon 会拒绝连接
# ❌ 错误：scheme 写成 postgresql://，SQLAlchemy 会尝试用 psycopg2（我们装的是 psycopg3）
```

**为什么用 `-pooler`**：Render 免费层实例会重启扩容，且我们的连接池配了
`pool_size=5 + max_overflow=0`。走 pooled 端点由 Neon 侧做连接复用，
否则并发稍高就会 `too many clients already`。

### 1.3 免费层限制（要知道）

- 单项目、0.5 GB 存储
- **5 分钟无活动自动挂起**，下次访问冷启动约 1～3 秒
- 所以对外的首次请求会慢，属正常现象

---

## 2. 后端部署到 Render

### 2.1 创建 Web Service

1. 登录 [Render](https://render.com) → New → **Web Service**
2. 连接 GitHub 仓库，选分支
3. 关键配置：

| 配置项 | 值 |
|---|---|
| **Root Directory** | `apps/api` |
| **Environment** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | Free（MVP 阶段够用） |

> **Root Directory 一定要填 `apps/api`**，否则 Render 在仓库根目录找不到 requirements.txt。

### 2.2 Python 版本

Render 默认可能用较老的 Python，而本项目要求 **>= 3.12**。两种指定方式选一个：

- 环境变量：`PYTHON_VERSION=3.12`
- 或仓库里放 `apps/api/.python-version`，内容 `3.12`

### 2.3 数据库迁移（关键，容易漏）

表不会自动创建。三种做法，推荐第一种：

**做法 A（推荐）：写进 Build Command**

```
pip install -r requirements.txt && alembic upgrade head
```

好处是每次部署都会自动补齐新迁移，不会忘。

**做法 B：手动跑一次**
Render 控制台 → 服务 → **Shell** 标签页 → 执行 `alembic upgrade head`

**做法 C：Pre-Deploy Command**
Render 部分套餐支持，填 `alembic upgrade head`

> 不管用哪种，第一次部署后请确认 `daily_health_scores`、`recipes`、
> `ai_recognition_usage` 这些表都存在。

### 2.4 环境变量（Render → Environment）

**必填：**

| 变量 | 示例 | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...@...-pooler...?sslmode=require` | 见 1.2 |
| `JWT_SECRET` | 长随机串 | 生成：`python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CORS_ORIGINS` | `["https://your-app.vercel.app"]` | **必须是 JSON 数组字符串** |

**可选（有默认值，可不填）：**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_TTL_MINUTES` | `15` | |
| `REFRESH_TOKEN_TTL_DAYS` | `30` | |
| `AI_VISION_MODEL` | `qwen-vl-max-latest` | |
| `AI_VISION_TIMEOUT_SECONDS` | `15` | |
| `AI_VISION_MAX_IMAGE_BYTES` | `8388608` | 8MB |
| `LEADERBOARD_MAX_COMPUTE_USERS` | `200` | 榜单补算上限 |
| `LEADERBOARD_MIN_LOGGED_DAYS` | `3` | 进榜门槛 |

**AI 相关（已暂停，可留空）：**

| 变量 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | 留空则 AI 识别接口返回配置错误，不影响其它功能 |

> ⚠️ `CORS_ORIGINS` 最常见的错误：写成 `https://xxx.vercel.app`（没有方括号）。
>
> 这不是"静默降级"，而是**启动直接崩溃**：
> ```
> pydantic_settings.exceptions.SettingsError:
>   error parsing value for field "cors_origins" from source "EnvSettingsSource"
> ```
> 表现是 Render 部署成功但服务起不来、日志里一堆红色。
>
> 正确写法（多个域名）：`["https://a.vercel.app","https://b.vercel.app"]`
> 注意：**结尾不要带斜杠**。

### 2.5 验证后端

部署完成后：

```
https://your-api.onrender.com/health    → {"status":"ok"}
https://your-api.onrender.com/docs      → Swagger UI（19 个接口）
```

> 🐌 **首次访问会等 30～60 秒** —— Render 免费层冷启动，正常现象。后续请求就快了。

---

## 3. 前端部署到 Vercel

### 3.1 创建项目

1. 登录 [Vercel](https://vercel.com) → Add New → Project
2. 导入同一仓库
3. 关键配置：

| 配置项 | 值 |
|---|---|
| **Root Directory** | `apps/web` |
| **Framework Preset** | Next.js（自动识别） |
| **Build Command** | 默认（`npm run build`） |
| **Output Directory** | 默认（`.next`） |

> **Root Directory 一定要填 `apps/web`**。

### 3.2 环境变量（Vercel → Settings → Environment Variables）

| 变量 | 值 | 环境 |
|---|---|---|
| `BACKEND_API_URL` | `https://your-api.onrender.com` | Production（Preview 可同值） |

**两点极其重要：**

1. **变量名不要加 `NEXT_PUBLIC_` 前缀**
   `BACKEND_API_URL` 只在服务端（BFF 路由）里使用。加了 `NEXT_PUBLIC_` 会被打进浏览器包，
   后端地址就暴露了 —— 而我们做 BFF 代理的目的之一就是隐藏它。

2. **结尾不要带斜杠**
   写成 `https://your-api.onrender.com`，不要 `https://your-api.onrender.com/`
   代理里拼接是 `${BACKEND}/api/v1/...`，多一个斜杠会变成 `//api/v1/...`。

### 3.3 关于 CORS 的一个好消息

因为浏览器只跟 Vercel 同域的 `/api/*` 通信，真正的跨域请求发生在
**Vercel 服务端 → Render**，属于服务器到服务器调用，**浏览器同源策略不生效**。

所以：
- 主流程不需要担心 CORS
- 登录用的 httpOnly Cookie 落在 Vercel 域上，是**第一方 Cookie**，不受第三方 Cookie 限制

`CORS_ORIGINS` 仍然建议配上，供以后直连 API（手机 App、第三方集成）或调试 `/docs` 使用。

---

## 4. 上线后验收清单

按顺序检查：

- [ ] `https://your-api.onrender.com/health` 返回 `{"status":"ok"}`
- [ ] `/docs` 能打开，接口数 = 19
- [ ] 前端首页能打开，无控制台报错
- [ ] **注册新账号成功**
- [ ] **登录后刷新页面仍是登录态**（验证 refresh cookie + BFF 正常工作）
- [ ] `/settings/goals` 设置目标成功
- [ ] `/today` 搜索食物 → 添加记录 → 右侧看板**无刷新更新**
- [ ] `/dashboard` 三个 Tab 都能正常切换
- [ ] 复盘 Tab 显示仪表盘与三根得分条
- [ ] 排行榜 Tab 显示榜单，底部有「我的排名」卡片
- [ ] 记录不足 3 天时，排行榜显示「再记 N 天即可上榜」

---

## 5. 常见坑（按出现概率排序）

### 5.1 `too many clients already`
用了 Direct 连接串。换 `-pooler`。

### 5.2 `sslmode` 相关连接失败
`DATABASE_URL` 末尾缺 `?sslmode=require`。

### 5.3 Render 构建时报找不到 requirements.txt
Root Directory 没设成 `apps/api`。

### 5.4 前端 502 / 接口全挂
`BACKEND_API_URL` 没配，或带了结尾斜杠，或后端还在冷启动。

### 5.5 登录后一刷新就掉线
- 检查 `JWT_SECRET` 是否配置（没配可能每次重启都变）
- 检查后端是否真的起来了（Render 免费层会休眠）

### 5.6 CORS 报错
只在直接访问 Render 域名时出现。检查 `CORS_ORIGINS` 是不是合法的 JSON 数组。

### 5.7 表不存在
迁移没跑。见 2.3。

### 5.8 时区不对（记录跑到前一天）
用户时区存在 `users.timezone`，默认 `Asia/Shanghai`。
Vercel / Render 默认是 UTC，但我们所有日期都走 `app/core/time.py` 的
`current_local_date()`，按用户时区算，不受服务器时区影响。
如果发现日期偏移，检查 `tzdata` 是否装上（已在 requirements.txt 里）。

---

## 6. 成本与限制

| 平台 | 免费层限制 | 影响 |
|---|---|---|
| Vercel | 100 GB 带宽 / 月 | 个人项目够用 |
| Render | 750 小时 / 月，15 分钟无活动休眠 | **每次休眠后首次请求慢 30s+** |
| Neon | 0.5 GB，5 分钟无活动挂起 | 冷启动 1～3 秒 |

**要不要升级 Render？**
如果受不了 30 秒冷启动，Render 付费层（约 $7/月）可以常驻实例，
这是最先值得花钱的地方。

---

## 7. 自定义域名（可选）

1. Vercel：Settings → Domains → 添加域名，按提示配 CNAME
2. Render：Settings → Custom Domains → 添加，配 CNAME
3. **加完域名后记得回到 Render 把 `CORS_ORIGINS` 加上新域名**

---

## 8. Railway 作为替代（可选）

如果选 Railway 而不是 Render，差异很小：

| 项 | Render | Railway |
|---|---|---|
| 起始命令 | 控制台填 `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | 同，或用 `Procfile` |
| 端口 | `$PORT` 环境变量 | 同 |
| 根目录 | Root Directory: `apps/api` | Settings → Source → Root Directory |
| 冷启动 | 免费层会休眠 | 免费额度用完后停服，不休眠 |

其它（环境变量、迁移、`DATABASE_URL` 格式）完全一致。
