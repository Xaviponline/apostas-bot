import json
import tempfile
import unittest
from pathlib import Path
from lambda_resultados_shadow import guardar_resultados


class TestLambdaResultadosShadow(unittest.TestCase):
    def test_identidade_captura_conflito_e_deduplicacao(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/"snap.jsonl", Path(tmp)/"res.jsonl"
            jogo = dict(id=1, casa_id=2, fora_id=3, timestamp=1800000000)
            reg = dict(versao=1, chave="a", jogo=jogo, liga_codigo="eng.1",
                       capturado_em_utc="2026-01-01T00:00:00+00:00")
            tardio = dict(reg, chave="b", capturado_em_utc="2030-01-01T00:00:00+00:00")
            errado = dict(reg, chave="c", jogo=dict(jogo, fora_id=9))
            src.write_text("\n".join(json.dumps(x) for x in (reg,tardio,errado))+"\n")
            final = dict(jogo, final_regulamentar_shadow=True, golos_casa=2, golos_fora=1)
            self.assertEqual(guardar_resultados(src,dst,{"eng.1":[dict(final, final_regulamentar_shadow=False)]}),0)
            self.assertEqual(guardar_resultados(src,dst,{"eng.1":[final,dict(final,golos_casa=3)]}),0)
            self.assertEqual(guardar_resultados(src,dst,{"eng.1":[final]}),1)
            self.assertEqual(guardar_resultados(src,dst,{"eng.1":[final]}),0)
            self.assertEqual(json.loads(dst.read_text())["chave"],"a")


if __name__ == "__main__":
    unittest.main()
