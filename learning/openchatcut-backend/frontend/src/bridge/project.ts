// 项目持久化客户端：browser 权威 state → server SQLite 落盘 / 加载。
import type { ProjectDoc } from '../editor/types'

export async function loadProject(): Promise<ProjectDoc | null> {
  const res = await fetch('/api/project')
  if (!res.ok) return null
  const body = (await res.json()) as { exists: boolean; state?: ProjectDoc }
  return body.exists && body.state ? body.state : null
}

export async function saveProject(doc: ProjectDoc): Promise<void> {
  await fetch('/api/project', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state: doc }),
  })
}
