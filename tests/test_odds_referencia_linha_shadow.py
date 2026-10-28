"""Prova offline: handicap do catálogo vs linha escrita no bookmakerOutcomeId."""
import json
import tempfile
import unittest
from pathlib import Path

from odds_auditoria import AuditoriaOdds
from odds_linha_diagnostico_shadow import resumo_linha_shadow
from odds_rastreio import RastreioOdds


def mercado(handicap, ref):
    return {
        "name": "Over Under Full Time",
        "handicap": handicap,
        "period": "fulltime",
        "odds": [{"seleção": "Over", "ref": ref, "odd": 1.78}],
    }


def observar(mercados):
    return resumo_linha_shadow(
        mercados, "Over 2.5 Golos",
        AuditoriaOdds._mercado_compativel,
        AuditoriaOdds._odd_numero,
    )


class ProvaReferenciaShadowTests(unittest.TestCase):
    def test_referencia_2_5_contra_catalogo_8_5_detetada_sem_aprovar_odd(self):
        m = mercado(8.5, "2.5/over")
        obs = observar([m])
        self.assertEqual(obs["linhas_handicap"], [8.5])
        self.assertEqual(obs["linhas_ref_lado_alvo"], [2.5])
        self.assertEqual(obs["refs_alvo_handicap_divergente"], 1)
        self.assertFalse(AuditoriaOdds._item_compativel(
            "Over 2.5 Golos", m, m["odds"][0], "Celtic", "Dundee United"
        ))

    def test_referencia_8_5_contra_catalogo_8_5_sem_conflito(self):
        obs = observar([mercado(8.5, "8.5/over")])
        self.assertEqual(obs["linhas_ref_lado_alvo"], [8.5])
        self.assertEqual(obs["refs_alvo_handicap_divergente"], 0)

    def test_ref_nao_parseavel_nao_vira_prova_da_linha(self):
        obs = observar([mercado(8.5, "internal-id-984")])
        self.assertEqual(obs["linhas_ref_lado_alvo"], [])
        self.assertEqual(obs["refs_lado_alvo_com_linha"], 0)

    def test_ref_divergente_e_catalogo_correto_assinala_conflito(self):
        obs = observar([mercado(2.5, "8.5/over")])
        self.assertEqual(obs["refs_outra_handicap_alvo"], 1)

    def test_diagnostico_gravado_sem_valor_de_odd_ou_ref_raw(self):
        contexto = observar([mercado(8.5, "2.5/over")])
        selecao = {
            "jogo": {"id": 1, "casa": "Celtic", "fora": "Dundee United", "liga": "Premiership", "timestamp": 1793216700},
            "mercado": "Over 2.5 Golos",
            "_odds_diag": "linha_ou_selecao_nao_disponivel",
            "_odds_contexto_linha": contexto,
        }
        with tempfile.TemporaryDirectory() as d:
            rastreio = RastreioOdds(Path(d) / "trace.jsonl")
            rastreio.registar([selecao])
            raw = json.loads(rastreio.path.read_text().strip())
            self.assertEqual(raw["contexto_linha"]["linhas_ref_lado_alvo"], [2.5])
            self.assertNotIn("2.5/over", rastreio.path.read_text())
            self.assertNotIn("1.78", rastreio.path.read_text())
            detalhe = rastreio.detalhe("Celtic")
            self.assertIn("Linhas explícitas na referência da seleção: 2.5", detalhe)
            self.assertIn("Ref alvo / handicap diferente: 1", detalhe)


if __name__ == "__main__":
    unittest.main()
