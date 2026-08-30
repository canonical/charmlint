"""Performance rules — avoidable runtime cost in the charm's Python source."""

import ast
import collections
from collections.abc import Sequence

from .. import _ast
from .. import _models as models
from ._base import Rule

# The number of reads of one key, on a single execution path through one
# function, that the rule tolerates. Two reads of the same option are how
# "look at it, then act on it" is often spelled; a third is where the
# repetition starts to read as an oversight.
_LIMIT = 2

_GET = "get"

# The spellings that reach a charm's config. ``self.config`` is what a charm
# writes and ``self.model.config`` the same mapping reached the long way; a
# library holds the charm it was constructed with and goes through that.
# Anything else named ``config`` — ``self._stored.config``, a parser's
# ``self.parser.config`` — is some other object, and the rule has no idea
# what reading it costs or whether the keys are config options at all.
_MAPPINGS = frozenset(
    {
        "self.config",
        "self.model.config",
        "self.charm.config",
        "self.charm.model.config",
        "self._charm.config",
        "self._charm.model.config",
    }
)

# One config read: which mapping it went through, and which option it asked
# for. The mapping is part of the identity because a library's
# ``self.charm.config`` and its own ``self.config`` need not be the same
# object, and merging them would invent reads that are not there.
_Access = tuple[str, str]
_Counts = collections.Counter[_Access]


def _config_mapping(node: ast.expr) -> str | None:
    """Return the spelling of the config mapping *node* names, else ``None``."""
    name = _ast.dotted_name(node)
    return name if name in _MAPPINGS else None


def _access(node: ast.AST) -> _Access | None:
    """Return the config read *node* performs, else ``None``.

    Both spellings count: ``self.config["k"]`` and ``self.config.get("k")``.
    A non-literal key (``self.config[name]``) is unresolvable, and guessing
    which reads share a key would be worse than not reporting.
    """
    if isinstance(node, ast.Subscript):
        # A store or a delete is not a read. Neither is legal on ops' config
        # mapping, but a plain dict named ``config`` allows both.
        if not isinstance(node.ctx, ast.Load):
            return None
        mapping = _config_mapping(node.value)
        key = _ast.dict_key(node.slice)
    elif isinstance(node, ast.Call):
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == _GET and node.args):
            return None
        mapping = _config_mapping(func.value)
        key = _ast.dict_key(node.args[0])
    else:
        return None
    return None if mapping is None or key is None else (mapping, key)


# Counting reads is not counting nodes. Two arms of an ``if`` are alternatives
# — at most one of them runs — so a key read once in each arm is read once,
# and summing the arms would report a repetition that cannot happen. Every
# helper below therefore returns the reads on the *worst single path* through
# the code it was given: ``+`` for things that run in sequence, ``|`` (which
# on a Counter is the element-wise maximum) for things that are alternatives.
#
# Loops are counted once rather than multiplied. A single read inside a loop
# body really does happen many times, but flagging one lexical access would
# be a different and much noisier rule; this one stays with what is written.


def _expression(node: ast.AST | None) -> _Counts:
    """Return the reads on the worst path through an expression."""
    counts: _Counts = collections.Counter()
    if node is None:
        return counts
    access = _access(node)
    if access is not None:
        counts[access] += 1
    if isinstance(node, ast.Lambda):
        # The body is a separate function. The argument defaults are not:
        # they are evaluated here, where the lambda is written.
        return counts + _expression(node.args)
    if isinstance(node, ast.IfExp):
        return (
            counts + _expression(node.test) + (_expression(node.body) | _expression(node.orelse))
        )
    for child in ast.iter_child_nodes(node):
        counts += _expression(child)
    return counts


def _body(body: Sequence[ast.stmt]) -> _Counts:
    """Return the reads on the worst path through a statement list.

    Walked backwards, so that when a branch is reached the reads of
    everything after it are already known: a branch that returns or raises
    never reaches them, and a guard clause is therefore an alternative to
    the rest of the function rather than a step on the way to it.
    """
    after: _Counts = collections.Counter()
    for statement in reversed(body):
        if isinstance(statement, ast.If):
            arms = _branch(statement.body, after) | _branch(statement.orelse, after)
            after = _expression(statement.test) + arms
        elif isinstance(statement, ast.Match):
            arms = collections.Counter()
            for case in statement.cases:
                arms |= _expression(case.guard) + _branch(case.body, after)
            if not _exhaustive(statement):
                # Nothing matched, so the statement did nothing and control
                # carried on into whatever follows it.
                arms |= after
            after = _expression(statement.subject) + arms
        else:
            counts = _statement(statement)
            after = counts + after if _falls_through([statement]) else counts
    return after


