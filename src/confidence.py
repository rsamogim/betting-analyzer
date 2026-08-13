"""Correlaciona h2h e totals, calcula confianca e calibra xG total."""

import json
from pathlib import Path

from xg_calibration import invert_poisson_cdf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def normalize_h2h(analysis: dict) -> dict:
    """Remove o overround (vig) do mercado h2h dividindo cada prob pela soma das 3."""
    total = analysis["home_prob"] + analysis["draw_prob"] + analysis["away_prob"]
    return {
        "home_prob_real": round(analysis["home_prob"] / total * 100, 1),
        "draw_prob_real": round(analysis["draw_prob"] / total * 100, 1),
        "away_prob_real": round(analysis["away_prob"] / total * 100, 1),
    }


def normalize_totals(analysis: dict) -> dict | None:
    """Remove o overround do mercado totals dividindo cada prob pela soma over+under.

    Usa a soma over+under (nao home+draw+away) porque sao mercados distintos,
    cada um com seu proprio overround.
    """
    over, under = analysis.get("over_2_5_prob"), analysis.get("under_2_5_prob")
    if over is None or under is None:
        return None
    total = over + under
    return {
        "over_2_5_prob_real": round(over / total * 100, 1),
        "under_2_5_prob_real": round(under / total * 100, 1),
    }


def calculate_confidence(game_analysis: dict) -> dict:
    """Correlaciona o favoritismo do h2h (normalizado) com a tendencia over/under.

    Regra:
      - "forte": home e o favorito claro (prob > empate E > visitante) E over 2.5 > 50%
      - "fraca": qualquer outro caso
    Confianca fixa: 75% se forte, 65% se fraca.
    """
    h2h_real = normalize_h2h(game_analysis)
    totals_real = normalize_totals(game_analysis)

    home = h2h_real["home_prob_real"]
    draw = h2h_real["draw_prob_real"]
    away = h2h_real["away_prob_real"]
    over = totals_real["over_2_5_prob_real"] if totals_real else None

    home_is_favorite = home > max(draw, away)
    over_high = over is not None and over > 50

    if home_is_favorite and over_high:
        correlation = "forte"
        confidence = 75.0
    else:
        correlation = "fraca"
        confidence = 65.0

    return {
        "correlation": correlation,
        "confidence_pct": confidence,
        "home_prob_real": home,
        "draw_prob_real": draw,
        "away_prob_real": away,
        "over_2_5_prob_real": over,
        "under_2_5_prob_real": totals_real["under_2_5_prob_real"] if totals_real else None,
    }


def xg_from_over_prob(over_2_5_prob_real_pct: float | None) -> float | None:
    """xG total calibrado: inverte a CDF de Poisson pra achar o lambda cuja
    P(X > 2.5) reproduz over_2_5_prob_real (ja normalizado, sem vig).

    Substitui a heuristica linear anterior (over_prob * 3.0), que subestimava
    gols de forma severa - confirmado quando o Monte Carlo simulado com ela
    deu BTTS/over muito abaixo do implicito nas odds reais. Ainda e uma
    estimativa (depende do goals ~ Poisson e de uma unica linha, 2.5), nao
    xG "de verdade" validado contra resultados reais.
    """
    if over_2_5_prob_real_pct is None:
        return None
    return invert_poisson_cdf(over_2_5_prob_real_pct / 100)


def main() -> None:
    analysis_path = DATA_DIR / "sample_analysis.json"
    with open(analysis_path, "r", encoding="utf-8") as f:
        game_analysis = json.load(f)

    confidence = calculate_confidence(game_analysis)
    xg_expected = xg_from_over_prob(confidence["over_2_5_prob_real"])

    result = {
        "game_id": game_analysis.get("game_id"),
        "home_team": game_analysis.get("home_team"),
        "away_team": game_analysis.get("away_team"),
        "confidence_pct": confidence["confidence_pct"],
        "correlation": confidence["correlation"],
        "xg_expected": xg_expected,
        "xg_confidence": "media (calibrado via Poisson, ainda nao validado contra resultados reais)",
        "recommendation": "Validar xg_expected com dados reais (ex: Understat) antes de usar em decisoes.",
        "probs_normalized": {
            "home": confidence["home_prob_real"],
            "draw": confidence["draw_prob_real"],
            "away": confidence["away_prob_real"],
            "over_2_5": confidence["over_2_5_prob_real"],
            "under_2_5": confidence["under_2_5_prob_real"],
        },
    }

    print(f"{game_analysis['home_team']} vs {game_analysis['away_team']}")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    output_path = DATA_DIR / "sample_confidence.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nSalvo em: {output_path}")


if __name__ == "__main__":
    main()
