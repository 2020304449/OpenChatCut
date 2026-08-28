# Research: src/editor/ 的 EditorCore（问题 3）

- **Query**: 原版 EditorCore 如何持有「项目权威」（state 唯一真源）、command 如何 apply、undo/redo 是什么机制（快照 snapshot 还是命令反演）。
- **Scope**: internal
- **Date**: 2026-08-28

## 一、state 唯一真源：ProjectDoc + historyReduce

### 1.1 入口 hook

`src/editor/store.ts` 的 `useEditor(initial: ProjectDoc)`（store.ts:15-54）：

```ts
const [h, dispatch] = useReducer(historyReduce, { past: [], present: initial, future: [] });
const doc = h.present;
const commands = useMemo<EditorCommands>(() => buildCommands(dispatch, () => docRef.current), []);
```

- **唯一真源就是 `h.present`（一个 `ProjectDoc`）**。`dispatch` 来自 `useReducer`，所有命令、UI、agent 工具最终都汇聚到这一个 reducer。
- 对外暴露：`state`（active timeline）、`doc`（整个 ProjectDoc）、`commands`（命令集）、`canUndo`/`canRedo`、`getUndoTarget`/`getRedoTarget`（给 agent 的 undo/redo 工具用，store.ts:42-43）。

### 1.2 ProjectDoc 结构

`src/editor/projectTypes.ts:8-17`：

```ts
interface ProjectDoc {
  version: typeof CURRENT_PROJECT_VERSION;
  assets: MediaAsset[];        // 项目级媒体池，所有 timeline 共享
  mediaFolders: MediaFolder[];
  timelines: Timeline[];       // 多 timeline
  activeTimelineId: string;
  designStyle?: DesignStyle;   // 品牌设计系统
}
```

- `activeTimeline(doc)`（projectTypes.ts:20）：按 `activeTimelineId` 取活动 timeline，stale 则回退第一个。
- `activeEditorState(doc)`（projectTypes.ts:27）：把项目级 `assets` 附到活动 timeline（派生的，**不落盘**，projectTypes.ts 注释 + reducerProject.ts:23-26 `stamp` 会剥掉 `assets`）。

## 二、command 如何 apply

### 2.1 命令层 → action 层

- 命令接口 `EditorCommands`（`src/editor/storeCommands.ts:41-208`）：100+ 命令（addMediaItem、setItemVolume、addTransition、createTimeline、applyDoc、undo/redo 等）。
- `buildCommands(dispatch, getDoc)`（`src/editor/storeCommandBuilder.ts:40-444`）把每个命令实现为对 `dispatch(action)` 的调用。命令不直接改状态，而是构造 `AtomicAction` 或 `BatchAction` 交给 reducer。
- `uid`（storeCommandBuilder.ts:35）：id 用 `crypto.randomUUID()`，保证跨 session 唯一（注释解释避免 IndexedDB 重载后 id 碰撞）。
- 多步命令（如 `createCaptionTrack` storeCommandBuilder.ts:380）用 `batch` 动作打包成一个 undo 步。

### 2.2 动作 → 状态（reducer 层）

`src/editor/reduce.ts`（barrel）导出三层：
1. `projectReduce`（`src/editor/reducerProject.ts:28`）—— **项目级 reducer**，路由分发：
   - `batch` 动作：逐个 reduce（reducerProject.ts:29-31）。
   - 项目级动作（`tl.*`/`pool.*`/`design.*`，reducerProject.ts:19/36-246）。
   - 其余 per-timeline 动作：作用于 `activeTimeline`（reducerProject.ts:248-256），`reduce`（`src/editor/reducerTimeline.ts`）执行，`stamp` 回写 identity，最后 `sequenceGraphError` 校验序列图合法性。
2. `historyReduce`（`src/editor/reducerHistory.ts:42`）—— 历史包装（见下）。
3. `reduce`（`src/editor/reducerTimeline.ts`）—— 单 timeline reducer（clip/track/transcript 操作）。

**关键特性**：`projectReduce` 是**纯函数**，输入 `(ProjectDoc, Action)` 输出新 `ProjectDoc`（immutable），无副作用。非法操作（如序列图错误、重叠 track）直接返回原 doc（`return p`），从而「无效动作不进历史」。

## 三、undo/redo：快照（snapshot）机制，不是命令反演

`src/editor/reducerHistory.ts` 明确采用 **whole-project 快照栈**：

```ts
interface History {
  past: ProjectDoc[];   // 完整项目快照数组
  present: ProjectDoc;
  future: ProjectDoc[];
  gesture?: 'open' | 'pushed';
}
const HISTORY_LIMIT = 100;
```

