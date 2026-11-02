import re
import shlex

SAFE_ENV_NAMES = {".env.example", ".env.sample", ".env.template", ".env.dist"}
SECRET_NAMES = {".netrc", ".pypirc", ".git-credentials", "credentials", "credentials.json"}
SECRET_DIRS = {".ssh", ".aws", ".gnupg"}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
KEY_FILE = re.compile(r"id_(?:rsa|dsa|ecdsa|ed25519)(?!.*\.pub$)")

SEPARATORS = {";", "&&", "||", "&", "|", "|&", "\n"}
PIPES = {"|", "|&"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
INTERPRETER = re.compile(r"^(?:python[\d.]*|node|nodejs|perl|ruby|php|deno|bun)$")
WRAPPERS = {"sudo", "doas", "command", "exec", "nohup", "time", "nice", "builtin", "stdbuf"}
NAME_ONLY = {
    "echo", "printf", "true", "false", ":", "test", "[", "[[", "ls", "stat", "file", "wc",
    "touch", "mkdir", "basename", "dirname", "realpath", "readlink", "which", "type", "du",
}
GIT_NAME_ONLY = {"check-ignore", "ls-files", "status", "log", "commit", "rev-parse", "branch", "switch"}
GIT_DIFF_SUMMARY = {"--stat", "--name-only", "--name-status", "--numstat", "--shortstat", "--quiet", "--exit-code", "--summary"}
FIND_ACTIONS = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-x", "--exec", "-X", "--exec-batch"}
ROOT_TARGETS = {"/", "/*", "~", "~/", "$HOME", "${HOME}", "$HOME/", ".", "./", "..", "../", "*", ".git", ".git/"}
WRITE_CMDS = {"rm", "mv", "truncate", "tee", "cp", "touch", "ln"}
DOWNLOADERS = {"curl", "wget"}
SUBST = "__SUBST__"
SUBST_DL = "__SUBST_DL__"

ENV_DUMP_CODE = re.compile(
    r"os\.environ(?!\s*(?:\[|\.get\b|\.setdefault\b|\.pop\b))|process\.env(?!\s*[.\[])|%ENV\b|ENV\.to_h"
)
DOTENV_CODE = re.compile(r"load_dotenv|dotenv_values|require\(\s*['\"]dotenv")
STRING_LITERAL = re.compile(r"(['\"])([^'\"\n]{1,300})\1")
READ_CALL = re.compile(r"([A-Za-z_][\w.]*)\s*\((?:[^()]*,)?\s*\[?\s*(?:['\"][^'\"]*['\"]\s*,\s*)*$")
READ_FUNCS = {
    "open", "Path", "PurePath", "read_text", "read_bytes", "join", "copy", "copyfile", "copy2", "move",
    "readFileSync", "readFile", "createReadStream", "load_dotenv", "dotenv_values", "read", "File",
    "popen", "check_output", "check_call", "run", "call", "Popen", "system", "exec", "spawn", "spawnSync",
    "execSync", "foreach", "readlines", "loadtxt", "read_csv", "fopen", "file_get_contents",
}
HEREDOC = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)([A-Za-z_][\w.-]*)\2")

INSTEAD_SECRET = "ask a person for the non-secret value you need"
INSTEAD_DOWNLOAD = "download the file, read it, then run it explicitly"


class Blocked(Exception):
    def __init__(self, reason, instead):
        super().__init__(reason)
        self.reason = reason
        self.instead = instead


def is_secret_path(raw):
    path = raw.strip().strip("'\"").replace("\\", "/")
    if not path or any(c.isspace() for c in path):
        return False
    if path.startswith("/proc/") and path.endswith("/environ"):
        return True
    parts = [p for p in path.split("/") if p]
    if not parts:
        return False
    if any(p in SECRET_DIRS for p in parts):
        return True
    name = parts[-1]
    if name == ".env" or (name.startswith(".env.") and name not in SAFE_ENV_NAMES):
        return True
    if name.startswith(".env") and any(c in name[4:] for c in "*?["):
        return True
    if name in SECRET_NAMES or KEY_FILE.match(name):
        return True
    return name.endswith(SECRET_SUFFIXES)


