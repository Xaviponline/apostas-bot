import copy
import tempfile
import unittest
from pathlib import Path

from main_competicoes import BotPremiumDiarioCompeticoes
from main_diario import RegistoPrevisoesDiario
from main_sofascore import AJUDA


class V13AuditTests(unittest.TestCase):
    def _previsao(
        self,
        event_id,
        resultado,
        prob=0.68,
        mercado="Over 2.5 Golos",
        ranking=7,
        data="2026-09-26",
        margem=0.05,
        lambda_casa=1.60,
        lambda_fora=1.25,
        ppg_casa=1.80,
        ppg_fora=1.10,
        amostra_local=5,
    ):
        return {
            "chave": f"{event_id}|{mercado}",
            "event_id": event_id,
            "data_jogo": data,
            "timestamp_jogo": 1790449200 + event_id,
            "casa": f"Casa {event_id}",
            "fora": f"Fora {event_id}",
            "liga": "English League One",
            "mercado": mercado,
            "modelo_versao": "V1.2",
            "ranking_modelo": ranking,
            "confianca_modelo": "ALTA" if prob >= 0.68 else "MÉDIA-ALTA",
            "probabilidade": prob,
            "probabilidade_bruta": 0.725 if prob == 0.68 else prob,
            "qualidade": 81,
            "odd_justa": 1.0 / prob,
            "odd_minima": 1.05 / prob,
            "criada_em": "2026-09-26T00:10:00Z",
            "estado": "liquidada",
            "resultado_binario": resultado,
            "diagnostico_modelo": {
                "versao": 1,
                "liga_codigo": "eng.3",
                "limite_mercado": 0.57,
                "margem_limite": margem,
                "lambda_casa": lambda_casa,
                "lambda_fora": lambda_fora,
                "ppg_casa": ppg_casa,
                "ppg_fora": ppg_fora,
                "amostra_casa": 8,
                "amostra_fora": 8,
                "amostra_casa_local": amostra_local,
                "amostra_fora_local": amostra_local,
                "amostra_liga": 35,
            },
        }

    def test_auditoria_v13_e_read_only_e_mostra_telemetria(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            previsoes = [
                self._previsao(1, 0, ranking=6, margem=0.01),
                self._previsao(2, 0, ranking=7, margem=0.01),
                self._previsao(3, 0, ranking=8, margem=0.01),
                self._previsao(4, 0, ranking=9, margem=0.01),
                self._previsao(5, 1, ranking=10, margem=0.01),
                self._previsao(
                    6,
                    1,
                    prob=0.64,
                    mercado="Under 2.5 Golos",
                    ranking=2,
                    margem=0.06,
                    lambda_casa=1.05,
                    lambda_fora=0.95,
                ),
            ]
            reg.dados = {"versao": 1, "previsoes": previsoes}
            antes = copy.deepcopy(reg.dados)

            texto = reg.relatorio_auditoria_v13()

            self.assertIn("AUDITORIA V1.3", texto)
            self.assertIn("Com telemetria detalhada: 6", texto)
            self.assertIn("MARGEM SOBRE THRESHOLD", texto)
            self.assertIn("LAMBDA TOTAL", texto)
            self.assertIn("MAIORES FALHAS DA COORTE", texto)
            self.assertIn("SINAIS EXPLORATÓRIOS", texto)
            self.assertIn("Ranking — #6–10", texto)
            self.assertIn("apenas 1 dia", texto)
            self.assertEqual(reg.dados, antes)

    def test_auditoria_sem_telemetria_nao_inventa_dados(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            p = self._previsao(10, 1)
            p.pop("diagnostico_modelo")
            reg.dados = {"versao": 1, "previsoes": [p]}

            texto = reg.relatorio_auditoria_v13()

            self.assertIn("Com telemetria detalhada: 0", texto)
            self.assertIn("Ainda não existem previsões liquidadas", texto)

    def test_comando_v13_audit_so_responde_ao_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.dados = {
                "versao": 1,
                "previsoes": [self._previsao(20, 1)],
            }

            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.owner_id = 999
            bot.chat_id = -100
            bot.username = "TesteBot"
            bot.previsoes = reg
            mensagens = []
            bot.enviar_mensagem = lambda chat_id, texto: mensagens.append((chat_id, texto))

            bot.processar_comando(-100, "/v13_audit", user_id=999)
            self.assertEqual(len(mensagens), 1)
            self.assertIn("AUDITORIA V1.3", mensagens[0][1])

            mensagens.clear()
            bot.processar_comando(-100, "/v13_audit", user_id=998)
            self.assertEqual(mensagens, [])

    def test_ajuda_documenta_v13_audit(self):
        self.assertIn("/v13_audit", AJUDA)


if __name__ == "__main__":
    unittest.main()
