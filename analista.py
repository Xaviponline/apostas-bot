#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANALISTA DE APOSTAS
Análise profissional com filtros rígidos
"""

from datetime import datetime
from typing import List, Dict

class AnalistaApostas:
    
    def __init__(self):
        self.min_probabilidade = 0.55  # 55% mínimo
        self.min_roi = 0.02  # 2% ROI mínimo
        self.min_confianca = 3  # ⭐⭐⭐ mínimo
        self.min_odds = 1.65  # Odds mínimas
        
        self.ligas = {
            "PL": "🏴 Premier League",
            "LALIGA": "🇪🇸 La Liga",
            "SERIEA": "🇮🇹 Serie A",
            "BUNDESLIGA": "🇩🇪 Bundesliga",
            "LIGUE1": "🇫🇷 Ligue 1",
            "PORTUGAL": "🇵🇹 Liga Portugal",
            "BRASIL": "🇧🇷 Brasileirão",
            "MLS": "🇺🇸 MLS",
            "SPL": "🇸🇦 Saudi Pro League"
        }
    
    def gerar_jogos_dia(self) -> List[Dict]:
        """Gera jogos do dia para análise (simulado)"""
        jogos = [
            {
                "id": 1,
                "jogo": "Liverpool vs Fulham",
                "liga": "PL",
                "horario": "15:00",
                "casa": {"nome": "Liverpool", "media_golos": 2.1, "elo": 1750},
                "fora": {"nome": "Fulham", "media_golos": 1.3, "elo": 1600}
            },
            {
                "id": 2,
                "jogo": "Real Madrid vs Rayo",
                "liga": "LALIGA",
                "horario": "20:00",
                "casa": {"nome": "Real Madrid", "media_golos": 2.1, "elo": 1800},
                "fora": {"nome": "Rayo", "media_golos": 1.2, "elo": 1500}
            },
            {
                "id": 3,
                "jogo": "Arsenal vs Ipswich",
                "liga": "PL",
                "horario": "17:30",
                "casa": {"nome": "Arsenal", "media_golos": 1.8, "elo": 1720},
                "fora": {"nome": "Ipswich", "media_golos": 1.0, "elo": 1480}
            },
            {
                "id": 4,
                "jogo": "Flamengo vs Vasco",
                "liga": "BRASIL",
                "horario": "19:00",
                "casa": {"nome": "Flamengo", "media_golos": 1.9, "elo": 1680},
                "fora": {"nome": "Vasco", "media_golos": 1.0, "elo": 1520}
            },
            {
                "id": 5,
                "jogo": "Bayern Munich vs Frankfurt",
                "liga": "BUNDESLIGA",
                "horario": "18:30",
                "casa": {"nome": "Bayern", "media_golos": 2.3, "elo": 1850},
                "fora": {"nome": "Frankfurt", "media_golos": 1.1, "elo": 1550}
            },
            {
                "id": 6,
                "jogo": "PSG vs Toulouse",
                "liga": "LIGUE1",
                "horario": "20:45",
                "casa": {"nome": "PSG", "media_golos": 2.0, "elo": 1800},
                "fora": {"nome": "Toulouse", "media_golos": 0.9, "elo": 1450}
            },
            {
                "id": 7,
                "jogo": "Napoli vs Roma",
                "liga": "SERIEA",
                "horario": "20:45",
                "casa": {"nome": "Napoli", "media_golos": 1.7, "elo": 1700},
                "fora": {"nome": "Roma", "media_golos": 1.2, "elo": 1580}
            },
            {
                "id": 8,
                "jogo": "Benfica vs Gil Vicente",
                "liga": "PORTUGAL",
                "horario": "18:00",
                "casa": {"nome": "Benfica", "media_golos": 1.8, "elo": 1750},
                "fora": {"nome": "Gil Vicente", "media_golos": 0.8, "elo": 1400}
            },
        ]
        return jogos
    
    def analisar_jogo(self, jogo: Dict) -> Dict:
        """Analisa um jogo individual"""
        
        casa = jogo["casa"]
        fora = jogo["fora"]
        
        # Calcula probabilidades para cada tipo
        apostas = []
        
        # 1. Ambas Marcam
        prob_ambas = self.calcular_ambas_marcam(casa, fora)
        odds_ambas = 1.85 + (0.03 * (prob_ambas - 0.58))
        roi_ambas = (odds_ambas * prob_ambas) - 1
        
        apostas.append({
            "tipo": "Ambas Marcam",
            "probabilidade": prob_ambas,
            "odds": round(odds_ambas, 2),
            "roi": round(roi_ambas * 100, 1),
            "confianca": self.calcular_confianca(prob_ambas, roi_ambas),
            "risco": self.calcular_risco(prob_ambas, roi_ambas)
        })
        
        # 2. Over 2.5 Golos
        prob_over = self.calcular_over_golos(casa, fora, 2.5)
        odds_over = 1.82 + (0.02 * (prob_over - 0.58))
        roi_over = (odds_over * prob_over) - 1
        
        apostas.append({
            "tipo": "Over 2.5 Golos",
            "probabilidade": prob_over,
            "odds": round(odds_over, 2),
            "roi": round(roi_over * 100, 1),
            "confianca": self.calcular_confianca(prob_over, roi_over),
            "risco": self.calcular_risco(prob_over, roi_over)
        })
        
        # 3. Vitória Casa
        prob_vitoria = self.calcular_vitoria_casa(casa, fora)
        odds_vitoria = 2.5 - (prob_vitoria * 1.5)
        roi_vitoria = (odds_vitoria * prob_vitoria) - 1
        
        apostas.append({
            "tipo": f"Vitória {casa['nome']}",
            "probabilidade": prob_vitoria,
            "odds": round(odds_vitoria, 2),
            "roi": round(roi_vitoria * 100, 1),
            "confianca": self.calcular_confianca(prob_vitoria, roi_vitoria),
            "risco": self.calcular_risco(prob_vitoria, roi_vitoria)
        })
        
        # 4. Over 3.5 Golos
        prob_over35 = self.calcular_over_golos(casa, fora, 3.5)
        odds_over35 = 2.15 + (0.02 * (prob_over35 - 0.45))
        roi_over35 = (odds_over35 * prob_over35) - 1
        
        apostas.append({
            "tipo": "Over 3.5 Golos",
            "probabilidade": prob_over35,
            "odds": round(odds_over35, 2),
            "roi": round(roi_over35 * 100, 1),
            "confianca": self.calcular_confianca(prob_over35, roi_over35),
            "risco": self.calcular_risco(prob_over35, roi_over35)
        })
        
        return {
            "jogo": jogo["jogo"],
            "liga": self.ligas.get(jogo["liga"], jogo["liga"]),
            "horario": jogo["horario"],
            "apostas": apostas
        }
    
    def calcular_ambas_marcam(self, casa: Dict, fora: Dict) -> float:
        """Probabilidade Ambas Marcam"""
        prob = (casa["media_golos"] / 4) * (fora["media_golos"] / 4)
        return min(prob, 0.75)
    
    def calcular_over_golos(self, casa: Dict, fora: Dict, limite: float) -> float:
        """Probabilidade Over X Golos"""
        media = casa["media_golos"] + fora["media_golos"]
        if media >= limite:
            return min(0.5 + (media - limite) * 0.1, 0.75)
        return max(0.3 - (limite - media) * 0.1, 0.15)
    
    def calcular_vitoria_casa(self, casa: Dict, fora: Dict) -> float:
        """Probabilidade Vitória Casa"""
        elo_diff = casa["elo"] - fora["elo"]
        prob = 1 / (1 + 10 ** (-elo_diff / 400))
        return prob
    
    def calcular_confianca(self, prob: float, roi: float) -> int:
        """Calcula confiança em estrelas (1-5)"""
        score = (prob * 0.6) + (min(roi, 0.10) / 0.10 * 0.4)
        if score >= 0.85:
            return 5
        elif score >= 0.75:
            return 4
        elif score >= 0.65:
            return 3
        elif score >= 0.50:
            return 2
        return 1
    
    @staticmethod
    def calcular_risco(prob: float, roi: float) -> str:
        """Classifica risco"""
        if prob >= 0.60 and roi >= 0.05:
            return "🟢 BAIXO"
        elif prob >= 0.50 and roi >= 0.02:
            return "🟡 MÉDIO"
        elif prob >= 0.45 and roi >= 0.04:
            return "🟠 MÉDIO-ALTO"
        return "🔴 ALTO"
    
    def filtrar_apostas(self, analise_dia: Dict) -> List[Dict]:
        """Filtra apostas que passam nos parâmetros rígidos"""
        
        apostas_validas = []
        
        for jogo_analise in analise_dia:
            jogo = jogo_analise["jogo"]
            liga = jogo_analise["liga"]
            horario = jogo_analise["horario"]
            
            for aposta in jogo_analise["apostas"]:
                # FILTROS RÍGIDOS
                if aposta["probabilidade"] < self.min_probabilidade:
                    continue
                if aposta["roi"] < (self.min_roi * 100):
                    continue
                if aposta["confianca"] < self.min_confianca:
                    continue
                if aposta["odds"] < self.min_odds:
                    continue
                
                # Passou todos os filtros!
                apostas_validas.append({
                    "jogo": jogo,
                    "liga": liga,
                    "horario": horario,
                    "tipo": aposta["tipo"],
                    "probabilidade": int(aposta["probabilidade"] * 100),
                    "odds": aposta["odds"],
                    "roi": aposta["roi"],
                    "confianca": aposta["confianca"],
                    "risco": aposta["risco"]
                })
        
        # Ordena por qualidade
        return sorted(apostas_validas, 
                     key=lambda x: (x["probabilidade"] * 0.5 + x["roi"] * 50),
                     reverse=True)
    
    def gerar_relatorio(self) -> str:
        """Gera relatório completo das apostas do dia"""
        
        # Analisa todos os jogos
        jogos = self.gerar_jogos_dia()
        analise_dia = [self.analisar_jogo(jogo) for jogo in jogos]
        
        # Filtra apostas válidas
        apostas_validas = self.filtrar_apostas(analise_dia)
        
        if not apostas_validas:
            return "❌ Nenhuma aposta com valor encontrada hoje"
        
        # Formata relatório
        relatorio = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        relatorio += "🎯 ANÁLISE PREMIUM - " + datetime.now().strftime("%d/%m/%Y") + "\n"
        relatorio += f"📊 {len(apostas_validas)} APOSTAS COM VALOR\n"
        relatorio += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for idx, aposta in enumerate(apostas_validas, 1):
            relatorio += f"#{idx} {aposta['risco']}\n"
            relatorio += f"⚽ {aposta['jogo']} ({aposta['horario']})\n"
            relatorio += f"🏆 {aposta['liga']}\n"
            relatorio += f"💰 {aposta['tipo']} @{aposta['odds']}\n"
            relatorio += f"📈 {aposta['probabilidade']}% | ROI +{aposta['roi']}%\n"
            relatorio += f"⭐ Confiança: {'⭐' * aposta['confianca']}\n"
            relatorio += "─────────────────────────────────\n\n"
        
        relatorio += f"✅ Total: {len(apostas_validas)} apostas analisadas\n"
        relatorio += f"📈 ROI Médio: +{sum(a['roi'] for a in apostas_validas) / len(apostas_validas):.1f}%\n"
        
        return relatorio
