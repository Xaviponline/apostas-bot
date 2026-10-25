"""Testes sintéticos offline. Não abrem /data nem fazem pedidos de rede."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.auditoria_calibracao_offline import (
    bin_prob, metrics, normalize_records, run, market_evidence,
)

class AuditoriaOfflineTests(unittest.TestCase):
    def test_faixas_fronteiras(self):
        self.assertEqual([bin_prob(p) for p in (.50,.549,.55,.60,.65,.70,.81,.49)],
                         ["50–55%","50–55%","55–60%","60–65%","65–70%","70%+","70%+","Abaixo de 50%"])

    def test_metricas_pendentes_excluidos_e_brier(self):
        r, errors = normalize_records([
            {"casa":"A","fora":"B","liga":"L","mercado":"Under 2.5 Golos","probabilidade":.60,"resultado_binario":1},
            {"casa":"C","fora":"D","liga":"L","mercado":"Over 2.5 Golos","probabilidade":.80,"resultado_binario":0},
            {"casa":"E","fora":"F","liga":"L","mercado":"Ambas Marcam","probabilidade":.90,"resultado_binario":None},
        ])
        m=metrics(r)
        self.assertEqual((m["previsoes_total"],m["liquidadas_validas"],m["ganhas"],m["perdidas"]),(3,2,1,1))
        self.assertEqual(m["taxa_acerto_pct"],50.0)
        self.assertEqual(m["prob_prevista_media_pct"],70.0)
        self.assertEqual(m["acertos_esperados"],1.4)
        self.assertEqual(m["brier"],.4)
        self.assertFalse(errors)

    def test_nao_altera_fonte_e_nunca_sobrescreve_saida(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/"previsoes.json"
            original={"previsoes":[
                {"data_jogo":"2026-10-20","casa":"A","fora":"B","liga":"Liga A","mercado":"Under 2.5 Golos",
                 "probabilidade":.65,"odd_real":1.90,"resultado_binario":1},
                {"data_jogo":"2026-10-21","casa":"C","fora":"D","liga":"Liga B","mercado":"Vitória Casa",
                 "probabilidade":.55,"odd_real":2.10,"resultado_binario":0},
            ]}
            src.write_text(json.dumps(original),encoding="utf-8")
            antes=hashlib.sha256(src.read_bytes()).hexdigest()
            out=root/"resultados"
            s=run(src,out)
            self.assertEqual(s["liquidadas_validas"],2)
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),antes)
            with (out/"calibracao_faixas.csv").open(encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),6)
            self.assertEqual(next(r for r in rows if r["faixa"]=="55–60%")["perdidas"],"1")
            with (out/"previsoes_todas.csv").open(encoding="utf-8-sig",newline="") as f:
                cases=list(csv.DictReader(f))
            self.assertEqual(cases[0]["odd_inicial"],"1.9")
            self.assertEqual(cases[1]["resultado"],"PERDEU")
            with self.assertRaises(FileExistsError):
                run(src,out)

    def test_mercados_apenas_evidencia_existente(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            trace=root/"odds_rastreio.jsonl"
            trace.write_text(json.dumps({
                "fonte":"OddsPapi / Betano PT","mercado_id_fonte":"1010",
                "mercado_nome_fonte":"Over Under Full Time","periodo_fonte":"fulltime",
                "linha_fonte":2.5,"mercado_modelo":"Under 2.5 Golos",
                "diagnostico":"","jogo":"A vs B"
            }),encoding="utf-8")
            diary=root/"clv_tentativas.json"
            diary.write_text(json.dumps({"eventos":[
                {"snapshot":408,"resultado":"sem_fecho","motivo":"mercado_nao_disponivel",
                 "mercados_contexto":{"total":2,"compativeis":0,"sem_catalogo":1}},
            ]}),encoding="utf-8")
            markets, failures=market_evidence(trace,diary)
            self.assertEqual(markets[0]["nome_mercado_fonte"],"Over Under Full Time")
            self.assertEqual(failures[0]["motivo_guardado"],"mercado_nao_disponivel")
            self.assertIn("sem_catalogo=1",failures[0]["observacao"])

if __name__=="__main__":
    unittest.main()
