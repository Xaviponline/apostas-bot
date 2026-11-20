from vitorias_diagnostico_shadow import relatorio_vitorias_shadow


def test_segmentos_e_dados_em_falta():
    rows = [
        {"mercado":"Vitória Fora","probabilidade":.65,"resultado_binario":0,"liga":"Belgian Pro League",
         "diagnostico_modelo":{"amostra_casa":2,"amostra_fora":7,"lambda_casa":1.0,"lambda_fora":3.0}},
        {"mercado":"Vitória Casa","probabilidade":.65,"resultado_binario":1,"liga":"French Ligue 2"},
        {"mercado":"Under 3.5 Golos","probabilidade":.7,"resultado_binario":1},
    ]
    out=relatorio_vitorias_shadow({"previsoes":rows})
    assert "Liquidadas: 2" in out
    assert "pequena (<6)" in out
    assert ">=1.5" in out
    assert "sem diagnóstico: 1" in out
    assert "Sem lambdas: 1" in out


def test_vazio():
    assert "Sem seleções suficientes" in relatorio_vitorias_shadow({"previsoes":[]})
