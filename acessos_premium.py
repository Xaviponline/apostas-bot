"""Controlo persistente de acessos Premium.

A autorização comercial é separada do motor de previsões. Este módulo nunca
altera snapshots, fórmulas ou resultados do modelo.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import tempfile


class GestorAcessosPremium:
    VERSAO = 1

    def __init__(self, path=None):
        if path is None:
            data_dir = Path(os.getenv("DATA_DIR", "/data"))
            path = data_dir / "acessos_premium.json"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dados = self._carregar()

    def _carregar(self):
        if not self.path.exists():
            return {"versao": self.VERSAO, "clientes": {}}
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Ficheiro de acessos Premium inválido.") from exc
        if not isinstance(dados, dict) or not isinstance(dados.get("clientes"), dict):
            raise ValueError("Formato do ficheiro de acessos Premium inválido.")
        dados.setdefault("versao", self.VERSAO)
        return dados

    def _guardar(self):
        conteudo = json.dumps(self.dados, ensure_ascii=False, indent=2, sort_keys=True)
        fd, temp_path = tempfile.mkstemp(
            prefix="acessos_", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as ficheiro:
                ficheiro.write(conteudo)
                ficheiro.flush()
                os.fsync(ficheiro.fileno())
            os.replace(temp_path, self.path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _agora(agora=None):
        if agora is None:
            return datetime.now(timezone.utc)
        if agora.tzinfo is None:
            return agora.replace(tzinfo=timezone.utc)
        return agora.astimezone(timezone.utc)

    @staticmethod
    def _parse_iso(valor):
        if not valor:
            return None
        try:
            return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        except (TypeError, ValueError):
            return None

    def adicionar(self, user_id, dias, agora=None):
        user_id = int(user_id)
        dias = int(dias)
        if user_id <= 0:
            raise ValueError("USER_ID inválido.")
        if dias < 1 or dias > 3650:
            raise ValueError("Os dias devem estar entre 1 e 3650.")

        agora_dt = self._agora(agora)
        chave = str(user_id)
        atual = self.dados["clientes"].get(chave) or {}
        validade_atual = self._parse_iso(atual.get("validade_ate"))
        base = validade_atual if validade_atual and validade_atual > agora_dt else agora_dt
        validade = base + timedelta(days=dias)

        registo = {
            "user_id": user_id,
            "ativo": True,
            "criado_em": atual.get("criado_em")
            or agora_dt.isoformat().replace("+00:00", "Z"),
            "atualizado_em": agora_dt.isoformat().replace("+00:00", "Z"),
            "validade_ate": validade.isoformat().replace("+00:00", "Z"),
        }
        self.dados["clientes"][chave] = registo
        self._guardar()
        return dict(registo)

    def remover(self, user_id, agora=None):
        chave = str(int(user_id))
        registo = self.dados["clientes"].get(chave)
        if not isinstance(registo, dict):
            return False
        agora_dt = self._agora(agora)
        registo["ativo"] = False
        registo["atualizado_em"] = agora_dt.isoformat().replace("+00:00", "Z")
        self._guardar()
        return True

    def estado(self, user_id, agora=None):
        try:
            chave = str(int(user_id))
        except (TypeError, ValueError):
            return {"existe": False, "ativo": False, "user_id": None, "validade_ate": None}

        registo = self.dados["clientes"].get(chave)
        if not isinstance(registo, dict):
            return {
                "existe": False,
                "ativo": False,
                "user_id": int(user_id),
                "validade_ate": None,
            }

        agora_dt = self._agora(agora)
        validade = self._parse_iso(registo.get("validade_ate"))
        ativo = bool(registo.get("ativo")) and validade is not None and validade > agora_dt
        segundos = max((validade - agora_dt).total_seconds(), 0.0) if validade else 0.0
        return {
            "existe": True,
            "ativo": ativo,
            "user_id": int(user_id),
            "validade_ate": validade,
            "segundos_restantes": segundos,
        }

    def listar(self, agora=None):
        saida = []
        for chave in sorted(self.dados["clientes"], key=lambda valor: int(valor)):
            try:
                estado = self.estado(int(chave), agora=agora)
            except (TypeError, ValueError):
                continue
            saida.append(estado)
        return saida
