"""Arranque de produção com cobertura V1, taças e base histórica alargada."""
import logging

from estatisticas_espn_competicoes import EstatisticasESPNCompeticoes
from main_diario import RegistoPrevisoesDiario
from main_enriquecido import (
    AnalisadorInteligenteEnriquecido,
    BotPremiumDiarioDiagnostico,
    BuscadorJogosEnriquecido,
)


class BotPremiumDiarioCompeticoes(BotPremiumDiarioDiagnostico):
    def _executar_cobertura(self):
        base = super()._executar_cobertura()
        diagnosticos = dict(
            getattr(self.analisador.estatisticas, "diagnostico_base", {}) or {}
        )
        if not diagnosticos:
            return base

        linhas = ["", "🔬 Base histórica taças/UEFA:"]
        for codigo, diag in sorted(diagnosticos.items()):
            if not isinstance(diag, dict):
                continue
            jogos = int(diag.get("jogos") or 0)
            fonte = str(diag.get("fonte") or "-")
            if fonte == "cache":
                linhas.append(f"• {codigo}: {jogos} jogos | cache")
                continue
            blocos = int(diag.get("blocos") or 0)
            ok = int(diag.get("blocos_ok") or 0)
            falhas = int(diag.get("blocos_falha") or 0)
            motivos = ", ".join(str(x) for x in (diag.get("motivos") or []))
            extra = f" | {motivos}" if motivos else ""
            linhas.append(
                f"• {codigo}: {jogos} jogos | blocos OK {ok}/{blocos} | "
                f"falhas {falhas}{extra}"
            )
        return base + "\n" + "\n".join(linhas)


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        buscador = BuscadorJogosEnriquecido()
        estatisticas = EstatisticasESPNCompeticoes()
        analisador = AnalisadorInteligenteEnriquecido(
            buscador_jogos=buscador,
            estatisticas=estatisticas,
        )
        BotPremiumDiarioCompeticoes(
            buscador=buscador,
            analisador=analisador,
            previsoes=RegistoPrevisoesDiario(),
        ).buscar_atualizacoes()
    except Exception:
        logging.error(
            "Arranque ou escrita interrompidos. Verifica configuração, histórico "
            "e permissões; detalhes omitidos para proteger credenciais."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
