"""Testes de offsite S3 e monitor independente: sem rede e sem credenciais reais."""
import base64
import copy
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from botocore.exceptions import ClientError
from cryptography.exceptions import InvalidTag

from backups_locais import CopiasSeguranca
from backup_externo import BackupExterno, MAGIC
from vigilancia_externa import VigilanciaExterna
from main_competicoes import BotPremiumDiarioCompeticoes


TZ = ZoneInfo("Europe/Lisbon")
SEGREDO_CLIENTE = "dado-pessoal-privado-99999"


def ambiente_s3():
    return {
        "BACKUP_S3_ENDPOINT_URL": "https://s3.exemplo.com",
        "BACKUP_S3_REGION": "auto",
        "BACKUP_S3_BUCKET": "backups-bot-test",
        "BACKUP_S3_ACCESS_KEY_ID": "key-de-testes",
        "BACKUP_S3_SECRET_ACCESS_KEY": "chave-ficticia-sem-permissoes",
        "BACKUP_AES256_KEY_B64": base64.b64encode(bytes(range(32))).decode(),
    }


def dados_local(base, data=None):
    data = data or datetime(2030, 3, 20, 9, 20, tzinfo=TZ)
    (base / "previsoes_premium.json").write_text(
        json.dumps({"previsoes": [{"proprietario": SEGREDO_CLIENTE}]}),
        encoding="utf-8",
    )
    (base / "acessos_premium.json").write_text(
        json.dumps({"clientes": {"99": {"ativo": True}}}),
        encoding="utf-8",
    )
    backups = CopiasSeguranca(base)
    assert backups.executar_se_devido(data)
    return backups


class FakeS3:
    def __init__(self):
        self.data = {}
        self.calls = []

    def head_object(self, Bucket, Key):
        self.calls.append(("head", Bucket, Key))
        key = (Bucket, Key)
        if key not in self.data:
            raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")
        body, meta = self.data[key]
        return {"ContentLength": len(body), "Metadata": meta}

    def put_object(self, Bucket, Key, Body, Metadata, **kwargs):
        self.calls.append(("put", Bucket, Key))
        self.data[(Bucket, Key)] = (bytes(Body), dict(Metadata))

    def get_object(self, Bucket, Key):
        self.calls.append(("get", Bucket, Key))
        b, metadata = self.data[(Bucket, Key)]
        return {"Body": BytesIO(b), "Metadata": dict(metadata)}


