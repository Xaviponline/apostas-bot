#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANALISTA 100% DINÂMICO
Gera apostas automaticamente cada dia baseado em data
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
        
        # Seed com data de HOJE para gerar dados consistentes
        self.data_hoje = datetime.now().strftime("%d/%m/%Y")
        self.seed = int(datetime.now().strftime("%d%m%Y"))
        random.seed(self.seed)
    
    def gerar_apostas_simples(self) -> List[Dict]:
        """Gera 15 apostas de HOJE dinamicamente"""
        
        # Dados base
        ligas = [
            "🏴 Premier League",
            "🇪🇸 La Liga",
            "🇮🇹 Serie A",
            "🇩🇪 Bundesliga",
            "🇫🇷 Ligue 1",
            "🇵🇹 Liga Portugal",
            "🇧🇷 Brasileirão"
        ]
        
        times = [
            ("Liverpool", "Fulham"),
            ("Manchester City", "Brighton"),
            ("Arsenal", "Ipswich"),
            ("Real Madrid", "Rayo"),
            ("Barcelona", "Getafe"),
            ("Bayern Munich", "Frankfurt"),
            ("PSG", "Toulouse"),
            ("Napoli", "Roma"),
            ("Benfica", "Gil Vicente"),
            ("Inter", "Monza"),
            ("Dortmund", "Cologne"),
            ("Flamengo", "Vasco"),
            ("Chelsea", "Luton"),
            ("Valencia", "Sevilla"),
            ("AC Milan", "Lazio"),
        ]
        
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
            # Seleciona aleatoriamente (mas consistente para a mesma data)
            time_idx = (i * 3 + self.seed) % len(times)
            liga_idx = (i * 2 + self.seed) % len(ligas)
            tipo_idx = (i + self.seed) % len(tipos_aposta)
            hora_idx = (i * 4 + self.seed) % len(horarios)
            
            casa, fora = times[time_idx]
            liga = ligas[liga_idx]
            tipo = tipos_aposta[tipo_idx]
            horario = horarios[hora_idx]
            
            # Gera odds e probabilidades variadas mas com qualidade
            base_prob = 55 + (i % 10) * 2  # 55-75%
            odds_base = 1.65 + (i % 6) * 0.15  # 1.65-2.55
            
            prob = base_prob + random.randint(-5, 10)
            odds = round(odds_base + random.uniform(-0.10, 0.20), 2)
            
            # Garante odds mínimo 1.65
            if odds < 1.65:
                odds = 1.65
            
            roi = (odds * (prob / 100)) - 1
            
            # Filtra qualidade mínima
            if prob >= self.min_probabilidade and roi >= self.min_roi and odds >= self.min_odds:
                confianca = self._calcular_confianca(prob / 100, roi)
                risco = self._calcular_risco(prob / 100, roi)
                
                if confianca >= self.min_confianca:
                    apostas.append({
                        "data": self.data_hoje,
                        "horario": horario,
                        "jogo": f"{casa} vs {fora}",
                        "liga": liga,
                        "tipo": tipo,
                        "probabilidade": prob,
                        "odds": odds,
                        "roi": round(roi * 100, 1),
                        "confianca": confianca,
                        "risco": risco
                    })
        
        # Se gerar menos de 15, regenera com critérios mais baixos
        while len(apostas) < 15:
            i = len(apostas)
            time_idx = (i * 3 + self.seed) % len(times)
            liga_idx = (i * 2 + self.seed) % len(ligas)
            tipo_idx = (i + self.seed) % len(tipos_aposta)
            hora_idx = (i * 4 + self.seed) % len(horarios)
            
            casa, fora = times[time_idx]
            liga = ligas[liga_idx]
            tipo = tipos_aposta[tipo_idx]
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
                "liga": liga,
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
        """Gera relatório com apostas de HOJE (dinâmicas)"""
        
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
