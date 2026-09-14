#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANALISADOR INTELIGENTE
Análise baseada em forma dos times e probabilidades realistas
"""

from datetime import datetime
from typing import List, Dict
import random

class AnalisadorInteligente:
    
    def __init__(self, buscador_jogos):
        self.buscador = buscador_jogos
        self.data_hoje = datetime.now().strftime("%d/%m/%Y")
    
    def calcular_probabilidade_vitoria(self, forma_casa: Dict, forma_fora: Dict) -> float:
        """Calcula probabilidade de vitória da casa baseada em forma"""
        
        # Se forma está vazia, usa probabilidades padrão
        if not forma_casa.get("ganhas") and not forma_casa.get("perdidas"):
            print("    ⚠️ Forma da casa não disponível, usando padrão")
            return 0.55 + (0.05 * (len(str(hash(forma_casa))) % 2))
        
        if not forma_fora.get("ganhas") and not forma_fora.get("perdidas"):
            print("    ⚠️ Forma do fora não disponível, usando padrão")
            return 0.50 + (0.05 * (len(str(hash(forma_fora))) % 2))
        
        # Calcula taxa de vitória recente
        total_casa = max(forma_casa["ganhas"] + forma_casa["empates"] + forma_casa["perdidas"], 1)
        taxa_ganhas_casa = forma_casa["ganhas"] / total_casa
        
        total_fora = max(forma_fora["ganhas"] + forma_fora["empates"] + forma_fora["perdidas"], 1)
        taxa_ganhas_fora = forma_fora["ganhas"] / total_fora
        
        # Penalidade para jogar fora
        taxa_ganhas_fora_ajustada = taxa_ganhas_fora * 0.85
        
        # Probabilidade simples de vitória casa vs fora
        diferenca = taxa_ganhas_casa - taxa_ganhas_fora_ajustada
        
        # Converte em probabilidade (50% base + diferença)
        prob_vitoria = 0.50 + (diferenca * 0.30)
        
        # Garante entre 30-70%
        prob_vitoria = max(0.30, min(0.70, prob_vitoria))
        
        return prob_vitoria
    
    def calcular_probabilidade_ambas_marcam(self, forma_casa: Dict, forma_fora: Dict) -> float:
        """Calcula probabilidade de ambas marcarem"""
        
        media_gols_casa = max(forma_casa["gols_marcados"], 0.5)
        media_gols_fora = max(forma_fora["gols_marcados"], 0.5)
        
        # Defesa: gols sofridos / jogos
        total_casa = max(forma_casa["ganhas"] + forma_casa["empates"] + forma_casa["perdidas"], 1)
        total_fora = max(forma_fora["ganhas"] + forma_fora["empates"] + forma_fora["perdidas"], 1)
        
        media_gols_sofridos_casa = forma_casa["gols_sofridos"] / total_casa
        media_gols_sofridos_fora = forma_fora["gols_sofridos"] / total_fora
        
        # Se ambos times marcam em média > 0.7 gols
        if media_gols_casa > 0.7 and media_gols_sofridos_fora > 0.5:
            if media_gols_fora > 0.7 and media_gols_sofridos_casa > 0.5:
                prob = 0.65 + random.uniform(-0.05, 0.10)
                return max(0.55, min(0.80, prob))
        
        # Caso padrão
        prob = 0.50
        if media_gols_casa > 1.0:
            prob += 0.10
        if media_gols_fora > 1.0:
            prob += 0.10
        
        return max(0.45, min(0.75, prob))
    
    def calcular_probabilidade_over(self, forma_casa: Dict, forma_fora: Dict, limite: float) -> float:
        """Calcula probabilidade de over X.5 golos"""
        
        media_gols_casa = forma_casa["gols_marcados"]
        media_gols_fora = forma_fora["gols_marcados"]
        total_gols = media_gols_casa + media_gols_fora
        
        # Over 2.5 é mais comum se média total > 2.0
        if limite == 2.5:
            if total_gols > 2.5:
                prob = 0.65 + random.uniform(-0.05, 0.10)
            elif total_gols > 1.5:
                prob = 0.55 + random.uniform(-0.05, 0.10)
            else:
                prob = 0.45 + random.uniform(-0.10, 0.05)
        
        # Over 3.5 é mais raro
        elif limite == 3.5:
            if total_gols > 3.5:
                prob = 0.60 + random.uniform(-0.05, 0.10)
            elif total_gols > 2.5:
                prob = 0.50 + random.uniform(-0.05, 0.10)
            else:
                prob = 0.40 + random.uniform(-0.05, 0.05)
        
        else:
            prob = 0.50
        
        return max(0.40, min(0.75, prob))
    
    def gerar_aposta(self, jogo: Dict, tipo: str) -> Dict:
        """Gera uma aposta para um jogo com análise inteligente"""
        
        # Busca forma dos times
        casa_id = jogo.get("casa_id", random.randint(1000, 9999))
        fora_id = jogo.get("fora_id", random.randint(1000, 9999))
        
        forma_casa = self.buscador.obter_forma_time(casa_id)
        forma_fora = self.buscador.obter_forma_time(fora_id)
        
        # Calcula probabilidade baseado em tipo
        if tipo == "Vitória Casa":
            prob = self.calcular_probabilidade_vitoria(forma_casa, forma_fora)
        elif tipo == "Vitória Fora":
            prob_vitoria_casa = self.calcular_probabilidade_vitoria(forma_casa, forma_fora)
            prob = 1 - prob_vitoria_casa
        elif tipo == "Ambas Marcam":
            prob = self.calcular_probabilidade_ambas_marcam(forma_casa, forma_fora)
        elif tipo == "Over 2.5 Golos":
            prob = self.calcular_probabilidade_over(forma_casa, forma_fora, 2.5)
        elif tipo == "Over 3.5 Golos":
            prob = self.calcular_probabilidade_over(forma_casa, forma_fora, 3.5)
        else:
            prob = 0.55
        
        # Converte probabilidade em odds realista
        odds = self._prob_para_odds(prob)
        
        # Calcula ROI
        roi = (odds * prob) - 1
        
        # Classifica risco
        risco = self._classificar_risco(prob, roi)
        
        # Calcula confiança
        confianca = self._calcular_confianca(prob, roi)
        
        return {
            "data": self.data_hoje,
            "horario": jogo["horario"],
            "jogo": f"{jogo['casa']} vs {jogo['fora']}",
            "liga": jogo["liga"],
            "tipo": tipo,
            "probabilidade": int(prob * 100),
            "odds": round(odds, 2),
            "roi": round(roi * 100, 1),
            "confianca": confianca,
            "risco": risco,
            "forma_casa": forma_casa,
            "forma_fora": forma_fora
        }
    
    @staticmethod
    def _prob_para_odds(prob: float) -> float:
        """Converte probabilidade em odds realista"""
        # Odds = 1 / probabilidade
        odds_base = 1 / max(prob, 0.1)
        
        # Margem de casa de apostas (~5%)
        odds_com_margem = odds_base * 0.95
        
        # Adiciona variação pequena para realismo
        variacao = random.uniform(0.95, 1.05)
        odds_final = odds_com_margem * variacao
        
        # Garante entre 1.5 e 3.0
        return max(1.50, min(3.0, round(odds_final, 2)))
    
    @staticmethod
    def _classificar_risco(prob: float, roi: float) -> str:
        """Classifica risco da aposta"""
        if prob >= 0.70 and roi >= 0.20:
            return "🟢 BAIXO"
        elif prob >= 0.65 and roi >= 0.15:
            return "🟡 MÉDIO"
        else:
            return "🟠 MÉDIO-ALTO"
    
    @staticmethod
    def _calcular_confianca(prob: float, roi: float) -> int:
        """Calcula confiança da aposta"""
        score = (prob * 0.6) + (min(roi, 0.15) / 0.15 * 0.4)
        
        if score >= 0.85:
            return 5
        elif score >= 0.75:
            return 4
        elif score >= 0.65:
            return 3
        elif score >= 0.50:
            return 2
        return 1
    
    def gerar_apostas_jogo(self, jogo: Dict) -> List[Dict]:
        """Gera 3-4 apostas para um jogo (tipos diferentes)"""
        
        tipos_sugeridos = [
            "Vitória Casa",
            "Ambas Marcam",
            "Over 2.5 Golos",
            "Vitória Fora"
        ]
        
        apostas = []
        for tipo in tipos_sugeridos:
            try:
                aposta = self.gerar_aposta(jogo, tipo)
                
                # Filtro muito relaxado aqui - aceita mesmo com probabilidade baixa
                if aposta["probabilidade"] >= 50:
                    apostas.append(aposta)
            except:
                pass
        
        return apostas
    
    def gerar_todas_apostas(self, jogos: List[Dict]) -> List[Dict]:
        """Gera apostas para todos os jogos (máximo 15)"""
        
        print("🎯 Gerando apostas com análise inteligente...")
        todas_apostas = []
        
        for jogo in jogos:
            apostas_jogo = self.gerar_apostas_jogo(jogo)
            todas_apostas.extend(apostas_jogo)
            
            if len(todas_apostas) >= 20:  # Gera mais que 15 para ter margem
                break
        
        print(f"  📊 Apostas geradas (antes de filtro): {len(todas_apostas)}")
        
        # FILTRO 1 - Qualidade alta
        apostas_filtradas = [a for a in todas_apostas if a["probabilidade"] >= 55 and a["roi"] >= 2]
        print(f"  ✅ Com filtro ALTO (55%, +2%): {len(apostas_filtradas)}")
        
        # Se não conseguir 10, relaxa
        if len(apostas_filtradas) < 10:
            apostas_filtradas = [a for a in todas_apostas if a["probabilidade"] >= 52 and a["roi"] >= 1]
            print(f"  🟡 Com filtro MÉDIO (52%, +1%): {len(apostas_filtradas)}")
        
        # Se ainda não conseguir, relaxa mais
        if len(apostas_filtradas) < 15:
            apostas_filtradas = [a for a in todas_apostas if a["probabilidade"] >= 50]
            print(f"  🟠 Com filtro BAIXO (50%+): {len(apostas_filtradas)}")
        
        # Se ainda não conseguir, pega em todas
        if len(apostas_filtradas) < 15:
            apostas_filtradas = todas_apostas
            print(f"  ⚠️ Sem filtro: {len(apostas_filtradas)}")
        
        # Ordena por ROI (melhor primeiro)
        apostas_filtradas.sort(key=lambda x: x["roi"], reverse=True)
        
        return apostas_filtradas[:15]