- `historyReduce`（reducerHistory.ts:42-70）：
  - `undo`（:46-50）：`present ← past.pop()`，`future ← [oldPresent, ...future]`。
  - `redo`（:51-55）：`present ← future.shift()`，`past.push(oldPresent)`。
  - mutation 动作（`MUTATING.has(action.type)`，reducerActions.ts）：`past.push(oldPresent)`，`present ← next`，清空 `future`。
  - 非 mutation 动作（select / `tl.switch`，:69）：只换 present，**不进历史**。
- **命令反演 vs 快照**：这是**纯快照**——undo 直接恢复上一个完整 `ProjectDoc` 对象，不执行逆命令。代价是内存（每步存整份 doc，限 100 步），换来实现简单与正确性。

### 3.1 gesture 合并（拖拽优化）

- `history.beginGesture` / `history.endGesture`（reducerHistory.ts:44-45）标记连续手势。
- 逻辑（reducerHistory.ts:58-68）：手势期间第一次 mutation 正常 push 历史并置 `gesture:'pushed'`；后续 tick 只替换 present（`{...h, present: next, future: []}`），不再 push。
- 目的（reducerHistory.ts:13-18 注释）：音量 0→2 若每 0.05 步都 push 会瞬间灌爆 100 步历史，undo 只能退一格。合并后 undo 回到「拖拽前」。

## 四、agent 工具如何落到 EditorCore

- 工具执行器 `executeTool`（`src/agent/tools.ts:300-315`）按工具名懒加载 executor，executor 收到 `AgentContext`（`src/agent/context.ts:41-72`）。
- `AgentContext` 的核心就是 `commands: EditorCommands` + `getState` + `getDoc`（context.ts:42-46）—— 即工具直接调用 `EditorCommands`（`ctx.commands.setItemVolume(...)` 等），由 `buildCommands` 转成 action → reducer → 更新 `ProjectDoc`。
- 这就是「**工具 == 命令**」的映射（tools.ts:76-78 注释：`Canonical tool definitions ... Each one executes against the EditorCore command layer (tool == command)`）。

## 五、Draft 草稿引擎（proposal 机制用）

`src/editor/store.ts:71-98`：

```ts
export function makeDraft(base: ProjectDoc): DraftEngine {
  let doc = base;
  let pending: AnyAction[] = [];
  const dispatch: ProjectDispatch = (a) => {
    if (isHistoryControlAction(a)) return;   // 草稿里历史/手势无意义
    const next = projectReduce(doc, a);
    if (next !== doc) { doc = next; pending.push(a); }
  };
  return {
    commands: buildCommands(dispatch, () => doc),
    getState: () => activeEditorState(doc),
    getDoc: () => doc,
    takeActions: () => { const out = pending; pending = []; return out; },
  };
}
export function replayActions(base, actions) { return actions.reduce((d, a) => projectReduce(d, a), base); }
```

- `makeDraft` 复用同一套 `buildCommands` + `projectReduce`，但对**草稿副本**操作，并**记录 actions**，不碰真库、不进历史。
- 应用到真库时用 `replayActions(base, actions)`（store.ts:96）重放，或直接 `applyDoc`（`dispatch({type:'tl.setDoc', doc})`，storeCommandBuilder.ts:102）。

## 六、persist：编辑态 vs 持久化边界

- `ProjectDoc` 内存态是唯一编辑真源；持久化在 `src/persist/projectStore.ts`（server-backed + IndexedDB cache），保存的是**文档快照**（`saveProject(projectId, doc)`）。
- undo/redo 历史、选区、手势状态**不落盘**，是纯内存态。

## Related Spec / 文件索引

- `src/editor/reducerTimeline.ts` —— 单 timeline reducer。
- `src/editor/reducerActions.ts` —— action 类型 + `MUTATING` 集合。
- `src/editor/reducerClipActions.ts` / `reducerTrackActions.ts` / `reducerTranscriptActions.ts` —— 各类 action 的 reducer 分支。
- `src/agent/context.ts` —— `AgentContext`（工具与 EditorCore 的粘合层）。

## Caveats / Not Found

- 未逐条核对 `MUTATING` 集合（`src/editor/reducerActions.ts`）具体包含哪些 action type；但「mutation 进历史、非 mutation 不进」的机制已确认。
- `HISTORY_LIMIT=100` 是固定值（reducerHistory.ts:21），未发现可配置项。
- 命令 100+ 个的完整清单未在本文复述，详见 `storeCommands.ts` 接口定义。
