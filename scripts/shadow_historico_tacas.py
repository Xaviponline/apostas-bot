"""Verificacao SHADOW das fontes publicas de historico de Champions/Taca.

SEM TOKEN, SEM ODDS, SEM Railway, SEM escrita de snapshots, SEM apostas.
Nao altera filtros, modelo ou programa de producao.
"""
import sys
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from estatisticas_forma_web import EstatisticasFormaWeb


def main():
    agora = datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    fonte = EstatisticasFormaWeb()
    casos = [
        ("uefa.champions", "Liga dos Campeoes", 9),
        ("por.taca.portugal", "Taca de Portugal", 1),
    ]
    print("SHADOW | 14/10/2026 | baseline /cobertura de producao: 10 jogos cobertos, 0 com historico")
    print("SHADOW | so consulta duas competicoes publicas, sem acesso a producao ou ficheiros de cliente")
    sem_validacao = 0
    for codigo, nome, cobertos in casos:
        try:
            base = fonte._fetch_liga(codigo, agora)
            diag = fonte.diagnostico_base.get(codigo) or {}
            quantidade = len(base)
            procedencia = diag.get("fonte", "nao especificada")
            print(
                f"SHADOW | {nome} | jogos na agenda base={cobertos} | "
                f"historico={quantidade} | fonte={procedencia} | minimo={fonte.MIN_JOGOS_BASE}"
            )
            if quantidade < fonte.MIN_JOGOS_BASE:
                sem_validacao += 1
                print("SHADOW | historico insuficiente; nenhuma entrada comercial autorizada")
        except Exception as exc:
            sem_validacao += 1
            # So um motivo curto: remover URLs e sequencias longas do provider.
            diag = fonte.diagnostico_base.get(codigo) or {}
            motivo = str(diag.get("motivo") or "sem detalhe")
            motivo = re.sub(r"https?://[^\\s]+", "[URL]", motivo)[:160]
            print(
                f"SHADOW | {nome} | SEM VALIDACAO REAL | "
                f"fonte={diag.get('fonte','indisponivel')} | "
                f"erro={type(exc).__name__} | motivo={motivo}"
            )
    print("SHADOW | FIM | teste diagnostico: nao promove modelos nem altera coorte")
    if sem_validacao:
        print(f"SHADOW | BLOQUEADO: {sem_validacao}/{len(casos)} fontes nao validadas; nao promover")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
