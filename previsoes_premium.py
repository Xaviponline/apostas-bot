"""Registo auditável das previsões do motor premium.

Cada previsão é guardada antes do jogo e os campos do modelo não são alterados
por novas execuções do /analisa. Enquanto uma previsão continuar pendente e o
jogo ainda não tiver começado, uma odd real que faltava pode ser anexada com a
hora exata da captura. Depois do resultado final, a previsão pode ser liquidada
e usada para medir taxa de acerto, Brier Score e, quando aplicável, ROI.
"""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import os
import tempfile
import requests


class RegistoPrevisoes:
    VERSAO = 1
    MODELO_VERSAO = "V1.2"
    DIAGNOSTICO_SNAPSHOT_VERSAO = 1
    INTEGRIDADE_SNAPSHOT_VERSAO = 1
    JANELA_CLV_SEG = 30 * 60
    # Gate comercial pré-registado em 09/10/2026, antes de consultar as odds do dia.
    # Os snapshots 1–206 pertencem ao período anterior e nunca entram neste teste.
    V13_COMERCIAL_START_SNAPSHOT = 207
    V13_COMERCIAL_TARGET = 50
    V13_COMERCIAL_MIN_DIAS = 20
    V13_COMERCIAL_MIN_CLV_AMOSTRAS = 40
    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

    def __init__(self, path=None, session=None):
        if path is None:
            data_dir = Path(os.getenv("DATA_DIR", "/data"))
            path = data_dir / "previsoes_premium.json"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.dados = self._carregar()

    def _carregar(self):
        if not self.path.exists():
            return {"versao": self.VERSAO, "previsoes": []}
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Ficheiro de previsões inválido; não foi sobrescrito.") from exc
        if not isinstance(dados, dict) or not isinstance(dados.get("previsoes"), list):
            raise ValueError("Formato do ficheiro de previsões inválido.")
        dados.setdefault("versao", self.VERSAO)
        return dados

    def _guardar(self):
        conteudo = json.dumps(self.dados, ensure_ascii=False, indent=2, sort_keys=True)
        fd, temp_path = tempfile.mkstemp(
            prefix="previsoes_", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(conteudo)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _data_jogo(jogo):
        ts = jogo.get("timestamp")
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(
                ZoneInfo("Europe/Lisbon")
            ).strftime("%Y-%m-%d")
        return datetime.now(ZoneInfo("Europe/Lisbon")).strftime("%Y-%m-%d")

    @staticmethod
    def _chave(event_id, mercado):
        return f"{event_id}|{mercado}"

    @staticmethod
    def _odd_real_valida(valor):
        try:
            odd = float(valor)
        except (TypeError, ValueError):
            return None
        return odd if odd > 1.0 else None

    @staticmethod
    def _jogo_ainda_nao_comecou(registo, agora_ts):
        ts = registo.get("timestamp_jogo")
        return isinstance(ts, (int, float)) and float(ts) > float(agora_ts)

    @staticmethod
    def _float_diagnostico(valor, casas=6):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return None
        if numero != numero or numero in (float("inf"), float("-inf")):
            return None
        return round(numero, casas)

    @classmethod
    def _payload_integridade(cls, registo):
        """Campos do modelo que devem permanecer imutáveis após o snapshot."""
        campos = (
            "chave",
            "event_id",
            "data_jogo",
            "timestamp_jogo",
            "casa",
            "fora",
            "liga",
            "mercado",
            "modelo_versao",
            "ranking_modelo",
            "confianca_modelo",
            "score_modelo",
            "probabilidade",
            "probabilidade_bruta",
            "qualidade",
            "odd_justa",
            "odd_minima",
            "criada_em",
            "diagnostico_modelo",
        )
        return {campo: registo.get(campo) for campo in campos}

    @classmethod
    def _hash_snapshot(cls, registo):
        payload = json.dumps(
            cls._payload_integridade(registo),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _selar_snapshot(cls, registo):
        """Sela apenas snapshots novos; históricos antigos não são retro-selados."""
        registo["integridade_versao"] = cls.INTEGRIDADE_SNAPSHOT_VERSAO
        registo["snapshot_hash"] = cls._hash_snapshot(registo)

    @classmethod
    def _odd_entrada_valor(cls, registo):
        confirmada = cls._odd_real_valida(registo.get("odd_valor_confirmado"))
        if confirmada is not None:
            return confirmada
        inicial = cls._odd_real_valida(registo.get("odd_real"))
        minima = cls._odd_real_valida(registo.get("odd_minima"))
        if inicial is not None and minima is not None and inicial >= minima:
            return inicial
        return None

    @classmethod
    def _marcar_valor_inicial(cls, registo, agora_iso):
        """Classifica a odd congelada sem alterar a decisão/modelo."""
        odd = cls._odd_real_valida(registo.get("odd_real"))
        minima = cls._odd_real_valida(registo.get("odd_minima"))
        if odd is None:
            registo["valor_estado"] = "sem_odd"
            return
        registo["odd_mercado_atual"] = round(odd, 4)
        registo["odd_mercado_atual_em"] = agora_iso
        if minima is not None and odd >= minima:
            registo["valor_estado"] = "confirmado"
            registo.setdefault("valor_confirmado_em", agora_iso)
            registo.setdefault("odd_valor_confirmado", round(odd, 4))
        else:
            registo["valor_estado"] = "sem_valor"

    def verificar_integridade(self):
        """Verifica hashes dos snapshots selados sem modificar qualquer registo."""
        protegidos = validos = divergentes = legados = 0
        for p in self.dados.get("previsoes", []):
            hash_guardado = str(p.get("snapshot_hash") or "").strip()
            if not hash_guardado:
                legados += 1
                continue
            protegidos += 1
            if hash_guardado == self._hash_snapshot(p):
                validos += 1
            else:
                divergentes += 1
        return {
            "total": len(self.dados.get("previsoes", [])),
            "protegidos": protegidos,
            "validos": validos,
            "divergentes": divergentes,
            "legados_sem_hash": legados,
        }

    def atualizar_estado_mercado(self, selecoes, agora=None, janela_clv_seg=None):
        """Atualiza apenas metadados comerciais com odds atuais pré-jogo.

        A odd inicial congelada, probabilidades e restantes campos do modelo
        nunca são reescritos. Se a consulta ocorrer perto do início, a odd atual
        também é guardada como melhor aproximação disponível à closing line.
        """
        agora_dt = agora or datetime.now(timezone.utc)
        if agora_dt.tzinfo is None:
            agora_dt = agora_dt.replace(tzinfo=timezone.utc)
        agora_ts = agora_dt.timestamp()
        agora_iso = agora_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        janela = int(
            self.JANELA_CLV_SEG if janela_clv_seg is None else janela_clv_seg
        )
        existentes = {
            self._chave(p.get("event_id"), p.get("mercado")): p
            for p in self.dados.get("previsoes", [])
        }
        alterados = confirmados = expirados = fechos = 0

        for s in selecoes or []:
            jogo = s.get("jogo") or {}
            chave = self._chave(jogo.get("id"), s.get("mercado"))
            registo = existentes.get(chave)
            if not registo or registo.get("estado") != "pendente":
                continue
            if not self._jogo_ainda_nao_comecou(registo, agora_ts):
                continue
            odd_atual = self._odd_real_valida(s.get("odd_real"))
            minima = self._odd_real_valida(registo.get("odd_minima"))
            if odd_atual is None or minima is None:
                continue

            estado_anterior = str(registo.get("valor_estado") or "")
            registo["odd_mercado_atual"] = round(odd_atual, 4)
            registo["odd_mercado_atual_em"] = agora_iso
            try:
                prob = float(registo["probabilidade"])
                registo["ev_mercado_atual"] = round((prob * odd_atual) - 1.0, 6)
            except (KeyError, TypeError, ValueError):
                pass

            if odd_atual >= minima:
                if not registo.get("valor_confirmado_em"):
                    registo["valor_confirmado_em"] = agora_iso
                    registo["odd_valor_confirmado"] = round(odd_atual, 4)
                    confirmados += 1
                elif estado_anterior == "expirado":
                    registo["valor_reativado_em"] = agora_iso
                registo["valor_estado"] = "confirmado"
            else:
                if registo.get("valor_confirmado_em"):
                    if estado_anterior != "expirado":
                        expirados += 1
                        registo["valor_expirou_em"] = agora_iso
                    registo["valor_estado"] = "expirado"
                else:
                    registo["valor_estado"] = "sem_valor"

            ts = registo.get("timestamp_jogo")
            if isinstance(ts, (int, float)):
                faltam = float(ts) - agora_ts
                if 0 < faltam <= janela:
                    registo["odd_fecho"] = round(odd_atual, 4)
                    registo["odd_fecho_capturada_em"] = agora_iso
                    entrada = self._odd_entrada_valor(registo)
                    if entrada is not None:
                        registo["clv_odds"] = round((entrada / odd_atual) - 1.0, 6)
                    fechos += 1
            alterados += 1

        if alterados:
            self._guardar()
        return {
            "alterados": alterados,
            "confirmados_novos": confirmados,
            "expirados_novos": expirados,
            "fechos_capturados": fechos,
        }

    def registar_fecho_tardio(self, selecoes, agora=None):
        """Auditoria T-10m: acrescenta uma segunda cotação, sem modificar o CLV oficial.

        A odd inicial, o fecho original e o gate comercial V1.3 ficam intactos.
        Não cria uma entrada VALUE e nunca preenche fechos históricos.
        """
        agora_dt = agora or datetime.now(timezone.utc)
        if agora_dt.tzinfo is None:
            agora_dt = agora_dt.replace(tzinfo=timezone.utc)
        agora_ts = agora_dt.timestamp()
        agora_iso = agora_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        existentes = {
            self._chave(p.get("event_id"), p.get("mercado")): p
            for p in self.dados.get("previsoes", [])
        }
        capturados = 0
        for s in selecoes or []:
            jogo = s.get("jogo") or {}
            p = existentes.get(self._chave(jogo.get("id"), s.get("mercado")))
            if not p or p.get("estado") != "pendente":
                continue
            if self._odd_entrada_valor(p) is None:
                continue
            if self._odd_real_valida(p.get("odd_fecho")) is None:
                continue
            if self._odd_real_valida(p.get("odd_fecho_tardio")) is not None:
                continue
            ts = p.get("timestamp_jogo")
            if not isinstance(ts, (int, float)) or not 0 < float(ts) - agora_ts <= 10 * 60:
                continue
            cotacao = self._odd_real_valida(s.get("odd_real"))
            if cotacao is None:
                continue
            p["odd_fecho_tardio"] = round(cotacao, 4)
            p["odd_fecho_tardio_capturada_em"] = agora_iso
            p["clv_odds_tardio"] = round(self._odd_entrada_valor(p) / cotacao - 1, 6)
            capturados += 1
        if capturados:
            self._guardar()
        return capturados

    def metricas_carteira_valor(self, modelo_versao="V1.2"):
        """Carteira shadow: 1u apenas quando a odd atingiu a odd mínima."""
        elegiveis = []
        for p in self.dados.get("previsoes", []):
            if modelo_versao and str(p.get("modelo_versao") or "") != modelo_versao:
                continue
            entrada = self._odd_entrada_valor(p)
            if entrada is None:
                continue
            elegiveis.append((p, entrada))

        liquidadas = [
            (p, odd) for p, odd in elegiveis if p.get("resultado_binario") in (0, 1)
        ]
        liquidadas.sort(
            key=lambda item: (
                float(item[0].get("timestamp_jogo") or 0),
                str(item[0].get("chave") or ""),
            )
        )
        ganhos = sum(int(p["resultado_binario"]) for p, _ in liquidadas)
        lucro = 0.0
        acumulado = pico = 0.0
        max_drawdown = 0.0
        streak = max_streak = 0
        for p, odd in liquidadas:
            pnl = (odd - 1.0) if int(p["resultado_binario"]) == 1 else -1.0
            lucro += pnl
            acumulado += pnl
            pico = max(pico, acumulado)
            max_drawdown = max(max_drawdown, pico - acumulado)
            if int(p["resultado_binario"]) == 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        total = len(liquidadas)
        return {
            "elegiveis": len(elegiveis),
            "liquidadas": total,
            "pendentes": len(elegiveis) - total,
            "ganhos": ganhos,
            "perdas": total - ganhos,
            "lucro_unidades": lucro,
            "roi": (lucro / total) if total else None,
            "max_drawdown": max_drawdown,
            "max_streak_perdas": max_streak,
        }

    def metricas_clv(self, modelo_versao="V1.2"):
        amostras = []
        for p in self.dados.get("previsoes", []):
            if modelo_versao and str(p.get("modelo_versao") or "") != modelo_versao:
                continue
            entrada = self._odd_entrada_valor(p)
            fecho = self._odd_real_valida(p.get("odd_fecho"))
            if entrada is None or fecho is None:
                continue
            amostras.append((entrada / fecho) - 1.0)
        if not amostras:
            return {"total": 0, "media": None, "positivos": 0}
        return {
            "total": len(amostras),
            "media": sum(amostras) / len(amostras),
            "positivos": sum(1 for valor in amostras if valor > 0),
        }

    def metricas_clv_tardio(self, modelo_versao="V1.2"):
        """Métrica exploratória separada: não altera o CLV pré-registado da V1.3."""
        amostras = []
        for p in self.dados.get("previsoes", []):
            if modelo_versao and str(p.get("modelo_versao") or "") != modelo_versao:
                continue
            entrada = self._odd_entrada_valor(p)
            fecho = self._odd_real_valida(p.get("odd_fecho_tardio"))
            if entrada is not None and fecho is not None:
                amostras.append(entrada / fecho - 1)
        return {
            "total": len(amostras),
            "media": sum(amostras) / len(amostras) if amostras else None,
            "positivos": sum(v > 0 for v in amostras),
        }

    def entradas_carteira_valor(self, modelo_versao="V1.2"):
        """Detalhe auditável e apenas de leitura das mesmas entradas da carteira.

        Não consulta odds, não reescreve snapshots e não infere fechos em falta.
        """
        entradas = []
        for p in self.dados.get("previsoes", []):
            if modelo_versao and str(p.get("modelo_versao") or "") != modelo_versao:
                continue
            odd_entrada = self._odd_entrada_valor(p)
            if odd_entrada is None:
                continue

            odd_fecho = self._odd_real_valida(p.get("odd_fecho"))
            resultado = p.get("resultado_binario")
            liquidada = resultado in (0, 1)
            pnl = (
                (odd_entrada - 1.0) if int(resultado) == 1 else -1.0
            ) if liquidada else None

            entradas.append({
                "chave": str(p.get("chave") or ""),
                "data_jogo": str(p.get("data_jogo") or ""),
                "timestamp_jogo": p.get("timestamp_jogo"),
                "casa": str(p.get("casa") or "?"),
                "fora": str(p.get("fora") or "?"),
                "mercado": str(p.get("mercado") or "?"),
                "ranking_modelo": p.get("ranking_modelo"),
                "odd_minima": self._odd_real_valida(p.get("odd_minima")),
                "odd_entrada": odd_entrada,
                "odd_fecho": odd_fecho,
                "clv": (odd_entrada / odd_fecho - 1.0) if odd_fecho else None,
                "resultado_binario": resultado if liquidada else None,
                "lucro_unidades": pnl,
                "fecho_capturado_em": p.get("odd_fecho_capturada_em"),
                "odd_fecho_tardio": self._odd_real_valida(p.get("odd_fecho_tardio")),
                "fecho_tardio_capturado_em": p.get("odd_fecho_tardio_capturada_em"),
            })

        entradas.sort(
            key=lambda p: (
                float(p["timestamp_jogo"] or 0),
                p["chave"],
            ),
            reverse=True,
        )
        return entradas

    def metricas_v13_comercial(self):
        """Gate prospetivo Top5 + VALUE, pré-registado e apenas de leitura.

        Coorte fixa: primeiras 50 entradas V1.2 com ranking #1–5, a partir do
        snapshot #207, cuja primeira odd confirmada atingiu a odd mínima.
        Não há substituição de entradas, extensão oportunista ou promoção automática.
        """
        candidatos = []
        top5_monitorizadas = 0
        previsoes = self.dados.get("previsoes", [])
        for indice, p in enumerate(previsoes, 1):
            if indice < self.V13_COMERCIAL_START_SNAPSHOT:
                continue
            if str(p.get("modelo_versao") or "") != "V1.2":
                continue
            try:
                ranking = int(p.get("ranking_modelo"))
            except (TypeError, ValueError):
                continue
            if ranking < 1 or ranking > 5:
                continue
            top5_monitorizadas += 1

            entrada = self._odd_entrada_valor(p)
            if entrada is None:
                continue
            confirmado_em = str(
                p.get("valor_confirmado_em")
                or p.get("odds_capturada_em")
                or p.get("criada_em")
                or ""
            )
            fecho = self._odd_real_valida(p.get("odd_fecho"))
            resultado = p.get("resultado_binario")
            liquidada = resultado in (0, 1)
            pnl = (
                (entrada - 1.0) if int(resultado) == 1 else -1.0
            ) if liquidada else None
            candidatos.append(
                {
                    "snapshot": indice,
                    "confirmado_em": confirmado_em,
                    "data_jogo": str(p.get("data_jogo") or ""),
                    "casa": str(p.get("casa") or "?"),
                    "fora": str(p.get("fora") or "?"),
                    "mercado": str(p.get("mercado") or "?"),
                    "ranking_modelo": ranking,
                    "odd_entrada": entrada,
                    "odd_fecho": fecho,
                    "clv": (entrada / fecho - 1.0) if fecho else None,
                    "resultado_binario": resultado if liquidada else None,
                    "lucro_unidades": pnl,
                }
            )

        # A entrada comercial nasce quando o valor é confirmado. A hora é
        # imutável; snapshot serve de desempate auditável.
        candidatos.sort(
            key=lambda x: (
                x["confirmado_em"] or "9999-12-31T23:59:59Z",
                x["snapshot"],
            )
        )
        coorte = candidatos[: self.V13_COMERCIAL_TARGET]
        liquidadas = [x for x in coorte if x["resultado_binario"] in (0, 1)]
        ganhos = sum(int(x["resultado_binario"]) for x in liquidadas)
        lucro = sum(float(x["lucro_unidades"]) for x in liquidadas)
        roi = (lucro / len(liquidadas)) if liquidadas else None

        acumulado = pico = 0.0
        max_drawdown = 0.0
        streak = max_streak = 0
        for x in liquidadas:
            pnl = float(x["lucro_unidades"])
            acumulado += pnl
            pico = max(pico, acumulado)
            max_drawdown = max(max_drawdown, pico - acumulado)
            if int(x["resultado_binario"]) == 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        clvs = [float(x["clv"]) for x in coorte if x["clv"] is not None]
        clv_media = (sum(clvs) / len(clvs)) if clvs else None
        dias = len({x["data_jogo"] for x in coorte if x["data_jogo"]})

        coorte_fechada = len(coorte) >= self.V13_COMERCIAL_TARGET
        todas_liquidadas = (
            coorte_fechada and len(liquidadas) == self.V13_COMERCIAL_TARGET
        )
        regras = {
            "coorte_50": coorte_fechada,
            "dias_20": dias >= self.V13_COMERCIAL_MIN_DIAS,
            "liquidacao_completa": todas_liquidadas,
            "roi_positivo": bool(todas_liquidadas and roi is not None and roi > 0),
            "clv_cobertura": len(clvs) >= self.V13_COMERCIAL_MIN_CLV_AMOSTRAS,
            "clv_positivo": bool(
                len(clvs) >= self.V13_COMERCIAL_MIN_CLV_AMOSTRAS
                and clv_media is not None
                and clv_media > 0
            ),
        }
        if not coorte_fechada:
            estado = "RECOLHA"
        elif not todas_liquidadas:
            estado = "AGUARDA_LIQUIDACAO"
        elif all(regras.values()):
            estado = "PASSOU"
        else:
            estado = "NAO_PASSOU"

        return {
            "inicio_snapshot": self.V13_COMERCIAL_START_SNAPSHOT,
            "alvo": self.V13_COMERCIAL_TARGET,
            "top5_monitorizadas": top5_monitorizadas,
            "elegiveis_total": len(candidatos),
            "coorte": coorte,
            "coorte_tamanho": len(coorte),
            "liquidadas": len(liquidadas),
            "pendentes": len(coorte) - len(liquidadas),
            "ganhos": ganhos,
            "perdas": len(liquidadas) - ganhos,
            "lucro_unidades": lucro,
            "roi": roi,
            "max_drawdown": max_drawdown,
            "max_streak_perdas": max_streak,
            "dias": dias,
            "clv_amostras": len(clvs),
            "clv_media": clv_media,
            "clv_positivos": sum(1 for x in clvs if x > 0),
            "min_dias": self.V13_COMERCIAL_MIN_DIAS,
            "min_clv_amostras": self.V13_COMERCIAL_MIN_CLV_AMOSTRAS,
            "regras": regras,
            "estado": estado,
        }

    @classmethod
    def _snapshot_diagnostico(cls, selecao):
        """Congela inputs já calculados pelo modelo para auditoria futura.

        Esta estrutura é criada apenas em novas previsões. Snapshots existentes
        nunca são enriquecidos retroativamente.
        """
        diagnostico = {"versao": cls.DIAGNOSTICO_SNAPSHOT_VERSAO}

        liga_codigo = str(selecao.get("liga_codigo") or "").strip()
        if liga_codigo:
            diagnostico["liga_codigo"] = liga_codigo

        campos_float = (
            "limite_mercado",
            "margem_limite",
            "lambda_casa",
            "lambda_fora",
            "ppg_casa",
            "ppg_fora",
            "media_liga_casa",
            "media_liga_fora",
            "media_modelo_casa_gf",
            "media_modelo_casa_ga",
            "media_modelo_fora_gf",
            "media_modelo_fora_ga",
        )
        for campo in campos_float:
            valor = cls._float_diagnostico(selecao.get(campo))
            if valor is not None:
                diagnostico[campo] = valor

        for campo in (
            "amostra_casa",
            "amostra_fora",
            "amostra_casa_local",
            "amostra_fora_local",
            "amostra_liga",
        ):
            try:
                valor = int(selecao.get(campo))
            except (TypeError, ValueError):
                continue
            if valor >= 0:
                diagnostico[campo] = valor

        probabilidades = {}
        bruto = selecao.get("probabilidades")
        if isinstance(bruto, dict):
            for mercado, valor in bruto.items():
                numero = cls._float_diagnostico(valor)
                if numero is None or not (0.0 < numero < 1.0):
                    continue
                probabilidades[str(mercado)] = numero
        if probabilidades:
            diagnostico["probabilidades_brutas_mercados"] = probabilidades

        # Só grava o bloco quando há telemetria além do número de versão.
        return diagnostico if len(diagnostico) > 1 else None

    def _anexar_odd_se_segura(self, registo, selecao, agora_iso, agora_ts):
        """Anexa apenas a primeira odd real, sem alterar qualquer campo do modelo."""
        if registo.get("estado") != "pendente":
            return False
        if self._odd_real_valida(registo.get("odd_real")) is not None:
            return False
        if not self._jogo_ainda_nao_comecou(registo, agora_ts):
            return False

        odd_real = self._odd_real_valida(selecao.get("odd_real"))
        if odd_real is None:
            return False
        try:
            prob = float(registo["probabilidade"])
        except (KeyError, TypeError, ValueError):
            return False

        registo.update(
            {
                "odd_real": round(odd_real, 4),
                "ev_real": round((prob * odd_real) - 1.0, 6),
                "odds_fonte": str(selecao.get("odds_fonte") or ""),
                "odds_event_id": str(selecao.get("odds_event_id") or ""),
                "odds_atualizada_em": str(selecao.get("odds_atualizada_em") or ""),
                "odds_capturada_em": agora_iso,
            }
        )
        self._marcar_valor_inicial(registo, agora_iso)
        return True

    def registar(self, selecoes):
        """Guarda previsões novas e completa odds ausentes apenas antes do jogo."""
        existentes = {
            self._chave(p.get("event_id"), p.get("mercado")): p
            for p in self.dados["previsoes"]
        }
        agora_dt = datetime.now(timezone.utc)
        agora_ts = agora_dt.timestamp()
        agora = agora_dt.isoformat().replace("+00:00", "Z")
        adicionadas = 0
        odds_anexadas = 0

        for s in selecoes or []:
            jogo = s.get("jogo") or {}
            event_id = jogo.get("id")
            mercado = s.get("mercado")
            if event_id is None or not mercado:
                continue
            chave = self._chave(event_id, mercado)
            if chave in existentes:
                if self._anexar_odd_se_segura(
                    existentes[chave], s, agora, agora_ts
                ):
                    odds_anexadas += 1
                continue
            try:
                prob = float(s["probabilidade"])
                prob_bruta = float(s.get("probabilidade_bruta", prob))
                qualidade = int(s["qualidade"])
                odd_justa = float(s["odd_justa"])
                odd_minima = float(s["odd_minima"])
            except (KeyError, TypeError, ValueError):
                continue

            try:
                ranking_modelo = int(s.get("ranking_modelo"))
                if ranking_modelo <= 0:
                    ranking_modelo = None
            except (TypeError, ValueError):
                ranking_modelo = None

            confianca_modelo = str(s.get("confianca") or "").strip() or None
            try:
                score_modelo = float(s.get("score"))
            except (TypeError, ValueError):
                score_modelo = None

            registo = {
                "chave": chave,
                "event_id": int(event_id),
                "data_jogo": self._data_jogo(jogo),
                "timestamp_jogo": jogo.get("timestamp"),
                "casa": str(jogo.get("casa") or ""),
                "fora": str(jogo.get("fora") or ""),
                "liga": str(jogo.get("liga") or ""),
                "mercado": str(mercado),
                "modelo_versao": self.MODELO_VERSAO,
                "ranking_modelo": ranking_modelo,
                "confianca_modelo": confianca_modelo,
                "score_modelo": round(score_modelo, 6) if score_modelo is not None else None,
                "probabilidade": round(prob, 6),
                "probabilidade_bruta": round(prob_bruta, 6),
                "qualidade": qualidade,
                "odd_justa": round(odd_justa, 4),
                "odd_minima": round(odd_minima, 4),
                "criada_em": agora,
                "estado": "pendente",
                "resultado_binario": None,
                "golos_casa": None,
                "golos_fora": None,
                "liquidada_em": None,
            }

            diagnostico_modelo = self._snapshot_diagnostico(s)
            if diagnostico_modelo is not None:
                registo["diagnostico_modelo"] = diagnostico_modelo

            odd_real = self._odd_real_valida(s.get("odd_real"))
            if odd_real is not None:
                registo.update(
                    {
                        "odd_real": round(odd_real, 4),
                        "ev_real": round((prob * odd_real) - 1.0, 6),
                        "odds_fonte": str(s.get("odds_fonte") or ""),
                        "odds_event_id": str(s.get("odds_event_id") or ""),
                        "odds_atualizada_em": str(s.get("odds_atualizada_em") or ""),
                        "odds_capturada_em": agora,
                    }
                )

            self._marcar_valor_inicial(registo, agora)
            self._selar_snapshot(registo)
            self.dados["previsoes"].append(registo)
            existentes[chave] = registo
            adicionadas += 1

        if adicionadas or odds_anexadas:
            self._guardar()
        return adicionadas

    @staticmethod
    def _resultado_mercado(mercado, gc, gf):
        if mercado == "Vitória Casa":
            return int(gc > gf)
        if mercado == "Vitória Fora":
            return int(gf > gc)
        if mercado == "Ambas Marcam":
            return int(gc > 0 and gf > 0)
        if mercado == "Over 1.5 Golos":
            return int(gc + gf >= 2)
        if mercado == "Over 2.5 Golos":
            return int(gc + gf >= 3)
        if mercado == "Under 2.5 Golos":
            return int(gc + gf <= 2)
        if mercado == "Under 3.5 Golos":
            return int(gc + gf <= 3)
        if mercado == "1X (Casa ou Empate)":
            return int(gc >= gf)
        if mercado == "X2 (Empate ou Fora)":
            return int(gf >= gc)
        return None

    @staticmethod
    def _score(valor):
        try:
            return int(str(valor).strip())
        except (TypeError, ValueError):
            return None

    def _resultados_espn(self, data_iso, liga_codigo="all"):
        """Obtém resultados finais ESPN por rota global ou competição específica."""
        compacta = str(data_iso).replace("-", "")
        liga_codigo = str(liga_codigo or "all").strip() or "all"
        r = self.session.get(
            f"{self.ESPN_BASE}/{liga_codigo}/scoreboard",
            params={"dates": compacta},
            timeout=(5, 25),
        )
        r.raise_for_status()
        dados = r.json()
        eventos = dados.get("events") if isinstance(dados, dict) else None
        if not isinstance(eventos, list):
            raise ValueError("Resultados ESPN inválidos.")

        saida = {}
        for evento in eventos:
            try:
                status = ((evento.get("status") or {}).get("type") or {})
                if str(status.get("state") or "").lower() != "post" and not status.get("completed"):
                    continue
                competicoes = evento.get("competitions") or []
                if not competicoes:
                    continue
                concorrentes = (competicoes[0] or {}).get("competitors") or []
                casa = next((c for c in concorrentes if c.get("homeAway") == "home"), None)
                fora = next((c for c in concorrentes if c.get("homeAway") == "away"), None)
                if casa is None or fora is None:
                    continue
                gc, gf = self._score(casa.get("score")), self._score(fora.get("score"))
                if gc is None or gf is None:
                    continue
                saida[int(evento["id"])] = (gc, gf)
            except (KeyError, TypeError, ValueError):
                continue
        return saida

    def atualizar_pendentes(self, buscador=None):
        """Liquida previsões pendentes. Falhas de rede não alteram o histórico."""
        pendentes = [p for p in self.dados["previsoes"] if p.get("estado") == "pendente"]
        if not pendentes:
            return 0

        por_data = {}
        for p in pendentes:
            por_data.setdefault(p.get("data_jogo"), []).append(p)

        liquidadas = 0
        agora = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for data_iso, previsoes in por_data.items():
            if not data_iso:
                continue
            try:
                resultados = self._resultados_espn(data_iso)
            except (requests.RequestException, RuntimeError, ValueError, TypeError):
                continue
            for p in previsoes:
                resultado = resultados.get(p.get("event_id"))
                if resultado is None:
                    continue
                gc, gf = resultado
                y = self._resultado_mercado(p.get("mercado"), gc, gf)
                if y is None:
                    continue
                p["estado"] = "ganhou" if y == 1 else "perdeu"
                p["resultado_binario"] = y
                p["golos_casa"] = gc
                p["golos_fora"] = gf
                p["liquidada_em"] = agora
                liquidadas += 1
        if liquidadas:
            self._guardar()
        return liquidadas

    def estatisticas(self):
        todos = self.dados["previsoes"]
        liquidados = [p for p in todos if p.get("resultado_binario") in (0, 1)]
        pendentes = sum(1 for p in todos if p.get("estado") == "pendente")
        ganhos = sum(int(p["resultado_binario"]) for p in liquidados)
        perdas = len(liquidados) - ganhos
        hit_rate = (ganhos / len(liquidados)) if liquidados else None
        if liquidados:
            brier = sum(
                (float(p["probabilidade"]) - int(p["resultado_binario"])) ** 2
                for p in liquidados
            ) / len(liquidados)
        else:
            brier = None

        com_odds = []
        for p in liquidados:
            odd = self._odd_real_valida(p.get("odd_real"))
            if odd is not None:
                com_odds.append((p, odd))
        lucro_unidades = sum(
            (odd - 1.0) if int(p["resultado_binario"]) == 1 else -1.0
            for p, odd in com_odds
        )
        roi = (lucro_unidades / len(com_odds)) if com_odds else None
        ev_medio = (
            sum((float(p["probabilidade"]) * odd) - 1.0 for p, odd in com_odds)
            / len(com_odds)
            if com_odds
            else None
        )
        return {
            "total": len(todos),
            "pendentes": pendentes,
            "liquidadas": len(liquidados),
            "ganhos": ganhos,
            "perdas": perdas,
            "hit_rate": hit_rate,
            "brier": brier,
            "odds_liquidadas": len(com_odds),
            "lucro_unidades": lucro_unidades,
            "roi": roi,
            "ev_medio": ev_medio,
        }

    def relatorio(self):
        s = self.estatisticas()
        linhas = [
            "📊 PERFORMANCE DO MODELO — AUDITORIA",
            "",
            f"Previsões registadas: {s['total']}",
            f"Liquidadas: {s['liquidadas']} | Pendentes: {s['pendentes']}",
        ]

        pendentes_detalhe = [
            p for p in self.dados["previsoes"] if p.get("estado") == "pendente"
        ]
        if pendentes_detalhe:
            linhas.extend(["", "⏳ PREVISÕES PENDENTES"])
            for p in sorted(
                pendentes_detalhe,
                key=lambda item: (
                    str(item.get("data_jogo") or ""),
                    float(item.get("timestamp_jogo") or 0),
                ),
            ):
                ts = p.get("timestamp_jogo")
                hora = "--:--"
                if isinstance(ts, (int, float)):
                    hora = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(
                        ZoneInfo("Europe/Lisbon")
                    ).strftime("%H:%M")
                odd = self._odd_real_valida(p.get("odd_real"))
                sufixo_odd = f" | Odd {odd:.2f}" if odd is not None else ""
                linhas.append(
                    f"• {p.get('data_jogo') or '--'} {hora} — "
                    f"{p.get('casa') or '?'} vs {p.get('fora') or '?'} | "
                    f"{p.get('mercado') or 'Mercado desconhecido'}{sufixo_odd}"
                )

        if not s["liquidadas"]:
            linhas.extend(
                [
                    "",
                    "Ainda não há previsões liquidadas suficientes para avaliar o modelo.",
                    "As previsões ficam guardadas antes do jogo e os campos do modelo não são reescritos pelo /analisa.",
                ]
            )
            return "\n".join(linhas)

        linhas.extend(
            [
                "",
                f"✅ Acertos: {s['ganhos']} | ❌ Falhas: {s['perdas']}",
                f"🎯 Taxa de acerto: {s['hit_rate']*100:.1f}%",
                f"📐 Brier Score: {s['brier']:.4f} (menor é melhor)",
            ]
        )
        if s["odds_liquidadas"]:
            sinal_lucro = "+" if s["lucro_unidades"] >= 0 else ""
            sinal_roi = "+" if s["roi"] >= 0 else ""
            sinal_ev = "+" if s["ev_medio"] >= 0 else ""
            linhas.extend(
                [
                    "",
                    "💶 AUDITORIA DE ODDS REAIS",
                    f"Previsões liquidadas com odd congelada: {s['odds_liquidadas']}",
                    f"Resultado a 1u por previsão: {sinal_lucro}{s['lucro_unidades']:.2f}u",
                    f"ROI observado: {sinal_roi}{s['roi']*100:.1f}%",
                    f"EV médio no snapshot: {sinal_ev}{s['ev_medio']*100:.1f}%",
                    "As odds servem apenas para auditoria e não alteram retroativamente as seleções da V1.",
                ]
            )
        else:
            linhas.extend(
                [
                    "",
                    "ROI ainda não é apresentado porque não há previsões liquidadas com odds reais capturadas antes do início do jogo.",
                    "As previsões antigas sem snapshot de odd continuam válidas para hit rate/Brier, mas não entram no ROI.",
                ]
            )
        return "\n".join(linhas)