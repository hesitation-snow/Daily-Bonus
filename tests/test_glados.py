import importlib.util
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from checkin import glados

SCRIPT = Path(__file__).resolve().parents[1] / 'integrations/auto_checkin/glados_checkin.py'
spec = importlib.util.spec_from_file_location('auto_checkin', SCRIPT)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class GladosTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'GLADOS_COOKIE': 'test-cookie'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.checker = source.GLaDOSChecker()

    def response(self, data):
        response = Mock()
        response.json.return_value = data
        return response

    def test_success(self):
        with patch.object(source.requests, 'post', return_value=self.response({'message': 'Got 1 Points'})) as post:
            self.assertEqual(self.checker.perform_checkin(), (True, '获得 1 积分 🎉'))
            self.assertEqual(post.call_args.kwargs['json'], {'token': 'glados.cloud'})
            self.assertEqual(post.call_args.kwargs['timeout'], 15)
        with patch.object(source.requests, 'get', return_value=self.response({'code': 0, 'data': {'leftDays': '12.34'}})):
            self.assertEqual(self.checker.check_status(), (True, '剩余天数: 12.3 🗓️'))

    def test_already_checked_in(self):
        self.assertTrue(self.checker._handle_checkin_result('Please Try Tomorrow')[0])

    def test_stable_configured_browser_identity(self):
        ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15'
        with patch.dict(os.environ, {'GLADOS_USER_AGENT': ua}):
            checker = source.GLaDOSChecker()
        with patch.object(source.requests, 'post', return_value=self.response({'code': 0, 'message': 'Checkin!'})) as post, patch.object(source.requests, 'get', return_value=self.response({'code': 0, 'data': {'leftDays': 5}})) as get:
            checker.perform_checkin()
            checker.check_status()
            self.assertEqual(post.call_args.kwargs['headers']['User-Agent'], ua)
            self.assertEqual(get.call_args.kwargs['headers']['User-Agent'], ua)
            self.assertEqual(checker._gen_headers(), checker._gen_headers())

    def test_new_success_messages(self):
        for message in ("Today's observation logged. Return tomorrow for more points.", 'Checkin!'):
            with patch.object(source.requests, 'post', return_value=self.response({'code': 0, 'message': message})):
                self.assertTrue(self.checker.perform_checkin()[0])

    def test_device_rejection_is_actionable_even_with_success_text(self):
        for data in (
            {'code': 4, 'message': 'Automated check-in detected. Please sign in again to continue.'},
            {'code': 4, 'reason': 'device-mismatch', 'message': 'Got 1 Points'},
        ):
            with patch.object(source.requests, 'post', return_value=self.response(data)):
                success, message = self.checker.perform_checkin()
                self.assertFalse(success)
                self.assertIn('GLADOS_USER_AGENT', message)
                self.assertIn('GLADOS_COOKIE', message)
        with patch.object(source.requests, 'get', return_value=self.response(data)):
            self.assertIn('GLADOS_USER_AGENT', self.checker.check_status()[1])

    def test_rejected_checkin_never_counts_as_success(self):
        with patch.object(source.requests, 'post', return_value=self.response({'code': 2, 'message': 'Got 1 Points'})):
            self.assertFalse(self.checker.perform_checkin()[0])

    def test_expired_session_explains_cookie_refresh(self):
        with patch.object(source.requests, 'post', return_value=self.response({'code': 1, 'message': '没有权限'})):
            success, message = self.checker.perform_checkin()
            self.assertFalse(success)
            self.assertIn('gld:sess.sig', message)

    def test_invalid_status_never_reports_zero_days(self):
        for data in ({'code': 1}, {'code': 0, 'data': {}}, [], {'code': 0, 'data': {'leftDays': 'invalid'}}):
            with self.subTest(data=data), patch.object(source.requests, 'get', return_value=self.response(data)):
                success, message = self.checker.check_status()
                self.assertFalse(success)
                self.assertNotIn('剩余天数', message)

    def test_transport_and_json_errors(self):
        for error in (source.requests.Timeout('secret'), ValueError('secret')):
            with patch.object(source.requests, 'post', side_effect=error):
                success, message = self.checker.perform_checkin()
                self.assertFalse(success)
                self.assertNotIn('secret', message)

    def test_adapter_escapes_html_and_excludes_telegram_secrets(self):
        with patch.dict(os.environ, {'TG_BOT_TOKEN': 'secret', 'GLADOS_USER_AGENT': 'browser-ua'}), patch.object(glados.subprocess, 'run', return_value=Mock(returncode=0, stdout='<account>&')) as run:
            self.assertEqual(glados.main(), '&lt;account&gt;&amp;')
            self.assertNotIn('TG_BOT_TOKEN', run.call_args.kwargs['env'])
            self.assertEqual(run.call_args.kwargs['env']['GLADOS_USER_AGENT'], 'browser-ua')

    def test_adapter_failure_and_timeout(self):
        with patch.object(glados.subprocess, 'run', return_value=Mock(returncode=1, stdout='secret')):
            self.assertNotIn('secret', glados.main())
        with patch.object(glados.subprocess, 'run', side_effect=subprocess.TimeoutExpired('test', 60)):
            self.assertIn('超时', glados.main())

    def test_missing_cookie_skips_process(self):
        with patch.dict(os.environ, {'GLADOS_COOKIE': ''}), patch.object(glados.subprocess, 'run') as run:
            self.assertEqual(glados.main(), 'No GLADOS_COOKIE set')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
