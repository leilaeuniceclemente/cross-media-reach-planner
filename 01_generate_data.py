#!/usr/bin/env python3
"""
01_generate_data.py
-------------------
Generates the synthetic dataset for the Media Reach & Frequency Model portfolio tool.

Everything here is SYNTHETIC and reproducible (fixed seed). No real rate cards,
brands, or business context. The data is shaped so that a genuine, discoverable
insight is baked in: traditional platforms (Free TV, Radio, OOH) carry high
absolute reach but their SHARE OF MIND is eroding year on year, while digital
platforms (Meta, YouTube, TikTok) carry rising share of mind and are under
invested. A plan that maximises absolute reach therefore loses awareness
momentum versus a year ago, and reallocating spend from TV into digital is what
grows awareness.

Three data pillars (mirroring the real methodology):
  1. media_consumption.csv     - Nielsen-style reach / population viewing by quarter
  2. share_of_mind.csv         - minutes spent x viewers -> attention-minutes -> SoM%
  3. reach_frequency_by_brand.csv - historical 1+/3+ reach and avg frequency by brand

Plus, for rigor / inspection:
  - reach_curves.csv           - spend -> reach(1+/2+/3+), avg freq sampled per platform
  - platform_params.csv        - the latent parameters driving everything
  - mix_scenarios.csv          - TV-skewed baseline vs recommended mix, with outcomes

And the runtime bundle:
  - ../data.json               - parameters the dashboard reads to compute live in JS

Reach model (single medium): Negative Binomial Distribution (NBD) of exposures with
a structural-zero "reachable base" cap. Cross-media combination: Sainsbury's random
duplication formula, CMR(k+) = 1 - prod(1 - reach_i(k+)).
"""

import csv
import json
import math
import os
import random

random.seed(20260622)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

CURRENCY = "PHP"
UNIVERSE = 60_000_000          # synthetic target universe (All Adults), people
EFFECTIVE_FREQ = 3             # default effective frequency threshold (n+)
QUARTERS = ["Q1 YA", "Q2 YA", "Q3 YA", "Q4 YA", "Q1 TY", "Q2 TY", "Q3 TY", "Q4 TY"]
#   YA = year ago, TY = this year. 8 quarters of trend.

# ----------------------------------------------------------------------------
# LATENT PLATFORM PARAMETERS  (synthetic)
# ----------------------------------------------------------------------------
# cover_max : reachable fraction of the universe (structural ceiling on 1+ reach)
# r         : NBD shape. Higher r -> exposures spread more evenly -> reach builds
#             faster per GRP. Lower r -> exposures pile onto a narrow group ->
#             frequency concentrates, incremental reach is poorer.
# cpm       : synthetic cost per thousand impressions, in CURRENCY
# grp_max   : inventory ceiling on GRPs the platform can deliver
# group     : "traditional" or "digital"
# som_minutes_ya / som_minutes_ty : avg minutes per viewer per quarter (drives SoM)
# som_viewers_ya / som_viewers_ty : people viewing (millions) (drives SoM)
#
# The SoM trend is the engine of the insight: traditional minutes & viewers drift
# DOWN from year-ago to this-year, digital drift UP.
PLATFORMS = [
    # Free TV: high reachable base and high NBD shape -> reach saturates FAST, so a
    # large spend cut barely dents reach (the "we were buying wasted frequency" point).
    dict(key="tv",    name="Free TV",  group="traditional",
         cover_max=0.88, r=3.00, cpm=240, grp_max=900,
         som_minutes_ya=128, som_minutes_ty=115, som_viewers_ya=44.0, som_viewers_ty=40.5),
    dict(key="radio", name="Radio",    group="traditional",
         cover_max=0.30, r=1.70, cpm=95,  grp_max=500,
         som_minutes_ya=40,  som_minutes_ty=35,  som_viewers_ya=15.0, som_viewers_ty=13.5),
    dict(key="ooh",   name="OOH",      group="traditional",
         cover_max=0.45, r=2.80, cpm=80,  grp_max=420,
         som_minutes_ya=12,  som_minutes_ty=12,  som_viewers_ya=31.0, som_viewers_ty=30.0),
    # Digital ordered for investment priority Meta > YouTube > TikTok: Meta has the
    # broadest reachable base and cheapest efficient reach, YouTube next, TikTok smallest.
    dict(key="meta",  name="Meta",     group="digital",
         cover_max=0.80, r=1.60, cpm=140, grp_max=1100,
         som_minutes_ya=52,  som_minutes_ty=66,  som_viewers_ya=33.0, som_viewers_ty=38.0),
    dict(key="yt",    name="YouTube",  group="digital",
         cover_max=0.72, r=1.80, cpm=165, grp_max=1100,
         som_minutes_ya=60,  som_minutes_ty=82,  som_viewers_ya=30.0, som_viewers_ty=35.0),
    dict(key="tt",    name="TikTok",   group="digital",
         cover_max=0.55, r=1.40, cpm=130, grp_max=1000,
         som_minutes_ya=34,  som_minutes_ty=60,  som_viewers_ya=20.0, som_viewers_ty=29.0),
]

