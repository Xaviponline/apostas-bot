from calibracao_shadow import relatorio_calibracao_shadow


def test_segmentacao_e_corte_temporal():
    rows = []
    for day in range(1, 9):
        for i in range(20):
            rows.append({"data_jogo": f"2026-11-{day:02d}",
                         "probabilidade": .7,
                         "resultado_binario": int(i < 12),
                         "mercado": "Ambas Marcam"})
    report = relatorio_calibracao_shadow({"previsoes": rows})
    assert "n=160" in report
    assert "previsto 70.0%" in report
    assert "real 60.0%" in report
    assert "Validação temporal" in report
    assert "simulado" in report


def test_nao_inclui_pendentes_e_prob_invalidas():
    rows = [
        {"data_jogo": "2026-11-20", "probabilidade": .9, "resultado_binario": None},
        {"data_jogo": "2026-11-19", "probabilidade": 2, "resultado_binario": 1},
    ]
    report = relatorio_calibracao_shadow({"previsoes": rows})
    assert "n=0" in report
    assert "Sem dados suficientes" in report
