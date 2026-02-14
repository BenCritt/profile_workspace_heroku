from unittest.mock import MagicMock, patch

from django.test import RequestFactory, TestCase

from .forms import RedirectCheckerForm
from .redirect_checker_utils import trace_redirects
from .views import redirect_checker_view


class RedirectCheckerFormTests(TestCase):
    """Tests for URL input validation and normalization."""

    def test_valid_https_url(self):
        form = RedirectCheckerForm(data={"url": "https://example.com"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["url"], "https://example.com")

    def test_valid_http_url(self):
        form = RedirectCheckerForm(data={"url": "http://example.com"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["url"], "http://example.com")

    def test_auto_prepend_https(self):
        """If no scheme is provided, https:// should be prepended."""
        form = RedirectCheckerForm(data={"url": "example.com"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["url"], "https://example.com")

    def test_auto_prepend_with_path(self):
        form = RedirectCheckerForm(data={"url": "example.com/some/page"})
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["url"], "https://example.com/some/page"
        )

    def test_whitespace_stripped(self):
        form = RedirectCheckerForm(data={"url": "  https://example.com  "})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["url"], "https://example.com")

    def test_reject_ftp_scheme(self):
        form = RedirectCheckerForm(data={"url": "ftp://example.com"})
        self.assertFalse(form.is_valid())

    def test_reject_empty_input(self):
        form = RedirectCheckerForm(data={"url": ""})
        self.assertFalse(form.is_valid())

    def test_reject_no_hostname(self):
        form = RedirectCheckerForm(data={"url": "https://"})
        self.assertFalse(form.is_valid())


class TraceRedirectsTests(TestCase):
    """Tests for the core redirect-tracing logic."""

    @patch("redirect_checker.utils.requests.get")
    def test_no_redirects(self, mock_get):
        """A URL that returns 200 immediately should produce one hop."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Server": "nginx", "Content-Type": "text/html"}
        mock_get.return_value = mock_resp

        result = trace_redirects("https://example.com")

        self.assertEqual(result["total_hops"], 0)
        self.assertEqual(len(result["hops"]), 1)
        self.assertTrue(result["hops"][0]["is_final"])
        self.assertEqual(result["chain_type"], "clean")
        self.assertFalse(result["has_loop"])

    @patch("redirect_checker.utils.requests.get")
    def test_single_301_redirect(self, mock_get):
        """A single 301 → 200 chain should show 2 hops, 1 redirect."""
        redirect_resp = MagicMock()
        redirect_resp.status_code = 301
        redirect_resp.headers = {
            "Location": "https://www.example.com/",
            "Server": "Apache",
        }

        final_resp = MagicMock()
        final_resp.status_code = 200
        final_resp.headers = {"Server": "nginx", "Content-Type": "text/html"}

        mock_get.side_effect = [redirect_resp, final_resp]

        result = trace_redirects("https://example.com")

        self.assertEqual(result["total_hops"], 1)
        self.assertEqual(len(result["hops"]), 2)
        self.assertTrue(result["hops"][0]["is_redirect"])
        self.assertTrue(result["hops"][1]["is_final"])

    @patch("redirect_checker.utils.requests.get")
    def test_redirect_loop_detected(self, mock_get):
        """A loop (A → B → A) should be caught and flagged."""
        resp_a = MagicMock()
        resp_a.status_code = 302
        resp_a.headers = {"Location": "https://b.example.com/"}

        resp_b = MagicMock()
        resp_b.status_code = 302
        resp_b.headers = {"Location": "https://a.example.com/"}

        # The third call would be back to A, but loop detection should stop
        # before making it.
        mock_get.side_effect = [resp_a, resp_b]

        result = trace_redirects("https://a.example.com/")

        self.assertTrue(result["has_loop"])
        self.assertEqual(result["chain_type"], "errors")
        self.assertTrue(
            any("loop" in issue.lower() for issue in result["issues"])
        )

    @patch("redirect_checker.utils.requests.get")
    def test_long_chain_warning(self, mock_get):
        """A chain with >2 redirects should generate a warning."""
        responses = []
        for i in range(4):
            r = MagicMock()
            r.status_code = 301
            r.headers = {"Location": f"https://example.com/step{i + 1}"}
            responses.append(r)

        final = MagicMock()
        final.status_code = 200
        final.headers = {"Server": "nginx", "Content-Type": "text/html"}
        responses.append(final)

        mock_get.side_effect = responses

        result = trace_redirects("https://example.com/step0")

        self.assertEqual(result["total_hops"], 4)
        self.assertTrue(
            any("long redirect chain" in issue.lower() for issue in result["issues"])
        )


class RedirectCheckerViewTests(TestCase):
    """Tests for the Django view layer."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_get_returns_empty_form(self):
        request = self.factory.get("/projects/redirect-checker/")
        response = redirect_checker_view(request)
        self.assertEqual(response.status_code, 200)

    @patch("redirect_checker.views.trace_redirects")
    def test_post_valid_url_calls_trace(self, mock_trace):
        mock_trace.return_value = {
            "hops": [],
            "total_hops": 0,
            "total_time": 0.1,
            "issues": [],
            "has_loop": False,
            "final_url": "https://example.com",
            "chain_type": "clean",
        }

        request = self.factory.post(
            "/projects/redirect-checker/",
            data={"url": "https://example.com"},
        )
        response = redirect_checker_view(request)
        self.assertEqual(response.status_code, 200)
        mock_trace.assert_called_once_with("https://example.com")

    def test_post_invalid_url_returns_form_errors(self):
        request = self.factory.post(
            "/projects/redirect-checker/",
            data={"url": ""},
        )
        response = redirect_checker_view(request)
        self.assertEqual(response.status_code, 200)
