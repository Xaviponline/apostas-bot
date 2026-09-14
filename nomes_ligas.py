"""Nomes de competições apresentados ao utilizador em português de Portugal.

Os nomes internos vindos das fontes permanecem inalterados. Este módulo só
traduz/normaliza a apresentação no Telegram.
"""
import re
import unicodedata


def _normalizar(texto):
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(ch for ch in valor if not unicodedata.combining(ch))
    valor = re.sub(r"\s+", " ", valor).strip().casefold()
    return valor


NOMES_PT = {
    # Portugal
    "portuguese primeira liga": "Liga Portugal",
    "primeira liga": "Liga Portugal",
    "liga portugal": "Liga Portugal",
    "liga portugal 2": "Liga Portugal 2",
    "segunda liga": "Liga Portugal 2",
    "portuguese liga 2": "Liga Portugal 2",
    "taca de portugal": "Taça de Portugal",
    "portuguese cup": "Taça de Portugal",
    "liga revelacao sub-23": "Liga Revelação Sub-23",

    # UEFA / seleções
    "uefa champions league": "Liga dos Campeões",
    "champions league": "Liga dos Campeões",
    "uefa europa league": "Liga Europa",
    "europa league": "Liga Europa",
    "uefa conference league": "Liga Conferência",
    "uefa europa conference league": "Liga Conferência",
    "conference league": "Liga Conferência",
    "uefa nations league": "Liga das Nações",
    "nations league": "Liga das Nações",
    "uefa european championship": "Campeonato da Europa",
    "european championship": "Campeonato da Europa",
    "fifa world cup": "Campeonato do Mundo",
    "world cup": "Campeonato do Mundo",

    # Inglaterra
    "english premier league": "Premier League",
    "premier league": "Premier League",
    "english fa cup": "FA Cup",
    "fa cup": "FA Cup",
    "english carabao cup": "EFL Cup",
    "english league cup": "EFL Cup",
    "efl cup": "EFL Cup",
    "english league championship": "Championship",
    "efl championship": "Championship",
    "championship": "Championship",
    "english league one": "League One",
    "league one": "League One",

    # Espanha
    "spanish laliga": "LaLiga",
    "laliga": "LaLiga",
    "spanish segunda division": "Segunda Divisão",
    "segunda division": "Segunda Divisão",
    "copa del rey": "Taça do Rei",
    "spanish copa del rey": "Taça do Rei",

    # Itália
    "italian serie a": "Série A",
    "serie a": "Série A",
    "italian serie b": "Série B",
    "serie b": "Série B",
    "italian serie c": "Série C",
    "serie c": "Série C",
    "coppa italia": "Taça de Itália",
    "italian coppa italia": "Taça de Itália",

    # Alemanha
    "german bundesliga": "Bundesliga",
    "bundesliga": "Bundesliga",
    "german 2. bundesliga": "2. Bundesliga",
    "2. bundesliga": "2. Bundesliga",
    "german 3. liga": "3. Liga",
    "3. liga": "3. Liga",
    "dfb pokal": "Taça da Alemanha",

    # França
    "french ligue 1": "Ligue 1",
    "ligue 1": "Ligue 1",
    "french ligue 2": "Ligue 2",
    "ligue 2": "Ligue 2",
    "coupe de france": "Taça de França",

    # Países Baixos
    "dutch eredivisie": "Eredivisie",
    "eredivisie": "Eredivisie",
    "dutch keuken kampioen divisie": "Eerste Divisie",
    "keuken kampioen divisie": "Eerste Divisie",
    "eerste divisie": "Eerste Divisie",
    "knvb beker": "Taça dos Países Baixos",

    # Turquia
    "turkish super lig": "Super Liga Turca",
    "super lig": "Super Liga Turca",
    "turkish 1. lig": "1. Liga Turca",
    "tff 1. lig": "1. Liga Turca",

    # Bélgica / Escandinávia
    "belgian pro league": "Liga Belga",
    "jupiler pro league": "Liga Belga",
    "swedish allsvenskan": "Allsvenskan",
    "allsvenskan": "Allsvenskan",
    "norwegian eliteserien": "Eliteserien",
    "eliteserien": "Eliteserien",

    # América do Sul
    "brasileiro serie a": "Brasileirão Série A",
    "brazilian serie a": "Brasileirão Série A",
    "brasileiro serie b": "Brasileirão Série B",
    "brazilian serie b": "Brasileirão Série B",
    "argentine liga profesional": "Liga Argentina",
    "copa libertadores": "Copa Libertadores",
    "conmebol libertadores": "Copa Libertadores",
    "copa sudamericana": "Copa Sul-Americana",
    "conmebol sudamericana": "Copa Sul-Americana",
    "copa america": "Copa América",

    # América do Norte
    "major league soccer": "MLS",
    "mls": "MLS",
}


def nome_liga_pt(nome):
    """Devolve um nome familiar em PT-PT, preservando nomes não mapeados."""
    original = str(nome or "Competição").strip() or "Competição"
    chave = _normalizar(original)
    if chave in NOMES_PT:
        return NOMES_PT[chave]

    # Algumas fontes acrescentam prefixos/sufixos ao nome canónico.
    for conhecido, traduzido in sorted(NOMES_PT.items(), key=lambda item: len(item[0]), reverse=True):
        if conhecido and conhecido in chave:
            return traduzido
    return original
