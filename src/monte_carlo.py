"""Simula placares de futebol via Poisson + Monte Carlo e deriva probabilidades de mercado."""

import json
from collections import Counter
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def simulate_match(home_xg: float, away_xg: float, simulations: int = 10000, seed: int | None = 42) -> dict:
    """Simula placares sorteando home_goals ~ Poisson(home_xg) e away_goals ~ Poisson(away_xg).

    Os dois sorteios sao independentes (premissa padrao de modelos de gols em
    futebol). Na pratica existe uma leve correlacao negativa em placares baixos
    (efeito que modelos tipo Dixon-Coles corrigem), ignorada aqui por simplicidade.
    """
    rng = np.random.default_rng(seed)
    home_goals = rng.poisson(home_xg, size=simulations)
    away_goals = rng.poisson(away_xg, size=simulations)

    counts = Counter(zip(home_goals.tolist(), away_goals.tolist()))
    score_distribution = {
        f"{h}-{a}": round(count / simulations * 100, 2) for (h, a), count in counts.most_common()
    }

    return {
        "home_xg": home_xg,
        "away_xg": away_xg,
        "simulations": simulations,
        "score_distribution": score_distribution,
    }


def derive_probabilities(score_distribution: dict[str, float]) -> dict:
    """Deriva over/under 2.5 e o placar mais provavel a partir da distribuicao simulada.

    So over/under: o split home/away (Opcao A) nunca foi calibrado pra
    reproduzir o 1X2 real, entao probabilidades de 1X2 derivadas da simulacao
    nao sao confiaveis o bastante pra sugerir aposta (ver historico).
    """
    over_2_5_prob = 0.0
    for score, prob in score_distribution.items():
        home_goals, away_goals = (int(x) for x in score.split("-"))
        if home_goals + away_goals > 2.5:
            over_2_5_prob += prob

    most_likely_score = max(score_distribution, key=score_distribution.get)

    return {
        "over_2_5_prob": round(over_2_5_prob, 2),
        "under_2_5_prob": round(100 - over_2_5_prob, 2),
        "most_likely_score": most_likely_score,
    }


def estimate_xg_split(xg_expected: float, home_prob_real: float, away_prob_real: float) -> tuple[float, float]:
    """Divide o xG total em xg_home/xg_away.

    Opcao A (usada aqui): divide proporcionalmente ao favoritismo do h2h
    normalizado (home_prob_real vs away_prob_real, empate descartado do rateio).
    Opcao B seria um split fixo tipo 55/45 baseado na vantagem media de mandante
    do futebol em geral - descartada porque ignora o favoritismo especifico
    deste jogo, que ja temos calculado a partir das odds reais.
    """
    total_directional = home_prob_real + away_prob_real
    home_share = home_prob_real / total_directional
    xg_home = round(xg_expected * home_share, 3)
    xg_away = round(xg_expected - xg_home, 3)
    return xg_home, xg_away


def main(output_filename: str = "sample_monte_carlo.json") -> None:
    with open(DATA_DIR / "sample_confidence.json", "r", encoding="utf-8") as f:
        confidence = json.load(f)

    xg_expected = confidence["xg_expected"]
    probs = confidence["probs_normalized"]
    xg_home, xg_away = estimate_xg_split(xg_expected, probs["home"], probs["away"])

    print(f"{confidence['home_team']} vs {confidence['away_team']}")
    print(f"xg_expected total: {xg_expected} -> xg_home={xg_home}, xg_away={xg_away} (Opcao A: split proporcional ao favoritismo)\n")

    simulation = simulate_match(xg_home, xg_away, simulations=10000)
    derived = derive_probabilities(simulation["score_distribution"])

    print(f"Placar mais provavel simulado: {derived['most_likely_score']}")
    print(f"Over 2.5 simulado: {derived['over_2_5_prob']}%")

    result = {
        "game_id": confidence.get("game_id"),
        "home_team": confidence["home_team"],
        "away_team": confidence["away_team"],
        "xg_expected_total": xg_expected,
        "xg_home": xg_home,
        "xg_away": xg_away,
        "xg_split_method": "opcao_a_proporcional_favoritismo",
        "simulations": simulation["simulations"],
        "most_likely_score": derived["most_likely_score"],
        "over_2_5_prob_simulated": derived["over_2_5_prob"],
        "under_2_5_prob_simulated": derived["under_2_5_prob"],
        "score_distribution": simulation["score_distribution"],
    }

    output_path = DATA_DIR / output_filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nSalvo em: {output_path}")


if __name__ == "__main__":
    main()