def path_candidates(token):
    yield token
    if token.startswith("@"):
        yield token[1:]
    if "=" in token:
        value = token.split("=", 1)[1]
        yield value
        if value.startswith("@"):
            yield value[1:]
    if ":" in token and not token.startswith(("http:", "https:")):
        yield token.rsplit(":", 1)[1]


def names_secret(token):
    return any(is_secret_path(c) for c in path_candidates(token))


def _matching_paren(text, start):
    depth, i, single, double = 1, start, False, False
    while i < len(text):
        ch = text[i]
        if ch == "\\" and not single:
            i += 2
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif not single and not double:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise Blocked("could not parse the command (unbalanced parentheses)", "simplify the command")


def extract_substitutions(text, policy):
    out, i, single, double = [], 0, False, False
    while i < len(text):
        ch = text[i]
        if ch == "\\" and not single:
            out.append(text[i:i + 2])
            i += 2
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        if not single:
            opener = text[i:i + 2]
            if (opener == "$(" and text[i:i + 3] != "$((") or (not double and opener in ("<(", ">(")):
                end = _matching_paren(text, i + 2)
                inner = text[i + 2:end]
                out.append(SUBST_DL if analyse(inner, policy) else SUBST)
                i = end + 1
                continue
            if ch == "`":
                end = text.find("`", i + 1)
                if end < 0:
                    raise Blocked("could not parse the command (unbalanced backquote)", "simplify the command")
                out.append(SUBST_DL if analyse(text[i + 1:end], policy) else SUBST)
                i = end + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _consumer(prefix):
    segment = re.split(r"&&|\|\||[;|&]", prefix)[-1]
    words = segment.split()
    while words and (words[0] in WRAPPERS or "=" in words[0] and not words[0].startswith("-")):
        words = words[1:]
    return words[0].rsplit("/", 1)[-1] if words else ""


def split_heredocs(command, policy):
    lines = command.split("\n")
    kept, i = [], 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for match in HEREDOC.finditer(line):
            strip_tabs, quoted, delimiter = match.group(1), match.group(2), match.group(3)
            body = []
            while i < len(lines):
                candidate = lines[i].lstrip("\t") if strip_tabs else lines[i]
                i += 1
                if candidate == delimiter:
                    break
                body.append(lines[i - 1])
            text = "\n".join(body)
            consumer = _consumer(line[:match.start()])
            if consumer in SHELLS:
                analyse(text, policy)
            elif INTERPRETER.match(consumer):
                check_code(text)
            elif not quoted:
                extract_substitutions(text, policy)
    return "\n".join(kept)


def tokenize(text):
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError as exc:
        raise Blocked(f"could not parse the command ({exc})", "simplify the command")
    return tokens


def strip_comments(text):
    out, i, single, double = [], 0, False, False
    while i < len(text):
        ch = text[i]
        if ch == "\\" and not single:
            out.append(text[i:i + 2])
            i += 2
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif ch == "#" and not single and not double and (i == 0 or text[i - 1] in " \t\n;&|("):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def check_code(code):
    if ENV_DUMP_CODE.search(code):
        raise Blocked("dumping environment variables", "read only the variable you need and never print secrets")
    if DOTENV_CODE.search(code):
        raise Blocked("loading a secrets file from code", INSTEAD_SECRET)
    for match in STRING_LITERAL.finditer(code):
        if not is_secret_path(match.group(2)):
            continue
        line_start = code.rfind("\n", 0, match.start()) + 1
        call = READ_CALL.search(code[line_start:match.start()])
        if call and call.group(1).rsplit(".", 1)[-1] in READ_FUNCS:
            raise Blocked("reading a secrets file from code", INSTEAD_SECRET)


