/**
 * 浏览器工具 schema 唯一真源。
 *
 * Java 只透传这里提交的 function-calling schema，不解析剪辑领域参数。schema 必须与浏览器
 * handler 同步维护，否则模型会生成浏览器无法执行的调用。`undo/redo` 是用户历史操作，不能
 * 放进 Proposal 草稿，因此不在协商工具中。
 */

export interface AgentFunctionSchema {
  type: 'function'
  function: {
    name: string
    description: string
    parameters: JsonObjectSchema
    'x-read-only': boolean
    'x-requires-approval': boolean
  }
}

interface JsonObjectSchema {
  type: 'object'
  properties: Record<string, Record<string, unknown>>
  required?: readonly string[]
  additionalProperties: false
}

type ToolOptions = {
  readOnly?: boolean
  requiresApproval?: boolean
  required?: readonly string[]
}

// 这些小型构造器只负责生成 JSON Schema，不做运行时业务校验。
// 运行时参数仍由 executeTool 统一收敛，避免模型 schema 和浏览器执行逻辑各自演化。
const str = (description: string, values?: readonly string[]) => ({
  type: 'string', description, ...(values ? { enum: values } : {}),
})
const num = (description: string, minimum?: number) => ({
  type: 'number', description, ...(minimum === undefined ? {} : { minimum }),
})
const bool = (description: string) => ({ type: 'boolean', description })
const obj = (description: string) => ({ type: 'object', description })
const arr = (items: Record<string, unknown>, description: string) => ({ type: 'array', items, description })

function tool(
  name: string,
  description: string,
  properties: Record<string, Record<string, unknown>>,
  options: ToolOptions = {},
): AgentFunctionSchema {
  // 扩展字段会原样发送给 Java；Java 只读取只读/审批元数据，不解析具体编辑参数。
  return {
    type: 'function',
    function: {
      name,
      description,
      parameters: {
        type: 'object', properties,
        ...(options.required ? { required: options.required } : {}),
        additionalProperties: false,
      },
      'x-read-only': options.readOnly === true,
      'x-requires-approval': options.requiresApproval === true,
    },
  }
}

const itemId = str('片段 ID')
const action = (values?: readonly string[]) => str('操作类型', values)

