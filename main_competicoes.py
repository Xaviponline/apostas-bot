"""Arranque de produção com cobertura V1, taças e base histórica alargada."""
import logging

from analisador_inteligente import AnalisadorInteligente
from estatisticas_espn_competicoes import EstatisticasESPNCompeticoes
from main_diario import RegistoPrevisoesDiario
from main_enriquecido import (
    AnalisadorInteligenteEnriquecido,
    BotPremiumDiarioDiagnostico,
    BuscadorJogosEnriquecido,
)


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        buscador = BuscadorJogosEnriquecido()
        estatisticas = EstatisticasESPNCompeticoes()
        analisador = AnalisadorInteligenteEnriquecido(
            buscador_jogos=buscador,
            estatisticas=estatisticas,
        )
        BotPremiumDiarioDiagnostico(
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
