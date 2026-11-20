from calibracao_mercados_shadow import relatorio_calibracao_mercados


def test_mercados_sem_contaminacao_temporal():
    rows = []
    for d in range(1, 11):
        for i in range(10):
            rows.append({"data_jogo":f"2026-11-{d:02d}","mercado":"Vitória Fora",
                         "probabilidade":.65,"resultado_binario":int(i<4)})
    out=relatorio_calibracao_mercados({"previsoes":rows})
    assert "Vitória Fora" in out
    assert "Corte comum" in out
    assert "IC95%" in out
    assert "Sem simulação: amostra insuficiente" in out


def test_sem_dados():
    assert "Dias insuficientes" in relatorio_calibracao_mercados({"previsoes":[]})
