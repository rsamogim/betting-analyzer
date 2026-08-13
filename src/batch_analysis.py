"""Roda o pipeline completo (analysis -> confidence -> monte_carlo -> recommendation) pra todos os jogos de um arquivo de odds salvo."""

import json
from pathlib import Path

from analysis import analyze_implied_odds
from betting_recommendation import suggest_bets
from confidence import calculate_confidence, xg_from_over_prob
from monte_carlo import derive_probabilities, estimate_xg_split, simulate_match

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def analyze_game(game: dict) -> dict | None:
    """Roda o pipeline completo pra 1 jogo. Retorna None se a Pinnacle nao tiver
    linha de totals em 2.5 pra esse jogo (a calibracao de xG depende dela).
    """
    analysis = analyze_implied_odds(game)
    if analysis.get("over_2_5_prob") is None:
        return None

    confidence = calculate_confidence(analysis)
    xg_expected = xg_from_over_prob(confidence["over_2_5_prob_real"])
    probs = {
        "home": confidence["home_prob_real"],
        "draw": confidence["draw_prob_real"],
        "away": confidence["away_prob_real"],
        "over_2_5": confidence["over_2_5_prob_real"],
        "under_2_5": confidence["under_2_5_prob_real"],
    }
    xg_home, xg_away = estimate_xg_split(xg_expected, probs["home"], probs["away"])
    simulation = simulate_match(xg_home, xg_away, simulations=10000)
    derived = derive_probabilities(simulation["score_distribution"])

    game_analysis = {
        "game_id": analysis["game_id"],
        "home_team": analysis["home_team"],
        "away_team": analysis["away_team"],
        "confidence_pct": confidence["confidence_pct"],
        "correlation": confidence["correlation"],
        "xg_expected": xg_expected,
        "probs_normalized": probs,
    }
    monte_carlo_results = {
        "over_2_5_prob_simulated": derived["over_2_5_prob"],
        "under_2_5_prob_simulated": derived["under_2_5_prob"],
    }

    return {
        "home_team": game_analysis["home_team"],
        "away_team": game_analysis["away_team"],
        "suggestions": suggest_bets(game_analysis, monte_carlo_results),
    }


def run_batch(games: list[dict]) -> dict:
    analyzed = []
    skipped = 0
    for game in games:
        result = analyze_game(game)
        if result is None:
            skipped += 1
            continue
        analyzed.append(result)

    return {
        "games_total": len(games),
        "games_analyzed": len(analyzed),
        "games_skipped_no_2_5_line": skipped,
        "total_suggestions": sum(len(r["suggestions"]) for r in analyzed),
        "results": analyzed,
    }


def main() -> None:
    with open(DATA_DIR / "sample_odds_response.json", "r", encoding="utf-8") as f:
        games = json.load(f)

    batch = run_batch(games)

    print(f"Jogos no arquivo: {batch['games_total']}")
    print(f"Jogos analisados (Pinnacle com linha 2.5): {batch['games_analyzed']}")
    print(f"Jogos pulados (sem linha 2.5 na Pinnacle): {batch['games_skipped_no_2_5_line']}")
    print(f"Total de sugestoes com value: {batch['total_suggestions']}\n")

    for result in batch["results"]:
        label = f"{result['home_team']} vs {result['away_team']}"
        if result["suggestions"]:
            for s in result["suggestions"]:
                print(f"  [{label}] {s['market']}: edge {s['edge_pct']}pp, {s['units']} unidades")
        else:
            print(f"  [{label}] sem sugestao")


if __name__ == "__main__":
    main()
