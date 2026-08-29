import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, Copy, LogOut, MessageCircle, Play, RefreshCw, RotateCcw, Search, Send, ShieldCheck, Trash2, Users, Wifi, WifiOff, X } from 'lucide-react'
import { adminCleanupGames, adminDeleteGame, adminListGames, closeRoom, createRoom, joinRoom, resumeRoom, WS_BASE } from './api'
import type { AdminGame } from './api'
import type { Card, RoomState, Session } from './types'

const SESSION_KEY = 'friends-spades-session'

function normalizeRoomState(state: RoomState): RoomState {
  // Keep the UI usable while an older room snapshot or an API revision is
  // briefly present during deployment. New collections must never crash render.
  return {
    ...state,
    biddingStage: state.biddingStage ?? 'estimates',
    teamBidOrder: Array.isArray(state.teamBidOrder) ? state.teamBidOrder : [],
    teamRanking: Array.isArray(state.teamRanking) ? state.teamRanking : [],
    chatMessages: Array.isArray(state.chatMessages) ? state.chatMessages : [],
    players: (state.players ?? []).map((player) => ({
      ...player,
      contributionTricks: player.contributionTricks ?? 0,
    })),
  }
}

function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveSession(session: Session | null) {
  if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  else localStorage.removeItem(SESSION_KEY)
}

export default function App() {
  const [session, setSession] = useState<Session | null>(loadSession)
  const [state, setState] = useState<RoomState | null>(null)
  const [error, setError] = useState('')
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!session) return
    resumeRoom(session)
      .then(({ state }) => setState(normalizeRoomState(state)))
      .catch(() => {
        saveSession(null)
        setSession(null)
        setState(null)
      })
  }, [session])

  useEffect(() => {
    if (!session) return
    let stopped = false
    let retryTimer: number | undefined

    const connect = () => {
      if (stopped) return
      const ws = new WebSocket(`${WS_BASE}/ws/${session.roomCode}/${session.playerId}`)
      socketRef.current = ws
      ws.onopen = () => {
        setConnected(true)
        setError('')
      }
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === 'state') setState(normalizeRoomState(msg.state))
        if (msg.type === 'error') setError(msg.message)
      }
      ws.onclose = (event) => {
        setConnected(false)
        if (event.code === 4404 || event.code === 4400) {
          stopped = true
          saveSession(null)
          setSession(null)
          setState(null)
          setError(event.code === 4400 ? 'The host closed that game.' : 'That room session has expired. Create a room or join again.')
          return
        }
        if (!stopped) retryTimer = window.setTimeout(connect, 1200)
      }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      stopped = true
      if (retryTimer) clearTimeout(retryTimer)
      socketRef.current?.close()
    }
  }, [session])

  const send = (payload: Record<string, unknown>) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) {
      setError('Connection is not ready yet')
      return
    }
    setError('')
    socketRef.current.send(JSON.stringify(payload))
  }

  const enter = (roomCode: string, playerId: string, rejoinPin: string, initial: RoomState) => {
    const next = { roomCode, playerId, rejoinPin }
    saveSession(next)
    setState(normalizeRoomState(initial))
    setSession(next)
  }

  const leave = () => {
    socketRef.current?.close()
    saveSession(null)
    setSession(null)
    setState(null)
    setError('')
  }

  if (!session || !state) {
    return <Home onEnter={enter} error={error} setError={setError} />
  }

  return (
    <Game
      state={state}
      playerId={session.playerId}
      rejoinPin={session.rejoinPin}
      connected={connected}
      error={error}
      send={send}
      leave={leave}
    />
  )
}

