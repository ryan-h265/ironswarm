from ironswarm.lwwelementset import LWWElementSet


def test_lwwelementset_add():
    lww = LWWElementSet()
    lww.add("apple", timestamp=100, node="A")
    assert lww.lookup("apple") == {"timestamp": 100, "node": "A"}
    assert "apple" in lww.keys()


def test_lwwelementset_remove():
    lww = LWWElementSet()
    lww.add("apple", timestamp=100, node="A")
    lww.remove("apple", timestamp=200, node="B")
    assert not lww.lookup("apple")
    assert "apple" not in lww.keys()


def test_lwwelementset_merge():
    lww1 = LWWElementSet()
    lww2 = LWWElementSet()
    lww1.add("apple", timestamp=100, node="A")
    lww2.remove("apple", timestamp=200, node="B")
    lww1.merge(lww2)
    assert not lww1.lookup("apple")
    assert "apple" not in lww1.keys()


def test_lwwelementset_to_dict():
    lww = LWWElementSet()
    lww.add("apple", timestamp=100, node="A")
    lww.remove("banana", timestamp=200, node="B")
    result = lww.to_dict()
    assert result["add_set"]["apple"] == {"timestamp": 100, "node": "A"}
    assert result["remove_set"]["banana"] == {"timestamp": 200, "node": "B"}


def test_lwwelementset_from_dict():
    data = {
        "add_set": {"apple": {"timestamp": 100, "node": "A"}},
        "remove_set": {"banana": {"timestamp": 200, "node": "B"}},
    }
    lww = LWWElementSet.from_dict(data)
    assert lww.lookup("apple") == {"timestamp": 100, "node": "A"}
    assert not lww.lookup("banana")


def test_lwwelementset_keys():
    lww = LWWElementSet()
    lww.add("apple", timestamp=100)
    lww.add("banana", timestamp=200)
    lww.remove("banana", timestamp=300)
    assert lww.keys() == {"apple"}


def test_lwwelementset_values():
    lww = LWWElementSet()
    lww.add("apple", timestamp=100, node="A")
    lww.add("banana", timestamp=200, node="B")
    lww.remove("banana", timestamp=300)
    values = lww.values()
    assert ("apple", {"timestamp": 100, "node": "A"}) in values
    assert ("banana", {"timestamp": 200, "node": "B"}) not in values
