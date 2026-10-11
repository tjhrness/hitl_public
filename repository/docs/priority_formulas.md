# Review priority formulas, version 1

These deterministic workflow scores are not probabilities or statistical significance.
The user authorized specifying the previously undefined formulas. All calculations use
included items only. Raw signals below are proportions; normalized signals are 100 times
the raw value, clamped to [0,100]. Inapplicable means null, never zero.

Let K be the worksheet category domain size, ordinal ranks run from 0 to K-1,
and R be the included worksheet continuous maximum minus minimum.

| Signal | Binary / nominal | Ordinal | Continuous |
| --- | --- | --- | --- |
| Pairwise disagreement | Fraction of unordered pairs with unequal labels | Mean absolute pair rank difference / (K-1) | Fraction of pairs whose absolute difference strictly exceeds tolerance |
| Inverse consensus | 1 minus largest category share | Same | Inapplicable |
| Spread | Shannon entropy divided by log(K) | Item rank range / (K-1) | Item range / R |
| Deviation | Inapplicable | Mean absolute rank distance from unique mode, or median rank on a tie, divided by (K-1) | Mean absolute distance from item median / R |
| Outlier | 1 if any item outlier, else 0 | Same | Same |
| No consensus | 1 if tied modes, else 0 | Same | Inapplicable |

Zero-range denominators return zero. Entropy uses the worksheet domain, so an item
using two of three available categories is less dispersed than one using all three equally.
Outlier rules remain those in PROJECT_CONTEXT.md; two-rater panels cannot have outliers.

Worked examples (normalized percentages):

- Binary [a,b] with domain {a,b}: disagreement 100, inverse consensus 50,
  entropy 100, deviation inapplicable, outlier 0, no consensus 100.
- Ordinal [low,middle,high] in a three-category domain: pair distances 1,2,1
  give disagreement 66.6667; inverse consensus 66.6667; spread 100;
  median-centered deviation 33.3333; outlier 0; no consensus 100.
- Continuous [0,1,2], worksheet range 2 and tolerance 1: only the (0,2) pair
  exceeds tolerance, giving disagreement 33.3333; spread 100; deviation 33.3333.
  Inverse consensus and no consensus are inapplicable; outlier is 0.
- A constant worksheet produces zero for every applicable signal.

Rater diagnostics use the same pair disagreement definition averaged over each rater's
item-peer pairs. Agreement is exact equality for categorical ratings and within-tolerance
for continuous ratings. Ordered direction is the mean signed deviation from the item
panel median in rank steps or original units; it describes observed scoring, not intent.
Variance is population variance across that rater's included items; spread is their range.
