import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes


class SofaFake:
    def __init__(self, codigo_nome="UEFA Europa League", total=24):
        self.codigo_nome = codigo_nome
        self.total = total
        self.chamadas = []

    def _get_sofa(self, caminho):
        self.chamadas.append(caminho)
        if caminho.startswith("/sport/football/scheduled-events/"):
            return {
                "events": [
                    {
                        "id": 1,
                        "tournament": {
                            "name": self.codigo_nome,
                            "uniqueTournament": {"id": 679, "name": self.codigo_nome},
                        },
                        "season": {"id": 9999},
                    }
                ]
            }
        if caminho.startswith("/unique-tournament/679/season/9999/events/last/"):
            eventos = []
            for i in range(self.total):
                eventos.append(
                    {
                        "id": 10000 + i,
                        "startTimestamp": 1700000000 - i * 86400,
                        "status": {"code": 100, "type": "finished"},
                        "homeTeam": {"id": 100 + i, "name": f"Casa {i}"},
                        "awayTeam": {"id": 200 + i, "name": f"Fora {i}"},
                        "homeScore": {"current": 5, "normaltime": 2},
                        "awayScore": {"current": 4, "normaltime": 1},
                    }
                )
            return {"events": eventos, "hasNextPage": False}
        raise ValueError("caminho inesperado")


class RespostaFake:
    def __init__(self, dados, status_code=200):
        self._dados = dados
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._dados


class SessaoWWWFake:
    def __init__(self, dados):
        self.dados = dados
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return RespostaFake(self.dados)


class SofaApiFalhaFake:
    def __init__(self, dados_www):
        self.sofa_http_status = 403
        self.ultimo_http_status = 403
        self.browser_mode = False
        self.sofa_session = SessaoWWWFake(dados_www)

    @staticmethod
    def _headers_sofa():
        return {"Accept": "application/json"}

    def _get_sofa(self, caminho):
        self.sofa_http_status = 403
        raise ValueError("Fonte SofaScore indisponível.")


class HistoricoHibridoTests(unittest.TestCase):
    REF = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))

    def test_codigo_bloqueado_usa_sofascore_sem_tentar_espn(self):
        class Probe(EstatisticasHibridasCompeticoes):
            def _recolher_base_tolerante(self, *args, **kwargs):
                raise AssertionError("ESPN não deve ser chamada para código confirmado bloqueado")

        sofa = SofaFake()
        stats = Probe(sofa_client=sofa)
        historico = stats._fetch_liga("uefa.europa", self.REF)
        self.assertGreaterEqual(len(historico), stats.MIN_JOGOS_BASE)
        self.assertEqual(stats.diagnostico_base["uefa.europa"]["fonte"], "sofascore")
        self.assertTrue(any("unique-tournament/679" in x for x in sofa.chamadas))

    def test_host_www_e_tentado_quando_api_falha(self):
        sofa = SofaApiFalhaFake({"events": []})
        stats = EstatisticasHibridasCompeticoes(sofa_client=sofa)
        dados = stats._sofa_get("/sport/football/scheduled-events/2026-09-16")
        self.assertEqual(dados, {"events": []})
        self.assertEqual(len(sofa.sofa_session.urls), 1)
        self.assertTrue(
            sofa.sofa_session.urls[0].startswith("https://www.sofascore.com/api/v1/")
        )

    def test_normalizacao_sofa_prefere_resultado_90_minutos(self):
        stats = EstatisticasHibridasCompeticoes(sofa_client=SofaFake())
        evento = {
            "id": 77,
            "startTimestamp": 1700000000,
            "status": {"code": 100, "type": "afterextra"},
            "homeTeam": {"id": 1, "name": "Casa"},
            "awayTeam": {"id": 2, "name": "Fora"},
            "homeScore": {"current": 4, "normaltime": 1, "overtime": 3},
            "awayScore": {"current": 3, "normaltime": 1, "overtime": 2},
        }
        item = stats._normalizar_resultado_sofa(
            evento, "eng.league_cup", self.REF.timestamp()
        )
        self.assertEqual(item["golos_casa"], 1)
        self.assertEqual(item["golos_fora"], 1)

    def test_correspondencia_de_competicao_e_exata_e_conservadora(self):
        sofa = SofaFake(codigo_nome="UEFA Europa Conference League")
        stats = EstatisticasHibridasCompeticoes(sofa_client=sofa)
        with self.assertRaises(ValueError):
            stats._descobrir_competicao_sofa("uefa.europa", self.REF)

    def test_base_sofascore_insuficiente_e_rejeitada(self):
        sofa = SofaFake(total=9)
        stats = EstatisticasHibridasCompeticoes(sofa_client=sofa)
        with self.assertRaises(ValueError):
            stats._fetch_liga("uefa.europa", self.REF)
        diag = stats.diagnostico_base["uefa.europa"]
        self.assertEqual(diag["fonte"], "sofascore_indisponivel")
        self.assertIn("base insuficiente", diag["motivo"])

    def test_liga_normal_nao_usa_sofascore(self):
        class Probe(EstatisticasHibridasCompeticoes):
            def _consultar_intervalo(self, liga_codigo, inicio, fim):
                return []

            def _sofa_get(self, caminho):
                raise AssertionError("Liga normal não deve usar SofaScore")

        stats = Probe(sofa_client=SofaFake())
        self.assertEqual(stats._fetch_liga("esp.1", self.REF), [])


if __name__ == "__main__":
    unittest.main()
