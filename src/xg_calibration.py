"""Calibra xG total a partir de over/under real, invertendo a CDF de Poisson."""

import math


def poisson_cdf(lam: float, k: int) -> float:
    """P(X <= k) para X ~ Poisson(lam)."""
    return sum(math.exp(-lam) * lam**i / math.factorial(i) for i in range(k + 1))


def invert_poisson_cdf(over_prob: float, threshold: float = 2.5) -> float:
    """Encontra lambda (xG total) tal que P(Poisson(lambda) > threshold) = over_prob.

    Nao existe forma fechada para inverter a CDF de Poisson. P(X <= floor(threshold))
    e estritamente decrescente em lambda, entao ha uma raiz unica - resolvida aqui
    por busca binaria.

    Isso garante consistencia interna com o modelo de Poisson (o xG devolvido,
    se simulado de volta, reproduz o over/under de entrada), mas nao valida o
    modelo em si nem o split home/away - so ancora o TOTAL esperado de gols no
    que o mercado realmente precifica pra essa linha.
    """
    if not (0 < over_prob < 1):
        raise ValueError(f"over_prob deve estar entre 0 e 1 (exclusive), recebido {over_prob}")

    target_under = 1 - over_prob
    k = math.floor(threshold)

    lo, hi = 1e-6, 20.0
    for _ in range(100):
        mid = (lo + hi) / 2
        # poisson_cdf(lambda, k) decresce conforme lambda aumenta
        if poisson_cdf(mid, k) > target_under:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


if __name__ == "__main__":
    over_prob = 0.493
    xg_total = invert_poisson_cdf(over_prob)
    print(f"invert_poisson_cdf(over_prob={over_prob}) = {xg_total}")

    # sanity check: simular de volta com esse lambda deve reproduzir ~over_prob
    k = 2
    p_under = poisson_cdf(xg_total, k)
    print(f"Verificacao: P(under 2.5 | lambda={xg_total}) = {round(p_under, 4)} (esperado ~{round(1 - over_prob, 4)})")
