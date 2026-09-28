# Game Rules Implemented in This MVP

These are the current code-level rules. They are intentionally isolated in `backend/app/game_engine.py` so they can be adjusted after the first play-test.

## Game length

- 13 rounds total.
- Round number = number of cards dealt to each player.
  - Round 1 → 1 card/player
  - ...
  - Round 13 → 13 cards/player

## Decks

- 2–3 players → host chooses 1 or 2 standard decks + 1 Joker.
- 4–7 players → 2 standard 52-card decks + 1 Joker.
- 8–12 players → 3 standard 52-card decks + 1 Joker.
- 13–16 players → 4 standard 52-card decks + 1 Joker.
- Cards are shuffled every round.
- Only the number of cards needed for that round is dealt; remaining cards stay undealt.

## Joker

- Exactly one Joker exists in the shoe.
- Joker may be played at any time.
- Joker ignores the follow-suit requirement.
- Joker wins the trick automatically.
- If Joker is the first card of a trick, there is no required suit for that trick; everyone else may play any card.

## Normal card play

- First normal card led determines the suit to follow.
- If you have a normal card of the led suit, you must play that suit, unless you choose the Joker.
- If you do not have the led suit, you may play any card.
- Spades are trump: a spade beats any non-spade card in a trick unless Joker is present.
- Among spades, highest rank wins.
- If no spade is played, highest card of the led suit wins.
- With two decks, identical-card ties are currently won by whichever identical highest card was played first.

## Current MVP assumption: no "spades broken" restriction

The MVP currently allows a player to lead a spade at any time. If your group follows the traditional rule that spades cannot be led until spades have been broken (unless the hand contains only spades/Joker), we can add it after your local review.

## Guess / Bid scoring

If tricks won >= Guess:

```text
Base score = Guess × 10 + (Won - Guess)
New bags   = Won - Guess
```

If tricks won < Guess:

```text
Base score = -(Guess × 10) + Won
New bags   = 0
```

Examples:

| Guess | Won | Base Score | New Bags |
|---:|---:|---:|---:|
| 3 | 3 | 30 | 0 |
| 3 | 4 | 31 | 1 |
| 3 | 5 | 32 | 2 |
| 3 | 2 | -28 | 0 |
| 2 | 1 | -19 | 0 |
| 0 | 2 | 2 | 2 |

## Bag penalty

- Bags accumulate per individual player.
- Every time a player reaches 5 bags:
  - subtract 50 from that player's score;
  - remove 5 bags;
  - any bags beyond 5 carry forward.

Example:

```text
Existing bags: 4
Guess: 2
Won: 4
Base score: +22
New bags: +2
Bag total: 6
Penalty: -50
Remaining bags: 1
Net round impact: -28
```

## Individual mode

- Highest total score after Round 13 wins.

## Team mode

- Players are automatically assigned alternately to Team A and Team B as they join.
- Each player keeps an individual score and individual bag count.
- Team score = sum of team members' final individual scores.
- Highest team total wins.
- Individual ranking is still shown as an MVP/leaderboard.
