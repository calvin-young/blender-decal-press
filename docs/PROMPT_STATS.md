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
| 3 | 5 | 8 | 7 | 23 |

## Sessions

| Date | Tool and model | Prompts | Steering lines | Notes |
|---|---|---|---|---|
| 2026-11-09/10 | Claude Code (workstation), Opus 5.5 | 6 | 13 | 0.1.0 to 0.4.0: text decals, layered and image decals, font, rename, fit on awkward faces, placement |
| 2026-11-11/24 | Claude Code (workstation), Fable 5.2 then Opus 5.5 | 6 (relayed by an orchestrating session) | 10 | Audit, vision, bug hunt, 0.5.0 |

## Steering

Newest first, tagged with its kind (decide, correct, domain, tested, scope) and category (bug, ui,
feature, direction).

- 2026-11-23 [domain][direction]: 580 and Dual Tone resolve the same: 600 dpi printhead, bleed to about the PA 12 grain; smallest text about 2 mm; orientation doesn't change color.
- 2026-11-23 [decide][direction]: Dual Tone is a real target (5600 now, 1200 in about a year).
- 2026-11-23 [decide][direction]: sharp text always comes first; image size won't be a problem.
- 2026-11-23 [tested][bug]: decals project through and show inverted on the backs of parts; not usable, mostly for text.
- 2026-11-12 [scope][feature]: keep an exact-faces placement mode beside placement on the surface, with a switch.
- 2026-11-12 [scope][feature]: a Flatten button baking layers into one texture, also as a 3MF export option.
- 2026-11-11 [scope][ui]: a panel location preference, the same in all the add-ons.
- 2026-11-11 [tested][bug]: decals invisible in Solid shading, so a part could print with a decal nobody saw.
- 2026-11-11 [correct][direction]: the Resolution setting shouldn't be needed; the same look at any size.
- 2026-11-11 [tested][feature]: images on Suzanne with Subdivision distort oddly.
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
