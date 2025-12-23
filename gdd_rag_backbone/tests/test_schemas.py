"""Tests for GDD schemas."""

from gdd_rag_backbone.gdd.schemas import GddMap, GddObject, TankSpec


def test_gdd_object_creation():
    obj = GddObject(
        id="obj_1",
        name="Barrel",
        category="BR",
        size_x=1.0,
        size_y=1.0,
        size_z=1.5,
        hp=100,
        destructible=True,
    )
    assert obj.id == "obj_1"
    assert obj.category == "BR"
    assert obj.name == "Barrel"
    assert obj.size_x == 1.0
    assert obj.destructible is True
    assert obj.to_dict()["id"] == "obj_1"


def test_tank_spec_creation():
    tank = TankSpec(
        id="tank_1",
        class_name="Heavy",
        name="Tiger Tank",
        hp=500,
        armor=100,
        speed=30.0,
    )
    assert tank.id == "tank_1"
    assert tank.class_name == "Heavy"
    assert tank.name == "Tiger Tank"
    assert tank.hp == 500
    assert tank.armor == 100


def test_map_spec_creation():
    gdd_map = GddMap(
        id="map_1",
        name="Desert Oasis",
        mode="CTF",
        scene="Desert",
        player_count=16,
    )
    assert gdd_map.id == "map_1"
    assert gdd_map.name == "Desert Oasis"
    assert gdd_map.mode == "CTF"
    assert gdd_map.player_count == 16


def test_schemas_import():
    from gdd_rag_backbone.gdd.schemas import GddMap, GddObject, TankSpec

    assert GddObject is not None
    assert TankSpec is not None
    assert GddMap is not None
