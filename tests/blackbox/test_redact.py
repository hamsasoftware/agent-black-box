from pathlib import Path

from blackbox.redact import Redactor, find_secrets, scan
from conftest import FAKE_KEY

GH = "ghp_" + "A1b2C3d4" * 5
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
BEARER = "Bear" + "er abcdefghijklmnopqrstuvwx"
ASSIGNED = "api_" + "key = 'abcdefghijklmnop1234'"


def test_patterns_are_redacted():
    r = Redactor()
    text = (f"key {FAKE_KEY} gh {GH} aws {AWS} Authorization: {BEARER} "
            f"{ASSIGNED} mail a.b+c@mail.example.com path /home/alice/project/x.py "
            "mac /Users/bob/code root /root/.ssh")
    out = r.text(text)
    for leaked in (FAKE_KEY, GH, AWS, "abcdefghijklmnopqrstuvwx", "abcdefghijklmnop1234", "a.b+c@", "alice", "bob"):
        assert leaked not in out
    assert "~/project/x.py" in out and "~/code" in out and "~/.ssh" in out
    assert "Bearer [REDACTED:bearer]" in out


def test_env_values_and_replacements():
    r = Redactor(["supersecretvalue", "1", ""], {"/tmp/ws": "<workspace>"})
    assert r.text("x supersecretvalue y /tmp/ws/a 1") == "x [REDACTED:env] y <workspace>/a 1"


def test_home_is_tilde():
    r = Redactor()
    assert r.text(str(Path.home()) + "/a") == "~/a"


def test_obj_recurses():
    r = Redactor(["supersecretvalue"])
    assert r.obj({"a": ["supersecretvalue", 3, None], "supersecretvalue": True}) == {
        "a": ["[REDACTED:env]", 3, None], "[REDACTED:env]": True}


def test_private_key_block():
    pem = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIabc\n-----END RSA " + "PRIVATE KEY-----"
    assert "MIIabc" not in Redactor().text(pem)


def test_plain_text_untouched():
    text = "def tokens(self): return self.input_tokens  # 1234 passed @pytest.fixture"
    assert Redactor().text(text) == text
    assert find_secrets(text) == []


def test_scan(tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "a.txt").write_text("nothing here\n")
    (clean / ".git").mkdir()
    (clean / ".git" / "x").write_text(GH)
    assert scan([str(clean)]) == []
    (clean / "b.txt").write_text(f"line\ntoken {GH}\n")
    assert scan([str(clean)]) == [(str(clean / "b.txt"), 2, "github-token")]
    (clean / "c.txt").write_text("someone" + "@" + "example.org\n")
    assert scan([str(clean / "c.txt")]) == []
    assert scan([str(clean / "c.txt")], strict=True)[0][2] == "email"
    (clean / "d.txt").write_text("value supersecretvalue\n")
    assert scan([str(clean / "d.txt")], extra_secrets=["supersecretvalue"])[0][2] == "env-value"
