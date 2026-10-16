"""Conservative shell AST inspection and shell-free, cwd-locked execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import re
import shutil
import subprocess

import bashlex

from .extractor import normalize


@dataclass
class CommandAnalysis:
    commands: list[list[str]] = field(default_factory=list)
    has_pipeline: bool = False
    has_substitution: bool = False
    has_chain: bool = False
    has_redirection: bool = False
    opaque: bool = False
    parse_error: bool = False


def analyze_command(command: str) -> CommandAnalysis:
    result = CommandAnalysis()
    try:
        trees = bashlex.parse(command)
    except (bashlex.errors.ParsingError, NotImplementedError, ValueError, TypeError):
        result.parse_error = True
        return result
    def visit(node):
        kind = node.kind
        if kind == "pipeline":
            result.has_pipeline = True
        elif kind in {"commandsubstitution", "processsubstitution"}:
            result.has_substitution = True
        elif kind == "operator" and getattr(node, "op", "") in {";", "&&", "||", "&", "\n"}:
            result.has_chain = True
        elif kind == "redirect":
            result.has_redirection = True
        elif kind in {"parameter", "for", "while", "until", "function", "if", "compound"}:
            result.opaque = True
        elif kind == "command":
            words = [part.word for part in node.parts if part.kind == "word"]
            if words:
                result.commands.append(words)
        for value in vars(node).values():
            if isinstance(value, bashlex.ast.node):
                visit(value)
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, bashlex.ast.node):
                        visit(child)
    for tree in trees:
        visit(tree)
    if len(trees) > 1:
        result.has_chain = True
    return result


def command_name(word: str) -> str:
    return word.replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")


def git_subcommand(argv: list[str]) -> str | None:
    if not argv or command_name(argv[0]) != "git":
        return None
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg in {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}:
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            return arg.casefold()
    return None


def exec_violation(command: str, rule: dict, *, readonly=False) -> str | None:
    if not command.strip() or len(command) > 65536:
        return "命令为空或超出审计长度限制"
    normalized, _ = normalize(command)
    original = analyze_command(command)
    detection = analyze_command(normalized.split("\n[base64] ")[0])
    words = [word.casefold() for argv in original.commands + detection.commands for word in argv]
    names = {command_name(argv[0]) for argv in original.commands + detection.commands if argv}
    low = normalized.casefold()
    if readonly and any(git_subcommand(argv) in {"push", "commit"}
                        for argv in original.commands + detection.commands):
        return "只读代码检视任务禁止通过 exec 执行 git.push/git.commit"
    for argv in original.commands + detection.commands:
        if argv and command_name(argv[0]) == "git":
            subcommand = git_subcommand(argv)
            if subcommand not in {"status", "diff", "log", "show", "rev-parse", "ls-files"}:
                return "exec 中 git 仅允许读取子命令；其他动作必须使用受审计的显式工具"
            if any(a == "-c" or a.startswith(("--config-env", "--exec-path", "--ext-diff", "--textconv")) for a in argv[1:]):
                return "exec 中 git 包含外部执行或配置覆盖选项"
    if original.has_substitution or detection.has_substitution or "$(" in low or "`" in command:
        return "命令 AST 包含命令替换或进程替换"
    downloads = set(rule["download_commands"])
    executors = set(rule["execution_commands"])
    if names & downloads and (names & executors or original.has_pipeline or original.has_chain):
        return "命令 AST 包含远程下载后执行或下载管道执行链"
    if ("base64" in low or "frombase64string" in low or "b64decode" in low) and (
        names & executors or any(word in words for word in ("-d", "--decode")) or "exec" in low or "eval" in low
    ):
        return "命令 AST 包含 Base64 解码执行链"
    # Interpreter/eval wrappers hide a second language and would bypass all other rules.
    if names & (executors | {"eval", "exec", "source", ".", "env", "sudo", "nohup", "xargs", "find", "tee"}):
        return "命令含解释器、间接执行或不透明包装器，无法安全核验"
    if original.has_chain or detection.has_chain or ";" in low or "&&" in low or "||" in low:
        return "命令 AST 包含链式或后台执行"
    if original.has_redirection or detection.has_redirection:
        return "命令 AST 包含文件重定向，必须使用受审计的 fs.write"
    if original.opaque or detection.opaque or original.parse_error or detection.parse_error:
        return "命令语法无法完整审计，已按保守策略阻断"
    return None


class SafeExecutor:
    """Not an OS sandbox. Run approved argv directly; never evaluate a shell string.

    Only configured executables can run. Callers must still enforce decide()
    before execution; cwd locking does not itself restrict filesystem access.
    """
    def __init__(self, execution_root: Path, blocked_markers=None, allowed_executables=None):
        self.cwd = execution_root.resolve(strict=True)
        self.markers = tuple(blocked_markers or ["API_KEY", "SECRET", "TOKEN", "SSH_AUTH_SOCK"])
        self.allowed = allowed_executables or {"git", "rg"}

    def environment(self, source=None):
        # Allowlist also removes BASH_ENV, PYTHONPATH, LD_PRELOAD, git config hooks, etc.
        source = os.environ if source is None else source
        keys = {"SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "LANG", "LC_ALL"}
        env = {k: v for k, v in source.items() if k.upper() in keys and not any(m in k.upper() for m in self.markers)}
        env["PATH"] = os.defpath
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        return env

    def run(self, argv: list[str], *, timeout: float = 10, cwd: Path | None = None):
        if cwd is not None and Path(cwd).resolve() != self.cwd:
            raise ValueError("cwd is locked to execution_root")
        if not argv or any(not isinstance(a, str) or "\x00" in a for a in argv):
            raise ValueError("explicit argv required")
        if any(separator in argv[0] for separator in ("/", "\\", ":")):
            raise ValueError("executable paths cannot be supplied by an action")
        name = command_name(argv[0])
        if name not in self.allowed:
            raise ValueError("executable is not allowlisted")
        if name == "git" and (len(argv) < 2 or argv[1] not in {"status", "diff", "log", "show", "rev-parse", "ls-files"}):
            raise ValueError("safe wrapper only permits read-only git subcommands")
        if name == "git" and any(a.startswith(("--exec-path", "--upload-pack", "--config-env", "--ext-diff", "--textconv")) or a == "--output" or a.startswith("--output=") for a in argv[2:]):
            raise ValueError("unsafe git option")
        if name == "rg" and any(a.startswith(("--pre", "--hostname-bin")) for a in argv[1:]):
            raise ValueError("unsafe rg execution option")
        executable = shutil.which(argv[0])
        if not executable:
            raise FileNotFoundError(argv[0])
        # Canonical absolute executable selected before giving child a minimal PATH.
        arguments = argv[1:]
        if name == "git":
            arguments = ["--no-pager", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=" + os.devnull,
                         "-c", "diff.external=", *arguments]
            if argv[1] in {"diff", "show", "log"}:
                arguments += ["--no-ext-diff", "--no-textconv"]
        return subprocess.run([str(Path(executable).resolve()), *arguments], cwd=self.cwd,
                              env=self.environment(), shell=False, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, check=False)
