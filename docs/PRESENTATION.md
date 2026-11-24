# Presentation guide: Analysis + the third game (Claim)

A script for presenting my part of the project, with what to click and what to
say. About 6–8 minutes.

## Before you start (2 minutes, do it before the call)

```powershell
cd C:\projects\project-AI-
git pull
python -m balancer web
```

The browser opens the Ember Duel page. Keep the terminal open; press Ctrl+C
there when you are done. If you share your screen, share the browser window.

---

## 1. The problem (30 seconds, no clicking)

> "Our tool plays a game thousands of times with AI players and tells a
> designer whether the game is fair: does going first win too often, is one
> card too strong. My part is the **analysis**: measuring how strong each card
> really is, and checking that the tool works on games other than our card game."

## 2. Card ablation (1–2 minutes)

Show the chart `docs/figures/ablation_vs_lift.png` (or the README on GitHub).

> "The obvious way to measure a card is: do players who start with it win more?
> That misses expensive cards, because you can't play them early.
> So I added **ablation**: take one card out of one player's deck, put a plain
> card in its place, and replay the *exact same* games. Because the deals are
> identical, luck cancels out, and the difference is what the card is worth."

Key result to say:

> "Inferno is worth **+22%** by ablation but only **+3%** by the old measure.
> And ablation finds every card we deliberately broke: cheap Flare +30%,
> cheap Hearth jumps from −11% to +12%."

## 3. Skill matters (1 minute)

Show `docs/figures/card_value_by_skill.png`.

> "I ran ablation with four skill levels, from a random player up to strong
> tree search. Inferno gets **stronger** with skill (+9% → +28%); Hearth gets
> **weaker** (−4% → −17%). Designers usually playtest with friends, not
> experts, so they would underrate Inferno and overrate Hearth."

## 4. The third game: Claim (2 minutes, live)

Click **Claim: new game →** at the top of the Ember Duel page.

> "To show the tool is general, I added a completely different game: no cards,
> no hidden information, no luck after the deal. A 4×4 board; you take turns
> claiming a square, score its number, plus 1 for each of your own squares next
> to it."

- **Play** tab → Opponent **Hard** → **New game** → click 3–4 squares.
  > "Hard is Monte Carlo tree search. The small +n on each square is what it's
  > worth to you right now."

- **Balance lab** tab → Game **Claim** → Version **Balanced (default)** →
  **Run analysis** (about 5 seconds).
  > "First player scores about 51%: fair. That's because I tuned it: the second
  > player starts with 2 bonus points."

- Version **Planted: No bonus points for moving second** → **Run analysis**.
  > "Remove the bonus and the tool flags it straight away: the first player
  > wins about 74%, and the confidence interval is nowhere near 50%."

Extra point if there is time:

> "Interesting twist: with the same 2-point bonus, a *weaker* AI that only
> looks one move ahead gives the second player the advantage. So the right
> compensation depends on how good your players are."

## 5. One tool, three games (1 minute)

**Compare games** tab.

> "Same agents, same analyzer, no game-specific code, on a card game, a solved
> maths game and a board game. Each has one planted problem, and the tool finds
> all three. For Nim we know the right answer from theory, pile 13 is a
> first-player win and pile 12 a second-player win, and the tool gets both
> right."

## 6. Close (15 seconds)

> "So: ablation measures card value properly, it shows balance depends on skill,
> and the comparison shows the tool works on very different games."

---

## Likely questions

- **Why replay the same seeds?** Same shuffled decks in both runs, so the only
  difference is the card. That removes most of the luck, so far fewer games are
  needed for a reliable answer.
- **What is the 95% CI?** The range the true value is very likely in. We only
  flag a problem when that whole range is clearly away from fair.
- **What is z?** How many "noise units" a result is from zero. Above 3 is very
  unlikely to be chance.
- **Why does Nim use piles 13 and 12, not 21?** The theory only shows up with
  perfect play; even MCTS-1000 still makes mistakes on a 21-token pile.
- **Why 2 bonus points in Claim?** Measured: 0 → first player wins 75%,
  1 → 64%, 2 → 51%.

## Commands, if asked to show the terminal

```powershell
python -m balancer ablate --preset planted_card
python -m balancer ablate --skill random greedy mcts:50 --seeds 200
python -m balancer compare
python -m balancer simulate --game grid --preset planted_seat --agents mcts:50 mcts:50 --games 600
```