# Synthetic brands for the historical R&F pillar. Generic, no real names.
BRANDS = ["Brand Aster", "Brand Briar", "Brand Cedar", "Brand Dune",
          "Brand Ember", "Brand Fern", "Brand Grove", "Brand Haven",
          "Brand Ivory", "Brand Juno"]


# ----------------------------------------------------------------------------
# REACH MODEL  (must match the JS in index_template.html exactly)
# ----------------------------------------------------------------------------
def nbd_pmf(r, lam, nmax):
    """NBD probability of exactly n exposures, n = 0..nmax, via stable recurrence."""
    if lam <= 0:
        p = [0.0] * (nmax + 1)
        p[0] = 1.0
        return p
    p0 = (r / (r + lam)) ** r
    p = [0.0] * (nmax + 1)
    p[0] = p0
    ratio = lam / (lam + r)
    for n in range(1, nmax + 1):
        p[n] = p[n - 1] * ((r + n - 1) / n) * ratio
    return p


def cpp(cpm, universe):
    """Cost per GRP (one rating point) = cost of impressions equal to 1% of universe."""
    return cpm * universe / 100_000.0


def grp_from_spend(spend, cpm, universe):
    return spend / cpp(cpm, universe) if spend > 0 else 0.0


def platform_reach(grp, p, universe=UNIVERSE, nmax=40):
    """
    Single-medium reach for one platform at a GRP level.
    Returns dict with reach at 1+/2+/3+ (fractions of universe) and avg frequency.
    """
    cover = p["cover_max"]
    if grp <= 0 or cover <= 0:
        return dict(r1=0.0, r2=0.0, r3=0.0, avg_freq=0.0, grp=grp)
    lam = (grp / 100.0) / cover           # mean exposures among the reachable base
    pmf = nbd_pmf(p["r"], lam, nmax)
    # reach(k+) over the FULL universe = cover * (1 - sum_{n<k} pmf)
    cum = 0.0
    r_at = {}
    for k in (1, 2, 3):
        cum_below = sum(pmf[0:k])
        r_at[k] = cover * (1.0 - cum_below)
    r1 = r_at[1]
    avg_freq = (grp / 100.0) / r1 if r1 > 0 else 0.0
    return dict(r1=r1, r2=r_at[2], r3=r_at[3], avg_freq=avg_freq, grp=grp)


def sainsbury(reaches):
    """Cross-Media Reach: 1 - prod(1 - r_i). Random duplication / independence."""
    prod = 1.0
    for r in reaches:
        prod *= (1.0 - r)
    return 1.0 - prod


def grp_for_reach(target_reach, p, universe=UNIVERSE):
    """Invert the reach model: GRPs needed to hit a target POPULATION reach (1+)."""
    c = p["cover_max"]
    R = min(target_reach, c * 0.999)
    if R <= 0:
        return 0.0
    p0 = 1.0 - R / c                       # required NBD P(0) among reachable
    r = p["r"]
    lam = r * (p0 ** (-1.0 / r) - 1.0)     # invert P0 = (r/(r+lam))^r
    return lam * c * 100.0                  # GRP = lam * cover * 100


# ----------------------------------------------------------------------------
# SHARE OF MIND  (minutes spent x people viewing -> attention-minutes -> SoM%)
# ----------------------------------------------------------------------------
def attention_minutes(minutes, viewers_millions):
    return minutes * viewers_millions          # arbitrary attention units (millions of minutes)


def som_table(period):  # period in {"ya","ty"}
    raw = {}
    for p in PLATFORMS:
        m = p[f"som_minutes_{period}"]
        v = p[f"som_viewers_{period}"]
        raw[p["key"]] = attention_minutes(m, v)
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}, raw


SOM_TY, ATT_TY = som_table("ty")
SOM_YA, ATT_YA = som_table("ya")


# ----------------------------------------------------------------------------
# WRITE: platform_params.csv
# ----------------------------------------------------------------------------
with open(os.path.join(DATA, "platform_params.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["platform", "group", "reachable_base_pct", "nbd_shape_r",
                "cpm_" + CURRENCY, "grp_ceiling", "share_of_mind_ty_pct",
                "share_of_mind_ya_pct", "som_delta_ppt"])
    for p in PLATFORMS:
        k = p["key"]
        w.writerow([p["name"], p["group"], round(p["cover_max"] * 100, 1), p["r"],
                    p["cpm"], p["grp_max"], round(SOM_TY[k] * 100, 1),
                    round(SOM_YA[k] * 100, 1),
                    round((SOM_TY[k] - SOM_YA[k]) * 100, 1)])

# ----------------------------------------------------------------------------
# WRITE: share_of_mind.csv  (the pillar: minutes x viewers)
# ----------------------------------------------------------------------------
with open(os.path.join(DATA, "share_of_mind.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["platform", "period", "avg_minutes_per_viewer", "viewers_millions",
                "attention_minutes_mn", "share_of_mind_pct"])
    for period, som, att, label in [("ty", SOM_TY, ATT_TY, "This year"),
                                    ("ya", SOM_YA, ATT_YA, "Year ago")]:
        for p in PLATFORMS:
            k = p["key"]
            w.writerow([p["name"], label, p[f"som_minutes_{period}"],
                        p[f"som_viewers_{period}"], round(att[k], 1),
                        round(som[k] * 100, 1)])

