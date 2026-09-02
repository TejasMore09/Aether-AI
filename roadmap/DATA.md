# Where the data comes from

The largest risk in this project, and the one that cannot be closed by
writing code. Every band, every relation and every economic constant in the
system today is a considered guess. This file is the plan for replacing them,
written down because it is the question a fresh session is least able to
answer for itself.

There are four different data problems here and they have four different
answers. Conflating them is how "we need real data" stays vague for months.

---

## 1. Sector bands — what "normal" looks like in an industry

**Needed for:** Phase 3. Right now a stock brokerage and a bakery get
byte-identical packs.

**In hand, verified, ready to use.** Damodaran's working-capital dataset is
committed at `reference/damodaran-working-capital-2026-01.xls` — see
`reference/README.md` for the provenance check and the numbers. 94 industries,
dated 2026-01-05, US companies, and `DSO = 365 x (Acc Rec / Sales)` was
checked against sectors an SME actually occupies rather than assumed: grocery
retail 6.4 days, restaurants 19.4, trucking 45.3, building materials 50.3,
software 61.5. Median across all 94 is 46.8 days. Those are defensible
starting bands. The same file carries `Inventory/Sales` and `Acc Pay/Sales`
for Phase 5.

**Two limits, and the second is a hard requirement on Phase 3.**

These are US *public* companies. An SME's DSO is not a listed company's DSO —
small firms have worse terms and less leverage over customers. What transfers
is the *ordering* across sectors, not the levels. Phase 3.6 exists precisely
so a band can say "seeded from US public-company data, not SME data" on the
screen where a customer reads it.

And the conversion is **invalid for financial sectors**, where reported
revenue is not comparable to the receivable: banks come out at 0 days, REITs
at 485, brokerage at 512, non-bank financial services at 4863. Phase 3 must
refuse these industries and fall back to the pack default rather than seed
them. Note where that bites — a stock brokerage is the vision's own example of
a sector-aware agent, and it is exactly the sector this dataset cannot supply.

**Better but not free:**
- **RMA Annual Statement Studies** — the actual SME benchmark, built from bank
  loan files. This is what a lender uses. Expensive; frequently available
  through a university library.
- **CMIE Prowess** (India) — firm-level financials including unlisted
  companies. Paid; standard at Indian universities.

**Free, coarser, real SME data:**
- [Eurostat Structural Business Statistics](https://ec.europa.eu/eurostat/web/structural-business-statistics/database)
  — `sbs_ovw_act` (enterprises by detailed NACE Rev. 2 activity),
  `sbs_sc_ovw` (by size class) and `sbs_ovw_iep` (investment, expenditure,
  purchases). Genuinely SME-scale, because the size-class breakdown is the
  point of it. **But it carries no working-capital ratios**, so it does not
  compete with Damodaran for bands.

  Its real value here is **NACE Rev. 2 as the sector taxonomy for 3.1** — a
  standard, hierarchical, internationally recognised classification, which
  beats inventing one. India's NIC and the US SIC/NAICS are the same tree with
  different labels, and SEC filings are keyed on SIC, so a mapping between
  them is work Phase 3 has to do anyway. Damodaran's 94 industry names are
  ad hoc and will need mapping to whichever taxonomy is chosen.

**Not useful, checked so nobody checks again:** the MCA "Annual Reports on
Working & Administration of the Companies Act" are statistics about company
*registrations and compliance* — how many companies incorporated, struck off,
prosecuted. They contain no financial ratios. What is useful at MCA is a
different thing: individual company balance sheets via MCA21, which are
per-document and paid, and require knowing which companies to ask for.

---

## 2. Time series — do the cross-domain relations actually hold?

**Needed for:** validating `relations.yaml`, and all of Phase 4.

This is a different problem from bands. A distribution across firms tells you
nothing about whether stretching DSO *precedes* runway compression in the same
business. That needs the same firm measured repeatedly.

**Available now, free:**
[SEC Financial Statement Data Sets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)
— every XBRL-tagged US filing since 2009, published as quarterly flat files,
including SIC industry code. Thousands of firms, dozens of quarters each,
covering receivables, cash, revenue and payables together.

That is enough to test the actual claims in `relations.yaml` against reality:
does receivables deterioration lead cash deterioration, in the same company,
with the lag we assert? The answer may be no. Finding that out is worth more
than any feature.

**Its two honest limits:** quarterly, not weekly, so short lags are invisible;
and public companies, so the levels are wrong even where the mechanism is
right. It validates *direction and mechanism*, not thresholds.

---

## 3. Real SME operating data

**Needed for:** everything that actually matters. Calibration, the quality
gate, whether findings are useful rather than merely correct.

**No dataset exists. This cannot be bought or scraped.** It comes from real
businesses agreeing to share, and that is a conversation, not an engineering
task. The routes, in order of how well they usually work:

1. **An accountant or CA firm.** One accountant serving forty SMEs is the
   highest-leverage single contact available — they hold the data, they
   already know which clients have cash problems, and they can judge whether a
   finding is useful better than any test can.
2. **Design partners.** Three to five businesses, read-only access, free use
   in exchange. The standard route, and the one that also answers "is this
   worth paying for".
3. **Tejas's own network.** Family and friends' businesses. Small sample,
   trivially available, and better than zero.

**Until then:** Xero and QuickBooks both provide demo companies with
realistically shaped seeded data. Not real, but real enough to build and test
connectors against in Phase 7 without waiting for anybody.

---

## 4. Outcomes — did acting actually help?

**Needed for:** Phase 9.2 and 9.4, and therefore for Mega to be trustworthy at
all.

**This one has no shortcut of any kind.** It requires decisions to be made,
months to pass, and results to be observed. It cannot be sourced, purchased or
simulated, and no amount of engineering compresses it. It is the reason the
honest estimate for the full product is measured in years rather than months,
and the reason Phase 9 sits where it does.

---

## What this means for sequencing

Items 1 and 2 are solvable now, alone, for free. Item 3 is not solvable by
writing code at all. Item 4 is bounded by the calendar.

So the phases that will stall are exactly the ones that need item 3, and the
fix is not more code. That is worth re-reading before deciding that a slow
phase means something is wrong with the implementation.
