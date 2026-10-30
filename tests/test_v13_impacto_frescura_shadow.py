"""Regressoes offline: impacto descritivo da frescura V1.3, sem HTTP."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from auditoria_impacto_frescura_v13_shadow import _grupo, relatorio_impacto_frescura_v13

AGORA = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)


def iso(horas):
    return (AGORA - timedelta(hours=horas)).isoformat()


def original(idade_horas, prob=0.66):
    return {
        "casa": "Teste Casa", "fora": "Teste Fora",
        "mercado": "Under 3.5 Golos", "probabilidade": prob,
        "odds_capturada_em": AGORA.isoformat(),
        "odds_atualizada_em": iso(idade_horas),
    }


def entrada(indice, resultado, lucro, clv=None):
    return {
        "snapshot": indice, "resultado_binario": resultado,
        "lucro_unidades": lucro, "clv": clv,
        "data_jogo": f"2026-10-{20 + indice:02d}",
    }


class RegistoFalso:
    def __init__(self, coorte, originais):
        self.dados = {"previsoes": originais}
        self.metricas = {"coorte": coorte, "alvo": 50}

    def metricas_v13_comercial(self):
        return self.metricas


class ImpactoFrescuraShadowTests(unittest.TestCase):
    def test_grupos_exatos_seis_horas_sem_confundir_captura_e_mudanca(self):
        self.assertEqual(_grupo(original(6)), "ate_6h")
        self.assertEqual(_grupo(original(6.001)), "mais_6h")
        self.assertEqual(_grupo(original(24)), "mais_6h")
        self.assertEqual(_grupo(original(-0.20)), "futura")
        self.assertEqual(_grupo(original(-0.05)), "ate_6h")
        s = original(7)
        s.pop("odds_atualizada_em")
        self.assertEqual(_grupo(s), "desconhecida")

    def test_roi_por_grupo_nao_mistura_pendente_ou_clv_faltante(self):
        dados = RegistoFalso(
            [
                entrada(1, 1, 0.8, .02),
                entrada(2, 0, -1.0),
                entrada(3, 0, -1.0, -.03),
                entrada(4, None, None),
                entrada(5, 1, 0.7, .04),
            ],
            [
                original(1), original(2), original(36),
                original(38), {"probabilidade": .50},
            ],
        )
        antigo = copy.deepcopy(dados.dados)
        coh = copy.deepcopy(dados.metricas)
        with patch("requests.Session", side_effect=AssertionError("rede proibida")):
            r = relatorio_impacto_frescura_v13(dados)
        self.assertIn("Entradas: 5/50", r)
        self.assertIn("Alteracao ate 6h: 2 entradas | 2 liquidadas", r)
        self.assertIn("✅ 1/2 | P/L -0,20u | ROI -10,0%", r)
        self.assertIn("Alteracao ha mais de 6h: 2 entradas | 1 liquidadas", r)
        self.assertIn("✅ 0/1 | P/L -1,00u | ROI -100,0%", r)
        self.assertIn("Sem timestamps comparaveis: 1 entradas | 1 liquidadas", r)
        self.assertIn("CLV com fecho: 1/2", r)
        self.assertEqual(r.count("CLV com fecho: 1/2"), 2)
        self.assertIn("Zero HTTP", r)
        self.assertEqual(dados.dados, antigo)
        self.assertEqual(dados.metricas, coh)

    def test_booleans_e_pnl_malformado_nunca_inventam_roi(self):
        dados = RegistoFalso(
            [entrada(1, True, 0.8), entrada(2, 1, float("nan"))],
            [original(11), original(11)],
        )
        r = relatorio_impacto_frescura_v13(dados)
        self.assertIn("Alteracao ha mais de 6h: 2 entradas | 0 liquidadas", r)
        self.assertIn("1 liquidacoes sem P/L utilizavel", r)
        self.assertNotIn("nan", r.lower())

    def test_referencia_invalida_ou_duplicada_e_assinalada(self):
        dados = RegistoFalso([
            entrada(1, 1, 0.7), entrada(1, 0, -1),
            entrada(200, 1, 0.7), entrada(-1, 1, 0.7),
        ], [original(2)])
        r = relatorio_impacto_frescura_v13(dados)
        self.assertIn("ligacoes inconsistentes: 3", r)
        self.assertIn("Alteracao ate 6h: 1 entradas | 1 liquidadas", r)

    def test_dados_estruturais_invalidos_falham_fechado(self):
        d = RegistoFalso([], [])
        d.metricas["coorte"] = None
        with self.assertRaises(ValueError):
            relatorio_impacto_frescura_v13(d)
        d.metricas["coorte"] = []
        d.dados = {"previsoes": "invalido"}
        with self.assertRaises(ValueError):
            relatorio_impacto_frescura_v13(d)


if __name__ == "__main__":
    unittest.main()
