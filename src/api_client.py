"""Cliente minimo para a The Odds API (https://the-odds-api.com/)."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
CONFIG_EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "config.example.yaml"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Le config.yaml; se nao existir (ex: checkout limpo no CI, onde o arquivo
    com a chave real esta no .gitignore), cai pro config.example.yaml - as
    configuracoes nao-secretas (ligas, markets, etc) sao as mesmas, so o
    api_key e placeholder e precisa vir da env var ODDS_API_KEY (ver get_api_key).
    """
    if not path.exists():
        path = CONFIG_EXAMPLE_PATH
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_api_key(config: dict) -> str:
    """Preferencia: env var ODDS_API_KEY (usada no GitHub Actions via secret) > config.yaml local."""
    api_key = os.environ.get("ODDS_API_KEY") or config["odds_api"]["api_key"]
    if not api_key or api_key == "seu_api_key_aqui":
        raise ValueError(
            "api_key nao configurada. Defina a env var ODDS_API_KEY ou edite "
            f"{CONFIG_PATH} com sua chave real da The Odds API."
        )
    return api_key


def fetch_sports(api_key: str, base_url: str) -> tuple[list[dict], requests.Response]:
    """Busca a lista de esportes/ligas disponiveis. Endpoint gratuito (nao consome credits)."""
    response = requests.get(f"{base_url}/sports", params={"apiKey": api_key}, timeout=10)
    response.raise_for_status()
    return response.json(), response


def matched_leagues(sports: list[dict], leagues: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separa as leagues configuradas entre encontradas e nao encontradas na resposta da API."""
    available_keys = {sport["key"] for sport in sports}
    found = [league for league in leagues if league["key"] in available_keys]
    missing = [league for league in leagues if league["key"] not in available_keys]
    return found, missing


def filter_games_within_days(games: list[dict], days: int = 2, now: datetime | None = None) -> list[dict]:
    """Mantem jogos cujo commence_time (UTC) caia entre agora e agora + days dias."""
    now = now or datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    return [
        game
        for game in games
        if now <= datetime.fromisoformat(game["commence_time"].replace("Z", "+00:00")) <= cutoff
    ]


def fetch_games_with_odds(
    sport_key: str,
    api_key: str,
    base_url: str,
    markets: list[str] = ["h2h", "totals"],
    regions: str = "eu",
    odds_format: str = "decimal",
    days: int = 2,
) -> tuple[list[dict], requests.Response]:
    """Busca jogos dos proximos `days` dias com odds para os markets informados.

    Bookmakers: nenhum filtro aplicado, retorna todos os disponiveis na regiao.
    """
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": ",".join(markets),
        "oddsFormat": odds_format,
        "dateFormat": "iso",
    }
    response = requests.get(f"{base_url}/sports/{sport_key}/odds", params=params, timeout=10)
    response.raise_for_status()
    games = filter_games_within_days(response.json(), days=days)
    return games, response


def save_sample_response(games: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(games, f, indent=2, ensure_ascii=False)


def main() -> None:
    config = load_config()
    api_key = get_api_key(config)
    base_url = config["odds_api"]["base_url"]
    leagues = config["odds_api"]["leagues"]

    sports, response = fetch_sports(api_key, base_url)
    found, missing = matched_leagues(sports, leagues)
    remaining = response.headers.get("x-requests-remaining")

    if missing:
        print("Nao encontradas:")
        for league in missing:
            print(f"  [X] {league['name']} ({league['key']})")
        return

    print("API Key validada")
    print("Ligas encontradas:")
    for league in found:
        print(f"  - {league['name']} ({league['key']})")
    print(f"Creditos restantes: {remaining}\n")

    print("--- Teste de odds: Premier League (soccer_epl) ---")
    games, odds_response = fetch_games_with_odds("soccer_epl", api_key, base_url)
    print(f"Jogos hoje/amanha com odds: {len(games)}")
    if games:
        print("Estrutura do primeiro jogo:")
        print(json.dumps(games[0], indent=2, ensure_ascii=False))
    print(f"Custo desta chamada (credits): {odds_response.headers.get('x-requests-last')}")
    print(f"Creditos restantes apos a chamada: {odds_response.headers.get('x-requests-remaining')}")

    sample_path = DATA_DIR / "sample_odds_response.json"
    if games:
        save_sample_response(games, sample_path)
    else:
        # Nenhum jogo hoje/amanha no momento (ex.: entre rodadas). Salva a
        # resposta completa (proximos jogos, sem filtro de data) so para ter
        # uma amostra util da estrutura de dados.
        print("Sem jogos hoje/amanha agora - salvando resposta completa (sem filtro de data) como amostra.")
        save_sample_response(odds_response.json(), sample_path)
    print(f"Amostra salva em: {sample_path}")


if __name__ == "__main__":
    main()
