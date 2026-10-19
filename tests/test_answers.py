import pytest

from app.questionnaire.answers import AnswerError, to_facts
from app.questionnaire.models import Question


def Q(**kw):
    base = dict(id="q", domain="goals", text="?", fact_key="k")
    return Question(**{**base, **kw})


def test_multi_with_other():
    q = Q(type="multi", options=["a", "b"], allow_other=True)
    facts = to_facts(q, ["a", "autre"], "ski de fond")
    assert [(f.key, f.value) for f in facts] == [("k", ["a", "autre"]), ("k.other", "ski de fond")]


def test_other_requires_text_and_option_allowed():
    q = Q(type="multi", options=["a"], allow_other=True)
    with pytest.raises(AnswerError):
        to_facts(q, ["autre"])
    with pytest.raises(AnswerError):
        to_facts(Q(type="multi", options=["a"]), ["autre"], "x")


def test_single_validation():
    q = Q(type="single", options=["a", "b"])
    assert to_facts(q, "a")[0].value == "a"
    with pytest.raises(AnswerError):
        to_facts(q, "c")
    with pytest.raises(AnswerError):
        to_facts(q, ["a"])


def test_number_scale_date_text():
    assert to_facts(Q(type="number"), 12.5)[0].value == 12.5
    for bad in (-1, "12", True):
        with pytest.raises(AnswerError):
            to_facts(Q(type="number"), bad)
    with pytest.raises(AnswerError):
        to_facts(Q(type="scale"), 6)
    assert to_facts(Q(type="date"), "2027-03-01")[0].value == "2027-03-01"
    with pytest.raises(AnswerError):
        to_facts(Q(type="date"), "demain")
    assert to_facts(Q(type="text"), "  ok ")[0].value == "ok"


def test_entries():
    from app.questionnaire.models import EntryField

    q = Q(type="entries", fields=[
        EntryField(id="sport", label="Sport", type="single", options=["trail", "vélo"]),
        EntryField(id="from", label="Depuis", type="year"),
        EntryField(id="to", label="Jusqu'en", type="year", optional=True),
    ])
    ok = to_facts(q, [{"sport": "trail", "from": 2015}])
    assert ok[0].value == [{"sport": "trail", "from": 2015}]
    assert to_facts(q, [])[0].value == []  # « rien à signaler »
    for bad in ([{"sport": "golf", "from": 2015}], [{"sport": "trail"}],
                [{"sport": "trail", "from": 1800}],
                [{"sport": "trail", "from": 2015, "x": 1}], "x"):
        with pytest.raises(AnswerError):
            to_facts(q, bad)
