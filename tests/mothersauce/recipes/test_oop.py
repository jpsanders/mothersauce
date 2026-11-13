from datetime import time

import pytest

from mothersauce.recipes.oop import Bounded, Fridge, Kitchen, Order, Shift, demo


def test_descriptor_validates_each_attribute_by_name() -> None:
    fridge = Fridge("walk in", 3, 100)
    with pytest.raises(ValueError, match="celsius must be -30 to 15, got 16"):
        fridge.celsius = 16
    with pytest.raises(ValueError, match="litres must be 1 to 5000, got 0"):
        Fridge("tiny", 3, 0)
    fridge.celsius = -2
    assert fridge.celsius == -2


def test_descriptor_on_the_class_returns_itself() -> None:
    assert isinstance(Fridge.celsius, Bounded)
    assert (Fridge.celsius.low, Fridge.celsius.high) == (-30, 15)


def test_slots_forbid_new_attributes() -> None:
    fridge = Fridge("walk in", 3, 100)
    assert not hasattr(fridge, "__dict__")
    with pytest.raises(AttributeError):
        fridge.colour = "white"  # type: ignore[attr-defined]


@pytest.mark.parametrize(("celsius", "safe"), [(5, True), (5.1, False), (-18, True)])
def test_computed_property(celsius: float, safe: bool) -> None:
    assert Fridge("f", celsius, 10).is_safe is safe


def test_shift_ordering_and_equality() -> None:
    early, late = Shift.from_text("07:00-15:00"), Shift.from_text(" 18:00 - 23:30 ")
    assert early < late and late > early and early <= Shift.from_text("07:00-15:00")
    assert early == Shift(time(7), time(15)) and early != late
    assert len({early, Shift.from_text("07:00-15:00")}) == 1
    assert early.__eq__("07:00-15:00") is NotImplemented


def test_shift_minutes_and_validation() -> None:
    assert Shift.from_text("18:00-23:30").minutes == 330
    assert Shift.minutes_between(time(9), time(10, 15)) == 75
    with pytest.raises(ValueError, match="end after it starts"):
        Shift.from_text("15:00-07:00")


def test_order_behaves_like_a_collection() -> None:
    order = Order("sole")
    order.add("tart")
    assert len(order) == 2 and list(order) == ["sole", "tart"] and order[1] == "tart"
    assert "sole" in order and "soup" not in order
    assert order + Order("soup") == Order("sole", "tart", "soup")
    assert not Order() and bool(order)
    assert repr(order) == "Order('sole', 'tart')"


def test_mutable_order_is_not_hashable() -> None:
    with pytest.raises(TypeError, match="unhashable"):
        {Order("sole")}


def test_kitchen_composes_and_queues_fifo() -> None:
    kitchen = Kitchen([Fridge("walk in", 3, 100)])
    assert kitchen.accept(Order("a")) and kitchen.accept(Order("b"))
    assert not kitchen.accept(Order())
    assert kitchen.next_order() == Order("a")
    assert kitchen.next_order() == Order("b")
    assert kitchen.next_order() is None


def test_kitchen_refuses_orders_when_a_fridge_is_warm() -> None:
    kitchen = Kitchen([Fridge("walk in", 3, 100), Fridge("pastry", 9, 50)])
    assert not kitchen.accept(Order("tart"))


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "descriptor caught it: celsius must be -30 to 15, got 40" in out
    assert "with __slots__" in out
