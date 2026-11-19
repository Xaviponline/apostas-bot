"""Regression tests for Portugal daylight-saving time in odds trace."""
from odds_rastreio import RastreioOdds


def test_october_portugal_summer_time():
    item = {
        "observado_em": "2026-10-16T18:20:00+00:00",
        "odds_atualizada_em": "2026-10-16T16:18:16.142Z",
    }
    assert RastreioOdds._hora_portugal(item["observado_em"]) == "16/10/2026 19:20"
    assert RastreioOdds._hora_portugal(item["odds_atualizada_em"]) == "16/10/2026 17:18"
    assert RastreioOdds._frescura_shadow(item) == "dentro do limiar no registo (2.0 h)"


def test_november_portugal_winter_time():
    item = {
        "observado_em": "2026-11-13T09:00:00+00:00",
        "odds_atualizada_em": "2026-11-11T18:59:44.371Z",
    }
    assert RastreioOdds._hora_portugal(item["observado_em"]) == "13/11/2026 09:00"
    assert RastreioOdds._frescura_shadow(item) == "antiga no registo (38.0 h)"
