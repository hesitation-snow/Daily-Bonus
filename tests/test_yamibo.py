import unittest
from unittest.mock import MagicMock, Mock, patch

from checkin import yamibo


class YamiboWafTests(unittest.TestCase):
    def setUp(self):
        yamibo.msg = []
        self.cookie = {'name': 'nox_jst_v1', 'value': 'test-pass', 'domain': '.yamibo.com', 'path': '/'}

    def browser(self):
        manager = MagicMock()
        runtime = manager.__enter__.return_value
        browser = runtime.chromium.launch.return_value
        context = browser.new_context.return_value
        return manager, browser, context, context.new_page.return_value

    def test_open_forum_without_waf_cookie_needs_no_browser(self):
        with patch.object(yamibo, 'SESSION') as session, patch.object(yamibo, 'sync_playwright') as playwright:
            session.get.return_value = Mock(status_code=200, text='<div id="nv_forum">百合会</div>')
            self.assertTrue(yamibo.solve_waf())
            playwright.assert_not_called()

    def test_cookie_delayed_until_after_navigation(self):
        manager, browser, context, page = self.browser()
        context.cookies.side_effect = [[], [self.cookie]]
        with patch.object(yamibo, 'sync_playwright', return_value=manager), patch.object(yamibo, '_verify_forum', side_effect=[False, True]), patch.object(yamibo, 'SESSION') as session:
            self.assertTrue(yamibo.solve_waf())
            page.wait_for_timeout.assert_called_once_with(500)
            self.assertEqual(page.goto.call_args.kwargs['wait_until'], 'domcontentloaded')
            session.cookies.set.assert_called_once_with('nox_jst_v1', 'test-pass', domain='.yamibo.com', path='/')
            browser.close.assert_called_once()

    def test_navigation_timeout_still_checks_cookie(self):
        manager, browser, context, page = self.browser()
        page.goto.side_effect = yamibo.PlaywrightTimeoutError('timed out')
        context.cookies.return_value = [self.cookie]
        with patch.object(yamibo, 'sync_playwright', return_value=manager), patch.object(yamibo, '_verify_forum', side_effect=[False, True]), patch.object(yamibo, 'SESSION'):
            self.assertTrue(yamibo.solve_waf())
            browser.close.assert_called_once()

    def test_cookie_alone_does_not_mean_success(self):
        manager, browser, context, page = self.browser()
        context.cookies.return_value = [self.cookie]
        with patch.object(yamibo, 'sync_playwright', return_value=manager), patch.object(yamibo, '_verify_forum', return_value=False), patch.object(yamibo.time, 'monotonic', side_effect=[0, 1, 31]), patch.object(yamibo, 'SESSION'):
            self.assertFalse(yamibo.solve_waf())
            self.assertIn('通行 Cookie 已生成', yamibo.msg[-1]['value'])
            browser.close.assert_called_once()

    def test_browser_failure_is_reported_and_browser_closed(self):
        manager, browser, context, page = self.browser()
        page.goto.side_effect = yamibo.PlaywrightError('internal sensitive detail')
        with patch.object(yamibo, 'sync_playwright', return_value=manager), patch.object(yamibo, '_verify_forum', return_value=False):
            self.assertFalse(yamibo.solve_waf())
            self.assertIn('Chromium', yamibo.msg[-1]['value'])
            self.assertNotIn('sensitive', yamibo.msg[-1]['value'])
            browser.close.assert_called_once()

    def test_challenge_or_unrelated_page_is_not_forum(self):
        for status, text in [(405, '<script>nox</script>'), (200, '<html>Access denied</html>'), (403, 'Powered by Discuz!')]:
            self.assertFalse(yamibo._forum_ready(status, text))

    def test_signed_page_challenge_recovers_target_once(self):
        challenge = Mock(status_code=405, text='<script>window.__noxExpire=30</script>')
        normal = Mock(status_code=200, text='<a class="btna primary" href="plugin.php?id=zqlj_sign&amp;sign=abc123"><span>点击打卡</span></a>')
        with patch.object(yamibo, 'SESSION') as session, patch.object(yamibo, 'solve_waf', return_value=True) as recover:
            session.get.side_effect = [challenge, normal]
            self.assertEqual(yamibo.get_sign_page()[:2], ('abc123', False))
            recover.assert_called_once_with(f'{yamibo.BASE_URL}/plugin.php?id=zqlj_sign')
            self.assertEqual(session.get.call_count, 2)

    def test_repeated_waf_does_not_loop_or_claim_signed(self):
        challenge = Mock(status_code=405, text='<script>window.__noxExpire=30</script>')
        with patch.object(yamibo, 'SESSION') as session, patch.object(yamibo, 'solve_waf', return_value=True) as recover:
            session.get.return_value = challenge
            self.assertEqual(yamibo.get_sign_page(), (None, None, None))
            recover.assert_called_once()
            self.assertIn('HTTP 405', yamibo.msg[-1]['value'])

    def test_bare_403_triggers_one_recovery(self):
        denied = Mock(status_code=403, text='<html>Forbidden</html>')
        normal = Mock(status_code=200, text='<a href="plugin.php?id=zqlj_sign&amp;sign=abc123">点击打卡</a>')
        with patch.object(yamibo, 'SESSION') as session, patch.object(yamibo, 'solve_waf', return_value=True) as recover:
            session.get.side_effect = [denied, normal]
            self.assertEqual(yamibo.get_sign_page()[:2], ('abc123', False))
            recover.assert_called_once_with(f'{yamibo.BASE_URL}/plugin.php?id=zqlj_sign')
            self.assertEqual(session.get.call_count, 2)

    def test_persistent_bare_403_is_not_mislabeled_as_waf(self):
        denied = Mock(status_code=403, text='<html>Forbidden</html>')
        with patch.object(yamibo, 'SESSION') as session, patch.object(yamibo, 'solve_waf', return_value=True) as recover:
            session.get.return_value = denied
            self.assertEqual(yamibo.get_sign_page(), (None, None, None))
            recover.assert_called_once()
            self.assertIn('访问被拒绝', yamibo.msg[-1]['value'])
            self.assertNotIn('仍被 WAF 拦截', yamibo.msg[-1]['value'])

    def test_nested_multiclass_signed_button(self):
        normal = Mock(status_code=200, text="<a class='extra btna'><span>今日已打卡</span></a>")
        with patch.object(yamibo, '_get_sign_response', return_value=normal):
            self.assertEqual(yamibo.get_sign_page()[:2], (None, True))

    def test_unknown_markup_is_not_waf_or_already_signed(self):
        normal = Mock(status_code=200, text='<html>我的打卡动态</html>')
        with patch.object(yamibo, '_get_sign_response', return_value=normal):
            self.assertEqual(yamibo.get_sign_page(), (None, None, None))
            self.assertIn('页面结构', yamibo.msg[-1]['value'])

    def test_auth_cookies_seed_browser_but_other_domains_do_not(self):
        session = yamibo.cffi_requests.Session()
        session.cookies.set('EeqY_2132_auth', 'login-token', domain='bbs.yamibo.com')
        session.cookies.set('nox_jst_v1', 'old-waf', domain='bbs.yamibo.com')
        session.cookies.set('unrelated', 'private', domain='example.com')
        with patch.object(yamibo, 'SESSION', session):
            cookies = yamibo._browser_cookies()
            self.assertEqual([c['name'] for c in cookies], ['EeqY_2132_auth'])
            self.assertEqual(cookies[0]['value'], 'login-token')

    def test_target_browser_preserves_auth_and_only_imports_waf(self):
        manager, browser, context, page = self.browser()
        context.cookies.return_value = [self.cookie, {'name': 'EeqY_2132_auth', 'value': 'guest'}]
        session = yamibo.cffi_requests.Session()
        session.cookies.set('EeqY_2132_auth', 'login-token', domain='bbs.yamibo.com')
        url = f'{yamibo.BASE_URL}/plugin.php?id=zqlj_sign'
        with patch.object(yamibo, 'SESSION', session), patch.object(yamibo, 'sync_playwright', return_value=manager), patch.object(yamibo, '_verify_forum', side_effect=[False, True]):
            self.assertTrue(yamibo.solve_waf(url))
            self.assertEqual(page.goto.call_args.args[0], url)
            self.assertEqual(context.add_cookies.call_args.args[0][0]['value'], 'login-token')
            self.assertEqual(session.cookies.get('EeqY_2132_auth'), 'login-token')

    def test_new_waf_cookie_removes_duplicate_old_domains_only(self):
        session = yamibo.cffi_requests.Session()
        session.cookies.set('nox_jst_v1', 'old-one', domain='bbs.yamibo.com')
        session.cookies.set('nox_jst_v1', 'old-two', domain='.yamibo.com')
        session.cookies.set('EeqY_2132_auth', 'login-token', domain='bbs.yamibo.com')
        with patch.object(yamibo, 'SESSION', session):
            yamibo._set_waf_cookie(self.cookie)
            cookies = [c for c in session.cookies.jar if c.name == 'nox_jst_v1']
            self.assertEqual(len(cookies), 1)
            self.assertEqual(cookies[0].value, 'test-pass')
            self.assertEqual(session.cookies.get('EeqY_2132_auth'), 'login-token')

    def test_diagnostics_distinguish_browser_denial_from_cookie_failure(self):
        manager, browser, context, page = self.browser()
        page.goto.return_value = Mock(status=403)
        page.content.return_value = '<html>Forbidden</html>'
        context.cookies.return_value = []
        with patch.object(yamibo, 'sync_playwright', return_value=manager), patch.object(yamibo, '_verify_forum', return_value=False), patch.object(yamibo.time, 'monotonic', side_effect=[0, 31]):
            self.assertFalse(yamibo.solve_waf())
            self.assertIn('浏览器 HTTP 403', yamibo.msg[-1]['value'])
            self.assertIn('Cookie 未生成', yamibo.msg[-1]['value'])


if __name__ == '__main__':
    unittest.main()
