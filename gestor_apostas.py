#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GESTOR DE APOSTAS
Armazena histórico de apostas e resultados
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional

class GestorApostas:
    
    def __init__(self):
        self.ficheiro_apostas = "apostas_historico.json"
        self.carregar_ou_criar()
    
    def carregar_ou_criar(self):
        """Carrega histórico de apostas ou cria ficheiro novo"""
        if os.path.exists(self.ficheiro_apostas):
            try:
                with open(self.ficheiro_apostas, 'r', encoding='utf-8') as f:
                    self.dados = json.load(f)
            except:
                self.dados = {"apostas": []}
        else:
            self.dados = {"apostas": []}
    
    def guardar(self):
        """Guarda dados em ficheiro JSON"""
        try:
            with open(self.ficheiro_apostas, 'w', encoding='utf-8') as f:
                json.dump(self.dados, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ Erro ao guardar: {e}")
            return False
    
    def adicionar_aposta(self, aposta_dict: Dict) -> int:
        """Adiciona uma aposta ao histórico"""
        
        aposta = {
            "id": len(self.dados["apostas"]) + 1,
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "jogo": aposta_dict.get("jogo"),
            "liga": aposta_dict.get("liga"),
            "tipo": aposta_dict.get("tipo"),
            "odds": aposta_dict.get("odds"),
            "probabilidade": aposta_dict.get("probabilidade"),
            "roi_esperado": aposta_dict.get("roi"),
            "resultado": None,  # ✅ Ganhou / ❌ Perdeu / ⏳ Pendente
            "roi_real": None,
            "data_resultado": None
        }
        
        self.dados["apostas"].append(aposta)
        self.guardar()
        
        return aposta["id"]
    
    def registar_resultado(self, aposta_id: int, resultado: str) -> bool:
        """
        Regista resultado de uma aposta
        resultado: "ganhou" ou "perdeu"
        """
        
        for aposta in self.dados["apostas"]:
            if aposta["id"] == aposta_id:
                aposta["resultado"] = resultado
                aposta["data_resultado"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                
                # Calcula ROI real
                if resultado == "ganhou":
                    aposta["roi_real"] = round((aposta["odds"] - 1) * 100, 1)
                else:
                    aposta["roi_real"] = -100  # Perda total
                
                self.guardar()
                return True
        
        return False
    
    def obter_aposta(self, aposta_id: int) -> Optional[Dict]:
        """Obtém aposta por ID"""
        for aposta in self.dados["apostas"]:
            if aposta["id"] == aposta_id:
                return aposta
        return None
    
    def obter_apostas_hoje(self) -> List[Dict]:
        """Obtém apostas de hoje"""
        hoje = datetime.now().strftime("%d/%m/%Y")
        return [a for a in self.dados["apostas"] if a["data"].startswith(hoje)]
    
    def obter_apostas_pendentes(self) -> List[Dict]:
        """Obtém apostas sem resultado ainda"""
        return [a for a in self.dados["apostas"] if a["resultado"] is None]
    
    def obter_apostas_finalizadas(self) -> List[Dict]:
        """Obtém apostas com resultado"""
        return [a for a in self.dados["apostas"] if a["resultado"] is not None]
    
    def calcular_estatisticas(self, apostas: List[Dict] = None) -> Dict:
        """Calcula estatísticas"""
        
        if apostas is None:
            apostas = self.dados["apostas"]
        
        if not apostas:
            return {
                "total": 0,
                "ganhas": 0,
                "perdidas": 0,
                "pendentes": 0,
                "win_rate": 0,
                "roi_medio_esperado": 0,
                "roi_medio_real": 0,
                "lucro_real": 0
            }
        
        ganhas = [a for a in apostas if a["resultado"] == "ganhou"]
        perdidas = [a for a in apostas if a["resultado"] == "perdeu"]
        pendentes = [a for a in apostas if a["resultado"] is None]
        
        finalizadas = len(ganhas) + len(perdidas)
        
        win_rate = (len(ganhas) / finalizadas * 100) if finalizadas > 0 else 0
        
        roi_esperado_total = sum(a["roi_esperado"] for a in apostas)
        roi_medio_esperado = roi_esperado_total / len(apostas) if apostas else 0
        
        roi_real_total = sum(a["roi_real"] for a in (ganhas + perdidas) if a["roi_real"] is not None)
        roi_medio_real = roi_real_total / finalizadas if finalizadas > 0 else 0
        
        # Lucro em euros (assumindo €1 por aposta)
        lucro_real = len(ganhas) - len(perdidas)
        
        return {
            "total": len(apostas),
            "ganhas": len(ganhas),
            "perdidas": len(perdidas),
            "pendentes": len(pendentes),
            "win_rate": round(win_rate, 1),
            "roi_medio_esperado": round(roi_medio_esperado, 1),
            "roi_medio_real": round(roi_medio_real, 1),
            "lucro_real": lucro_real
        }
    
    def gerar_relatorio(self, dias: int = 1) -> str:
        """Gera relatório de performance"""
        
        # Obtém apostas dos últimos dias
        apostas_recentes = self.dados["apostas"][-100:]  # Últimas 100
        
        stats = self.calcular_estatisticas(apostas_recentes)
        
        relatorio = "📊 RELATÓRIO DE PERFORMANCE\n"
        relatorio += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        relatorio += f"📈 ESTATÍSTICAS:\n"
        relatorio += f"   Total: {stats['total']} apostas\n"
        relatorio += f"   ✅ Ganhas: {stats['ganhas']}\n"
        relatorio += f"   ❌ Perdidas: {stats['perdidas']}\n"
        relatorio += f"   ⏳ Pendentes: {stats['pendentes']}\n\n"
        
        if stats['ganhas'] + stats['perdidas'] > 0:
            relatorio += f"📊 WIN RATE: {stats['win_rate']}%\n\n"
        
        relatorio += f"💰 ROI:\n"
        relatorio += f"   Esperado: +{stats['roi_medio_esperado']}%\n"
        relatorio += f"   Real: +{stats['roi_medio_real']}%\n"
        relatorio += f"   Lucro: €{stats['lucro_real']}\n\n"
        
        # Últimas 5 apostas
        relatorio += "📋 ÚLTIMAS APOSTAS:\n"
        for aposta in apostas_recentes[-5:]:
            status = "✅" if aposta["resultado"] == "ganhou" else "❌" if aposta["resultado"] == "perdeu" else "⏳"
            relatorio += f"   {status} #{aposta['id']} {aposta['jogo'][:30]} @{aposta['odds']}\n"
        
        return relatorio
    
    def exportar_csv(self) -> str:
        """Exporta histórico como CSV"""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.dados["apostas"][0].keys())
        
        writer.writeheader()
        writer.writerows(self.dados["apostas"])
        
        return output.getvalue()
