// 前端内置演示工程：真实媒体 src 指向 /media/*（Vite public/）。
// 用于前后端联调：打开即有内容，AI 编辑直接落在 browser 权威 store 上。
import type { ProjectDoc } from './types'

export function demoProject(): ProjectDoc {
  return {
    docVersion: 1,
    version: 1,
    assets: [
      { id: 'a1', name: '花 (flower)', kind: 'video', src: '/media/sample-1.mp4', durationInFrames: 150, width: 1280, height: 720 },
      { id: 'a2', name: 'Sintel 预告片', kind: 'video', src: '/media/sample-2.mp4', durationInFrames: 1560, width: 854, height: 480 },
      { id: 'a3', name: '背景音乐', kind: 'audio', src: '/media/track-1.mp3', durationInFrames: 600 },
      { id: 'a4', name: 'Logo', kind: 'image', src: '/media/logo.png', width: 512, height: 512 },
    ],
    mediaFolders: [],
    timelines: [
      {
        id: 'tl1',
        name: '宣传片',
        fps: 30,
        width: 1920,
        height: 1080,
        items: [
          { id: 'i1', track: 'V1', startFrame: 0, durationInFrames: 150, name: '花', kind: 'video', src: '/media/sample-1.mp4', sourceAssetId: 'a1' },
          { id: 'i2', track: 'V1', startFrame: 150, durationInFrames: 210, name: 'Sintel A', kind: 'video', src: '/media/sample-2.mp4', sourceAssetId: 'a2', srcInFrame: 0 },
          { id: 'i3', track: 'V1', startFrame: 360, durationInFrames: 180, name: 'Sintel B', kind: 'video', src: '/media/sample-2.mp4', sourceAssetId: 'a2', srcInFrame: 300 },
          { id: 'i4', track: 'V2', startFrame: 60, durationInFrames: 90, name: 'Logo 叠层', kind: 'image', src: '/media/logo.png', sourceAssetId: 'a4' },
          { id: 'i5', track: 'A1', startFrame: 0, durationInFrames: 540, name: 'BGM', kind: 'audio', src: '/media/track-1.mp3', sourceAssetId: 'a3', volume: 0.5 },
        ],
        transitions: [{ id: 'tr1', incomingItemId: 'i2', transType: 'crossfade', durationInFrames: 15 }],
        markers: [
          { id: 'm1', name: '高潮点', frame: 120, color: '#f59e0b' },
          { id: 'm2', name: '重点段落', startFrame: 30, endFrame: 150, color: '#3b82f6' },
        ],
        captions: {
          enabled: true,
          items: [
            { startFrame: 0, endFrame: 90, text: '大家好，这是演示工程' },
            { startFrame: 90, endFrame: 210, text: '真实视频轨道 + AI 编辑' },
          ],
        },
      },
    ],
    activeTimelineId: 'tl1',
  }
}
