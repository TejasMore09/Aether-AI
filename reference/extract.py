"""Turn the reference workbook into something reviewable.

    python reference/extract.py

An .xls is a binary blob. Committed as-is, nobody can see what changed when
next January's edition lands — a band could move thirty days and the diff
would say "51200 bytes differ". The CSV this produces is the artefact of
record: it is what the code reads, what a person reviews, and what a test
validates the sector crosswalk against.

The workbook stays in the repository as the receipt. This script is how the
two are kept honest with each other, and it is re-runnable rather than a
one-off someone has to reconstruct.

Requires xlrd (`pip install xlrd`), which is deliberately not a runtime
dependency: the platform reads the CSV, never the workbook.
"""

import csv
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
SOURCE = HERE / "damodaran-working-capital-2026-01.xls"
TARGET = SOURCE.with_suffix(".csv")

# Columns, in the workbook's own order. Implied DSO/DIO/DPO are derived here
# rather than at read time so the arithmetic is visible in the file a person
# reviews, not buried in code they have to go and find.
HEADER = [
    "industry",
    "firms",
    "ar_over_sales",
    "inventory_over_sales",
    "ap_over_sales",
    "noncash_wc_over_sales",
    "implied_dso_days",
    "implied_dio_days",
    "implied_dpo_days",
]


def main() -> int:
    try:
        import xlrd
    except ImportError:
        print("xlrd is required to re-extract. pip install xlrd", file=sys.stderr)
        return 1

    if not SOURCE.exists():
        print(f"missing {SOURCE}", file=sys.stderr)
        return 1

    book = xlrd.open_workbook(str(SOURCE))
    sheet = book.sheet_by_name("Industry Averages")
    updated = xlrd.xldate_as_datetime(sheet.cell_value(0, 1), book.datemode).date()

    rows = []
    for r in range(8, sheet.nrows):
        name = str(sheet.cell_value(r, 0)).strip()
        if not name or name.lower().startswith("total"):
            continue
        # Per column, not per row. A few industries have a blank in one ratio
        # and real figures in the others; dropping the whole row for that would
        # silently remove an industry the sector crosswalk references, and the
        # only symptom would be a band that never seeds.
        def number(column: int) -> float | None:
            try:
                return float(sheet.cell_value(r, column))
            except (ValueError, TypeError):
                return None

        firms = number(1)
        ar, inv, ap, wc = (number(c) for c in range(2, 6))
        if firms is None or all(v is None for v in (ar, inv, ap, wc)):
            continue

        def ratio(v: float | None) -> str:
            return "" if v is None else f"{v:.6f}"

        def days(v: float | None) -> str:
            return "" if v is None else f"{v * 365:.1f}"

        rows.append(
            [
                name,
                int(firms),
                ratio(ar),
                ratio(inv),
                ratio(ap),
                ratio(wc),
                days(ar),
                days(inv),
                days(ap),
            ]
        )

    with TARGET.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([f"# Aswath Damodaran, NYU Stern. Data updated {updated}. US companies."])
        writer.writerow([f"# Extracted from {SOURCE.name} by reference/extract.py. Do not hand-edit."])
        writer.writerow(HEADER)
        writer.writerows(sorted(rows))

    print(f"wrote {TARGET.name}: {len(rows)} industries, data as of {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
