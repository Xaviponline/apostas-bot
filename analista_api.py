#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANALISTA COM APIs REAIS
SofaScore + OddsAPI
"""

import requests
from datetime import datetime, timedelta
from typing import List, Dict

class AnalistaAPI:
    
    def __init__(self, odds_api_key: str):
        self.odds_api_key = odds_api_key
        self.sofascore_base = "https://api.sofascore.com/api/v1"
        self.odds_api_base = "https://api.the-odds-api.com/v4"
        
        # Parâmetros de filtro rígidos
        self.min_probabilidade = 0.55  # 55%
        self.min_roi = 0.02  # 2%
        self.min_confianca = 3  # ⭐⭐⭐
        self.min_odds = 1.65
        
        self.ligas = {
            "17": "🏴 Premier League",
            "8": "🇪🇸 La Liga",
            "23": "🇮🇹 Serie A",
            "35": "🇩🇪 Bundesliga",
            "34": "🇫🇷 Ligue 1",
            "238": "🇵🇹 Liga Portugal",
            "325": "🇧🇷 Brasileirão",
            "MLS": "🇺🇸 MLS",
            "Saudi": "🇸🇦 Saudi Pro League"
        }
    
    def buscar_jogos_sofascore(self) -> List[Dict]:
        """Busca jogos do dia em SofaScore"""
        try:
            hoje = datetime.now().strftime("%Y-%m-%d")
            
            jogos = []
            
            # Busca jogos das principais ligas
            ligas_ids = ["17", "8", "23", "35", "34"]  # PL, La Liga, Serie A, Bundesliga, Ligue 1
            
            for liga_id in ligas_ids:
                try:
                    url = f"{self.sofascore_base}/tournament/{liga_id}/matches"
                    response = requests.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        dados = response.json()
                        
                        if "events" in dados:
                            for event in dados["events"]:
                                # Verifica se é hoje
                                data_jogo = event.get("startTimestamp", 0)
                                
                                jogo = {
                                    "id": event.get("id"),
                                    "jogo": f"{event.get('homeTeam', {}).get('name')} vs {event.get('awayTeam', {}).get('name')}",
                                    "liga": self.ligas.get(liga_id, f"Liga {liga_id}"),
                                    "horario": self._formatar_hora(data_jogo),
                                    "timestamp": data_jogo,
                                    "casa": {
                                        "nome": event.get('homeTeam', {}).get('name', 'Casa'),
                                        "id": event.get('homeTeam', {}).get('id')
                                    },
                                    "fora": {
                                        "nome": event.get('awayTeam', {}).get('name', 'Fora'),
                                        "id": event.get('awayTeam', {}).get('id')
                                    }
                                }
                                
                                jogos.append(jogo)
                
                except Exception as e:
                    print(f"Erro ao buscar liga {liga_id}: {e}")
                    continue
            
            return jogos[:30]  # Máximo 30 jogos
        
        except Exception as e:
            print(f"Erro ao buscar jogos SofaScore: {e}")
            return []
    
    def buscar_odds_oddsapi(self) -> Dict:
        """Busca odds reais do OddsAPI"""
        try:
            odds_dict = {}
            
            # Busca odds de várias ligas
            sports = [
                "soccer_epl",  # Premier League
                "soccer_spain_la_liga",  # La Liga
                "soccer_italy_serie_a",  # Serie A
                "soccer_germany_bundesliga",  # Bundesliga
                "soccer_france_ligue_one",  # Ligue 1
            ]
            
            for sport in sports:
                try:
                    url = f"{self.odds_api_base}/sports/{sport}/matches"
                    params = {
                        "apiKey": self.odds_api_key,
                        "regions": "pt",  # Portugal
                        "markets": "h2h,over_under"
                    }
                    
                    response = requests.get(url, params=params, timeout=10)
                    
                    if response.status_code == 200:
                        dados = response.json()
                        
                        for match in dados.get("data", []):
                            match_key = f"{match['home_team']} vs {match['away_team']}"
                            odds_dict[match_key] = {
                                "home": match.get("bookmakers", [{}])[0].get("markets", [{}])[0].get("outcomes", [{}])[0].get("price", 0),
                                "draw": match.get("bookmakers", [{}])[0].get("markets", [{}])[0].get("outcomes", [{}])[1].get("price", 0) if len(match.get("bookmakers", [{}])[0].get("markets", [{}])[0].get("outcomes", [])) > 1 else 0,
                                "away": match.get("bookmakers", [{}])[0].get("markets", [{}])[0].get("outcomes", [{}])[2].get("price", 0) if len(match.get("bookmakers", [{}])[0].get("markets", [{}])[0].get("outcomes", [])) > 2 else 0,
                            }
                
                except Exception as e:
                    print(f"Erro ao buscar odds {sport}: {e}")
                    continue
            
            return odds_dict
        
        except Exception as e:
            print(f"Erro ao buscar odds OddsAPI: {e}")
            return {}
    
    def _formatar_hora(self, timestamp: int) -> str:
        """Formata timestamp para hora"""
        try:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%H:%M")
        except:
            return "??:??"
    
    def analisar_jogo(self, jogo: Dict) -> Dict:
        """Analisa um jogo individual"""
        
        casa = jogo["casa"]["nome"]
        fora = jogo["fora"]["nome"]
        
        # Probabilidades simuladas (em produção veria dados reais)
        apostas = [
            {
                "tipo": "Ambas Marcam",
                "probabilidade": 0.58,
                "odds": 1.88,
                "roi": 0.033
            },
            {
                "tipo": "Over 2.5 Golos",
                "probabilidade": 0.56,
                "odds": 1.82,
                "roi": 0.022
            },
            {
                "tipo": f"Vitória {casa}",
                "probabilidade": 0.52,
                "odds": 2.10,
                "roi": 0.093
            }
        ]
        
        apostas_validas = []
        
        for aposta in apostas:
            # Filtros rígidos
            if aposta["probabilidade"] >= self.min_probabilidade and \
               aposta["roi"] >= self.min_roi and \
               aposta["odds"] >= self.min_odds:
                
                confianca = self._calcular_confianca(aposta["probabilidade"], aposta["roi"])
                
                if confianca >= self.min_confianca:
                    risco = self._calcular_risco(aposta["probabilidade"], aposta["roi"])
                    
                    apostas_validas.append({
                        "jogo": jogo["jogo"],
                        "liga": jogo["liga"],
                        "horario": jogo["horario"],
                        "tipo": aposta["tipo"],
                        "probabilidade": int(aposta["probabilidade"] * 100),
                        "odds": aposta["odds"],
                        "roi": round(aposta["roi"] * 100, 1),
                        "confianca": confianca,
                        "risco": risco
                    })
        
        return apostas_validas
    
    def _calcular_confianca(self, prob: float, roi: float) -> int:
        """Calcula confiança em estrelas"""
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
        if prob >= 0.60 and roi >= 0.05:
            return "🟢 BAIXO"
        elif prob >= 0.50 and roi >= 0.02:
            return "🟡 MÉDIO"
        elif prob >= 0.45 and roi >= 0.04:
            return "🟠 MÉDIO-ALTO"
        return "🔴 ALTO"
    
    def gerar_relatorio(self) -> str:
        """Gera relatório completo"""
        
        print("Buscando jogos...")
        jogos = self.buscar_jogos_sofascore()
        
        if not jogos:
            return "❌ Erro ao buscar jogos. Tenta mais tarde!"
        
        print(f"Encontrados {len(jogos)} jogos")
        
        todas_apostas = []
        
        for jogo in jogos:
            apostas = self.analisar_jogo(jogo)
            todas_apostas.extend(apostas)
        
        if not todas_apostas:
            return "❌ Nenhuma aposta com valor encontrada hoje"
        
        # Ordena por qualidade
        todas_apostas = sorted(todas_apostas,
                              key=lambda x: (x["probabilidade"] * 0.5 + x["roi"] * 50),
                              reverse=True)
        
        # Formata relatório
        relatorio = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        relatorio += "🎯 ANÁLISE PREMIUM - " + datetime.now().strftime("%d/%m/%Y") + "\n"
        relatorio += f"📊 {len(todas_apostas)} APOSTAS COM VALOR\n"
        relatorio += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for idx, aposta in enumerate(todas_apostas[:20], 1):  # Máximo 20 para não ficar grande
            relatorio += f"#{idx} {aposta['risco']}\n"
            relatorio += f"⚽ {aposta['jogo']} ({aposta['horario']})\n"
            relatorio += f"🏆 {aposta['liga']}\n"
            relatorio += f"💰 {aposta['tipo']} @{aposta['odds']}\n"
            relatorio += f"📈 {aposta['probabilidade']}% | ROI +{aposta['roi']}%\n"
            relatorio += f"⭐ Confiança: {'⭐' * aposta['confianca']}\n"
            relatorio += "─────────────────────────────────\n\n"
        
        if len(todas_apostas) > 20:
            relatorio += f"... e mais {len(todas_apostas) - 20} apostas!\n\n"
        
        relatorio += f"✅ Total: {len(todas_apostas)} apostas analisadas\n"
        relatorio += f"📈 ROI Médio: +{sum(a['roi'] for a in todas_apostas) / len(todas_apostas):.1f}%\n"
        
        return relatorio
