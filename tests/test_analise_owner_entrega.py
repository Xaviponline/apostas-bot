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
        self.assertIn("Equipa Casa × Equipa Fora", resumo)
        self.assertIn("61,0%", resumo)
        self.assertIn("Sem cotação", resumo)
        self.assertIn("1 jogo por começar", resumo)
        self.assertNotIn("2026-11-26", resumo)
        self.assertIn("Sem previsões", resumo_analises_hoje([p], instante(21)))

    def test_analise_matinal_guarda_sem_difundir_as_20_previsoes(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            bot = BotPremiumReal(token="teste", gestor=object(), owner_id=1, chat_id=1,
                                 buscador=object(), odds=object(), analisador=object(),
                                 previsoes=reg)
            def gerar(tecnica=False):
                reg.dados["previsoes"] = [previsao()]
                return "🎯 ANÁLISE PREMIUM"
            bot._executar_analise = Mock(side_effect=gerar)
            bot._guardar_lambda_auto = Mock()
            bot._guardar_lambda_resultados_auto = Mock()
            bot.api = Mock(return_value={"message_id": 1})
            self.assertTrue(bot._executar_analise_auto_se_devida(instante(9)))
            self.assertFalse(bot._executar_analise_auto_se_devida(instante(9, 30)))
            self.assertEqual(bot._executar_analise.call_count, 1)
            bot.api.assert_not_called()
            self.assertEqual(len(reg.dados["previsoes"]), 1)
            self.assertFalse((Path(tmp) / "analise_owner_entrega.json").exists())

    def test_falha_telegram_nao_altera_execucao_matinal(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            bot = BotPremiumReal(token="teste", gestor=object(), owner_id=1, chat_id=1,
                                 buscador=object(), odds=object(), analisador=object(),
                                 previsoes=reg)
            bot._executar_analise = Mock(return_value="Análise guardada")
            bot._guardar_lambda_auto = Mock()
            bot._guardar_lambda_resultados_auto = Mock()
            bot.api = Mock(side_effect=RuntimeError("telegram indisponível"))
            self.assertTrue(bot._executar_analise_auto_se_devida(instante(9)))
            self.assertFalse(bot._executar_analise_auto_se_devida(instante(9, 20)))
            self.assertEqual(bot._executar_analise.call_count, 1)
            bot.api.assert_not_called()

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


    def test_analises_hoje_separadas_por_preco_historico_sem_mudar_snapshot(self):
        import copy
        base = previsao()
        acima = dict(base, event_id=101, ranking_modelo=1,
                     casa="Jong Ajax", fora="Heracles Almelo",
                     mercado="Under 3.5 Golos", probabilidade=.694,
                     odd_real=1.87, odd_minima=1.51, valor_estado="confirmado")
        abaixo = dict(base, event_id=102, ranking_modelo=2,
                      casa="Brest", fora="Paris FC",
                      odd_real=1.31, odd_minima=1.53)
        sem = dict(base, event_id=103, ranking_modelo=3,
                   casa="Vila Nova", fora="Atlético Goianiense",
                   odd_real=None, odd_minima=1.64)
        snapshots = [abaixo, sem, acima]
        original = copy.deepcopy(snapshots)
        texto = resumo_analises_hoje(snapshots, instante(9))
        self.assertIn("3 jogos por começar", texto)
        self.assertIn("🟠 1 acima da mínima (histórico)", texto)
        self.assertIn("🔴 1 sem valor/expiradas", texto)
        self.assertIn("⚪ 1 sem cotação/mínima", texto)
        self.assertIn("Jong Ajax × Heracles Almelo", texto)
        self.assertIn("🎯 Under 3.5 Golos · 69,4%", texto)
        self.assertIn("💶 Odd 1,87 · Mín. 1,51 · 🟠 Acima do mínimo*", texto)
        self.assertIn("EV teórico invulgar", texto)
        self.assertIn("💶 Odd 1,31 · Mín. 1,53 · 🔴 Sem VALUE", texto)
        self.assertIn("💶 Sem cotação · Mín. 1,64 · ⚪ Por verificar", texto)
        self.assertLess(texto.index("Jong Ajax"), texto.index("Brest"))
        self.assertLess(texto.index("Brest"), texto.index("Vila Nova"))
        self.assertNotIn("Odd justa", texto)
        self.assertEqual(snapshots, original)

    def test_analises_nao_confundem_preco_expirado_com_value(self):
        p = previsao()
        p.update(odd_real=1.90, odd_minima=1.60, valor_estado="expirado",
                 odd_mercado_atual=1.40)
        texto = resumo_analises_hoje([p], instante(9))
        self.assertIn("🔴 1 sem valor/expiradas", texto)
        self.assertIn("VALUE expirado", texto)
        self.assertNotIn("🟠 1 acima da mínima", texto)

    def test_analises_podem_mostrar_ranking_13_e_nao_promovem_top5(self):
        p = previsao()
        p.update(ranking_modelo=13, event_id=313, odd_real=1.60,
                 odd_minima=1.70, probabilidade=.618,
                 casa="Caykur Rizespor", fora="Kasimpasa")
        texto = resumo_analises_hoje([p], instante(9))
        self.assertIn("🏅 #13", texto)
        self.assertIn("61,8%", texto)
        self.assertIn("Odd 1,60 · Mín. 1,70 · 🔴 Sem VALUE", texto)
        self.assertNotIn("Ranking Top 5", texto)

    def test_comando_manual_preserva_formato_premium_sem_envios_automáticos(self):
        p = previsao()
        relatorio = resumo_analises_hoje([p], instante(9))
        self.assertIn("ANÁLISES PREMIUM", relatorio)
        self.assertIn("Equipa Casa × Equipa Fora", relatorio)
        self.assertIn("sem novas APIs", relatorio)


if __name__ == "__main__":
    unittest.main()
