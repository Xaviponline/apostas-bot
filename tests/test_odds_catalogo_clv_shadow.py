"""Regressões CLV SHADOW: catálogo existente, SEM consumir odds nem forçar matches."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clv_observatorio import ObservatorioCLV
from clv_tentativas import DiarioTentativasCLV, _catalogo_sanitizado
from odds_auditoria import AuditoriaOdds
from odds_catalogo_clv_shadow import resumo_catalogo_sem_match


INICIO = datetime(2026, 10, 28, 22, 30, tzinfo=timezone.utc)


def mercado(mid, nome, periodo="fulltime", handicap=None, ref=""):
    return {
        "id": str(mid), "name": nome, "period": periodo,
        "handicap": handicap, "playerProp": False,
        "odds": [{"seleção": "Under", "odd": 1.85,
                  "ref": ref or f"ref-segredo-{mid}"}],
    }


def mercados_31():
    itens = [mercado(999, "Full Time Goals Total", handicap=2.5, ref="outcome-segredo")]
    itens += [mercado(1000+i, "Full Time Result") for i in range(28)]
    itens += [mercado(222, "Total Corners", handicap=2.5)]
    itens += [mercado(333, "Team 1 Total Goals", handicap=2.5)]
    return itens


class FonteFalsa:
    configurada = True
    nome_fonte = "OddsPapi / Betano PT"
    provider = "oddspapi"

    def __init__(self, mercados):
        self.mercados = mercados
        self.consultas = 0

    def eventos_hoje(self):
        return [{
            "id": "12", "casa": "Santos", "fora": "Palmeiras",
            "data": INICIO.isoformat(), "liga": "Brazil Serie A",
        }]

    def odds_evento(self, event_id):
        self.consultas += 1
        return {
            "id": "12", "casa": "Santos", "fora": "Palmeiras",
            "liga": "Brazil Serie A", "bookmaker_disponivel": True,
            "mercados": self.mercados, "fonte": self.nome_fonte,
        }


class RegistoFalso:
    def __init__(self, path):
        self.path = Path(path)
        self.dados = {"previsoes": [{
            "event_id": 12, "casa": "Santos", "fora": "Palmeiras",
            "mercado": "Under 2.5 Golos",
            "data_jogo": "2026-10-28",
            "timestamp_jogo": INICIO.timestamp(), "odd_fecho": None,
        }]}

    def _odd_real_valida(self, valor):
        return None

    def metricas_v13_comercial(self):
        return {
            "coorte": [{
                "snapshot": 1, "casa": "Santos", "fora": "Palmeiras",
                "mercado": "Under 2.5 Golos", "data_jogo": "2026-10-28",
                "odd_fecho": None,
            }],
            "coorte_tamanho": 1, "alvo": 50,
        }


class CatalogoCLVShadowTests(unittest.TestCase):
    def _selecoes(self):
        return [{
            "jogo": {
                "id": 12, "casa": "Santos", "fora": "Palmeiras",
                "liga": "Brazil Serie A", "timestamp": INICIO.timestamp(),
            },
            "mercado": "Under 2.5 Golos", "probabilidade": 0.67,
        }]

    def test_31_mercados_nenhum_match_mas_catalogo_da_pista(self):
        fonte = FonteFalsa(mercados_31())
        selecoes = self._selecoes()
        anterior = copy.deepcopy(selecoes)
        saida = AuditoriaOdds(fonte).enriquecer(selecoes)
        self.assertEqual(fonte.consultas, 1)
        self.assertEqual(selecoes, anterior)
        self.assertEqual(saida[0]["_odds_diag"], "mercado_nao_disponivel")
        self.assertEqual(saida[0]["_odds_contexto_mercados"], {
            "total": 31, "compativeis": 0, "sem_catalogo": 0,
        })
        pista = saida[0]["_odds_catalogo_clv_shadow"]
        self.assertEqual(pista["potenciais"], 1)
        self.assertEqual(pista["potenciais_outro_periodo"], 0)
        self.assertEqual(pista["amostra"][0]["nome"], "Full Time Goals Total")
        self.assertEqual(pista["amostra"][0]["linha"], "2.5")
        self.assertNotIn("odd_real", saida[0])
        self.assertNotIn("outcome-segredo", json.dumps(pista))
        self.assertNotIn("1.85", json.dumps(pista))

    def test_telemetria_persiste_sem_mudar_snapshot_ou_clv(self):
        with tempfile.TemporaryDirectory() as t:
            reg = RegistoFalso(Path(t) / "previsoes.json")
            antes = copy.deepcopy(reg.dados)
            sel = self._selecoes()
            fonte = FonteFalsa(mercados_31())
            en = AuditoriaOdds(fonte).enriquecer(sel)
            diario = DiarioTentativasCLV.para_previsoes(reg)
            self.assertEqual(diario.registar(reg, sel, "consulta_concluida", en), 1)
            self.assertEqual(fonte.consultas, 1)
            self.assertEqual(antes, reg.dados)
            leitura = DiarioTentativasCLV.para_previsoes(reg).por_snapshot()[1]["ultima"]
            self.assertEqual(leitura["motivo"], "mercado_nao_disponivel")
            self.assertEqual(leitura["catalogo_shadow"]["amostra"][0]["id"], "999")
            texto = ObservatorioCLV().relatorio(reg, agora=INICIO + timedelta(hours=2))
            self.assertIn("Pistas no catalogo", texto)
            self.assertIn("Full Time Goals Total", texto)
            self.assertIn("linha 2.5", texto)
            self.assertNotIn("1.85", diario.path.read_text(encoding="utf-8"))
            self.assertNotIn("ref-segredo", diario.path.read_text(encoding="utf-8"))
            self.assertNotIn("outcome-segredo", diario.path.read_text(encoding="utf-8"))
            self.assertIsNone(reg.dados["previsoes"][0]["odd_fecho"])

    def test_suspeito_noutro_periodo_contado_mas_nunca_torna_odd(self):
        fonte = FonteFalsa([mercado(77, "Full Time Total Goals",
                                     periodo="firsthalf", handicap=2.5)])
        r = AuditoriaOdds(fonte).enriquecer(self._selecoes())[0]
        self.assertEqual(r["_odds_diag"], "mercado_nao_disponivel")
        self.assertEqual(r["_odds_catalogo_clv_shadow"]["potenciais_outro_periodo"], 1)
        self.assertNotIn("odd_real", r)

    def test_mercado_correspondente_mantem_extracao_original(self):
        fonte = FonteFalsa([mercado(1012, "Total Goals", handicap=2.5, ref="Under")])
        r = AuditoriaOdds(fonte).enriquecer(self._selecoes())[0]
        self.assertEqual(fonte.consultas, 1)
        self.assertEqual(r["odd_real"], 1.85)
        self.assertNotIn("_odds_catalogo_clv_shadow", r)

    def test_catalogo_invalido_ou_injetado_nao_e_guardado(self):
        cru = resumo_catalogo_sem_match(
            [mercado("site:token", "Total Goals\\nhttps://secret", handicap=2.5)],
            "Under 2.5 Golos", AuditoriaOdds._periodo_compativel,
        )
        texto = json.dumps(cru)
        self.assertNotIn("https:", texto)
        self.assertNotIn("site:token", texto)
        self.assertEqual(cru["amostra"][0]["id"], "?")
        self.assertIsNotNone(_catalogo_sanitizado(cru))
        cru["amostra"][0]["nome"] = "Market\\nSECRET"
        self.assertIsNone(_catalogo_sanitizado(cru))

    def test_nao_aceita_cotacoes_para_corners_equipa_player(self):
        r = resumo_catalogo_sem_match([
            mercado(1, "Total Corners", handicap=2.5),
            mercado(2, "Team 1 Total Goals", handicap=2.5),
            mercado(3, "Total Player Shots", handicap=2.5),
        ], "Under 2.5 Golos", AuditoriaOdds._periodo_compativel)
        self.assertEqual(r["potenciais"], 0)
        self.assertEqual(len(r["amostra"]), 3)

    def test_so_funciona_em_mercado_golos_sem_rede(self):
        self.assertIsNone(resumo_catalogo_sem_match(
            mercados_31(), "Vitória Casa", AuditoriaOdds._periodo_compativel))
        self.assertIsNone(resumo_catalogo_sem_match(
            {}, "Under 2.5 Golos", AuditoriaOdds._periodo_compativel))


if __name__ == "__main__":
    unittest.main()
