# Data Dictionary — Media Reach & Frequency Model

All data here is **synthetic and reproducible** (fixed seed in `scripts/01_generate_data.py`).
No real rate cards, brands, audiences, or business context appear anywhere. The numbers are
shaped so that one genuine insight is discoverable: traditional platforms carry high absolute
reach but **declining share of mind**, digital platforms carry **rising share of mind** and are
under-invested, so a plan that chases absolute reach loses awareness momentum versus a year ago,
and reallocating spend from TV into digital is what grows awareness.

To swap in real (anonymised) numbers later: match these column schemas, drop the files into
`data/`, and re-run `01` then `02`. No code changes needed if the columns line up.

---

## The model (one page)

**Single-medium reach.** Each platform's exposure distribution is a Negative Binomial (NBD)
with a structural-zero "reachable base" cap:

- `cover_max` — the fraction of the universe the platform can ever reach (1+ ceiling).
- `r` — NBD shape. Higher `r` spreads exposures evenly → reach builds faster per GRP.
  Lower `r` concentrates exposures → frequency piles up, incremental reach is poorer.
- Mean exposures among the reachable base: `lambda = (GRP/100) / cover_max`.
- `reach(k+) = cover_max * (1 - sum of NBD pmf for n < k)`.
- `avg_frequency = (GRP/100) / reach(1+)`.

**Cross-Media Reach (CMR).** Platforms are combined with **Sainsbury's random-duplication
formula** (independence assumption):

> `CMR(k+) = 1 - product over platforms of (1 - reach_i(k+))`

`blended_frequency = (sum of GRP/100) / CMR(1+)`.

**Share of Mind (SoM).** `attention_minutes = avg_minutes_per_viewer * viewers`. SoM% is each
platform's attention minutes as a share of the total. Computed for this year (TY) and a year ago
(YA); the YA→TY shift is the engine of the insight.

**Awareness Index.** `100 * sum over platforms of (0.5*reach1+ + 0.5*reach3+) * SoM_ty`.
Values both being seen at all and being seen at effective frequency, weighted by mind share.

**Awareness Momentum vs YA.** `100 * sum of (0.5*reach1+ + 0.5*reach3+) * (SoM_ty - SoM_ya)`.
Positive when the plan leans into rising-mind platforms, negative when it leans on declining-mind
ones. This is the "are we growing vs year ago" reframe, made into a number.

**Cost.** `cost_per_GRP = cpm * universe / 100000`; `spend = GRP * cost_per_GRP`.

---

## Files

### `data/platform_params.csv` — the latent parameters
| column | meaning |
|---|---|
| platform | display name |
| group | `traditional` or `digital` |
| reachable_base_pct | `cover_max` as a percent (1+ reach ceiling) |
| nbd_shape_r | NBD shape parameter `r` |
| cpm_PHP | synthetic cost per thousand impressions |
| grp_ceiling | max GRPs the platform can deliver (inventory) |
| share_of_mind_ty_pct | this-year share of mind |
| share_of_mind_ya_pct | year-ago share of mind |
| som_delta_ppt | TY minus YA, in percentage points |

### `data/share_of_mind.csv` — pillar 1: minutes × viewers
| column | meaning |
|---|---|
| platform | display name |
| period | `This year` or `Year ago` |
| avg_minutes_per_viewer | mins per viewer per quarter |
| viewers_millions | people viewing the platform |
| attention_minutes_mn | minutes × viewers (attention units) |
| share_of_mind_pct | normalised share of total attention |

### `data/media_consumption.csv` — pillar 2: Nielsen-style reach trend
| column | meaning |
|---|---|
| platform | display name |
| quarter | `Q1 YA`…`Q4 TY` (8 quarters) |
| reach_1plus_pct | 1+ reach at a reference investment |
| population_viewing_mn | people viewing |
| avg_minutes_per_viewer | mins per viewer |

### `data/reach_frequency_by_brand.csv` — pillar 3: historical R&F by brand
| column | meaning |
|---|---|
| brand | synthetic brand name |
| platform | display name |
| period | `Year ago` or `This year` |
| grp | gross rating points |
| reach_1plus_pct | 1+ reach |
| reach_3plus_pct | 3+ (effective) reach |
| avg_frequency | average frequency among reached |

### `data/reach_curves.csv` — spend → reach, sampled (rigor)
| column | meaning |
|---|---|
| platform | display name |
| grp | gross rating points |
| spend_PHP_mn | implied spend, millions |
| reach_1plus_pct / reach_2plus_pct / reach_3plus_pct | reach at 1+/2+/3+ |
| avg_frequency | average frequency among reached |

### `data/mix_scenarios.csv` — TV-skewed baseline vs recommended
Per-platform spend share, GRP, and reach for each scenario, followed by scenario-level
metrics (CMR 1+, CMR 3+, blended frequency, Awareness Index, Awareness Momentum vs YA).

### `data/segment_consumption.csv` — audience segments (Affluent vs Mass)
| column | meaning |
|---|---|
| segment | `Affluent` or `Mass` |
| platform | display name |
| group | `traditional` or `digital` |
| period | `Year ago` or `This year` |
| reach_within_segment_pct | penetration / reach inside that segment |
| share_of_mind_pct | share of mind within that segment |

Digital indexes higher among affluent on level; digital reach growth is fastest among mass.

### `data.json` — runtime bundle
Parameters the dashboard reads to compute everything live in JavaScript (the same NBD +
Sainsbury math as above). Beyond the platform parameters it also carries: `segments`
(affluent / mass / all share of mind and reach, year-ago and this-year), `brand_series`
(per-brand 8-quarter reach trend, net and effective cross-media reach, best three quarters),
and `brand_plans` (per-brand do-nothing baseline and recommended spend, the latter built
from each brand's historical reach highs tilted by the share-of-mind multiplier). The CSVs
are for inspection and rigor; the live site is `index.html`.

---

## Reproduce
```
python3 scripts/01_generate_data.py   # builds CSVs + data.json
python3 scripts/02_build_index.py     # builds index.html from index_template.html
```
Re-run order is always `01` then `02`.