class OffsiteTests(unittest.TestCase):
    def test_env_nao_configurado_nao_faz_rede(self):
        with tempfile.TemporaryDirectory() as td:
            bk = dados_local(Path(td))
            s3 = FakeS3()
            e = BackupExterno(bk, env={}, client=s3)
            self.assertEqual(e.estado_config(), "desativado")
            self.assertFalse(e.executar_se_devido(datetime(2030, 3, 20, 10, 0, tzinfo=TZ)))
            self.assertEqual(s3.calls, [])
            self.assertIn("desativado", e.relatorio())

    def test_env_incompleto_nao_faz_rede(self):
        with tempfile.TemporaryDirectory() as td:
            bk = dados_local(Path(td))
            s3 = FakeS3()
            e = BackupExterno(bk, env={"BACKUP_S3_BUCKET": "x"}, client=s3)
            self.assertEqual(e.estado_config(), "incompleto")
            self.assertFalse(e.executar_se_devido(datetime(2030, 3, 20, 10, 0, tzinfo=TZ)))
            self.assertEqual(s3.calls, [])

    def test_upload_cifrado_verifica_download_e_restauro(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            bk = dados_local(base)
            antes = (base / "previsoes_premium.json").read_bytes()
            s3 = FakeS3()
            e = BackupExterno(bk, env=ambiente_s3(), client=s3)
            t = datetime(2030, 3, 20, 10, 0, tzinfo=TZ)
            self.assertTrue(e.executar_se_devido(t))
            self.assertFalse(e.executar_se_devido(t + timedelta(minutes=5)))
            self.assertEqual([v[0] for v in s3.calls], ["head", "put", "get"])
            ciphertext, metadata = next(iter(s3.data.values()))
            self.assertTrue(ciphertext.startswith(MAGIC))
            self.assertNotIn(SEGREDO_CLIENTE.encode(), ciphertext)
            self.assertEqual(metadata["data"], "2030-03-20")
            self.assertEqual((base / "previsoes_premium.json").read_bytes(), antes)
            self.assertIn("✅ Upload", e.relatorio(t))
            chave = bytes(range(32))
            m = BackupExterno.validar_cifrado(ciphertext, chave, "2030-03-20")
            self.assertIn("previsoes_premium.json", m["ficheiros"])
            self.assertNotIn("chave-ficticia", e.relatorio(t))

    def test_blob_cifrado_adulterado_ou_chave_errada_falha(self):
        with tempfile.TemporaryDirectory() as td:
            bk = dados_local(Path(td))
            s3 = FakeS3()
            e = BackupExterno(bk, env=ambiente_s3(), client=s3)
            e.executar_se_devido(datetime(2030, 3, 20, 11, 0, tzinfo=TZ))
            c, _ = next(iter(s3.data.values()))
            with self.assertRaises(InvalidTag):
                BackupExterno.validar_cifrado(c, bytes([7])*32, "2030-03-20")
            alterado = c[:-1] + bytes([c[-1] ^ 1])
            with self.assertRaises(InvalidTag):
                BackupExterno.validar_cifrado(alterado, bytes(range(32)), "2030-03-20")

    def test_nao_confirma_upload_adulterado(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            bk = dados_local(base)
            s3 = FakeS3()
            original = s3.put_object
            def corrupcao(*args, **kwargs):
                body = kwargs["Body"]
                kwargs["Body"] = body[:-1] + bytes([body[-1] ^ 1])
                return original(*args, **kwargs)
            s3.put_object = corrupcao
            e = BackupExterno(bk, env=ambiente_s3(), client=s3)
            with self.assertRaises(RuntimeError):
                e.executar_se_devido(datetime(2030, 3, 20, 10, 0, tzinfo=TZ))
            self.assertFalse(e.state.exists())
            self.assertTrue(bk.validar(bk.destino / "2030-03-20"))

    def test_remoto_ja_existente_nao_substitui(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            bk = dados_local(base)
            s3 = FakeS3()
            e = BackupExterno(bk, env=ambiente_s3(), client=s3)
            dt = datetime(2030, 3, 20, 10, 0, tzinfo=TZ)
            e.executar_se_devido(dt)
            original = copy.deepcopy(s3.data)
            e.state.unlink()
            self.assertTrue(e.executar_se_devido(dt))
            self.assertEqual(s3.data, original)
            self.assertEqual([q[0] for q in s3.calls].count("put"), 1)

    def test_sem_upload_durante_janela_clv(self):
        with tempfile.TemporaryDirectory() as td:
            bk = dados_local(Path(td))
            s3 = FakeS3()
            e = BackupExterno(bk, env=ambiente_s3(), client=s3)
            self.assertFalse(e.executar_se_devido(datetime(2030, 3, 20, 9, 25, tzinfo=TZ)))
            self.assertFalse(e.executar_se_devido(datetime(2030, 3, 20, 19, 15, tzinfo=TZ)))
            self.assertEqual(s3.calls, [])

    def test_endpoint_http_e_chave_invalida_falham_fechado(self):
        with tempfile.TemporaryDirectory() as td:
            bk = dados_local(Path(td))
            dt = datetime(2030, 3, 20, 10, 0, tzinfo=TZ)
            for variavel, invalido in [("BACKUP_S3_ENDPOINT_URL","http://inseguro"),("BACKUP_AES256_KEY_B64","xxx")]:
                env = ambiente_s3()
                env[variavel] = invalido
                s3 = FakeS3()
                e = BackupExterno(bk, env=env, client=s3)
                with self.assertRaises(ValueError):
                    e.executar_se_devido(dt)
                self.assertEqual(s3.calls, [])


class MonitorExternoTests(unittest.TestCase):
    URL = "https://hc-ping.com/12345678-1234-4234-9234-123456789abc"

    def test_inativo_sem_configuracao(self):
        sessao = Mock()
        m = VigilanciaExterna(env={}, session=sessao)
        self.assertFalse(m.ping())
        sessao.get.assert_not_called()

    def test_ping_cinco_minutos_e_estado_sem_token(self):
        with tempfile.TemporaryDirectory() as td:
            s = Mock()
            s.get.return_value.status_code = 200
            agora = [1.0]
            m = VigilanciaExterna(Path(td)/"estado.json", env={"HEALTHCHECKS_PING_URL": self.URL},
                                  session=s, tempo=lambda: agora[0])
            self.assertTrue(m.ping())
            self.assertFalse(m.ping())
            agora[0] = 300.1
            self.assertFalse(m.ping())
            agora[0] = 301.5
            self.assertTrue(m.ping())
            self.assertEqual(s.get.call_count, 2)
            self.assertIn("Ultimo ping HTTP 200", m.relatorio())
            self.assertNotIn(self.URL, m.relatorio())
            self.assertNotIn(self.URL, (Path(td)/"estado.json").read_text())

    def test_nao_aceita_url_falsa_nem_redirecionamentos(self):
        for bad in ("http://hc-ping.com/12345678-1234-4234-9234-123456789abc",
                    "https://outro.com/12345678-1234-4234-9234-123456789abc",
                    "https://hc-ping.com@evil.com/12345678-1234-4234-9234-123456789abc"):
            m = VigilanciaExterna(env={"HEALTHCHECKS_PING_URL": bad}, session=Mock())
            with self.assertRaises(ValueError):
                m.ping()
            m.session.get.assert_not_called()

    def test_falha_request_nao_expõe_token(self):
        import requests
        s = Mock()
        s.get.side_effect = requests.Timeout("GET " + self.URL)
        m = VigilanciaExterna(env={"HEALTHCHECKS_PING_URL": self.URL}, session=s)
        with self.assertRaises(RuntimeError) as ex:
            m.ping()
        self.assertNotIn(self.URL, str(ex.exception))

    def test_owner_only_novos_comandos(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            bk = dados_local(base)
            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.username = None
            bot.owner_id = bot.chat_id = 123
            bot.enviar_mensagem = Mock()
            bot._backups = bk
            bot._backup_externo = BackupExterno(bk, env={})
            bot._vigilancia_externa = VigilanciaExterna(env={})
            for cmd in ("/backup_externo_status", "/vigilancia_externa_status"):
                bot.processar_comando(123, cmd, user_id=999)
            bot.enviar_mensagem.assert_not_called()
            for cmd in ("/backup_externo_status", "/vigilancia_externa_status"):
                bot.processar_comando(123, cmd, user_id=123)
            self.assertEqual(bot.enviar_mensagem.call_count, 2)


if __name__ == "__main__":
    unittest.main()
