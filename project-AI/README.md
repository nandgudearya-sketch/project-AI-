# Automated Playtesting and Balance Tuning for Games

**Team:** Karan Manish Shah, Nidhi Nimmagadda, Arya Atul Nandgude
**Course:** Foundations of AI, Khoury College, Northeastern University

A tool that plays a game thousands of times with AI agents, finds balance
problems (first-player advantage, overpowered or useless cards, games that
run too long or are decided by luck), and checks whether rule changes make
the game fairer.

## Quick start

Requires Python 3.8+. No external libraries.

```bash
python main.py                                   # greedy agents, 2000 games
python main.py --agent mcts --games 100 --iterations 100
python main.py --agent random --games 5000
python main.py --swap-games 0                    # skip the slower card swap test
```

## Project structure

```
main.py                     Run a full balance test
balance_tool/
  game_interface.py         The Game class every game must implement
  card_duel.py              Our original test game, with planted imbalances
  agents.py                 Random, Greedy, and MCTS agents (skill levels)
  simulate.py               Plays many games and records results
  report.py                 Seat advantage, game length, skill/luck checks
  experiments.py            Card swap test that measures card strength
```

## Test game: Card Duel

Two players each have a shuffled deck. Each turn you gain mana (your turn
number, capped at 8), draw a card, and play any cards you can afford.
Cards deal damage, heal, or draw. First to reduce the opponent to 0 HP wins.
All numbers (HP, costs, damage, hand size, turn limit) are parameters in
`DEFAULT_PARAMS`.

**Planted imbalances** (ground truth for evaluation):

| Imbalance | Expected detection |
|---|---|
| `Dragon` costs 3 but deals 7 damage | Card swap test flags it as too strong |
| `Pebble` costs 3 but deals 1 damage | Flagged as rarely played |
| No compensation for going second | Seat advantage check flags player 0 |

## Current results (greedy agents)

- **First-player advantage:** player 0 wins about 81% of games.
- **Dragon:** a deck with Dragon beats a deck with Bolt instead about 83% of the time.
- **Pebble:** played only 0.06 times per game.
- **Skill vs. luck:** greedy beats random about 96% of the time, so skill matters.
- **Fix check:** giving player 1 two extra starting cards lowers player 0's
  win rate from 81% to 73%. That helps but isn't enough, which is what the
  optimizer (planned) should solve.

## Lessons learned so far

**"Win rate when played" is misleading.** Our first version flagged Pebble as
strong and missed Dragon. Because both players share the same deck, weak cards
get played mainly by whoever already has spare mana (usually the player who is
winning), and strong cards appear equally on both sides. The **card swap test**
fixes this: it compares two decks that differ in only one card, so any
difference in win rate is caused by that card.

**Results depend on agent skill.** MCTS plays Pebble far more often than the
greedy agent, so "rarely played" depends on who's playing. This is a good
reason to report findings across several agent skill levels.

## Adding a new game

Create a class that inherits from `Game` in `game_interface.py` and implement
`initial_state`, `current_player`, `legal_actions`, `apply`, `is_terminal`,
and `winner`. Optionally implement `determinize` (for fair MCTS),
`action_value` (for the greedy agent), and `summary` (for richer reports).
The agents, simulator, and seat/length/skill checks will then work unchanged.

## Roadmap

- [x] Game interface and Card Duel test game
- [x] Random, greedy, and MCTS agents
- [x] Simulator and balance report with confidence intervals
- [x] Card swap test for card strength
- [ ] **Parameter optimizer**: search for parameter changes that bring win
      rates close to 50% (e.g. hill climbing, simulated annealing, or a
      genetic algorithm), then verify with fresh simulations
- [ ] **Dominant strategy search**: find fixed strategies or deck choices
      that beat everything else
- [ ] Run checks at several agent skill levels and compare
- [ ] Human vs. agent games to check agents play reasonably
- [ ] Plug in a second game