def analyse(command, policy):
    command = command.replace("\\\n", "")
    command = split_heredocs(command, policy)
    command = strip_comments(command)
    command = extract_substitutions(command, policy)
    tokens = tokenize(command.replace("\n", " ; "))
    has_download = False
    pipeline_download = False
    current = []
    for tok in tokens + [";"]:
        if tok in SEPARATORS:
            if current:
                name = simple_command(current, policy, pipeline_download)
                if name in DOWNLOADERS:
                    has_download = True
                    pipeline_download = pipeline_download or tok in PIPES
            if tok not in PIPES:
                pipeline_download = False
            current = []
        else:
            current.append(tok)
    return has_download


def _strip_wrappers(tokens):
    while tokens:
        head = tokens[0].rsplit("/", 1)[-1]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
            tokens = tokens[1:]
        elif head in WRAPPERS:
            tokens = tokens[1:]
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
        elif head == "timeout":
            tokens = tokens[1:]
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
            tokens = tokens[1:]
        else:
            break
    return tokens


def _split_redirections(tokens):
    args, reads, writes, i = [], [], [], 0
    while i < len(tokens):
        tok = tokens[i]
        if tok and set(tok) <= set("<>&|") and ("<" in tok or ">" in tok):
            target = tokens[i + 1] if i + 1 < len(tokens) else ""
            if tok in ("<<<", "<<", "<<-"):
                pass
            elif tok in (">&", "<&") and target.isdigit():
                pass
            elif "<" in tok:
                reads.append(target)
            else:
                writes.append(target)
            if args and args[-1].isdigit():
                args.pop()
            i += 2
            continue
        args.append(tok)
        i += 1
    return args, reads, writes


def _secret_block(cmd, token):
    raise Blocked(f"{cmd} on a secrets file ({token})", INSTEAD_SECRET)


def simple_command(tokens, policy, after_download_pipe):
    tokens = _strip_wrappers(tokens)
    if not tokens:
        return ""
    cmd = tokens[0].rsplit("/", 1)[-1]
    args, reads, writes = _split_redirections(tokens[1:])
    for target in reads:
        if names_secret(target):
            _secret_block("redirect", target)
    for target in writes:
        if policy.protected(target):
            raise Blocked(policy.protected_write_reason, policy.protected_instead)
    if after_download_pipe and (cmd in SHELLS or INTERPRETER.match(cmd) or cmd in ("source", ".", "eval")):
        raise Blocked("piping a download into a shell", INSTEAD_DOWNLOAD)
    if cmd in SHELLS | {"source", ".", "eval"} or INTERPRETER.match(cmd):
        if any(SUBST_DL in a for a in args):
            raise Blocked("running downloaded code in a shell", INSTEAD_DOWNLOAD)
    if cmd == "env":
        rest = [a for a in args if not a.startswith("-")]
        rest = _strip_wrappers(rest)
        if not rest:
            raise Blocked("dumping environment variables", "read only the variable you need and never print secrets")
        return simple_command(rest, policy, after_download_pipe)
    if cmd in ("printenv", "compgen") or (cmd == "set" and not args) or (
        cmd in ("export", "declare", "typeset") and all(a.startswith("-") for a in args)
    ):
        raise Blocked("dumping environment variables", "read only the variable you need and never print secrets")
    if cmd in SHELLS:
        if "-c" in args and args.index("-c") + 1 < len(args):
            analyse(args[args.index("-c") + 1], policy)
            return cmd
    elif cmd == "eval":
        analyse(" ".join(args), policy)
        return cmd
    elif INTERPRETER.match(cmd):
        for flag in ("-c", "-e", "-E", "-r", "--eval", "-p", "--print"):
            if flag in args and args.index(flag) + 1 < len(args):
                position = args.index(flag)
                check_code(args[position + 1])
                args = args[:position] + args[position + 2:]
    elif cmd == "xargs":
        rest = list(args)
        while rest and rest[0].startswith("-"):
            rest = rest[1:]
        if rest:
            simple_command(rest, policy, False)
        return cmd
    if cmd in NAME_ONLY:
        return cmd
    if cmd == "git":
        git_command(args, policy)
        return cmd
    if cmd == "gh" and args[:2] == ["pr", "merge"] and policy.repo_rules:
        raise Blocked("merging a pull request", "leave merging to a human reviewer")
    if cmd == "rm" and any(a == "--recursive" or (re.match(r"^-[a-zA-Z]*[rR]", a)) for a in args):
        if any(a in ROOT_TARGETS for a in args):
            raise Blocked("recursive delete of a root, home, parent or repository directory", "delete specific paths")
    if cmd in ("grep", "egrep", "fgrep", "rg", "ag", "ack"):
        args = _drop_pattern(args)
    if cmd in ("find", "fd", "fdfind"):
        if not any(a in FIND_ACTIONS for a in args):
            return cmd
        if any(names_secret(a) for a in args):
            raise Blocked("running a command on secrets files", INSTEAD_SECRET)
        return cmd
    for arg in args:
        if names_secret(arg):
            _secret_block(cmd, arg)
    if policy.protected_dirs:
        editing = cmd in WRITE_CMDS or (cmd in ("sed", "perl") and any(a.startswith("-i") or a == "--in-place" for a in args))
        targets = args[-1:] if cmd in ("cp", "ln") else args
        if editing and any(policy.protected(a) for a in targets if not a.startswith("-")):
            raise Blocked(policy.protected_change_reason, policy.protected_instead)
    return cmd


