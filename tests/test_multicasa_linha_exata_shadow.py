"""Regressoes para diagnostico multicasa SHADOW de linhas exatas."""
from datetime import datetime, timezone

from odds_referencia_shadow import _recolher, _selecao


def test_totais_nao_inferem_linha_35_de_25():
    evento = {
        "home_team": "Grenoble", "away_team": "Stade de Reims",
        "bookmakers": [{
            "key": "betclic",
            "markets": [{
                "key": "totals",
                "last_update": "2026-11-06T10:00:00Z",
                "outcomes": [
                    {"name": "Under", "point": 2.5, "price": 1.85},
                    {"name": "Over", "point": 2.5, "price": 1.88},
                ],
            }],
        }],
    }
    cotacoes, _, _, _ = _recolher(evento, datetime(2026, 11, 6, 11, tzinfo=timezone.utc))
    assert cotacoes["Under 2.5 Golos"]["betclic"] == 1.85
    assert not cotacoes.get("Under 3.5 Golos")


def test_linha_35_exata_e_bookmaker_identificado():
    evento = {
        "home_team": "Grenoble", "away_team": "Stade de Reims",
        "bookmakers": [{
            "key": "betsson",
            "markets": [{
                "key": "totals",
                "last_update": "2026-11-06T10:00:00Z",
                "outcomes": [{"name": "Under", "point": 3.5, "price": 1.62}],
            }],
        }],
    }
    cotacoes, _, _, _ = _recolher(evento, datetime(2026, 11, 6, 11, tzinfo=timezone.utc))
    assert cotacoes["Under 3.5 Golos"]["betsson"] == 1.62
    assert not cotacoes.get("Under 2.5 Golos")
