"""Testes offline para diagnostico de ligacao mercado_ref/modelo, zero HTTP."""
import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from main_competicoes import BotPremiumDiarioCompeticoes
from mercado_ref_diagnostico import diagnosticar_snapshot_mercado


ARGS = "2026-10-24 20:30 | Gil Vicente | FC Porto"
TS = datetime(2026, 10, 24, 19, 30, tzinfo=timezone.utc).timestamp()


def snap(**kwargs):
    d = {
        "data_jogo": "2026-10-24", "casa": "Gil Vicente",
        "fora": "Porto", "timestamp_jogo": TS, "estado": "pendente",
        "mercado": "Over 2.5 Golos", "probabilidade": 0.6, "odd_minima": 1.75,
    }
    d.update(kwargs)
    return d


class MercadoRefDiagnosticoTests(unittest.TestCase):
    def test_sem_snapshots_distingue_falta_de_selecao(self):
        txt = diagnosticar_snapshot_mercado(ARGS, [])
        self.assertIn("Snapshots existentes: 0 | na data: 0", txt)
        self.assertIn("Sem snapshots nessa data", txt)
        self.assertIn("Compativeis para mostrar junto da referencia: 0", txt)
        self.assertIn("Zero HTTP / zero creditos", txt)

    def test_snapshots_de_outros_jogos_nao_sao_associados(self):
        x = snap(casa="Casa Pia", fora="Arouca")
        txt = diagnosticar_snapshot_mercado(ARGS, [x])
        self.assertIn("na data: 1", txt)
        self.assertIn("nenhum com as duas equipas", txt)
        self.assertIn("Compativeis para mostrar junto da referencia: 0", txt)

    def test_equipa_e_hora_exatas_liga_sem_inventar_preco(self):
        original = snap(casa="Gil Vicente FC", fora="FC Porto")
        dados = [original]
        anterior = copy.deepcopy(dados)
        txt = diagnosticar_snapshot_mercado(ARGS, dados)
        self.assertIn("Equipas+ordem exatas (qualquer data): 1", txt)
        self.assertIn("Compativeis para mostrar junto da referencia: 1", txt)
        self.assertIn("elegivel", txt)
        self.assertNotIn("EV", txt)
        self.assertEqual(dados, anterior)

    def test_hora_errada(self):
        txt = diagnosticar_snapshot_mercado(ARGS, [
            snap(timestamp_jogo=TS + 60 * 60)
        ])
        self.assertIn("hora fora da tolerancia de 15 min: 1", txt)
        self.assertIn("Compativeis para mostrar junto da referencia: 0", txt)

    def test_estados_e_mercados_sem_suporte(self):
        txt = diagnosticar_snapshot_mercado(ARGS, [
            snap(estado="liquidada"),
            snap(mercado="Ambas Marcam"),
            snap(odd_minima=0),
        ])
        self.assertIn("estado diferente de pendente: 1", txt)
        self.assertIn("mercado nao suportado no comparador: 1", txt)
        self.assertIn("probabilidade/odd minima ausente ou invalida: 1", txt)
        self.assertIn("Compativeis para mostrar junto da referencia: 0", txt)

    def test_ordem_invertida_ou_coincidencia_parcial_nao_associa(self):
        txt = diagnosticar_snapshot_mercado(ARGS, [
            snap(casa="FC Porto", fora="Gil Vicente"),
            snap(casa="Gil Vicente", fora="Braga"),
        ])
        self.assertIn("Ordem invertida na data: 1", txt)
        self.assertIn("Coincidencias parciais (NAO associadas)", txt)
        self.assertIn("Compativeis para mostrar junto da referencia: 0", txt)

    def test_data_alvo_nao_mistura_dia_vizinho(self):
        txt = diagnosticar_snapshot_mercado(ARGS, [
            snap(data_jogo="2026-10-23", timestamp_jogo=TS - 86400),
        ])
        self.assertIn("na data: 0", txt)
        self.assertIn("hora fora da tolerancia de 15 min: 1", txt)

    def test_argumentos_invalidos_sem_operacao(self):
        for args in ("", "abc", "2026-10-24 | Gil Vicente | FC Porto",
                     "2026-10-24 20:30 | FC Porto | Porto",
                     "2026-10-24 25:30 | Gil Vicente | FC Porto",
                     "2026-10-24 20:30 | G | Porto"):
            txt = diagnosticar_snapshot_mercado(args, [snap()])
            self.assertIn("Formato:", txt)

    def test_comando_so_owner_sem_http(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 51
        bot.username = None
        bot.previsoes = type("Store", (), {"dados": {"previsoes": [snap()]}})()
        enviados = []
        bot.enviar_mensagem = lambda chat, txt: enviados.append(txt)
        with patch("requests.sessions.Session.request", side_effect=AssertionError("HTTP proibido")):
            bot.processar_comando(52, "/mercado_ref_diag " + ARGS, user_id=52)
            bot.processar_comando(51, "/mercado_ref_diag " + ARGS, user_id=51)
            bot.processar_comando(51, "/mercado_ref_diag " + ARGS, user_id=51)
        self.assertEqual(len(enviados), 2)
        self.assertIn("Compativeis para mostrar junto da referencia: 1", enviados[0])
        self.assertEqual(enviados[0], enviados[1])


if __name__ == "__main__":
    unittest.main()
