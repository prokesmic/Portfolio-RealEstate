# Portfolio House

Light-mode real-estate net-worth dashboard for a personal property portfolio.

The app now focuses on three things:

- estimating each property's market value once a day from Prague Sreality comparables
- comparing that value against mortgage balances to show real-estate equity
- blending in editable cashflow, cash, and other debt assumptions directly in the browser

## What It Does

- Builds a daily snapshot into `dashboard/data/portfolio_snapshot.json`
- Keeps a rolling history so the UI can chart equity over time
- Lets you refresh the snapshot manually through `/api/refresh-portfolio`
- Stores cash, other debts, rents, insurance, taxes, and mortgage payments locally in the browser

## Main Files

- `data/portfolio_seed.json`: seeded property facts and manual anchors
- `scripts/build_portfolio_snapshot.py`: live valuation snapshot builder
- `api/refresh-portfolio.py`: on-demand refresh endpoint
- `dashboard/index.html`: portfolio experience shell
- `dashboard/app.js`: rendering and local financial assumptions
- `dashboard/styles.css`: premium light-mode visual system
- `.github/workflows/refresh-portfolio-snapshot.yml`: daily automation

## Refresh The Snapshot

Local:

```bash
python3 scripts/build_portfolio_snapshot.py
```

API:

```bash
curl -X POST http://localhost:8000/api/refresh-portfolio
```

GitHub:

1. Open `Actions`
2. Select `Refresh Portfolio Snapshot`
3. Click `Run workflow`

The scheduled workflow runs daily at `06:15 UTC` and writes the refreshed snapshot back into the repo when values changed.

## Notes

- Market estimation currently uses Prague comparables from the Sreality API plus your manual estimate range as a stabilizing anchor when confidence is lower.
- Cashflow remains editable in the UI because mortgage payment, tax, insurance, and rent assumptions are still being collected.
- The app is ready for more properties and more debt categories as you add them.
