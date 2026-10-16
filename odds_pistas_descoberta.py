"""Pistas PASSIVAS das listagens de fixtures já devolvidas, sem associações novas.

Uma equipa visível na lista não comprova a presença do jogo pretendido.
Zero HTTP e zero alteração dos critérios de escolha de odds.
"""


def _apenas_sufixo_saf(esperado, observado, nome_compativel, normalizar):
    """Só sinaliza SAF final no nome da fonte, sem criar equivalências no motor."""
    if nome_compativel(esperado, observado):
        return False
    tokens = normalizar(observado).split()
    return bool(
        len(tokens) > 1
        and tokens[-1] == "saf"
        and nome_compativel(esperado, " ".join(tokens[:-1]))
    )


def recolher_pistas(
    jogo, eventos, primarios, complemento_consultado, nome_compativel,
    normalizar=None, timestamp_fn=None,
):
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
        # Diagnóstico novo (somente listas já recebidas, nunca matching).
        "saf_testado": callable(normalizar) and callable(timestamp_fn),
        "saf_casa_primaria": False,
        "saf_fora_primaria": False,
        "saf_casa_complementar": False,
        "saf_fora_complementar": False,
        "saf_par_primario": 0,
        "saf_par_complementar": 0,
        "saf_par_hora_compativel": 0,
        "saf_par_hora_divergente": 0,
        "saf_par_hora_desconhecida": 0,
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
        # SAF é uma designação jurídica: observar a variante como hipótese,
        # sem lhe atribuir fixture/mercado/odd, mesmo com horário compatível.
        if campos["saf_testado"]:
            casa_saf = _apenas_sufixo_saf(
                casa, evento.get("casa"), nome_compativel, normalizar
            )
            fora_saf = _apenas_sufixo_saf(
                fora, evento.get("fora"), nome_compativel, normalizar
            )
            if casa_saf:
                campos["saf_casa_" + origem] = True
            if fora_saf:
                campos["saf_fora_" + origem] = True
            mesma_partida_possivel = (
                (casa_saf or nome_compativel(casa, evento.get("casa")))
                and (fora_saf or nome_compativel(fora, evento.get("fora")))
                and (casa_saf or fora_saf)
            )
            if mesma_partida_possivel:
                chave = "saf_par_complementar" if complementar else "saf_par_primario"
                campos[chave] = min(campos[chave] + 1, 99)
                try:
                    ts_modelo = float(jogo.get("timestamp"))
                    ts_fonte = timestamp_fn(evento.get("data"))
                except (TypeError, ValueError, OverflowError):
                    ts_modelo = ts_fonte = None
                if ts_modelo is None or ts_fonte is None:
                    fase_hora = "saf_par_hora_desconhecida"
                elif abs(ts_modelo - ts_fonte) <= 90 * 60:
                    fase_hora = "saf_par_hora_compativel"
                else:
                    fase_hora = "saf_par_hora_divergente"
                campos[fase_hora] = min(campos[fase_hora] + 1, 99)
        # Nunca associar inversões de mandante/visitante automaticamente.
        if (
            nome_compativel(casa, evento.get("fora"))
            and nome_compativel(fora, evento.get("casa"))
        ):
            campos["par_invertido"] = True
    return campos
