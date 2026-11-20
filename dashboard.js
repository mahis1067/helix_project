async function loadData() {
  const data = await fetch("/api/data").then(response => response.json());

  const popular = document.querySelector("#popular");
  popular.innerHTML = data.popular_dishes.slice(0, 8).map(item =>
    `<li><div><strong>${item.dish}</strong><div class="bar-track"><div class="bar" style="width:${item.consumed_pct * 100}%"></div></div></div><strong>${Math.round(item.consumed_pct * 100)}%</strong></li>`
  ).join("");

  const leftovers = document.querySelector("#leftovers");
  leftovers.innerHTML = ["morning", "afternoon", "evening"].map(period =>
    `<li><div><strong>${period}</strong><div class="bar-track"><div class="bar" style="width:${data.period_leftovers[period] * 100}%;background:${period === "morning" ? "#e8a52b" : period === "afternoon" ? "#0d7a63" : "#2e73b8"}"></div></div></div><strong>${Math.round(data.period_leftovers[period] * 100)}%</strong></li>`
  ).join("");

  const carbon = document.querySelector("#carbon");
  carbon.innerHTML = data.carbon.slice(0, 8).map(item =>
    `<li><span>${item.ingredient}</span><strong>${Math.round(item.kg_co2e).toLocaleString()} kg CO2e</strong></li>`
  ).join("");
}

async function loadRecommendation() {
  const period = document.querySelector("#period").value;
  const day = document.querySelector("#day").value;
  const available = document.querySelector("#available").value;
  const params = new URLSearchParams({ period, day, available });
  const result = await fetch(`/api/recommend?${params}`).then(response => response.json());

  document.querySelector("#turnout").textContent = result.predicted_turnout.toLocaleString();
  document.querySelector("#chosenDish").textContent = result.chosen?.dish || "No recommendation";
  document.querySelector("#chosenScore").textContent =
    result.chosen ? `Recommendation score ${result.chosen.score}` : "";

  const chosenIngredients = document.querySelector("#chosenIngredients");
  if (result.chosen) {
    const ingredients = result.chosen.ingredients.split(",").map(item => item.trim());
    chosenIngredients.innerHTML = ingredients.map(item =>
      `<span class="tag ${result.chosen.missing_ingredients.includes(item.toLowerCase()) ? "missing" : ""}">${item}</span>`
    ).join("");
  }

  document.querySelector("#recommendations").innerHTML = result.recommendations.map(item => `
    <div class="recommendation-item">
      <div><strong>${item.dish}</strong><br><span>${item.meal_fit} fit · ${item.ingredient_coverage}% ingredients covered</span></div>
      <strong>${item.score}</strong>
    </div>
  `).join("");
}

document.querySelectorAll("#day, #period, #available").forEach(control => {
  control.addEventListener("change", loadRecommendation);
  control.addEventListener("input", loadRecommendation);
});

document.querySelectorAll(".entry-tabs button").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".entry-tabs button").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    document.querySelectorAll(".entry-form").forEach(form => form.classList.add("hidden"));
    document.querySelectorAll(".entry-form").forEach(form => {
      if (form.dataset.table === button.dataset.table) form.classList.remove("hidden");
    });
  });
});

document.querySelectorAll(".entry-form").forEach(form => {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form));
    payload.table = form.dataset.table;
    const status = document.querySelector("#entryStatus");
    status.textContent = "Saving...";
    try {
      const response = await fetch("/api/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      status.textContent = "Entry added to the workbook.";
      form.reset();
      await loadData();
      await loadRecommendation();
    } catch (error) {
      status.textContent = error.message;
      status.style.color = "#b42318";
    }
  });
});

loadData();
loadRecommendation();
