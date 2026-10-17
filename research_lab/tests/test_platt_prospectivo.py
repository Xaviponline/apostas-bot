"""Contratos da experiência prospectiva congelada e sem retro-leakage."""
import copy
import unittest
from datetime import datetime, timedelta, timezone

from research_lab.platt_prospectivo import (
    atualizar_protocolo, resumo_protocolo, _assinar,
)

AGORA = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def hist(n=120):
    itens = []
    for i in range(n):
        inicio = AGORA - timedelta(days=22 - i // 6, hours=8)
        itens.append({
            "snapshot_index": i + 1,
            "chave": f"{i}|Under 2.5 Golos",
            "event_id": i + 1, "data_jogo": inicio.date().isoformat(),
            "timestamp_jogo": inicio.timestamp(),
            "criada_em": iso(inicio - timedelta(hours=5)),
            "modelo_versao": "V1.2", "ranking_modelo": i % 20 + 1,
            "mercado": "Under 2.5 Golos",
            "probabilidade": 0.67 + (i % 8) * 0.002,
            "resultado_binario": 1 if i % 3 else 0,
        })
    return itens


def futuro(indice=200, ranking=3, quando=None, criado=None):
    kickoff = quando or (AGORA + timedelta(hours=3))
    return {
        "snapshot_index": indice,
        "chave": f"{indice}|Over 2.5 Golos",
        "event_id": indice, "data_jogo": kickoff.date().isoformat(),
        "timestamp_jogo": kickoff.timestamp(),
        "criada_em": iso(criado or (AGORA - timedelta(minutes=20))),
        "modelo_versao": "V1.2", "ranking_modelo": ranking,
        "mercado": "Over 2.5 Golos",
        "probabilidade": 0.69,
        "resultado_binario": None,
    }


def dados(items):
    return {"records": items, "records_sha256": "dataset-para-teste"}


class PlattProspectivoTests(unittest.TestCase):
    def test_treina_so_passado_e_congela_antes_do_inicio(self):
        previsoes = hist()
        item = futuro()
        previews = copy.deepcopy(previsoes + [item])
        estado = atualizar_protocolo(None, dados(previsoes + [item]), agora=AGORA)
        self.assertEqual(previews, previsoes + [item])
        self.assertEqual(estado["estado"], "CONGELADO")
        self.assertEqual(estado["treino_n"], 120)
        self.assertEqual(len(estado["previsoes"]), 1)
        self.assertIn("200", estado["previsoes"])
        p = estado["previsoes"]["200"]
        self.assertEqual(p["resultado"], None)
        self.assertTrue(0 < p["p_platt"] < 1)
        self.assertEqual(p["p_champion"], 0.69)
        self.assertEqual(p["fingerprint"], _assinar(item))
        self.assertLess(AGORA.timestamp(), p["evento_em"])
        self.assertIn("treino_digest", estado)

    def test_reexportacao_nao_retoca_calibrador_nem_previsao(self):
        itens = hist() + [futuro()]
        estado = atualizar_protocolo(None, dados(itens), agora=AGORA)
        anterior = copy.deepcopy(estado)
        segunda_base = hist(126) + [futuro()]
        de_novo = atualizar_protocolo(
            estado, dados(segunda_base), agora=AGORA + timedelta(hours=1)
        )
        self.assertEqual(estado, anterior)
        self.assertEqual(de_novo["treino_digest"], anterior["treino_digest"])
        self.assertEqual(de_novo["coef"], anterior["coef"])
        self.assertEqual(de_novo["intercept"], anterior["intercept"])
        self.assertEqual(de_novo["previsoes"]["200"]["p_platt"],
                         anterior["previsoes"]["200"]["p_platt"])

    def test_liquidacao_so_apos_jogo_e_nao_recalcula_p(self):
        itens = hist() + [futuro()]
        estado = atualizar_protocolo(None, dados(itens), agora=AGORA)
        p_fixo = estado["previsoes"]["200"]["p_platt"]
        itens[-1]["resultado_binario"] = 0
        antes_do_fim = atualizar_protocolo(
            estado, dados(itens), agora=AGORA + timedelta(hours=4)
        )
        self.assertIsNone(antes_do_fim["previsoes"]["200"]["resultado"])
        depois = atualizar_protocolo(
            antes_do_fim, dados(itens), agora=AGORA + timedelta(hours=7)
        )
        self.assertEqual(depois["previsoes"]["200"]["resultado"], 0)
        self.assertEqual(depois["previsoes"]["200"]["p_platt"], p_fixo)
        itens[-1]["resultado_binario"] = 1
        conflito = atualizar_protocolo(
            depois, dados(itens), agora=AGORA + timedelta(hours=8)
        )
        self.assertEqual(conflito["previsoes"]["200"]["resultado"], 0)
        self.assertIn("snapshot_200_resultado_divergente", conflito["avisos"])

    def test_entrada_tardia_sem_timestamp_ou_rank_mais_baixo_excluidos(self):
        items = hist() + [
            futuro(201, 6),
            futuro(202, 1, quando=AGORA - timedelta(minutes=1)),
            futuro(203, 1, criado=AGORA + timedelta(minutes=1)),
            futuro(204, 2, criado=AGORA + timedelta(hours=10)),
            futuro(205, 4),
        ]
        items[-1]["timestamp_jogo"] = None
        estado = atualizar_protocolo(None, dados(items), agora=AGORA)
        self.assertEqual(estado["previsoes"], {})

    def test_alteracoes_de_dados_criticos_sao_rejeitadas(self):
        items = hist() + [futuro()]
        estado = atualizar_protocolo(None, dados(items), agora=AGORA)
        manipulado = copy.deepcopy(items)
        manipulado[-1]["probabilidade"] = 0.88
        alterado = atualizar_protocolo(
            estado, dados(manipulado), agora=AGORA + timedelta(hours=7)
        )
        self.assertIn("snapshot_200_identidade_divergente", alterado["avisos"])
        self.assertIsNone(alterado["previsoes"]["200"]["resultado"])
        self.assertEqual(alterado["previsoes"]["200"]["p_champion"], 0.69)

    def test_nao_recupera_jogos_passados_com_pseudo_prevista(self):
        passado = futuro(777, 2, quando=AGORA - timedelta(days=1),
                         criado=AGORA - timedelta(days=2))
        passado["resultado_binario"] = 1
        estado = atualizar_protocolo(None, dados(hist() + [passado]), agora=AGORA)
        self.assertNotIn("777", estado["previsoes"])

    def test_treino_insuficiente_falha_fechado(self):
        estado = atualizar_protocolo(None, dados(hist(18) + [futuro()]), agora=AGORA)
        self.assertEqual(estado["estado"], "AGUARDA_TREINO")
        self.assertEqual(estado["previsoes"], {})
        self.assertEqual(resumo_protocolo(estado)["previsoes"], 0)

    def test_criterios_checkpoint_sem_promocao(self):
        estado = atualizar_protocolo(None, dados(hist() + [futuro()]), agora=AGORA)
        resumo = resumo_protocolo(estado)
        self.assertEqual(resumo["estado"], "AVALIAÇÃO_DESCRITIVA")
        self.assertEqual(resumo["alvo"], 100)
        self.assertEqual(resumo["liquidadas"], 0)
        self.assertFalse(resumo["promocao_automatica"])
        self.assertNotIn("conclusao_shadow", resumo)

    def test_estado_corrompido_nunca_reset_automatico(self):
        with self.assertRaises(ValueError):
            atualizar_protocolo({"schema": 1, "estado": "CONGELADO"},
                                dados(hist()), agora=AGORA)
        with self.assertRaises(ValueError):
            atualizar_protocolo(None, {"records": "corrompido"}, agora=AGORA)


if __name__ == "__main__":
    unittest.main()
