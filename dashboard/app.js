const STORAGE_KEY = "portfolio-house-local-model-v1";
const LOCALE = "cs-CZ";
const CURRENCY = "CZK";

const state = {
  snapshot: null,
  model: null,
  refreshing: false,
};

const elements = {
  lastUpdatedPill: document.getElementById("lastUpdatedPill"),
  propertyCountPill: document.getElementById("propertyCountPill"),
  refreshTimePill: document.getElementById("refreshTimePill"),
  heroNetWorth: document.getElementById("heroNetWorth"),
  heroNarrative: document.getElementById("heroNarrative"),
  heroValue: document.getElementById("heroValue"),
  heroValueDelta: document.getElementById("heroValueDelta"),
  heroDebt: document.getElementById("heroDebt"),
  heroDebtMeta: document.getElementById("heroDebtMeta"),
  showcaseBackdrop: document.getElementById("showcaseBackdrop"),
  showcaseTitle: document.getElementById("showcaseTitle"),
  showcaseText: document.getElementById("showcaseText"),
  showcaseStats: document.getElementById("showcaseStats"),
  showcaseStrip: document.getElementById("showcaseStrip"),
  metricsGrid: document.getElementById("metricsGrid"),
  equityChart: document.getElementById("equityChart"),
  historyMeta: document.getElementById("historyMeta"),
  pulseHeadline: document.getElementById("pulseHeadline"),
  pulseLines: document.getElementById("pulseLines"),
  assumptionsForm: document.getElementById("assumptionsForm"),
  cashflowStatus: document.getElementById("cashflowStatus"),
  cashflowBreakdown: document.getElementById("cashflowBreakdown"),
  missingDataList: document.getElementById("missingDataList"),
  propertyGrid: document.getElementById("propertyGrid"),
  refreshButton: document.getElementById("refreshButton"),
  scrollToSetup: document.getElementById("scrollToSetup"),
};

const isFileProtocol = window.location.protocol === "file:";
const snapshotPath = isFileProtocol ? "./data/portfolio_snapshot.json" : "/data/portfolio_snapshot.json";
const refreshPath = "/api/refresh-portfolio";

const formatCurrency = (value) =>
  new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency: CURRENCY,
    maximumFractionDigits: 0,
  }).format(Number(value || 0));

const formatCompactCurrency = (value) =>
  new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency: CURRENCY,
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(Number(value || 0));

const formatPercent = (value) =>
  value === null || value === undefined ? "-" : `${Number(value).toFixed(1)} %`;

const formatDateTime = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  return new Intl.DateTimeFormat(LOCALE, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};

const formatNumber = (value) =>
  new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 }).format(Number(value || 0));

const cssImage = (url) => (url ? `url("${String(url).replace(/"/g, '\\"')}")` : "linear-gradient(135deg, #d7d4ce, #e9ddcb)");

const bestImage = (property) =>
  property.comparables?.find((item) => item.image_url)?.image_url || "";

const createDefaultModel = (snapshot) => ({
  cash_czk: Number(snapshot.cash_czk || 0),
  pension_czk: Number(snapshot.pension_czk || 0),
  other_debts_czk: 0,
  daily_review_time: snapshot.recommended_refresh_time || "08:15",
  properties: Object.fromEntries(
    snapshot.properties.map((property) => [
      property.id,
      {
        usage: property.use || "unknown",
        monthly_rent_czk: 0,
        monthly_mortgage_payment_czk: 0,
        monthly_operating_cost_czk: 0,
        annual_property_tax_czk: 0,
        annual_insurance_czk: 0,
      },
    ]),
  ),
});

const loadModel = (snapshot) => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    const defaults = createDefaultModel(snapshot);
    return {
      ...defaults,
      ...parsed,
      properties: Object.fromEntries(
        snapshot.properties.map((property) => [
          property.id,
          {
            ...defaults.properties[property.id],
            ...(parsed.properties?.[property.id] || {}),
          },
        ]),
      ),
    };
  } catch {
    return createDefaultModel(snapshot);
  }
};

