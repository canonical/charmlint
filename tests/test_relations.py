"""Tests for relation databag rules."""

import pathlib

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


class TestNondeterministicValueInDatabag:
    """Tests for RELATIONS-004 — a fresh value into a databag."""

    def test_uuid_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["n"] = str(uuid.uuid4())\n')
        hits = _hits(tmp_charm, "RELATIONS-004")
        assert len(hits) == 1
        assert hits[0].severity == Severity.WARNING

    def test_timestamp_through_fstring_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["t"] = f"at {time.time()}"\n')
        assert len(_hits(tmp_charm, "RELATIONS-004")) == 1

    def test_datetime_now_flagged(self, tmp_charm: pathlib.Path):
        _charm(
            tmp_charm, '    relation.data[self.app]["t"] = datetime.datetime.now().isoformat()\n'
        )
        assert len(_hits(tmp_charm, "RELATIONS-004")) == 1

    def test_token_in_update_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app].update({"s": secrets.token_hex()})\n')
        assert len(_hits(tmp_charm, "RELATIONS-004")) == 1

    def test_stable_value_not_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["h"] = self.hostname\n')
        assert not _hits(tmp_charm, "RELATIONS-004")


class TestUnsortedJsonInDatabag:
    """Tests for RELATIONS-005 — json.dumps() without sort_keys."""

    def test_opaque_mapping_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["b"] = json.dumps(payload)\n')
        hits = _hits(tmp_charm, "RELATIONS-005")
        assert len(hits) == 1
        assert hits[0].severity == Severity.INFO

    def test_sort_keys_not_flagged(self, tmp_charm: pathlib.Path):
        _charm(
            tmp_charm, '    relation.data[self.app]["b"] = json.dumps(payload, sort_keys=True)\n'
        )
        assert not _hits(tmp_charm, "RELATIONS-005")

    def test_dict_literal_not_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["b"] = json.dumps({"a": 1})\n')
        assert not _hits(tmp_charm, "RELATIONS-005")

    def test_sequence_argument_not_flagged(self, tmp_charm: pathlib.Path):
        _charm(tmp_charm, '    relation.data[self.app]["b"] = json.dumps(sorted(names))\n')
        assert not _hits(tmp_charm, "RELATIONS-005")
