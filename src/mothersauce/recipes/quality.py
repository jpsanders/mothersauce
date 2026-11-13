"""
Data quality: rules as data, results you can count, and overrides with an audit trail.

A load that quietly accepts bad rows is worse than one that fails. Write each check as a small named rule, register it
once, and run every rule over every record, collecting findings instead of stopping at the first. Each rule carries a
severity: an error quarantines the record, a warning lets it through and reports it.

Real data has known exceptions, such as a staff meal priced at zero. Overrides make them explicit: which record,
which rule, who approved it, why, and until when. They are applied in one place and listed in the report, instead
of an ``if`` hidden inside a rule where nobody will find it again.

A rule that crashes on bad input must not crash the run: an exception inside a check counts as a failed check.
"""

from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from mothersauce.recipes.enums import Severity, Station

__all__ = ["RULES", "Finding", "Override", "Report", "Rule", "check_batch", "demo", "rule"]

type Record = Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Rule:
    """
    One named check.

    :param name: How reports and overrides refer to it
    :param severity: ``ERROR`` quarantines the record; ``WARNING`` only reports it
    :param message: What a failure means, for people
    :param check: Returns True when the record passes
    """

    name: str
    severity: Severity
    message: str
    check: Callable[[Record], bool]


RULES: dict[str, Rule] = {}


def rule(name: str, severity: Severity, message: str) -> Callable[[Callable[[Record], bool]], Callable[[Record], bool]]:
    """
    Register a check function as a rule.

    :param name: The rule's name
    :param severity: How bad a failure is
    :param message: What a failure means
    :returns: A decorator that registers the function and returns it unchanged
    """

    def register(check: Callable[[Record], bool]) -> Callable[[Record], bool]:
        if name in RULES:
            raise ValueError(f"rule {name!r} is already registered")
        RULES[name] = Rule(name, severity, message, check)
        return check

    return register


@rule("dish_present", Severity.ERROR, "the dish is missing")
def _dish_present(record: Record) -> bool:
    return bool(record.get("dish", "").strip())


@rule("quantity_positive", Severity.ERROR, "the quantity must be a whole number above zero")
def _quantity_positive(record: Record) -> bool:
    return int(record["quantity"]) > 0


@rule("price_not_negative", Severity.ERROR, "the price must be zero or more")
def _price_not_negative(record: Record) -> bool:
    return Decimal(record["unit_price"]) >= 0


@rule("price_not_zero", Severity.ERROR, "a zero price needs an override, such as a staff meal")
def _price_not_zero(record: Record) -> bool:
    return Decimal(record["unit_price"]) != 0


@rule("known_station", Severity.ERROR, "the station is not one of the kitchen's stations")
def _known_station(record: Record) -> bool:
    return record.get("station", "") in set(Station)


@rule("large_quantity", Severity.WARNING, "more than 20 of one dish; check it is not a typo")
def _large_quantity(record: Record) -> bool:
    return int(record["quantity"]) <= 20


@dataclass(frozen=True, slots=True)
class Override:
    """
    An approved exception to one rule for one record.

    :param record_id: The record it applies to
    :param rule: The rule it waives
    :param approved_by: Who approved it
    :param reason: Why
    :param expires: The last day it applies; None for no end
    """

    record_id: str
    rule: str
    approved_by: str
    reason: str
    expires: date | None = None

    def active(self, today: date) -> bool:
        """
        Whether the override still applies.

        :param today: The day of the check
        :returns: True until the expiry date has passed
        """
        return self.expires is None or today <= self.expires


@dataclass(frozen=True, slots=True)
class Finding:
    """
    One failed check on one record.

    :param record_id: Which record
    :param rule: Which rule
    :param severity: The rule's severity
    :param message: What it means
    :param waived_by: The override that waived it, if any
    """

    record_id: str
    rule: str
    severity: Severity
    message: str
    waived_by: Override | None = None


