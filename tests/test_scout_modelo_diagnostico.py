from datetime import datetime, timezone
from scout_modelo_diagnostico import relatorio_scout_modelo


def test_exclusao_por_liga_top5_sem_http():
    p = {
        "data_jogo": "2026-11-20", "estado": "pendente",
        "timestamp_jogo": datetime(2026, 11, 20, 19, 45, tzinfo=timezone.utc).timestamp(),
        "ranking_modelo": 1, "qualidade": 80, "probabilidade": .7,
        "odd_minima": 1.6, "mercado": "Vitória Fora",
        "liga": "Belgian Pro League", "casa": "Cercle", "fora": "Westerlo",
        "event_id": 123,
    }
    msg = relatorio_scout_modelo({"previsoes": [p]}, datetime(2026,11,20,10,tzinfo=timezone.utc))
    assert "liga_sem_mapeamento" in msg
    assert "Westerlo" in msg
    assert "não configurado" in msg


def test_calibracao_sem_inventar_dados():
    p = {"data_jogo": "2026-11-19", "estado": "ganhou",
         "probabilidade": .7, "resultado_binario": 1,
         "golos_casa": 1, "golos_fora": 2,
         "diagnostico_modelo": {"lambda_casa": 1.1, "lambda_fora": 1.8}}
    msg = relatorio_scout_modelo({"previsoes": [p]}, datetime(2026,11,20,10,tzinfo=timezone.utc))
    assert "Brier 0.090" in msg
    assert "Golos previstos 2.90" in msg
    assert "Reais 3.00" in msg