def _drop_pattern(args):
    if any(a in ("-e", "--regexp") or a.startswith("--regexp=") for a in args):
        kept, skip = [], False
        for a in args:
            if skip:
                skip = False
                continue
            if a in ("-e", "--regexp"):
                skip = True
                continue
            kept.append(a)
        return kept
    kept, dropped = [], False
    for a in args:
        if not dropped and not a.startswith("-"):
            dropped = True
            continue
        kept.append(a)
    return kept


def git_command(args, policy):
    rest = list(args)
    while rest and rest[0].startswith("-"):
        flag = rest.pop(0)
        if flag in ("-C", "-c") and rest:
            rest.pop(0)
    if not rest:
        return
    sub, opts = rest[0], rest[1:]
    if sub == "push":
        if policy.block_push:
            raise Blocked("pushing", "stop and report that the work is ready")
        if any(o in ("--force", "-f", "--force-with-lease", "--force-if-includes") or o.startswith(("--force-with-lease=", "+"))
               or re.match(r"^-[a-zA-Z]*f", o) for o in opts):
            raise Blocked("force-pushing", "push normally and ask a person if history must be rewritten")
        return
    if sub == "reset" and "--hard" in opts:
        raise Blocked("git reset --hard", "use git stash or a new commit")
    if sub == "clean" and any(o == "--force" or re.match(r"^-[a-zA-Z]*f", o) for o in opts):
        raise Blocked("git clean -f", "list untracked files with git status and ask")
    if sub == "commit" and any(o in ("--no-verify", "-n") for o in opts):
        raise Blocked("skipping commit hooks", "fix what the hook reports")
    if policy.repo_rules:
        if sub in ("checkout", "restore") and "." in opts:
            raise Blocked("discarding all working-tree changes", "restore specific files you changed")
        if sub == "branch" and any(o == "-D" or (o.startswith("-") and not o.startswith("--") and "D" in o) for o in opts):
            raise Blocked("force-deleting a branch", "ask a person")
        if sub in ("filter-branch", "filter-repo"):
            raise Blocked("rewriting history", "ask a person")
    if sub in GIT_NAME_ONLY:
        return
    if sub == "diff" and any(o in GIT_DIFF_SUMMARY for o in opts):
        return
    for opt in opts:
        if names_secret(opt):
            raise Blocked(f"git {sub} on a secrets file ({opt})", INSTEAD_SECRET)


class Policy:
    def __init__(self, block_push=False, repo_rules=False, protected=None,
                 protected_write_reason="writing protected data directly",
                 protected_change_reason="changing protected data directly",
                 protected_instead="ask a person"):
        self.protected_write_reason = protected_write_reason
        self.protected_change_reason = protected_change_reason
        self.protected_instead = protected_instead
        self.block_push = block_push
        self.repo_rules = repo_rules
        self._protected = protected
        self.protected_dirs = protected is not None

    def protected(self, path):
        return bool(self._protected and self._protected(path))


def check_command(command, policy):
    analyse(command, policy)