@dataclass(slots=True)
class Report:
    """
    What a check of a batch found.

    :param accepted: Records with no unwaived error
    :param quarantined: Records held back for a person to look at
    :param findings: Every failed check, waived or not
    """

    accepted: list[Record] = field(default_factory=list)
    quarantined: list[Record] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def by_rule(self) -> Counter[str]:
        """
        Count the findings that were not waived, per rule.

        :returns: Rule names with counts, most frequent first
        """
        counts = Counter(f.rule for f in self.findings if f.waived_by is None)
        return Counter(dict(counts.most_common()))

    def waived(self) -> list[Finding]:
        """
        List the findings an override waived, for the audit trail.

        :returns: The waived findings
        """
        return [f for f in self.findings if f.waived_by is not None]


def _passes(check: Callable[[Record], bool], record: Record) -> bool:
    try:
        return check(record)
    except KeyError, ValueError, TypeError, InvalidOperation:
        return False  # the usual ways a value is missing or malformed
    except Exception:  # a bug in a rule fails the check; it must not stop the run for every other record
        return False


def check_batch(
    records: Iterable[Record],
    *,
    rules: Mapping[str, Rule] = RULES,
    overrides: Sequence[Override] = (),
    key: str = "line_id",
    today: date | None = None,
) -> Report:
    """
    Run every rule on every record, apply the overrides, and split accepted from quarantined.

    Duplicate keys are a batch level check: the first record with a key is checked, every later one is quarantined.

    :param records: The batch
    :param rules: The rules to run
    :param overrides: Approved exceptions
    :param key: The field that identifies a record
    :param today: The day overrides are checked against; today when omitted
    :returns: The report
    """
    day = today or date.today()
    waivers = {(o.record_id, o.rule): o for o in overrides if o.active(day)}
    report = Report()
    seen: set[str] = set()
    for record in records:
        record_id = record.get(key, "")
        found = [
            Finding(record_id, r.name, r.severity, r.message, waivers.get((record_id, r.name)))
            for r in rules.values()
            if not _passes(r.check, record)
        ]
        if record_id in seen:
            found.append(Finding(record_id, "unique_key", Severity.ERROR, f"{key} {record_id!r} appears twice"))
        seen.add(record_id)
        report.findings.extend(found)
        blocking = any(f.severity >= Severity.ERROR and f.waived_by is None for f in found)
        (report.quarantined if blocking else report.accepted).append(record)
    return report


def demo() -> None:
    """Check a small batch with a duplicate, bad values, a warning and an approved staff meal."""
    batch: list[Record] = [
        {"line_id": "L1", "dish": "sole", "station": "grill", "quantity": "2", "unit_price": "31.50"},
        {"line_id": "L2", "dish": "tart", "station": "pastry", "quantity": "24", "unit_price": "9.00"},
        {"line_id": "L3", "dish": "soup", "station": "bar", "quantity": "1", "unit_price": "7.00"},
        {"line_id": "L4", "dish": "frites", "station": "fry", "quantity": "-1", "unit_price": "-5"},
        {"line_id": "L5", "dish": "staff meal", "station": "sauce", "quantity": "6", "unit_price": "0"},
        {"line_id": "L1", "dish": "sole", "station": "grill", "quantity": "2", "unit_price": "31.50"},
    ]
    staff_meal = Override("L5", "price_not_zero", "head chef", "family meal before service", date(2026, 12, 31))
    report = check_batch(batch, overrides=[staff_meal], today=date(2026, 11, 12))
    print(
        f"accepted {[r['line_id'] for r in report.accepted]}, quarantined {[r['line_id'] for r in report.quarantined]}"
    )
    print(f"findings by rule: {dict(report.by_rule())}")
    for finding in report.waived():
        if override := finding.waived_by:
            print(f"waived: {finding.record_id} {finding.rule}, by {override.approved_by} ({override.reason})")
