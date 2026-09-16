"""Arranque de produção com cobertura V1 e histórico híbrido de competições."""
import logging
from collections import Counter

from estatisticas_forma_web import EstatisticasFormaWeb
from main_diario import RegistoPrevisoesDiario
from main_enriquecido import (
    AnalisadorInteligenteEnriquecido,
    BotPremiumDiarioDiagnostico,
    BuscadorJogosEnriquecido,
)


class BotPremiumDiarioCompeticoes(BotPremiumDiarioDiagnostico):
    def _executar_cobertura(self):
        base = super()._executar_cobertura()
        estatisticas = self.analisador.estatisticas
        diagnosticos = dict(getattr(estatisticas, "diagnostico_base", {}) or {})
        formas = dict(getattr(estatisticas, "_formas_globais", {}) or {})
        erros_forma = dict(getattr(estatisticas, "ultimo_erros_forma", {}) or {})
        if not diagnosticos and not formas and not erros_forma:
            return base

        linhas = []
        if diagnosticos:
            linhas.extend(["", "🔬 Base histórica taças/UEFA:"])
            for codigo, diag in sorted(diagnosticos.items()):
                if not isinstance(diag, dict):
                    continue
                jogos = int(diag.get("jogos") or 0)
                fonte = str(diag.get("fonte") or "-")
                if fonte in {"cache", "cache_sofascore"}:
                    origem = "SofaScore cache" if fonte == "cache_sofascore" else "cache"
                    linhas.append(f"• {codigo}: {jogos} jogos | {origem}")
                    continue
                if fonte == "sofascore":
                    paginas = int(diag.get("paginas") or 0)
                    linhas.append(
                        f"• {codigo}: {jogos} jogos | SofaScore | páginas {paginas}"
                    )
                    continue
                if fonte == "sofascore_indisponivel":
                    motivo = str(diag.get("motivo") or "sem detalhe")
                    linhas.append(
                        f"• {codigo}: 0 jogos | SofaScore indisponível | {motivo}"
                    )
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

        if formas or erros_forma:
            suficientes = sum(1 for jogos in formas.values() if len(jogos or []) >= 4)
            insuficientes = sum(1 for jogos in formas.values() if len(jogos or []) < 4)
            linhas.extend([
                "",
                "⚙️ Forma recente multicompetição:",
                f"• Equipas com ≥4 jogos: {suficientes} | insuficientes: {insuficientes} | erros: {len(erros_forma)}",
            ])
            if erros_forma:
                contagem = Counter(str(motivo or "indisponível") for motivo in erros_forma.values())
                resumo = ", ".join(f"{motivo} ×{n}" for motivo, n in sorted(contagem.items()))
                linhas.append(f"• Falhas: {resumo}")

        return base + "\n" + "\n".join(linhas)


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        buscador = BuscadorJogosEnriquecido()
        estatisticas = EstatisticasFormaWeb()
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
