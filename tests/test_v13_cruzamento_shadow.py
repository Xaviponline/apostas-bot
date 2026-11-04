"""Testes SHADOW: cruzamento mercado/idade e detalhe por snapshot oficial."""
import copy
import unittest
from datetime import datetime, timedelta, timezone

from main_competicoes import BotPremiumDiarioCompeticoes
from v13_cruzamento_shadow import _idade, relatorio_cruzamento_v13


BASE = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat()


def caso(i, mercado="Under 3.5 Golos", y=0, pnl=-1.0,
         age=1, p=.68, clv=None, data="2026-11-04"):
    capturada = BASE
    altered = BASE - timedelta(hours=age) if age is not None else None
    original = {
        "mercado": mercado, "probabilidade": p, "casa": f"Casa{i}", "fora": f"Fora{i}",
        "data_jogo": data, "odds_capturada_em": iso(capturada),
        "odds_atualizada_em": iso(altered) if altered else None,
        "diagnostico_modelo": {"liga_codigo": "eng.2"},
    }
    item = {"snapshot": i, "mercado": mercado, "resultado_binario": y,
            "lucro_unidades": pnl, "clv": clv, "odd_entrada": 1.90,
            "data_jogo": data}
    return original, item


class Reg:
    def __init__(self, items):
        self.dados = {"previsoes": [x[0] for x in items]}
        self.coorte = [x[1] for x in items]

    def metricas_v13_comercial(self):
        c = self.coorte
        total = sum(float(e["lucro_unidades"]) for e in c
                    if e.get("resultado_binario") in (0, 1)
                    and e.get("lucro_unidades") is not None)
        return {
            "coorte": c, "alvo": 50, "estado": "RECOLHA",
            "coorte_tamanho": len(c),
            "liquidadas": sum(e.get("resultado_binario") in (0, 1) for e in c),
            "clv_amostras": sum(e.get("clv") is not None for e in c),
            "lucro_unidades": total,
        }


