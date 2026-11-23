import io
import os
import shutil
import struct
import tempfile
import unittest
import zlib

from auxiliar import EXEMPLOS, galo_cli
from galo import BYTECODE_VERSION
from galo.compiler import compile_source
from galo.compiler.bytecode import MAGIC, CodeObject, Op, dump_module, load_module, verify, Module
from galo.errors import GaloBytecodeError
from galo.runtime.vm import VM


def rodar(module, entradas=()):
    out = io.StringIO()
    linhas = list(entradas)

    def ler(prompt=""):
        out.write(prompt)
        if not linhas:
            raise EOFError
        return linhas.pop(0)

    VM(out=out, input_fn=ler).run(module)
    return out.getvalue()


def com_crc(payload: bytes, versao: int = BYTECODE_VERSION) -> bytes:
    return MAGIC + struct.pack("<H", versao) + payload + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF)


DETERMINISTICOS = ["ola_mundo", "fatorial", "fibonacci", "listas", "mapas", "maquina_turing", "brainfuck",
                   "erros", "primos", "ordenacao", "closures", "hanoi"]


class TestFormato(unittest.TestCase):
    def test_ida_e_volta_preserva_o_comportamento(self):
        for nome in DETERMINISTICOS:
            with self.subTest(exemplo=nome):
                with open(os.path.join(EXEMPLOS, nome + ".galo"), encoding="utf-8") as f:
                    fonte = f.read()
                modulo = compile_source(fonte, nome + ".galo").module
                dados = dump_module(modulo)
                recarregado = load_module(dados, nome + ".galoc")
                self.assertEqual(rodar(modulo), rodar(recarregado))
                self.assertEqual(dump_module(recarregado), dados)

    def test_constantes_de_todos_os_tipos(self):
        fonte = ('mostre -12345678901234567890123, 0, -0.0, 1.5e300, "çãé 🐓 \\n", verdadeiro, falso, nulo\n'
                 'defina d do tipo decimal como 1\nmostre d')
        modulo = load_module(dump_module(compile_source(fonte).module))
        self.assertEqual(rodar(modulo), '-12345678901234567890123 0 -0.0 1.5e+300 çãé 🐓 \n verdadeiro falso nulo\n1.0\n')

    def test_metadados(self):
        modulo = compile_source('programa "Teste"\nmostre 1', "teste.galo").module
        m = load_module(dump_module(modulo))
        self.assertEqual((m.program_name, m.source_name), ("Teste", "teste.galo"))

    def test_assinatura_invalida(self):
        with self.assertRaises(GaloBytecodeError) as ctx:
            load_module(b"isto nao e bytecode")
        self.assertEqual(ctx.exception.code, "G502")

    def test_versao_incompativel(self):
        dados = bytearray(dump_module(compile_source("mostre 1").module))
        dados[len(MAGIC):len(MAGIC) + 2] = struct.pack("<H", BYTECODE_VERSION + 1)
        with self.assertRaises(GaloBytecodeError) as ctx:
            load_module(bytes(dados))
        self.assertEqual(ctx.exception.code, "G503")

    def test_corrupcao_detectada(self):
        dados = dump_module(compile_source("mostre 1 + 2").module)
        for posicao in range(len(MAGIC) + 2, len(dados)):
            alterado = bytearray(dados)
            alterado[posicao] ^= 0x55
            with self.subTest(posicao=posicao):
                with self.assertRaises(GaloBytecodeError):
                    load_module(bytes(alterado))

    def test_arquivo_truncado(self):
        dados = dump_module(compile_source("mostre 1").module)
        with self.assertRaises(GaloBytecodeError):
            load_module(dados[:-7])

    def _modulo_manual(self, code, consts=(None,), nlocals=0):
        co = CodeObject("<programa>", "x.galo")
        co.code = list(code)
        co.positions = [(1, 1)] * (len(code) // 2)
        co.consts = list(consts)
        co.nlocals = nlocals
        return co

    def test_verificador_rejeita_bytecode_mal_formado(self):
        casos = {
            "instrução desconhecida": [250, 0, Op.RETURN, 0],
            "constante inexistente": [Op.CONST, 9, Op.RETURN, 0],
            "variável local inexistente": [Op.LOAD_LOCAL, 3, Op.RETURN, 0],
            "desvio para posição inválida": [Op.JUMP, 3, Op.RETURN, 0],
            "não termina com um retorno": [Op.CONST, 0],
        }
        for detalhe, code in casos.items():
            with self.subTest(detalhe):
                with self.assertRaises(GaloBytecodeError) as ctx:
                    verify(self._modulo_manual(code))
                self.assertIn(detalhe, ctx.exception.message)

    def test_verificador_aceita_bytecode_valido(self):
        verify(self._modulo_manual([Op.CONST, 0, Op.RETURN, 0]))


class TestExecucaoIndependenteDoFonte(unittest.TestCase):
    def test_compilar_apagar_fonte_e_rodar(self):
        with tempfile.TemporaryDirectory() as pasta:
            fonte = os.path.join(pasta, "prog.galo")
            shutil.copy(os.path.join(EXEMPLOS, "fatorial.galo"), fonte)
            r = galo_cli("compilar", fonte)
            self.assertEqual(r.returncode, 0, r.stderr)
            os.remove(fonte)
            r = galo_cli("rodar", os.path.join(pasta, "prog.galoc"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("10! = 3628800", r.stdout)

    def test_erro_de_execucao_em_bytecode_sem_fonte(self):
        with tempfile.TemporaryDirectory() as pasta:
            fonte = os.path.join(pasta, "falha.galo")
            with open(fonte, "w", encoding="utf-8") as f:
                f.write("defina l como [1]\nmostre l[5]\n")
            self.assertEqual(galo_cli("compilar", fonte, "-o", os.path.join(pasta, "f.galoc")).returncode, 0)
            os.remove(fonte)
            r = galo_cli("rodar", os.path.join(pasta, "f.galoc"))
            self.assertEqual(r.returncode, 2)
            self.assertIn("[G304]", r.stderr)
            self.assertIn("Linha: 2", r.stderr)


if __name__ == "__main__":
    unittest.main()
