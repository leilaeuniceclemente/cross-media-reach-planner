# Cross-Media Reach Console

An interactive cross-media reach and frequency planner. It models how a campaign's
reach, frequency, and brand awareness respond as spend moves across TV, radio, OOH, and
digital platforms, and it reframes success from absolute reach to awareness growth.

**Live demo:** https://leilistiic.github.io/cross-media-reach-planner/

All data is **synthetic and reproducible**. There are no real rate cards, brands,
audiences, or business context anywhere in this repository.

---

## What it does

**Tab 1 — Consumption and share of mind (the diagnostic).**
- A share-of-mind slopegraph from year-ago to this-year: traditional platforms hold reach
  while their share of mind erodes, digital platforms carry the growth.
- An Affluent / Mass / All audience toggle on both share of mind and reach. Digital
  indexes higher among affluent on level, but the fastest digital reach growth is in mass.
- A per-brand view across eight quarters showing net reach (flat and high), unaided
  awareness, and top-of-mind awareness, with the best three quarters flagged. Net reach
  stays near the ceiling throughout, which is why a headline reach number can hide a
  falling awareness trend.

**Tab 2 — Cross-media mix planner (the recommendation).**
- Spend sliders per platform with live per-platform reach, frequency, and a
  reach-against-ceiling meter (population reach and in-platform reach shown separately).
- A live cross-media reach readout that renders Sainsbury's de-duplication formula term
  by term as spend changes.
- A brand filter. Each brand gets its own recommended plan, built from the reach mix that
  ran during its highest-awareness quarters and weighted by the share-of-mind multiplier,
  with projected unaided and top-of-mind awareness.

---

## How it works

**Single-medium reach.** Each platform's exposure distribution is a Negative Binomial with
a structural-zero reachable-base cap. From a GRP level it yields reach at 1+, 2+, and 3+,
plus average frequency.

**Cross-media reach.** Platforms combine with Sainsbury's random-duplication formula,
`CMR(k+) = 1 - product over platforms of (1 - reach_i(k+))`.

**Share of mind.** Attention minutes are `minutes per viewer x viewers`, normalised to a
share per platform, tracked year-ago and this-year, and split by audience segment.

**Awareness.** Each brand carries unaided and top-of-mind awareness across the quarters,
driven by that quarter's reach-and-share-of-mind mix. Unaided saturates toward a ceiling,
so for larger brands it plateaus and top-of-mind becomes the benchmark; smaller brands
still have unaided headroom. The benchmark metric selects the brand's best quarters, and
those quarters supply the reach targets the recommendation aims for.

A fuller write-up of the model and every data field is in
[`DATA_DICTIONARY.md`](DATA_DICTIONARY.md).

---

## Reproduce

```bash
python3 scripts/01_generate_data.py   # builds the labelled CSVs and data.json
python3 scripts/02_build_index.py     # injects data.json into the template -> index.html
```

Re-run order is always `01` then `02`. Script `01` generates the synthetic data with a
fixed seed, so output is identical on every run. Script `02` is a pure templating step.

To use real (anonymised) numbers later, match the CSV schemas documented in the data
dictionary, drop the files into `data/`, and re-run `01` then `02`.

---

## Repository layout

```
index.html               self-contained interactive page (the live tool)
index_template.html       template with a __DATA__ placeholder
data.json                 runtime bundle the page reads (injected by 02)
DATA_DICTIONARY.md        model write-up and column definitions
scripts/
  01_generate_data.py     synthetic data generator
  02_build_index.py       builder (template + data.json -> index.html)
data/                     labelled CSV companion tables
  platform_params.csv
  share_of_mind.csv
  segment_consumption.csv
  media_consumption.csv
  reach_frequency_by_brand.csv
  brand_awareness.csv
  reach_curves.csv
  mix_scenarios.csv
previews/                 static screenshots
```

---

## Notes

- The page is a single self-contained HTML file. All charts are inline SVG and all
  computation runs client-side in vanilla JavaScript, mirroring the Python model exactly.
- No external scripts, fonts, or network calls. It runs offline.
- The page is tagged `noindex, nofollow`.
- Built for desktop and mobile.

## Tech

Python for data generation. Vanilla HTML, CSS, and JavaScript for the page, with no
frameworks or build step beyond the templating script.
