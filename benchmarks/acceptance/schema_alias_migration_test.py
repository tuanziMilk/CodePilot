import pytest
from profiles_v2.codec_in import decode_profile
from profiles_v2.codec_out import encode_profile
from profiles_v2.errors import ProfileFormatError
from profiles_v2.service import normalize_record


def test_new_field_wins_and_input_is_unchanged():
    payload = {
        "id": "u-2", "name": "Legacy", "display_name": "Canonical",
        "active": False,
    }
    original = dict(payload)
    profile = decode_profile(payload)
    assert profile.display_name == "Canonical"
    assert profile.active is False
    assert payload == original


def test_normalization_never_recreates_legacy_alias():
    assert normalize_record({"id": "u-3", "name": "Grace"}) == {
        "id": "u-3", "display_name": "Grace", "active": True
    }
    assert "name" not in encode_profile(
        decode_profile({"id": "u-4", "display_name": "Lin"})
    )


@pytest.mark.parametrize("payload", [
    {}, {"id": "u-5"}, {"id": "u-5", "name": ""},
    {"id": "u-5", "display_name": ""},
])
def test_required_values_remain_enforced(payload):
    with pytest.raises(ProfileFormatError):
        decode_profile(payload)
