"""Tests for the JSON-string parsing helpers behind the new sensors.

Pure-function tests only: the helpers take raw Device.setStatus values
(documents arrive JSON-encoded inside the string value) and must tolerate
every malformed shape installs can produce without raising.
"""

import json

from custom_components.poolside.const import (
    ACID_MIX_EVENT_FIELD,
    ENERGY_NATURAL_GAS_KEY,
    ENERGY_WATTS_KEY,
    LAST_MINUTE_OF_ENERGY_CONSUMPTION_FIELD,
    ON_UNTIL_FIELD,
)
from custom_components.poolside.sensor import (
    _datetime_value,
    _dose_amount,
    _dose_extra_attributes,
    _energy_document,
    _energy_total_reported,
    _json_document,
    _water_quality_value,
)

# A real dose event captured from a controller's Device.setStatus push, as
# it arrives on the wire: the document JSON-encoded inside the string value.
REAL_DOSE_EVENT = {
    "UUID": "9d5365d1-d267-49f2-afa4-a44a09bd7943",
    "StartDateTime": "2026-08-31T13:58:16.8837444-05:00",
    "EndDateTime": "2026-08-31T14:24:24.8837657-05:00",
    "DoseSeconds": 68,
    "DoseAmount": 5.0,
    "DosingUnit": "OZ",
    "MixMinutes": 25,
    "ChemicalType": "CHLORINE",
    "ChemicalPumpUUID": "Universal-Chemical-Pump",
    "InterruptedAt": None,
    "Before": 597.0,
    "After": None,
    "IgnoreBadEvent": False,
    "PumpMinimumPowerLevelWhileMixing": 25,
    "PumpMinimumPowerLevelWhileDosing": 100,
    "ManuallyInitiatedEvent": False,
    "DosingCutShort": False,
}


class StubClient:
    """Minimal get_status double: one key -> one raw value."""

    def __init__(self, status: dict[str, dict]) -> None:
        """Store the raw status by (uuid, field)."""
        self._status = status

    def get_status(self, uuid: str, field: str):
        """Return the raw value pushed for (uuid, field)."""
        return self._status.get(uuid, {}).get(field)


def _encoded(value) -> str:
    """Encode a document the way the wire does: JSON inside the string."""
    return json.dumps(value)


BODY = "fb773a00-3b89-41d6-ac73-37d4b87a6203"


def test_dose_event_json_string_parses():
    """A double-encoded dose event yields its amount and attributes."""
    client = StubClient({BODY: {ACID_MIX_EVENT_FIELD: _encoded(REAL_DOSE_EVENT)}})
    document = _json_document(
        BODY, ACID_MIX_EVENT_FIELD, client.get_status(BODY, ACID_MIX_EVENT_FIELD)
    )
    assert _dose_amount(document) == 5.0
    attributes = _dose_extra_attributes(document)
    assert attributes["duration_seconds"] == 68
    assert attributes["started"] == REAL_DOSE_EVENT["StartDateTime"]
    assert attributes["ended"] == REAL_DOSE_EVENT["EndDateTime"]
    assert attributes["mix_minutes"] == 25
    assert attributes["probe_before"] == 597.0
    assert attributes["unit"] == "OZ"
    # InterruptedAt is null in the payload and is omitted, not forced in.
    assert "interrupted" not in attributes


def test_dose_event_null_and_malformed():
    """Null (no dose information) and junk render as no data, not an error."""
    assert _json_document(BODY, ACID_MIX_EVENT_FIELD, None) is None
    assert _dose_amount(None) is None
    assert _dose_extra_attributes(None) == {}
    assert _json_document(BODY, ACID_MIX_EVENT_FIELD, "not json{") is None
    assert _json_document(BODY, ACID_MIX_EVENT_FIELD, '"just a string"') is None
    # Empty string is a common null-ish push and must not parse as a document.
    assert _json_document(BODY, ACID_MIX_EVENT_FIELD, "") is None


def test_energy_document_json_string_parses():
    """A double-encoded energy document yields both totals."""
    energy = {
        ENERGY_WATTS_KEY: 1250.0,
        ENERGY_NATURAL_GAS_KEY: 42000.0,
        "TotalLiquidPropaneBtuUsed": 0.0,
    }
    client = StubClient(
        {BODY: {LAST_MINUTE_OF_ENERGY_CONSUMPTION_FIELD: _encoded(energy)}}
    )
    document = _energy_document(client, BODY)
    assert document is not None
    assert document[ENERGY_WATTS_KEY] == 1250.0
    assert document[ENERGY_NATURAL_GAS_KEY] == 42000.0
    assert document["TotalLiquidPropaneBtuUsed"] == 0.0


def test_energy_document_null_safe():
    """Absent and malformed energy items render as no data."""
    assert _energy_document(StubClient({}), BODY) is None
    assert _energy_document(StubClient({BODY: {}}), BODY) is None
    assert _energy_document(
        StubClient({BODY: {LAST_MINUTE_OF_ENERGY_CONSUMPTION_FIELD: None}}), BODY
    ) is None
    assert _energy_document(
        StubClient(
            {BODY: {LAST_MINUTE_OF_ENERGY_CONSUMPTION_FIELD: "junk"}}
        ),
        BODY,
    ) is None


def test_on_until_parses_datetime():
    """OnUntil parses an ISO datetime, tolerating double-JSON quoting."""
    parsed = _datetime_value("2026-10-21T19:00:00-05:00")
    assert parsed is not None
    assert parsed.tzinfo is not None
    # The wire shape: the datetime JSON-encoded inside the string value.
    parsed = _datetime_value('"2026-10-21T19:00:00-05:00"')
    assert parsed is not None
    assert parsed.isoformat().startswith("2026-10-21T19:00:00")
    assert _datetime_value(None) is None


def test_water_quality_value_tolerant():
    """Known values map to their options; anything else is no data."""
    assert _water_quality_value("GOOD") == "good"
    assert _water_quality_value("ok") == "ok"
    assert _water_quality_value(" LOW ") == "low"
    assert _water_quality_value("ALERT") == "alert"
    assert _water_quality_value("NONE") == "none"
    assert _water_quality_value(None) is None
    assert _water_quality_value("SOMETHING_NEW") is None