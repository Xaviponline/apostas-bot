#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RASTREADOR DE RESULTADOS
Busca scores e compara com apostas
"""

import requests
from typing import Dict, Optional
from datetime import datetime

class RastreadorResultados:
    
    def __init__(self):
        self.base_url = "https://api.sofascore.com"
    
    def buscar_score_por_times(self, casa: str, fora: str) -> Optional[Dict]:
        """
        Busca score de um jogo pelo nome dos times
        Retorna: {"casa": 2, "fora": 1, "status": "finished"}
        """
        try:
            # Busca jogo via SofaScore
            query = f"{casa.replace(' ', '%20')} {fora.replace(' ', '%20')}"
            url = f"{self.base_url}/api/v1/events"
            
            params = {
                "limit": 50,
                "offset": 0,
                "sort": "-startTimestamp"
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                dados = response.json()
                
                # Procura jogo correspondente
                for evento in dados.get("events", []):
                    home = evento.get("homeTeam", {}).get("name", "").lower()
                    away = evento.get("awayTeam", {}).get("name", "").lower()
                    
                    if casa.lower() in home and fora.lower() in away:
                        return {
                            "casa": evento.get("homeScore", {}).get("current", 0),
                            "fora": evento.get("awayScore", {}).get("current", 0),
                            "status": evento.get("status", "not_started"),
                            "jogo": f"{home.title()} vs {away.title()}"
                        }
            
            return None
        
        except Exception as e:
            print(f"❌ Erro ao buscar score: {e}")
            return None
    
    def analisar_aposta(self, aposta: Dict, score: Dict) -> Optional[str]:
        """
        Analisa se aposta ganhou ou perdeu
        Retorna: "ganhou", "perdeu" ou None (jogo não terminou)
        """
        
        if not score or score.get("status") != "finished":
            return None  # Jogo ainda não terminou
        
        casa = score["casa"]
        fora = score["fora"]
        tipo = aposta["tipo"]
        
        # Análise por tipo de aposta
        if tipo == "Ambas Marcam":
            if casa > 0 and fora > 0:
                return "ganhou"
            else:
                return "perdeu"
        
        elif tipo == "Over 2.5 Golos":
            total = casa + fora
            if total >= 3:
                return "ganhou"
            else:
                return "perdeu"
        
        elif tipo == "Over 3.5 Golos":
            total = casa + fora
            if total >= 4:
                return "ganhou"
            else:
                return "perdeu"
        
        elif tipo == "Vitória Casa":
            if casa > fora:
                return "ganhou"
            else:
                return "perdeu"
        
        elif tipo == "Vitória Fora":
            if fora > casa:
                return "ganhou"
            else:
                return "perdeu"
        
        elif tipo == "Over Cantos":
            # Necessita dados de cantos (não sempre disponível)
            return None
        
        elif tipo == "Primeira Parte Over 1.5":
            # Necessita dados de primeira parte
            return None
        
        return None
    
    def processar_apostas_pendentes(self, gestor) -> Dict:
        """
        Processa todas as apostas pendentes
        Retorna: {"processadas": N, "ganhas": N, "perdidas": N}
        """
        
        apostas_pendentes = gestor.obter_apostas_pendentes()
        
        processadas = 0
        ganhas = 0
        perdidas = 0
        
        for aposta in apostas_pendentes:
            # Busca score do jogo
            jogo_parts = aposta["jogo"].split(" vs ")
            if len(jogo_parts) != 2:
                continue
            
            casa, fora = jogo_parts
            score = self.buscar_score_por_times(casa.strip(), fora.strip())
            
            if score and score.get("status") == "finished":
                # Analisa aposta
                resultado = self.analisar_aposta(aposta, score)
                
                if resultado:
                    gestor.registar_resultado(aposta["id"], resultado)
                    processadas += 1
                    
                    if resultado == "ganhou":
                        ganhas += 1
                    else:
                        perdidas += 1
        
        return {
            "processadas": processadas,
            "ganhas": ganhas,
            "perdidas": perdidas
        }
    
    def obter_resumo_apostas(self, apostas: list) -> str:
        """Gera resumo das últimas apostas"""
        
        if not apostas:
            return "📋 Sem apostas ainda!"
        
        resumo = "📋 ÚLTIMAS APOSTAS:\n"
        resumo += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for aposta in apostas[-10:]:  # Últimas 10
            if aposta["resultado"] == "ganhou":
                status = "✅"
            elif aposta["resultado"] == "perdeu":
                status = "❌"
            else:
                status = "⏳"
            
            resumo += f"{status} #{aposta['id']} - {aposta['jogo'][:35]}\n"
            resumo += f"   {aposta['tipo']} @{aposta['odds']}\n"
            resumo += f"   Prob: {aposta['probabilidade']}% | ROI: +{aposta['roi_esperado']}%\n\n"
        
        return resumo
