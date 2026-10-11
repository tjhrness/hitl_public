# Statistical implementation decisions

All point estimates use included item rows with complete fixed rater panels.

## Agreement and Cohen kappa

Raw agreement is the percentage of exact matches across every item and unordered
rater pair. Confusion matrices place the first alias in rows and the second in
columns. Categories follow deterministic normalized order.

Cohen kappa is `1 - observed_disagreement / expected_disagreement`. Expected
disagreement uses independent empirical rater marginals. Unweighted distance is
the unequal-category indicator. Ordinal linear and quadratic distances are the
absolute rank difference and its square. Rescaling all distances cancels in the
ratio. Zero expected disagreement is explicitly noncomputable.

Tests compare all three forms against independently maintained statsmodels,
alongside hand calculations and rater-swap invariance. Reference:
[statsmodels Cohen kappa](https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.cohens_kappa.html).

Fleiss kappa uses the complete fixed-panel formulation, pooled category proportions,
and observed agreement averaged across all item/pair observations. Reference tests
use statsmodels `fleiss_kappa`, including perfect and strongly imbalanced panels.

## Krippendorff alpha

Alpha uses complete-data coincidence disagreement and without-replacement expected
disagreement. Nominal distance is 0/1. Ordinal distance is the squared pooled
frequency between ordered categories, counting half each endpoint. It is not
interval distance. Tests compare both levels to the independent `krippendorff`
package with explicit value-domain order and row-order invariance.
[Reference implementation](https://github.com/pln-fing-udelar/fast-krippendorff).

## Gwet AC1/AC2

AC1 uses identity agreement weights. AC2 uses quadratic agreement weights
`w(a,b)=1-((rank(a)-rank(b))/(q-1))²` over user-confirmed ordinal order.
`Pa` is the mean agreement weight across item/pair observations;
`Pe = sum(w) * sum(p*(1-p)) / (q*(q-1))`; `AC=(Pa-Pe)/(1-Pe)`.
The observed category domain must contain at least two categories. A one-category
domain is blocked explicitly rather than introducing an artificial epsilon.

Eight golden fixtures come from independent irrCAC 0.4.4. It requires older SciPy,
so the generator runs in a separate Python 3.12 environment. Its generated JSON
is consumed by the Python 3.14 tests without a runtime irrCAC dependency.
Reproduce with `tests/golden/generate_gwet_reference.py`; the JSON records provenance.
[Reference documentation](https://irrcac.readthedocs.io/en/latest/usage/usage_raw_data.html).

## Continuous agreement and Lin CCC

Practical agreement uses `abs(a-b) <= tolerance`. Panel MAE/RMSE are arithmetic
means of their pairwise estimates. Lin CCC uses population central moments
(divisor n), with no multi-rater average labeled as CCC. Either rater having zero
variance is a blocking computability condition.

Independent hand fixtures: x=(1,2,3), y=x yields 1; y=x+1 yields 4/7; y=2x yields
4/11; y=(3,2,1) yields -1. Swapping raters leaves each result unchanged.
[Lin's original paper](https://pubmed.ncbi.nlm.nih.gov/2720055/).

## ICC

Balanced two-way ANOVA yields item, rater, and residual mean squares.
Only average-measures forms are exposed: ICC(A,k) absolute agreement and ICC(C,k)
consistency, interpreted under random comparable raters. Their formulas are
`(MS_items-MS_error)/(MS_items+(MS_raters-MS_error)/n)` and
`(MS_items-MS_error)/MS_items`, respectively. Estimated variance components are
stored, including negative estimates; they are not silently truncated.

Independent pingouin 0.7.0 fixtures compare ICC(A,k) and ICC(C,k) directly. Fixtures
cover systematic bias, perfect agreement, low agreement, and multiple panel sizes.
Generator and source version accompany the fixtures. Reference-library warnings
for zero residual variance concern its inference calculations; only finite point
estimates are used by these point-estimate fixtures.

## BCa uncertainty

The bootstrap resamples whole item rows with replacement, default B=10,000.
The master seed is 1729. Child seeds are the first 64 SHA-256 bits of UTF-8 JSON
`[master_seed, version, criterion, metric, pair]`, in big-endian order.
BCa uses midrank bias correction (half ties), leave-one-item-out jackknife
acceleration, and linear empirical quantiles. Batching changes memory use but not
the random stream. Nonfinite resamples or degenerate adjustments fail explicitly;
there is no percentile fallback. Reference tests compare the complete interval
against SciPy BCa using the same generated sample stream.

Pairwise exact-agreement proportions use Wilson score intervals over independent
item indicators. Overall exact agreement uses Wilson only for two raters; larger
panels use whole-row BCa to preserve dependence among pairs. Other scalar outputs
use BCa, including Bland–Altman mean bias; limits of agreement remain separate.
Known noncomputable jackknife/CI cases block in preflight. Unforeseen invalid
bootstrap draws abort the requested result rather than being dropped or replaced.

## Significance

Only the validated two-sided asymptotic unweighted Cohen kappa=0 test is enabled.
Its null variance uses independent empirical marginals and matches statsmodels.
Nonpositive null variance omits significance with an explicit caveat. Holm step-down
adjustment groups pairs within each criterion × metric/test family. Raw probabilities
are transient internal values and never become public/persisted result fields.
