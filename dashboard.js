async function loadData() {
  const data = await fetch("/api/data").then(response => response.json());

  const carbon = document.querySelector("#carbon");
  carbon.innerHTML = data.carbon.slice(0, 8).map(item =>
    `<li><span>${item.ingredient}</span><strong>${Math.round(item.kg_co2e).toLocaleString()} kg CO2e</strong></li>`
  ).join("");
}

async function loadRecommendation() {
  const period = document.querySelector("#period").value;
  const day = document.querySelector("#day").value;
  const params = new URLSearchParams({ period, day });
  const result = await fetch(`/api/recommend?${params}`).then(response => response.json());

  document.querySelector("#turnout").textContent = result.predicted_turnout.toLocaleString();

  document.querySelector("#recommendations").innerHTML = result.recommendations.map(item => `
    <div class="alternative-item">
      <div>
        <strong>${item.dish}</strong>
        <div class="alternative-meta">${item.meal_fit} fit · ${item.ingredient_coverage}% ingredients covered · ${item.estimated_kg_co2e} kg CO2e estimate</div>
      </div>
      <div class="alternative-result">
        <span>Recommendation score</span>
        <strong>${item.score}</strong>
      </div>
      <div class="alternative-result">
        <span>Amount to make</span>
        <strong>${item.amount_to_make.toLocaleString()} portions</strong>
      </div>
    </div>
  `).join("") || '<div class="recommendation-item"><strong>No matching dishes</strong></div>';

  const dishCarbon = document.querySelector("#dishCarbon");
  if (result.chosen) {
    dishCarbon.innerHTML = result.chosen.carbon_breakdown.map(item =>
      `<li><span>${item.ingredient}</span><strong>${item.kg_co2e_per_kg} kg CO2e/kg</strong></li>`
    ).join("");
  } else {
    dishCarbon.innerHTML = "<li><span>No dish selected</span></li>";
  }

  const recommended = result.recommendations;
  const maxMade = Math.max(...recommended.map(item => item.made), 1);
  document.querySelector("#recommendedConsumption").innerHTML = recommended.map(item => {
    const madeWidth = item.made / maxMade * 100;
    const consumedWidth = item.consumed / maxMade * 100;
    return `
      <div class="chart-row">
        <strong class="chart-label">${item.dish}</strong>
        <div class="paired-bars">
          <div class="paired-bar made" style="width:${madeWidth}%"><span>Made ${item.made}</span></div>
          <div class="paired-bar consumed" style="width:${consumedWidth}%"><span>Consumed ${item.consumed}</span></div>
        </div>
      </div>
    `;
  }).join("");

  const maxLeftover = Math.max(...recommended.map(item => item.avg_leftover_pct * 100), 1);
  document.querySelector("#recommendedLeftovers").innerHTML = recommended.map(item => {
    const value = item.avg_leftover_pct * 100;
    const width = value / maxLeftover * 100;
    return `
      <div class="chart-row">
        <strong class="chart-label">${item.dish}</strong>
        <div class="leftover-track">
          <div class="leftover-bar" style="width:${width}%"><span>${value.toFixed(1)}%</span></div>
        </div>
      </div>
    `;
  }).join("");
}

document.querySelectorAll("#day, #period").forEach(control => {
  control.addEventListener("change", loadRecommendation);
  control.addEventListener("input", loadRecommendation);
});

loadData();
loadRecommendation();
