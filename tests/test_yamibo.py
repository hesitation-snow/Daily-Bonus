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
            self.assertIn('未获得可用通行 Cookie', yamibo.msg[-1]['value'])
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


if __name__ == '__main__':
    unittest.main()
