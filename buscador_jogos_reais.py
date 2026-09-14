"""Interface reservada para uma fonte de dados validada.

O conector original não foi validado em produção. A versão de manutenção
não consulta endpoints incertos nem substitui dados em falta por dados inventados.
"""
class BuscadorJogosReais:
    estado = 'não configurado'

    def buscar_todos_jogos_hoje(self):
        return []

    def obter_forma_time(self, team_id):
        return None
