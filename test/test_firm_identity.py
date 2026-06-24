import uuid

from app.models.firm_alias import FIRM_ALIAS_TYPES, FirmAlias
from app.services.firm_identity import canonical_domain


def test_canonical_domain_normalizes_urls_and_subdomains():
    assert canonical_domain("https://www.SmithLaw.com/x?utm=1") == "smithlaw.com"
    assert canonical_domain("mail.smithlaw.co.uk") == "smithlaw.co.uk"
    assert canonical_domain("Jane@Sub.SmithLaw.com") == "smithlaw.com"


def test_canonical_domain_returns_no_key_for_vanity_and_consumer_domains():
    assert canonical_domain("a@smithlaw.filevineapp.com") is None
    assert canonical_domain("https://portal.casepeer.com/matter/1") is None
    assert canonical_domain("https://firm.smartadvocate.com") is None
    assert canonical_domain("b@gmail.com") is None


def test_firm_alias_model_contract():
    assert set(FIRM_ALIAS_TYPES) == {
        "legacy_pif_id",
        "domain",
        "alt_domain",
        "email_domain",
        "vanity_domain",
        "firm_name_fuzzy",
    }

    alias = FirmAlias(
        alias_type="domain",
        alias_value="smithlaw.com",
        firm_id=uuid.uuid4(),
        confidence=0.95,
        source="test",
    )
    assert alias.alias_value == "smithlaw.com"
    assert alias.confidence == 0.95
