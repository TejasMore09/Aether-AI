# Reference data

Third-party data the system will be seeded from. Kept in the repository, not
merely linked, because a link rots and a laptop gets formatted — and because
a band nobody can trace back to a file is indistinguishable from a guess.

Nothing here is loaded at runtime yet. See `roadmap/DATA.md` for what each
file is for and what it cannot answer.

---

## `damodaran-working-capital-2026-01.xls`

**Source:** [Working Capital Ratios by Sector (US)](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/wcdata.html),
Aswath Damodaran, NYU Stern. Free to use, updated annually.

**Provenance verified:** the file's own metadata names Aswath Damodaran as
author, and its `Date updated` cell reads **2026-01-05**. The sheet declares
its scope as *US companies*.

**Contents:** sheet `Industry Averages`, 94 usable industries, each with
number of firms, `Acc Rec/ Sales`, `Inventory/Sales`, `Acc Pay/ Sales`,
`Non-cash WC/ Sales`.

**What it gives us:** per-sector healthy bands for receivables in Phase 3, and
for inventory and payables in Phase 5.

    DSO = 365 x (Acc Rec / Sales)

**The conversion was checked, not assumed.** Across the 94 industries the
implied DSO has a median of 46.8 days, with the 10th and 90th percentiles at
14.6 and 87.4. Sectors an SME plausibly occupies come out sensibly:

| Industry | Implied DSO |
|---|---|
| Retail (Grocery and Food) | 6.4 days |
| Restaurant/Dining | 19.4 days |
| Trucking | 45.3 days |
| Building Materials | 50.3 days |
| Construction Supplies | 54.1 days |
| Software (System & Application) | 61.5 days |
| Business & Consumer Services | 67.3 days |

### Two limits that must reach the screen, not just this file

**It is US public companies.** An SME's DSO is not a listed company's DSO —
small firms usually have worse terms and less leverage over their customers.
What transfers is the *ordering* across sectors, not the levels. Phase 3.6
exists so a band can say where it came from.

**The conversion is invalid for financial sectors and must refuse them rather
than map them.** Where reported revenue is not comparable to the receivable,
the arithmetic produces nonsense:

| Industry | "Implied DSO" |
|---|---|
| Banks (Regional) | 0.0 days |
| R.E.I.T. | 484.6 days |
| Brokerage & Investment Banking | 511.5 days |
| Financial Svcs. (Non-bank & Insurance) | 4862.6 days |

Advertising (172.9 days) is the subtler case: agencies report commission
revenue while carrying gross client billings as receivables.

This matters directly for the vision's own example — a stock brokerage is
precisely the sector where this dataset cannot supply a band. Phase 3 must
exclude these industries explicitly and fall back to the pack default, rather
than seeding a number that is four thousand days wrong.
