from fastapi_rfc9457.models import PROBLEM_MEDIA_TYPE, ProblemDetail


def test_media_type_constant():
    assert PROBLEM_MEDIA_TYPE == "application/problem+json"


def test_defaults_and_required_fields():
    pd = ProblemDetail(title="Not Found", status=404)
    assert pd.type == "about:blank"
    assert pd.detail is None
    assert pd.instance is None


def test_exclude_none_drops_unset_standard_members():
    pd = ProblemDetail(title="Not Found", status=404)
    assert (
        pd.model_dump_json(exclude_none=True)
        == '{"type":"about:blank","title":"Not Found","status":404}'
    )


def test_extension_members_carried_on_the_wire():
    pd = ProblemDetail(title="Out of Credit", status=403, balance=30, accounts=["/acct/12"])
    dumped = pd.model_dump(exclude_none=True)
    assert dumped["balance"] == 30
    assert dumped["accounts"] == ["/acct/12"]