class CruzamentoV13Tests(unittest.TestCase):
    def test_idades_e_limites_exatos(self):
        for delta, grupo in [
            (6, "ate6"), (6.00001, "6a24"), (24, "6a24"),
            (24.01, "mais24"), (-.0833333333333333, "ate6"),
            (-.1, "futura"), (None, "semhora"),
        ]:
            p, _ = caso(1, age=delta)
            self.assertEqual(_idade(p)[0], grupo)

    def test_disjoint_cross_reconciliado_e_pnl(self):
        it = [
            caso(1, age=1, y=0, pnl=-1., clv=-.01),
            caso(2, age=48, y=1, pnl=.8, clv=.04),
            caso(3, "Under 2.5 Golos", age=1, y=0, pnl=-1., clv=None),
            caso(4, "Over 2.5 Golos", age=None, y=None, pnl=None, clv=None),
        ]
        reg = Reg(it)
        before = copy.deepcopy(reg.dados)
        before_c = copy.deepcopy(reg.coorte)
        result = relatorio_cruzamento_v13(reg)
        self.assertIn("Coorte oficial 4/50 | validas 4 | inconsistencias 0", result)
        self.assertIn("Liquidadas 3 | pendentes 1", result)
        self.assertIn("Totais reconciliados", result)
        self.assertIn("Under 3.5 Golos — 2 entradas", result)
        self.assertIn("mais 24h: 1 ent/1 liq | 1/1 acertos | P/L +0,80u", result)
        self.assertIn("ate 6h: 1 ent/1 liq | 0/1 acertos | P/L -1,00u", result)
        self.assertIn("sem comparacao: 1 ent/0 liq", result)
        self.assertIn("CLV UNDER 3.5: n=2", result)
        self.assertEqual(reg.dados, before)
        self.assertEqual(reg.coorte, before_c)

    def test_under35_detalhes_e_dias_sem_recompensar_pendentes(self):
        it = [caso(1, age=1, y=0, pnl=-1, clv=-.02),
              caso(2, age=12, y=None, pnl=None, clv=None),
              caso(3, "Under 2.5 Golos", age=3, y=1, pnl=.7, clv=None)]
        reg = Reg(it)
        result = relatorio_cruzamento_v13(reg, "under35")
        self.assertIn("DETALHE: Under 3.5 Golos", result)
        self.assertIn("1 ent/1 liq", relatorio_cruzamento_v13(Reg([it[0]]), "under35"))
        self.assertIn("#1 2026-11-04 Casa1 vs Fora1 ❌", result)
        self.assertIn("#2 2026-11-04 Casa2 vs Fora2 ⏳", result)
        self.assertNotIn("#3 2026-11-04", result)
        self.assertIn("CLV falta", result)
        self.assertIn("pior dia: 2026-11-04 P/L -1,00u", result)

    def test_outlier_clv_median_and_trim(self):
        it = [caso(i+1, age=i+1, y=0, pnl=-1,
                   clv=.10 if i == 0 else -.01)
              for i in range(6)]
        rep = relatorio_cruzamento_v13(Reg(it), "under35")
        self.assertIn("positivos 1/6", rep)
        self.assertIn("mediana -1,0%", rep)
        self.assertIn("maior +10,0%", rep)
        self.assertIn("media excluindo maior -1,0%", rep)

    def test_invalid_duplicate_market_mismatch_quarantine(self):
        i = [caso(1), caso(2, "Over 2.5 Golos")]
        r = Reg(i)
        r.coorte = [r.coorte[0], r.coorte[0],
                    dict(r.coorte[1], mercado="Under 3.5 Golos")]
        rep = relatorio_cruzamento_v13(r)
        self.assertIn("inconsistencias 2", rep)
        self.assertIn("DADOS INCONSISTENTES", rep)
        self.assertIn("validas 1", rep)
        self.assertNotIn("Over 2.5 Golos —", rep)

    def test_missing_pnl_must_not_make_roi(self):
        i = [caso(1, y=0, pnl=None)]
        r = Reg(i)
        rep = relatorio_cruzamento_v13(r)
        self.assertIn("P/L valido 0/1; sem ROI", rep)
        self.assertIn("DADOS INCONSISTENTES", rep)

    def test_missing_clv_not_imputed_and_nan_rejected(self):
        it = [caso(1, clv=None), caso(2, clv=None, p=float("nan"))]
        rep = relatorio_cruzamento_v13(Reg(it), "under35")
        self.assertIn("CLV: sem fechos", rep)
        self.assertIn("CLV falta", rep)
        self.assertIn("Brier 0.462", rep)

    def test_owner_only_command_zero_mutations(self):
        r = Reg([caso(1)])
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.previsoes = r
        bot.owner_id, bot.chat_id, bot.username = 55, 55, None
        sent = []
        bot.enviar_mensagem = lambda chat_id, message: sent.append((chat_id, message))
        before = copy.deepcopy(r.dados)
        bot.processar_comando(56, "/v13_cruzamento", user_id=56)
        self.assertEqual(sent, [])
        bot.processar_comando(55, "/v13_cruzamento under35", user_id=55)
        self.assertEqual(len(sent), 1)
        self.assertIn("DETALHE: Under 3.5 Golos", sent[0][1])
        self.assertEqual(r.dados, before)

    def test_unknown_argument_uses_no_registro(self):
        class Toxic:
            def metricas_v13_comercial(self):
                raise AssertionError("should not read")
        self.assertIn("Formato:", relatorio_cruzamento_v13(Toxic(), "nao_sei"))

    def test_market_age_never_assumes_betano_executability(self):
        rep = relatorio_cruzamento_v13(Reg([caso(1)]))
        self.assertIn("nao e disponibilidade Betano", rep)
        self.assertIn("Sem HTTP/escrita", rep)


if __name__ == "__main__":
    unittest.main()
