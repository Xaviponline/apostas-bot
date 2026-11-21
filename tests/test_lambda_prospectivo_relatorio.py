import json
from lambda_prospectivo_relatorio import relatorio_prospectivo


def test_no_file_no_api(tmp_path):
    s=relatorio_prospectivo(tmp_path/"absent.jsonl",{"previsoes":[]})
    assert "Sem registos" in s


def test_only_settled_matches_and_multiclass_brier(tmp_path):
    path=tmp_path/"shadow.jsonl"
    probs={"Vitória Casa":.6,"Empate":.2,"Vitória Fora":.2}
    alt={"Vitória Casa":.5,"Empate":.3,"Vitória Fora":.2}
    records=[{"versao":1,"jogo":{"id":42},"original_1x2":probs,"alternativa_1x2":alt},
             {"versao":1,"jogo":{"id":43},"original_1x2":probs,"alternativa_1x2":alt}]
    path.write_text("\n".join(json.dumps(x) for x in records))
    settled={"previsoes":[{"event_id":42,"golos_casa":2,"golos_fora":0,"resultado_binario":1}]}
    s=relatorio_prospectivo(path,settled)
    assert "com resultado oficial associado: 1" in s
    assert "sem resultado: 1" in s
    assert "Brier 1X2" in s
    assert "Subconjunto" in s
