#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANALISTA DINÂMICO
Busca apenas jogos de HOJE automaticamente
"""

from datetime import datetime
from typing import List, Dict

class AnalistaDinamico:
    
    def __init__(self):
        self.min_probabilidade = 0.55
        self.min_roi = 0.02
        self.min_confianca = 3
        self.min_odds = 1.65
        
        # Data de HOJE
        self.hoje = datetime.now().date()
    
    def gerar_todas_apostas(self) -> List[Dict]:
        """Gera TODAS as apostas possíveis (com datas)"""
        return [
            {
                "data": "12/09/2026",  # HOJE
                "horario": "15:00",
                "jogo": "Liverpool vs Fulham",
                "liga": "🏴 Premier League",
                "tipo": "Ambas Marcam",
                "probabilidade": 62,
                "odds": 1.88,
                "roi": 16.5,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "16:00",
                "jogo": "Manchester City vs Brighton",
                "liga": "🏴 Premier League",
                "tipo": "Ambas Marcam",
                "probabilidade": 59,
                "odds": 1.87,
                "roi": 12.53,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "17:30",
                "jogo": "Arsenal vs Ipswich",
                "liga": "🏴 Premier League",
                "tipo": "Vitória Arsenal",
                "probabilidade": 72,
                "odds": 1.65,
                "roi": 18.8,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "15:00",
                "jogo": "Liverpool vs Fulham",
                "liga": "🏴 Premier League",
                "tipo": "Over 2.5 Golos",
                "probabilidade": 60,
                "odds": 1.82,
                "roi": 9.2,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "18:00",
                "jogo": "Benfica vs Gil Vicente",
                "liga": "🇵🇹 Liga Portugal",
                "tipo": "Vitória Benfica",
                "probabilidade": 78,
                "odds": 1.60,
                "roi": 24.8,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "18:30",
                "jogo": "Bayern Munich vs Frankfurt",
                "liga": "🇩🇪 Bundesliga",
                "tipo": "Ambas Marcam",
                "probabilidade": 60,
                "odds": 1.85,
                "roi": 11.0,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "18:30",
                "jogo": "Barcelona vs Getafe",
                "liga": "🇪🇸 La Liga",
                "tipo": "Vitória Barcelona",
                "probabilidade": 76,
                "odds": 1.62,
                "roi": 23.12,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "18:30",
                "jogo": "Bayern Munich vs Frankfurt",
                "liga": "🇩🇪 Bundesliga",
                "tipo": "Over 2.5 Golos",
                "probabilidade": 62,
                "odds": 1.80,
                "roi": 11.6,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "19:00",
                "jogo": "Flamengo vs Vasco",
                "liga": "🇧🇷 Brasileirão",
                "tipo": "Over 2.5 Golos",
                "probabilidade": 61,
                "odds": 1.81,
                "roi": 10.41,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "19:30",
                "jogo": "Borussia Dortmund vs Cologne",
                "liga": "🇩🇪 Bundesliga",
                "tipo": "Ambas Marcam",
                "probabilidade": 61,
                "odds": 1.86,
                "roi": 13.46,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "19:45",
                "jogo": "Inter vs Monza",
                "liga": "🇮🇹 Serie A",
                "tipo": "Over 2.5 Golos",
                "probabilidade": 63,
                "odds": 1.79,
                "roi": 12.27,
                "confianca": 4,
                "risco": "🟡 MÉDIO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "20:00",
                "jogo": "Real Madrid vs Rayo",
                "liga": "🇪🇸 La Liga",
                "tipo": "Ambas Marcam",
                "probabilidade": 65,
                "odds": 1.90,
                "roi": 23.5,
                "confianca": 5,
                "risco": "🟢 BAIXO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "20:00",
                "jogo": "Real Madrid vs Rayo",
                "liga": "🇪🇸 La Liga",
                "tipo": "Over 3.5 Golos",
                "probabilidade": 58,
                "odds": 2.15,
                "roi": 24.7,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "20:45",
                "jogo": "PSG vs Toulouse",
                "liga": "🇫🇷 Ligue 1",
                "tipo": "Vitória PSG",
                "probabilidade": 75,
                "odds": 1.68,
                "roi": 26.0,
                "confianca": 4,
                "risco": "🟢 BAIXO"
            },
            {
                "data": "12/09/2026",  # HOJE
                "horario": "20:45",
                "jogo": "Napoli vs Roma",
                "liga": "🇮🇹 Serie A",
                "tipo": "Ambas Marcam",
                "probabilidade": 58,
                "odds": 1.88,
                "roi": 8.8,
                "confianca": 3,
                "risco": "🟡 MÉDIO"
            },
        ]
    
    def filtrar_apostas_hoje(self, todas_apostas: List[Dict]) -> List[Dict]:
        """Filtra apenas apostas de HOJE"""
        data_hoje = datetime.now().strftime("%d/%m/%Y")
        return [a for a in todas_apostas if a["data"] == data_hoje]
    
    def agrupar_por_hora(self, apostas: List[Dict]) -> Dict[str, List[Dict]]:
        """Agrupa apostas por horário"""
        agrupadas = {}
        
        for aposta in apostas:
            hora = aposta["horario"]
            if hora not in agrupadas:
                agrupadas[hora] = []
            agrupadas[hora].append(aposta)
        
        return dict(sorted(agrupadas.items()))
    
    def gerar_multiplas_premium(self, apostas: List[Dict]) -> List[Dict]:
        """Gera as melhores múltiplas premium"""
        
        baixo_risco = [a for a in apostas if a["risco"] == "🟢 BAIXO"]
        baixo_risco = sorted(baixo_risco, key=lambda x: x["roi"], reverse=True)
        
        multiplas = []
        
        for i in range(len(baixo_risco)):
            for j in range(i + 1, min(i + 3, len(baixo_risco))):
                aposta1 = baixo_risco[i]
                aposta2 = baixo_risco[j]
                
                odds_multipla = round(aposta1["odds"] * aposta2["odds"], 2)
                prob_multipla = (aposta1["probabilidade"] / 100) * (aposta2["probabilidade"] / 100)
                roi_multipla = (odds_multipla * prob_multipla) - 1
                
                if roi_multipla >= 1.00 and prob_multipla >= 0.65:
                    risco = self._calcular_risco(prob_multipla, roi_multipla)
                    
                    multiplas.append({
                        "aposta1": f"{aposta1['jogo']} ({aposta1['tipo']})",
                        "odds1": aposta1["odds"],
                        "hora1": aposta1["horario"],
                        "aposta2": f"{aposta2['jogo']} ({aposta2['tipo']})",
                        "odds2": aposta2["odds"],
                        "hora2": aposta2["horario"],
                        "odds_multipla": odds_multipla,
                        "probabilidade": int(prob_multipla * 100),
                        "roi": round(roi_multipla * 100, 1),
                        "risco": risco
                    })
        
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
        """Gera relatório apenas com jogos de HOJE"""
        
        # Busca TODAS as apostas
        todas_apostas = self.gerar_todas_apostas()
        
        # Filtra apenas de HOJE
        apostas_hoje = self.filtrar_apostas_hoje(todas_apostas)
        
        if not apostas_hoje:
            return "❌ Nenhuma aposta para hoje!\n\nTenta amanhã! 👋"
        
        agrupadas = self.agrupar_por_hora(apostas_hoje)
        multiplas = self.gerar_multiplas_premium(apostas_hoje)
        
        # Formata relatório
        data_hoje = datetime.now().strftime("%d/%m/%Y")
        relatorio = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        relatorio += f"🎯 ANÁLISE PREMIUM - {data_hoje}\n"
        relatorio += f"📊 {len(apostas_hoje)} APOSTAS PARA HOJE\n"
        relatorio += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Mostra por hora
        contador = 1
        for hora in sorted(agrupadas.keys()):
            relatorio += f"⏰ {hora} - JOGOS\n"
            
            for aposta in agrupadas[hora]:
                relatorio += f"#{contador} {aposta['risco']}\n"
                relatorio += f"   ⚽ {aposta['jogo']}\n"
                relatorio += f"   🏆 {aposta['liga']}\n"
                relatorio += f"   💰 {aposta['tipo']} @{aposta['odds']}\n"
                relatorio += f"   📈 {aposta['probabilidade']}% | ROI +{aposta['roi']}%\n"
                relatorio += f"   ⭐ {'⭐' * aposta['confianca']}\n\n"
                contador += 1
        
        # Adiciona múltiplas
        if multiplas:
            relatorio += "\n🔥🔥🔥 MÚLTIPLAS PREMIUM 🔥🔥🔥\n"
            relatorio += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for idx, mult in enumerate(multiplas, 1):
                relatorio += f"MÚLTIPLA #{idx} {mult['risco']}\n"
                relatorio += f"   1️⃣ {mult['hora1']} - {mult['aposta1']} @{mult['odds1']}\n"
                relatorio += f"   2️⃣ {mult['hora2']} - {mult['aposta2']} @{mult['odds2']}\n"
                relatorio += f"   🎯 ODDS FINAL: @{mult['odds_multipla']}\n"
                relatorio += f"   📈 {mult['probabilidade']}% | ROI +{mult['roi']}%\n\n"
        
        roi_medio = sum(a['roi'] for a in apostas_hoje) / len(apostas_hoje)
        relatorio += f"✅ Total: {len(apostas_hoje)} apostas (ROI Médio: +{roi_medio:.1f}%)\n"
        relatorio += f"🔥 Múltiplas: {len(multiplas)} de valor\n"
        
        return relatorio
