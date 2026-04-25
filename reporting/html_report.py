from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config.logging_config import get_logger

logger = get_logger(__name__)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _priority_rank(insight: dict) -> int:
    title = (insight.get("title") or "").lower()
    impact_type = (insight.get("impact_type") or "").lower()
    # 1) Revenue loss prevention, 2) Revenue recovery, 3) Growth
    if impact_type == "risk" or "return" in title or "duplicate" in title or "discount" in title:
        return 0
    if "churn" in title or "dead inventory" in title:
        return 1
    return 2


def _top_priorities(insights: list[dict]) -> list[dict]:
    ranked = sorted(
        insights,
        key=lambda i: (
            {"high": 0, "medium": 1, "low": 2}.get((i.get("severity") or "").lower(), 9),
            _priority_rank(i),
            -_safe_float(i.get("potential_value")),
        ),
    )
    return ranked[:3]


def _health_score(summary: dict) -> int:
    insights = summary.get("insights", [])
    inventory = summary.get("inventory", {})
    customers = summary.get("customers", {})
    revenue = summary.get("revenue", {})
    trend = revenue.get("trend", {})

    score = 100
    high_count = len([i for i in insights if (i.get("severity") or "").lower() == "high"])
    medium_count = len([i for i in insights if (i.get("severity") or "").lower() == "medium"])
    score -= min(high_count * 15, 45)
    score -= min(medium_count * 8, 24)

    out_of_stock = len(inventory.get("out_of_stock", []))
    critical = len(inventory.get("critical_stock", []))
    score -= min(out_of_stock * 0.6, 18)
    score -= min(critical * 1.2, 12)

    churned = len(customers.get("churned", []))
    score -= min(churned * 1.5, 12)

    current_7d = _safe_int(trend.get("current_7d_orders"))
    if current_7d == 0:
        score -= 12
    elif current_7d < 5:
        score -= 6

    return max(0, min(100, round(score)))


def _health_color(score: int) -> str:
    if score <= 40:
        return "red"
    if score <= 70:
        return "yellow"
    return "green"