# ----------------------------------------------------------------------------
# WRITE: media_consumption.csv  (Nielsen-style reach trend by quarter)
# ----------------------------------------------------------------------------
# Quarterly 1+ reach per platform at a reference investment, drifting with the
# SoM story: traditional flat-to-down, digital climbing.
def quarter_factor(p, qi):
    """Multiplier on reference reach across the 8 quarters."""
    # qi 0..7; YA quarters 0..3, TY quarters 4..7
    base = 1.0
    if p["group"] == "traditional":
        drift = -0.015 * qi                       # slow erosion
    else:
        drift = 0.020 * qi                        # steady climb
    seasonal = 0.03 * math.sin(qi / 1.6)          # mild seasonality
    noise = random.uniform(-0.012, 0.012)
    return max(0.4, base + drift + seasonal + noise)

REF_GRP = 350.0
with open(os.path.join(DATA, "media_consumption.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["platform", "quarter", "reach_1plus_pct", "population_viewing_mn",
                "avg_minutes_per_viewer"])
    for p in PLATFORMS:
        for qi, q in enumerate(QUARTERS):
            rr = platform_reach(REF_GRP, p)
            qf = quarter_factor(p, qi)
            reach = min(p["cover_max"], rr["r1"] * qf)
            # interpolate minutes between YA and TY across quarters
            t = qi / (len(QUARTERS) - 1)
            mins = p["som_minutes_ya"] + (p["som_minutes_ty"] - p["som_minutes_ya"]) * t
            viewers = (p["som_viewers_ya"]
                       + (p["som_viewers_ty"] - p["som_viewers_ya"]) * t)
            w.writerow([p["name"], q, round(reach * 100, 1),
                        round(viewers, 1), round(mins, 1)])

# ----------------------------------------------------------------------------
# WRITE: reach_frequency_by_brand.csv  (historical R&F by brand x platform)
# ----------------------------------------------------------------------------
# Each brand has a slightly different baseline spend intensity and a platform
# tilt; older periods are more TV-tilted (the latent "everyone was TV-skewed").
with open(os.path.join(DATA, "reach_frequency_by_brand.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["brand", "platform", "period", "grp", "reach_1plus_pct",
                "reach_3plus_pct", "avg_frequency"])
    for b in BRANDS:
        intensity = random.uniform(0.7, 1.4)
        for p in PLATFORMS:
            for period, label in [("ya", "Year ago"), ("ty", "This year")]:
                # TV tilt shrinks this year; digital tilt grows this year
                if p["group"] == "traditional":
                    tilt = 1.25 if period == "ya" else 1.0
                else:
                    tilt = 0.7 if period == "ya" else 1.15
                grp = max(0.0, REF_GRP * intensity * tilt
                          * random.uniform(0.6, 1.1)
                          * (p["grp_max"] / 900.0))
                grp = min(grp, p["grp_max"])
                rr = platform_reach(grp, p)
                w.writerow([b, p["name"], label, round(grp, 0),
                            round(rr["r1"] * 100, 1), round(rr["r3"] * 100, 1),
                            round(rr["avg_freq"], 2)])

# ----------------------------------------------------------------------------
# WRITE: reach_curves.csv  (spend -> reach sampled, for rigor)
# ----------------------------------------------------------------------------
with open(os.path.join(DATA, "reach_curves.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["platform", "grp", "spend_" + CURRENCY + "_mn", "reach_1plus_pct",
                "reach_2plus_pct", "reach_3plus_pct", "avg_frequency"])
    for p in PLATFORMS:
        steps = 18
        for i in range(steps + 1):
            grp = p["grp_max"] * i / steps
            rr = platform_reach(grp, p)
            spend = grp * cpp(p["cpm"], UNIVERSE)
            w.writerow([p["name"], round(grp, 0), round(spend / 1e6, 2),
                        round(rr["r1"] * 100, 1), round(rr["r2"] * 100, 1),
                        round(rr["r3"] * 100, 1), round(rr["avg_freq"], 2)])

