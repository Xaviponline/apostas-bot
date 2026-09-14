"""Recomendações suspensas até integrar odds e um modelo validado."""
from datetime import datetime
from zoneinfo import ZoneInfo

class AnalisadorInteligente:
    motivo_indisponivel = (
        'A análise automática está suspensa: falta uma fonte validada de jogos, '
        'estatísticas e odds da Betano, e um modelo de probabilidades avaliado. '
        'Não são geradas apostas nem probabilidades de substituição. '
        'Podes registar apostas que já fizeste com /add_aposta e acompanhar /resultados.'
    )

    def __init__(self, buscador_jogos=None):
        self.buscador = buscador_jogos

    @property
    def data_hoje(self):
        return datetime.now(ZoneInfo('Europe/Lisbon')).strftime('%d/%m/%Y')

    def gerar_todas_apostas(self, jogos):
        return []
