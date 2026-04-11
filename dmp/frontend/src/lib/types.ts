export interface Track {
  id: string
  title: string
  artist: string
  album: string
  album_artist?: string
  track_number?: number
  disc_number?: number
  duration?: number
  date?: string
  genre?: string
  source: 'local' | 'qobuz' | 'upnp'
  uri: string
  artwork_url?: string
}

export interface QueueItem {
  position: number
  track: Track
  is_current: boolean
}

export interface HistoryEntry {
  track: Track
  played_at: string
}

export interface Playlist {
  name: string
  last_modified?: string
}

export interface PlaybackStatus {
  state: 'play' | 'pause' | 'stop'
  current_track: Track | null
  position: number
  duration: number
  queue_length: number
  random: boolean
  repeat: boolean
}

export interface LibraryStats {
  artists: number
  albums: number
  songs: number
  db_playtime: number
}

export interface AlbumInfo {
  name: string
  artist: string
  date?: string
  track_count?: number
  artwork_url?: string
}

export type ViewTab = 'library' | 'queue' | 'history' | 'playlists'
export type LibraryMode = 'artists' | 'albums' | 'tracks' | 'search'