# ----------------------------------------------------------------------------
# AWARENESS METRICS  (effective-reach weighted by share of mind)
# ----------------------------------------------------------------------------
def plan_outcomes(spend_by_key, ef=EFFECTIVE_FREQ):
    """Given spend (CURRENCY) per platform key, compute the full outcome set."""
    per = {}
    reaches_1, reaches_2, reaches_3 = [], [], []
    total_grp = 0.0
    total_spend = 0.0
    ai_ty = ai_ya = 0.0
    momentum = 0.0
    for p in PLATFORMS:
        k = p["key"]
        spend = spend_by_key.get(k, 0.0)
        grp = min(grp_from_spend(spend, p["cpm"], UNIVERSE), p["grp_max"])
        rr = platform_reach(grp, p)
        per[k] = dict(name=p["name"], spend=spend, grp=grp,
                      r1=rr["r1"], r3=rr["r3"], avg_freq=rr["avg_freq"])
        reaches_1.append(rr["r1"]); reaches_2.append(rr["r2"]); reaches_3.append(rr["r3"])
        total_grp += grp
        total_spend += spend
        # Awareness proxy = share of audience ATTENTION actually reached: 1+ reach
        # weighted by each platform's share of mind. Being present where attention is
        # growing (digital) builds awareness; being present where it is shrinking (TV)
        # does not, even at high reach. This operationalises "grow vs year ago".
        aware_unit = rr["r1"]
        ai_ty += aware_unit * SOM_TY[k]
        ai_ya += aware_unit * SOM_YA[k]
        momentum += aware_unit * (SOM_TY[k] - SOM_YA[k])
    cmr1 = sainsbury(reaches_1)
    cmr3 = sainsbury(reaches_3)
    blended_freq = (total_grp / 100.0) / cmr1 if cmr1 > 0 else 0.0
    return dict(per=per, cmr1=cmr1, cmr3=cmr3, blended_freq=blended_freq,
                total_grp=total_grp, total_spend=total_spend,
                awareness_index=ai_ty * 100, awareness_index_ya=ai_ya * 100,
                awareness_momentum=momentum * 100)


def greedy_optimize(budget, metric="awareness_index", ef=EFFECTIVE_FREQ, chunks=240,
                    max_share=0.30):
    """Allocate budget in chunks to the platform with best marginal gain on metric.
    max_share caps any single platform so the result is a planner-credible mix,
    not a corner solution that zeroes out a whole medium."""
    spend = {p["key"]: 0.0 for p in PLATFORMS}
    step = budget / chunks
    grp_caps = {p["key"]: p["grp_max"] * cpp(p["cpm"], UNIVERSE) for p in PLATFORMS}
    caps = {k: min(grp_caps[k], budget * max_share) for k in grp_caps}

    def score(s):
        o = plan_outcomes(s)
        if metric == "cmr":
            return o["cmr1"]
        if metric == "effective_reach":
            return o["cmr3"]
        if metric == "reach_per_spend":
            return o["cmr1"]
        return o["awareness_index"]

    for _ in range(chunks):
        base = score(spend)
        best_k, best_gain = None, -1e18
        for p in PLATFORMS:
            k = p["key"]
            if spend[k] + step > caps[k]:
                continue
            trial = dict(spend); trial[k] += step
            gain = score(trial) - base
            if gain > best_gain:
                best_gain, best_k = gain, k
        if best_k is None or best_gain <= 0:
            # if nothing improves the metric, top up the cheapest reach builder
            best_k = min((p for p in PLATFORMS if spend[p["key"]] + step <= caps[p["key"]]),
                         key=lambda p: p["cpm"], default=None)
            if best_k is None:
                break
            best_k = best_k["key"]
        spend[best_k] += step
    return spend


# ----------------------------------------------------------------------------
# WRITE: mix_scenarios.csv  (TV-skewed baseline vs recommended)
# ----------------------------------------------------------------------------
BUDGET = 90_000_000   # synthetic baseline media budget, CURRENCY

# Baseline: heavily TV-skewed (~90% Free TV), digital near-zero (the whitespace).
baseline_weights = dict(tv=0.90, radio=0.03, ooh=0.025, meta=0.018, yt=0.015, tt=0.012)
baseline_spend = {k: BUDGET * wv for k, wv in baseline_weights.items()}
base_out = plan_outcomes(baseline_spend)

# Recommended plan, briefed the way a planner does: target a reach change per platform.
# TV trims only slightly (it was saturated), digital grows materially, ranked
# Meta > YouTube > TikTok. Invert reach -> GRP -> spend to hit the 1+ targets, then
# reinvest the freed TV budget into digital FREQUENCY (constant total budget) to lift
# effective reach. This is the "same money, reallocated TV -> digital" plan.
REACH_DELTA = dict(tv=-0.04, radio=+0.01, ooh=+0.01,
                   meta=+0.20, yt=+0.18, tt=+0.15)

recommended_spend = {}
for p in PLATFORMS:
    k = p["key"]
    base_reach = base_out["per"][k]["r1"]
    target = max(0.0, min(p["cover_max"] * 0.999, base_reach + REACH_DELTA[k]))
    grp = min(grp_for_reach(target, p), p["grp_max"])
    recommended_spend[k] = grp * cpp(p["cpm"], UNIVERSE)
rec_out = plan_outcomes(recommended_spend)

# Year-ago reference = what last year's TV-heavy plan delivered under last year's
# consumption. Growth vs YA compares a plan's awareness now against that reference;
# growth vs do-nothing compares it against keeping the TV-heavy plan this year.
REF_YA = base_out["awareness_index_ya"]
def growth_vs_ya(out):
    return (out["awareness_index"] / REF_YA - 1.0) * 100.0 if REF_YA > 0 else 0.0
def growth_vs_donothing(out):
    return (out["awareness_index"] / base_out["awareness_index"] - 1.0) * 100.0 \
        if base_out["awareness_index"] > 0 else 0.0

# Optional: the model's own awareness-maximising allocation (separate explore feature
# in the live tool, not the headline recommendation).
model_opt_spend = greedy_optimize(BUDGET, metric="awareness_index")

