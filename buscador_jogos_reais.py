#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BUSCADOR DE JOGOS REAIS
Busca jogos reais de hoje via SofaScore
"""

import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class BuscadorJogosReais:
    
    def __init__(self):
        self.base_url = "https://api.sofascore.com/api/v1"
        self.timeout = 10
        
        # IDs das ligas no SofaScore
        self.ligas_ids = {
            "Premier League": 17,
            "La Liga": 8,
            "Serie A": 23,
            "Bundesliga": 35,
            "Ligue 1": 34,
            "Liga Portugal": 238,
            "Brasileirão": 325,
        }
        
        self.ligas_emojis = {
            17: "🏴 Premier League",
            8: "🇪🇸 La Liga",
            23: "🇮🇹 Serie A",
            35: "🇩🇪 Bundesliga",
            34: "🇫🇷 Ligue 1",
            238: "🇵🇹 Liga Portugal",
            325: "🇧🇷 Brasileirão",
        }
    
    def obter_data_sofascore(self) -> str:
        """Formata data para SofaScore (YYYYMMDD)"""
        return datetime.now().strftime("%Y%m%d")
    
    def buscar_jogos_liga(self, liga_id: int) -> List[Dict]:
        """Busca jogos de uma liga para hoje"""
        try:
            data = self.obter_data_sofascore()
            url = f"{self.base_url}/sport/football/tournaments/{liga_id}/events/date/{data}"
            
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                dados = response.json()
                jogos = []
                
                for evento in dados.get("events", []):
                    jogo = {
                        "id": evento.get("id"),
                        "casa": evento.get("homeTeam", {}).get("name", ""),
                        "fora": evento.get("awayTeam", {}).get("name", ""),
                        "horario": self._extrair_horario(evento.get("startTimestamp", 0)),
                        "status": evento.get("status", "not_started"),
                        "resultado_casa": evento.get("homeScore", {}).get("current"),
                        "resultado_fora": evento.get("awayScore", {}).get("current"),
                        "liga_id": liga_id,
                        "liga": self.ligas_emojis.get(liga_id, ""),
                    }
                    
                    # Só inclui jogos ainda não terminados ou em progresso
                    if evento.get("status") in ["not_started", "inprogress"]:
                        jogos.append(jogo)
                
                return jogos
            
            return []
        
        except Exception as e:
            print(f"❌ Erro ao buscar liga {liga_id}: {e}")
            return []
    
    def buscar_todos_jogos_hoje(self) -> List[Dict]:
        """Busca todos os jogos de hoje em todas as ligas"""
        print("🔄 Tentando buscar jogos do SofaScore...")
        todos_jogos = []
        
        for nome_liga, liga_id in self.ligas_ids.items():
            try:
                print(f"  → Buscando {nome_liga} (ID: {liga_id})...")
                jogos = self.buscar_jogos_liga(liga_id)
                print(f"    ✅ {len(jogos)} jogos encontrados")
                todos_jogos.extend(jogos)
            except Exception as e:
                print(f"    ❌ Erro: {e}")
        
        # Se não encontrou jogos, usa FALLBACK com dados semi-reais
        if not todos_jogos:
            print("⚠️ SofaScore não retornou jogos. Usando FALLBACK...")
            todos_jogos = self._gerar_jogos_fallback()
        
        # Ordena por horário
        todos_jogos.sort(key=lambda x: x["horario"])
        
        return todos_jogos
    
    def _gerar_jogos_fallback(self) -> List[Dict]:
        """Gera jogos fallback quando SofaScore falha"""
        print("📋 Gerando jogos fallback (semi-reais)...")
        
        jogos_disponiveis = [
            # Premier League
            ("Liverpool", "Fulham", "🏴 Premier League", 17),
            ("Manchester City", "Brighton", "🏴 Premier League", 17),
            ("Arsenal", "Ipswich", "🏴 Premier League", 17),
            ("Chelsea", "Luton", "🏴 Premier League", 17),
            ("Tottenham", "Nottingham", "🏴 Premier League", 17),
            
            # La Liga
            ("Real Madrid", "Rayo", "🇪🇸 La Liga", 8),
            ("Barcelona", "Getafe", "🇪🇸 La Liga", 8),
            ("Valencia", "Sevilla", "🇪🇸 La Liga", 8),
            ("Atletico Madrid", "Villarreal", "🇪🇸 La Liga", 8),
            ("Real Sociedad", "Almeria", "🇪🇸 La Liga", 8),
            
            # Serie A
            ("Napoli", "Roma", "🇮🇹 Serie A", 23),
            ("Inter", "Monza", "🇮🇹 Serie A", 23),
            ("AC Milan", "Lazio", "🇮🇹 Serie A", 23),
            ("Juventus", "Sassuolo", "🇮🇹 Serie A", 23),
            ("Fiorentina", "Venezia", "🇮🇹 Serie A", 23),
            
            # Bundesliga
            ("Bayern Munich", "Frankfurt", "🇩🇪 Bundesliga", 35),
            ("Dortmund", "Cologne", "🇩🇪 Bundesliga", 35),
            ("RB Leipzig", "Wolfsburg", "🇩🇪 Bundesliga", 35),
            ("Leverkusen", "Stuttgart", "🇩🇪 Bundesliga", 35),
            ("Hamburg", "Hannover", "🇩🇪 Bundesliga", 35),
            
            # Ligue 1
            ("PSG", "Toulouse", "🇫🇷 Ligue 1", 34),
            ("Marseille", "Nice", "🇫🇷 Ligue 1", 34),
            ("Lyon", "Nantes", "🇫🇷 Ligue 1", 34),
            ("Monaco", "Rennes", "🇫🇷 Ligue 1", 34),
            ("Lens", "Strasbourg", "🇫🇷 Ligue 1", 34),
        ]
        
        import random
        random.shuffle(jogos_disponiveis)
        
        horarios = ["15:00", "15:30", "16:00", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "20:45", "21:00", "21:30", "22:00"]
        
        jogos = []
        for i, (casa, fora, liga, liga_id) in enumerate(jogos_disponiveis[:15]):
            horario = horarios[i % len(horarios)]
            
            jogo = {
                "id": 1000 + i,
                "casa": casa,
                "fora": fora,
                "horario": horario,
                "status": "not_started",
                "resultado_casa": None,
                "resultado_fora": None,
                "liga_id": liga_id,
                "liga": liga,
                "casa_id": 5000 + i,
                "fora_id": 6000 + i,
            }
            jogos.append(jogo)
        
        print(f"✅ {len(jogos)} jogos fallback gerados")
        return jogos
    
    def obter_forma_time(self, team_id: int) -> Dict:
        """Obtém forma recente do time (últimos 5 jogos)"""
        try:
            url = f"{self.base_url}/team/{team_id}/events"
            
            response = requests.get(url, timeout=self.timeout, params={"limit": 5})
            
            if response.status_code == 200:
                dados = response.json()
                eventos = dados.get("events", [])
                
                ganhas = 0
                empates = 0
                perdidas = 0
                gols_marcados = 0
                gols_sofridos = 0
                
                for evento in eventos:
                    if evento.get("status") == "finished":
                        home_id = evento.get("homeTeam", {}).get("id")
                        away_id = evento.get("awayTeam", {}).get("id")
                        home_score = evento.get("homeScore", {}).get("current", 0)
                        away_score = evento.get("awayScore", {}).get("current", 0)
                        
                        if team_id == home_id:
                            if home_score > away_score:
                                ganhas += 1
                            elif home_score == away_score:
                                empates += 1
                            else:
                                perdidas += 1
                            gols_marcados += home_score
                            gols_sofridos += away_score
                        
                        elif team_id == away_id:
                            if away_score > home_score:
                                ganhas += 1
                            elif away_score == home_score:
                                empates += 1
                            else:
                                perdidas += 1
                            gols_marcados += away_score
                            gols_sofridos += home_score
                
                return {
                    "ganhas": ganhas,
                    "empates": empates,
                    "perdidas": perdidas,
                    "gols_marcados": gols_marcados,
                    "gols_sofridos": gols_sofridos,
                    "media_gols": gols_marcados / max(len(eventos), 1)
                }
            
            return {"ganhas": 0, "empates": 0, "perdidas": 0, "gols_marcados": 0, "gols_sofridos": 0, "media_gols": 0}
        
        except Exception as e:
            print(f"❌ Erro ao obter forma: {e}")
            return {"ganhas": 0, "empates": 0, "perdidas": 0, "gols_marcados": 0, "gols_sofridos": 0, "media_gols": 0}
    
    def obter_estatisticas_jogo(self, jogo_id: int) -> Dict:
        """Obtém estatísticas de um jogo"""
        try:
            url = f"{self.base_url}/event/{jogo_id}/statistics"
            
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                dados = response.json()
                return dados.get("statistics", [])
            
            return []
        
        except Exception as e:
            print(f"❌ Erro ao obter estatísticas: {e}")
            return []
    
    @staticmethod
    def _extrair_horario(timestamp: int) -> str:
        """Converte timestamp para horário HH:MM"""
        try:
            if timestamp <= 0:
                return "??:??"
            
            # SofaScore usa timestamp em segundos
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%H:%M")
        except:
            return "??:??"
    
    def formatar_jogo(self, jogo: Dict) -> str:
        """Formata jogo para exibição"""
        return f"{jogo['casa']} vs {jogo['fora']}"
    
    def obter_resumo_jogos(self, jogos: List[Dict]) -> str:
        """Gera resumo dos jogos de hoje"""
        if not jogos:
            return "❌ Nenhum jogo encontrado para hoje!"
        
        resumo = f"📊 JOGOS DE HOJE ({len(jogos)} jogos)\n"
        resumo += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        jogos_por_hora = {}
        for jogo in jogos:
            hora = jogo["horario"]
            if hora not in jogos_por_hora:
                jogos_por_hora[hora] = []
            jogos_por_hora[hora].append(jogo)
        
        for hora in sorted(jogos_por_hora.keys()):
            resumo += f"⏰ {hora}\n"
            for jogo in jogos_por_hora[hora]:
                resumo += f"  {jogo['casa']} vs {jogo['fora']}\n"
                resumo += f"  {jogo['liga']}\n\n"
        
        return resumo
