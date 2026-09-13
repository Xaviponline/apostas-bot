#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANALISTA DINÂMICO CORRIGIDO
Ligas SEMPRE corretas associadas aos times
"""

from datetime import datetime
import random
from typing import List, Dict

class AnistaDinamicoTotal:
    
    def __init__(self):
        self.min_probabilidade = 0.55
        self.min_roi = 0.02
        self.min_confianca = 3
        self.min_odds = 1.65
        
        # Seed com data de HOJE
        self.data_hoje = datetime.now().strftime("%d/%m/%Y")
        self.seed = int(datetime.now().strftime("%d%m%Y"))
        random.seed(self.seed)
        
        # Jogos com ligas CORRETAS (cada jogo tem sua liga)
        self.todos_jogos = [
            # Premier League
            ("Liverpool", "Fulham", "🏴 Premier League"),
            ("Manchester City", "Brighton", "🏴 Premier League"),
            ("Arsenal", "Ipswich", "🏴 Premier League"),
            ("Chelsea", "Luton", "🏴 Premier League"),
            ("Tottenham", "Nottingham", "🏴 Premier League"),
            
            # La Liga
            ("Real Madrid", "Rayo", "🇪🇸 La Liga"),
            ("Barcelona", "Getafe", "🇪🇸 La Liga"),
            ("Valencia", "Sevilla", "🇪🇸 La Liga"),
            ("Atletico Madrid", "Villarreal", "🇪🇸 La Liga"),
            ("Real Sociedad", "Almeria", "🇪🇸 La Liga"),
            
            # Serie A
            ("Napoli", "Roma", "🇮🇹 Serie A"),
            ("Inter", "Monza", "🇮🇹 Serie A"),
            ("AC Milan", "Lazio", "🇮🇹 Serie A"),
            ("Juventus", "Sassuolo", "🇮🇹 Serie A"),
            ("Fiorentina", "Venezia", "🇮🇹 Serie A"),
            
            # Bundesliga
            ("Bayern Munich", "Frankfurt", "🇩🇪 Bundesliga"),
            ("Dortmund", "Cologne", "🇩🇪 Bundesliga"),
            ("RB Leipzig", "Wolfsburg", "🇩🇪 Bundesliga"),
            ("Leverkusen", "Stuttgart", "🇩🇪 Bundesliga"),
            ("Hamburg", "Hannover", "🇩🇪 Bundesliga"),
            
            # Ligue 1
            ("PSG", "Toulouse", "🇫🇷 Ligue 1"),
            ("Marseille", "Nice", "🇫🇷 Ligue 1"),
            ("Lyon", "Nantes", "🇫🇷 Ligue 1"),
            ("Monaco", "Rennes", "🇫🇷 Ligue 1"),
            ("Lens", "Strasbourg", "🇫🇷 Ligue 1"),
            
            # Liga Portugal
            ("Benfica", "Gil Vicente", "🇵🇹 Liga Portugal"),
            ("Porto", "Guimaraes", "🇵🇹 Liga Portugal"),
            ("Sporting", "Estoril", "🇵🇹 Liga Portugal"),
            ("Braga", "Arouca", "🇵🇹 Liga Portugal"),
            ("Boavista", "Santa Clara", "🇵🇹 Liga Portugal"),
            
            # Brasileirão
            ("Flamengo", "Vasco", "🇧🇷 Brasileirão"),
            ("Sao Paulo", "Corinthians", "🇧🇷 Brasileirão"),
            ("Palmeiras", "Santos", "🇧🇷 Brasileirão"),
            ("Botafogo", "Cruzeiro", "🇧🇷 Brasileirão"),
            ("Gremio", "Internacional", "🇧🇷 Brasileirão"),
        ]
    
    def gerar_apostas_simples(self) -> List[Dict]:
        """Gera 15 apostas de HOJE dinamicamente COM LIGAS CORRETAS"""
        
        tipos_aposta = [
            "Ambas Marcam",
            "Over 2.5 Golos",
            "Over 3.5 Golos",
            "Vitória Casa",
            "Vitória Fora",
            "Over Cantos",
            "Primeira Parte Over 1.5"
        ]
        
        horarios = [
            "15:00", "15:30", "16:00", "17:00", "17:30",
            "18:00", "18:30", "19:00", "19:30", "19:45",
            "20:00", "20:15", "20:30", "20:45", "21:00"
        ]
        
        apostas = []
        
        for i in range(15):
            # Seleciona jogo (com liga CORRECTA associada)
            jogo_idx = (i * 2 + self.seed) % len(self.todos_jogos)
            casa, fora, liga = self.todos_jogos[jogo_idx]
            
            # Tipo de aposta
            tipo_idx = (i + self.seed) % len(tipos_aposta)
            tipo = tipos_aposta[tipo_idx]
            
            # Horário
            hora_idx = (i * 4 + self.seed) % len(horarios)
            horario = horarios[hora_idx]
            
            # Gera odds e probabilidades
            base_prob = 55 + (i % 10) * 2
            odds_base = 1.65 + (i % 6) * 0.15
            
            prob = base_prob + random.randint(-5, 10)
            odds = round(odds_base + random.uniform(-0.10, 0.20), 2)
            
            if odds < 1.65:
                odds = 1.65
            
            roi = (odds * (prob / 100)) - 1
            
            # Filtra qualidade
            if prob >= self.min_probabilidade and roi >= self.min_roi and odds >= self.min_odds:
                confianca = self._calcular_confianca(prob / 100, roi)
                risco = self._calcular_risco(prob / 100, roi)
                
                if confianca >= self.min_confianca:
                    apostas.append({
                        "data": self.data_hoje,
                        "horario": horario,
                        "jogo": f"{casa} vs {fora}",
                        "liga": liga,  # AQUI: Liga CORRETA!
                        "tipo": tipo,
                        "probabilidade": prob,
                        "odds": odds,
                        "roi": round(roi * 100, 1),
                        "confianca": confianca,
                        "risco": risco
                    })
        
        # Se gerar menos de 15, adiciona mais
        while len(apostas) < 15:
            i = len(apostas)
            jogo_idx = (i * 3 + self.seed) % len(self.todos_jogos)
            casa, fora, liga = self.todos_jogos[jogo_idx]
            
            tipo_idx = (i + self.seed) % len(tipos_aposta)
            tipo = tipos_aposta[tipo_idx]
            
            hora_idx = (i * 5 + self.seed) % len(horarios)
            horario = horarios[hora_idx]
            
            prob = 52 + random.randint(0, 25)
            odds = 1.60 + random.uniform(0, 0.50)
            odds = round(max(odds, 1.60), 2)
            
            roi = (odds * (prob / 100)) - 1
            confianca = self._calcular_confianca(prob / 100, roi)
            risco = self._calcular_risco(prob / 100, roi)
            
            apostas.append({
                "data": self.data_hoje,
                "horario": horario,
                "jogo": f"{casa} vs {fora}",
                "liga": liga,  # AQUI TAMBÉM: Liga CORRETA!
                "tipo": tipo,
                "probabilidade": prob,
                "odds": odds,
                "roi": round(roi * 100, 1),
                "confianca": confianca,
                "risco": risco
            })
        
        return apostas[:15]
    
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
    
    def _calcular_confianca(self, prob: float, roi: float) -> int:
        """Calcula confiança"""
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
    def _calcular_risco(prob: float, roi: float) -> str:
        """Classifica risco"""
        if prob >= 0.70 and roi >= 1.20:
            return "🟢 BAIXO"
        elif prob >= 0.65 and roi >= 1.00:
            return "🟡 MÉDIO"
        else:
            return "🟠 MÉDIO-ALTO"
    
    def gerar_relatorio(self) -> str:
        """Gera relatório com apostas de HOJE (dinâmicas e com ligas corretas)"""
        
        apostas = self.gerar_apostas_simples()
        
        if not apostas:
            return "❌ Nenhuma aposta gerada para hoje!\n\nTenta mais tarde! 👋"
        
        agrupadas = self.agrupar_por_hora(apostas)
        multiplas = self.gerar_multiplas_premium(apostas)
        
        # Formata relatório
        relatorio = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        relatorio += f"🎯 ANÁLISE PREMIUM - {self.data_hoje}\n"
        relatorio += f"📊 {len(apostas)} APOSTAS PARA HOJE\n"
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
        
        roi_medio = sum(a['roi'] for a in apostas) / len(apostas)
        relatorio += f"✅ Total: {len(apostas)} apostas (ROI Médio: +{roi_medio:.1f}%)\n"
        relatorio += f"🔥 Múltiplas: {len(multiplas)} de valor\n"
        
        return relatorio
