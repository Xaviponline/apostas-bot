"""Provas offline de diagnostico passivo de mercado ausente em CLV."""
import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clv_tentativas import DiarioTentativasCLV
from clv_observatorio import ObservatorioCLV
from odds_auditoria import AuditoriaOdds
from previsoes_premium import RegistoPrevisoes


class FonteSemMercado:
    configurada = True
    nome_fonte = "Fonte mock"

    def __init__(self, mercados):
        self.mercados = mercados
        self.consultas = 0

    def eventos_hoje(self):
        return [{"id": "evento-falso", "casa": "Casa", "fora": "Fora"}]

    def odds_evento(self, event_id):
        self.consultas += 1
        return {"id": event_id, "casa": "Casa", "fora": "Fora",
                "mercados": self.mercados, "fonte": self.nome_fonte}


class MercadoContextoShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reg = RegistoPrevisoes(Path(self.tmp.name) / "previsoes.json")
        self.reg.V13_COMERCIAL_START_SNAPSHOT = 1
        self.inicio = datetime.now(timezone.utc) + timedelta(minutes=8)
        self.selecao = {
            "jogo": {"id": 814, "casa": "Casa", "fora": "Fora",
                     "liga": "Liga Teste", "timestamp": self.inicio.timestamp()},
            "mercado": "Under 2.5 Golos", "probabilidade": .66,
            "probabilidade_bruta": .66, "qualidade": 75,
            "odd_justa": 1.515, "odd_minima": 1.70,
            "odd_real": 1.80, "ranking_modelo": 2,
        }
        self.reg.registar([self.selecao])
        self.diario = DiarioTentativasCLV.para_previsoes(self.reg)

    def test_extrai_contexto_sem_api_extra_e_preserva_original(self):
        mercados = [
            {"id": "1010", "name": "Market 1010", "odds": [
                {"seleção": "Under", "odd": 1.8}
            ]},
            {"id": "42", "name": "Full Time Result", "odds": [
                {"seleção": "1", "odd": 2.1}
            ]},
        ]
        fonte = FonteSemMercado(mercados)
        original = copy.deepcopy(self.selecao)
        saida = AuditoriaOdds(fonte).enriquecer([self.selecao])
        self.assertEqual(fonte.consultas, 1)
        self.assertEqual(self.selecao, original)
        self.assertEqual(saida[0]["_odds_diag"], "mercado_nao_disponivel")
        self.assertEqual(
            saida[0]["_odds_contexto_mercados"],
            {"total": 2, "compativeis": 0, "sem_catalogo": 1},
        )

    def test_relatorio_mostra_novos_campos_sem_alterar_coorte(self):
        antes = copy.deepcopy(self.reg.dados)
        enriquecida = {
            **self.selecao,
            "_odds_diag": "mercado_nao_disponivel",
            "_odds_contexto_mercados": {
                "total": 5, "compativeis": 0, "sem_catalogo": 2
            },
        }
        self.diario.registar(
            self.reg, [self.selecao], "consulta_concluida", [enriquecida],
        )
        diag = self.diario.por_snapshot()[1]["ultima"]
        self.assertEqual(diag["mercados_contexto"]["sem_catalogo"], 2)
        rel = ObservatorioCLV().relatorio(
            self.reg, agora=self.inicio + timedelta(minutes=6)
        )
        self.assertIn("Mercados recebidos: 5 | compatíveis: 0 | sem catálogo: 2", rel)
        self.assertEqual(self.reg.dados, antes)
        self.assertIsNone(self.reg.dados["previsoes"][0].get("odd_fecho"))

    def test_historicos_antigos_sem_contexto_nao_sao_inferidos(self):
        self.diario.registar(
            self.reg, [self.selecao], "consulta_concluida",
            [{**self.selecao, "_odds_diag": "mercado_nao_disponivel"}],
        )
        rel = ObservatorioCLV().relatorio(
            self.reg, agora=self.inicio + timedelta(minutes=6)
        )
        self.assertIn("Diagnóstico: mercado_nao_disponivel", rel)
        self.assertNotIn("Mercados recebidos:", rel)

    def test_contexto_desconhecido_nao_persiste_conteudo_arbitrario(self):
        self.diario.registar(
            self.reg, [self.selecao], "consulta_concluida", [{
                **self.selecao,
                "_odds_diag": "mercado_nao_disponivel",
                "_odds_contexto_mercados": {
                    "total": "chave_secreta",
                    "compativeis": 0,
                    "sem_catalogo": 0,
                }
            }],
        )
        rel = self.diario.path.read_text(encoding="utf-8")
        self.assertNotIn("chave_secreta", rel)
        self.assertNotIn("mercados_contexto", rel)

    def test_mercado_ausente_zero_diferente_de_metadados_ausentes(self):
        for markets, wanted in [
            ([], {"total": 0, "compativeis": 0, "sem_catalogo": 0}),
            ([{"id": "1010", "name": "Market 1010"}],
             {"total": 1, "compativeis": 0, "sem_catalogo": 1}),
        ]:
            with self.subTest(markets=markets):
                c = AuditoriaOdds._contexto_mercados_passivo(
                    {"mercados": markets}, "Under 2.5 Golos"
                )
                self.assertEqual(c, wanted)


if __name__ == "__main__":
    unittest.main()
