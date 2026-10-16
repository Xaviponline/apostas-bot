"""Pistas PASSIVAS das listagens de fixtures já devolvidas, sem associações novas.

Uma equipa visível na lista não comprova a presença do jogo pretendido.
Zero HTTP e zero alteração dos critérios de escolha de odds.
"""


def recolher_pistas(jogo, eventos, primarios, complemento_consultado, nome_compativel):
    campos = {
        "versao": 1,
        "primarios_vistos": min(max(int(primarios), 0), 10000),
        "complementar_consultada": bool(complemento_consultado),
        "complementares_vistos": 0,
        "casa_primaria": False,
        "fora_primaria": False,
        "casa_complementar": False,
        "fora_complementar": False,
        "par_invertido": False,
    }
    casa = jogo.get("casa")
    fora = jogo.get("fora")
    for evento in eventos or []:
        if not isinstance(evento, dict):
            continue
        complementar = bool(evento.get("_origem_descoberta_complementar"))
        origem = "complementar" if complementar else "primaria"
        if complementar:
            campos["complementares_vistos"] = min(
                campos["complementares_vistos"] + 1, 10000
            )
        if nome_compativel(casa, evento.get("casa")):
            campos["casa_" + origem] = True
        if nome_compativel(fora, evento.get("fora")):
            campos["fora_" + origem] = True
        # Nunca associar inversões de mandante/visitante automaticamente.
        if (
            nome_compativel(casa, evento.get("fora"))
            and nome_compativel(fora, evento.get("casa"))
        ):
            campos["par_invertido"] = True
    return campos