const saveModel = () => {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state.model));
};

const computeViewModel = () => {
  const snapshot = state.snapshot;
  const model = state.model;
  const properties = snapshot.properties.map((property) => {
    const assumptions = model.properties[property.id];
    const monthlyTax = Number(assumptions.annual_property_tax_czk || 0) / 12;
    const monthlyInsurance = Number(assumptions.annual_insurance_czk || 0) / 12;
    const monthlyRent = Number(assumptions.monthly_rent_czk || 0);
    const monthlyMortgage = Number(assumptions.monthly_mortgage_payment_czk || 0);
    const monthlyOperating = Number(assumptions.monthly_operating_cost_czk || 0);
    const monthlyOutflow = monthlyMortgage + monthlyOperating + monthlyTax + monthlyInsurance;
    const monthlyCashflow = monthlyRent - monthlyOutflow;

    const dynamicMissing = [];
    if (!monthlyMortgage) dynamicMissing.push("monthly mortgage payment");
    if (!monthlyOperating) dynamicMissing.push("monthly operating costs");
    if (!assumptions.annual_insurance_czk) dynamicMissing.push("annual insurance");
    if (!assumptions.annual_property_tax_czk) dynamicMissing.push("annual property tax");
    if (assumptions.usage === "rental" && !monthlyRent) dynamicMissing.push("monthly rent");
    if (assumptions.usage === "unknown") dynamicMissing.push("usage");

    return {
      ...property,
      assumptions,
      monthlyCashflow,
      monthlyOutflow,
      monthlyRent,
      dynamicMissing,
    };
  });

  const totalEquity = snapshot.totals.real_estate_equity_czk;
  const totalValue = snapshot.totals.estimated_value_czk;
  const totalDebt = snapshot.totals.mortgage_balance_czk;
  const cash = Number(model.cash_czk || 0);
  const otherDebts = Number(model.other_debts_czk || 0);
  const pension = Number(model.pension_czk || 0);
  const portfolioNetWorth = totalEquity + cash + pension - otherDebts;
  const monthlyCashflow = properties.reduce((sum, property) => sum + property.monthlyCashflow, 0);
  const missingInputs = properties.flatMap((property) =>
    property.dynamicMissing.map((field) => `${property.name}: ${field}`),
  );

  return {
    snapshot,
    properties,
    totals: {
      totalEquity,
      totalValue,
      totalDebt,
      cash,
      pension,
      otherDebts,
      portfolioNetWorth,
      monthlyCashflow,
    },
    missingInputs,
  };
};

const renderMetrics = (view) => {
  const previous = view.snapshot.history.at(-2);
  const deltaValue = previous
    ? view.totals.totalValue - Number(previous.estimated_value_czk || 0)
    : null;

  const cards = [
    {
      label: "Real-Estate Equity",
      value: formatCurrency(view.totals.totalEquity),
      text: "Součet dnešní odhadované hodnoty mínus zůstatky hypoték.",
    },
    {
      label: "Hotovost",
      value: formatCurrency(view.totals.cash),
      text: "Editovatelný polštář pro čisté jmění mimo nemovitosti.",
    },
    {
      label: "Penzijko",
      value: formatCurrency(view.totals.pension),
      text: "Další dlouhodobé aktivum mimo real-estate equity.",
    },
    {
      label: "Value Change",
      value: deltaValue === null ? "-" : `${deltaValue >= 0 ? "+" : "-"}${formatCurrency(Math.abs(deltaValue))}`,
      text: "Rozdíl proti předchozímu uloženému snapshotu.",
    },
    {
      label: "Další Dluhy",
      value: formatCurrency(view.totals.otherDebts),
      text: "Postupně můžeš přidávat další osobní nebo investiční závazky.",
    },
  ];

  elements.metricsGrid.innerHTML = cards
    .map(
      (card) => `
        <article class="metric-card">
          <span class="card-label">${card.label}</span>
          <strong>${card.value}</strong>
          <p>${card.text}</p>
        </article>
      `,
    )
    .join("");
};

