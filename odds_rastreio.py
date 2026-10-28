"""Registo local append-only de metadados OddsPapi observados em chamadas existentes.

Sem consultar o fornecedor, sem credenciais e sem reescrever qualquer snapshot.
Nao constitui confirmacao independente de odds na app Betano.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import unicodedata
from pathlib import Path
import json
import os


class RastreioOdds:
    MAX_BYTES = 20 * 1024 * 1024

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    def registar(self, selecoes, operacao="ODDS"):
        if self.path is None:
            return 0
        linhas = []
        agora = datetime.now(timezone.utc).isoformat()
        for s in selecoes or []:
            if not isinstance(s, dict):
                continue
            jogo = s.get("jogo") or {}
            diag = s.get("_odds_diag")
            meta = s.get("_rastreio_odds") or {}
            contexto = s.get("_odds_evento_contexto") or {}
            if not isinstance(contexto, dict):
                contexto = {}
            # Apenas metadados e cotacoes observadas; nunca guardar payload
            # integral da API, credenciais ou identificadores de clientes.
            if not meta and not diag:
                continue
            # Guardar somente contagens de mercados já recebidos em memória.
            # Nem payload, nem odds alternativas, nem novos pedidos à API.
            contexto_mercados = s.get("_odds_contexto_mercados")
            contagens_mercados = {}
            if isinstance(contexto_mercados, dict):
                for chave in ("total", "compativeis", "sem_catalogo"):
                    numero = contexto_mercados.get(chave)
                    if isinstance(numero, int) and not isinstance(numero, bool) and 0 <= numero <= 999:
                        contagens_mercados[chave] = numero
            # Contagens de linhas já observadas, sem odds, IDs ou payloads.
            origem_linha = s.get("_odds_contexto_linha")
            resumo_linha = {}
            if isinstance(origem_linha, dict):
                contadores = (
                    "mercados_linha_alvo", "mercados_outra_linha",
                    "mercados_sem_handicap", "lado_alvo_linha_alvo",
                    "lado_alvo_outra_linha", "lado_alvo_sem_handicap",
                    "lado_desconhecido_linha_alvo",
                )
                for chave in contadores:
                    numero = origem_linha.get(chave)
                    if isinstance(numero, int) and not isinstance(numero, bool) and 0 <= numero <= 999:
                        resumo_linha[chave] = numero
                linhas = origem_linha.get("linhas_handicap")
                if isinstance(linhas, list):
                    from math import isfinite
                    resumo_linha["linhas_handicap"] = [
                        float(v) for v in linhas[:8]
                        if type(v) in (int, float) and isfinite(float(v)) and 0 <= float(v) <= 20
                    ]
                alvo = origem_linha.get("alvo")
                if type(alvo) in (int, float):
                    from math import isfinite
                    if isfinite(float(alvo)) and 0 <= float(alvo) <= 20:
                        resumo_linha["alvo"] = float(alvo)
            pistas = s.get("_odds_descoberta")
            pistas = pistas if isinstance(pistas, dict) and pistas.get("versao") == 1 else {}
            resumo_pistas = {}
            if pistas:
                resumo_pistas = {"versao": 1}
                for campo in ("primarios_vistos", "complementares_vistos"):
                    numero = pistas.get(campo)
                    resumo_pistas[campo] = (
                        min(max(numero, 0), 10000)
                        if isinstance(numero, int) and not isinstance(numero, bool)
                        else 0
                    )
                for campo in (
                    "complementar_consultada", "casa_primaria", "fora_primaria",
                    "casa_complementar", "fora_complementar", "par_invertido",
                ):
                    resumo_pistas[campo] = pistas.get(campo) is True
                if pistas.get("saf_testado") is True:
                    resumo_pistas["saf_testado"] = True
                    for campo in (
                        "saf_casa_primaria", "saf_fora_primaria",
                        "saf_casa_complementar", "saf_fora_complementar",
                    ):
                        resumo_pistas[campo] = pistas.get(campo) is True
                    for campo in (
                        "saf_par_primario", "saf_par_complementar",
                        "saf_par_hora_compativel", "saf_par_hora_divergente",
                        "saf_par_hora_desconhecida",
                    ):
                        numero = pistas.get(campo)
                        resumo_pistas[campo] = (
                            min(max(numero, 0), 99)
                            if isinstance(numero, int) and not isinstance(numero, bool)
                            else 0
                        )
            item = {
                "observado_em": agora,
                "operacao": str(operacao or "ODDS")[:32],
                "jogo": f"{jogo.get('casa') or '?'} vs {jogo.get('fora') or '?'}"[:200],
                "event_id_modelo": str(jogo.get("id") or "")[:64],
                "mercado_modelo": str(s.get("mercado") or "")[:80],
                "liga_modelo": str(jogo.get("liga") or "")[:120],
                "liga_fonte_fixture": str(contexto.get("liga_fixture") or "")[:120],
                "liga_fonte_odds": str(contexto.get("liga_odds") or "")[:120],
                "inicio_fonte_fixture": str(contexto.get("inicio_fixture") or "")[:64],
                "timestamp_jogo": jogo.get("timestamp"),
                "odd_observada": s.get("odd_real"),
                "diagnostico": str(diag or "")[:64],
                "contexto_mercados": contagens_mercados,
                "contexto_linha": resumo_linha,
                "fonte": str(s.get("odds_fonte") or "")[:80],
                "fixture_id_fonte": str(s.get("odds_event_id") or "")[:64],
                "odds_atualizada_em": str(s.get("odds_atualizada_em") or "")[:64],
                "mercado_id_fonte": str(meta.get("market_id") or "")[:64],
                "mercado_nome_fonte": str(meta.get("market_name") or "")[:120],
                "periodo_fonte": str(meta.get("period") or "")[:60],
                "linha_fonte": meta.get("handicap"),
                "selecao_nome_fonte": str(meta.get("selection_name") or "")[:120],
                "outcome_ref_fonte": str(meta.get("outcome_ref") or "")[:80],
                "bookmaker_changed_at": str(meta.get("bookmakerChangedAt") or "")[:64],
                "market_updated_at": str(meta.get("market_updated_at") or "")[:64],
                "resultado_associacao": str(meta.get("association") or "")[:64],
                "alertas_contexto": list(s.get("_odds_alertas") or [])[:6],
                "descoberta_passiva": resumo_pistas,
            }
            linhas.append((json.dumps(item, ensure_ascii=False, sort_keys=True)+"\n").encode("utf-8"))
        if not linhas:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise RuntimeError("Rastreio nao pode ser symlink")
        anterior = self.path.stat().st_size if self.path.exists() else 0
        bloco = b"".join(linhas)
        if anterior + len(bloco) > self.MAX_BYTES:
            raise RuntimeError("Rastreio atingiu limite de 20 MB; requer arquivo manual")
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        with os.fdopen(fd, "ab") as f:
            f.write(bloco)
            f.flush()
            os.fsync(f.fileno())
        return len(linhas)

    def relatorio(self):
        if self.path is None or not self.path.exists():
            return "🔎 RASTREIO ODDS — ainda sem observacoes locais."
        if self.path.is_symlink():
            return "🔎 RASTREIO ODDS — ficheiro inseguro."
        total = com_ref = anomalias = 0
        ultimos = []
        with self.path.open("r", encoding="utf-8") as f:
            for linha in f:
                if not linha.strip():
                    continue
                item = json.loads(linha)
                total += 1
                if item.get("mercado_id_fonte") and item.get("outcome_ref_fonte"):
                    com_ref += 1
                if item.get("diagnostico") or item.get("alertas_contexto"):
                    anomalias += 1
                if item.get("odd_observada") and item.get("mercado_id_fonte"):
                    ultimos.append(item)
                    ultimos = ultimos[-4:]
        linhas = [
            "🔎 RASTREIO ODDS — AUDITORIA LOCAL",
            f"Observacoes: {total}",
            f"Com ID de mercado e referencia de selecao: {com_ref}",
            f"Com diagnostico/alertas: {anomalias}",
            "",
            "ULTIMAS COTACOES COM REFERENCIAS:",
        ]
        for a in reversed(ultimos):
            linhas.append(f"• {a['jogo']} | {a['mercado_modelo']} @{a['odd_observada']}")
            linhas.append(f"  fixture={a['fixture_id_fonte']} | mercado={a['mercado_id_fonte']} | selecao={a['outcome_ref_fonte']}")
        linhas.extend([
            "ℹ️ Metadados observados; nao valida de forma independente a cotacao na Betano.",
            "🔒 Nao altera odds/modelo, nao consulta API e nao guarda chaves.",
        ])
        return "\n".join(linhas)

    @staticmethod
    def _texto_pesquisa(texto):
        texto = unicodedata.normalize("NFKD", str(texto or ""))
        return "".join(c for c in texto if not unicodedata.combining(c)).casefold()

    @staticmethod
    def _hora_portugal(valor):
        if valor in (None, ""):
            return "não registada"
        try:
            if isinstance(valor, (float, int)):
                dt = datetime.fromtimestamp(float(valor), timezone.utc)
            else:
                dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(ZoneInfo("Europe/Lisbon")).strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError, OverflowError, OSError):
            return "data inválida"

    def detalhe(self, termo):
        """Pesquisa local por jogo/fixture e mostra provas existentes.

        Nunca consulta OddsPapi, não reescreve o JSONL nem associa odds.
        Campos antigos não recolhidos são explicitamente desconhecidos.
        """
        termo = str(termo or "").strip()
        if not 3 <= len(termo) <= 80:
            return (
                "🔎 Usa /odds_rastreio_detalhe <nome da equipa ou ID do fixture>\n"
                "Exemplos: /odds_rastreio_detalhe Estudiantes\n"
                "          /odds_rastreio_detalhe RKC"
            )
        if self.path is None or not self.path.exists():
            return "🔎 RASTREIO ODDS — Ainda não existem observações locais."
        if self.path.is_symlink():
            raise RuntimeError("Rastreio não pode ser symlink")
        if self.path.stat().st_size > self.MAX_BYTES:
            raise RuntimeError("Rastreio excede o limite de segurança")
        busca = self._texto_pesquisa(termo)
        total = 0
        ultimos = []
        with self.path.open("r", encoding="utf-8") as f:
            for linha in f:
                if not linha.strip():
                    continue
                item = json.loads(linha)
                if not isinstance(item, dict):
                    raise ValueError("Registo de rastreio inválido")
                campos = (
                    item.get("jogo"), item.get("event_id_modelo"),
                    item.get("fixture_id_fonte"),
                )
                if not any(busca in self._texto_pesquisa(campo) for campo in campos):
                    continue
                total += 1
                ultimos.append(item)
                ultimos = ultimos[-3:]

        if not total:
            return (
                f"🔎 RASTREIO ODDS — '{termo}'\n"
                "Sem observações locais correspondentes.\n"
                "ℹ️ Não foram feitas novas consultas à OddsPapi."
            )

        def campo(item, chave):
            valor = item.get(chave)
            return str(valor) if valor not in (None, "") else "não registado"

        linhas = [
            "🔎 RASTREIO ODDS — DETALHE LOCAL",
            f"🔍 Pesquisa: {termo}",
            f"📚 Observações encontradas: {total} | últimas {len(ultimos)}",
            "ℹ️ As observações podem ser rondas repetidas, não jogos distintos.",
        ]
        for item in reversed(ultimos):
            odd = item.get("odd_observada")
            try:
                odd_txt = f"{float(odd):.2f}".replace(".", ",") if odd is not None else "não registada"
            except (TypeError, ValueError, OverflowError):
                odd_txt = "inválida"
            alertas = item.get("alertas_contexto") or []
            if not isinstance(alertas, list):
                alertas = []
            contexto_mercados = item.get("contexto_mercados")
            contexto_linha = item.get("contexto_linha")
            linhas.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━",
                f"⚽ {campo(item, 'jogo')}",
                f"🎯 Modelo: {campo(item, 'mercado_modelo')} | Odd observada: {odd_txt}",
                f"🕘 Jogo (modelo): {self._hora_portugal(item.get('timestamp_jogo'))}",
                f"🕘 Jogo (fixture fonte): {self._hora_portugal(item.get('inicio_fonte_fixture'))}",
                f"🏆 Liga (modelo): {campo(item, 'liga_modelo')}",
                f"🏆 Liga (fixture): {campo(item, 'liga_fonte_fixture')}",
                f"🏆 Liga (odds): {campo(item, 'liga_fonte_odds')}",
                f"📡 Fonte: {campo(item, 'fonte')} | Observado: {self._hora_portugal(item.get('observado_em'))}",
                f"🆔 Fixture fonte: {campo(item, 'fixture_id_fonte')}",
                f"🔢 Mercado: {campo(item, 'mercado_id_fonte')} — {campo(item, 'mercado_nome_fonte')}",
                f"📋 Período: {campo(item, 'periodo_fonte')} | Linha: {campo(item, 'linha_fonte')}",
                f"🎯 Seleção fonte: {campo(item, 'selecao_nome_fonte')} | Ref: {campo(item, 'outcome_ref_fonte')}",
                f"🔗 Associação: {campo(item, 'resultado_associacao')}",
                f"🕒 Atualização odd: {campo(item, 'odds_atualizada_em')}",
                f"⚠️ Diagnóstico: {campo(item, 'diagnostico')} | Contexto: {', '.join(str(a) for a in alertas) if alertas else 'sem alerta registado'}",
            ])
            if (isinstance(contexto_mercados, dict) and
                all(isinstance(contexto_mercados.get(k), int) and
                    not isinstance(contexto_mercados.get(k), bool)
                    for k in ("total", "compativeis", "sem_catalogo"))):
                linhas.append(
                    f"🧮 Mercados recebidos: {contexto_mercados['total']} | "
                    f"Compatíveis: {contexto_mercados['compativeis']} | "
                    f"Sem catálogo: {contexto_mercados['sem_catalogo']}"
                )
            if isinstance(contexto_linha, dict) and "mercados_linha_alvo" in contexto_linha:
                vistos = contexto_linha.get("linhas_handicap") or []
                vistos_txt = ", ".join(str(v).rstrip("0").rstrip(".") if "." in str(v) else str(v) for v in vistos) or "não observadas"
                linhas.append(
                    f"🔎 Linhas handicap observadas: {vistos_txt} | "
                    f"Mercados no alvo: {contexto_linha.get('mercados_linha_alvo', 0)} | "
                    f"Noutra linha: {contexto_linha.get('mercados_outra_linha', 0)} | "
                    f"Sem handicap: {contexto_linha.get('mercados_sem_handicap', 0)}"
                )
                linhas.append(
                    f"   Seleção-alvo no handicap certo: {contexto_linha.get('lado_alvo_linha_alvo', 0)} | "
                    f"Noutra linha: {contexto_linha.get('lado_alvo_outra_linha', 0)} | "
                    f"Sem handicap: {contexto_linha.get('lado_alvo_sem_handicap', 0)} | "
                    f"Sem lado identificável no alvo: {contexto_linha.get('lado_desconhecido_linha_alvo', 0)}"
                )
        linhas.extend([
            "",
            "ℹ️ Campos 'não registado' não podem ser reconstruídos do histórico; "
            "competições e horas da fonte passam a ser guardadas em futuras recolhas.",
            "ℹ️ Linhas observadas são metadados passivos; a ausência não prova falta de oferta na Betano.",
            "ℹ️ Mercados recebidos e catalogados são contagens, não prova de ausência na Betano.",
            "🔒 Dados locais, sem nova chamada OddsPapi, sem validação independente Betano e sem alterar apostas.",
        ])
        return "\n".join(linhas)

    @staticmethod
    def _instante(valor):
        """Interpretar a hora de observação como UTC, sem data inferida."""
        if not valor:
            return None
        try:
            dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return None
            return dt.timestamp()
        except (ValueError, TypeError, OverflowError):
            return None

    def ultimas_observacoes(self, selecoes, agora=None):
        """Ultima recolha por event_id/mercado/kickoff, apenas evidência local.

        Não prova disponibilidade atual. As leituras anteriores ao kickoff e
        anteriores ao instante da mensagem são as únicas consideradas.
        Nunca altera odds, previsões ou ficheiros.
        """
        dt = agora or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            raise ValueError("Hora com timezone obrigatória")
        alvos = {}
        for p in selecoes or []:
            if not isinstance(p, dict) or p.get("event_id") is None or not p.get("mercado"):
                continue
            try:
                kickoff = float(p["timestamp_jogo"])
                if not (float("-inf") < kickoff < float("inf")):
                    continue
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
            alvos[(str(p["event_id"]), str(p["mercado"]), int(kickoff))] = kickoff

        if not alvos or self.path is None or not self.path.exists():
            return {}
        if self.path.is_symlink() or self.path.stat().st_size > self.MAX_BYTES:
            raise RuntimeError("Rastreio indisponível por segurança")
        resultado = {}
        from math import isfinite
        with self.path.open("r", encoding="utf-8") as ficheiro:
            for linha in ficheiro:
                if not linha.strip():
                    continue
                item = json.loads(linha)
                if not isinstance(item, dict):
                    raise ValueError("Linha de rastreio inválida")
                try:
                    inicio = float(item["timestamp_jogo"])
                    if not isfinite(inicio):
                        continue
                except (KeyError, ValueError, TypeError, OverflowError):
                    continue
                chave = (
                    str(item.get("event_id_modelo") or ""),
                    str(item.get("mercado_modelo") or ""),
                    int(inicio),
                )
                kickoff = alvos.get(chave)
                if kickoff is None:
                    continue
                obs = self._instante(item.get("observado_em"))
                if obs is None or obs > dt.timestamp() or obs >= kickoff:
                    continue
                anterior = resultado.get(chave)
                if anterior is not None and anterior["timestamp"] > obs:
                    continue
                preco = item.get("odd_observada")
                try:
                    preco = float(preco) if preco is not None else None
                    if preco is not None and (not isfinite(preco) or preco <= 1):
                        preco = None
                except (ValueError, TypeError, OverflowError):
                    preco = None
                resultado[chave] = {
                    "timestamp": obs,
                    "preco": preco,
                    "diagnostico": str(item.get("diagnostico") or "")[:64],
                }
        return resultado

    def relatorio_disponibilidade(self, previsoes, agora=None):
        """Diagnóstico READ-ONLY de odds historicas sem reconfirmação.

        Um diagnostico posterior à cotação não prova retirada da odd,
        mas impede que esta leitura a confunda com preço atual.
        Não altera snapshot, estado de VALUE, CLV nem V1.3.
        """
        dt = agora or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            raise ValueError("Hora timezone-aware necessária")
        from datetime import timedelta
        from math import isfinite

        data_limite = (dt.astimezone(ZoneInfo("Europe/Lisbon")).date()
                       - timedelta(days=7)).isoformat()
        registos = previsoes.dados.get("previsoes", [])
        alvos = {}
        for p in registos:
            if not isinstance(p, dict) or str(p.get("data_jogo") or "") < data_limite:
                continue
            minimo = p.get("odd_minima")
            odd = p.get("odd_valor_confirmado")
            if odd is None:
                odd = p.get("odd_real")
            try:
                minimo = float(minimo)
                odd = float(odd)
                inicio = float(p.get("timestamp_jogo"))
                if (not all(isfinite(x) for x in (minimo, odd, inicio))
                    or minimo <= 1 or odd < minimo):
                    continue
            except (TypeError, ValueError, OverflowError):
                continue
            evento = p.get("event_id")
            mercado = p.get("mercado")
            if evento is None or not mercado:
                continue
            chave = (str(evento), str(mercado), int(inicio))
            alvos[chave] = {
                "jogo": f"{p.get('casa') or '?'} vs {p.get('fora') or '?'}",
                "mercado": str(mercado),
                "inicio": inicio,
                "entrada": odd,
                "ultimo": None,
                "n_observacoes": 0,
            }

        if self.path is None or not self.path.exists():
            return (
                "🔎 VALIDADE DAS ODDS — AUDITORIA LOCAL\n"
                "Rastreio de consultas indisponível; não é possível reconfirmar "
                "os preços históricos. Nenhuma aposta foi alterada."
            )
        if self.path.is_symlink() or self.path.stat().st_size > self.MAX_BYTES:
            raise RuntimeError("Rastreio indisponível por segurança")
        with self.path.open("r", encoding="utf-8") as f:
            for linha in f:
                if not linha.strip():
                    continue
                item = json.loads(linha)
                if not isinstance(item, dict):
                    raise ValueError("Rastreio corrompido")
                try:
                    ini = int(float(item.get("timestamp_jogo")))
                except (TypeError, ValueError, OverflowError):
                    continue
                chave = (
                    str(item.get("event_id_modelo") or ""),
                    str(item.get("mercado_modelo") or ""),
                    ini,
                )
                alvo = alvos.get(chave)
                if alvo is None:
                    continue
                observado_ts = self._instante(item.get("observado_em"))
                if observado_ts is None or observado_ts >= alvo["inicio"] or observado_ts > dt.timestamp():
                    continue
                alvo["n_observacoes"] += 1
                atual = alvo["ultimo"]
                # Uma observação mais antiga nunca desfaz um sinal posterior.
                if atual is None or observado_ts >= atual["timestamp"]:
                    cotacao = item.get("odd_observada")
                    try:
                        preco = float(cotacao) if cotacao is not None else None
                        if preco is not None and (not isfinite(preco) or preco <= 1):
                            preco = None
                    except (TypeError, ValueError, OverflowError):
                        preco = None
                    alvo["ultimo"] = {
                        "timestamp": observado_ts,
                        "odd": preco,
                        "diag": str(item.get("diagnostico") or ""),
                    }

        sem_preco = []
        cotadas = 0
        sem_dados = 0
        for alvo in alvos.values():
            ultima = alvo["ultimo"]
            if ultima is None:
                sem_dados += 1
            elif ultima["odd"] is not None:
                cotadas += 1
            elif ultima["diag"]:
                sem_preco.append(alvo)
            else:
                sem_dados += 1

        sem_preco.sort(key=lambda p: (p["inicio"], p["jogo"]), reverse=True)
        linhas = [
            "🔎 VALIDADE DAS ODDS — AUDITORIA LOCAL",
            f"📚 VALUE histórico nos últimos 7 dias: {len(alvos)} seleção(ões)",
            f"✅ Última observação com preço: {cotadas}",
            f"⚠️ Última observação sem cotação válida: {len(sem_preco)}",
            f"❓ Sem observação conclusiva: {sem_dados}",
            "",
            "⚠️ Registo de VALUE não significa que a odd esteja disponível agora.",
        ]
        for alvo in sem_preco[:8]:
            ultima = alvo["ultimo"]
            hora = self._hora_portugal(ultima["timestamp"])
            linhas.extend([
                "",
                f"⚠️ {alvo['jogo']} | {alvo['mercado']}",
                f"  Odd histórica {alvo['entrada']:.2f} | Última tentativa: {hora}",
                f"  Diagnóstico: {ultima['diag']} — preço NÃO reconfirmado",
            ])
        if len(sem_preco) > 8:
            linhas.append(f"+{len(sem_preco)-8} sinais adicionais")
        linhas.extend([
            "",
            "ℹ️ Erro/mercado ausente numa recolha não prova retirada definitiva na Betano.",
            "ℹ️ 'Última observação com preço' também NÃO prova preço atual.",
            "🔒 Sem novas chamadas OddsPapi, sem alterar snapshots, CLV, V1.2, V1.3 ou Platt.",
        ])
        return "\n".join(linhas)
