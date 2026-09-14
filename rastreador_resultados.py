"""Liquidação local de mercados simples por marcador declarado pelo utilizador.
Apenas tempo regulamentar com compensação. Não consulta resultados externos.
"""
class RastreadorResultados:
    def analisar_aposta(self, aposta, score):
        if not score or score.get('status') != 'finished':
            return None
        casa, fora = score.get('casa'), score.get('fora')
        if type(casa) is not int or type(fora) is not int or min(casa, fora) < 0:
            return None
        condicoes = {
            'Ambas Marcam': casa > 0 and fora > 0,
            'Over 2.5 Golos': casa + fora > 2.5,
            'Over 3.5 Golos': casa + fora > 3.5,
            'Vitória Casa': casa > fora,
            'Vitória Fora': fora > casa,
        }
        tipo = aposta.get('tipo')
        if tipo not in condicoes:
            return None
        return 'ganhou' if condicoes[tipo] else 'perdeu'