const renderShowcase = (view) => {
  const [featured, ...others] = [...view.properties].sort(
    (a, b) => b.valuation.estimated_value_czk - a.valuation.estimated_value_czk,
  );

  if (!featured) return;

  elements.showcaseBackdrop.style.backgroundImage = cssImage(bestImage(featured));
  elements.showcaseTitle.textContent = featured.name;
  elements.showcaseText.textContent = `${featured.locality}. Dnešní odhad ${formatCurrency(
    featured.valuation.estimated_value_czk,
  )}, equity ${formatCurrency(featured.finance.equity_czk)} a confidence ${Math.round(
    featured.valuation.confidence_score * 100,
  )} %.`;

  elements.showcaseStats.innerHTML = [
    ["Value", formatCompactCurrency(featured.valuation.estimated_value_czk)],
    ["Equity", formatCompactCurrency(featured.finance.equity_czk)],
    ["LTV", formatPercent(featured.finance.ltv_pct)],
  ]
    .map(
      ([label, value]) => `
        <div class="showcase-chip">
          <span>${label}</span>
          <strong>${value}</strong>
        </div>
      `,
    )
    .join("");

  elements.showcaseStrip.innerHTML = others
    .map(
      (property) => `
        <article class="showcase-mini" style="--card-image:${cssImage(bestImage(property))}">
          <span>${property.label}</span>
          <strong>${property.name}</strong>
          <span>${formatCompactCurrency(property.valuation.estimated_value_czk)}</span>
        </article>
      `,
    )
    .join("");
};

