"""Regressões offline para telemetria de tentativas de CLV oficial."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from clv_observatorio import ObservatorioCLV
from clv_tentativas import DiarioTentativasCLV
from main_sofascore import BotPremiumReal
from previsoes_premium import RegistoPrevisoes


class TentativasCLVTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reg = RegistoPrevisoes(Path(self.tmp.name) / "previsoes.json")
        self.reg.V13_COMERCIAL_START_SNAPSHOT = 1
        self.inicio = datetime.now(timezone.utc) + timedelta(minutes=8)
        self.reg.registar([{
            "jogo": {
                "id": 812, "casa": "Casa", "fora": "Fora",
                "liga": "Teste", "timestamp": self.inicio.timestamp(),
            },
            "mercado": "Under 2.5 Golos",
            "probabilidade": 0.62, "probabilidade_bruta": 0.64,
            "qualidade": 80, "odd_justa": 1.61,
            "odd_minima": 1.70, "odd_real": 1.80,
            "ranking_modelo": 1, "confianca": "MÉDIA",
        }])
        self.p = self.reg.dados["previsoes"][0]
        self.candidata = [{
            "jogo": {"id": 812, "casa": "Casa", "fora": "Fora", "timestamp": self.inicio.timestamp()},
            "mercado": "Under 2.5 Golos", "probabilidade": 0.62,
            "qualidade": 80, "odd_justa": 1.61, "odd_minima": 1.70,
        }]
        self.diario = DiarioTentativasCLV.para_previsoes(self.reg)

    def test_sem_preexistencia_fica_desconhecido_sem_api(self):
        antes = copy.deepcopy(self.reg.dados)
        texto = ObservatorioCLV().relatorio(self.reg, self.inicio + timedelta(minutes=6))
        self.assertIn("Sem telemetria histórica: causa não confirmada", texto)
        self.assertEqual(self.reg.dados, antes)
        self.assertFalse(self.diario.path.exists())

    def test_causa_documentada_e_persistencia_apos_reinicializacao(self):
        anterior = copy.deepcopy(self.reg.dados)
        n = self.diario.registar(
            self.reg, self.candidata, "consulta_concluida",
            [{**self.candidata[0], "_odds_diag": "mercado_nao_disponivel"}],
        )
        self.assertEqual(n, 1)
        self.assertEqual(self.reg.dados, anterior)
        depois = DiarioTentativasCLV.para_previsoes(self.reg).por_snapshot()
        self.assertEqual(depois[1]["ultima"]["motivo"], "mercado_nao_disponivel")
        self.assertIn(
            "Diagnóstico: mercado_nao_disponivel",
            ObservatorioCLV().relatorio(self.reg, self.inicio + timedelta(minutes=6)),
        )

    def test_diagnostico_desconhecido_nao_reproduz_mensagem_api(self):
        self.diario.registar(
            self.reg, self.candidata, "consulta_concluida",
            [{**self.candidata[0], "_odds_diag": "url_com_token=privado"}],
        )
        conteudo = self.diario.path.read_text()
        self.assertNotIn("url_com_token", conteudo)
        self.assertIn("motivo_nao_confirmado", conteudo)

    def test_quota_e_interrupcao_documentadas_sem_consultas(self):
        dados = copy.deepcopy(self.reg.dados)
        self.diario.registar(self.reg, self.candidata, "quota_nao_autorizou")
        self.diario.registar(self.reg, self.candidata, "consulta_interrompida")
        t = self.diario.por_snapshot()[1]
        self.assertEqual(t["tentativas"], 2)
        self.assertEqual(t["ultima"]["motivo"], "consulta_interrompida")
        self.assertEqual(self.reg.dados, dados)

    def test_ficheiro_corrompido_preservado_e_falha_fechada(self):
        self.diario.path.write_text("{invalid")
        with self.assertRaises(RuntimeError):
            self.diario.registar(self.reg, self.candidata, "quota_nao_autorizou")
        self.assertEqual(self.diario.path.read_text(), "{invalid")
        self.assertIn(
            "Diário indisponível; causa por apurar",
            ObservatorioCLV().relatorio(self.reg, self.inicio + timedelta(minutes=6)),
        )

    def _bot(self):
        return BotPremiumReal(
            token="teste", gestor=object(), owner_id=1, chat_id=1,
            buscador=object(), odds=object(), analisador=object(),
            previsoes=self.reg,
        )

    def test_captura_existente_regista_sucesso_sem_pedidos_extra(self):
        bot = self._bot()
        enriquecer = Mock(return_value=[{**self.candidata[0], "odd_real": 1.79}])
        bot._enriquecer_com_cobertura = enriquecer
        self.assertEqual(bot._capturar_clv_pendentes(self.candidata), 1)
        enriquecer.assert_called_once()
        self.assertEqual(self.p["odd_fecho"], 1.79)
        self.assertEqual(self.p["odd_real"], 1.80)
        self.assertEqual(self.diario.por_snapshot()[1]["ultima"]["motivo"], "fecho_persistido")
        self.assertEqual(self.reg.verificar_integridade()["divergentes"], 0)

    def test_quota_bloqueada_cria_apenas_telemetria(self):
        bot = self._bot()
        bot._selecoes_clv_proximas = Mock(return_value=self.candidata)
        bot._quota_permite_captura = Mock(return_value=False)
        bot._capturar_clv_pendentes = Mock()
        antes = copy.deepcopy(self.reg.dados)
        self.assertEqual(bot._capturar_clv_se_devido(), 0)
        bot._capturar_clv_pendentes.assert_not_called()
        self.assertEqual(self.reg.dados, antes)
        self.assertEqual(self.diario.por_snapshot()[1]["ultima"]["motivo"], "quota_nao_autorizou")

    def test_operacao_falhada_documenta_sem_efeito_na_captura(self):
        bot = self._bot()
        bot._selecoes_clv_proximas = Mock(return_value=self.candidata)
        bot._quota_permite_captura = Mock(return_value=True)
        bot._capturar_clv_pendentes = Mock(side_effect=RuntimeError("erro externo"))
        bot._contexto_odds = lambda op: __import__("contextlib").nullcontext()
        self.assertEqual(bot._capturar_clv_se_devido(), 0)
        self.assertEqual(self.diario.por_snapshot()[1]["ultima"]["motivo"], "consulta_interrompida")


if __name__ == "__main__":
    unittest.main()
