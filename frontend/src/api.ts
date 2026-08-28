import type { RoomState, Session } from './types'

const isLocal =
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'

export const API_BASE = isLocal
  ? 'http://localhost:8000'
  : 'https://card-game-api.purplecoast-1e73a5fa.westus2.azurecontainerapps.io'

export const WS_BASE = isLocal
  ? 'ws://localhost:8000'
  : 'wss://card-game-api.purplecoast-1e73a5fa.westus2.azurecontainerapps.io'

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

export type AdminGame = {
  code: string
  status: 'open' | 'in_progress' | 'completed'
  hostName: string
  playerCount: number
  botCount: number
  connectedCount?: number
  roundNumber: number
  finishedAt: string | null
  storage: string
}

export async function adminListGames(adminKey: string) {
  return json<{ games: AdminGame[] }>(
    await fetch(`${API_BASE}/admin/games`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ adminKey }),
    }),
  )
}

export async function adminDeleteGame(code: string, adminKey: string) {
  return json<{ closed: boolean }>(
    await fetch(`${API_BASE}/admin/games/${encodeURIComponent(code)}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ adminKey }),
    }),
  )
}

export async function adminCleanupGames(adminKey: string, scope: 'active' | 'completed' | 'all') {
  return json<{ activeClosed: number; completedDeleted: number }>(
    await fetch(`${API_BASE}/admin/games/cleanup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ adminKey, scope }),
    }),
  )
}

export async function resumeRoom(session: Session) {
  return json<{ state: RoomState }>(
    await fetch(`${API_BASE}/rooms/${session.roomCode}/players/${session.playerId}`),
  )
}