const renderChart = (history) => {
  if (!history.length) {
    elements.equityChart.innerHTML = `<div class="empty">Zatím není k dispozici historie.</div>`;
    return;
  }

  if (history.length === 1) {
    elements.equityChart.innerHTML = `<div class="empty">Historie se začne kreslit po dalším denním snapshotu.</div>`;
    return;
  }

  const values = history.map((item) => Number(item.real_estate_equity_czk || 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(max - min, 1);
  const width = 820;
  const height = 240;

  const path = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / spread) * (height - 16) - 8;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");

  const areaPath = `${path} L ${width} ${height} L 0 ${height} Z`;
  const startDate = history[0]?.date || "";
  const endDate = history.at(-1)?.date || "";

  elements.historyMeta.textContent = `${history.length} uložených dnů`;
  elements.equityChart.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="Equity history chart">
      <defs>
        <linearGradient id="equityFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="rgba(23, 94, 97, 0.35)"></stop>
          <stop offset="100%" stop-color="rgba(23, 94, 97, 0.02)"></stop>
        </linearGradient>
      </defs>
      <path d="${areaPath}" fill="url(#equityFill)"></path>
      <path d="${path}" fill="none" stroke="#175e61" stroke-width="4" stroke-linecap="round"></path>
    </svg>
    <div class="chart-axis">
      <span>${startDate}</span>
      <span>${formatCompactCurrency(min)}</span>
      <span>${formatCompactCurrency(max)}</span>
      <span>${endDate}</span>
    </div>
  `;
};

const renderNarrative = (view) => {
  elements.pulseHeadline.textContent = view.snapshot.narrative.headline;
  elements.pulseLines.innerHTML = view.snapshot.narrative.lines
    .map((line) => `<div class="narrative-item">${line}</div>`)
    .join("");
};

const renderAssumptionsForm = (view) => {
  const globalFields = `
    <section class="form-group">
      <span class="card-label">Global Inputs</span>
      <h3>Cash, other debt and review time</h3>
      <div class="form-grid">
        <label class="field">
          <span>Hotovost celkem</span>
          <input data-scope="global" data-field="cash_czk" type="number" min="0" step="1000" value="${view.totals.cash}" />
        </label>
        <label class="field">
          <span>Penzijko / retirement</span>
          <input data-scope="global" data-field="pension_czk" type="number" min="0" step="1000" value="${view.totals.pension}" />
        </label>
        <label class="field">
          <span>Další dluhy celkem</span>
          <input data-scope="global" data-field="other_debts_czk" type="number" min="0" step="1000" value="${view.totals.otherDebts}" />
        </label>
        <label class="field">
          <span>Denní review time</span>
          <input data-scope="global" data-field="daily_review_time" type="time" value="${state.model.daily_review_time}" />
        </label>
      </div>
    </section>
  `;

  const propertyGroups = view.properties
    .map(
      (property) => `
        <section class="form-group">
          <span class="card-label">${property.label}</span>
          <h3>${property.name}</h3>
          <div class="form-grid">
            <label class="field">
              <span>Usage</span>
              <select data-scope="property" data-property-id="${property.id}" data-field="usage">
                <option value="unknown" ${property.assumptions.usage === "unknown" ? "selected" : ""}>Unknown</option>
                <option value="owner_occupied" ${property.assumptions.usage === "owner_occupied" ? "selected" : ""}>Owner occupied</option>
                <option value="rental" ${property.assumptions.usage === "rental" ? "selected" : ""}>Rental</option>
              </select>
            </label>
            <label class="field">
              <span>Nájem měsíčně</span>
              <input data-scope="property" data-property-id="${property.id}" data-field="monthly_rent_czk" type="number" min="0" step="500" value="${property.assumptions.monthly_rent_czk}" />
            </label>
            <label class="field">
              <span>Splátka hypotéky měsíčně</span>
              <input data-scope="property" data-property-id="${property.id}" data-field="monthly_mortgage_payment_czk" type="number" min="0" step="500" value="${property.assumptions.monthly_mortgage_payment_czk}" />
            </label>
            <label class="field">
              <span>Provozní náklady měsíčně</span>
              <input data-scope="property" data-property-id="${property.id}" data-field="monthly_operating_cost_czk" type="number" min="0" step="500" value="${property.assumptions.monthly_operating_cost_czk}" />
            </label>
            <label class="field">
              <span>Daň z nemovitosti ročně</span>
              <input data-scope="property" data-property-id="${property.id}" data-field="annual_property_tax_czk" type="number" min="0" step="100" value="${property.assumptions.annual_property_tax_czk}" />
            </label>
            <label class="field">
              <span>Pojištění ročně</span>
              <input data-scope="property" data-property-id="${property.id}" data-field="annual_insurance_czk" type="number" min="0" step="100" value="${property.assumptions.annual_insurance_czk}" />
            </label>
          </div>
        </section>
      `,
    )
    .join("");

  elements.assumptionsForm.innerHTML = globalFields + propertyGroups;
};

const renderCashflow = (view) => {
  elements.cashflowStatus.textContent = `${view.missingInputs.length} missing inputs`;
  elements.cashflowBreakdown.innerHTML = view.properties
    .map(
      (property) => `
        <div class="cashflow-row">
          <div>
            <strong>${property.name}</strong>
            <span>${property.assumptions.usage === "rental" ? "Rental mode" : property.assumptions.usage === "owner_occupied" ? "Owner occupied" : "Usage not set"}</span>
          </div>
          <div>
            <strong>${formatCurrency(property.monthlyRent)}</strong>
            <span>Příjmy</span>
          </div>
          <div>
            <strong>${formatCurrency(property.monthlyOutflow)}</strong>
            <span>Náklady</span>
          </div>
          <div>
            <strong>${formatCurrency(property.monthlyCashflow)}</strong>
            <span>Netto / měsíc</span>
          </div>
        </div>
      `,
    )
    .join("");

  elements.missingDataList.innerHTML =
    view.missingInputs.length > 0
      ? view.missingInputs.map((item) => `<span class="missing-chip">${item}</span>`).join("")
      : `<span class="pill accent">Cashflow inputs are complete for this browser.</span>`;
};

const renderProperties = (view) => {
  elements.propertyGrid.innerHTML = view.properties
    .map((property) => {
      const tags = [
        `${property.disposition || "-"}`,
        `${formatNumber(property.usable_area_m2)} m²`,
        property.floor ? `${property.floor}. patro` : null,
        property.garden_area_m2 ? `zahrada ${formatNumber(property.garden_area_m2)} m²` : null,
        property.balcony_area_m2 ? `balkon ${formatNumber(property.balcony_area_m2)} m²` : null,
        property.loggia_area_m2 ? `lodzie ${formatNumber(property.loggia_area_m2)} m²` : null,
      ]
        .filter(Boolean)
        .map((value) => `<span class="pill">${value}</span>`)
        .join("");

      const financeGrid = `
        <div class="finance-grid">
          <div class="finance-pill">
            <span>Equity</span>
            <strong>${formatCurrency(property.finance.equity_czk)}</strong>
          </div>
          <div class="finance-pill">
            <span>Hypotéka</span>
            <strong>${formatCurrency(property.finance.mortgage_balance_czk)}</strong>
          </div>
          <div class="finance-pill">
            <span>LTV</span>
            <strong>${formatPercent(property.finance.ltv_pct)}</strong>
          </div>
        </div>
      `;

      const comparables = property.comparables.length
        ? property.comparables
            .map(
              (comp) => `
                <div class="comp-card">
                  ${
                    comp.image_url
                      ? `<img class="comp-image" src="${comp.image_url}" alt="${comp.title}" loading="lazy" />`
                      : `<div class="comp-image" aria-hidden="true"></div>`
                  }
                  <div>
                    <span>${comp.locality}</span>
                    <p>${comp.title}</p>
                  </div>
                  <div class="comp-meta">
                    <span>${formatCurrency(comp.price_czk)}</span>
                    <span>${formatCurrency(comp.price_per_m2_czk)} / m²</span>
                    <span>${formatNumber(comp.usable_area_m2)} m²</span>
                    ${comp.distance_km !== null ? `<span>${formatNumber(comp.distance_km)} km</span>` : ""}
                  </div>
                  <a href="${comp.url}" target="_blank" rel="noreferrer">Open comparable</a>
                </div>
              `,
            )
            .join("")
        : `<div class="empty">Pro tuto nemovitost dnes nebyly k dispozici dost silné live comparables.</div>`;

      return `
        <article class="property-card">
          <div class="property-cover" style="--property-image:${cssImage(bestImage(property))}">
            <div class="property-head">
              <span class="card-label">${property.label}</span>
              <h3>${property.name}</h3>
              <p>${property.address}</p>
            </div>

            <div class="property-tags">${tags}</div>

            <div class="property-value">
              <span class="card-label">Dnešní odhad</span>
              <strong>${formatCurrency(property.valuation.estimated_value_czk)}</strong>
              <div class="property-range">
                ${formatCurrency(property.valuation.estimate_low_czk)} až ${formatCurrency(property.valuation.estimate_high_czk)}
              </div>
              <div class="property-note">
                ${property.valuation.methodology}
              </div>
            </div>
          </div>

          <div class="property-body">
            ${financeGrid}

            <div>
              <div class="property-meta">
                <span class="pill accent">Confidence ${Math.round(property.valuation.confidence_score * 100)} %</span>
                ${
                  property.valuation.value_change_vs_previous_czk
                    ? `<span class="pill">${property.valuation.value_change_vs_previous_czk >= 0 ? "+" : "-"}${formatCurrency(Math.abs(property.valuation.value_change_vs_previous_czk))} vs. last snapshot</span>`
                    : ""
                }
              </div>
              <div class="confidence-bar" style="--confidence-width:${Math.round(property.valuation.confidence_score * 100)}%"></div>
              <div class="confidence-meta">
                ${property.valuation.comparable_count} comparables, weighted market ppm² ${
                  property.valuation.weighted_price_per_m2_czk
                    ? formatCurrency(property.valuation.weighted_price_per_m2_czk)
                    : "-"
                }
              </div>
            </div>

            <div class="comparables">
              <h4>Top comparables</h4>
              ${comparables}
            </div>
          </div>
        </article>
      `;
    })
    .join("");
};

const renderHero = (view) => {
  const previous = view.snapshot.history.at(-2);
  const deltaEquity = previous
    ? view.totals.totalEquity - Number(previous.real_estate_equity_czk || 0)
    : null;

  elements.lastUpdatedPill.textContent = `Snapshot: ${formatDateTime(view.snapshot.generated_at)}`;
  elements.propertyCountPill.textContent = `${view.properties.length} tracked properties`;
  elements.refreshTimePill.textContent = `Daily review around ${state.model.daily_review_time}`;
  elements.heroNetWorth.textContent = formatCurrency(view.totals.portfolioNetWorth);
  elements.heroNarrative.textContent = `${formatCurrency(view.totals.totalEquity)} real-estate equity + ${formatCurrency(
    view.totals.cash,
  )} cash + ${formatCurrency(view.totals.pension)} pension - ${formatCurrency(view.totals.otherDebts)} other debt.`;
  elements.heroValue.textContent = formatCurrency(view.totals.totalValue);
  elements.heroValueDelta.textContent =
    deltaEquity === null
      ? "First stored snapshot in this series."
      : `${deltaEquity >= 0 ? "+" : "-"}${formatCurrency(Math.abs(deltaEquity))} equity vs. previous snapshot`;
  elements.heroDebt.textContent = formatCurrency(view.totals.totalDebt);
  elements.heroDebtMeta.textContent = `${view.properties.filter((property) => property.finance.ltv_pct !== null).length} active mortgage positions tracked`;
};

const render = () => {
  const view = computeViewModel();
  renderHero(view);
  renderShowcase(view);
  renderMetrics(view);
  renderChart(view.snapshot.history || []);
  renderNarrative(view);
  renderAssumptionsForm(view);
  renderCashflow(view);
  renderProperties(view);
};

const handleInput = (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
  const { scope, field, propertyId } = target.dataset;
  if (!scope || !field) return;

  const rawValue = target.value;
  const value = target.type === "number" ? Number(rawValue || 0) : rawValue;

  if (scope === "global") {
    state.model[field] = value;
  } else if (scope === "property" && propertyId) {
    state.model.properties[propertyId][field] = value;
  } else {
    return;
  }

  saveModel();
  render();
};

const refreshSnapshot = async () => {
  if (isFileProtocol) {
    window.alert("V file preview režimu nejde server-side refresh. Otevři appku přes localhost nebo Vercel deployment.");
    return;
  }
  if (state.refreshing) return;
  state.refreshing = true;
  elements.refreshButton.textContent = "Počítám…";

  try {
    const response = await fetch(refreshPath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    state.snapshot = payload.snapshot;
    state.model = loadModel(state.snapshot);
    saveModel();
    render();
  } catch (error) {
    console.error(error);
    window.alert("Nepodařilo se přepočítat portfolio snapshot.");
  } finally {
    state.refreshing = false;
    elements.refreshButton.textContent = "Přepočítat valuace";
  }
};

const loadSnapshot = async () => {
  if (isFileProtocol && window.__PORTFOLIO_SNAPSHOT__) {
    state.snapshot = window.__PORTFOLIO_SNAPSHOT__;
    state.model = loadModel(state.snapshot);
    saveModel();
    render();
    return;
  }

  const response = await fetch(`${snapshotPath}?ts=${Date.now()}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to load snapshot: ${response.status}`);
  }
  state.snapshot = await response.json();
  state.model = loadModel(state.snapshot);
  saveModel();
  render();
};

elements.assumptionsForm.addEventListener("input", handleInput);
elements.assumptionsForm.addEventListener("change", handleInput);
elements.refreshButton.addEventListener("click", refreshSnapshot);
elements.scrollToSetup.addEventListener("click", () =>
  document.getElementById("setup")?.scrollIntoView({ behavior: "smooth", block: "start" }),
);

loadSnapshot().catch((error) => {
  console.error(error);
  elements.heroNetWorth.textContent = "-";
  elements.heroNarrative.textContent = "Snapshot se nepodařilo načíst.";
  elements.metricsGrid.innerHTML = `<article class="metric-card"><span class="card-label">Error</span><strong>Snapshot unavailable</strong><p>Zkontroluj, že je vygenerovaný soubor <code>/data/portfolio_snapshot.json</code>.</p></article>`;
});
