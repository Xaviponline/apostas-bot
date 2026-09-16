"""Entrypoint de produção com recolha resiliente do histórico ESPN."""
import logging

from estatisticas_espn_resiliente import EstatisticasESPNResiliente
from main_diario import BotPremiumDiario, RegistoPrevisoesDiario


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        bot = BotPremiumDiario(previsoes=RegistoPrevisoesDiario())
        # Mantém o mesmo modelo V1; substitui apenas a forma de recolher o histórico.
        bot.analisador.estatisticas = EstatisticasESPNResiliente()
        bot.buscar_atualizacoes()
    except Exception:
        logging.error(
            "Arranque ou escrita interrompidos. Verifica configuração, histórico "
            "e permissões; detalhes omitidos para proteger credenciais."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
