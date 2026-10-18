"""Detalhe forense das odds já guardadas, sem queries pagas nem mutações."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo

from odds_auditoria import AuditoriaOdds
from odds_rastreio import RastreioOdds
from main_competicoes import BotPremiumDiarioCompeticoes


class FonteExistente:
    configurada = True
    nome_fonte = "OddsPapi Betano PT (teste)"

    def __init__(self):
        self.chamadas = 0

    def eventos_hoje(self):
        self.chamadas += 1
        return [{
            "id": "fixture123", "casa": "Estudiantes de La Plata",
            "fora": "San Lorenzo", "liga": "Argentina League",
            "data": "2026-10-18T16:00:00Z"
        }]

    def odds_evento(self, event_id):
        self.chamadas += 1
        return {
            "id": event_id, "casa": "Estudiantes de La Plata", "fora": "San Lorenzo",
            "liga": "Liga Profesional", "fonte": self.nome_fonte,
            "mercados": [{
                "id": 101, "name": "Full Time Result", "period": "fulltime",
                "updatedAt": "2026-10-18T12:00:00Z",
                "odds": [{
                    "ref": "1", "seleção": "1", "odd": 2.07,
                    "bookmakerChangedAt": "2026-10-18T11:59:00Z"
                }],
            }],
        }


class OddsRastreioDetalheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "odds_rastreio.jsonl"
        self.rastreio = RastreioOdds(self.path)
        self.ts = datetime(2026, 10, 18, 17, tzinfo=ZoneInfo("Europe/Lisbon")).timestamp()

    def _selecao(self):
        return {
            "jogo": {
                "id": 108, "casa": "Estudiantes de La Plata",
                "fora": "San Lorenzo", "liga": "Liga Argentina",
                "timestamp": self.ts,
            },
            "mercado": "Vitória Casa", "probabilidade": .69,
            "odd_minima": 1.52,
        }

    def test_contexto_passivo_da_mesma_consulta_sem_alterar_selecao(self):
        fonte = FonteExistente()
        entrada = self._selecao()
        antes = copy.deepcopy(entrada)
        saida = AuditoriaOdds(fonte).enriquecer([entrada])
        self.assertEqual(entrada, antes)
        self.assertEqual(fonte.chamadas, 2)
        item = saida[0]
        self.assertEqual(item["odd_real"], 2.07)
        self.assertIn("competicao_divergente", item["_odds_alertas"])
        contexto = item["_odds_evento_contexto"]
        self.assertEqual(contexto["liga_fixture"], "Argentina League")
        self.assertEqual(contexto["liga_odds"], "Liga Profesional")
        self.assertEqual(contexto["inicio_fixture"], "2026-10-18T16:00:00Z")
        self.assertEqual(self.rastreio.registar(saida), 1)
        self.assertEqual(fonte.chamadas, 2)  # análise de logs não chama odds
        gravado = json.loads(self.path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(gravado["liga_modelo"], "Liga Argentina")
        self.assertEqual(gravado["liga_fonte_fixture"], "Argentina League")
        self.assertEqual(gravado["liga_fonte_odds"], "Liga Profesional")
        self.assertEqual(gravado["mercado_id_fonte"], "101")
        self.assertEqual(gravado["selecao_nome_fonte"], "1")
        self.assertEqual(gravado["resultado_associacao"], "unica")
        anterior = self.path.read_bytes()
        resposta = self.rastreio.detalhe("Estudiantes")
        for trecho in (
            "Full Time Result", "Argentina League", "Liga Profesional",
            "Liga Argentina", "Vitória Casa", "2,07", "fixture123",
            "fulltime", "competicao_divergente", "18/10/2026 17:00",
            "Associação: unica", "Seleção fonte: 1",
        ):
            self.assertIn(trecho, resposta)
        self.assertEqual(self.path.read_bytes(), anterior)
        self.assertEqual(fonte.chamadas, 2)

    def test_historico_legacy_sem_mentir_sobre_campos_em_falta(self):
        linha = {
            "jogo": "Estudiantes de La Plata vs San Lorenzo",
            "event_id_modelo": "108",
            "fixture_id_fonte": "id1000015573265414",
            "mercado_modelo": "Vitória Casa",
            "odd_observada": 2.07,
            "mercado_id_fonte": "101",
            "outcome_ref_fonte": "10096318663",
            "mercado_nome_fonte": "Full Time Result",
            "periodo_fonte": "fulltime",
            "selecao_nome_fonte": "Home",
            "resultado_associacao": "unica",
            "timestamp_jogo": self.ts,
        }
        self.path.write_text(json.dumps(linha) + "\n", encoding="utf-8")
        antes = self.path.read_bytes()
        resposta = self.rastreio.detalhe("id1000015573265414")
        self.assertIn("Liga (fixture): não registado", resposta)
        self.assertIn("Liga (odds): não registado", resposta)
        self.assertIn("Jogo (fixture fonte): não registada", resposta)
        self.assertIn("10096318663", resposta)
        self.assertIn("Full Time Result", resposta)
        self.assertEqual(self.path.read_bytes(), antes)

    def test_pesquisa_acento_case_e_apenas_ultimos_tres(self):
        for i in range(6):
            item = {
                "jogo": "Atlético Mineiro vs ABC",
                "event_id_modelo": i,
                "mercado_modelo": "Under 2.5 Golos",
                "odd_observada": 1.40 + i / 10,
            }
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item) + "\n")
        rep = self.rastreio.detalhe("ATLETICO")
        self.assertIn("Observações encontradas: 6 | últimas 3", rep)
        self.assertIn("1,90", rep)
        self.assertNotIn("1,40", rep)

    def test_termo_invalido_e_sem_resultados_sem_criar_ficheiro(self):
        self.assertIn("Usa /odds_rastreio_detalhe", self.rastreio.detalhe("A"))
        self.assertIn("Ainda não existem observações", self.rastreio.detalhe("Estudiantes"))
        self.assertFalse(self.path.exists())
        self.path.write_text('{"jogo":"RKC Waalwijk vs Volendam"}\n', encoding="utf-8")
        self.assertIn("Sem observações locais", self.rastreio.detalhe("Estudiantes"))

    def test_apenas_owner_pode_obter_detalhe(self):
        self.path.write_text(
            json.dumps({"jogo": "Estudiantes vs San Lorenzo", "mercado_modelo": "Vitória Casa"}) + "\n",
            encoding="utf-8"
        )
        b = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        b.owner_id = 43
        b.chat_id = 43
        b.username = None
        b._rastreio_odds = self.rastreio
        respostas = []
        b.enviar_mensagem = lambda chat_id, msg: respostas.append((chat_id, msg))
        b.processar_comando(22, "/odds_rastreio_detalhe Estudiantes", user_id=22)
        self.assertEqual(respostas, [])
        b.processar_comando(43, "/odds_rastreio_detalhe Estudiantes", user_id=43)
        self.assertEqual(len(respostas), 1)
        self.assertIn("DETALHE LOCAL", respostas[0][1])


if __name__ == "__main__":
    unittest.main()
