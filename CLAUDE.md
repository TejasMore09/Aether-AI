# Aether

**Before writing any code, read `roadmap/README.md`.** It carries the vision,
the phased plan, the current position, and the decisions already made. Sessions
here do not persist, so that folder is the project's memory — anything not
written there is lost when a conversation ends.

Then `ARCHITECTURE.md` for how the system is built, and `platform/README.md`
for how to run it.

## Working agreements

- Update `roadmap/PROGRESS.md` after every meaningful piece of work, and move
  the position marker in `roadmap/README.md` and `roadmap/PLAN.md` when a phase
  boundary is crossed.
- Add to `roadmap/DECISIONS.md` when making a choice a later session might
  reverse by accident.
- Commit messages carry the reasoning, not just the change. They are the most
  reliable memory this project has.
- One branch per feature, small PRs. This followed a 25-commit, 33,000-line PR
  nobody could review.
- Be honest in the documents. Half-built means half-built; a guessed number is
  a guessed number. A plan that overstates progress removes the prompt that
  would have corrected it.