with open(os.path.join(DATA, "mix_scenarios.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["scenario", "platform", "spend_share_pct", "grp",
                "reach_1plus_pct", "reach_3plus_pct"])
    for label, out, spend in [("TV-skewed baseline", base_out, baseline_spend),
                              ("Recommended mix", rec_out, recommended_spend)]:
        tot = sum(spend.values())
        for p in PLATFORMS:
            k = p["key"]
            w.writerow([label, p["name"], round(spend[k] / tot * 100, 1),
                        round(out["per"][k]["grp"], 0),
                        round(out["per"][k]["r1"] * 100, 1),
                        round(out["per"][k]["r3"] * 100, 1)])
    w.writerow([])
    w.writerow(["scenario", "metric", "value", "", "", ""])
    for label, out in [("TV-skewed baseline", base_out), ("Recommended mix", rec_out)]:
        w.writerow([label, "Cross-Media Reach 1+ (%)", round(out["cmr1"] * 100, 1), "", "", ""])
        w.writerow([label, "Cross-Media Reach 3+ (%)", round(out["cmr3"] * 100, 1), "", "", ""])
        w.writerow([label, "Blended frequency", round(out["blended_freq"], 2), "", "", ""])
        w.writerow([label, "Awareness Index", round(out["awareness_index"], 1), "", "", ""])
        w.writerow([label, "Awareness Momentum vs YA", round(out["awareness_momentum"], 1), "", "", ""])

# ----------------------------------------------------------------------------
# WRITE runtime bundle: ../data.json
# ----------------------------------------------------------------------------
bundle = dict(
    meta=dict(currency=CURRENCY, universe=UNIVERSE, effective_freq=EFFECTIVE_FREQ,
              default_budget=BUDGET, quarters=QUARTERS,
              note="Synthetic, reproducible data. No real rate cards, brands, or business context."),
    platforms=[dict(key=p["key"], name=p["name"], group=p["group"],
                    cover_max=p["cover_max"], r=p["r"], cpm=p["cpm"],
                    grp_max=p["grp_max"],
                    som_ty=SOM_TY[p["key"]], som_ya=SOM_YA[p["key"]],
                    minutes_ty=p["som_minutes_ty"], minutes_ya=p["som_minutes_ya"],
                    viewers_ty=p["som_viewers_ty"], viewers_ya=p["som_viewers_ya"])
               for p in PLATFORMS],
    baseline_weights=baseline_weights,
    baseline_spend=baseline_spend,
    recommended_spend=recommended_spend,
    model_opt_spend=model_opt_spend,
    brands=BRANDS,
)

# brand R&F for the dashboard brand selector: a full quarterly trend per brand across
# 8 quarters (Q1 YA .. Q4 TY). Traditional investment/reach drifts down, digital drifts
# up, so each brand shows the category shift. We also compute the blended Cross-Media
# Reach (Sainsbury) per quarter and flag each brand's best three quarters by CMR, which
# is exactly the "find the highest-reach quarters" diagnostic.
def brand_quarter_grp(p, qi, intensity, tilt):
    BRAND_SCALE = 0.22                      # operate below saturation so plans need no CMR cap
    if p["group"] == "traditional":
        trend = 1.20 - 0.045 * qi          # declining investment / delivery
    else:
        trend = 0.45 + 0.085 * qi          # ramping up
    seasonal = 1.0 + 0.10 * math.sin(qi / 1.4 + (len(p["name"]) % 4))
    noise = random.uniform(0.82, 1.15)
    grp = (REF_GRP * BRAND_SCALE * intensity * tilt[p["key"]] * max(0.1, trend)
           * seasonal * noise * (p["grp_max"] / 900.0))
    return min(p["grp_max"], grp)

# Each brand gets a distinctive historical signature: a digital platform it over-indexes
# on, plus its own TV reliance. This is what makes the per-brand recommendations differ.
DIGITAL_KEYS = ["meta", "yt", "tt"]
brand_tilt = {}
for b in BRANDS:
    primary = random.choice(DIGITAL_KEYS)
    t = {p["key"]: random.uniform(0.85, 1.15) for p in PLATFORMS}
    t[primary] *= random.uniform(1.4, 1.7)          # historical strength on one digital
    t["tv"] *= random.uniform(0.78, 1.28)           # TV reliance varies by brand
    brand_tilt[b] = t

# Brand awareness maturity: bigger brands carry high, plateauing unaided awareness, so
# top-of-mind becomes their benchmark; smaller brands still have unaided headroom.
brand_maturity = {}
for i, b in enumerate(BRANDS):
    brand_maturity[b] = random.uniform(0.71, 0.80) if i < 4 else random.uniform(0.46, 0.64)

UBA_CEIL, TOMA_CEIL = 0.88, 0.62
UBA_THRESHOLD = 70.0                 # mean unaided awareness above this -> benchmark on TOMA

