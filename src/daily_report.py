"""Gera o relatorio diario pre-jogo, varrendo as ligas configuradas em config.yaml."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from analysis import analyze_implied_odds
from api_client import fetch_games_with_odds, get_api_key, load_config
from betting_recommendation import suggest_bets
from confidence import calculate_confidence, xg_from_over_prob
from monte_carlo import derive_probabilities, estimate_xg_split, simulate_match

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
BRT = timezone(timedelta(hours=-3))


def analyze_game(game: dict) -> dict | None:
    """Roda o pipeline completo (analysis -> confidence -> monte_carlo -> recommendation) pra 1 jogo.

    None se a Pinnacle nao tiver linha de totals em 2.5 pra esse jogo - a
    calibracao de xG (invert_poisson_cdf) depende especificamente dela.
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
        "commence_time": game.get("commence_time"),
        "suggestions": suggest_bets(game_analysis, monte_carlo_results),
    }


def loop_all_leagues(leagues: list[dict], api_key: str, base_url: str, days: int = 7) -> dict:
    """Busca jogos dos proximos `days` dias pra cada liga (leagues = [{"key":..., "name":...}]),
    filtra pela linha de totals 2.5 na Pinnacle e roda o pipeline completo.
    """
    leagues_summary = []
    all_suggestions = []
    credits_used = 0
    credits_remaining = None
    games_found_total = 0
    games_analyzed_total = 0

    for league in leagues:
        games, response = fetch_games_with_odds(
            league["key"], api_key, base_url, markets=["h2h", "totals"], days=days
        )
        credits_used += int(response.headers.get("x-requests-last", 0))
        credits_remaining = response.headers.get("x-requests-remaining")

        analyzed = []
        for game in games:
            result = analyze_game(game)
            if result is None:
                continue
            analyzed.append(result)
            for s in result["suggestions"]:
                all_suggestions.append(
                    {**s, "league": league["name"], "match": f"{result['home_team']} vs {result['away_team']}"}
                )

        games_found_total += len(games)
        games_analyzed_total += len(analyzed)
        leagues_summary.append(
            {
                "league": league["name"],
                "sport_key": league["key"],
                "games_found": len(games),
                "games_analyzed": len(analyzed),
            }
        )

    coverage_pct = round(games_analyzed_total / games_found_total * 100, 1) if games_found_total else 0.0

    return {
        "leagues_summary": leagues_summary,
        "games_found_total": games_found_total,
        "games_analyzed_total": games_analyzed_total,
        "coverage_pct": coverage_pct,
        "credits_used": credits_used,
        "credits_remaining": credits_remaining,
        "suggestions": all_suggestions,
    }


def format_report(report: dict, leagues: list[dict], now_brt: datetime) -> str:
    league_names = ", ".join(league["name"] for league in leagues)

    lines = [
        f"=== ANALISE PRE-JOGO {now_brt.strftime('%H:%M')} BRT ({now_brt.strftime('%d/%m/%Y')}) ===",
        "",
        f"Ligas analisadas: {league_names}",
        "",
        f"Jogos encontrados: {report['games_found_total']}",
        f"Jogos analisados (linha 2.5 Pinnacle): {report['games_analyzed_total']} ({report['coverage_pct']}% cobertura)",
        f"Creditos usados: {report['credits_used']} / {report['credits_remaining']}",
        "",
        "=== SUGESTOES COM VALUE (Edge >= 5%) ===",
    ]

    if report["suggestions"]:
        for s in report["suggestions"]:
            lines.append(
                f"[{s['league']}] {s['match']} - {s['market']}: edge {s['edge_pct']:+.2f}pp, "
                f"odds~{s['decimal_odds_est']}, {s['units']} unidades"
            )
    else:
        lines.append("Nenhuma sugestao")

    lines.append("")
    lines.append("=== RESUMO ===")
    if report["suggestions"]:
        lines.append(f"{len(report['suggestions'])} sugestao(oes) com value encontrada(s):")
        for s in report["suggestions"]:
            lines.append(f"  - [{s['league']}] {s['match']}: {s['market']} ({s['units']} unidades)")
    else:
        lines.append("Nenhuma sugestao")

    return "\n".join(lines) + "\n"


def main(output_filename: str | None = None) -> None:
    config = load_config()
    api_key = get_api_key(config)
    base_url = config["odds_api"]["base_url"]
    leagues = config["odds_api"]["leagues"]

    report = loop_all_leagues(leagues, api_key, base_url)
    now_brt = datetime.now(BRT)
    text = format_report(report, leagues, now_brt)

    print(text)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = output_filename or f"betting_report_{now_brt.strftime('%Y%m%d')}.txt"
    output_path = REPORTS_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Salvo em: {output_path}")


if __name__ == "__main__":
    main()
