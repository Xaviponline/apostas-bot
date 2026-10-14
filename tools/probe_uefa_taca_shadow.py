"""Sonda SHADOW so de leitura para base historica Champions e Taca.

Uso: python tools/probe_uefa_taca_shadow.py
Nao cria previsoes, nao consulta OddsPapi, nao grava qualquer ficheiro.
Executar apenas no CI de PR de testes; nunca no arranque de producao.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import json

from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_forma_web import EstatisticasFormaWeb


def executar():
    data_ref = datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    stats = EstatisticasFormaWeb(sofa_client=BuscadorJogosReais(enabled=True))
    resultados = []
    tudo_ok = True
    for codigo in ("uefa.champions", "por.taca.portugal"):
        registo = {"competicao": codigo, "minimo_requerido": stats.MIN_JOGOS_BASE}
        try:
            base = stats._fetch_liga(codigo, data_ref=data_ref)
            diagnostico = stats.diagnostico_base.get(codigo) or {}
            registo["fonte"] = diagnostico.get("fonte", "desconhecida")
            registo["jogos_finalizados"] = len(base)
            registo["valido"] = (
                len(base) >= stats.MIN_JOGOS_BASE
                and all(float(p["timestamp"]) < data_ref.timestamp() for p in base)
                and all(str(p["liga_codigo"]) == codigo for p in base)
            )
        except Exception as exc:
            # Nao incluir texto do erro: pode conter URLs ou payloads.
            registo["valido"] = False
            registo["erro_tipo"] = type(exc).__name__
            registo["fonte"] = (stats.diagnostico_base.get(codigo) or {}).get("fonte")
        resultados.append(registo)
        tudo_ok &= registo["valido"]
    print("SHADOW_FONTE_HISTORICA=" + json.dumps(resultados, ensure_ascii=False, sort_keys=True))
    return 0 if tudo_ok else 1


if __name__ == "__main__":
    raise SystemExit(executar())
