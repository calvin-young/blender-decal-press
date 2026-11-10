# Collaboration log

How this project was made with AI help, and how much of it the human steered. Counts and one-line
summaries only, never prompt text.

## Disclosure

- **Tools and models:** Claude Code on a dedicated development machine, Claude Opus 5.5.
- **How much is AI:** almost all. The AI writes the code, tests and docs and runs the tests; the
  maintainer reviews little of the code.
- **What the human did:** set the requirements, chose the name, tests builds on real parts, and
  polices the interface.
- **How AI work is marked:** commits made by the AI end with `Co-Authored-By: Claude <model>`.
- **Accountability:** the maintainer publishes and answers for everything in the repository.

## Steering tally

| Bugs found | UI tweaks | New features | Direction | Total |
|---|---|---|---|---|
| 1 | 4 | 5 | 3 | 13 |

## Sessions

| Date | Tool and model | Prompts | Steering lines | Notes |
|---|---|---|---|---|
| 2026-11-09/10 | Claude Code (workstation), Opus 5.5 | 6 | 13 | 0.1.0 to 0.4.0: text decals, layered and image decals, font, rename, fit on awkward faces, placement |

## Steering

Newest first, tagged with its kind (decide, correct, domain, tested, scope) and category (bug, ui,
feature, direction).

- 2026-11-10 [scope][feature]: rotate, translate and scale a decal after placement.
- 2026-11-10 [tested][bug]: weird results on real parts that aren't planar or rectangular.
- 2026-11-10 [decide][ui]: the panel goes in the Material tab.
- 2026-11-10 [decide][ui]: ExtraBold looks best.
- 2026-11-10 [decide][direction]: "decal" in the name; Inkstamp too close to Inkscape; Decal Press.
- 2026-11-09 [correct][ui]: the sidebar is crowded; two-letter compact tabs are hard to scan.
- 2026-11-09 [decide][direction]: test on 5.2 only and adjust the compatibility claims.
- 2026-11-09 [scope][feature]: Replace background defaults to the existing material's color.
- 2026-11-09 [scope][feature]: bundle a font, with a failsafe when it won't load.
- 2026-11-09 [decide][ui]: default decal color pure black.
- 2026-11-09 [scope][feature]: image decals with a key color and fuzziness.
- 2026-11-09 [domain][direction]: layer the decal over the existing material instead of replacing it.
- 2026-11-09 [scope][feature]: the original brief: face text sized to height or width, live, packed for 3MF.
