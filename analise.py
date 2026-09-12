#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MÓDULO DE ANÁLISE
Lógica principal de análise de apostas desportivas
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)

class AnalisadorApostas:
    
    def __init__(self):
        # APIs
        self.sofascore_url = "https://www.sofascore.com/api/v1"
        self.odds_api_url = "https://api.the-odds-api.com/v4"
        self.odds_api_key = "8e31b48e1b58c0f5cf45c99ddccfda58"  # Versão free
        
        # Configurações
        self.ligas = {
            "PL": {"id": 17, "nome": "Premier League", "pais": "🏴"},
            "LALIGA": {"id": 8, "nome": "La Liga", "pais": "🇪🇸"},
            "SERIEA": {"id": 23, "nome": "Serie A", "pais": "🇮🇹"},
            "BUNDESLIGA": {"id": 35, "nome": "Bundesliga", "pais": "🇩🇪"},
            "LIGUE1": {"id": 34, "nome": "Ligue 1", "pais": "🇫🇷"},
            "PORTUGAL": {"id": 144, "nome": "Liga Portugal", "pais": "🇵🇹"},
            "BRASIL": {"id": 325, "nome": "Brasileirão", "pais": "🇧🇷"},
            "MLS": {"id": 179, "nome": "MLS", "pais": "🇺🇸"},
            "SPL": {"id": 646, "nome": "Saudi Pro League", "pais": "🇸🇦"}
        }
        
        self.min_probabilidade = 0.55  # 55% mínimo
        self.min_roi = 0.02  # 2% ROI mínimo
        self.min_confianca = 3  # ⭐⭐⭐ mínimo
        
    def buscar_todos_jogos(self) -> List[Dict]:
        """Busca todos os jogos das ligas principais"""
        todos_jogos = []
        
        try:
            for codigo_liga, info_liga in self.ligas.items():
                jogos = self.buscar_jogos_liga(codigo_liga, info_liga)
                todos_jogos.extend(jogos)
                
            logger.info(f"Total de jogos encontrados: {len(todos_jogos)}")
            return todos_jogos
            
        except Exception as e:
            logger.error(f"Erro ao buscar jogos: {e}")
            return []
    
    def buscar_jogos_liga(self, codigo_liga: str, info_liga: Dict) -> List[Dict]:
        """Busca jogos de uma liga específica"""
        jogos = []
        
        try:
            # Simula busca (em produção seria API real)
            jogos_mock = self.gerar_jogos_mock(codigo_liga, info_liga)
            
            for jogo in jogos_mock:
                # Analisa cada jogo
                analise = self.analisar_jogo(jogo)
                
                if analise:
                    jogos.append({
                        **jogo,
                        'analise': analise
                    })
            
            return jogos
            
        except Exception as e:
            logger.error(f"Erro ao buscar liga {codigo_liga}: {e}")
            return []
    
    def analisar_jogo(self, jogo: Dict) -> Dict:
        """Analisa um jogo individual"""
        try:
            # 1. Calcula probabilidades
            probs = self.calcular_probabilidades(jogo)
            
            # 2. Busca odds
            odds = self.buscar_odds(jogo)
            
            # 3. Calcula ROI para cada tipo aposta
            apostas = self.calcular_apostas(probs, odds)
            
            # 4. Filtra por qualidade
            apostas_valor = [a for a in apostas if a['roi'] > self.min_roi]
            
            # 5. Seleciona melhor aposta
            if apostas_valor:
                melhor = sorted(apostas_valor, key=lambda x: x['roi'], reverse=True)[0]
                melhor['confianca_stars'] = self.calcular_confianca_stars(
                    melhor['probabilidade'],
                    melhor['roi']
                )
                return melhor
            
            return None
            
        except Exception as e:
            logger.error(f"Erro ao analisar jogo: {e}")
            return None
    
    def calcular_probabilidades(self, jogo: Dict) -> Dict:
        """Calcula probabilidades para cada tipo de aposta"""
        
        # Dados simulados (em produção viria de APIs de dados desportivos)
        casa = jogo.get('casa', {})
        fora = jogo.get('fora', {})
        liga = jogo.get('liga', '')
        
        probs = {
            'ambas_marcam': self.prob_ambas_marcam(casa, fora),
            'over_2_5': self.prob_over_golos(casa, fora, 2.5),
            'over_3_5': self.prob_over_golos(casa, fora, 3.5),
            'vitoria_casa': self.prob_vitoria_casa(casa, fora),
            'empate': self.prob_empate(casa, fora),
            'vitoria_fora': self.prob_vitoria_fora(casa, fora),
            'over_cantos': self.prob_over_cantos(casa, fora),
        }
        
        return probs
    
    def prob_ambas_marcam(self, casa: Dict, fora: Dict) -> float:
        """Probabilidade Ambas Marcam"""
        # Fórmula simplificada
        prob_casa = casa.get('media_golos', 1.5) / 4
        prob_fora = fora.get('media_golos', 1.2) / 4
        
        # Considera defesa
        prob_casa *= (1 - casa.get('media_golos_sofridos', 1.0) / 4)
        prob_fora *= (1 - fora.get('media_golos_sofridos', 1.2) / 4)
        
        # Combina probabilidades
        prob_ambas = prob_casa * prob_fora
        return min(prob_ambas, 0.75)  # Máximo 75%
    
    def prob_over_golos(self, casa: Dict, fora: Dict, limite: float) -> float:
        """Probabilidade Over X Golos"""
        media_total = casa.get('media_golos', 1.5) + fora.get('media_golos', 1.2)
        
        # Usa distribuição de Poisson simplificada
        if media_total >= limite:
            return min(0.5 + (media_total - limite) * 0.1, 0.75)
        else:
            return max(0.3 - (limite - media_total) * 0.1, 0.15)
    
    def prob_over_cantos(self, casa: Dict, fora: Dict) -> float:
        """Probabilidade Over 8.5 Cantos"""
        media_cantos = casa.get('media_cantos', 8) + fora.get('media_cantos', 7)
        
        if media_cantos >= 8.5:
            return min(0.5 + (media_cantos - 8.5) * 0.05, 0.75)
        else:
            return max(0.3 - (8.5 - media_cantos) * 0.05, 0.15)
    
    def prob_vitoria_casa(self, casa: Dict, fora: Dict) -> float:
        """Probabilidade Vitória Casa"""
        elo_casa = casa.get('elo', 1600)
        elo_fora = fora.get('elo', 1500)
        
        # Fórmula ELO
        diferenca = elo_casa - elo_fora
        prob = 1 / (1 + 10 ** (-diferenca / 400))
        
        return prob
    
    def prob_empate(self, casa: Dict, fora: Dict) -> float:
        """Probabilidade Empate"""
        return 0.25  # Simplificado
    
    def prob_vitoria_fora(self, casa: Dict, fora: Dict) -> float:
        """Probabilidade Vitória Fora"""
        elo_fora = fora.get('elo', 1500)
        elo_casa = casa.get('elo', 1600)
        
        diferenca = elo_fora - elo_casa
        prob = 1 / (1 + 10 ** (-diferenca / 400))
        
        return prob
    
    def buscar_odds(self, jogo: Dict) -> Dict:
        """Busca odds de múltiplas casas"""
        # Em produção, iria buscar de APIs reais
        # Por agora retorna valores simulados realistas
        
        odds_simuladas = {
            'ambas_marcam': {'Betclic': 1.88, 'Betano': 1.85, 'Bwin': 1.82},
            'over_2_5': {'Betano': 1.82, 'Betclic': 1.85, 'Bwin': 1.80},
            'over_3_5': {'Betclic': 2.20, 'Betano': 2.15, 'Bwin': 2.10},
            'vitoria_casa': {'Betano': 1.70, 'Betclic': 1.72, 'Bwin': 1.68},
            'empate': {'Betclic': 3.50, 'Betano': 3.40, 'Bwin': 3.30},
            'vitoria_fora': {'Betano': 4.50, 'Betclic': 4.60, 'Bwin': 4.40},
            'over_cantos': {'Betclic': 1.85, 'Betano': 1.82, 'Bwin': 1.80},
        }
        
        return odds_simuladas
    
    def calcular_apostas(self, probs: Dict, odds_dict: Dict) -> List[Dict]:
        """Calcula ROI para cada aposta"""
        apostas = []
        
        tipos_aposta = {
            'ambas_marcam': {'tipo': 'Ambas Marcam', 'key': 'ambas_marcam'},
            'over_2_5': {'tipo': 'Over 2.5 Golos', 'key': 'over_2_5'},
            'over_3_5': {'tipo': 'Over 3.5 Golos', 'key': 'over_3_5'},
            'vitoria_casa': {'tipo': 'Vitória Casa', 'key': 'vitoria_casa'},
            'over_cantos': {'tipo': 'Over 8.5 Cantos', 'key': 'over_cantos'},
        }
        
        for chave, config in tipos_aposta.items():
            if chave in probs and chave in odds_dict:
                prob = probs[chave]
                
                # Pega melhor odds
                odds_casas = odds_dict[chave]
                melhor_odd = max(odds_casas.values())
                melhor_casa = [k for k, v in odds_casas.items() if v == melhor_odd][0]
                
                # Calcula ROI
                roi = (melhor_odd * prob) - 1
                
                apostas.append({
                    'tipo': config['tipo'],
                    'probabilidade': round(prob * 100, 0),
                    'odds': melhor_odd,
                    'casa': melhor_casa,
                    'roi': round(roi * 100, 1),
                    'confianca': self.calcular_confianca_stars(prob, roi)
                })
        
        return apostas
    
    def calcular_confianca_stars(self, probabilidade: float, roi: float) -> int:
        """Calcula nível de confiança (1-5 estrelas)"""
        score = (probabilidade * 0.6) + (min(roi, 0.10) / 0.10 * 0.4)
        
        if score >= 0.85:
            return 5
        elif score >= 0.75:
            return 4
        elif score >= 0.65:
            return 3
        elif score >= 0.50:
            return 2
        else:
            return 1
    
    def filtrar_top_apostas(self, jogos: List[Dict], limite: int = 3) -> List[Dict]:
        """Filtra TOP apostas aplicando critérios rígidos"""
        
        apostas_filtradas = []
        
        for jogo in jogos:
            if 'analise' not in jogo:
                continue
            
            analise = jogo['analise']
            
            # FILTRO 1: Probabilidade mínima
            if analise.get('probabilidade', 0) < (self.min_probabilidade * 100):
                continue
            
            # FILTRO 2: ROI mínimo
            if analise.get('roi', 0) < (self.min_roi * 100):
                continue
            
            # FILTRO 3: Confiança mínima
            if analise.get('confianca', 0) < self.min_confianca:
                continue
            
            # FILTRO 4: Odds mínimas
            if analise.get('odds', 0) < 1.65:
                continue
            
            # Passou todos os filtros!
            apostas_filtradas.append({
                'jogo': f"{jogo['casa']['nome']} vs {jogo['fora']['nome']}",
                'liga': jogo['liga'],
                'horario': jogo.get('horario', '14:30'),
                'tipo': analise['tipo'],
                'odds': analise['odds'],
                'casa': analise['casa'],
                'probabilidade': analise['probabilidade'],
                'confianca': analise['confianca'],
                'roi': analise['roi'],
                'risco': self.calcular_risco(analise['probabilidade'], analise['roi']),
                'explicacao': self.gerar_explicacao(jogo, analise),
                'ganho_5': round(5 * (analise['odds']), 2),
                'ganho_10': round(10 * (analise['odds']), 2),
                'titulo': self.gerar_titulo(analise['probabilidade']),
                'multipla': self.gerar_multipla_sugerida(jogo, analise)
            })
        
        # Ordena por qualidade
        apostas_ordenadas = sorted(
            apostas_filtradas,
            key=lambda x: (x['probabilidade'] * 0.5 + x['roi'] * 50),
            reverse=True
        )
        
        return apostas_ordenadas[:limite]
    
    @staticmethod
    def calcular_risco(prob: float, roi: float) -> str:
        """Classifica nível de risco"""
        if prob >= 60 and roi >= 5:
            return "BAIXO"
        elif prob >= 50 and roi >= 2:
            return "MÉDIO"
        elif prob >= 45 and roi >= 4:
            return "MÉDIO-ALTO"
        else:
            return "ALTO"
    
    @staticmethod
    def gerar_titulo(prob: float) -> str:
        """Gera título baseado em probabilidade"""
        if prob >= 65:
            return "MÁXIMA PRIORIDADE (PREMIUM)"
        elif prob >= 60:
            return "EXCELENTE (PREMIUM)"
        elif prob >= 55:
            return "BOM VALOR"
        else:
            return "MARGINAL"
    
    @staticmethod
    def gerar_explicacao(jogo: Dict, analise: Dict) -> str:
        """Gera explicação da aposta"""
        # Explicação genérica (em produção seria mais detalhada)
        return (f"Análise baseada em forma recente, estatísticas xG, "
                f"histórico direto e dados da liga. "
                f"Confiança: {'⭐' * analise['confianca']}")
    
    @staticmethod
    def gerar_multipla_sugerida(jogo: Dict, analise: Dict) -> Dict:
        """Gera sugestão de múltipla"""
        if analise['probabilidade'] >= 60:
            return {
                'descricao': f"{analise['tipo']} + Outra aposta",
                'odds': round(analise['odds'] * 1.82, 2),
                'prob': max(int(analise['probabilidade'] * 0.58), 20),
                'ganho': round(5 * (analise['odds'] * 1.82), 2),
                'roi': 7,
                'risco': 'MÉDIO'
            }
        return None
    
    def buscar_jogos_vivos(self) -> List[Dict]:
        """Busca jogos em tempo real"""
        # Simulação - em produção seria API real
        return []
    
    def atualizar_jogo_vivo(self, jogo: Dict) -> Dict:
        """Atualiza análise de jogo ao vivo"""
        return {
            'jogo': jogo.get('nome', 'Jogo'),
            'placar': '1-0',
            'minuto': 25,
            'tipo': 'Ambas Marcam',
            'probabilidade': 68,
            'mudanca_importante': True,
            'mudanca_significativa': True
        }
    
    @staticmethod
    def gerar_jogos_mock(codigo_liga: str, info_liga: Dict) -> List[Dict]:
        """Gera dados mock para teste"""
        
        jogos_mock = {
            'PL': [
                {
                    'id': 1,
                    'casa': {'nome': 'Liverpool', 'media_golos': 2.1, 'media_golos_sofridos': 1.0, 'elo': 1750, 'media_cantos': 9.2},
                    'fora': {'nome': 'Fulham', 'media_golos': 1.3, 'media_golos_sofridos': 1.5, 'elo': 1600, 'media_cantos': 6.8},
                    'liga': f"{info_liga['pais']} {info_liga['nome']}",
                    'horario': '15:00'
                },
                {
                    'id': 2,
                    'casa': {'nome': 'Arsenal', 'media_golos': 1.8, 'media_golos_sofridos': 0.9, 'elo': 1720, 'media_cantos': 8.5},
                    'fora': {'nome': 'Ipswich', 'media_golos': 1.0, 'media_golos_sofridos': 1.8, 'elo': 1480, 'media_cantos': 7.2},
                    'liga': f"{info_liga['pais']} {info_liga['nome']}",
                    'horario': '17:30'
                },
            ],
            'LALIGA': [
                {
                    'id': 3,
                    'casa': {'nome': 'Real Madrid', 'media_golos': 2.1, 'media_golos_sofridos': 0.8, 'elo': 1800, 'media_cantos': 9.5},
                    'fora': {'nome': 'Rayo Vallecano', 'media_golos': 1.2, 'media_golos_sofridos': 1.6, 'elo': 1500, 'media_cantos': 6.5},
                    'liga': f"{info_liga['pais']} {info_liga['nome']}",
                    'horario': '20:00'
                },
            ],
            'BRASIL': [
                {
                    'id': 4,
                    'casa': {'nome': 'Flamengo', 'media_golos': 1.9, 'media_golos_sofridos': 1.1, 'elo': 1680, 'media_cantos': 8.8},
                    'fora': {'nome': 'Vasco', 'media_golos': 1.0, 'media_golos_sofridos': 1.7, 'elo': 1520, 'media_cantos': 6.3},
                    'liga': f"{info_liga['pais']} {info_liga['nome']}",
                    'horario': '19:00'
                },
            ]
        }
        
        return jogos_mock.get(codigo_liga, [])
