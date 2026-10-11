"""Resolution of the tokens that name rules in config and in comments.

Everywhere a user names a rule — ``select`` / ``ignore`` /
``per-rule-severity`` in the config file, ``--select`` / ``--ignore`` on
the command line, and the codes inside a suppression comment — the same
three spellings are accepted:

- a full rule ID, ``SECURITY-001``;
- a rule name, ``secret-in-plain-config``;
- a category, ``SECURITY``, standing for every rule in it.

Names are ruff's "wordier" spelling: ``ignore = ["secret-in-plain-config"]``
says what is being turned off, where ``ignore = ["SECURITY-001"]`` has to
be looked up. Both work, and one token resolves to the same rules either
way, so a config can mix them.

Case is significant: IDs and categories are upper-case, names are
lower-case, and a token in the wrong case names nothing. A rule may not
take a name that spells a category, so a token never resolves two ways.
"""

from ._rules import CATEGORIES, get_all_rules


def resolve(token: str) -> frozenset[str]:
    """Return the rule IDs *token* names, or an empty set if it names none.

    An empty result means the token is not a known rule ID, rule name or
    category — a typo, or a rule that has been removed. Callers that
    validate user input report it; callers matching a suppression
    comment just never match.
    """
    token = token.strip()
    if not token:
        return frozenset()
    rules = get_all_rules()
    if token in rules:
        return frozenset({token})
    for rule_id, rule in rules.items():
        if rule.name == token:
            return frozenset({rule_id})
    if token in CATEGORIES:
        return frozenset(rule_id for rule_id, rule in rules.items() if rule.category == token)
    return frozenset()


def is_category(token: str) -> bool:
    """Whether *token* names a whole category rather than a single rule.

    A category is the less specific spelling, so it loses to a rule ID or
    a rule name when ``select`` and ``ignore`` disagree.
    """
    token = token.strip()
    return token in CATEGORIES and token not in get_all_rules()


def matches_rule(tokens: list[str], rule_id: str) -> bool:
    """Whether any of *tokens* names *rule_id* specifically, by ID or name.

    The specific spelling and the broad one are asked about separately so
    that the specific one can win when ``select`` and ``ignore`` disagree.
    """
    return any(rule_id in resolve(token) for token in tokens if not is_category(token))


def matches_category(tokens: list[str], rule_id: str) -> bool:
    """Whether any of *tokens* names a category that contains *rule_id*."""
    return any(rule_id in resolve(token) for token in tokens if is_category(token))