export const SUPPORTED_TOOL_SCHEMAS: readonly AgentFunctionSchema[] = [
  tool('read_timeline', '读取当前时间线、片段、转场、字幕和标记', {}, { readOnly: true }),
  tool('read_project', '读取工程、时间线列表和素材池', {}, { readOnly: true }),
  tool('read_transcript', '读取指定片段的转写与删除状态', { itemId }, { readOnly: true, required: ['itemId'] }),
  tool('edit_track', '创建、更新、删除、紧凑排列或切换轨道状态', {
    action: action(['create', 'update', 'delete', 'toggle', 'tighten']), track: str('轨道 ID'),
    kind: str('新轨道类型'), name: str('轨道名称'), flag: str('轨道标志'),
    value: bool('标志值'), patch: obj('轨道属性补丁'),
  }, { required: ['action', 'track'] }),
  tool('edit_item', '批量新增、更新或删除时间线片段', {
    adds: arr(obj('新增片段参数'), '新增列表'), updates: arr(obj('更新片段参数'), '更新列表'),
    deletes: arr(obj('删除片段参数'), '删除列表'),
  }),
  tool('remove_item', '删除指定片段', { itemId }, { required: ['itemId'] }),
  tool('clear_timeline', '清空当前时间线', {}),
  tool('duplicate_item', '复制指定片段', { itemId }, { required: ['itemId'] }),
  tool('split_clip', '在指定帧切分片段', { itemId, atFrame: num('时间线绝对帧', 0) }, { required: ['itemId', 'atFrame'] }),
  tool('move_item', '移动片段到轨道或起始帧', {
    itemId, track: str('目标轨道'), startFrame: num('目标起始帧', 0),
  }, { required: ['itemId'] }),
  tool('set_item_timing', '设置片段开始、时长和源入点', {
    itemId, startFrame: num('起始帧', 0), durationInFrames: num('持续帧数', 1), srcInFrame: num('源入点帧', 0),
  }, { required: ['itemId'] }),
  tool('update_item_props', '更新片段通用属性', { itemId, patch: obj('片段属性补丁') }, { required: ['itemId', 'patch'] }),
  tool('set_clip_volume', '设置片段音量', { itemId, volume: num('音量') }, { required: ['itemId', 'volume'] }),
  tool('set_clip_fade', '设置片段淡入淡出', {
    itemId, fadeInFrames: num('淡入帧数', 0), fadeOutFrames: num('淡出帧数', 0),
  }, { required: ['itemId'] }),
  tool('set_clip_transform', '设置片段变换', { itemId, patch: obj('缩放、位移、旋转和透明度补丁') }, { required: ['itemId', 'patch'] }),
  tool('set_clip_filters', '设置片段滤镜', { itemId, patch: obj('亮度、对比度、饱和度和模糊补丁') }, { required: ['itemId', 'patch'] }),
  tool('set_clip_speed', '设置片段播放速度', { itemId, rate: num('播放倍率') }, { required: ['itemId', 'rate'] }),
  tool('set_clip_zoom', '设置片段缩放效果', { itemId, patch: obj('缩放效果补丁') }, { required: ['itemId', 'patch'] }),
  tool('set_clip_effects', '设置片段效果栈', { itemId, effects: arr(obj('效果定义'), '效果列表') }, { required: ['itemId', 'effects'] }),
  tool('add_transition', '添加片段转场', {
    incomingItemId: str('入场片段 ID'), transType: str('转场类型'), durationInFrames: num('持续帧数', 0),
  }, { required: ['transType'] }),
  tool('edit_transition', '更新或删除转场', {
    action: action(['update', 'remove']), transitionId: str('转场 ID'), patch: obj('转场补丁'),
  }, { required: ['action', 'transitionId'] }),
  tool('edit_captions', '设置、更新或隐藏字幕', {
    action: action(['set', 'update', 'set_hidden']), captions: obj('完整字幕数据'), enabled: bool('是否启用'),
    patch: obj('字幕补丁'), hidden: bool('是否隐藏'), position: str('字幕位置'), fontSize: num('字幕字号'),
    color: str('字幕颜色'), outlineColor: str('描边颜色'), outlineWidth: num('描边宽度'),
  }, { required: ['action'] }),
  tool('set_keyframe', '设置关键帧', {
    itemId, prop: str('动画属性'), frame: num('片段内帧', 0), value: num('属性值'), easing: str('缓动名称'),
  }, { required: ['itemId', 'prop', 'frame', 'value'] }),
  tool('remove_keyframe', '删除关键帧', {
    itemId, prop: str('动画属性'), frame: num('片段内帧', 0),
  }, { required: ['itemId', 'prop', 'frame'] }),
  tool('clear_keyframes', '清除关键帧', { itemId, prop: str('可选动画属性；缺失时清除全部') }, { required: ['itemId'] }),
  tool('manage_markers', '新增、更新或删除标记', {
    action: action(['add', 'update', 'remove']), marker: obj('新标记'), markerId: str('标记 ID'), patch: obj('标记补丁'),
  }, { required: ['action'] }),
  tool('select_clips', '选择一个或多个片段', {
    action: action(['select', 'select_many', 'select_all']), itemId, ids: arr(str('片段 ID'), '片段 ID 列表'),
    mode: str('选择模式', ['replace', 'add', 'toggle']),
  }, { required: ['action'] }),
  tool('manage_media_pool', '管理素材池资源和文件夹', {
    action: action(), asset: obj('素材定义'), folder: obj('文件夹定义'), assetId: str('素材 ID'),
    folderId: str('文件夹 ID'), ids: arr(str('素材 ID'), '素材 ID 列表'), assetIds: arr(str('素材 ID'), '素材 ID 列表'),
    name: str('名称'), newName: str('新名称'), kind: str('素材类型'), src: str('新媒体地址'), favorite: bool('是否收藏'),
  }, { required: ['action'] }),
  tool('list_audio', '列出素材池音频', {}, { readOnly: true }),
  tool('add_audio', '把素材池音频加入音轨', {
    assetId: str('素材 ID'), audioName: str('素材名称'), name: str('素材名称'), track: str('目标音轨'),
    startFrame: num('起始帧', 0), durationInFrames: num('持续帧数', 1),
  }),
  tool('set_item_transcript', '设置片段逐词转写', {
    itemId, words: arr(obj('包含 text/startMs/endMs/speaker 的词'), '逐词转写'), generationId: str('转写任务 ID'),
  }, { required: ['itemId', 'words'] }),
  tool('clean_script', '清理脚本填充词和停顿', {
    itemId, removeFillers: bool('是否移除填充词'), silenceFrames: num('压缩后停顿帧数', 0), cutPadFrames: num('切口保护帧数', 0),
  }, { required: ['itemId'] }),
  tool('delete_text', '按词索引删除转写内容', {
    itemId, wordIndices: arr(num('词索引', 0), '要删除的词索引'),
  }, { required: ['itemId', 'wordIndices'] }),
  tool('manage_transcript', '修词、重命名说话人、调整顺序或设置变体', {
    action: action(), itemId, wordIdx: num('词索引', 0), wordIndex: num('词索引', 0), text: str('修正文本'),
    fromSpeaker: str('原说话人'), toSpeaker: str('新说话人'), variants: arr(obj('转写变体'), '转写变体'),
    afterWordIdx: num('前一个词索引', 0), maxMs: num('最大间隔毫秒', 0),
    playOrder: arr(num('词索引', 0), '播放顺序'), track: str('轨道 ID'),
    orderedIds: arr(str('片段 ID'), '片段顺序'), starts: obj('片段起始帧映射'),
  }, { required: ['action', 'itemId'] }),
  tool('slip_item', '平移片段源窗口', { itemId, deltaInFrames: num('源窗口偏移帧数') }, { required: ['itemId', 'deltaInFrames'] }),
  tool('set_background_fill', '设置片段背景填充', {
    itemId, enabled: bool('是否启用'), strength: num('强度'),
  }, { required: ['itemId', 'enabled'] }),
  tool('replace_media', '替换片段媒体源', {
    itemId, src: str('新媒体地址'), sourceAssetId: str('素材 ID'), sourceRevision: str('素材版本'),
  }, { required: ['itemId', 'src'] }),
  tool('update_watermark', '更新工程水印', {
    enabled: bool('是否启用'), text: str('水印文字'), position: str('水印位置'), opacity: num('透明度'),
    fontSize: num('水印字号'), color: str('水印颜色'), margin: num('边距'),
  }),
  tool('set_item_denoise', '设置片段降噪结果', {
    itemId, denoisedSrc: str('降噪媒体地址'), strength: num('降噪强度'),
  }, { required: ['itemId', 'denoisedSrc'] }),
  tool('set_reframe_keyframe', '设置或删除智能重构图关键帧', {
    action: action(['set', 'remove']), itemId, frame: num('片段内帧', 0), focalPointX: num('焦点 X'),
    focalPointY: num('焦点 Y'), magnification: num('放大倍率'),
  }, { required: ['itemId', 'frame'] }),
  tool('manage_timelines', '创建、切换、复制、删除或重命名时间线', {
    action: action(), timelineId: str('时间线 ID'), newId: str('新时间线 ID'), name: str('时间线名称'),
    timeline: obj('完整时间线'), activate: bool('创建后是否激活'), width: num('画布宽度', 1),
    height: num('画布高度', 1), fit: str('适配方式', ['contain', 'cover']), hidden: bool('是否隐藏'),
  }, { required: ['action'] }),
  tool('edit_asset', '更新、替换、合并或删除素材池资产', {
    action: action(), assetId: str('素材 ID'), patch: obj('素材补丁'), src: str('新媒体地址'),
    duplicateId: str('重复素材 ID'), canonicalId: str('标准素材 ID'),
  }, { required: ['action', 'assetId'] }),
  tool('set_design_style', '设置或修补工程设计风格', {
    action: action(['set', 'patch']), style: obj('完整设计风格'), patch: obj('设计风格补丁'),
  }),
  tool('set_full_state', '批量更新当前时间线状态', { patch: obj('时间线属性补丁') }, { required: ['patch'] }),
  tool('set_aspect_ratio', '设置画布宽高和适配方式', {
    width: num('画布宽度', 1), height: num('画布高度', 1), fit: str('适配方式', ['contain', 'cover']),
  }, { required: ['width', 'height'] }),
  tool('change_cam', '设置多机位组或切换决策', {
    action: action(['set_groups', 'add_decision']), groups: arr(obj('多机位组'), '多机位组列表'),
    groupId: str('多机位组 ID'), fromFrame: num('开始帧', 0), toFrame: num('结束帧', 1), angleId: str('机位 ID'),
  }, { required: ['action'] }),
  tool('manage_link_group', '设置音视频链接组', {
    action: action(['add', 'set']), group: obj('链接组'), groups: arr(obj('链接组'), '链接组列表'),
  }, { required: ['action'] }),
  tool('submit_export', '保存当前工程并导出成片', {
    // 编码枚举必须与 jimanweb/origin-model 两侧一致，未知编码会在入口被拒绝。
    format: str('导出格式', ['video', 'audio']), codec: str('编码器', ['h264', 'vp8', 'mp3', 'wav']),
    fps: num('输出帧率', 1), name: str('输出文件名'),
  }, { requiresApproval: true, required: ['format'] }),
] as const

export const SUPPORTED_TOOL_NAMES: readonly string[] = SUPPORTED_TOOL_SCHEMAS.map((schema) => schema.function.name)

/** submit_export 在 bridge 执行，其余 47 项必须由 executeTool handler 覆盖。 */
export const BROWSER_EDIT_TOOL_NAMES: readonly string[] = SUPPORTED_TOOL_NAMES.filter((name) => name !== 'submit_export')
