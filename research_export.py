"""Exportação segura e apenas de leitura dos snapshots para o Research Lab.

O módulo nunca altera previsões nem lê ficheiros de acessos/clientes. Envia apenas
campos desportivos/modelo necessários à investigação, por HTTP privado autenticado.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any

import requests


SCHEMA_VERSION = 1

# Lista explícita: nada fora destes campos sai do serviço de produção.
CAMPOS_RESEARCH = {
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
    "estado",
    "resultado_binario",
    "golos_casa",
    "golos_fora",
    "liquidada_em",
    "odd_real",
    "ev_real",
    "odds_fonte",
    "odds_event_id",
    "odds_atualizada_em",
    "odds_capturada_em",
    "valor_estado",
    "odd_valor_confirmado",
    "valor_confirmado_em",
    "odd_fecho",
    "odd_fecho_capturada_em",
    "clv_odds",
    "diagnostico_modelo",
    "snapshot_hash",
    "snapshot_hash_versao",
}


def _canonical_json(valor: Any) -> bytes:
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def construir_payload_research(previsoes: list[dict[str, Any]]) -> dict[str, Any]:
    """Cria uma cópia sanitizada e verificável; nunca modifica a origem."""
    registos = []
    for indice, bruto in enumerate(previsoes or [], 1):
        if not isinstance(bruto, dict):
            continue
        item = {"snapshot_index": indice}
        for campo in CAMPOS_RESEARCH:
            if campo in bruto:
                item[campo] = bruto[campo]
        registos.append(item)

    digest = hashlib.sha256(_canonical_json(registos)).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "apostas-bot-production",
        "records": registos,
        "records_count": len(registos),
        "records_sha256": digest,
    }


class ResearchLabClient:
    def __init__(self, session=None):
        self.url = str(os.getenv("LAB_INGEST_URL") or "").rstrip("/")
        self.token = str(os.getenv("LAB_INGEST_TOKEN") or "")
        self.session = session or requests.Session()

    @property
    def configurado(self) -> bool:
        return bool(self.url and self.token)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def exportar(self, previsoes: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.configurado:
            raise RuntimeError("Research Lab não configurado.")
        payload = construir_payload_research(previsoes)
        resposta = self.session.post(
            f"{self.url}/ingest",
            headers=self.headers,
            json=payload,
            timeout=(3, 12),
        )
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict):
            raise RuntimeError("Resposta inválida do Research Lab.")
        return dados

    def status(self) -> dict[str, Any]:
        if not self.configurado:
            raise RuntimeError("Research Lab não configurado.")
        resposta = self.session.get(
            f"{self.url}/status",
            headers=self.headers,
            timeout=(3, 8),
        )
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict):
            raise RuntimeError("Resposta inválida do Research Lab.")
        return dados
