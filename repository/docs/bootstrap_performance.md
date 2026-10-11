# Deterministic bootstrap implementation 1.1

Execution uses up to four spawned worker processes, one job per criterion. Jobs
return in worksheet order. Each result keeps the existing SHA-256 child seed based
on input/configuration, criterion, metric, and rater pair; scheduling does not affect
draws. Qt dispatches orchestration in a background task and receives stage messages.

Bootstrap still draws 10,000 complete Item ID rows with replacement. Categorical
ratings are coded once per prepared statistic. Pair differences, category counts,
coincidences and continuous moments are sufficient statistics. Batches represent
the very same row indices as multiplicities before matrix reduction, avoiding
large sample tensors. Leave-one-out moments use total-minus-row reductions.
CCC and ICC share a constant centering offset to reduce moment cancellation.

BCa bias correction gives numerical ties half weight, using relative tolerance
1e-12 and absolute tolerance 1e-14. This prevents mathematically equal values from
changing the discrete bias count due to floating-point summation order. Degenerate
jackknives/resamples still fail. New BCa results record implementation version 1.1;
previously persisted results and reports remain untouched.

Regression tests compare all metric estimates and leave-one-out values with the
original reference implementations, compare intervals across batch sizes, and
retain the independent statistical fixture suite and SciPy BCa comparison.

Run `python scripts/benchmark.py` outside other heavy workloads. It generates a
10-criterion workbook with 1,000 items and 10 raters, mixed binary/nominal/ordinal/
continuous types, and all recommended metrics. Timing covers Execute, including
managed workbook reload, validation, preflight, calculation and persistence. It
excludes initial workbook creation/upload and report rendering. The script writes
`runtime-data/benchmark.json` and exits nonzero above 60 seconds. Neither resample
count nor selected metrics are reduced to obtain a passing result.
