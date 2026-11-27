"""Relatório OWNER de análises: entrega segura, retry e consulta sem odds."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from analise_owner_entrega import EntregaAnaliseOwner, resumo_analises_hoje
from main_sofascore import BotPremiumReal
from previsoes_premium import RegistoPrevisoes

PT = ZoneInfo("Europe/Lisbon")


def instante(hora=9, minuto=5):
    return datetime(2026, 11, 27, hora, minuto, tzinfo=PT)


def previsao():
    return {
        "modelo_versao": "V1.2", "data_jogo": "2026-11-27",
        "event_id": 321, "ranking_modelo": 1,
        "timestamp_jogo": instante(19).timestamp(), "estado": "pendente",
        "casa": "Equipa Casa", "fora": "Equipa Fora", "liga": "Liga Exemplo",
        "mercado": "Vitória Casa", "probabilidade": .61, "qualidade": 75,
        "odd_justa": 1.64, "odd_minima": 1.73, "confianca_modelo": "MÉDIA",
        "odd_real": None,
    }


class EntregaOwnerTests(unittest.TestCase):
    def test_entrega_por_partes_e_idempotencia_apos_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entrega.json"
            f = EntregaAnaliseOwner(path)
            self.assertTrue(f.preparar("2026-11-27", "Relatório com análise", lambda v: [v[:18], v[18:]]))
            envio = Mock()
            self.assertEqual(f.enviar_pendentes("2026-11-27", envio, max_partes=1), 1)
            segundo = EntregaAnaliseOwner(path)
            self.assertFalse(segundo.preparar("2026-11-27", "Texto substituído", lambda v: [v]))
            self.assertEqual(segundo.enviar_pendentes("2026-11-27", envio), 1)
            self.assertEqual(segundo.enviar_pendentes("2026-11-27", envio), 0)
            self.assertEqual(envio.call_count, 2)
            self.assertEqual(json.loads(path.read_text())["enviadas"], 2)

    def test_retentativa_apos_falha_telegram_sem_mudar_partes_confirmadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = EntregaAnaliseOwner(Path(tmp) / "entrega.json")
            f.preparar("2026-11-27", "Teste", lambda _: ["Parte 1", "Parte 2"])
            chamadas = []
            def enviar(txt):
                chamadas.append(txt)
                if txt == "Parte 2" and chamadas.count(txt) == 1:
                    raise RuntimeError("Telegram indisponível")
            with self.assertRaises(RuntimeError):
                f.enviar_pendentes("2026-11-27", enviar)
            self.assertEqual(f._ler()["enviadas"], 1)
            self.assertEqual(f.enviar_pendentes("2026-11-27", enviar), 1)
            self.assertEqual(chamadas, ["Parte 1", "Parte 2", "Parte 2"])

    def test_estado_corrompido_falha_fechado(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entrega.json"
            path.write_text("{", encoding="utf-8")
            f = EntregaAnaliseOwner(path)
            with self.assertRaises(RuntimeError):
                f.preparar("2026-11-27", "Novo", lambda x: [x])
            self.assertEqual(path.read_text(), "{")

    def test_resumo_owner_usa_so_snapshots_hoje_e_futuros(self):
        p = previsao()
        resumo = resumo_analises_hoje([p, dict(p), {**p, "data_jogo": "2026-11-26"}], instante(9))
        self.assertIn("Equipa Casa vs Equipa Fora", resumo)
        self.assertIn("61.0%", resumo)
        self.assertIn("Sem odd real confirmada", resumo)
        self.assertIn("1 previsão ainda por começar", resumo)
        self.assertNotIn("2026-11-26", resumo)
        self.assertIn("Sem previsões", resumo_analises_hoje([p], instante(21)))

    def test_integracao_envio_auto_ao_owner_sem_reexecutar_analise(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            bot = BotPremiumReal(token="teste", gestor=object(), owner_id=1, chat_id=1,
                                 buscador=object(), odds=object(), analisador=object(),
                                 previsoes=reg)
            def gerar(tecnica=False):
                reg.dados["previsoes"] = [previsao()]
                return "🎯 ANÁLISE PREMIUM\n⚽ Equipa Casa vs Equipa Fora\n📈 Modelo 61%"
            bot._executar_analise = Mock(side_effect=gerar)
            bot._guardar_lambda_auto = Mock()
            bot._guardar_lambda_resultados_auto = Mock()
            bot.api = Mock(return_value={"message_id": 1})
            self.assertTrue(bot._executar_analise_auto_se_devida(instante(9)))
            self.assertEqual(bot.api.call_count, 1)
            method, payload = bot.api.call_args.args
            self.assertEqual(method, "sendMessage")
            self.assertEqual(payload["chat_id"], 1)
            self.assertIn("Equipa Casa vs Equipa Fora", payload["text"])
            self.assertFalse(bot._executar_analise_auto_se_devida(instante(9, 30)))
            self.assertEqual(bot._executar_analise.call_count, 1)
            self.assertEqual(bot.api.call_count, 1)
            self.assertEqual(json.loads((Path(tmp) / "analise_owner_entrega.json").read_text())["enviadas"], 1)

    def test_falha_entrega_nao_repete_analise_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            bot = BotPremiumReal(token="teste", gestor=object(), owner_id=1, chat_id=1,
                                 buscador=object(), odds=object(), analisador=object(),
                                 previsoes=reg)
            def gerar(tecnica=False):
                reg.dados["previsoes"] = [previsao()]
                return "Análise guardada"
            bot._executar_analise = Mock(side_effect=gerar)
            bot._guardar_lambda_auto = Mock()
            bot._guardar_lambda_resultados_auto = Mock()
            bot.api = Mock(side_effect=[RuntimeError("falhou"), {"message_id": 2}])
            self.assertTrue(bot._executar_analise_auto_se_devida(instante(9)))
            self.assertEqual(bot._entrega_analise_owner._ler()["enviadas"], 0)
            self.assertFalse(bot._executar_analise_auto_se_devida(instante(9, 20)))
            self.assertEqual(bot._entrega_analise_owner._ler()["enviadas"], 1)
            self.assertEqual(bot._executar_analise.call_count, 1)
            self.assertEqual(bot.api.call_count, 2)

    def test_comando_so_owner_e_sem_nova_analise_ou_apis(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.dados["previsoes"] = [previsao()]
            bot = BotPremiumReal(token="teste", gestor=object(), owner_id=1, chat_id=1,
                                 buscador=object(), odds=object(), analisador=object(),
                                 previsoes=reg)
            bot.api = Mock(return_value={"message_id": 3})
            bot._executar_analise = Mock(side_effect=AssertionError("Não gerar"))
            # Comando consulta a data actual; simular entrada de calendário se necessário.
            from unittest.mock import patch
            with patch("analise_owner_entrega.datetime") as dt:
                dt.now.return_value = instante(9)
                dt.fromtimestamp.side_effect = datetime.fromtimestamp
                bot.processar_comando(1, "/analises_hoje", user_id=1)
            self.assertIn("Equipa Casa", bot.api.call_args.args[1]["text"])
            self.assertEqual(bot._executar_analise.call_count, 0)
            bot.api.reset_mock()
            bot.processar_comando(2, "/analises_hoje", user_id=2)
            bot.api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