def _branch(branch: Sequence[ast.stmt], after: _Counts) -> _Counts:
    """Return the reads of one branch, plus what follows it if it gets there."""
    counts = _body(branch)
    return counts + after if _falls_through(branch) else counts


def _falls_through(body: Sequence[ast.stmt]) -> bool:
    """Whether control can reach the statement after *body*.

    An approximation in the direction of fewer findings: a ``try`` or a
    ``match`` is taken to fall through however its arms end, so the reads
    after it are counted as reachable from within it.
    """
    if not body:
        return True
    last = body[-1]
    if isinstance(last, ast.If):
        return _falls_through(last.body) or _falls_through(last.orelse)
    if isinstance(last, ast.With | ast.AsyncWith):
        return _falls_through(last.body)
    return not _ast.is_terminal(last)


def _exhaustive(statement: ast.Match) -> bool:
    """Whether *statement* has an unguarded catch-all case."""
    return any(
        case.guard is None
        and isinstance(case.pattern, ast.MatchAs)
        and case.pattern.pattern is None
        for case in statement.cases
    )


def _statement(statement: ast.stmt) -> _Counts:
    """Return the reads on the worst path through one statement.

    ``if`` and ``match`` are handled by :func:`_body`, which is the only
    place that knows what follows them.
    """
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        # The body belongs to another scope and does not run here. The
        # decorators, argument defaults and base classes do.
        return _definition_site(statement)
    if isinstance(statement, ast.Try | ast.TryStar):
        handled: _Counts = collections.Counter()
        for handler in statement.handlers:
            handled |= _expression(handler.type) + _body(handler.body)
        # Either the body ran to completion and ``else`` followed, or an
        # exception diverted it into a handler. ``finally`` runs either way.
        normal = _body(statement.body) + _body(statement.orelse)
        return (normal | handled) + _body(statement.finalbody)
    if isinstance(statement, ast.For | ast.AsyncFor):
        return (
            _expression(statement.target)
            + _expression(statement.iter)
            + _body(statement.body)
            + _body(statement.orelse)
        )
    if isinstance(statement, ast.While):
        return _expression(statement.test) + _body(statement.body) + _body(statement.orelse)
    if isinstance(statement, ast.With | ast.AsyncWith):
        counts: _Counts = collections.Counter()
        for item in statement.items:
            counts += _expression(item)
        return counts + _body(statement.body)
    return _expression(statement)


def _definition_site(statement: ast.stmt) -> _Counts:
    """Return the reads a nested definition performs where it is written."""
    counts: _Counts = collections.Counter()
    for decorator in getattr(statement, "decorator_list", []):
        counts += _expression(decorator)
    args = getattr(statement, "args", None)
    if isinstance(args, ast.arguments):
        counts += _expression(args)
    for base in getattr(statement, "bases", []):
        counts += _expression(base)
    for kwarg in getattr(statement, "keywords", []):
        counts += _expression(kwarg)
    return counts


def _function_counts(function: ast.FunctionDef | ast.AsyncFunctionDef) -> _Counts:
    """Return the config reads on the worst path through *function*'s own body.

    ``_ast.walk_statements`` reaches every statement including those of a
    nested ``def``, which is the wrong set here: a closure's body runs when
    the closure is called, not where it is written, so its reads are neither
    repetitions of the enclosing function's nor hoistable out of it. The
    recursion below stops at a nested definition instead.
    """
    return _body(function.body)


class RepeatedConfigAccess(Rule):
    """Detect the same config option being read several times in one function.

    ``self.config["x"]`` is a mapping lookup, so the cost of repeating it is
    small; the reason to hoist it is that the reader has to check each
    spelling to be sure they all name the same option, and a rename has to
    find every one of them. Reads that cannot both happen — one in each arm
    of an ``if`` — are not repetitions and are not counted as such.
    """

    category = "PERFORMANCE"
    number = 1
    name = "repeated-config-access"
    description = "Same config option read more than twice in one function"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            for function in module.functions():
                counts = _function_counts(function)
                for (mapping, key), count in sorted(counts.items()):
                    if count <= _LIMIT:
                        continue
                    diagnostics.append(
                        self.diagnostic(
                            f"config option '{key}' is read {count} times in "
                            f"'{function.name}' — read it once into a local",
                            path=module.path,
                            line=function.lineno,
                            fix_hint=f"{key.replace('-', '_')} = {mapping}['{key}']",
                        )
                    )
        return diagnostics
