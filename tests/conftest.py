import pytest

from gridease.calc.engineering import run_all
from gridease.core.model import Project, Source, SourceKind
from gridease.intake.extract import RuleExtractor, apply_extraction

BRIEF = ("Ausgrid area cold store, rooftop PV 800 kWp, 3 x SMA STP 110-60 and 2 x Sungrow SG250HX, "
         "battery 2 x Sungrow SC125HV totalling 500 kWh, low voltage 400 V, max demand 600 kVA, "
         "export limit 150 kW, NMI 4103123456")


def user(p: Project, key, value, unit=None):
    return p.set_param(key, value, Source(kind=SourceKind.USER_INPUT, ref="test"), unit=unit)


@pytest.fixture
def project() -> Project:
    p = Project(name="Test cold store")
    apply_extraction(p, RuleExtractor().extract(BRIEF))
    user(p, "site.customer", "Demo Cold Storage Pty Ltd")
    user(p, "site.address", "1 Example Rd, Smithfield NSW")
    user(p, "contractor.licence_no", "EC12345")
    user(p, "load.profile_kw", [150] * 6 + [250] * 3 + [400] * 8 + [300] * 4 + [200] * 3)
    user(p, "tariff.import_peak_c_per_kwh", 35)
    user(p, "tariff.import_offpeak_c_per_kwh", 18)
    user(p, "tariff.export_c_per_kwh", 5)
    run_all(p)
    return p