brand_series = {}
brand_aware_model = {}
for b in BRANDS:
    intensity = random.uniform(0.75, 1.35)
    tilt = brand_tilt[b]
    platforms_reach = {p["name"]: [] for p in PLATFORMS}
    platforms_freq = {p["name"]: [] for p in PLATFORMS}
    cmr1, pressure = [], []
    for qi in range(len(QUARTERS)):
        r1s = []
        for p in PLATFORMS:
            grp = brand_quarter_grp(p, qi, intensity, tilt)
            rr = platform_reach(grp, p)
            platforms_reach[p["name"]].append(round(rr["r1"] * 100, 1))
            platforms_freq[p["name"]].append(round(rr["avg_freq"], 2))
            r1s.append(rr["r1"])
        cmr1.append(round(sainsbury(r1s) * 100, 1))
        # media awareness pressure that quarter = reach weighted by share of mind
        pressure.append(sum((platforms_reach[p["name"]][qi] / 100.0) * SOM_TY[p["key"]]
                            for p in PLATFORMS))
    pmin, pmax = min(pressure), max(pressure)
    peff = [((x - pmin) / (pmax - pmin) if pmax > pmin else 0.5) for x in pressure]

    # Awareness is DRIVEN by the quarter's media pressure, so the highest-awareness
    # quarters are the ones with the strongest (digital-tilted) reach mix. Unaided
    # saturates toward a ceiling (flat for big brands); top-of-mind keeps responding.
    ubase = brand_maturity[b]
    uspan = 0.55 * (0.86 - ubase)        # large base -> small span -> plateau
    tbase = ubase * 0.45                 # top-of-mind sits below unaided
    tspan = 0.22
    uba, toma = [], []
    for qi in range(len(QUARTERS)):
        u = min(UBA_CEIL, ubase + uspan * peff[qi] + random.uniform(-0.012, 0.012))
        t = min(TOMA_CEIL, u * 0.92, tbase + tspan * peff[qi] + random.uniform(-0.012, 0.012))
        uba.append(round(u * 100, 1)); toma.append(round(t * 100, 1))

    mean_uba = sum(uba) / len(uba)
    benchmark = "toma" if mean_uba >= UBA_THRESHOLD else "uba"
    bvals = toma if benchmark == "toma" else uba
    best = sorted(sorted(range(len(bvals)), key=lambda i: -bvals[i])[:3])
    worst = sorted(sorted(range(len(bvals)), key=lambda i: bvals[i])[:3])

    summary = []
    for p in PLATFORMS:
        rs = platforms_reach[p["name"]]; fs = platforms_freq[p["name"]]
        summary.append(dict(platform=p["name"], group=p["group"],
                            r1_ya=round(sum(rs[:4]) / 4, 1), r1_ty=round(sum(rs[4:]) / 4, 1),
                            freq_ya=round(sum(fs[:4]) / 4, 2), freq_ty=round(sum(fs[4:]) / 4, 2)))
    brand_series[b] = dict(quarters=QUARTERS, platforms_reach=platforms_reach,
                           cmr1=cmr1, toma=toma, uba=uba, benchmark=benchmark,
                           uba_level=round(mean_uba, 1), best_quarters=best,
                           worst_quarters=worst, summary=summary)
    brand_aware_model[b] = dict(pmin=pmin, pmax=pmax, uba_base=ubase, uba_span=uspan,
                                toma_base=tbase, toma_span=tspan,
                                uba_ceil=UBA_CEIL, toma_ceil=TOMA_CEIL, benchmark=benchmark)
bundle["brand_series"] = brand_series

# ----------------------------------------------------------------------------
# PER-BRAND PLANS: the recommendation targets the reach mix that ran during the
# brand's highest-awareness quarters (on its benchmark metric); the do-nothing
# baseline is the reach mix from its lowest-awareness quarters.
# ----------------------------------------------------------------------------
CMR_CEIL = 0.945                     # keep per-brand combined reach inside the band
DIGITAL_KEYS = ["meta", "yt", "tt"]

def brand_plans(b):
    bs = brand_series[b]
    def mean_reach(qidxs):
        out = {}
        for p in PLATFORMS:
            arr = bs["platforms_reach"][p["name"]]
            out[p["key"]] = sum(arr[i] for i in qidxs) / len(qidxs) / 100.0
        return out
    rec_t = mean_reach(bs["best_quarters"])     # reach mix in highest-awareness quarters
    base_t = mean_reach(bs["worst_quarters"])   # reach mix in lowest-awareness quarters

    # trim only the digital block if combined reach tops the band (keeps it growing
    # vs the baseline, which has lower digital from the weaker quarters)
    def cmr_with(scale):
        rs = [rec_t["tv"], rec_t["radio"], rec_t["ooh"]] + [rec_t[k] * scale for k in DIGITAL_KEYS]
        return sainsbury(rs)
    scale = 1.0
    if cmr_with(1.0) > CMR_CEIL:
        loS, hiS = 0.0, 1.0
        for _ in range(40):
            mid = (loS + hiS) / 2
            if cmr_with(mid) > CMR_CEIL: hiS = mid
            else: loS = mid
        scale = (loS + hiS) / 2
    rec_final = dict(rec_t)
    for k in DIGITAL_KEYS:
        rec_final[k] = rec_t[k] * scale

    def to_spend(t):
        return {p["key"]: min(grp_for_reach(min(t[p["key"]], p["cover_max"] * 0.999), p),
                              p["grp_max"]) * cpp(p["cpm"], UNIVERSE) for p in PLATFORMS}
    return to_spend(base_t), to_spend(rec_final)

