"""Compara probabilidades simuladas com as implicitas no mercado e sugere apostas com value."""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

EDGE_THRESHOLD_PCT = 5.0  # so sugere quando simulado supera o implied por isso ou mais
HALF_KELLY = 0.5  # reduz o Kelly cheio pela metade - pratica comum pra reduzir variancia
MAX_UNITS = 5.0  # teto de risco por aposta, independente do que o Kelly mandar


def implied_to_decimal_odds(implied_prob_pct: float) -> float:
    """Reconstroi a odd decimal a partir do implied prob percentual (odds = 100/prob).

    Aproximacao: assume que a odd reconstruida (com o vig ja embutido no
    implied prob) e a odd real disponivel pra apostar - nao busca a odd bruta
    de novo na API.
    """
    return round(100 / implied_prob_pct, 3)


def kelly_fraction(true_prob_pct: float, decimal_odds: float) -> float:
    """Kelly: f* = (b*p - q) / b, onde b = odds decimais - 1, p = prob "verdadeira" (simulada)."""
    p = true_prob_pct / 100
    q = 1 - p
    b = decimal_odds - 1
    f = (b * p - q) / b
    return max(0.0, f)


def kelly_units(f: float, confidence_pct: float) -> float:
    """Converte fracao de Kelly em 'unidades' (convencao: 1 unidade = 1% do bankroll).

    Aplica half-Kelly (HALF_KELLY) pra reduzir variancia e escala pela
    confianca do sinal (confidence_pct/100, vindo da correlacao h2h/totals).
    Sempre capado em MAX_UNITS como teto de risco.
    """
    stake_pct_bankroll = f * HALF_KELLY * (confidence_pct / 100) * 100
    return round(min(MAX_UNITS, stake_pct_bankroll), 2)


def market_comparisons(game_analysis: dict, monte_carlo_results: dict) -> list[dict]:
    """Compara simulado (Monte Carlo) vs implied odds do mercado, market a market, sem filtro de edge.

    Markets cobertos: so Over/Under 2.5. 1X2 foi removido - o split home/away
    (Opcao A) nunca foi calibrado pra reproduzir o 1X2 real, entao "value" ali
    era mais provavel erro de modelo do que edge de mercado (ver historico).
    game_analysis: saida de confidence.py (tem probs_normalized).
    monte_carlo_results: saida de monte_carlo.py (tem as probs simuladas de totals).
    """
    probs = game_analysis.get("probs_normalized", {})
    markets = [
        ("Over 2.5", monte_carlo_results.get("over_2_5_prob_simulated"), probs.get("over_2_5")),
        ("Under 2.5", monte_carlo_results.get("under_2_5_prob_simulated"), probs.get("under_2_5")),
    ]

    comparisons = []
    for label, simulated, implied in markets:
        if simulated is None or implied is None:
            continue
        comparisons.append(
            {
                "market": label,
                "simulated_prob": simulated,
                "implied_prob": implied,
                "edge_pct": round(simulated - implied, 2),
            }
        )
    return comparisons


def suggest_bets(game_analysis: dict, monte_carlo_results: dict, edge_threshold_pct: float = EDGE_THRESHOLD_PCT) -> list[dict]:
    """Filtra market_comparisons() para as apostas com edge >= edge_threshold_pct (default 5pp)
    e calcula o tamanho de aposta (Kelly simplificado) pra cada uma.
    """
    confidence_pct = game_analysis.get("confidence_pct", 65.0)

    suggestions = []
    for comparison in market_comparisons(game_analysis, monte_carlo_results):
        if comparison["edge_pct"] < edge_threshold_pct:
            continue

        decimal_odds = implied_to_decimal_odds(comparison["implied_prob"])
        f = kelly_fraction(comparison["simulated_prob"], decimal_odds)
        units = kelly_units(f, confidence_pct)

        suggestions.append(
            {
                **comparison,
                "decimal_odds_est": decimal_odds,
                "kelly_fraction": round(f, 4),
                "units": units,
            }
        )

    return suggestions


def main() -> None:
    with open(DATA_DIR / "sample_confidence.json", "r", encoding="utf-8") as f:
        game_analysis = json.load(f)
    with open(DATA_DIR / "sample_monte_carlo.json", "r", encoding="utf-8") as f:
        monte_carlo_results = json.load(f)

    comparisons = market_comparisons(game_analysis, monte_carlo_results)
    suggestions = suggest_bets(game_analysis, monte_carlo_results)

    print(f"{game_analysis['home_team']} vs {game_analysis['away_team']}\n")
    print("Analise por market (simulado vs implied):")
    for c in comparisons:
        print(f"  {c['market']:<10} simulado={c['simulated_prob']}%  implied={c['implied_prob']}%  edge={c['edge_pct']:+.2f}pp")

    print()
    if suggestions:
        for s in suggestions:
            print(f"  -> SUGESTAO: {s['market']}: edge {s['edge_pct']}pp, odds~{s['decimal_odds_est']}, {s['units']} unidades")
    else:
        print("Nenhuma sugestao (Over/Under parecem justos)")

    result = {
        "game_id": game_analysis.get("game_id"),
        "home_team": game_analysis["home_team"],
        "away_team": game_analysis["away_team"],
        "market_analysis": comparisons,
        "suggestions": suggestions,
    }

    output_path = DATA_DIR / "sample_recommendations_simplified.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nSalvo em: {output_path}")


if __name__ == "__main__":
    main()
