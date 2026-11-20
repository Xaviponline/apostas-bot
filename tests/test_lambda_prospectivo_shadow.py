import json
from lambda_prospectivo_shadow import criar_registo, guardar_registos


def _analise(jid):
    return {
        "jogo":{"id":jid,"timestamp":1795219200,"casa_id":11,"fora_id":22},
        "liga_codigo":"eng.1",
        "lambda_casa":2.025,"lambda_fora":3.214,
        "media_liga_casa":1.4,"media_liga_fora":1.2,
        "probabilidades":{"Vitória Casa":.2,"Empate":.2,"Vitória Fora":.6},
    }


def test_capture_all_and_deduplicate(tmp_path):
    path=tmp_path/"shadow.jsonl"
    analises=[_analise(1),_analise(2)]
    assert guardar_registos(path,analises)==2
    assert guardar_registos(path,analises)==0
    rows=[json.loads(x) for x in path.read_text().splitlines()]
    assert len(rows)==2
    assert all(x["resultado"] is None for x in rows)
    assert all(sum(x["alternativa_1x2"].values()) > .999999 for x in rows)
    assert rows[0]["alternativa_1x2"]["Vitória Fora"] != rows[0]["original_1x2"]["Vitória Fora"]


def test_shadow_does_not_modify_original():
    a=_analise(3)
    antes=repr(a)
    r=criar_registo(a)
    assert repr(a)==antes
    assert r["chave"]
    assert "Empate" in r["alternativa_1x2"]
