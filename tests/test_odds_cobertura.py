"""Testes offline do observatorio da cobertura por liga/mercado."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from main_competicoes import BotPremiumDiarioCompeticoes
from main_sofascore import BotPremiumReal
from odds_cobertura import ObservatorioCobertura
from previsoes_premium import RegistoPrevisoes


class CoberturaOddsTests(unittest.TestCase):
    def _selecao(self, eid, mercado="Under 2.5 Golos", liga="Liga Teste",
                 diag=None, odd=None, horas=3):
        selecionada = {
            "jogo": {
                "id": eid,
                "casa": "Casa",
                "fora": "Fora",
                "liga": liga,
                "timestamp": (datetime.now(timezone.utc) + timedelta(hours=horas)).timestamp(),
            },
            "mercado": mercado,
        }
        if diag is not None:
            selecionada["_odds_diag"] = diag
        if odd is not None:
            selecionada["odd_real"] = odd
        return selecionada

    def test_mesmo_evento_nao_infla_amostra_e_sucesso_persiste(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "odds_cobertura.json"
            observatorio = ObservatorioCobertura(path)
            erro = self._selecao(101, diag="odds_http_404")
            sucesso = self._selecao(101, odd=1.90)
            self.assertEqual(observatorio.registar([erro, erro]), 1)
            self.assertEqual(observatorio.registar([sucesso]), 0)
            self.assertEqual(observatorio.registar([erro]), 0)
            dados = ObservatorioCobertura(path).calcular()
            self.assertEqual(dados["observacoes_unicas"], 1)
            grupo = dados["grupos"][0]
            self.assertEqual(grupo["confirmados"], 1)
            self.assertEqual(grupo["incertos"], 0)
            self.assertEqual(grupo["estado"], "OBSERVADA")
            self.assertEqual(len(json.loads(path.read_text())["observacoes"]), 1)

    def test_cobertura_parcial_nao_se_chama_totalmente_observada(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = ObservatorioCobertura(Path(tmp) / "dados.json")
            obs.registar([
                self._selecao(1, odd=2.20),
                self._selecao(2, diag="mercado_nao_disponivel"),
                self._selecao(3, diag="fixture_omitido_no_lote"),
                self._selecao(4, diag="mercado_nao_disponivel"),
            ])
            grupo = obs.calcular()["grupos"][0]
            self.assertEqual((grupo["confirmados"], grupo["eventos"]), (1, 4))
            self.assertEqual(grupo["estado"], "PARCIAL OBSERVADA")

    def test_distingue_odd_ja_observada_da_ultima_observacao_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dados.json"
            obs = ObservatorioCobertura(path)
            p = self._selecao(100, odd=2.20)
            obs.registar([p])
            obs.registar([self._selecao(100, diag="mercado_nao_disponivel")])
            dados = obs.calcular()
            grupo = dados["grupos"][0]
            self.assertEqual(grupo["confirmados"], 1)
            self.assertEqual(grupo["ultima_com_odd"], 0)
            self.assertEqual(grupo["ultima_sem_odd"], 1)
            self.assertEqual(grupo["sem_observacao_local"], 0)
            texto = obs.relatorio()
            self.assertIn("1/1 com odd", texto)
            self.assertIn("0 com odd / 1 sem cotacao", texto)
            self.assertIn("nao comprova odd atual", texto)

    def test_snapshot_importado_nao_e_falsa_reconfirmacao(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = ObservatorioCobertura(Path(tmp) / "dados.json")
            snapshot = {
                "event_id": 200, "liga": "Liga Teste",
                "data_jogo": datetime.now(timezone.utc).date().isoformat(),
                "mercado": "Vitória Casa", "odd_real": 1.95,
                "odds_fonte": "OddsPapi / Betano PT",
            }
            grupo = obs.calcular([snapshot])["grupos"][0]
            self.assertEqual(grupo["confirmados"], 1)
            self.assertEqual(grupo["sem_observacao_local"], 1)
            self.assertEqual(grupo["ultima_com_odd"], 0)
            self.assertFalse(obs.path.exists())

    def test_http_400_404_e_fixtures_omitidos_sao_inconclusivos(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = ObservatorioCobertura(Path(tmp) / "observacoes.json")
            obs.registar([
                self._selecao(1, diag="odds_http_400"),
                self._selecao(2, diag="odds_http_404"),
                self._selecao(3, diag="fixture_omitido_no_lote"),
                self._selecao(4, diag="evento_nao_encontrado"),
            ])
            grupo = obs.calcular()["grupos"][0]
            self.assertEqual(grupo["incertos"], 4)
            self.assertEqual(grupo["betano_sem_odds"], 0)
            self.assertEqual(grupo["mercado_indisponivel"], 0)
            self.assertEqual(grupo["confirmados"], 0)
            self.assertFalse(grupo["candidata_revisao"])

    def test_separa_betano_sem_odds_de_mercado_ausente(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = ObservatorioCobertura(Path(tmp) / "dados.json")
            obs.registar([
                self._selecao(1, diag="betano_sem_odds_no_evento"),
                self._selecao(2, diag="mercado_nao_disponivel"),
                self._selecao(3, diag="linha_ou_selecao_nao_disponivel"),
            ])
            grupo = obs.calcular()["grupos"][0]
            self.assertEqual(grupo["betano_sem_odds"], 1)
            self.assertEqual(grupo["mercado_indisponivel"], 2)
            self.assertEqual(grupo["incertos"], 0)

    def test_somente_sinais_de_muitas_datas_podem_sugerir_revisao_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = ObservatorioCobertura(Path(tmp) / "dados.json")
            selecoes = [
                self._selecao(i, horas=(i % 3 + 1) * 24,
                              diag="mercado_nao_disponivel")
                for i in range(12)
            ]
            obs.registar(selecoes)
            grupo = obs.calcular()["grupos"][0]
            self.assertGreaterEqual(grupo["dias"], 3)
            self.assertEqual(grupo["confirmados"], 0)
            self.assertTrue(grupo["candidata_revisao"])
            self.assertIn("sem bloqueio", obs.relatorio())

    def test_snapshots_apenas_odd_real_confirmada_pela_oddspapi(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = ObservatorioCobertura(Path(tmp) / "dados.json")
            snapshots = [
                {"event_id": 99, "liga": "Liga Teste",
                 "data_jogo": datetime.now(timezone.utc).date().isoformat(),
                 "mercado": "Vitória Casa", "odd_real": 1.95,
                 "odds_fonte": "OddsPapi / Betano PT"},
                {"event_id": 99, "liga": "Liga Teste",
                 "data_jogo": datetime.now(timezone.utc).date().isoformat(),
                 "mercado": "Vitória Casa", "odd_real": 1.95,
                 "odds_fonte": "OddsPapi / Betano PT"},
                {"event_id": 100, "liga": "Liga Teste",
                 "data_jogo": datetime.now(timezone.utc).date().isoformat(),
                 "mercado": "Vitória Casa", "odd_real": 1.95,
                 "odds_fonte": "Outra fonte"},
            ]
            resultado = obs.calcular(snapshots)
            self.assertEqual(resultado["observacoes_unicas"], 1)
            self.assertEqual(resultado["confirmacoes_historicas"], 1)
            self.assertEqual(resultado["grupos"][0]["confirmados"], 1)
            self.assertFalse(obs.path.exists())  # consulta so leitura

    def test_ficheiro_corrompido_nao_e_sobrescrito(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dados.json"
            path.write_text("nao e json")
            obs = ObservatorioCobertura(path)
            with self.assertRaises(ValueError):
                obs.registar([self._selecao(1, odd=1.8)])
            self.assertEqual(path.read_text(), "nao e json")

    def test_enriquecimento_nao_faz_requisicoes_adicionais_e_preserva_saida(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            class OddsFake:
                provider = "oddspapi"
            bot = BotPremiumReal(
                token="teste", gestor=object(), owner_id=1, chat_id=1,
                buscador=object(), odds=OddsFake(), analisador=object(),
                previsoes=reg,
            )
            entrada = [self._selecao(5)]
            saida = [self._selecao(5, odd=1.75)]
            with patch("main_sofascore.AuditoriaOdds") as auditor:
                auditor.return_value.enriquecer.return_value = saida
                resultado = bot._enriquecer_com_cobertura(entrada)
                auditor.return_value.enriquecer.assert_called_once_with(entrada)
            self.assertIs(resultado, saida)
            self.assertEqual(len(reg.dados["previsoes"]), 0)
            self.assertEqual(ObservatorioCobertura(Path(tmp) / "odds_cobertura.json").calcular()["observacoes_unicas"], 1)

    def test_comando_admin_read_only_sem_odds_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            bot = object.__new__(BotPremiumDiarioCompeticoes)
            bot.previsoes = reg
            bot.owner_id = 1
            bot.chat_id = 1
            bot.username = None
            respostas = []
            bot.enviar_mensagem = lambda chat, msg: respostas.append((chat, msg))
            bot.processar_comando(1, "/odds_cobertura", user_id=1)
            self.assertEqual(len(respostas), 1)
            self.assertIn("COBERTURA ODDS", respostas[0][1])
            self.assertIn("Nao exclui ligas", respostas[0][1])
            self.assertFalse((Path(tmp) / "odds_cobertura.json").exists())


if __name__ == "__main__":
    unittest.main()
