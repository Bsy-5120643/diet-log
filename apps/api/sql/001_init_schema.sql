-- ============================================================================
-- 饮食记录 · 第一版 Schema (PostgreSQL)
-- 口径约定：foods 表所有营养字段均为「每 100g 可食部」；
--          food_entries 表同名营养字段为「本次实际摄入绝对值」。
-- ============================================================================

-- 中文模糊搜索需要三元组索引，普通 B-tree 对 LIKE '%关键词%' 无效
CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- ----------------------------------------------------------------------------
-- users：用户基本信息
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    email          text        NOT NULL,
    password_hash  text        NOT NULL,
    nickname       varchar(50),
    timezone       varchar(64) NOT NULL DEFAULT 'Asia/Shanghai',
    is_active      boolean     NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_users_email       UNIQUE (email),
    CONSTRAINT ck_users_email_lower CHECK (email = lower(email))
);

COMMENT ON TABLE  users          IS '用户主表';
COMMENT ON COLUMN users.email    IS '统一小写存储，登录唯一键';
COMMENT ON COLUMN users.timezone IS 'IANA 时区名，后续跨时区场景使用';


-- ----------------------------------------------------------------------------
-- goals：每日热量与三大营养素目标
-- 用 effective_from 生效日期而非覆盖写，保证历史汇总可追溯
-- ----------------------------------------------------------------------------
CREATE TABLE goals (
    id             uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    effective_from date         NOT NULL,
    energy_kcal    numeric(7,1) NOT NULL,
    protein_g      numeric(6,1) NOT NULL,
    fat_g          numeric(6,1) NOT NULL,
    carb_g         numeric(6,1) NOT NULL,
    fiber_g        numeric(6,1),
    sodium_mg      numeric(8,1),
    source         varchar(16)  NOT NULL DEFAULT 'manual',
    created_at     timestamptz  NOT NULL DEFAULT now(),
    updated_at     timestamptz  NOT NULL DEFAULT now(),

    CONSTRAINT uq_goals_user_effective_from UNIQUE (user_id, effective_from),
    CONSTRAINT ck_goals_energy_positive     CHECK (energy_kcal > 0),
    CONSTRAINT ck_goals_macros_non_negative CHECK (protein_g >= 0 AND fat_g >= 0 AND carb_g >= 0),
    CONSTRAINT ck_goals_source_valid        CHECK (source IN ('manual', 'calculated'))
);

COMMENT ON TABLE  goals                IS '每日营养目标，按生效日期分段';
COMMENT ON COLUMN goals.effective_from IS '生效起始日期；取某天目标 = effective_from <= date 的最新一条';
COMMENT ON COLUMN goals.source         IS 'manual=手填, calculated=由身高体重活动量估算';


-- ----------------------------------------------------------------------------
-- foods：食物库（公共字典）
-- 营养值统一按每 100g 存储；不含任何份量信息
-- ----------------------------------------------------------------------------
CREATE TABLE foods (
    id           uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    name         varchar(200) NOT NULL,
    brand        varchar(100),
    barcode      varchar(32),
    -- ↓↓↓ 以下均为「每 100g 可食部」口径 ↓↓↓
    energy_kcal  numeric(7,2) NOT NULL,
    protein_g    numeric(6,2) NOT NULL,
    fat_g        numeric(6,2) NOT NULL,
    carb_g       numeric(6,2) NOT NULL,
    fiber_g      numeric(6,2),
    sodium_mg    numeric(8,2),
    -- ↑↑↑ 以上均为「每 100g 可食部」口径 ↑↑↑
    source       varchar(16)  NOT NULL DEFAULT 'seed',
    created_by   uuid         REFERENCES users(id) ON DELETE SET NULL,
    is_public    boolean      NOT NULL DEFAULT false,
    is_active    boolean      NOT NULL DEFAULT true,
    created_at   timestamptz  NOT NULL DEFAULT now(),
    updated_at   timestamptz  NOT NULL DEFAULT now(),

    CONSTRAINT ck_foods_values_non_negative CHECK (
        energy_kcal >= 0 AND protein_g >= 0 AND fat_g >= 0 AND carb_g >= 0
    ),
    CONSTRAINT ck_foods_source_valid CHECK (source IN ('seed', 'usda', 'user')),
    CONSTRAINT ck_foods_user_owned   CHECK (
        (source = 'user' AND created_by IS NOT NULL) OR (source <> 'user')
    )
);

