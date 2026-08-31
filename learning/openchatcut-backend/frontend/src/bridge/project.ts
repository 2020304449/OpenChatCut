// 项目持久化客户端：browser 权威 state → jimanweb Redis 落盘 / 加载（多项目，统一 POST）。
import type { ProjectDoc } from '../editor/types'

export interface ProjectMeta {
  projectId: string
  name: string
}

export async function loadProject(projectId: string): Promise<ProjectDoc | null> {
  const res = await fetch('/api/project/load', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projectId }),
  })
  if (!res.ok) return null
  // jimanweb 统一 ResultResponse 包装：{ code, data, success }，exists/state 在 data 里
  const body = (await res.json()) as { success?: boolean; data?: { exists?: boolean; state?: ProjectDoc } }
  const d = body.data
  return d?.exists && d?.state ? d.state : null
}

export async function saveProject(projectId: string, doc: ProjectDoc): Promise<void> {
  await fetch('/api/project/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projectId, state: doc }),
  })
}

export async function listProjects(): Promise<ProjectMeta[]> {
  const res = await fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  if (!res.ok) return []
  const body = (await res.json()) as { success?: boolean; data?: { projects?: ProjectMeta[] } }
  return body.data?.projects ?? []
}
