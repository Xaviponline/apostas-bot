import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from main_sofascore import BotPremiumReal
from previsoes_premium import RegistoPrevisoes


class GestorFake:
    dados = {"ultimo_update": 0}


class OddsFake:
    configurada = True
    nome_fonte = "Fonte Teste"

    def eventos_hoje(self):
        return [
            {
                "id": "900",
                "casa": "Casa",
                "fora": "Fora",
                "data": "2026-09-19T12:00:00Z",
            }
        ]

    def odds_evento(self, event_id):
        if str(event_id) != "900":
            return None
        return {
            "id": "900",
            "casa": "Casa",
            "fora": "Fora",
            "fonte": "Fonte Teste",
            "bookmaker_disponivel": True,
            "mercados": [
                {
                    "name": "Full Time Result",
                    "odds": [
                        {"seleção": "1", "odd": 1.80},
                        {"seleção": "X", "odd": 3.20},
                        {"seleção": "2", "odd": 4.50},
                    ],
                }
            ],
        }


class OddsQuotaFake(OddsFake):
    ultimo_diagnostico_eventos = ""

    def status_conta(self):
        self.ultimo_diagnostico_eventos = "odds_quota_esgotada"
        return {"remaining": 0, "request_count": 250, "request_limit": 250}

    def eventos_hoje(self):
        raise AssertionError("Com quota esgotada não deve consultar fixtures")



