from modelo_snapshot_shadow import diagnostico_snapshot


def test_modelo_snapshot_historico_com_diagnostico():
    data = {"previsoes": [{
        "casa": "Cercle Brugge KSV", "fora": "KVC Westerlo",
        "data_jogo": "2026-11-20", "mercado": "Vitória Fora",
        "probabilidade": 0.592, "probabilidade_bruta": 0.615,
        "qualidade": 80, "odd_real": 3.35, "ev_real": 0.984,
        "diagnostico_modelo": {
            "lambda_casa": 0.8, "lambda_fora": 1.8,
            "amostra_casa": 8, "amostra_fora": 8,
            "amostra_liga": 35,
        },
    }]}
    msg = diagnostico_snapshot(data, "Westerlo")
    assert "Cercle Brugge" in msg
    assert "59,2%" in msg
    assert "0,800" in msg
    assert "35" in msg


def test_modelo_snapshot_sem_diagnostico_nao_inventa():
    msg = diagnostico_snapshot({"previsoes": [{
        "casa": "Cercle Brugge", "fora": "Westerlo",
        "probabilidade": 0.59,
    }]}, "Cercle")
    assert "Sem diagnóstico histórico" in msg
    assert "não registado" in msg


def test_modelo_snapshot_sem_resultados():
    assert "Sem snapshots" in diagnostico_snapshot({"previsoes": []}, "Cercle")
    assert "mínimo 3" in diagnostico_snapshot({"previsoes": []}, "Ce")
