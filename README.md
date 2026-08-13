# betting-analyzer

Pipeline que busca odds da [The Odds API](https://the-odds-api.com/), decodifica probabilidades implícitas, simula placares via Poisson + Monte Carlo e sugere apostas com value (Over/Under 2.5) comparando o simulado contra o mercado.

## Relatório diário

- Roda **09:00 BRT** todo dia via GitHub Actions (`.github/workflows/daily-betting-report.yml`, cron `0 12 * * *` em UTC).
- Cobre as 6 ligas configuradas em `config.yaml`: Premier League, LaLiga, Serie A, Bundesliga, Ligue 1, Brasileirão Série A.
- Arquivo gerado: `reports/betting_report_YYYYMMDD.txt` (um por dia, commitado de volta no repo pelo próprio workflow).
- Pode ser disparado manualmente na aba **Actions -> Daily Betting Report -> Run workflow**.

Rodar localmente:

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # depois edite com sua api_key real
python src/daily_report.py
```

## Setup do GitHub Actions

O workflow precisa da chave da The Odds API como *secret* do repositório (nunca commitada — `config.yaml` está no `.gitignore` e o script lê a env var `ODDS_API_KEY` em CI, caindo para `config.yaml` local fora do CI).

No repositório GitHub, em **Settings -> Secrets and variables -> Actions -> New repository secret**, ou via `gh` CLI:

```bash
gh secret set ODDS_API_KEY
```

- **`ODDS_API_KEY`** (obrigatório) — sua chave da The Odds API.
- **`EMAIL_PASSWORD`** (reservado, não usado ainda) — só necessário se/quando for adicionado envio do relatório por e-mail (Gmail app password). O workflow atual não envia e-mail, só commita o `.txt` em `reports/`.

## Limitações conhecidas

- **Só analisa jogos onde a Pinnacle oferece a linha de totals exatamente em 2.5.** Em torno de 40-70% dos jogos encontrados ficam de fora da análise por não terem essa linha específica (a calibração de xG via `invert_poisson_cdf` depende dela). "Jogos encontrados" vs "jogos analisados" no relatório mostra essa cobertura.
- **Janela de 7 dias pode gerar jogos duplicados entre relatórios consecutivos.** Um jogo que começa em 6 dias aparece no relatório de hoje e continua aparecendo nos relatórios dos próximos dias até acontecer — ainda não há deduplicação entre execuções.
- **Sugestões de aposta cobrem só Over/Under 2.5.** 1X2 e BTTS foram removidos do pipeline de sugestão (ver histórico) por não terem calibração confiável ainda.
- **`xg_expected` é uma estimativa calibrada a partir das odds (Poisson invertido), não xG real validado contra resultados** — nunca foi comparado contra dados de xG de fontes como Understat.
