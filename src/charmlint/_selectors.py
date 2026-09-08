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

IDs and categories are matched case-insensitively, as they were before
names existed. Names are lower-case by construction; a rule may not take
a name that spells a category, so a token never resolves two ways.
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
    upper = token.upper()
    if upper in rules:
        return frozenset({upper})
    lower = token.lower()
    for rule_id, rule in rules.items():
        if rule.name == lower:
            return frozenset({rule_id})
    if upper in CATEGORIES:
        return frozenset(rule_id for rule_id, rule in rules.items() if rule.category == upper)
    return frozenset()


def is_known(token: str) -> bool:
    """Whether *token* names anything charmlint knows about.

    Wider than ``bool(resolve(token))``: a category with no rules yet,
    and a well-formed ID within a known category, are both accepted even
    though they match nothing today. Naming a rule that has not landed
    yet is a forward-looking choice, not a typo, and it starts matching
    the day the rule does land — whereas a misspelled category or name
    would silently never match, which is what this rejects.
    """
    token = token.strip()
    if resolve(token):
        return True
    upper = token.upper()
    if upper in CATEGORIES:
        return True
    category, _, number = upper.rpartition("-")
    return category in CATEGORIES and number.isdigit()


def is_category(token: str) -> bool:
    """Whether *token* names a whole category rather than a single rule.

    A category is the less specific spelling, so it loses to a rule ID or
    a rule name when ``select`` and ``ignore`` disagree.
    """
    token = token.strip()
    return token.upper() in CATEGORIES and token.upper() not in get_all_rules()


def matches(tokens: list[str], rule_id: str, *, categories: bool) -> bool:
    """Whether any of *tokens* names *rule_id*.

    *categories* selects which half of *tokens* to consider: the category
    tokens, or the ones naming a single rule. Callers ask twice so that
    the specific spelling can win over the broad one.
    """
    return any(rule_id in resolve(token) for token in tokens if is_category(token) is categories)