function Home({
  onEnter,
  error,
  setError,
}: {
  onEnter: (roomCode: string, playerId: string, rejoinPin: string, state: RoomState) => void
  error: string
  setError: (value: string) => void
}) {
  const [createName, setCreateName] = useState('')
  const [joinName, setJoinName] = useState('')
  const [code, setCode] = useState('')
  const [joinPin, setJoinPin] = useState('')
  const [closeCode, setCloseCode] = useState('')
  const [closeName, setCloseName] = useState('')
  const [closePin, setClosePin] = useState('')
  const [maxPlayers, setMaxPlayers] = useState(2)
  const [deckCount, setDeckCount] = useState(2)
  const [mode, setMode] = useState<'individual' | 'teams'>('individual')
  const [teamCount, setTeamCount] = useState(2)
  const [busy, setBusy] = useState(false)
  const [showAdmin, setShowAdmin] = useState(false)
  const teamCounts = Array.from({ length: Math.max(0, Math.floor(maxPlayers / 2) - 1) }, (_, index) => index + 2)
    .filter((count) => maxPlayers % count === 0)
  const teamEligible = teamCounts.length > 0

  useEffect(() => {
    if (!teamEligible && mode === 'teams') setMode('individual')
    if (teamEligible && !teamCounts.includes(teamCount)) setTeamCount(teamCounts[0])
  }, [maxPlayers, mode, teamCount, teamEligible])

  const create = async () => {
    if (!createName.trim()) return setError('Enter your name')
    setBusy(true)
    try {
      const requiredDecks = maxPlayers >= 13 ? 4 : maxPlayers >= 8 ? 3 : maxPlayers >= 4 ? 2 : deckCount
      const result = await createRoom(createName.trim(), maxPlayers, mode, requiredDecks, teamCount)
      onEnter(result.roomCode, result.playerId, result.rejoinPin, result.state)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create room')
    } finally {
      setBusy(false)
    }
  }

  const join = async () => {
    if (!joinName.trim() || !code.trim()) return setError('Enter your name and room code')
    setBusy(true)
    try {
      const result = await joinRoom(code.trim(), joinName.trim(), joinPin.trim())
      onEnter(result.roomCode, result.playerId, result.rejoinPin, result.state)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not join room')
    } finally {
      setBusy(false)
    }
  }

  const closeExisting = async () => {
    if (!closeCode.trim() || !closeName.trim() || !/^\d{6}$/.test(closePin)) return setError('Enter the room code, host name, and 6-digit game rejoin PIN')
    if (!window.confirm(`Permanently close room ${closeCode.toUpperCase()}?`)) return
    setBusy(true)
    try {
      await closeRoom(closeCode.trim(), closeName.trim(), closePin)
      setCloseCode('')
      setCloseName('')
      setClosePin('')
      setError('')
      window.alert('Game closed and its stored snapshot deleted.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not close room')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="home-shell">
      <section className="hero">
        <div className="brand-mark">♠</div>
        <div>
          <p className="eyebrow">Your Table</p>
          <h1> SPADES </h1>
          <p className="hero-copy">
            13 rounds · wild Joker · 5 bags = −50 · live multiplayer
          </p>
        </div>
        <button className="admin-nav" onClick={() => setShowAdmin((value) => !value)}>{showAdmin ? <ArrowLeft size={17} /> : <ShieldCheck size={17} />}{showAdmin ? 'Back to games' : 'Admin'}</button>
      </section>

      {error && <div className="error-banner">{error}</div>}

      {showAdmin ? <AdminPanel /> : <>
      <section className="home-grid">
        <div className="panel">
          <p className="panel-kicker">HOST</p>
          <h2>Create a room</h2>
          <label>
            Your name
            <input value={createName} onChange={(e) => setCreateName(e.target.value)} placeholder="Rahul" maxLength={24} />
          </label>
          <label>
            Players
            <select value={maxPlayers} onChange={(e) => setMaxPlayers(Number(e.target.value))}>
              {Array.from({ length: 15 }, (_, index) => index + 2).map((n) => <option key={n} value={n}>{n} players</option>)}
            </select>
          </label>
          <label>
            Card decks
            {maxPlayers <= 3 ? (
              <select value={deckCount} onChange={(e) => setDeckCount(Number(e.target.value))}>
                <option value={1}>1 deck + Joker (53 cards)</option>
                <option value={2}>2 decks + Joker (105 cards)</option>
              </select>
            ) : maxPlayers <= 7 ? (
              <select value={2} disabled>
                <option value={2}>2 decks + Joker (required)</option>
              </select>
            ) : maxPlayers <= 12 ? (
              <select value={3} disabled>
                <option value={3}>3 decks + Joker (required)</option>
              </select>
            ) : (
              <select value={4} disabled>
                <option value={4}>4 decks + Joker (required)</option>
              </select>
            )}
          </label>
          <label>
            Score mode
            <select value={mode} onChange={(e) => setMode(e.target.value as 'individual' | 'teams')}>
              <option value="individual">Individual</option>
              <option value="teams" disabled={!teamEligible}>{teamEligible ? 'Teams' : 'Teams unavailable for this player count'}</option>
            </select>
          </label>
          {mode === 'teams' && (
            <label>
              Team setup
              <select value={teamCount} onChange={(e) => setTeamCount(Number(e.target.value))}>
                {teamCounts.map((count) => <option key={count} value={count}>{count} teams · {maxPlayers / count} players per team</option>)}
              </select>
            </label>
          )}
          <button className="primary" onClick={create} disabled={busy}>Create Game</button>
        </div>

        <div className="panel">
          <p className="panel-kicker">PLAYER</p>
          <h2>Join a room</h2>
          <label>
            Room code
            <input className="code-input" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="A4K9P" maxLength={5} />
          </label>
          <label>
            Your name
            <input value={joinName} onChange={(e) => setJoinName(e.target.value)} placeholder="Sandeep" maxLength={24} />
          </label>
          <label>
            Game rejoin PIN <small>(the shared PIN shown inside that game)</small>
            <input value={joinPin} onChange={(e) => setJoinPin(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="6-digit PIN" inputMode="numeric" />
          </label>
          <button className="secondary" onClick={join} disabled={busy}>Join Game</button>
        </div>
      </section>

      <section className="panel close-game-panel">
        <div><p className="panel-kicker">HOST CONTROL</p><h2>Close an existing game</h2><p>Removes the active room and any completed-game snapshot.</p></div>
        <input className="code-input" value={closeCode} onChange={(e) => setCloseCode(e.target.value.toUpperCase())} placeholder="Room code" maxLength={5} />
        <input value={closeName} onChange={(e) => setCloseName(e.target.value)} placeholder="Host name" maxLength={24} />
        <input value={closePin} onChange={(e) => setClosePin(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="Game rejoin PIN" inputMode="numeric" />
        <button className="danger" onClick={closeExisting} disabled={busy}><Trash2 size={17} /> Close Game</button>
      </section>

      <section className="rule-strip">
        <div><strong>🃏 Joker</strong><span>Play anytime. Wins automatically.</span></div>
        <div><strong>♠ Trump</strong><span>Follow suit; spades trump when void.</span></div>
        <div><strong>5 Bags</strong><span>Automatic −50 penalty.</span></div>
      </section>
      </>}
    </main>
  )
}

function AdminPanel() {
  const [adminKey, setAdminKey] = useState('')
  const [games, setGames] = useState<AdminGame[]>([])
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<'all' | AdminGame['status']>('all')
  const [message, setMessage] = useState('Enter the backend admin key to load stored games.')
  const [busy, setBusy] = useState(false)

  const loadGames = async () => {
    if (!adminKey) return setMessage('Enter the admin key.')
    setBusy(true)
    try {
      const result = await adminListGames(adminKey)
      setGames(result.games)
      setMessage(`${result.games.length} game${result.games.length === 1 ? '' : 's'} found.`)
    } catch (error) {
      setGames([])
      setMessage(error instanceof Error ? error.message : 'Could not load games')
    } finally {
      setBusy(false)
    }
  }

  const deleteGame = async (game: AdminGame) => {
    if (!window.confirm(`Close and delete game ${game.code}? Connected players will be removed.`)) return
    setBusy(true)
    try {
      await adminDeleteGame(game.code, adminKey)
      setGames((current) => current.filter((item) => item.code !== game.code))
      setMessage(`Game ${game.code} was deleted.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not delete game')
    } finally {
      setBusy(false)
    }
  }

  const cleanup = async (scope: 'active' | 'completed') => {
    if (!window.confirm(`Delete all ${scope} games shown by this backend?`)) return
    setBusy(true)
    try {
      const result = await adminCleanupGames(adminKey, scope)
      setMessage(`Closed ${result.activeClosed} active games and deleted ${result.completedDeleted} completed games.`)
      await loadGames()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Cleanup failed')
      setBusy(false)
    }
  }

  const filtered = games.filter((game) => {
    const matchesText = !query || game.code.toLowerCase().includes(query.toLowerCase()) || game.hostName.toLowerCase().includes(query.toLowerCase())
    return matchesText && (status === 'all' || game.status === status)
  })

  return (
    <section className="admin-panel">
      <div className="admin-heading"><div><p className="panel-kicker">ADMINISTRATION</p><h2>Stored games</h2><p>Active games are in memory. Completed games are SQLite snapshots.</p></div><ShieldCheck size={32} /></div>
      <div className="admin-auth"><input type="password" value={adminKey} onChange={(event) => setAdminKey(event.target.value)} placeholder="Backend admin key" /><button className="primary" onClick={loadGames} disabled={busy}><RefreshCw size={16} /> Load games</button></div>
      <p className="admin-message">{message}</p>
      <div className="admin-filters"><label><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search room code or host" /></label><select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}><option value="all">All statuses</option><option value="open">Open</option><option value="in_progress">In progress</option><option value="completed">Completed</option></select></div>
      <div className="admin-actions"><button className="danger" onClick={() => cleanup('completed')} disabled={busy || !adminKey}>Delete all completed</button><button className="danger" onClick={() => cleanup('active')} disabled={busy || !adminKey}>Close all active</button></div>
      <div className="admin-table-wrap"><table><thead><tr><th>Code</th><th>Host</th><th>Status</th><th>Round</th><th>Players</th><th>Connected</th><th>Storage</th><th /></tr></thead><tbody>{filtered.map((game) => <tr key={game.code}><td><strong>{game.code}</strong></td><td>{game.hostName}</td><td><span className={`game-status ${game.status}`}>{game.status.replace('_', ' ')}</span></td><td>{game.roundNumber}/13</td><td>{game.playerCount} + {game.botCount} bots</td><td>{game.connectedCount ?? '—'}</td><td>{game.storage}</td><td><button className="table-delete" onClick={() => deleteGame(game)} disabled={busy}><Trash2 size={15} /> Close</button></td></tr>)}</tbody></table>{filtered.length === 0 && <p className="empty-admin">No matching games.</p>}</div>
    </section>
  )
}

function Game({
  state,
  playerId,
  rejoinPin,
  connected,
  error,
  send,
  leave,
}: {
  state: RoomState
  playerId: string
  rejoinPin: string
  connected: boolean
  error: string
  send: (payload: Record<string, unknown>) => void
  leave: () => void
}) {
  const me = state.players.find((p) => p.id === playerId)!
  const isHost = state.hostPlayerId === playerId
  const [bid, setBid] = useState(0)
  const [showScore, setShowScore] = useState(false)
  const [showChat, setShowChat] = useState(false)
  const [lastReadMessages, setLastReadMessages] = useState(0)
  const myTeam = state.mode === 'teams' ? state.teamRanking.find((team) => team.team === me.team) : null
  const unreadMessages = Math.max(0, state.chatMessages.length - lastReadMessages)

  useEffect(() => setBid(0), [state.roundNumber])
  useEffect(() => {
    if (showChat) setLastReadMessages(state.chatMessages.length)
  }, [showChat, state.chatMessages.length])

  const copyCode = async () => {
    await navigator.clipboard?.writeText(state.code)
  }

  const endGame = async () => {
    if (!window.confirm('Close this game for every player and delete its stored snapshot?')) return
    try {
      await closeRoom(state.code, me.name, rejoinPin)
      leave()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Could not close the game')
    }
  }

  return (
    <main className={`game-shell phase-${state.phase} ${showChat ? 'chat-is-open' : ''}`}>
      <header className="game-header">
        <div>
          <p className="eyebrow">ROOM {state.code}</p>
          <div className="header-title-row">
            <h1>Friends Spades</h1>
            <button className="icon-button" onClick={copyCode} title="Copy room code"><Copy size={17} /></button>
          </div>
        </div>
        <div className="header-actions">
          <span className={`connection ${connected ? 'online' : ''}`}>{connected ? <Wifi size={16} /> : <WifiOff size={16} />}{connected ? 'Live' : 'Reconnecting'}</span>
          {isHost && <button className="icon-button danger-icon" onClick={endGame} title="Close game"><Trash2 size={18} /></button>}
          <button className="icon-button chat-toggle" onClick={() => setShowChat(true)} title="Open game chat"><MessageCircle size={18} />{unreadMessages > 0 && <small>{unreadMessages}</small>}</button>
          <button className="icon-button" onClick={leave} title="Leave"><LogOut size={18} /></button>
        </div>
      </header>

      {error && <div className="error-banner compact">{error}</div>}

      <div className="rejoin-note">Game rejoin PIN: <strong>{rejoinPin}</strong> <span>Shared by every player in this game. Keep it private.</span></div>

      <section className="status-row">
        <div><span>ROUND</span><strong>{state.roundNumber || '—'} / 13</strong></div>
        <div><span>TRICKS</span><strong>{state.completedTricks} / {state.roundNumber || '—'}</strong></div>
        <div><span>{myTeam ? `TEAM ${myTeam.team} SCORE` : 'YOUR SCORE'}</span><strong>{myTeam?.score ?? me.totalScore}</strong></div>
        <div><span>{myTeam ? 'TEAM BAGS' : 'BAGS'}</span><strong>{myTeam?.bags ?? me.bags} / 5</strong></div>
      </section>

      {state.phase === 'lobby' ? (
        <Lobby state={state} isHost={isHost} send={send} />
      ) : state.phase === 'drawing' ? (
        <CardDraw state={state} playerId={playerId} send={send} />
      ) : state.phase === 'draw_complete' ? (
        <DrawResults state={state} isHost={isHost} send={send} />
      ) : state.phase === 'cutting' ? (
        <DeckCut state={state} playerId={playerId} send={send} />
      ) : (
        <>
          <section className="table-layout">
            <PlayerRail state={state} playerId={playerId} />
            <GameTable state={state} playerId={playerId} send={send} />
          </section>

          {state.phase === 'bidding' && (
            <BidPanel state={state} me={me} bid={bid} setBid={setBid} send={send} />
          )}

          {(state.phase === 'bidding' || state.phase === 'playing') && (
            <Hand state={state} playerId={playerId} send={send} />
          )}

          {state.phase === 'round_complete' && (
            <RoundComplete state={state} isHost={isHost} send={send} />
          )}

          {state.phase === 'finished' && <FinalResults state={state} />}
        </>
      )}

      {state.phase !== 'lobby' && (
        <section className="score-section">
          <button className="score-toggle" onClick={() => setShowScore((v) => !v)}>
            {showScore ? 'Hide scoreboard' : 'Show scoreboard'}
          </button>
          {showScore && <Scoreboard state={state} />}
        </section>
      )}
      {showChat && <ChatPanel state={state} playerId={playerId} send={send} onClose={() => setShowChat(false)} />}
      {!showChat && (
        <button type="button" className="chat-edge-tab" onClick={() => setShowChat(true)} aria-label="Open side chat">
          <MessageCircle size={18} /><span>Chat</span>{unreadMessages > 0 && <small>{unreadMessages}</small>}
        </button>
      )}
    </main>
  )
}

function CardDraw({ state, playerId, send }: { state: RoomState; playerId: string; send: (p: Record<string, unknown>) => void }) {
  const me = state.players.find((player) => player.id === playerId)!
  return (
    <section className="draw-panel">
      <p className="eyebrow">PLAYER ORDER DRAW</p>
      <h2>{me.drawSubmitted ? 'Card selected' : 'Pick one facedown card'}</h2>
      <p>Lowest card bids first. Highest card bids last. Equal ranks use ♣, ♦, ♥, ♠ order.</p>
      <div className="draw-grid">
        {state.drawChoices.map((cardId, index) => (
          <button key={cardId} className="draw-card" disabled={me.drawSubmitted} onClick={() => send({ action: 'pick_draw_card', cardId })}>
            <span>♠</span><small>{index + 1}</small>
          </button>
        ))}
      </div>
      {me.drawSubmitted && <p className="waiting">Your card is locked and hidden. Waiting for the other players to pick…</p>}
    </section>
  )
}

function DrawResults({ state, isHost, send }: { state: RoomState; isHost: boolean; send: (p: Record<string, unknown>) => void }) {
  const ranking = state.players.slice().reverse()
  return (
    <section className="draw-panel results">
      <p className="eyebrow">FINAL SEATING</p>
      <h2>Last bidder to first bidder</h2>
      <p>{state.mode === 'teams' ? 'Teams alternate around the table. The strongest team draw holds the final seat and bids last.' : 'Rank is compared first. Suit is considered only when two players draw the same rank.'}</p>
      <div className="draw-results">
        {ranking.map((player, index) => {
          const bidPosition = state.players.findIndex((item) => item.id === player.id)
          return (
          <div key={player.id}>
            <b>#{index + 1} {player.name}</b>
            {player.drawCard && <CardFace card={player.drawCard} />}
            <span>{bidPosition === 0 ? 'Bids first' : bidPosition === state.players.length - 1 ? 'Bids last' : `Bids ${bidPosition + 1}`}</span>
          </div>
          )
        })}
      </div>
      {isHost ? <button className="primary" onClick={() => send({ action: 'confirm_order' })}><Play size={18} /> Start Round 1</button> : <p className="waiting">Waiting for the host to confirm the order…</p>}
    </section>
  )
}

function DeckCut({ state, playerId, send }: { state: RoomState; playerId: string; send: (p: Record<string, unknown>) => void }) {
  const [extraPosition, setExtraPosition] = useState(106)
  const cutter = state.players.find((player) => player.id === state.cutterPlayerId)
  const dealer = state.players.find((player) => player.id === state.dealerPlayerId)
  const firstRecipient = state.players.find((player) => player.seat === state.leaderSeat)
  const isCutter = state.cutterPlayerId === playerId
  const visibleCount = Math.min(state.cutCardCount, 105)
  const extraPositions = Array.from({ length: Math.max(0, state.cutCardCount - 105) }, (_, index) => index + 106)

  return (
    <section className="draw-panel cut-panel">
      <p className="eyebrow">ROUND {state.roundNumber} · CUT THE DECK</p>
      <h2>{isCutter ? 'Choose where to cut' : `Waiting for ${cutter?.name ?? 'the cutter'}`}</h2>
      <p>{dealer?.name ?? 'The dealer'} deals first to {firstRecipient?.name ?? 'the first player'}. Cutting after a card moves that card and every card before it to the bottom.</p>
      <div className="cut-summary"><strong>{state.cutCardCount} cards</strong><span>Cutter: {cutter?.name}</span><span>Dealer: {dealer?.name}</span></div>
      <div className="draw-grid cut-grid">
        {Array.from({ length: visibleCount }, (_, index) => index + 1).map((position) => (
          <button key={position} className="draw-card" disabled={!isCutter} onClick={() => send({ action: 'cut_deck', position })}>
            <span>♠</span><small>{position}</small>
          </button>
        ))}
      </div>
      {extraPositions.length > 0 && (
        <div className="extra-cut">
          <label>Additional positions 106–{state.cutCardCount}
            <select value={extraPosition} onChange={(event) => setExtraPosition(Number(event.target.value))} disabled={!isCutter}>
              {extraPositions.map((position) => <option key={position} value={position}>{position}</option>)}
            </select>
          </label>
          <button className="primary" disabled={!isCutter} onClick={() => send({ action: 'cut_deck', position: extraPosition })}>Cut at {extraPosition}</button>
        </div>
      )}
    </section>
  )
}

function Lobby({ state, isHost, send }: { state: RoomState; isHost: boolean; send: (p: Record<string, unknown>) => void }) {
  const teamLabels = Array.from({ length: state.teamCount }, (_, index) => String.fromCharCode(65 + index))
  const validTeamCounts = Array.from({ length: Math.max(0, Math.floor(state.maxPlayers / 2) - 1) }, (_, index) => index + 2)
    .filter((count) => state.maxPlayers % count === 0)
  const teamCapacity = state.mode === 'teams' ? state.maxPlayers / state.teamCount : 0
  const teamSizes = Object.fromEntries(teamLabels.map((team) => [team, state.players.filter((player) => player.team === team).length]))
  return (
    <section className="lobby-card">
      <div className="lobby-code">
        <span>ROOM CODE</span>
        <strong>{state.code}</strong>
        <p>{state.deckCount} {state.deckCount === 1 ? 'deck' : 'decks'} + Joker · Share this code with your friends.</p>
      </div>
      <div className="players-list">
        <div className="list-heading"><Users size={18} /> Players <span>{state.players.length}/{state.maxPlayers}{state.mode === 'teams' ? ` · ${state.teamCount} teams` : ''}</span></div>
        {state.mode === 'teams' && (
          <div className="team-editor">
            <label>Number of teams
              <select value={state.teamCount} disabled={!isHost || state.teamsLocked} onChange={(event) => send({ action: 'set_team_count', teamCount: Number(event.target.value) })}>
                {validTeamCounts.map((count) => <option key={count} value={count}>{count} teams · {state.maxPlayers / count} each</option>)}
              </select>
            </label>
            <div className="team-counts">{teamLabels.map((team) => <span key={team} className={teamSizes[team] > teamCapacity ? 'overfilled' : ''}>Team {team}: {teamSizes[team]}/{teamCapacity}</span>)}</div>
            {isHost && (state.teamsLocked
              ? <button className="secondary" onClick={() => send({ action: 'unlock_teams' })}>Edit teams</button>
              : <button className="primary" onClick={() => send({ action: 'lock_teams' })}>Lock teams</button>)}
            {!isHost && <p className="team-lock-status">{state.teamsLocked ? 'Teams are locked.' : 'The host is arranging teams.'}</p>}
          </div>
        )}
        {state.players.map((p) => (
          <div className="player-row" key={p.id}>
            <span className={`presence ${p.connected ? 'present' : ''}`} />
            <strong>{p.name}</strong>
            {p.isBot && <em>BOT</em>}
            {p.team && (isHost ? (
              <select
                className="team-select"
                aria-label={`Team for ${p.name}`}
                value={p.team}
                disabled={state.teamsLocked}
                onChange={(event) => send({ action: 'assign_team', playerId: p.id, team: event.target.value })}
              >
                {teamLabels.map((team) => <option key={team} value={team}>Team {team}</option>)}
              </select>
            ) : <em>Team {p.team}</em>)}
            {p.id === state.hostPlayerId && <small>HOST</small>}
          </div>
        ))}
        {state.mode === 'teams' && isHost && <p className="team-help">Arrange players freely, review each team count, then lock the teams. Overfilled teams cannot be locked.</p>}
      </div>
      {isHost ? (
        <button className="primary start" disabled={state.mode === 'teams' && !state.teamsLocked} onClick={() => send({ action: 'start_game' })}>
          <Play size={18} fill="currentColor" /> {state.mode === 'teams' && !state.teamsLocked ? 'Lock Teams to Start' : `Start Game ${state.players.length < state.maxPlayers ? 'with Computers' : ''}`}
        </button>
      ) : (
        <p className="waiting">Waiting for the host to start…</p>
      )}
    </section>
  )
}

function PlayerRail({ state, playerId }: { state: RoomState; playerId: string }) {
  return (
    <aside className="player-rail">
      {state.players.map((p) => {
        const team = state.teamRanking.find((item) => item.team === p.team)
        return <div key={p.id} className={`seat ${p.id === playerId ? 'me' : ''} ${state.currentPlayerId === p.id ? 'active' : ''}`}>
          <div className="avatar">{p.name.slice(0, 1).toUpperCase()}</div>
          <div className="seat-info">
            <strong>{p.name}{p.id === playerId ? ' · You' : ''}</strong>
            <span className="bid-won">{state.mode === 'teams' ? `Team ${p.team} · Estimate ${p.bidSubmitted ? p.bid : '—'} · Won ${p.tricks}` : `${p.bidSubmitted ? `Bid ${p.bid ?? '✓'}` : 'No bid'} · Won ${p.tricks}`}</span>
          </div>
          <div className="seat-score">{team?.score ?? p.totalScore}<small>{team?.bags ?? p.bags}b</small></div>
        </div>
      })}
    </aside>
  )
}

function GameTable({ state, playerId, send }: { state: RoomState; playerId: string; send: (p: Record<string, unknown>) => void }) {
  const playerName = (id: string) => state.players.find((p) => p.id === id)?.name ?? 'Player'
  const displayedTrick = state.currentTrick.length > 0 ? state.currentTrick : state.lastTrickCards
  const showingLastTrick = state.currentTrick.length === 0 && state.lastTrickCards.length > 0
  return (
    <section className="felt">
      <div className="felt-top">
        <span>{state.message}</span>
        {state.phase === 'playing' && state.currentPlayerId === playerId && <strong>YOUR TURN</strong>}
      </div>
      <div className="trick-grid">
        {displayedTrick.length === 0 ? (
          <div className="empty-trick">
            <span>♠</span>
            <p>{state.phase === 'bidding' ? 'Waiting for guesses' : 'Waiting for the lead card'}</p>
          </div>
        ) : displayedTrick.map((play) => (
          <div className="played-card" key={`${play.playerId}-${play.card.id}`}>
            <small>{playerName(play.playerId)}</small>
            <CardFace card={play.card} />
          </div>
        ))}
      </div>
      {showingLastTrick && state.lastTrickWinnerId && state.phase === 'playing' && (
        <div className="trick-review">
          <p className="last-winner">Completed trick: {playerName(state.lastTrickWinnerId)} won</p>
          {state.awaitingNextTrick && <button className="primary" onClick={() => send({ action: 'continue_trick' })}>Continue to next trick</button>}
        </div>
      )}
    </section>
  )
}

function BidPanel({
  state,
  me,
  bid,
  setBid,
  send,
}: {
  state: RoomState
  me: RoomState['players'][number]
  bid: number
  setBid: (v: number) => void
  send: (p: Record<string, unknown>) => void
}) {
  if (state.mode === 'teams') {
    const current = state.players.find((player) => player.id === state.currentPlayerId)
    const myTeam = state.teamRanking.find((team) => team.team === me.team)
    const currentTeam = state.teamRanking.find((team) => team.captainId === state.currentPlayerId && team.bid === null)
    const canAct = state.currentPlayerId === me.id
    return (
      <section className="team-bid-panel">
        <div className="team-bid-heading">
          <div><strong>{state.biddingStage === 'estimates' ? 'Public player estimates' : 'Combined team bids'}</strong><span>{state.biddingStage === 'estimates' ? 'Each estimate is visible to the entire table.' : 'The permanent team captain locks one final bid.'}</span></div>
          {state.biddingStage === 'teams' && myTeam && <b>Team {myTeam.team}: {myTeam.bid === null ? 'Not locked' : `${myTeam.bid} locked`}</b>}
        </div>
        <div className="estimate-grid">
          {state.players.map((player) => <div key={player.id}><span>{player.name} · Team {player.team}</span><strong>{player.bidSubmitted ? player.bid : '—'}</strong></div>)}
        </div>
        {state.biddingStage === 'teams' && (
          <div className="team-bid-status">
            {state.teamBidOrder.map((label) => {
              const team = state.teamRanking.find((item) => item.team === label)
              const captain = state.players.find((player) => player.id === team?.captainId)
              return <span key={label} className={team?.bid !== null ? 'locked' : ''}>Team {label}: {team?.bid ?? '—'} <small>Captain {captain?.name ?? '—'}</small></span>
            })}
          </div>
        )}
        {canAct ? (
          <div className="team-bid-action">
            <div><strong>{state.biddingStage === 'estimates' ? 'Your estimate' : `Final bid for Team ${me.team}`}</strong><span>{state.roundNumber} total tricks are available this round.</span></div>
            <BidControls roundNumber={state.roundNumber} bid={bid} setBid={setBid} label={state.biddingStage === 'estimates' ? 'Lock Estimate' : 'Lock Team Bid'} onSubmit={() => send({ action: state.biddingStage === 'estimates' ? 'submit_bid' : 'submit_team_bid', bid })} />
          </div>
        ) : <p className="waiting">Waiting for {current?.name ?? (currentTeam ? `Team ${currentTeam.team}'s captain` : 'the next bidder')}.</p>}
      </section>
    )
  }
  if (me.bidSubmitted) {
    return <section className="action-panel"><strong>Guess submitted ✓</strong><span>Waiting for the other players.</span></section>
  }
  if (state.currentPlayerId !== me.id) {
    const current = state.players.find((player) => player.id === state.currentPlayerId)
    return <section className="action-panel"><strong>Your cards are ready</strong><span>Waiting for {current?.name ?? 'the next player'} to lock their Guess.</span></section>
  }
  return (
    <section className="action-panel">
      <div>
        <strong>Your Guess</strong>
        <span>You have {state.roundNumber} card{state.roundNumber === 1 ? '' : 's'} this round.</span>
      </div>
      <BidControls roundNumber={state.roundNumber} bid={bid} setBid={setBid} label="Lock Guess" onSubmit={() => send({ action: 'submit_bid', bid })} />
    </section>
  )
}

function BidControls({ roundNumber, bid, setBid, label, onSubmit }: { roundNumber: number; bid: number; setBid: (value: number) => void; label: string; onSubmit: () => void }) {
  return <div className="bid-controls">
    <div className="quick-bids">{Array.from({ length: Math.min(roundNumber, 5) + 1 }, (_, i) => <button key={i} className={bid === i ? 'selected' : ''} onClick={() => setBid(i)}>{i}</button>)}</div>
    {roundNumber > 5 && <select aria-label="Bids above 5" value={bid > 5 ? bid : ''} onChange={(event) => setBid(Number(event.target.value))}><option value="" disabled>6+</option>{Array.from({ length: roundNumber - 5 }, (_, i) => i + 6).map((value) => <option key={value} value={value}>{value}</option>)}</select>}
    <button className="primary" onClick={onSubmit}>{label}</button>
  </div>
}

function Hand({ state, playerId, send }: { state: RoomState; playerId: string; send: (p: Record<string, unknown>) => void }) {
  const myTurn = state.currentPlayerId === playerId
  const bidding = state.phase === 'bidding'
  const legal = useMemo(() => new Set(state.legalCardIds), [state.legalCardIds])
  return (
    <section className="hand-section">
      <div className="hand-heading">
        <div><strong>Your hand</strong><span>{bidding ? 'Review your cards before locking your Guess' : myTurn ? 'Choose a highlighted card' : 'Wait for your turn'}</span></div>
        <div className="legend"><span>🃏 Joker can always be played</span></div>
      </div>
      <div className="hand-scroll">
        {state.hand.map((card) => {
          const allowed = myTurn && legal.has(card.id)
          return (
            <button
              key={card.id}
              className={`hand-card ${allowed ? 'legal' : ''} ${card.isJoker ? 'joker-card' : ''}`}
              disabled={!allowed}
              onClick={() => send({ action: 'play_card', cardId: card.id })}
            >
              <CardFace card={card} />
            </button>
          )
        })}
      </div>
    </section>
  )
}

function CardFace({ card }: { card: Card }) {
  if (card.isJoker) return <div className="card-face joker"><b>JOKER</b><span>🃏</span><small>WILD</small></div>
  const red = card.suit === 'hearts' || card.suit === 'diamonds'
  return <div className={`card-face ${red ? 'red' : ''}`}><b>{card.label}</b><span>{card.label.slice(-1)}</span><small>{card.deckIndex > 0 ? 'II' : 'I'}</small></div>
}

function RoundComplete({ state, isHost, send }: { state: RoomState; isHost: boolean; send: (p: Record<string, unknown>) => void }) {
  const latest = state.roundHistory[state.roundHistory.length - 1]
  return (
    <section className="round-complete">
      <div>
        <p className="eyebrow">ROUND {state.roundNumber} COMPLETE</p>
        <h2>Scores are in.</h2>
      </div>
      <div className="mini-results">
        {latest?.rows.map((row) => (
          <div key={row.playerId}>
            <strong>{row.name}</strong>
            <span>{row.bid} guess · {row.won} won</span>
            <span>Previous score: {row.scoreBefore}</span>
            <span>Round points: {formatSigned(row.baseScore)}</span>
            <span className={row.bagPenalty ? 'penalty-text' : ''}>Bag penalty: {row.bagPenalty ? formatSigned(row.bagPenalty) : '—'}</span>
            <b>{row.scoreBefore} {formatOperator(row.baseScore)} {row.bagPenalty ? formatOperator(row.bagPenalty) : ''} = {row.totalScore}</b>
            <span>Bags: {row.bagsBefore} + {row.newBags} earned {row.bagPenalty ? `→ penalty applied → ${row.remainingBags} remaining` : `→ ${row.remainingBags} remaining`}</span>
          </div>
        ))}
      </div>
      {isHost ? (
        <button className="primary" onClick={() => send({ action: 'next_round' })}><RotateCcw size={17} /> Start Round {state.roundNumber + 1}</button>
      ) : <p className="waiting">Waiting for host to start the next round…</p>}
    </section>
  )
}

function FinalResults({ state }: { state: RoomState }) {
  return (
    <section className="final-results">
      <div className="trophy">🏆</div>
      <p className="eyebrow">GAME COMPLETE</p>
      <h2>{state.mode === 'teams' && state.teamRanking.length ? `Team ${state.teamRanking[0].team} wins!` : `${state.individualRanking[0]?.name ?? 'Winner'} wins!`}</h2>
      {state.mode === 'teams' && (
        <div className="team-results">
          {state.teamRanking.map((team, i) => <div key={team.team}><span>#{i + 1} Team {team.team}</span><strong>{team.score}</strong></div>)}
        </div>
      )}
      <div className="ranking">
        {state.mode === 'teams' ? state.players.slice().sort((a, b) => b.contributionTricks - a.contributionTricks).map((player, i) => (
          <div key={player.id}><span>#{i + 1}</span><strong>{player.name}</strong><em>Team {player.team}</em><b>{player.contributionTricks}</b><small>contribution tricks</small></div>
        )) : state.individualRanking.map((p, i) => (
          <div key={p.playerId}><span>#{i + 1}</span><strong>{p.name}</strong>{p.team && <em>Team {p.team}</em>}<b>{p.score}</b><small>{p.bags} bags</small></div>
        ))}
      </div>
    </section>
  )
}

function Scoreboard({ state }: { state: RoomState }) {
  return (
    <div className="scoreboard-wrap">
      <h3>Current standings</h3>
      <p className="score-explainer">Total score is the score before bag penalties. Actual score is the final score after all bag penalties.</p>
      <table>
        <thead><tr><th>{state.mode === 'teams' ? 'Team' : 'Player'}</th><th>Current bags</th><th>Total bags</th><th>Total score</th><th>Actual score</th><th>Bid</th><th>Won</th></tr></thead>
        <tbody>
          {state.mode === 'teams' ? state.teamRanking.map((team) => (
            <tr key={team.team}><td>Team {team.team}</td><td>{team.bags}</td><td>{team.totalBags}</td><td>{team.grossScore}</td><td><strong>{team.score}</strong></td><td>{team.bid ?? '—'}</td><td>{team.tricks}</td></tr>
          )) : state.players.slice().sort((a, b) => b.totalScore - a.totalScore).map((p) => (
            <tr key={p.id}><td>{p.name}{p.team ? ` · ${p.team}` : ''}</td><td>{p.bags}</td><td>{p.totalBags}</td><td>{p.grossScore}</td><td><strong>{p.totalScore}</strong></td><td>{p.bid ?? '—'}</td><td>{p.tricks}</td></tr>
          ))}
        </tbody>
      </table>
      {state.mode === 'teams' && <><h3>Player contributions</h3><table><thead><tr><th>Player</th><th>Team</th><th>Public estimate</th><th>This round</th><th>Game total</th></tr></thead><tbody>{state.players.map((player) => <tr key={player.id}><td>{player.name}</td><td>Team {player.team}</td><td>{player.bid ?? '—'}</td><td>{player.tricks}</td><td>{player.contributionTricks}</td></tr>)}</tbody></table></>}
      <h3>Round-by-round score calculation</h3>
      <p className="score-explainer">Previous score + round points + bag penalty = new total. Every 5 accumulated bags produces a −50 penalty and removes 5 bags.</p>
      {state.roundHistory.slice().reverse().map((round) => (
        <div className="score-round" key={round.roundNumber}>
          <h4>Round {round.roundNumber}</h4>
          <table>
            <thead><tr><th>Player</th><th>Bid / Won</th><th>Previous</th><th>Round points</th><th>Bag penalty</th><th>New total</th><th>Bags</th></tr></thead>
            <tbody>
              {round.rows.map((row) => (
                <tr key={row.playerId}>
                  <td>{row.name}</td>
                  <td>{row.bid} / {row.won}</td>
                  <td>{row.scoreBefore}</td>
                  <td>{formatSigned(row.baseScore)}</td>
                  <td className={row.bagPenalty ? 'penalty-text' : ''}>{row.bagPenalty ? formatSigned(row.bagPenalty) : '—'}</td>
                  <td><strong>{row.totalScore}</strong></td>
                  <td>{row.bagsBefore} + {row.newBags} → {row.remainingBags}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

function ChatPanel({ state, playerId, send, onClose }: { state: RoomState; playerId: string; send: (payload: Record<string, unknown>) => void; onClose: () => void }) {
  const [message, setMessage] = useState('')
  const messagesRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const messages = messagesRef.current
    if (messages) messages.scrollTop = messages.scrollHeight
  }, [state.chatMessages.length])
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const clean = message.trim()
    if (!clean) return
    send({ action: 'send_chat', message: clean })
    setMessage('')
  }
  return <aside className="chat-panel" aria-label="Side chat">
      <header><div><strong>Side chat</strong><span>Visible to everyone · game remains active</span></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close side chat"><X size={18} /></button></header>
      <div className="chat-messages" ref={messagesRef}>
        {state.chatMessages.length === 0 && <p className="waiting">No messages yet. Start the conversation.</p>}
        {state.chatMessages.map((item) => <div key={item.id} className={`chat-message ${item.playerId === playerId ? 'mine' : ''}`}><small>{item.playerName}{item.team ? ` · Team ${item.team}` : ''}</small><p>{item.message}</p></div>)}
      </div>
      <form onSubmit={submit}><input maxLength={500} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Message everyone…" /><button className="primary" type="submit" disabled={!message.trim()}><Send size={17} /></button></form>
    </aside>
}

function formatSigned(value: number) {
  return value > 0 ? `+${value}` : `${value}`
}

function formatOperator(value: number) {
  return value >= 0 ? `+ ${value}` : `− ${Math.abs(value)}`
}
