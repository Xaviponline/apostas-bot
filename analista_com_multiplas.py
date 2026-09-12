#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANALISTA COM MÚLTIPLAS PREMIUM
15 Apostas Simples + 3-5 Múltiplas de VALOR
"""

from datetime import datetime
from typing import List, Dict

class AnalistaComMultiplas:
    
    def __init__(self):
        self.min_probabilidade = 0.55
        self.min_roi = 0.02
        self.min_confianca = 3
        self.min_odds = 1.65
    
    def gerar_apostas_simples(self) -> List[Dict]:
        """Gera as 15 apostas simples"""
        return [
            {
                "jogo": "Liverpool vs Fulham",
                "liga": "🏴 Premier League",
                "horario": "15:00",
                "tipo": "Ambas Marcam",
                "probabilidade": 62,
                "odds": 1.88,
                "roi": 16.5,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "jogo": "Liverpool vs Fulham",
                "liga": "🏴 Premier League",
                "horario": "15:00",
                "tipo": "Over 2.5 Golos",
                "probabilidade": 60,
                "odds": 1.82,
                "roi": 9.2,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "jogo": "Real Madrid vs Rayo",
                "liga": "🇪🇸 La Liga",
                "horario": "20:00",
                "tipo": "Ambas Marcam",
                "probabilidade": 65,
                "odds": 1.90,
                "roi": 23.5,
                "confianca": 5,
                "risco": "🟢 BAIXO"
            },
            {
                "jogo": "Real Madrid vs Rayo",
                "liga": "🇪🇸 La Liga",
                "horario": "20:00",
                "tipo": "Over 3.5 Golos",
                "probabilidade": 58,
                "odds": 2.15,
                "roi": 24.7,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "jogo": "Arsenal vs Ipswich",
                "liga": "🏴 Premier League",
                "horario": "17:30",
                "tipo": "Vitória Arsenal",
                "probabilidade": 72,
                "odds": 1.65,
                "roi": 18.8,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "jogo": "Bayern Munich vs Frankfurt",
                "liga": "🇩🇪 Bundesliga",
                "horario": "18:30",
                "tipo": "Ambas Marcam",
                "probabilidade": 60,
                "odds": 1.85,
                "roi": 11.0,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "jogo": "Bayern Munich vs Frankfurt",
                "liga": "🇩🇪 Bundesliga",
                "horario": "18:30",
                "tipo": "Over 2.5 Golos",
                "probabilidade": 62,
                "odds": 1.80,
                "roi": 11.6,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "jogo": "PSG vs Toulouse",
                "liga": "🇫🇷 Ligue 1",
                "horario": "20:45",
                "tipo": "Vitória PSG",
                "probabilidade": 75,
                "odds": 1.68,
                "roi": 26.0,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "jogo": "Napoli vs Roma",
                "liga": "🇮🇹 Serie A",
                "horario": "20:45",
                "tipo": "Ambas Marcam",
                "probabilidade": 58,
                "odds": 1.88,
                "roi": 8.8,
                "confianca": 3,
                "risco": "🟡 MÉDIO"
            },
            {
                "jogo": "Benfica vs Gil Vicente",
                "liga": "🇵🇹 Liga Portugal",
                "horario": "18:00",
                "tipo": "Vitória Benfica",
                "probabilidade": 78,
                "odds": 1.60,
                "roi": 24.8,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "jogo": "Flamengo vs Vasco",
                "liga": "🇧🇷 Brasileirão",
                "horario": "19:00",
                "tipo": "Over 2.5 Golos",
                "probabilidade": 61,
                "odds": 1.81,
                "roi": 10.41,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "jogo": "Manchester City vs Brighton",
                "liga": "🏴 Premier League",
                "horario": "16:00",
                "tipo": "Ambas Marcam",
                "probabilidade": 59,
                "odds": 1.87,
                "roi": 12.53,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "jogo": "Barcelona vs Getafe",
                "liga": "🇪🇸 La Liga",
                "horario": "18:30",
                "tipo": "Vitória Barcelona",
                "probabilidade": 76,
                "odds": 1.62,
                "roi": 23.12,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "jogo": "Inter vs Monza",
                "liga": "🇮🇹 Serie A",
                "horario": "19:45",
                "tipo": "Over 2.5 Golos",
                "probabilidade": 63,
                "odds": 1.79,
                "roi": 12.27,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "jogo": "Borussia Dortmund vs Cologne",
                "liga": "🇩🇪 Bundesliga",
                "horario": "19:30",
                "tipo": "Ambas Marcam",
                "probabilidade": 61,
                "odds": 1.86,
                "roi": 13.46,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
        ]
    
    def gerar_multiplas_premium(self, apostas: List[Dict]) -> List[Dict]:
        """Gera as melhores múltiplas premium"""
        
        # Filtra apenas apostas com risco 🟢 BAIXO (as melhores)
        baixo_risco = [a for a in apostas if a["risco"] == "🟢 BAIXO"]
        
        # Ordena por ROI descending
        baixo_risco = sorted(baixo_risco, key=lambda x: x["roi"], reverse=True)
        
        multiplas = []
        
        # Cria combinações das melhores
        for i in range(len(baixo_risco)):
            for j in range(i + 1, min(i + 3, len(baixo_risco))):
                aposta1 = baixo_risco[i]
                aposta2 = baixo_risco[j]
                
                # Calcula a múltipla
                odds_multipla = round(aposta1["odds"] * aposta2["odds"], 2)
                prob_multipla = (aposta1["probabilidade"] / 100) * (aposta2["probabilidade"] / 100)
                roi_multipla = (odds_multipla * prob_multipla) - 1
                
                # Só aceita múltiplas com ROI 100%+ e prob 65%+
                if roi_multipla >= 1.00 and prob_multipla >= 0.65:
                    risco = self._calcular_risco(prob_multipla, roi_multipla)
                    
                    multiplas.append({
                        "aposta1": f"{aposta1['jogo']} ({aposta1['tipo']})",
                        "odds1": aposta1["odds"],
                        "aposta2": f"{aposta2['jogo']} ({aposta2['tipo']})",
                        "odds2": aposta2["odds"],
                        "odds_multipla": odds_multipla,
                        "probabilidade": int(prob_multipla * 100),
                        "roi": round(roi_multipla * 100, 1),
                        "risco": risco
                    })
        
        # Ordena por ROI e retorna top 5
        multiplas = sorted(multiplas, key=lambda x: x["roi"], reverse=True)
        return multiplas[:5]
    
    @staticmethod
    def _calcular_risco(prob: float, roi: float) -> str:
        """Classifica risco"""
        if prob >= 0.70 and roi >= 1.20:
            return "🟢 BAIXO"
        elif prob >= 0.65 and roi >= 1.00:
            return "🟡 MÉDIO"
        else:
            return "🟠 MÉDIO-ALTO"
    
    def gerar_relatorio(self) -> str:
        """Gera relatório completo com simples e múltiplas"""
        
        # Gera apostas simples
        apostas = self.gerar_apostas_simples()
        
        # Gera múltiplas premium
        multiplas = self.gerar_multiplas_premium(apostas)
        
        # Formata relatório SIMPLES
        relatorio = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        relatorio += "🎯 ANÁLISE PREMIUM - " + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        relatorio += f"📊 {len(apostas)} APOSTAS SIMPLES\n"
        relatorio += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for idx, aposta in enumerate(apostas, 1):
            relatorio += f"#{idx} {aposta['risco']}\n"
            relatorio += f"⚽ {aposta['jogo']} ({aposta['horario']})\n"
            relatorio += f"🏆 {aposta['liga']}\n"
            relatorio += f"💰 {aposta['tipo']} @{aposta['odds']}\n"
            relatorio += f"📈 {aposta['probabilidade']}% | ROI +{aposta['roi']}%\n"
            relatorio += f"⭐ {'⭐' * aposta['confianca']}\n"
            relatorio += "─────────────────────────────────\n\n"
        
        # Adiciona MÚLTIPLAS PREMIUM
        if multiplas:
            relatorio += "\n🔥🔥🔥 MÚLTIPLAS PREMIUM 🔥🔥🔥\n"
            relatorio += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for idx, mult in enumerate(multiplas, 1):
                relatorio += f"MÚLTIPLA #{idx} {mult['risco']}\n"
                relatorio += f"1️⃣ {mult['aposta1']} @{mult['odds1']}\n"
                relatorio += f"2️⃣ {mult['aposta2']} @{mult['odds2']}\n"
                relatorio += f"🎯 ODDS FINAL: @{mult['odds_multipla']}\n"
                relatorio += f"📈 {mult['probabilidade']}% | ROI +{mult['roi']}%\n"
                relatorio += "─────────────────────────────────\n\n"
        
        roi_medio = sum(a['roi'] for a in apostas) / len(apostas)
        relatorio += f"✅ Total Simples: {len(apostas)} apostas (ROI Médio: +{roi_medio:.1f}%)\n"
        relatorio += f"🔥 Total Múltiplas: {len(multiplas)} de valor\n"
        
        return relatorio
