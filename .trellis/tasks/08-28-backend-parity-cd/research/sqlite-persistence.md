# Research: SQLite 持久化

- **Query**: 原版 server 的 SQLite schema（具体表结构）、在哪一层用（server 端？）、存什么（工程快照？素材？）
- **Scope**: internal
- **Date**: 2026-08-28

## 结论概览

原版 server 端 SQLite 是 **`node:sqlite`（`DatabaseSync`）实现的一个 key-value JSON 文档存储**，**不是**关系型 schema（没有 projects/clips/assets 之类的实体表）。它在 **server 端**，替代旧的「JSON 目录」项目存储。核心是一个 `kv` 表（`k TEXT PRIMARY KEY, v TEXT`），value 是完整 JSON 文档（工程快照 / chat / 生成 job / 已删工程清单）。另有 3 个辅助表：FTS5 全文索引、sqlite-vec 语义向量、迁移状态标记。

文件位置：`server/storage/`。启用由环境变量 `OPENCHATCUT_SQLITE_STORE=1` 触发，且必须完成 phase-2 迁移才生效。

## 表结构（确定，逐文件核对）

### 1. 主表 `kv`（`server/storage/sqlite-store.ts:77-84`）

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);
```

- `v` 是 `JSON.stringify` 后的整个文档（`encode/decode` 见 `sqlite-store.ts:296-297`）。
- 读写原语：`sqliteReadEntry/writeEntry/deleteEntry/readAll/writeAll/deleteProjectEntries`（`sqlite-store.ts:336-397`），同步事务 `sqliteImmediateTransaction`（`BEGIN IMMEDIATE`，`sqlite-store.ts:322`）。

### 2. 迁移状态表 `storage_migration_state`（`server/storage/sqlite-migration.ts:168-175`）

```sql
CREATE TABLE IF NOT EXISTS storage_migration_state (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  state TEXT NOT NULL CHECK (state = 'complete'),
  receipt TEXT NOT NULL
);
```

存一条权威 receipt（JSON），是「SQLite 是否已激活」的权威标记。`RECEIPT_PHASE = 2`（phase 1 = 只导 JSON 目录键；phase 2 = 增加 generation-jobs + deleted-projects 两个辅助键）。

### 3. 全文索引（`server/storage/fulltext-search.ts:35-41`）

```sql
CREATE TABLE IF NOT EXISTS search_state ( k TEXT PRIMARY KEY, sha256 TEXT NOT NULL );
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
  kind, project_id, content, ref, tokenize = 'unicode61'
);
```

- `kind` ∈ `chat|caption|transcript`，`content` 经 jieba 分词（`segmentForIndex`），`bm25()` 排序。
- `search_state` 用 sha256 做「内容哈希门控」避免重复索引。
- 仅对 `chat:*` 和 `project:*` 键建索引。

### 4. 语义向量（`server/storage/semantic-vectors.ts:60-63`）

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS semantic_vectors USING vec0(
  embedding float[<N>], scope_id text, asset_id text, sample_time float,
  source_revision text, scene_id text, scene_start float, scene_end float,
  model_version text
);
```

- `<N>` = `SEMANTIC_INFERENCE_CONTRACT.embeddingDimension`（512，见 `shared/project-store-validation.ts:5`）。
- `sqlite-vec` 扩展，`MATCH` 做 L2（≈余弦）TopK。

## 存储的键（kv 键命名空间）

`shared/project-store-validation.ts:4-11` 定义合法键与项目作用域前缀：
- 合法键正则：`^[a-zA-Z0-9:_-]{1,300}$`（排除 `__proto__/prototype/constructor`）。
- 项目文档：`project:<projectId>`（`PROJECT_DOCUMENT_CAS_KEY`，`validation.ts:225`）。
- chat：`chat:<projectId>`（legacy 前缀 `project|chat|creative-mode|thumb|proposal|versions|jobs:`，`validation.ts:11`）。
- 新式作用域键：`agent-runtime:`、`agent-session-generation:`、`agent-session-chat:`、`agent-session-proposal:`、`agent-session-runtime:`、`agent-session-artifact:`、`agent-artifact:`、`external-proposal:`、`offline-edit-session:`、`project-edit-ownership:`、`review:`、`upload-finalize:`、`export-recovery:`。
- 辅助键（`sqlite-migration-phase-one.ts:16-17`）：
  - `GENERATION_JOBS_KV_KEY = 'generation-jobs:snapshot'`
  - `DELETED_PROJECTS_KV_KEY = 'deleted-projects:v1'`

## 存什么（value 内容）

- **工程快照**：`project:<id>` 的 value 是完整 `ProjectDoc` JSON（时间线、片段、字幕、素材池 assets、designStyle 等）。`textOfProject`（`fulltext-search.ts:78-107`）遍历整个工程文档，把 `{text,startFrame}` 叶节点当 caption cue，其它 `text` 当 transcript，反证「工程文档包含 captions + 词级 transcript」。
- **chat 历史**：`chat:<id>` 的 value 含 `messages[]`（`textOfChat` `:58-76` 逐条取 `text/thinking/tool.name`）。
- **生成 job**：`generation-jobs:snapshot` 存服务端生成/渲染 job 注册表（异步 submit 的 jobId → 状态/结果）。`server/plugins/generation-jobs.ts` `createGenerationJob` 维护。
- **已删工程**：`deleted-projects:v1` 存 tombstone。

素材媒体文件本身**不进 SQLite**——它们存在 `public/media/uploads/`（或 MEDIA_DIR）；SQLite 只存「引用元数据」（src 路径、尺寸、时长、transcript 等）。

## 迁移机制（JSON → SQLite）

`server/storage/sqlite-migration.ts`：`OPENCHATCUT_SQLITE_STORE=1` 触发 `ensureJsonImported`（`BEGIN IMMEDIATE` 事务），把旧 JSON 目录每个 `*.json` 文件（`decodeURIComponent` 反解键）读入 `kv`，写权威 receipt（`storage_migration_state` + `project-store-v1.sqlite3.receipt.json` sidecar），**一个事务内完成**，崩溃只暴露旧后端或完整导入。`sqliteStoreEnabled()`（`sqlite-store.ts:102`）要求 receipt 存在且 `phase >= 2` 才真正切换到 SQLite。

数据库文件路径：`runtimeProfile().rootDir + 'project-store-v1.sqlite3'`（`sqlite-store.ts:60-65`），与旧 `project-store-v1/` 目录并列（不在目录内，避免 JSON 扫描读到外来文件）。

## 迁移清理

`cleanupLegacyJson`（`sqlite-store.ts:210-249`）：迁移后按 receipt 里的 `sources`（路径+sha256）逐个校验后删除旧 JSON 文件，仅删「路径和哈希都匹配」的文件。

## 事实 vs 推断

**确定的事实**：schema 是 5 张表（`kv`、`storage_migration_state`、`search_fts`、`search_state`、`semantic_vectors`），全部从代码直接读取。它是 server 端 key-value JSON 文档库，非关系型。激活需 `OPENCHATCUT_SQLITE_STORE=1` + phase-2 receipt。

**推断**：Python 后端「SQLite 持久化」对齐时，不需要复刻 5 张表；最小对齐点是**一张 `kv(k,v)` 表存 JSON 工程文档 + 一个权威迁移/版本标记**。FTS5/vec0 是搜索增强（C/D 阶段可选）。原版 value 是「整个 ProjectDoc JSON 快照」，与 Python 后端 `persist.py`（JSON 文件）的粒度一致，差异只在存储介质（SQLite 单表 vs 单文件 JSON）。
