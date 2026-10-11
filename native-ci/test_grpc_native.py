"""Real CPU loopback RPC and generated-stub regression tests."""
from concurrent import futures
import importlib.util
import pathlib
import subprocess
import sys
import sysconfig
import tempfile
import unittest

import grpc


class NativeGrpc(unittest.TestCase):
    def test_interpreter(self):
        self.assertEqual(sysconfig.get_platform(), 'win-arm64')
        self.assertEqual(sys.version_info[:2], (3, 12))

    def test_loopback_and_unknown_method(self):
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
            'native.Echo', {'Echo': grpc.unary_unary_rpc_method_handler(lambda request, context: b'reply:' + request)}),))
        port = server.add_insecure_port('127.0.0.1:0')
        self.assertGreater(port, 0)
        server.start()
        try:
            with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                self.assertEqual(channel.unary_unary('/native.Echo/Echo')(b'arm64', timeout=10), b'reply:arm64')
                with self.assertRaises(grpc.RpcError) as raised:
                    channel.unary_unary('/native.Echo/Missing')(b'negative', timeout=10)
                self.assertEqual(raised.exception.code(), grpc.StatusCode.UNIMPLEMENTED)
        finally:
            server.stop(0).wait(10)


class GeneratedGrpc(unittest.TestCase):
    def test_generated_stub(self):
        # No fallback or skip: this suite requires the built grpcio-tools wheel.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root/'native.proto').write_text('syntax = "proto3"; package native; message Message { string text = 1; } service Echo { rpc Reply(Message) returns (Message); }')
            subprocess.run([sys.executable, '-m', 'grpc_tools.protoc', f'-I{tmp}', f'--python_out={tmp}', f'--grpc_python_out={tmp}', str(root/'native.proto')], check=True, timeout=60)
            sys.path.insert(0, tmp)
            try:
                import native_pb2 as pb
                import native_pb2_grpc as api
                class Echo(api.EchoServicer):
                    def Reply(self, request, context):
                        return pb.Message(text=request.text[::-1])
                server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
                api.add_EchoServicer_to_server(Echo(), server)
                port = server.add_insecure_port('127.0.0.1:0')
                self.assertGreater(port, 0)
                server.start()
                try:
                    with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                        stub = api.EchoStub(channel)
                        result = stub.Reply(pb.Message(text='arm64-protoc'), timeout=10)
                        self.assertEqual(result.text, 'cotorp-46mra')
                        with self.assertRaises(grpc.RpcError) as raised:
                            channel.unary_unary('/native.Echo/NotImplemented')(b'', timeout=10)
                        self.assertEqual(raised.exception.code(), grpc.StatusCode.UNIMPLEMENTED)
                finally:
                    server.stop(0).wait(10)
                (root/'invalid.proto').write_text('this is deliberately invalid protobuf')
                bad = subprocess.run([sys.executable, '-m', 'grpc_tools.protoc', f'-I{tmp}', f'--python_out={tmp}', str(root/'invalid.proto')], capture_output=True, timeout=60)
                self.assertNotEqual(bad.returncode, 0)
                self.assertIn(b'Expected', bad.stderr)
            finally:
                sys.path.remove(tmp)


if __name__ == '__main__':
    unittest.main(verbosity=2)
