from lambda_counterfactual_shadow import relatorio_lambda_shadow, _prob


def test_sem_dados():
    assert "Dias insuficientes" in relatorio_lambda_shadow({"previsoes":[]})


def test_contrafactuais_nao_modificam_entrada():
    rows=[]
    for day in range(1,29):
        for mercado in ("Vitória Casa","Vitória Fora"):
            rows.append({"data_jogo":f"2026-10-{day:02d}","mercado":mercado,
                         "probabilidade":.65,"resultado_binario":int(day%3==0),
                         "diagnostico_modelo":{"lambda_casa":1.8,"lambda_fora":1.2,
                                               "media_liga_casa":1.4,"media_liga_fora":1.1}})
    original=repr(rows)
    out=relatorio_lambda_shadow({"previsoes":rows})
    assert "LAMBDA SHADOW" in out
    assert "Corte" in out
    assert "EXPLORATÓRIO" in out
    assert "sem escolha de variante" in out
    assert "20% médias liga" in out
    assert "diferença λ −30%" in out
    assert "Δ " in out
    assert repr(rows)==original


def test_lambda_variantes_probabilidades_validas():
    r={"lc":2.025,"lf":3.214,"bc":1.4,"bf":1.2,"mercado":"Vitória Fora","p":.65}
    for variante in ("base","shrink20","shrink40","delta15","delta30"):
        assert 0<=_prob(r,variante)<=1
