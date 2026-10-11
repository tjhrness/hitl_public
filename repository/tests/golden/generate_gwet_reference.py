"""Run with .reference/Scripts/python.exe (irrCAC 0.4.4), not application Python."""

import json
from pathlib import Path

import pandas as pd
from irrCAC.raw import CAC

cases = [
    [[0, 0], [1, 1], [0, 1], [1, 0]],
    [[0, 0, 1], [1, 1, 2], [2, 2, 2], [0, 1, 2]],
    [[0, 0, 0], [1, 1, 1], [2, 2, 2]],
    [[0, 0, 0]] * 20 + [[0, 0, 1]],
]
fixtures = []
for rows in cases:
    for weighting in ("identity", "quadratic"):
        result = CAC(pd.DataFrame(rows), weights=weighting, digits=12).gwet()
        fixtures.append(
            {"rows": rows, "weighting": weighting, "estimate": result["est"]["coefficient_value"]}
        )
Path(__file__).with_name("gwet_reference.json").write_text(
    json.dumps(
        {
            "source": "irrCAC 0.4.4, Python 3.12.14, scipy 1.12.0; digits=12",
            "cases": fixtures,
        },
        indent=2,
    ),
    encoding="utf-8",
)
