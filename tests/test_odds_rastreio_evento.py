"""Consulta forense de odds por partida + data local + mercado exato (sem HTTP)."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from main_competicoes import BotPremiumDiarioCompeticoes
from odds_rastreio import RastreioOdds
from odds_rastreio_evento import relatorio_rastreio_evento, _data_jogo, _partida

PT = ZoneInfo("Europe/Lisbon")


def item(jogo="Aston Villa vs Viking FK", dia="2026-10-21",
         mercado="Under 3.5 Golos", odd=2.07, n=0):
    ts = datetime.fromisoformat(dia+"T20:00:00").replace(tzinfo=PT).timestamp()
    return {
        "jogo": jogo, "timestamp_jogo": ts, "mercado_modelo": mercado,
        "event_id_modelo": "match-21", "odd_observada": odd,
        "observado_em": "2026-10-21T17:00:00Z",
        "fonte": "OddsPapi", "fixture_id_fonte": "fx21",
        "mercado_id_fonte": "m21", "mercado_nome_fonte": "Total Goals",
        "linha_fonte": 3.5, "selecao_nome_fonte": "Under",
        "outcome_ref_fonte": "under35",
        "resultado_associacao": "unica",
        "diagnostico": "", "liga_modelo": "UEFA Conference League",
        "liga_fonte_odds": "UEFA Conference League",
        "periodo_fonte": "fulltime",
        "inicio_fonte_fixture": "2026-10-21T19:00:00Z",
        "odds_atualizada_em": "2026-10-21T15:40:00Z",
        "n": n,
    }


class RastreioEventoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "odds_rastreio.jsonl"
        self.rastreio = RastreioOdds(self.path)

    def gravar(self, *items):
        with self.path.open("a", encoding="utf-8") as f:
            for i in items:
                f.write(json.dumps(i, ensure_ascii=False)+"\n")

    def consulta(self, texto="2026-10-21 Aston Villa vs Viking FK | Under 3.5 Golos"):
        return relatorio_rastreio_evento(self.rastreio, texto)

    def test_jogo_e_data_exatos_excluem_eventos_recentes_com_mesmas_equipas(self):
        antigo=item()
        recente=item("Galatasaray vs Aston Villa","2026-11-24","Over 2.5 Golos",1.82)
        recente2=item("Tromso vs Viking FK","2026-11-21","Vitória Fora",None)
        outra_data=item(dia="2026-11-24",odd=1.30)
        outro_mercado=item(mercado="Over 2.5 Golos", odd=1.42)
        self.gravar(antigo,recente,recente2,outra_data,outro_mercado)
        antes=self.path.read_bytes()
        texto=self.consulta()
        self.assertIn("Observações jogo/data: 2 | mercado pedido: 1",texto)
        self.assertIn("Under 3.5 Golos (1)",texto)
        self.assertIn("Over 2.5 Golos (1)",texto)
        self.assertIn("Odd: 2,07",texto)
        self.assertIn("Fixture fornecedor: fx21",texto)
        self.assertNotIn("Galatasaray",texto)
        self.assertNotIn("Tromso",texto)
        self.assertNotIn("Odd: 1,42",texto)
        self.assertEqual(self.path.read_bytes(),antes)

    def test_sem_filtro_mercado_inclui_ambos_e_sem_identidade_validada(self):
        self.gravar(item(),item(mercado="Over 2.5 Golos",odd=1.35))
        texto=self.consulta("2026-10-21 Aston Villa vs Viking FK")
        self.assertIn("mercado pedido: 2",texto)
        self.assertIn("Odd: 2,07",texto)
        self.assertIn("Odd: 1,35",texto)
        self.assertIn("NÃO valida por si só",texto)

    def test_nome_acento_caixa_e_separador_da_partida(self):
        self.gravar(item(jogo="Tromsø vs Viking FK"))
        t=self.consulta("2026-10-21 TROMSo vs Viking FK | Under 3.5 Golos")
        self.assertIn("mercado pedido: 1",t)
        self.assertIsNone(_partida("Viking FK"))
        self.assertEqual(_partida("Tromsø vs Viking FK"),_partida("Tromso × Viking FK"))

    def test_sem_correspondencia_nao_atesta_inexistencia_preco(self):
        self.gravar(item(jogo="Tromso vs Viking FK",dia="2026-11-21"))
        t=self.consulta()
        self.assertIn("Observações jogo/data: 0",t)
        self.assertIn("não disponibilizou a odd",t)
        self.assertNotIn("Odd: 2,07",t)

    def test_existe_jogo_mas_outro_mercado(self):
        self.gravar(item(mercado="Over 2.5 Golos",odd=1.70))
        t=self.consulta()
        self.assertIn("Observações jogo/data: 1 | mercado pedido: 0",t)
        self.assertIn("nenhum para o mercado exato",t)
        self.assertIn("Over 2.5 Golos (1)",t)

    def test_legacy_sem_timestamp_nao_inferir_data_por_observacao(self):
        legado=item()
        legado.pop("timestamp_jogo")
        self.gravar(legado)
        t=self.consulta()
        self.assertIn("Observações jogo/data: 0",t)
        self.assertIn("Mesmo nome mas sem data do jogo no registo: 1",t)
        self.assertNotIn("Odd: 2,07",t)

    def test_max_cinco_ultimas_sem_mudar_historico(self):
        self.gravar(*(item(odd=1.25 + .10*i,n=i) for i in range(9)))
        antes=self.path.read_bytes()
        t=self.consulta()
        self.assertIn("Observações jogo/data: 9 | mercado pedido: 9",t)
        self.assertIn("Últimas 5 observações",t)
        self.assertIn("Odd: 2,05",t)
        self.assertNotIn("Odd: 1,25",t)
        self.assertEqual(self.path.read_bytes(),antes)

    def test_input_invalido_sem_escrita(self):
        for arg in (
            "Aston Villa", "2026-20-21 Aston Villa vs Viking FK",
            "2026-10-21 Aston Villa", "2026-10-21 Aston Villa vs",
            "2026-10-21 Aston Villa vs Viking FK |",
            "2026-10-21 Aston Villa vs Viking FK | Under | Over",
        ):
            self.assertIn("Uso: /odds_rastreio_evento",self.consulta(arg))
        self.assertFalse(self.path.exists())

    def test_ficheiro_ausente_e_corrompido_falha_fechado(self):
        self.assertIn("não existem observações locais",self.consulta())
        self.gravar(item())
        with self.path.open("a",encoding="utf-8") as f:
            f.write("{abc")
        antes=self.path.read_bytes()
        with self.assertRaises((ValueError,TypeError)):
            self.consulta()
        self.assertEqual(self.path.read_bytes(),antes)

    def test_symlink_nao_consultar(self):
        origem=self.path.with_name("fonte.jsonl")
        origem.write_text(json.dumps(item())+"\n",encoding="utf-8")
        self.path.symlink_to(origem)
        with self.assertRaises(RuntimeError):
            self.consulta()

    def test_data_portugal_verao_vs_utc_e_sentinelas(self):
        ts=datetime(2026,10,21,0,30,tzinfo=PT).timestamp()
        d=item()
        d["timestamp_jogo"]=ts
        self.assertEqual(_data_jogo(d),"2026-10-21")
        d["timestamp_jogo"]=True
        self.assertIsNone(_data_jogo(d))
        d["timestamp_jogo"]=float("nan")
        self.assertIsNone(_data_jogo(d))

    def test_comando_so_owner_e_sem_requests(self):
        self.gravar(item())
        bot=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id=bot.chat_id=43
        bot.username=None
        bot._rastreio_odds=self.rastreio
        bot.enviar_mensagem=Mock()
        cmd="/odds_rastreio_evento 2026-10-21 Aston Villa vs Viking FK | Under 3.5 Golos"
        bot.processar_comando(44,cmd,user_id=44)
        bot.processar_comando(43,cmd,user_id=44)
        bot.enviar_mensagem.assert_not_called()
        bot.processar_comando(43,cmd,user_id=43)
        bot.enviar_mensagem.assert_called_once()
        texto=bot.enviar_mensagem.call_args.args[1]
        self.assertIn("JOGO/DATA EXATOS",texto)


if __name__=="__main__":
    unittest.main()
