export type Card = {
  id: string
  suit: 'clubs' | 'diamonds' | 'hearts' | 'spades' | null
  rank: number | null
  deckIndex: number
  isJoker: boolean
  label: string
}

export type PlayerState = {
  id: string
  name: string
  seat: number
  team: string | null
  connected: boolean
  isBot: boolean
  bid: number | null
  bidSubmitted: boolean
  tricks: number
  totalScore: number
  grossScore: number
  bags: number
  totalBags: number
  drawCard: Card | null
  drawSubmitted: boolean
  cardCount: number
}

export type RoundRow = {
  playerId: string
  name: string
  team: string | null
  bid: number
  won: number
  scoreBefore: number
  baseScore: number
  scoreAfterRound: number
  bagsBefore: number
  newBags: number
  bagsBeforePenalty: number
  bagPenalty: number
  remainingBags: number
  totalScore: number
}

export type RoomState = {
  code: string
  hostPlayerId: string
  maxPlayers: number
  deckCount: number
  mode: 'individual' | 'teams'
  phase: 'lobby' | 'drawing' | 'draw_complete' | 'cutting' | 'bidding' | 'playing' | 'round_complete' | 'finished'
  roundNumber: number
  leaderSeat: number
  message: string
  players: PlayerState[]
  currentPlayerId: string | null
  currentTrick: { playerId: string; card: Card }[]
  lastTrickWinnerId: string | null
  lastTrickCards: { playerId: string; card: Card }[]
  drawChoices: string[]
  cutCardCount: number
  cutterPlayerId: string | null
  dealerPlayerId: string | null
  cutPosition: number | null
  completedTricks: number
  awaitingNextTrick: boolean
  hand: Card[]
  legalCardIds: string[]
  roundHistory: { roundNumber: number; rows: RoundRow[] }[]
  individualRanking: { playerId: string; name: string; team: string | null; score: number; bags: number }[]
  teamRanking: { team: string; score: number }[]
}

export type Session = {
  roomCode: string
  playerId: string
  rejoinPin: string
}
