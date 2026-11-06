import contextlib
import io
import json
import unittest

from tests.site import Site, html
from web_crawler.cli import main


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_text_output(self):
        routes = {"/": html("/a", title="Home"), "/a": html(title="A")}
        with Site(routes) as site:
            rc, out, _ = run(site.base + "/", "--delay", "0", "--depth", "1")
        self.assertEqual(rc, 0)
        self.assertIn("[200]", out)
        self.assertIn("Home", out)
        self.assertIn("2 pages, 2 ok", out)

    def test_json_output(self):
        with Site({"/": html(title="Home")}) as site:
            rc, out, _ = run(site.base + "/", "--delay", "0", "--json")
        data = json.loads(out)
        self.assertEqual((rc, len(data), data[0]["title"]), (0, 1, "Home"))

    def test_bad_url(self):
        self.assertEqual(run("not-a-url")[0], 2)


if __name__ == "__main__":
    unittest.main()
