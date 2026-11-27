"""Testes da auditoria read-only de confiança das 20 previsões V1.2/dia."""
import copy
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from auditoria_confianca_v12_shadow import (
    _faixa, _resumo, _primeiras_vinte_por_dia,
    relatorio_confianca_modelo,
)
from main_competicoes import BotPremiumDiarioCompeticoes

PT = ZoneInfo("Europe/Lisbon")


def previsao(i=1, dia="2026-11-27", nivel="ALTA", prob=.7, resultado=1, versao="V1.2"):
    ts = datetime.fromisoformat(dia).replace(tzinfo=PT) + timedelta(hours=19)
    return {
        "modelo_versao": versao, "event_id": 51000 + i,
        "data_jogo": dia, "timestamp_jogo": ts.timestamp(),
        "ranking_modelo": i,
        "mercado": "Under 2.5 Golos", "confianca_modelo": nivel,
        "probabilidade": prob,
        "estado": ("ganhou" if resultado == 1 else "perdeu" if resultado == 0 else "pendente"),
        "resultado_binario": resultado,
    }


class AuditoriaConfiancaTests(unittest.TestCase):
    def test_taxa_previsto_brier_e_gap_por_grupo(self):
        dados = {"previsoes": [
            previsao(1, nivel="ALTA", prob=.7, resultado=1),
            previsao(2, nivel="ALTA", prob=.7, resultado=0),
            previsao(3, nivel="MÉDIA-ALTA", prob=.65, resultado=1),
            previsao(4, nivel="MÉDIA", prob=.6, resultado=1),
            previsao(5, nivel="BAIXA", prob=.55, resultado=0),
            previsao(6, nivel="BAIXA", prob=.55, resultado=None),
        ]}
        original = copy.deepcopy(dados)
        texto = relatorio_confianca_modelo(dados)
        self.assertIn("Seleções: 6 | Liquidadas válidas: 5 | Pendentes: 1", texto)
        self.assertIn("🟢 ALTA · n=2 | ✅ 1 | Prev. 70,0% → Real 50,0% | Δ -20,0pp | Brier 0,2900", texto)
        self.assertIn("🟡 MÉDIA-ALTA · n=1", texto)
        self.assertIn("🟠 MÉDIA · n=1", texto)
        self.assertIn("🔴 BAIXA · n=1", texto)
        self.assertIn("Por liquidar: 1", texto)
        self.assertIn("Amostra reduzida", texto)
        self.assertEqual(dados, original)

    def test_segura_inconsistencias_nao_inclui_versao_v13_ou_ranking21(self):
        rows = [previsao(i, nivel="ALTA", prob=.7, resultado=1) for i in range(1,21)]
        rows.append(previsao(21, nivel="BAIXA", prob=.55, resultado=0))
        rows.append(previsao(1, nivel="BAIXA", prob=.55, resultado=0))
        rows.append(previsao(4, versao="V1.3", nivel="BAIXA", prob=.55, resultado=0))
        self.assertEqual(len(_primeiras_vinte_por_dia(rows)), 20)
        t = relatorio_confianca_modelo({"previsoes": rows})
        self.assertIn("Seleções: 20 | Liquidadas válidas: 20", t)
        self.assertNotIn("🔴 BAIXA", t)

    def test_exclusao_de_bool_nan_malformado_ou_resultado_incoerente(self):
        r = [
            previsao(1, nivel="MÉDIA", prob=.65, resultado=1),
            previsao(2, nivel="MÉDIA", prob=.65, resultado=True),
            previsao(3, nivel="MÉDIA", prob=.65, resultado=0),
            previsao(4, nivel="MÉDIA", prob=.65, resultado=1),
        ]
        r[2]["estado"] = "ganhou"
        r[3]["probabilidade"] = float("nan")
        # NaN nem passa pela seleção inicial dos primeiros vinte.
        t = relatorio_confianca_modelo({"previsoes": r})
        self.assertIn("Seleções: 3 | Liquidadas válidas: 1", t)
        self.assertIn("Inconsistências: 2", t)

    def test_normalizacao_rotulos_sem_agregar_media_alta_com_media(self):
        self.assertEqual(_faixa("  média-alta "), "MÉDIA-ALTA")
        self.assertEqual(_faixa("MEDIA"), "MÉDIA")
        self.assertEqual(_faixa("MÉDIA"), "MÉDIA")
        self.assertEqual(_faixa("BAIXA"), "BAIXA")
        self.assertEqual(_faixa("outro"), "DESCONHECIDA")
        self.assertEqual(_faixa(None), "DESCONHECIDA")

    def test_grupos_suficientes_exibem_ic_e_nao_promovem_modelo(self):
        amostras = [(.7, 1, f"2026-11-{1+i//3:02d}") for i in range(30)]
        m = _resumo(amostras)
        self.assertEqual(m["n"], 30)
        self.assertEqual(m["dias"], 10)
        self.assertAlmostEqual(m["real"], 1.0)
        data = {"previsoes": [
            previsao(i%3+1, dia=f"2026-11-{i//3+1:02d}",
                     nivel="ALTA", prob=.7, resultado=1)
            for i in range(30)
        ]}
        # A mesma posição/ranking em dias diferentes é uma nova previsão legítima.
        for i,p in enumerate(data["previsoes"]):
            p["event_id"] = 51000 + i
        txt = relatorio_confianca_modelo(data)
        self.assertIn("IC95% acerto", txt)
        self.assertIn("nem valida V1.3", txt)
        self.assertNotIn("promoção aprovada", txt)

    def test_historico_vazio_e_data_invalida(self):
        self.assertIn("Ainda sem previsões válidas", relatorio_confianca_modelo({"previsoes":[]}))
        p = previsao()
        p["data_jogo"] = "2026-99-99"
        self.assertIn("Seleções: 0", relatorio_confianca_modelo({"previsoes":[p]}))
        with self.assertRaises(ValueError):
            relatorio_confianca_modelo({"previsoes":{}})

    def test_comando_so_owner_sem_apis_ou_alteracoes(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 43
        bot.username = None
        dados = {"previsoes":[previsao()]}
        anterior = copy.deepcopy(dados)
        bot.previsoes = SimpleNamespace(dados=dados)
        bot.enviar_mensagem = Mock()
        bot.processar_comando(43, "/confianca_modelo", user_id=43)
        bot.enviar_mensagem.assert_called_once()
        self.assertIn("CONFIANÇA DO MODELO", bot.enviar_mensagem.call_args.args[1])
        self.assertEqual(dados, anterior)
        bot.enviar_mensagem.reset_mock()
        bot.processar_comando(44, "/confianca_modelo", user_id=44)
        bot.processar_comando(43, "/confianca_modelo", user_id=55)
        bot.enviar_mensagem.assert_not_called()


if __name__ == "__main__":
    unittest.main()
