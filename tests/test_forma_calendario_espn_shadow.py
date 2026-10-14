"""Regressão do esquema de calendários de equipa ESPN (todos fixtures).

Apenas adapta dados de transporte. Nenhum limiar ou modelo é modificado.
"""
import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from estatisticas_espn_resiliente import EstatisticasESPNResiliente


REF = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("Europe/Lisbon"))


def calendario(
    eid, dia="2026-10-10", placar=(2, 1), completo=True, detalhe="FT",
    status_nivel="competicao", nome="League Match",
):
    tipo = {
        "state": "post" if completo else "pre",
        "completed": completo,
        "detail": detalhe,
    }
    evento = {
        "id": str(eid), "name": nome, "date": f"{dia}T19:00:00Z",
        "season": {"slug": "english-premier-league"},
        "competitions": [{
            "status": {"type": tipo},
            "competitors": [
                {
                    "homeAway": "home", "team": {"id": "101", "displayName": "Casa"},
                    "score": {"value": float(placar[0]), "displayValue": str(placar[0])},
                },
                {
                    "homeAway": "away", "team": {"id": "202", "displayName": "Fora"},
                    "score": {"value": float(placar[1]), "displayValue": str(placar[1])},
                },
            ],
        }],
    }
    if status_nivel == "evento":
        evento["status"] = evento["competitions"][0]["status"]
    return evento


class SessionFake:
    def __init__(self, eventos):
        self.eventos = eventos
        self.chamadas = 0

    def mount(self, *args):
        pass

    def get(self, url, timeout=None):
        self.chamadas += 1
        return self

    def raise_for_status(self):
        pass

    def json(self):
        return {"events": self.eventos}


class FormaESPNCalendarioTests(unittest.TestCase):
    def test_esquema_aninhado_recupera_resultado_sem_mutar_payload(self):
        original = calendario(1)
        copia = copy.deepcopy(original)
        adaptado = EstatisticasESPNResiliente._adaptar_evento_forma_equipa(original)
        self.assertEqual(original, copia)
        self.assertTrue(adaptado["status"]["type"]["completed"])
        resultado = EstatisticasESPNResiliente._normalizar_resultado(adaptado, "all")
        self.assertEqual((resultado["golos_casa"], resultado["golos_fora"]), (2, 1))
        self.assertEqual((resultado["casa_id"], resultado["fora_id"]), (101, 202))

    def test_calendario_ignora_nao_terminados_e_resultados_futuros(self):
        sessao = SessionFake([
            calendario(1),
            calendario(2, completo=False),
            calendario(3, dia="2026-10-20"),
            calendario(4, nome="Friendly Match"),
            calendario(5, detalhe="Won on penalties"),
        ])
        stats = EstatisticasESPNResiliente(session=sessao)
        historico = stats._fetch_forma_global(101, REF)
        self.assertEqual([x["id"] for x in historico], [1])
        self.assertEqual(len(stats._fetch_forma_global(101, REF)), 1)
        self.assertEqual(sessao.chamadas, 1)  # cache

    def test_estado_no_evento_continua_a_funcionar(self):
        sessao = SessionFake([calendario(6, status_nivel="evento")])
        stats = EstatisticasESPNResiliente(session=sessao)
        self.assertEqual(stats._fetch_forma_global(101, REF)[0]["id"], 6)

    def test_rejeita_score_ausente_decimal_negativo_e_incoerente(self):
        casos = []
        ausente = calendario(1)
        ausente["competitions"][0]["competitors"][0]["score"] = {"displayValue": "2"}
        casos.append(ausente)
        fracionado = calendario(2, placar=(2.5, 1))
        casos.append(fracionado)
        negativo = calendario(3, placar=(-1, 1))
        casos.append(negativo)
        incoerente = calendario(4)
        incoerente["competitions"][0]["competitors"][0]["score"]["displayValue"] = "3"
        casos.append(incoerente)

        for evento in casos:
            with self.subTest(id=evento["id"]):
                self.assertIsNone(
                    EstatisticasESPNResiliente._adaptar_evento_forma_equipa(evento)
                )

    def test_nao_altera_minimo_de_quatro_jogos_por_equipa(self):
        stats = EstatisticasESPNResiliente()
        self.assertIsNone(
            stats.analisar_jogo(
                {"league_code": "uefa.champions", "casa_id": 101, "fora_id": 202},
                [],
            )
        )


if __name__ == "__main__":
    unittest.main()
