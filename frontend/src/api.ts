import type { RoomState, Session } from './types'

const localProtocol = window.location.protocol === 'https:' ? 'https' : 'http'
const localWsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
const localHost = window.location.hostname || 'localhost'

export const API_BASE =
  import.meta.env.VITE_API_BASE ||
  `${localProtocol}://${localHost}:8000`

export const WS_BASE =
  import.meta.env.VITE_WS_BASE ||
  `${localWsProtocol}://${localHost}:8000`

async function json<T>(response: Response): Promise<T> {
  const body = await response.json()
  if (!response.ok) {
    throw new Error(body.detail || 'Request failed')
  }
  return body as T
}

export async function createRoom(name: string, maxPlayers: number, mode: 'individual' | 'teams', deckCount: number) {
  return json<{ roomCode: string; playerId: string; rejoinPin: string; state: RoomState }>(
    await fetch(`${API_BASE}/rooms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, maxPlayers, mode, deckCount }),
    }),
  )
}

export async function joinRoom(code: string, name: string, rejoinPin?: string) {
  return json<{ roomCode: string; playerId: string; rejoinPin: string; state: RoomState }>(
    await fetch(`${API_BASE}/rooms/${encodeURIComponent(code.toUpperCase())}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, rejoinPin: rejoinPin || undefined }),
    }),
  )
}

export async function closeRoom(code: string, name: string, rejoinPin: string) {
  return json<{ closed: boolean }>(
    await fetch(`${API_BASE}/rooms/${encodeURIComponent(code.toUpperCase())}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, rejoinPin }),
    }),
  )
}

export async function resumeRoom(session: Session) {
  return json<{ state: RoomState }>(
    await fetch(`${API_BASE}/rooms/${session.roomCode}/players/${session.playerId}`),
  )
}
