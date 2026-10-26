"""Testes sintéticos de regressao. Zero chamadas HTTP."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.auditoria_funil_value_offline import classify, official_entry, process, run


def sample(i, **kwargs):
    p={"modelo_versao":"V1.2","ranking_modelo":(i%5)+1,"probabilidade":0.65,
       "casa": "A", "fora":"B", "liga":"Teste", "mercado":"Under 3.5 Golos",
       "data_jogo":"2026-10-25","odd_minima":1.6154,"criada_em":"2026-10-25T10:00:00Z",
       "odd_real":None,"valor_estado":"sem_odd"}
    p.update(kwargs)
    return p


class TestValue(unittest.TestCase):
    def test_sem_odd(self):
        self.assertEqual(classify(sample(1))[0], "sem_odd_guardada")

    def test_quote_abaixo_minimo(self):
        self.assertEqual(classify(sample(1,odd_real=1.45))[0],"odds_guardadas_abaixo_minimo")

    def test_quote_acima_minimo_entrada_fallback(self):
        p=sample(1,odd_real=1.70)
        self.assertEqual(official_entry(p),1.70)
        self.assertEqual(classify(p)[0],"VALUE_confirmado")

    def test_confirmado_guarda_entrada_mesmo_se_estado_expirado(self):
        p=sample(1,odd_valor_confirmado=1.66,odd_mercado_atual=1.45,valor_estado="expirado")
        self.assertEqual(official_entry(p),1.66)
        self.assertEqual(classify(p)[0],"VALUE_confirmado")

    def test_nao_inventa_valor_quando_falta_limiar(self):
        self.assertEqual(classify(sample(1,odd_minima=None,odd_real=1.8))[0],"limiar_ausente")

    def test_captura_anomalia(self):
        p=sample(1,odd_minima=1.60,odd_mercado_atual=1.75)
        self.assertEqual(classify(p)[0],"inconsistencia_metadados_ou_tempos")

    def test_filtro_top5_snapshot_e_versao(self):
        data=[sample(i) for i in range(1,210)]
        data[206]=sample(207,ranking_modelo=6,odd_real=1.8)
        data[207]=sample(208,ranking_modelo=1,odd_real=1.8)
        data[208]=sample(209,ranking_modelo=2,modelo_versao="V1.1",odd_real=1.8)
        found=process(data)
        self.assertEqual([r["snapshot"] for r in found],[208])
        self.assertEqual(found[0]["coorte_v13"],"SIM")

    def test_coorte_primeiras_confirmacoes_e_fonte_intacta(self):
        data=[sample(i) for i in range(1,207)]
        data.extend([sample(207,odd_valor_confirmado=1.75,valor_confirmado_em="2026-10-25T14:00:00Z"),
                     sample(208,odd_valor_confirmado=1.65,valor_confirmado_em="2026-10-25T12:00:00Z")])
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"input.json"
            src.write_text(json.dumps({"previsoes":data}),encoding="utf-8")
            before=hashlib.sha256(src.read_bytes()).hexdigest()
            out=Path(d)/"output"
            result=run(src,out)
            self.assertEqual(result["value_confirmadas_elegiveis"],2)
            self.assertEqual(before,hashlib.sha256(src.read_bytes()).hexdigest())
            self.assertTrue((out/"top5_funil_detalhe.csv").exists())
            with self.assertRaises(ValueError):run(src,out)


if __name__ == "__main__":
    unittest.main()