def _build_dashboard_data(summary: dict) -> dict:
    insights = summary.get("insights", [])
    inventory = summary.get("inventory", {})
    customers = summary.get("customers", {})
    revenue = summary.get("revenue", {})

    churned_recovery = sum(
        _safe_float(i.get("potential_value"))
        for i in insights
        if (i.get("title") or "").lower() == "churned customers"
    )
    returns_recovery = sum(
        _safe_float(i.get("potential_value"))
        for i in insights
        if (i.get("title") or "").lower() == "high return rate product"
    )
    recoverable = churned_recovery + returns_recovery
    risk_exposure = sum(
        _safe_float(i.get("potential_value"))
        for i in insights
        if (i.get("impact_type") or "").lower() == "risk"
    )
    net_impact = recoverable - risk_exposure

    priorities = []
    for i in _top_priorities(insights):
        value = _safe_float(i.get("potential_value"))
        score = max(1.0, min(10.0, round((value / 100.0) + (3 if (i.get("severity") == "high") else 1.5), 1)))
        priorities.append(
            {
                "title": i.get("title") or "Untitled Priority",
                "severity": (i.get("severity") or "medium").upper(),
                "impactLabel": "at risk" if (i.get("impact_type") or "").lower() == "risk" else "potential",
                "impactValue": value,
                "priorityScore": score,
                "intensity": int(min(100, score * 10)),
            }
        )

    execution_plan = []
    for p in priorities:
        title = p["title"].lower()
        if "return" in title:
            execution_plan.append({"task": "Fix revenue leakage: pause high-return SKU", "minutes": 2})
        elif "churn" in title:
            execution_plan.append({"task": "Recover churned revenue: send win-back emails", "minutes": 5})
        elif "inventory" in title:
            execution_plan.append({"task": "Unlock tied capital: discount dead inventory", "minutes": 15})
        elif "concentration" in title:
            execution_plan.append({"task": "Reduce dependency risk: launch acquisition campaign", "minutes": 8})
    if not execution_plan:
        execution_plan = [{"task": "Execute highest-value fix first", "minutes": 10}]
    execution_plan = execution_plan[:3]

    total_minutes = sum(step["minutes"] for step in execution_plan)

    loyal = customers.get("loyal", [])
    loyal_revenue = sum(_safe_float(c.get("total_spent")) for c in loyal)
    top2_revenue = sum(_safe_float(c.get("total_spent")) for c in loyal[:2])
    concentration_pct = int(round((top2_revenue / loyal_revenue * 100), 0)) if loyal_revenue > 0 else 0

    dead_products = len(summary.get("anomalies", {}).get("no_sales_products", []))
    active_products = max(dead_products + 5, dead_products)  # placeholder for visual context only

    out_of_stock = len(inventory.get("out_of_stock", []))
    low_stock = len(inventory.get("low_stock", []))
    critical_stock = len(inventory.get("critical_stock", []))

    trend = revenue.get("trend", {})
    current_7d_orders = _safe_int(trend.get("current_7d_orders"))
    previous_7d_orders = _safe_int(trend.get("previous_7d_orders"))
    orders_change = current_7d_orders - previous_7d_orders

    net_revenue = _safe_float(revenue.get("summary", {}).get("net_revenue"))
    projected = net_revenue + recoverable
    projection_pct = ((projected - net_revenue) / net_revenue * 100) if net_revenue > 0 else 0.0

    health_score = _health_score(summary)
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "kpis": {
            "recoverableRevenue": recoverable,
            "riskExposure": risk_exposure,
            "netImpact": net_impact,
        },
        "health": {
            "score": health_score,
            "color": _health_color(health_score),
            "subscores": {
                "inventory": max(0, min(100, 100 - (out_of_stock + critical_stock) * 3)),
                "customers": max(0, min(100, 100 - concentration_pct // 2)),
                "revenue": 35 if current_7d_orders == 0 else min(100, 45 + current_7d_orders * 7),
            },
        },
        "priorities": priorities,
        "executionPlan": execution_plan,
        "executionTotalMinutes": total_minutes,
        "charts": {
            "deadInventory": {"dead": dead_products, "active": active_products},
            "customerRisk": {"concentrated": concentration_pct, "diversified": max(0, 100 - concentration_pct)},
            "stockIssues": {
                "outOfStock": out_of_stock,
                "lowStock": low_stock,
                "criticalStock": critical_stock,
            },
        },
        "alerts": {
            "outOfStock": f"{out_of_stock} out-of-stock variants need immediate restock.",
            "churned": f"{len(customers.get('churned', []))} churned customers are ready for win-back.",
            "deadInventory": f"{dead_products} dead products are locking working capital.",
        },
        "projection": {
            "currentRevenue": net_revenue,
            "projectedRevenue": projected,
            "increasePct": projection_pct,
        },
        "comparison": {
            "revenueChange": recoverable - risk_exposure,
            "ordersChange": orders_change,
            "churnChange": len(customers.get("churned", [])),
        },
    }


def build_report_html(summary: dict) -> str:
    """
    Builds the premium dashboard-style HTML report content.
    """
    dashboard_data = _build_dashboard_data(summary)
    data_json = json.dumps(dashboard_data)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Store Intelligence Report</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-gray-50 text-gray-900">
  <div class="max-w-7xl mx-auto px-6 py-8">
    <header class="mb-8">
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 class="text-3xl md:text-4xl font-bold tracking-tight">Store Intelligence Report</h1>
          <p id="generatedAt" class="text-sm text-gray-500 mt-1"></p>
        </div>
        <div class="bg-white rounded-2xl shadow-md p-6 w-full md:w-96">
          <p class="text-sm uppercase tracking-wide text-gray-500">Store Health Score</p>
          <div class="mt-2 flex items-end justify-between">
            <p id="healthScore" class="text-4xl font-bold">0 / 100</p>
            <span id="healthPill" class="text-xs px-3 py-1 rounded-full font-semibold"></span>
          </div>
          <div class="mt-4 w-full h-3 bg-gray-200 rounded-full overflow-hidden">
            <div id="healthBar" class="h-full rounded-full transition-all duration-500" style="width:0%"></div>
          </div>
          <div class="grid grid-cols-3 gap-2 mt-4 text-xs text-gray-500">
            <div>Inventory <span id="subInventory" class="font-semibold text-gray-800"></span></div>
            <div>Customers <span id="subCustomers" class="font-semibold text-gray-800"></span></div>
            <div>Revenue <span id="subRevenue" class="font-semibold text-gray-800"></span></div>
          </div>
        </div>
      </div>
    </header>

    <section class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      <div class="bg-white rounded-2xl shadow-md p-6 hover:shadow-lg transition">
        <p class="text-sm text-gray-500 uppercase tracking-wide">Recoverable Revenue</p>
        <p id="kpiRecoverable" class="text-4xl font-bold text-emerald-600 mt-2">$0</p>
      </div>
      <div class="bg-white rounded-2xl shadow-md p-6 hover:shadow-lg transition">
        <p class="text-sm text-gray-500 uppercase tracking-wide">Risk Exposure</p>
        <p id="kpiRisk" class="text-4xl font-bold text-amber-600 mt-2">$0</p>
      </div>
      <div class="bg-white rounded-2xl shadow-md p-6 hover:shadow-lg transition">
        <p class="text-sm text-gray-500 uppercase tracking-wide">Net Impact</p>
        <p id="kpiNet" class="text-4xl font-bold mt-2">$0</p>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
      <div class="lg:col-span-2 bg-white rounded-2xl shadow-md p-6">
        <h2 class="text-lg font-semibold">Today's Priorities</h2>
        <div id="priorityCards" class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4"></div>
      </div>
      <div class="bg-white rounded-2xl shadow-md p-6">
        <h2 class="text-lg font-semibold">Execution Plan</h2>
        <p id="totalFixTime" class="text-sm text-gray-500 mt-1"></p>
        <ul id="executionList" class="mt-4 space-y-3"></ul>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
      <div class="bg-white rounded-2xl shadow-md p-6">
        <h3 class="text-lg font-semibold mb-4">Dead Inventory</h3>
        <canvas id="deadInventoryChart" height="180"></canvas>
      </div>
      <div class="bg-white rounded-2xl shadow-md p-6">
        <h3 class="text-lg font-semibold mb-4">Customer Risk</h3>
        <canvas id="customerRiskChart" height="180"></canvas>
      </div>
      <div class="bg-white rounded-2xl shadow-md p-6">
        <h3 class="text-lg font-semibold mb-4">Stock Issues</h3>
        <canvas id="stockIssuesChart" height="180"></canvas>
      </div>
    </section>

    <section class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      <div class="rounded-2xl shadow-md p-6 bg-red-50 border border-red-200">
        <h4 class="font-semibold text-red-700">Out-of-stock Alert</h4>
        <p id="alertOutOfStock" class="text-sm text-red-600 mt-2"></p>
      </div>
      <div class="rounded-2xl shadow-md p-6 bg-amber-50 border border-amber-200">
        <h4 class="font-semibold text-amber-700">Churn Risk</h4>
        <p id="alertChurned" class="text-sm text-amber-700 mt-2"></p>
      </div>
      <div class="rounded-2xl shadow-md p-6 bg-slate-50 border border-slate-200">
        <h4 class="font-semibold text-slate-700">Dead Inventory</h4>
        <p id="alertDeadInventory" class="text-sm text-slate-700 mt-2"></p>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
      <div class="bg-white rounded-2xl shadow-md p-6">
        <h3 class="text-lg font-semibold">If you execute today's plan</h3>
        <p id="projectionText" class="text-2xl font-bold mt-3"></p>
        <p id="projectionDelta" class="text-sm text-emerald-600 mt-2"></p>
      </div>
      <div class="bg-white rounded-2xl shadow-md p-6">
        <h3 class="text-lg font-semibold">Change vs previous period</h3>
        <div class="mt-4 space-y-2 text-sm">
          <p id="cmpRevenue"></p>
          <p id="cmpOrders"></p>
          <p id="cmpChurn"></p>
        </div>
      </div>
    </section>
  </div>

  <script>
    const dashboardData = {data_json};

    function money(v) {{
      return new Intl.NumberFormat("en-US", {{ style: "currency", currency: "USD", maximumFractionDigits: 2 }}).format(v || 0);
    }}

    function signedMoney(v) {{
      const sign = v >= 0 ? "+" : "-";
      return `${{sign}}${{money(Math.abs(v))}}`;
    }}

    function trendArrow(v) {{
      if (v > 0) return "↑";
      if (v < 0) return "↓";
      return "→";
    }}

    document.getElementById("generatedAt").textContent = `Generated: ${{dashboardData.generatedAt}}`;

    const score = dashboardData.health.score;
    const color = dashboardData.health.color;
    const colorMap = {{
      red: {{ bar: "bg-red-500", pill: "bg-red-100 text-red-700", label: "Weak" }},
      yellow: {{ bar: "bg-amber-500", pill: "bg-amber-100 text-amber-700", label: "Watch" }},
      green: {{ bar: "bg-emerald-500", pill: "bg-emerald-100 text-emerald-700", label: "Healthy" }},
    }};
    const c = colorMap[color] || colorMap.yellow;
    document.getElementById("healthScore").textContent = `${{score}} / 100`;
    document.getElementById("healthBar").classList.add(...c.bar.split(" "));
    document.getElementById("healthBar").style.width = `${{score}}%`;
    document.getElementById("healthPill").classList.add(...c.pill.split(" "));
    document.getElementById("healthPill").textContent = c.label;
    document.getElementById("subInventory").textContent = dashboardData.health.subscores.inventory;
    document.getElementById("subCustomers").textContent = dashboardData.health.subscores.customers;
    document.getElementById("subRevenue").textContent = dashboardData.health.subscores.revenue;

    document.getElementById("kpiRecoverable").textContent = money(dashboardData.kpis.recoverableRevenue);
    document.getElementById("kpiRisk").textContent = money(dashboardData.kpis.riskExposure);
    const netEl = document.getElementById("kpiNet");
    netEl.textContent = signedMoney(dashboardData.kpis.netImpact);
    netEl.classList.add(dashboardData.kpis.netImpact >= 0 ? "text-emerald-600" : "text-red-600");

    const prioritiesWrap = document.getElementById("priorityCards");
    dashboardData.priorities.forEach((p) => {{
      const severityTone = p.severity === "HIGH"
        ? "text-red-700 bg-red-50 border-red-200"
        : "text-amber-700 bg-amber-50 border-amber-200";
      const card = document.createElement("div");
      card.className = "border rounded-2xl p-4 hover:shadow-md transition";
      card.innerHTML = `
        <div class="flex items-center justify-between">
          <span class="text-xs px-2 py-1 rounded-full border ${{severityTone}}">${{p.severity}}</span>
          <span class="text-xs text-gray-500">Score: ${{p.priorityScore}} / 10</span>
        </div>
        <h4 class="text-sm font-semibold mt-3">${{p.title}}</h4>
        <p class="text-2xl font-bold mt-2">${{p.impactLabel === "at risk" ? "" : "+"}}${{money(p.impactValue)}}</p>
        <div class="w-full bg-gray-200 h-2 rounded-full mt-3 overflow-hidden">
          <div class="h-2 rounded-full bg-slate-700" style="width:${{p.intensity}}%"></div>
        </div>
      `;
      prioritiesWrap.appendChild(card);
    }});

    document.getElementById("totalFixTime").textContent = `Total Fix Time: ${{dashboardData.executionTotalMinutes}} minutes`;
    const executionList = document.getElementById("executionList");
    dashboardData.executionPlan.forEach((step) => {{
      const li = document.createElement("li");
      li.className = "flex items-start justify-between gap-3";
      li.innerHTML = `
        <div class="flex items-start gap-3">
          <input type="checkbox" class="mt-1 rounded border-gray-300">
          <span class="text-sm">${{step.task}}</span>
        </div>
        <span class="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full">${{step.minutes}} min</span>
      `;
      executionList.appendChild(li);
    }});

    document.getElementById("alertOutOfStock").textContent = dashboardData.alerts.outOfStock;
    document.getElementById("alertChurned").textContent = dashboardData.alerts.churned;
    document.getElementById("alertDeadInventory").textContent = dashboardData.alerts.deadInventory;

    document.getElementById("projectionText").textContent =
      `${{money(dashboardData.projection.currentRevenue)}} -> ${{money(dashboardData.projection.projectedRevenue)}}`;
    document.getElementById("projectionDelta").textContent =
      `Potential uplift: +${{dashboardData.projection.increasePct.toFixed(1)}}%`;

    const cmpRev = dashboardData.comparison.revenueChange;
    const cmpOrd = dashboardData.comparison.ordersChange;
    const cmpChurn = dashboardData.comparison.churnChange;
    document.getElementById("cmpRevenue").textContent = `${{trendArrow(cmpRev)}} Revenue delta: ${{signedMoney(cmpRev)}}`;
    document.getElementById("cmpOrders").textContent = `${{trendArrow(cmpOrd)}} Orders delta: ${{cmpOrd}}`;
    document.getElementById("cmpChurn").textContent = `${{cmpChurn > 0 ? "↑" : "→"}} Churned customers tracked: ${{cmpChurn}}`;

    new Chart(document.getElementById("deadInventoryChart"), {{
      type: "bar",
      data: {{
        labels: ["Dead Products", "Active Products"],
        datasets: [{{
          label: "Product Count",
          data: [dashboardData.charts.deadInventory.dead, dashboardData.charts.deadInventory.active],
          backgroundColor: ["#B42318", "#1570EF"],
          borderRadius: 10,
        }}]
      }},
      options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
    }});

    new Chart(document.getElementById("customerRiskChart"), {{
      type: "pie",
      data: {{
        labels: ["Concentrated Revenue", "Diversified Revenue"],
        datasets: [{{
          data: [dashboardData.charts.customerRisk.concentrated, dashboardData.charts.customerRisk.diversified],
          backgroundColor: ["#B54708", "#12B76A"],
        }}]
      }},
      options: {{ responsive: true, plugins: {{ legend: {{ position: "bottom" }} }} }}
    }});

    new Chart(document.getElementById("stockIssuesChart"), {{
      type: "bar",
      data: {{
        labels: ["Out-of-stock", "Low", "Critical"],
        datasets: [{{
          data: [
            dashboardData.charts.stockIssues.outOfStock,
            dashboardData.charts.stockIssues.lowStock,
            dashboardData.charts.stockIssues.criticalStock
          ],
          backgroundColor: ["#B42318", "#175CD3", "#B54708"],
          borderRadius: 10,
        }}]
      }},
      options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
    }});
  </script>
</body>
</html>
"""


def create_report_html(summary: dict, output_dir: str = "reports") -> str:
    """
    Creates a premium dashboard-style HTML report using TailwindCSS + Chart.js.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"store-intelligence-{datetime.now(timezone.utc).strftime('%Y%m%d')}.html"
    output_path = out_dir / filename

    html = build_report_html(summary)

    output_path.write_text(html, encoding="utf-8")
    logger.info("HTML report written to %s", output_path)
    return str(output_path)
