"""Provas do painel SHADOW /odds_falhas por jogo, sem HTTP nem alterações."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from main_competicoes import BotPremiumDiarioCompeticoes
from odds_falhas_shadow import gerar_painel_falhas
from odds_rastreio import RastreioOdds


TZ_PT = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2026, 10, 16, 18, 0, tzinfo=TZ_PT)
TS = datetime(2026, 10, 16, 19, 0, tzinfo=TZ_PT).timestamp()


def previsao(rank, casa="Helmond Sport", fora="NAC Breda", mercado="Over 2.5 Golos",
             odd=None, fonte="OddsPapi / Betano PT", minimo=1.52):
    return {
        "modelo_versao": "V1.2", "data_jogo": "2026-10-16",
        "ranking_modelo": rank, "timestamp_jogo": TS,
        "event_id": 1000 + rank, "liga": "Eerste Divisie",
        "casa": casa, "fora": fora, "mercado": mercado,
        "odd_real": odd, "odd_minima": minimo, "odds_fonte": fonte,
    }


def selecao(p, diag=None, odd=None, alerta=None, meta=None, ts=None):
    s = {
        "jogo": {
            "id": p["event_id"], "timestamp": TS if ts is None else ts,
            "casa": p["casa"], "fora": p["fora"], "liga": p["liga"],
        },
        "mercado": p["mercado"],
    }
    if diag is not None:
        s["_odds_diag"] = diag
    if odd is not None:
        s["odd_real"] = odd
    if alerta:
        s["_odds_alertas"] = list(alerta)
    if meta:
        s["_rastreio_odds"] = meta
        s["odds_event_id"] = "fixture-123"
    return s


class OddsFalhasShadowTests(unittest.TestCase):
    def test_diags_por_jogo_e_estado_inconclusivo(self):
        p1 = previsao(1, casa="Stade Laval", fora="Clermont Foot", minimo=1.5)
        p2 = previsao(2, casa="Rapid Vienna", fora="TSV Hartberg",
                       mercado="Ambas Marcam", minimo=1.51)
        p3 = previsao(3, casa="Heerenveen", fora="Excelsior", mercado="Under 3.5 Golos")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "odds_rastreio.jsonl"
            hist = RastreioOdds(path)
            hist.registar([
                selecao(p1, diag="evento_nao_encontrado"),
                selecao(p2, diag="betano_sem_odds_no_evento"),
                selecao(p3, diag="fixture_omitido_no_lote"),
            ])
            original = path.read_bytes()
            copia = copy.deepcopy([p1, p2, p3])
            painel = gerar_painel_falhas(copia, path, agora=AGORA)
            self.assertIn("#1", painel)
            self.assertIn("jogo não encontrado na lista consultada", painel)
            self.assertIn("fornecedor indicou Betano sem odds", painel)
            self.assertIn("fixture omitido no lote — inconclusivo", painel)
            detalhe = gerar_painel_falhas(copia, path, "2", agora=AGORA)
            self.assertIn("bookmaker", detalhe)
            self.assertIn("Sem odd", detalhe)
            self.assertIn("ID de fixture na fonte: não guardado", detalhe)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(copia, [p1, p2, p3])

    def test_odd_historica_abaixo_minimo_nao_e_value(self):
        p = previsao(4, odd=1.35)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rastreio.jsonl"
            RastreioOdds(path).registar([
                selecao(p, odd=1.35, meta={
                    "market_id": "M100", "outcome_ref": "OUT11",
                    "association": "conferida",
                }),
                selecao(p, diag="odds_http_404"),
            ])
            detalhe = gerar_painel_falhas([p], path, "4", agora=AGORA)
            self.assertIn("Odd inicial 1,35 abaixo do mínimo 1,52", detalhe)
            self.assertIn("erro HTTP 404 — inconclusivo", detalhe)
            self.assertIn("Odd observada em rastreio: 1,35", detalhe)
            self.assertIn("não comprova", gerar_painel_falhas([
                previsao(5, odd=1.78)], path, "5", agora=AGORA))
            self.assertNotIn("VALOR AGORA", detalhe)

    def test_nome_hora_mercado_e_id_devem_coincidir(self):
        p = previsao(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rastreio.jsonl"
            RastreioOdds(path).registar([
                selecao(p, diag="evento_nao_encontrado", ts=TS + 5 * 3600),
                selecao({**p, "event_id": 999}, diag="odds_http_400"),
                selecao({**p, "casa": "Outra Equipa"}, diag="odds_http_401"),
                selecao({**p, "mercado": "Vitória Casa"}, diag="odds_http_403"),
            ])
            text = gerar_painel_falhas([p], path, "1", agora=AGORA)
            self.assertIn("Sem observações detalhadas associadas", text)
            self.assertNotIn("HTTP 400", text)
            self.assertNotIn("HTTP 401", text)
            self.assertNotIn("HTTP 403", text)

    def test_odd_ou_fonte_nao_verificada_nao_passa_a_confirmada(self):
        p = previsao(1, odd=1.9, fonte="Outra fonte")
        t = gerar_painel_falhas([p], None, "1", agora=AGORA)
        self.assertIn("sem confirmação no snapshot", t)
        self.assertIn("Ficheiro de rastreio não configurado", t)

    def test_rastreio_invalido_falha_fechado_sem_usar_parcial(self):
        p = previsao(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dados.jsonl"
            RastreioOdds(path).registar([selecao(p, diag="evento_nao_encontrado")])
            with path.open("a") as f:
                f.write("nao e json\n")
            text = gerar_painel_falhas([p], path, "1", agora=AGORA)
            self.assertIn("rastreio local ilegível", text.casefold())
            self.assertNotIn("jogo não encontrado na lista", text)
            self.assertEqual(path.read_text().splitlines()[-1], "nao e json")

    def test_alertas_sao_lista_de_codigos_autorizados(self):
        p = previsao(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rastreio.jsonl"
            RastreioOdds(path).registar([
                selecao(p, diag="fixture_omitido_no_lote",
                        alerta=["horario_divergente", "segredo-indesejado"]),
            ])
            t = gerar_painel_falhas([p], path, "1", agora=AGORA)
            self.assertIn("divergência de horário sinalizada", t)
            self.assertNotIn("segredo-indesejado", t)

    def test_owner_apenas_e_sem_chamadas_odds_ou_escrita(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "previsoes.json"
            path.write_text('{"versao":1,"previsoes":[]}', encoding="utf-8")
            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.owner_id = 42
            bot.chat_id = 42
            bot.username = None
            hoje = datetime.now(TZ_PT)
            p = previsao(1)
            p["data_jogo"] = hoje.date().isoformat()
            p["timestamp_jogo"] = hoje.timestamp() + 3*3600
            bot.previsoes = SimpleNamespace(path=path, dados={"previsoes": [p]})
            before = copy.deepcopy(bot.previsoes.dados)
            output = []
            bot.enviar_mensagem = lambda chat, msg: output.append((chat, msg))
            with patch("odds_auditoria.AuditoriaOdds.enriquecer",
                       side_effect=AssertionError("OddsPapi não pode ser consultada")):
                bot.processar_comando(42, "/odds_falhas", user_id=42)
                bot.processar_comando(42, "/odds_falhas 1", user_id=42)
                bot.processar_comando(43, "/odds_falhas", user_id=43)
            self.assertEqual(len(output), 2)
            self.assertIn("FALHAS DE ODDS POR JOGO", output[0][1])
            self.assertIn("RANKING" if False else "#1", output[1][1])
            self.assertEqual(before, bot.previsoes.dados)
            self.assertFalse((Path(tmp) / "odds_rastreio.jsonl").exists())
            self.assertEqual(path.read_text(), '{"versao":1,"previsoes":[]}')

    def test_ranking_repetido_e_ausencia_de_previsoes(self):
        p = previsao(1)
        self.assertIn("repetido", gerar_painel_falhas([p, copy.deepcopy(p)], None, "1", agora=AGORA))
        self.assertIn("Não existem previsões", gerar_painel_falhas([], None, agora=AGORA))
        self.assertIn("Formato", gerar_painel_falhas([p], None, "2 forma", agora=AGORA))


if __name__ == "__main__":
    unittest.main()