COMMENT ON TABLE  foods             IS '食物库，每 100g 营养值，无份量概念';
COMMENT ON COLUMN foods.energy_kcal IS '每 100g 热量 kcal';
COMMENT ON COLUMN foods.source      IS 'seed=内置种子, usda=外部导入, user=用户自建';
COMMENT ON COLUMN foods.is_active   IS '软删除标记，禁止物理删除（food_entries 有 RESTRICT 引用）';

CREATE UNIQUE INDEX uq_foods_barcode ON foods (barcode) WHERE barcode IS NOT NULL;


-- ----------------------------------------------------------------------------
-- food_entries：饮食记录
-- 份量语义 + 营养快照 + 计算结果 全部落在本行
-- ----------------------------------------------------------------------------
CREATE TABLE food_entries (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id   uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    food_id   uuid NOT NULL REFERENCES foods(id) ON DELETE RESTRICT,

    entry_date date        NOT NULL,
    meal_type  varchar(16) NOT NULL,

    -- 份量：quantity_g 是权威值，其余三个字段仅用于还原「用户当时怎么录的」
    quantity_g             numeric(8,2) NOT NULL,
    serving_unit           varchar(16),
    serving_count          numeric(6,2),
    serving_grams_per_unit numeric(8,2),

    -- 快照：创建记录时食物的每 100g 营养值，固化后不随 foods 变更
    snapshot_energy_kcal numeric(7,2) NOT NULL,
    snapshot_protein_g   numeric(6,2) NOT NULL,
    snapshot_fat_g       numeric(6,2) NOT NULL,
    snapshot_carb_g      numeric(6,2) NOT NULL,
    snapshot_fiber_g     numeric(6,2),
    snapshot_sodium_mg   numeric(8,2),

    -- 计算结果：snapshot × quantity_g / 100，保留 2 位
    energy_kcal numeric(8,2) NOT NULL,
    protein_g   numeric(7,2) NOT NULL,
    fat_g       numeric(7,2) NOT NULL,
    carb_g      numeric(7,2) NOT NULL,
    fiber_g     numeric(7,2),
    sodium_mg   numeric(9,2),

    note       text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_food_entries_meal_type_valid CHECK (
        meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')
    ),
    CONSTRAINT ck_food_entries_quantity_positive CHECK (quantity_g > 0),
    CONSTRAINT ck_food_entries_computed_consistent CHECK (
        energy_kcal = round(quantity_g * snapshot_energy_kcal / 100, 2)
        AND protein_g = round(quantity_g * snapshot_protein_g / 100, 2)
        AND fat_g     = round(quantity_g * snapshot_fat_g / 100, 2)
        AND carb_g    = round(quantity_g * snapshot_carb_g / 100, 2)
    )
);

COMMENT ON TABLE  food_entries                 IS '饮食记录，份量与营养快照均在本行';
COMMENT ON COLUMN food_entries.entry_date      IS '用户本地日期，不做时区转换';
COMMENT ON COLUMN food_entries.quantity_g      IS '权威份量值（克），所有计算基于它';
COMMENT ON COLUMN food_entries.serving_unit    IS '录入单位：g / 个 / 碗 / 杯 / 份';
COMMENT ON COLUMN food_entries.snapshot_energy_kcal IS '记录当时的每 100g 热量，避免食物库更新导致历史漂移';


-- ============================================================================
-- 索引
-- ============================================================================

-- 1) 登录查询：WHERE email = ? 每次登录都执行，唯一约束已自动建 B-tree
--    （上面 UNIQUE (email) 已覆盖，无需额外建）

-- 2) 取「某天生效的目标」：WHERE user_id = ? AND effective_from <= ? ORDER BY effective_from DESC
--    唯一约束 (user_id, effective_from) 已建复合索引，PG 可反向扫描，无需再建 DESC 版本

-- 3) 食物模糊搜索：LIKE '%关键词%' 前置通配符使 B-tree 失效，必须用 pg_trgm
CREATE INDEX ix_foods_name_trgm ON foods USING gin (name gin_trgm_ops);

-- 4) 公共食物库筛选（可选，数据量大后再加）
CREATE INDEX ix_foods_public_active ON foods (is_public, is_active) WHERE is_active = true;

-- 5) 最高频查询：某用户某天的全部记录 + 当日汇总聚合
CREATE INDEX ix_food_entries_user_date ON food_entries (user_id, entry_date DESC);

-- 6) 「我最近/最常吃的食物」：按 food 聚合或排序
CREATE INDEX ix_food_entries_user_food ON food_entries (user_id, food_id);

-- 7) 外键索引：PostgreSQL 不会自动为外键建索引，缺了会导致
--    删除 foods 时全表扫描 food_entries 做引用检查
CREATE INDEX ix_food_entries_food_id ON food_entries (food_id);
