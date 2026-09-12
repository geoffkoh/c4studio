// Front-, middle- and back-office actors, grouped by desk.

group "Front Office" {
    pm     = person "Portfolio Manager" "Constructs portfolios from strategy signals and raises parent orders"
    trader = person "Execution Trader" "Works orders, tunes algos and monitors execution quality"
    quant  = person "Quant Researcher" "Develops alpha signals and transaction cost models"
}

group "Middle Office" {
    riskMgr    = person "Risk Manager" "Monitors exposures, limits, VaR and drawdowns"
    compliance = person "Compliance Officer" "Maintains mandates and oversees regulatory reporting"
}

group "Back Office" {
    opsAnalyst = person "Operations Analyst" "Owns settlement, reconciliation and corporate actions"
}
