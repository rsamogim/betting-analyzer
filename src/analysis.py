"""Decodifica odds em probabilidades implicitas (analise reversa do mercado)."""

import json
from pathlib import Path

from xg_calibration import invert_poisson_cdf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def find_bookmaker(game: dict, key: str = "pinnacle") -> dict | None:
    return next((bm for bm in game.get("bookmakers", []) if bm["key"] == key), None)


def market_prices(bookmaker: dict, market_key: str, point: float | None = None) -> dict[str, float]:
    """Mapeia nome do outcome -> price para um market, opcionalmente filtrado por point."""
    market = next((m for m in bookmaker.get("markets", []) if m["key"] == market_key), None)
    if market is None:
        return {}
    return {
        o["name"]: o["price"]
        for o in market["outcomes"]
        if point is None or o.get("point") == point
    }


def implied_prob(price: float | None) -> float | None:
    """prob = 1 / odds (decimal). Nao remove o overround (vig) da casa."""
    return 1 / price if price else None


def pct(prob: float | None) -> float | None:
    return round(prob * 100, 1) if prob is not None else None


def analyze_implied_odds(game_with_odds: dict) -> dict:
    """Extrai odds da Pinnacle (h2h e totals 2.5) e calcula probabilidades implicitas.

    As probabilidades sao brutas (1/odds), sem remover a margem da casa (vig),
    entao home_prob + draw_prob + away_prob tende a somar > 100%.
    """
    pinnacle = find_bookmaker(game_with_odds, "pinnacle")
    if pinnacle is None:
        raise ValueError(f"Pinnacle nao encontrada no jogo {game_with_odds.get('id')}")

    home_team = game_with_odds["home_team"]
    away_team = game_with_odds["away_team"]

    h2h = market_prices(pinnacle, "h2h")
    totals_2_5 = market_prices(pinnacle, "totals", point=2.5)

    home_prob = implied_prob(h2h.get(home_team))
    draw_prob = implied_prob(h2h.get("Draw"))
    away_prob = implied_prob(h2h.get(away_team))
    over_prob = implied_prob(totals_2_5.get("Over"))
    under_prob = implied_prob(totals_2_5.get("Under"))

    # xG total calibrado invertendo a CDF de Poisson: acha o lambda cuja
    # P(X > 2.5) reproduz over_prob. Consistente com o modelo por construcao,
    # mas ainda ancorado na prob. bruta (com vig) da Pinnacle.
    xg_expected = invert_poisson_cdf(over_prob) if over_prob is not None else None

    return {
        "game_id": game_with_odds.get("id"),
        "home_team": home_team,
        "away_team": away_team,
        "home_prob": pct(home_prob),
        "draw_prob": pct(draw_prob),
        "away_prob": pct(away_prob),
        "over_2_5_prob": pct(over_prob),
        "under_2_5_prob": pct(under_prob),
        "xg_expected": xg_expected,
    }


def _pick_test_game(games: list[dict]) -> dict:
    """Prefere um jogo com linha de totals em 2.5 na Pinnacle, pra demonstrar o caso cheio."""
    for game in games:
        pinnacle = find_bookmaker(game, "pinnacle")
        if pinnacle and market_prices(pinnacle, "totals", point=2.5):
            return game
    return games[0]


def main() -> None:
    sample_path = DATA_DIR / "sample_odds_response.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        games = json.load(f)

    game = _pick_test_game(games)
    print(f"Jogo escolhido: {game['home_team']} vs {game['away_team']}")

    analysis = analyze_implied_odds(game)
    print(json.dumps(analysis, indent=2, ensure_ascii=False))

    output_path = DATA_DIR / "sample_analysis.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"\nAnalise salva em: {output_path}")


if __name__ == "__main__":
    main()
