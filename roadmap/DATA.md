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

**Available now, free, and good enough to start:**

[Damodaran's working-capital dataset](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/wcdata.html)
(NYU Stern, data as of January 2026, 142 industries, US firms) publishes
`Acc Rec/Sales` per industry. That converts directly:

    DSO = 365 x (Acc Rec / Sales)

So the receivables pack's healthy band can be seeded per sector from a real,
citable, annually-updated source instead of from judgement. The same file
carries `Inventory/Sales` and `Acc Pay/Sales`, which are the inventory and
payables packs in Phase 5. The Excel is at
`pages.stern.nyu.edu/~adamodar/pc/datasets/wcdata.xls`.

**The limitation, which must be labelled and not buried:** these are US
*public* companies. An SME's DSO is not a listed company's DSO — small firms
usually have worse collection terms and less leverage over customers. What
transfers is the *ordering* across sectors (software near zero, building
supplies high), not the levels. Phase 3.6 exists precisely so a band can say
"seeded from US public-company data, not SME data" on the screen where a
customer reads it.

**Better but not free:**
- **RMA Annual Statement Studies** — the actual SME benchmark, built from bank
  loan files. This is what a lender uses. Expensive; frequently available
  through a university library.
- **CMIE Prowess** (India) — firm-level financials including unlisted
  companies. Paid; standard at Indian universities.

**Free, coarser, real SME data:**
- [Eurostat Structural Business Statistics](https://ec.europa.eu/eurostat/web/structural-business-statistics/database)
  — several hundred NACE activities, broken down by enterprise size class, so
  genuinely about SMEs rather than large firms. Turnover and employment
  rather than working-capital ratios.
- MCA21 (India) — company filings are public per document.

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
