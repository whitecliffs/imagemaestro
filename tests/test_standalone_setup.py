import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
spec = importlib.util.spec_from_file_location('standalone_install', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
from services.local_access import LocalAccessMiddleware


class StandaloneSetupTests(unittest.TestCase):
    def test_amd_chipset_is_not_a_gpu(self):
        with patch.object(installer.sys, 'platform', 'linux'), patch.object(installer.platform, 'machine', return_value='x86_64'), patch.object(installer.os.path, 'exists', return_value=False), patch.object(installer.shutil, 'which', side_effect=lambda x: '/usr/bin/lspci' if x == 'lspci' else None), patch.object(installer.subprocess, 'check_output', return_value='Host bridge: Advanced Micro Devices AMD\nVGA compatible controller: Intel Graphics'):
            self.assertEqual(installer.detect_system()['gpu_type'], 'cpu')

    def test_uv_uses_selected_python_and_seeds_pip(self):
        with patch.object(Path, 'exists', return_value=False), patch.object(installer.shutil, 'which', return_value='/usr/bin/uv'), patch.object(installer.subprocess, 'check_call') as call:
            installer.create_virtualenv('/test/python3.11', Path('/test/venv'))
            self.assertEqual(call.call_args_list[0].args[0], ['uv', 'venv', '--seed', '--python', '/test/python3.11', '/test/venv'])

    def request(self, host='127.0.0.1:7860', origin=None, protocol='http'):
        async def check():
            messages = []
            async def app(scope, receive, send):
                await send({'type': 'http.response.start', 'status': 200})
            async def send(message):
                messages.append(message)
            headers = [(b'host', host.encode())]
            if origin is not None:
                headers.append((b'origin', origin.encode()))
            with patch.dict(os.environ, {'SERVER_NAME': '127.0.0.1'}):
                await LocalAccessMiddleware(app)({'type': protocol, 'headers': headers}, None, send)
            return messages[0]
        return asyncio.run(check())

    def test_normal_and_same_origin_requests(self):
        self.assertEqual(self.request()['status'], 200)
        self.assertEqual(self.request(origin='http://127.0.0.1:7860')['status'], 200)

    def test_cross_origin_post_and_rebinding_rejected(self):
        self.assertEqual(self.request(origin='https://evil.example')['status'], 403)
        self.assertEqual(self.request(host='evil.example')['status'], 403)
        self.assertEqual(self.request(origin='null')['status'], 403)

    def test_cross_origin_websocket_rejected(self):
        self.assertEqual(self.request(origin='https://evil.example', protocol='websocket')['code'], 1008)

    def test_cpu_seed_and_repeated_setup(self):
        import torch
        if torch.cuda.is_available():
            self.skipTest('CPU compatibility test')
        from shared.device_compat import setup_device_compatibility
        setup_device_compatibility()
        stream_class = torch.cuda.Stream
        setup_device_compatibility()
        self.assertIs(torch.cuda.Stream, stream_class)
        torch.manual_seed(123)
        first = torch.rand(2)
        torch.manual_seed(123)
        self.assertTrue(torch.equal(first, torch.rand(2)))


if __name__ == '__main__':
    unittest.main()
