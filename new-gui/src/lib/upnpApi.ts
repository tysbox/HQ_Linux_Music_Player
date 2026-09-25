import { request as req } from './http'

export type ServerId = 'soundgenic' | 'asset'

export interface UPnPServer {
  id: ServerId
  name: string
  ip: string
  reachable: boolean
}

export interface UPnPContainer {
  id: string
  title: string
  child_count?: string
}

export interface UPnPBrowseResult {
  server: string
  object_id: string
  containers: UPnPContainer[]
  tracks: any[]
  total: number
}

export const upnpApi = {
  servers: () =>
    req<{ servers: UPnPServer[] }>('/api/upnp/servers'),

  status: (server: ServerId = 'soundgenic') =>
    req<{ id: string; name: string; ip: string; reachable: boolean }>(
      `/api/upnp/status?server=${server}`
    ),

  browse: (id = '0', server: ServerId = 'soundgenic') =>
    req<UPnPBrowseResult>(
      `/api/upnp/browse?id=${encodeURIComponent(id)}&server=${server}`
    ),

  search: (q: string, server: ServerId = 'soundgenic', containerId = '0') =>
    req<{ server: string; query: string; tracks: any[]; total: number }>(
      `/api/upnp/search?q=${encodeURIComponent(q)}&server=${server}&container_id=${encodeURIComponent(containerId)}`
    ),
}