class OddsAutoCaptureTests(unittest.TestCase):
    def _snapshot(self, reg, inicio_seg=3600):
        ts = time.time() + inicio_seg
        reg.registar(
            [
                {
                    "jogo": {
                        "id": 900,
                        "casa": "Casa",
                        "fora": "Fora",
                        "liga": "English Premier League",
                        "timestamp": ts,
                    },
                    "mercado": "Vitória Casa",
                    "probabilidade": 0.61,
                    "probabilidade_bruta": 0.63,
                    "qualidade": 75,
                    "odd_justa": 1.64,
                    "odd_minima": 1.72,
                }
            ]
        )
        return reg.dados["previsoes"][0]

    def _bot(self, reg):
        return BotPremiumReal(
            token="teste",
            gestor=GestorFake(),
            owner_id=1,
            chat_id=1,
            buscador=object(),
            odds=OddsFake(),
            analisador=object(),
            previsoes=reg,
        )

    def test_captura_primeira_odd_antes_do_jogo(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg)
            bot = self._bot(reg)

            capturadas = bot._capturar_odds_pendentes()

            self.assertEqual(capturadas, 1)
            self.assertEqual(snapshot["odd_real"], 1.80)
            self.assertEqual(snapshot["odds_fonte"], "Fonte Teste")
            self.assertAlmostEqual(snapshot["ev_real"], (0.61 * 1.80) - 1, places=6)

            # Uma segunda ronda não substitui nem volta a contar a odd congelada.
            self.assertEqual(bot._capturar_odds_pendentes(), 0)
            self.assertEqual(snapshot["odd_real"], 1.80)


    def test_captura_clv_automatica_para_entrada_de_valor_perto_do_jogo(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=8 * 60)
            bot = self._bot(reg)

            # Primeiro congela a odd de entrada; 1.80 >= mínima 1.72.
            self.assertEqual(bot._capturar_odds_pendentes(), 1)
            self.assertEqual(snapshot["valor_estado"], "confirmado")
            self.assertNotIn("odd_fecho", snapshot)

            fechos = bot._capturar_clv_pendentes()

            self.assertEqual(fechos, 1)
            self.assertEqual(snapshot["odd_fecho"], 1.80)
            self.assertAlmostEqual(snapshot["clv_odds"], 0.0, places=6)
            # Nunca substitui a odd inicial congelada.
            self.assertEqual(snapshot["odd_real"], 1.80)

            # Depois de existir fecho, deixa de voltar a consultar esta entrada.
            self.assertEqual(bot._capturar_clv_pendentes(), 0)

    def test_clv_automatico_inicia_nos_ultimos_30_minutos(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=25 * 60)
            snapshot["odd_real"] = 1.80
            snapshot["valor_estado"] = "confirmado"
            snapshot["odd_valor_confirmado"] = 1.80
            bot = self._bot(reg)

            self.assertEqual(len(bot._selecoes_clv_proximas()), 1)

    def test_clv_automatico_ignora_jogo_a_mais_de_30_minutos(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=31 * 60)
            snapshot["odd_real"] = 1.80
            snapshot["valor_estado"] = "confirmado"
            snapshot["odd_valor_confirmado"] = 1.80
            bot = self._bot(reg)

            self.assertEqual(bot._selecoes_clv_proximas(), [])

    def test_clv_automatico_ignora_previsao_sem_valor_confirmado(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=8 * 60)
            snapshot["odd_real"] = 1.60
            snapshot["valor_estado"] = "sem_valor"
            bot = self._bot(reg)

            self.assertEqual(bot._selecoes_clv_proximas(), [])
            self.assertEqual(bot._capturar_clv_se_devido(), 0)
            self.assertNotIn("odd_fecho", snapshot)

    def test_suspende_captura_automatica_quando_quota_esgotada(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            self._snapshot(reg)
            bot = BotPremiumReal(
                token="teste",
                gestor=GestorFake(),
                owner_id=1,
                chat_id=1,
                buscador=object(),
                odds=OddsQuotaFake(),
                analisador=object(),
                previsoes=reg,
            )

            bot._proxima_captura_odds = 0
            self.assertEqual(bot._capturar_odds_se_devida(), 0)

    def test_clv_automatico_respeita_quota_esgotada(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=8 * 60)
            snapshot["odd_real"] = 1.80
            snapshot["valor_estado"] = "confirmado"
            snapshot["odd_valor_confirmado"] = 1.80
            bot = BotPremiumReal(
                token="teste",
                gestor=GestorFake(),
                owner_id=1,
                chat_id=1,
                buscador=object(),
                odds=OddsQuotaFake(),
                analisador=object(),
                previsoes=reg,
            )

            bot._proxima_captura_clv = 0
            self.assertEqual(bot._capturar_clv_se_devido(), 0)
            self.assertNotIn("odd_fecho", snapshot)

    def test_ignora_jogo_fora_da_janela_de_seis_horas(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=(7 * 60 * 60))
            bot = self._bot(reg)

            self.assertEqual(bot._capturar_odds_pendentes(), 0)
            self.assertNotIn("odd_real", snapshot)

    def test_ignora_jogo_que_ja_comecou(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            # Criamos manualmente um snapshot passado para testar a seleção automática.
            snapshot = {
                "chave": "900|Vitória Casa",
                "event_id": 900,
                "data_jogo": time.strftime("%Y-%m-%d", time.localtime()),
                "timestamp_jogo": time.time() - 60,
                "casa": "Casa",
                "fora": "Fora",
                "liga": "English Premier League",
                "mercado": "Vitória Casa",
                "probabilidade": 0.61,
                "qualidade": 75,
                "odd_justa": 1.64,
                "odd_minima": 1.72,
                "estado": "pendente",
            }
            reg.dados = {"versao": 1, "previsoes": [snapshot]}
            bot = self._bot(reg)

            self.assertEqual(bot._capturar_odds_pendentes(), 0)
            self.assertNotIn("odd_real", snapshot)


    def test_clv_tardio_captura_separada_sem_mudar_odd_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=8 * 60)
            bot = self._bot(reg)
            self.assertEqual(bot._capturar_odds_pendentes(), 1)
            self.assertEqual(bot._capturar_clv_pendentes(), 1)
            hash_antes = snapshot["snapshot_hash"]

            # Uma segunda consulta pode encontrar um preço diferente.
            atual = [{
                "jogo": {"id": 900},
                "mercado": "Vitória Casa",
                "odd_real": 1.65,
            }]
            self.assertEqual(reg.registar_fecho_tardio(atual), 1)
            self.assertEqual(snapshot["odd_fecho_tardio"], 1.65)
            self.assertAlmostEqual(snapshot["clv_odds_tardio"], 1.80 / 1.65 - 1, places=6)
            self.assertEqual(snapshot["odd_fecho"], 1.80)
            self.assertEqual(snapshot["odd_real"], 1.80)
            self.assertEqual(snapshot["odd_valor_confirmado"], 1.80)
            self.assertEqual(snapshot["snapshot_hash"], hash_antes)
            self.assertEqual(reg.verificar_integridade()["divergentes"], 0)
            self.assertEqual(reg.metricas_clv()["media"], 0)
            self.assertGreater(reg.metricas_clv_tardio()["media"], 0)
            self.assertEqual(reg.registar_fecho_tardio(atual), 0)

    def test_clv_tardio_nao_captura_antes_da_janela_ou_apos_inicio(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=12 * 60)
            snapshot["odd_real"] = 1.80
            snapshot["odd_valor_confirmado"] = 1.80
            snapshot["odd_fecho"] = 1.80
            bot = self._bot(reg)
            self.assertEqual(bot._selecoes_clv_proximas(tardio=True), [])
            selecao = [{"jogo": {"id": 900}, "mercado": "Vitória Casa", "odd_real": 1.70}]
            self.assertEqual(reg.registar_fecho_tardio(selecao), 0)
            depois_inicio = datetime.now(timezone.utc) + timedelta(minutes=13)
            self.assertEqual(reg.registar_fecho_tardio(selecao, agora=depois_inicio), 0)
            self.assertNotIn("odd_fecho_tardio", snapshot)

    def test_clv_tardio_automatico_recolhe_apenas_apos_primeiro_fecho(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=8 * 60)
            bot = self._bot(reg)
            self.assertEqual(bot._selecoes_clv_proximas(tardio=True), [])
            self.assertEqual(bot._capturar_odds_pendentes(), 1)
            self.assertEqual(bot._capturar_clv_pendentes(), 1)
            self.assertEqual(len(bot._selecoes_clv_proximas(tardio=True)), 1)
            self.assertEqual(bot._capturar_clv_tardio_se_devido(), 1)
            self.assertEqual(snapshot["odd_fecho_tardio"], 1.80)
            self.assertEqual(bot._capturar_clv_tardio_se_devido(), 0)

    def test_clv_tardio_respeita_quota_esgotada(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=8 * 60)
            snapshot["odd_real"] = 1.80
            snapshot["odd_valor_confirmado"] = 1.80
            snapshot["odd_fecho"] = 1.80
            bot = BotPremiumReal(
                token="teste", gestor=GestorFake(), owner_id=1, chat_id=1,
                buscador=object(), odds=OddsQuotaFake(), analisador=object(), previsoes=reg,
            )
            self.assertEqual(bot._capturar_clv_tardio_se_devido(), 0)
            self.assertNotIn("odd_fecho_tardio", snapshot)


if __name__ == "__main__":
    unittest.main()
