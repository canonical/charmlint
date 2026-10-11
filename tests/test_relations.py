"""Tests for relation databag rules."""

import pathlib

import pytest

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


def _hits(charm_dir: pathlib.Path, rule_id: str) -> list:
    return [d for d in lint(charm_dir) if d.rule_id == rule_id]


def _charm(charm_dir: pathlib.Path, body: str) -> None:
    write_charmcraft_yaml(charm_dir, {"name": "x"})
    write_charm_source(
        charm_dir,
        f"import datetime\nimport glob\nimport json\n"
        f"import secrets\nimport time\nimport uuid\n\n\n"
        f"def publish(self, relation, payload, names):\n{body}",
    )


class TestUnorderedValueInDatabag:
    """Tests for RELATIONS-003 — unordered collection into a databag."""

    def test_set_through_json_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["u"] = json.dumps(list(set(names)))\n')
        hits = _hits(tmp_charm, "RELATIONS-003")
        assert len(hits) == 1
        assert hits[0].severity == Severity.WARNING

    def test_set_comprehension_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["u"] = ",".join({n for n in names})\n')
        assert len(_hits(tmp_charm, "RELATIONS-003")) == 1

    def test_glob_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["f"] = ",".join(glob.glob("/x/*"))\n')
        assert len(_hits(tmp_charm, "RELATIONS-003")) == 1

    def test_update_call_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app].update({"u": str(set(names))})\n')
        assert len(_hits(tmp_charm, "RELATIONS-003")) == 1

    def test_sorted_not_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["u"] = json.dumps(sorted(set(names)))\n')
        assert not _hits(tmp_charm, "RELATIONS-003")

    def test_set_outside_a_databag_not_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    payload["u"] = json.dumps(list(set(names)))\n')
        assert not _hits(tmp_charm, "RELATIONS-003")

    def test_opaque_call_not_followed(self, tmp_charm: pathlib.Path):
        # ``self.render`` might sort what it is given; charmlint cannot
        # see the body, so its arguments are not reached.
        _charm(tmp_charm, '    relation.data[self.app]["u"] = self.render(set(names))\n')
        assert not _hits(tmp_charm, "RELATIONS-003")

    @pytest.mark.parametrize(
        "value",
        [
            '",".join(str(n) for n in set(names))',
            "json.dumps([n for n in set(names)])",
            "json.dumps({n: 1 for n in set(names)})",
            '",".join(str(p) for p in pathlib.Path("/x").iterdir())',
        ],
    )
    def test_iterating_over_an_unordered_value_flagged(self, tmp_charm: pathlib.Path, value: str):
        _charm(tmp_charm, f'    relation.data[self.app]["u"] = {value}\n')
        assert len(_hits(tmp_charm, "RELATIONS-003")) == 1

    @pytest.mark.parametrize(
        "body",
        [
            '    relation.data[self.app]["u"] = json.dumps({"a": list(set(names))})\n',
            '    relation.data[self.app]["u"] = json.dumps([1, list(set(names))])\n',
            '    relation.data[self.app]["u"] = f"units={list(set(names))}"\n',
            '    relation.data[self.app]["u"] = "units:" + ",".join(set(names))\n',
            '    relation.data[self.app].update(u=",".join(set(names)))\n',
            '    relation.data[self.app]["u"]: str = ",".join(set(names))\n',
        ],
    )
    def test_carried_through_unchanged_flagged(self, tmp_charm: pathlib.Path, body: str):
        _charm(tmp_charm, body)
        assert len(_hits(tmp_charm, "RELATIONS-003")) == 1

    def test_sorted_iteration_not_flagged(self, tmp_charm: pathlib.Path):
        _charm(
            tmp_charm,
            '    relation.data[self.app]["u"] = ",".join(n for n in sorted(set(names)))\n',
        )
        assert not _hits(tmp_charm, "RELATIONS-003")

    @pytest.mark.parametrize(
        "body",
        [
            # What the rule can't see is left alone, not guessed at: a name,
            # or a name passed through a wrapper, could hold anything.
            '    relation.data[self.app]["u"] = names\n',
            '    relation.data[self.app]["u"] = list(names)\n',
            '    relation.data[self.app]["u"] = str(names)\n',
            # Names aren't followed, so a set bound to a local is missed.
            '    u = set(names)\n    relation.data[self.app]["u"] = ",".join(u)\n',
        ],
    )
    def test_unseen_values_not_flagged(self, tmp_charm: pathlib.Path, body: str):
        _charm(tmp_charm, body)
        assert not _hits(tmp_charm, "RELATIONS-003")


class TestDatabagAlias:
    """A databag bound to a local is still a databag."""

    def test_alias_write_flagged(self, tmp_charm: pathlib.Path):
        _charm(
            tmp_charm,
            '    bag = relation.data[self.app]\n    bag["u"] = json.dumps(list(set(names)))\n',
        )
        assert len(_hits(tmp_charm, "RELATIONS-003")) == 1

    def test_alias_update_flagged(self, tmp_charm: pathlib.Path):
        _charm(
            tmp_charm,
            '    bag = relation.data[self.app]\n    bag.update({"u": ",".join(set(names))})\n',
        )
        assert len(_hits(tmp_charm, "RELATIONS-003")) == 1

    def test_unrelated_local_not_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    bag = {}\n    bag["u"] = json.dumps(list(set(names)))\n')
        assert not _hits(tmp_charm, "RELATIONS-003")

    def test_data_keyed_by_a_literal_is_not_a_databag(self, tmp_charm: pathlib.Path):
        # ops keys relation data by a unit or app, so this is some other
        # client's data, and a local bound to it isn't a databag either.
        _charm(
            tmp_charm,
            '    resp = self.client.data["items"]\n'
            '    resp["u"] = ",".join(set(names))\n'
            '    self.client.data[0]["u"] = ",".join(set(names))\n',
        )
        assert not _hits(tmp_charm, "RELATIONS-003")


class TestRegression:
    """Shapes taken from the charms this rule was measured against."""

    def test_set_comprehension_joined_into_two_databags(self, tmp_charm: pathlib.Path):
        # postgresql-operator src/relations/db.py: rebuilding allowed_units
        # from a set comprehension, joined into both the unit and the app
        # databag. Set iteration order for strings varies per process, so
        # every hook rewrites the same units in a new order. One diagnostic,
        # not two: it's one offending expression, written twice.
        _charm(
            tmp_charm,
            "    local_unit_data = relation.data[self.unit]\n"
            "    local_app_data = relation.data[self.app]\n"
            '    local_app_data["allowed_units"] = local_unit_data["allowed_units"] = " ".join({\n'
            '        unit for unit in names.split() if unit != "x/0"\n'
            "    })\n",
        )
        assert len(_hits(tmp_charm, "RELATIONS-003")) == 1
