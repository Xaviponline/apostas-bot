"""Testes de frescura historica passiva, sem consultas externas."""
from odds_rastreio import RastreioOdds


def test_frescura_shadow_antiga():
    item = {
        "observado_em": "2026-11-13T09:00:00+00:00",
        "odds_atualizada_em": "2026-11-11T18:59:44.371Z",
    }
    assert RastreioOdds._frescura_shadow(item).startswith("antiga no registo")


def test_frescura_shadow_recente():
    item = {
        "observado_em": "2026-10-16T19:00:00+00:00",
        "odds_atualizada_em": "2026-10-16T16:18:16.142Z",
    }
    assert RastreioOdds._frescura_shadow(item).startswith("dentro do limiar")


def test_frescura_shadow_sem_data_e_futuro():
    base = {"observado_em": "2026-11-19T09:00:00Z"}
    assert RastreioOdds._frescura_shadow(base) == "sem data de atualizacao comprovada"
    assert RastreioOdds._frescura_shadow({
        **base, "odds_atualizada_em": "2026-11-19T09:06:00Z"
    }) == "data futura no fornecedor"


def test_frescura_shadow_sem_observacao():
    assert RastreioOdds._frescura_shadow({
        "odds_atualizada_em": "2026-11-19T08:00:00Z"
    }).startswith("indeterminada")
