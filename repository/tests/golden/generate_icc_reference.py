"""Generate independent ICC(A,k)/ICC(C,k) reference fixtures with pingouin 0.7.0."""

import json
from pathlib import Path

import pandas as pd
import pingouin as pg

cases = [
    [[1, 2, 1], [2, 3, 3], [4, 4, 5], [5, 7, 6], [8, 8, 9]],
    [[1, 4], [2, 5], [4, 7], [7, 10]],
    [[1, 1], [2, 2], [3, 3], [4, 4]],
    [[1, 7, 4], [7, 2, 1], [3, 6, 8], [6, 1, 3], [2, 9, 5]],
]
fixtures = []
for rows in cases:
    table = pd.DataFrame(
        [(i, j, value) for i, row in enumerate(rows) for j, value in enumerate(row)],
        columns=["item", "rater", "rating"],
    )
    result = pg.intraclass_corr(data=table, targets="item", raters="rater", ratings="rating")
    values = dict(zip(result["Type"], result["ICC"], strict=True))
    fixtures.append(
        {"rows": rows, "absolute": values["ICC(A,k)"], "consistency": values["ICC(C,k)"]}
    )
Path(__file__).with_name("icc_reference.json").write_text(
    json.dumps(
        {
            "source": f"pingouin {pg.__version__}; balanced complete data; ICC(A,k)/ICC(C,k)",
            "cases": fixtures,
        },
        indent=2,
    ),
    encoding="utf-8",
)
