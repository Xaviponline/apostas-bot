"""SHADOW: base de UEFA/Taca reconstruida por calendario ESPN de equipas."""
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from estatisticas_forma_web import EstatisticasFormaWeb


REF = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("Europe/Lisbon"))


def evento(i, slug, data=None, total_casa=2, total_fora=1, home_id=None):
    instante = data or (datetime(2026, 9, 25, 18, tzinfo=timezone.utc) - timedelta(days=i))
    iso = instante.isoformat().replace("+00:00", "Z")
    casa_id = home_id or (1000+i)
    return {
        "id": 400000 + i,
        "date": iso,
        "name": f"T{casa_id} vs T{2000+i}",
        "season": {"name": "2026-27 Group Stage", "slug": slug},
        "league": {"name": "Group Stage", "slug": slug},
        "status": {"type": {"state": "post", "completed": True, "name": "STATUS_FINAL"}},
        "competitions": [{
            "date": iso,
            "competitors": [
                {"homeAway":"home", "team":{"id":str(casa_id),"displayName":"Casa"}, "score":str(total_casa)},
                {"homeAway":"away", "team":{"id":str(2000+i),"displayName":"Fora"}, "score":str(total_fora)},
            ],
        }],
    }


class Probe(EstatisticasFormaWeb):
    def __init__(self, codigo, total=12, sem_identificacao=False):
        super().__init__()
        self.codigo = codigo
        self.total = total
        self.sem_identificacao = sem_identificacao
        self.calls = []
        self._equipas_contexto_liga = {codigo: {10, 20}}

    def _fetch_base_sofa(self, liga_codigo, data_ref=None):
        raise ValueError("API HTTP 403; WWW HTTP 403")

    def _eventos_equipa_temporada(self, team_id, season):
        self.calls.append((team_id, season))
        slug = {
            "uefa.champions": "2026-27-uefa-champions-league",
            "por.taca.portugal": "2026-27-portuguese-taca-de-portugal",
        }[self.codigo]
        if self.sem_identificacao:
            slug = ""
        eventos = [evento(i, slug) for i in range(self.total)]
        # Amigaveis e outras provas nunca podem entrar na base.
        eventos.extend([evento(200, "international-friendly"), evento(201, "uefa-europa-league")])
        return eventos


class EspnEquipaShadowTests(unittest.TestCase):
    def test_fallback_certos_so_eventos_da_propria_prova(self):
        for codigo in ("uefa.champions", "por.taca.portugal"):
            with self.subTest(codigo=codigo):
                stats = Probe(codigo)
                base = stats._fetch_liga(codigo, REF)
                self.assertEqual(len(base), 12)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "espn_equipas_clubes")
                self.assertEqual({x["liga_codigo"] for x in base}, {codigo})
                self.assertEqual({x["golos_casa"] for x in base}, {2})
                self.assertEqual({x["golos_fora"] for x in base}, {1})
                self.assertEqual(len(stats.calls), 4)
                self.assertEqual(set(season for _, season in stats.calls), {2025, 2026})
                self.assertEqual(stats.diagnostico_base[codigo]["consultas_ok"], 4)

    def test_sem_identificacao_falha_fechado_nunca_adivinha_group_stage(self):
        stats = Probe("uefa.champions", sem_identificacao=True)
        with self.assertRaisesRegex(ValueError, "insuficiente"):
            stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(stats.diagnostico_base["uefa.champions"]["fonte"], "sofa_e_espn_equipas_indisponiveis")

    def test_amostra_inferior_a_dez_recusada(self):
        stats = Probe("por.taca.portugal", total=9)
        with self.assertRaises(ValueError):
            stats._fetch_liga("por.taca.portugal", REF)

    def test_resultados_futuros_e_antigos_excluidos(self):
        class SoAntigos(Probe):
            def _eventos_equipa_temporada(self, team_id, season):
                retorno = super()._eventos_equipa_temporada(team_id, season)
                retorno.append(evento(1000, "2026-27-uefa-champions-league",
                                     data=REF.astimezone(timezone.utc) + timedelta(days=1)))
                retorno.append(evento(1001, "2026-27-uefa-champions-league",
                                     data=REF.astimezone(timezone.utc) - timedelta(days=500)))
                return retorno
        stats = SoAntigos("uefa.champions")
        base = stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(len(base), 12)

    def test_conflitos_de_resultado_nao_entram_na_base(self):
        class Divergentes(Probe):
            def _eventos_equipa_temporada(self, team_id, season):
                base = super()._eventos_equipa_temporada(team_id, season)
                if team_id == 20:
                    base[0] = evento(0, "2026-27-uefa-champions-league", total_casa=7)
                return base
        stats = Divergentes("uefa.champions", total=12)
        resultados = stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(len(resultados), 11)
        self.assertNotIn(400000, {x["id"] for x in resultados})
        self.assertEqual(stats.diagnostico_base["uefa.champions"]["conflitos"], 1)

    def test_sem_ids_de_equipas_suspende_a_base(self):
        stats = Probe("uefa.champions")
        stats._equipas_contexto_liga = {}
        with self.assertRaisesRegex(ValueError, "insuficientes"):
            stats._fetch_liga("uefa.champions", REF)


if __name__ == "__main__":
    unittest.main()
