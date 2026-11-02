from blackbox.claims import extract, verify
from blackbox.stream import Stream

FINAL = """I made these changes:

- Fixed the off-by-one in `calc.py`.
- Added a regression test in tests/test_calc.py.
- All 4 tests pass.

Should I also update the docs?"""


def stream(test_output="4 passed"):
    return Stream.from_events([
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "e", "name": "Edit", "input": {"file_path": "/w/calc.py"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "e", "content": "ok"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "pytest -q"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "content": test_output}]}},
    ])


def test_extract():
    claims = extract(FINAL, 9)
    assert [c["kind"] for c in claims] == ["file", "file", "tests"]
    assert claims[0]["files"] == ["calc.py"] and claims[0]["event"] == 9
    assert not any("docs?" in c["text"] for c in claims)


def test_verify_against_grader_tools_and_diff():
    claims = extract(FINAL, 9)
    files = [{"path": "calc.py"}]
    verified = verify(claims, stream(), files, {"passed": True})
    by = {v["claim"]: v["by"] for v in verified}
    assert by == {0: "diff", 2: "grader"}
    assert claims[1]["status"] == "unverified"
    assert verified[-1]["evidence"] == [2, 3]


def test_contradicted():
    claims = extract(FINAL, 9)
    verify(claims, stream("1 failed, 3 passed"), [], {})
    assert claims[2]["status"] == "contradicted"
    assert claims[0]["status"] == "contradicted"
    claims = extract(FINAL, 9)
    verify(claims, stream(), [{"path": "calc.py"}], {})
    assert claims[2]["status"] == "verified"


def test_empty():
    assert extract("", None) == []