brand_plans_bundle = {}
for b in BRANDS:
    bsp, rsp = brand_plans(b)
    brand_plans_bundle[b] = dict(baseline_spend=bsp, recommended_spend=rsp,
                                 awareness=brand_aware_model[b])
bundle["brand_plans"] = brand_plans_bundle

# brand_awareness.csv for inspection
with open(os.path.join(DATA, "brand_awareness.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["brand", "quarter", "unaided_awareness_pct", "top_of_mind_pct",
                "benchmark_metric", "is_best_quarter"])
    for b in BRANDS:
        bs = brand_series[b]
        for qi, q in enumerate(bs["quarters"]):
            w.writerow([b, q, bs["uba"][qi], bs["toma"][qi], bs["benchmark"].upper(),
                        "yes" if qi in bs["best_quarters"] else ""])

# quarterly consumption series for the trend chart
series = {}
for p in PLATFORMS:
    pts = []
    for qi, q in enumerate(QUARTERS):
        rr = platform_reach(REF_GRP, p)
        qf = quarter_factor(p, qi)
        reach = min(p["cover_max"], rr["r1"] * qf)
        t = qi / (len(QUARTERS) - 1)
        mins = p["som_minutes_ya"] + (p["som_minutes_ty"] - p["som_minutes_ya"]) * t
        pts.append(dict(q=q, reach=round(reach*100,1), minutes=round(mins,1)))
    series[p["key"]] = pts
bundle["consumption_series"] = series

# ----------------------------------------------------------------------------
# AUDIENCE SEGMENTS: Affluent vs Mass
# ----------------------------------------------------------------------------
# Two cuts of the universe. Per platform we set, for each segment, a penetration
# (reach within the segment) and minutes per viewer, for year-ago and this-year.
# Invariants baked in:
#   - Digital LEVEL is higher among affluent (early adopters), both periods.
#   - Digital GROWTH (TY minus YA) is fastest among mass (the growth frontier).
#   - TV leans mass and erodes in both segments.
SEG_SHARE = dict(affluent=0.28, mass=0.72)

# pen = penetration / reach within segment; mn = avg minutes per viewer.  (ya, ty)
SEG = {
    "affluent": {
        "tv":    dict(pen=(0.80, 0.74), mn=(95, 72)),
        "radio": dict(pen=(0.30, 0.27), mn=(30, 26)),
        "ooh":   dict(pen=(0.55, 0.55), mn=(12, 12)),
        "meta":  dict(pen=(0.72, 0.78), mn=(60, 74)),
        "yt":    dict(pen=(0.68, 0.76), mn=(78, 92)),
        "tt":    dict(pen=(0.40, 0.52), mn=(45, 66)),
    },
    "mass": {
        "tv":    dict(pen=(0.90, 0.86), mn=(135, 100)),
        "radio": dict(pen=(0.34, 0.30), mn=(42, 32)),
        "ooh":   dict(pen=(0.47, 0.46), mn=(12, 12)),
        "meta":  dict(pen=(0.34, 0.56), mn=(46, 66)),   # +22 pts: fast
        "yt":    dict(pen=(0.30, 0.55), mn=(58, 78)),   # +25 pts: faster
        "tt":    dict(pen=(0.22, 0.48), mn=(30, 62)),   # +26 pts: fastest
    },
}
PERIOD_IDX = {"ya": 0, "ty": 1}

def seg_block(seg):
    pop = SEG_SHARE[seg] * UNIVERSE
    out = {}
    for period in ("ya", "ty"):
        pi = PERIOD_IDX[period]
        att, reach, viewers = {}, {}, {}
        for p in PLATFORMS:
            k = p["key"]
            pen = SEG[seg][k]["pen"][pi]
            mn = SEG[seg][k]["mn"][pi]
            v = pen * pop
            reach[k] = pen
            viewers[k] = v
            att[k] = mn * (v / 1e6)            # attention minutes (millions)
        tot = sum(att.values())
        som = {k: att[k] / tot for k in att}
        out[period] = dict(reach=reach, som=som, viewers=viewers, attention=att)
    return out

seg_data = {s: seg_block(s) for s in SEG_SHARE}

# "all" = population-weighted aggregate of the two segments (single source of truth
# for the consumption view's combined number).
def seg_all():
    out = {}
    for period in ("ya", "ty"):
        att, reach_num = {}, {}
        totpop = sum(SEG_SHARE.values()) * UNIVERSE
        for p in PLATFORMS:
            k = p["key"]
            a = sum(seg_data[s][period]["attention"][k] for s in SEG_SHARE)
            reached = sum(seg_data[s][period]["reach"][k] * SEG_SHARE[s] * UNIVERSE
                          for s in SEG_SHARE)
            att[k] = a
            reach_num[k] = reached / totpop
        tot = sum(att.values())
        som = {k: att[k] / tot for k in att}
        out[period] = dict(reach=reach_num, som=som)
    return out

