"""Provas offline da equivalencia EXATA LPF; sem rede, quotas ou snapshots."""
import unittest
from datetime import datetime, timezone

from odds_auditoria import AuditoriaOdds

INICIO = datetime(2026, 10, 30, 22, 0, tzinfo=timezone.utc)


def evento(liga, inicio=None):
    return {
        "casa": "Huracán",
        "fora": "Tigre",
        "liga": liga,
        "data": (inicio or INICIO).isoformat(),
    }


def jogo(liga):
    return {
        "casa": "Huracán",
        "fora": "Tigre",
        "liga": liga,
        "timestamp": INICIO.timestamp(),
    }


class EquivalenciaLPFShadowTests(unittest.TestCase):
    def test_argentina_lpf_primera_lpf_nao_alerta_divergencia(self):
        alertas = AuditoriaOdds._alertas_contexto(
            jogo("Argentine Liga Profesional"), evento("Primera LPF")
        )
        self.assertNotIn("competicao_divergente", alertas)
        self.assertEqual(alertas, [])

    def test_equivalencia_tambem_na_resposta_odds(self):
        alertas = AuditoriaOdds._alertas_contexto(
            jogo("Argentine Liga Profesional"),
            evento("Outra Competicao"),
            {"liga": "Primera LPF"},
        )
        self.assertEqual(alertas, [])

    def test_nomes_invertidos_tambem_sao_equivalentes(self):
        self.assertEqual(AuditoriaOdds._alertas_contexto(
            jogo("Primera LPF"), evento("Argentine Liga Profesional"),
        ), [])

    def test_primera_nacional_continua_divergente(self):
        self.assertIn("competicao_divergente", AuditoriaOdds._alertas_contexto(
            jogo("Argentine Liga Profesional"), evento("Primera Nacional"),
        ))

    def test_copa_lpf_nao_e_a_primera_lpf(self):
        self.assertIn("competicao_divergente", AuditoriaOdds._alertas_contexto(
            jogo("Argentine Liga Profesional"), evento("Copa LPF"),
        ))

    def test_equipa_jovem_nao_usa_alias(self):
        alertas = AuditoriaOdds._alertas_contexto(
            jogo("Argentine Liga Profesional"), evento("Primera LPF U19"),
        )
        self.assertIn("competicao_divergente", alertas)

    def test_competicao_com_sufixo_reserva_nao_usa_alias(self):
        alertas = AuditoriaOdds._alertas_contexto(
            jogo("Argentine Liga Profesional"), evento("Primera LPF Reserva"),
        )
        self.assertIn("competicao_divergente", alertas)

    def test_horario_errado_continua_sinalizado(self):
        tarde = datetime(2026, 10, 31, 1, 0, tzinfo=timezone.utc)
        alertas = AuditoriaOdds._alertas_contexto(
            jogo("Argentine Liga Profesional"), evento("Primera LPF", tarde),
        )
        self.assertIn("horario_divergente", alertas)

    def test_nao_toca_no_preco_nem_na_identificacao_da_linha(self):
        mercado = {
            "name": "Over Under Full Time",
            "period": "fulltime",
            "handicap": 3.5,
        }
        odd = {"seleção": "Under", "ref": "10656653447", "odd": 1.13}
        self.assertTrue(AuditoriaOdds._item_compativel(
            "Under 3.5 Golos", mercado, odd, "Huracán", "Tigre",
        ))
        self.assertFalse(AuditoriaOdds._item_compativel(
            "Under 2.5 Golos", mercado, odd, "Huracán", "Tigre",
        ))


if __name__ == "__main__":
    unittest.main()