segments_bundle = dict(shares=SEG_SHARE,
                       affluent={pr: dict(reach=seg_data["affluent"][pr]["reach"],
                                          som=seg_data["affluent"][pr]["som"])
                                 for pr in ("ya", "ty")},
                       mass={pr: dict(reach=seg_data["mass"][pr]["reach"],
                                      som=seg_data["mass"][pr]["som"])
                             for pr in ("ya", "ty")},
                       all=seg_all())
bundle["segments"] = segments_bundle

# segment_consumption.csv for inspection
with open(os.path.join(DATA, "segment_consumption.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["segment", "platform", "group", "period",
                "reach_within_segment_pct", "share_of_mind_pct"])
    for seg in ("affluent", "mass"):
        for period, label in (("ya", "Year ago"), ("ty", "This year")):
            for p in PLATFORMS:
                k = p["key"]
                w.writerow([seg.title(), p["name"], p["group"], label,
                            round(seg_data[seg][period]["reach"][k] * 100, 1),
                            round(seg_data[seg][period]["som"][k] * 100, 1)])

with open(os.path.join(ROOT, "data.json"), "w") as f:
    json.dump(bundle, f, indent=2)

# ----------------------------------------------------------------------------
# Console summary (sanity check)
# ----------------------------------------------------------------------------
def pct(x): return f"{x*100:5.1f}%"

print("=== Synthetic Media R&F dataset built ===")
print(f"Universe: {UNIVERSE:,}  Baseline budget: {CURRENCY} {BUDGET:,}  EffFreq: {EFFECTIVE_FREQ}+\n")
print("Share of Mind (minutes x viewers, normalised):")
for p in PLATFORMS:
    k = p["key"]
    print(f"  {p['name']:9s} {p['group']:11s} "
          f"YA {pct(SOM_YA[k])} -> TY {pct(SOM_TY[k])}  "
          f"({(SOM_TY[k]-SOM_YA[k])*100:+.1f} ppt)")

print("\nPer-platform reach: baseline -> recommended  (population reach, then in-platform)")
print(f"  {'platform':9s} {'spend%':>7s} {'base pop':>9s} {'rec pop':>8s} {'Δppt':>6s} "
      f"{'base in':>8s} {'rec in':>8s}")
rec_tot = sum(recommended_spend.values())
for p in PLATFORMS:
    k = p["key"]
    bp = base_out["per"][k]["r1"]; rp = rec_out["per"][k]["r1"]
    bi = bp / p["cover_max"]; ri = rp / p["cover_max"]
    print(f"  {p['name']:9s} {recommended_spend[k]/rec_tot*100:6.1f}% "
          f"{pct(bp):>9s} {pct(rp):>8s} {(rp-bp)*100:+6.1f} {pct(bi):>8s} {pct(ri):>8s}")

print("\nScenario comparison:")
for label, out in [("TV-skewed baseline", base_out), ("Recommended plan", rec_out)]:
    print(f"  {label:22s} spend {CURRENCY} {out['total_spend']/1e6:5.1f}M  "
          f"CMR1 {pct(out['cmr1'])}  CMR3 {pct(out['cmr3'])}  "
          f"AwIdx {out['awareness_index']:5.1f}  "
          f"vsYA {growth_vs_ya(out):+5.1f}%  "
          f"vsDoNothing {growth_vs_donothing(out):+5.1f}%")
print(f"\n  Recommended digital spend rank: "
      + " > ".join(sorted(['meta','yt','tt'],
                          key=lambda k: -recommended_spend[k])))

print("\nAudience segments (digital reach within segment, YA -> TY):")
print(f"  {'platform':9s} {'AFFLUENT':>18s} {'MASS':>18s}")
for p in PLATFORMS:
    if p["group"] != "digital":
        continue
    k = p["key"]
    a_ya = seg_data["affluent"]["ya"]["reach"][k]; a_ty = seg_data["affluent"]["ty"]["reach"][k]
    m_ya = seg_data["mass"]["ya"]["reach"][k];     m_ty = seg_data["mass"]["ty"]["reach"][k]
    print(f"  {p['name']:9s} "
          f"{a_ya*100:5.1f}->{a_ty*100:5.1f} ({(a_ty-a_ya)*100:+4.1f}) "
          f"{m_ya*100:7.1f}->{m_ty*100:5.1f} ({(m_ty-m_ya)*100:+4.1f})")
print("  invariant check: affluent digital LEVEL higher, mass digital GROWTH faster")
print("  affluent digital SoM TY:",
      {p['name']: round(seg_data['affluent']['ty']['som'][p['key']]*100,1)
       for p in PLATFORMS if p['group']=='digital'})
print("  mass digital SoM TY:    ",
      {p['name']: round(seg_data['mass']['ty']['som'][p['key']]*100,1)
       for p in PLATFORMS if p['group']=='digital'})
print("  'all' SoM TY (vs locked total):",
      {p['name']: round(segments_bundle['all']['ty']['som'][p['key']]*100,1) for p in PLATFORMS})
print("\nFiles written to:", DATA)
