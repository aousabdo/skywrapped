import dataclasses
import math

import pytest

from skywrapped.targets import Target, display_name, group_targets, normalise_id

from helpers import fr


@pytest.mark.parametrize("raw,norm", [("M 8", "M8"), ("Messier 31", "M31"), ("NGC 7293", "NGC7293"),
    ("SH2-245_LExt", "SH2-245"), ("Sh2-136", "SH2-136"), ("SH2136", "SH2-136"), ("IC_434_LUlt", "IC434"),
    ("ldn1147_bare", "LDN1147"), ("vdB 152", "VDB152"), ("VdB152", "VDB152"), ("B33", "B33"),
    ("Lagoon Nebula", None), ("", None), ("my secret field", None), ("Sh 2-136", "SH2-136"),
    ("NGC0224", "NGC224"), ("Cr 399", "CR399"), ("Moon", None), ("M", None)])
def test_normalise_id(raw, norm):
    assert normalise_id(raw) == norm


def test_display_name():
    assert [display_name(i) for i in ["M8", "NGC7293", "SH2-136", "VDB152", "LDN1235", "B33"]] == \
           ["M 8", "NGC 7293", "Sh2-136", "vdB 152", "LDN 1235", "B 33"]


def test_two_pointings():
    fs = [fr(ra=270.9, dec=-24.38, fov=(3, 2)) for _ in range(10)] + [fr(ra=274.7, dec=-13.8, fov=(3, 2)) for _ in range(10)]
    assert sorted(t.key for t in group_targets(fs)) == ["M16", "M8"]


def test_mosaic_panels_merge():
    fs = [fr(ra=10.68 + dx, dec=41.27, fov=(2, 1.3), hint="M31") for dx in (-1.0, 0, 1.0) for _ in range(5)]
    ts = group_targets(fs)
    assert [t.key for t in ts] == ["M31"] and len(ts[0].frame_idx) == 15


def test_hint_wins_inside_field():
    assert group_targets([fr(ra=83.85, dec=-4.82, fov=(3, 2))])[0].key == "NGC1977"  # geometry alone
    assert group_targets([fr(ra=83.85, dec=-4.82, fov=(3, 2), hint="M 42")])[0].key == "M42"


def test_label_never_raw_hint():
    t = group_targets([fr(hint="my secret field")])[0]
    assert t.label == "Unnamed target" and "secret" not in t.label


def test_heart_nebula_key_label_common_name():
    t = group_targets([fr(ra=38.2, dec=61.45, fov=(3, 2), hint="whatever")])[0]
    assert (t.key, t.label, t.common_name) == ("IC1805", "IC 1805", "Heart Nebula")


def test_messier_key_and_common_name():
    t = group_targets([fr(ra=10.68, dec=41.27, fov=(4, 3))])[0]
    assert (t.key, t.label) == ("M31", "M 31") and "Andromeda" in t.common_name


def test_non_lights_ignored_and_indices_input_order():
    fs = [fr(ra=10.68, dec=41.27), fr(ra=10.68, dec=41.27, frame_type="dark"), fr(ra=10.68, dec=41.27)]
    ts = group_targets(fs)
    assert len(ts) == 1 and ts[0].frame_idx == [0, 2]


def test_time_order_not_input_order_but_idx_sorted():
    a = fr(ra=270.9, dec=-24.38)
    b = fr(ra=274.7, dec=-13.8)
    ts = group_targets([b, a])
    assert [t.key for t in ts] == ["M16", "M8"]  # input order of first frame


def test_no_coordinates_uses_hint():
    ts = group_targets([fr(hint="M31_Refractor"), fr(hint="Messier 31")])
    assert [t.key for t in ts] == ["M31"] and ts[0].ra is None and ts[0].frame_idx == [0, 1]


def test_no_match_label_is_coordinates():
    t = group_targets([fr(ra=85.25, dec=-2.2, fov=(0.2, 0.1))])[0]
    assert isinstance(t, Target) and t.common_name is None
    assert t.label == "RA 05h41m, Dec −02°"


def test_empty():
    assert group_targets([]) == []


def test_tiny_centred_object_loses_to_larger_neighbour_unless_hinted():
    # NGC121 (3.8') sits at the centre; NGC104 (47 Tuc, 32') is 0.6 deg away
    fs = lambda hint=None: [fr(ra=6.70104, dec=-71.53567, fov=(3, 2), hint=hint)]
    assert group_targets(fs())[0].key == "NGC104"
    assert group_targets(fs("NGC121"))[0].key == "NGC121"


def test_everything_tiny_falls_back_to_coordinates():
    t = group_targets([fr(ra=283.39587, dec=33.02858, fov=(3, 2))])[0]
    assert t.label.startswith("RA ") and t.common_name is None


def test_ra_wrap_one_cluster():
    ts = group_targets([fr(ra=359.9, dec=10.0, fov=(2, 1.3)), fr(ra=0.1, dec=10.0, fov=(2, 1.3))])
    assert len(ts) == 1 and ts[0].frame_idx == [0, 1]


def test_high_dec_uses_true_separation():
    # 0.25 deg on the sky at dec +80 is 0.3/cos(80) = 1.73 deg of RA
    dra = 0.25 / math.cos(math.radians(80))
    near = group_targets([fr(ra=100.0, dec=80.0, fov=(1, 0.7)), fr(ra=100.0 + dra, dec=80.0, fov=(1, 0.7))])
    assert len(near) == 1
    dra = 0.35 / math.cos(math.radians(80))  # 0.35 > 0.4 * 0.7
    far = group_targets([fr(ra=100.0, dec=80.0, fov=(1, 0.7)), fr(ra=100.0 + dra, dec=80.0, fov=(1, 0.7))])
    assert len(far) == 2


def test_coordinates_without_fov_do_not_crash():
    f = fr(ra=270.9, dec=-24.38, fov=(3, 2))
    f = dataclasses.replace(f, fov_deg=None)
    assert len(group_targets([f])) == 1


def test_unnamed_clusters_stay_separate():
    ts = group_targets([fr(ra=85.25, dec=-2.2, fov=(0.2, 0.1)), fr(ra=85.26, dec=-2.21, fov=(0.2, 0.1))] +
                       [fr(ra=85.25, dec=-2.2, fov=(0.2, 0.1))])
    assert len(ts) == 1  # same pointing still one cluster
    a = fr(ra=85.25, dec=-2.2, fov=(0.2, 0.1))
    b = fr(ra=85.30, dec=-2.2, fov=(0.2, 0.1))  # 0.05 deg apart: two clusters, same rounded label
    ts = group_targets([a, b])
    assert len(ts) == 2 and ts[0].label == ts[1].label


def test_same_common_name_is_one_target():
    """The Rosette's parts (NGC 2237, 2238, and the NGC 2244 cluster) and the Eastern Veil's (NGC 6992, 6995)."""
    rosette = ([fr(ra=97.72754, dec=5.04917, fov=(0.1, 0.08), hint="NGC 2237") for _ in range(3)]
               + [fr(ra=97.66821, dec=5.01306, fov=(0.1, 0.08), hint="NGC 2238") for _ in range(3)]
               + [fr(ra=97.9815, dec=4.94294, fov=(0.1, 0.08), hint="NGC 2244") for _ in range(2)])
    ts = group_targets(rosette)
    assert [(t.key, t.label, t.common_name, len(t.frame_idx)) for t in ts] == [
        ("NGC2237", "NGC 2237", "Rosette Nebula", 8)]
    veil = ([fr(ra=314.29483, dec=31.23517, fov=(0.3, 0.2), hint="NGC 6995") for _ in range(2)]
            + [fr(ra=314.07946, dec=31.74275, fov=(1.0, 0.7), hint="NGC 6992") for _ in range(4)]
            + [fr(ra=311.49242, dec=30.59514, fov=(1.0, 0.7), hint="NGC 6960")])
    ts = group_targets(veil)
    assert sorted((t.key, t.common_name, len(t.frame_idx)) for t in ts) == [
        ("NGC6960", "Veil Nebula", 1), ("NGC6992", "Eastern Veil", 6)]
    ts = group_targets([fr(hint="NGC 2238"), fr(hint="NGC 2237")])  # no coordinates: by hint, merged the same way
    assert [(t.key, t.frame_idx) for t in ts] == [("NGC2237", [0, 1])]


# ---- archive-run fixes: hints beyond designations, the Lagoon fold

def test_m8_centred_field_is_m8_without_a_hint():
    assert group_targets([fr(ra=271.020, dec=-24.349, fov=(1.32, 0.75))])[0].key == "M8"


def test_common_name_hint_names_the_lagoon():
    t = group_targets([fr(ra=271.020, dec=-24.349, fov=(1.32, 0.75), hint="Lagoon Nebula")])[0]
    assert t.key == "M8" and "Lagoon" in t.common_name


@pytest.mark.parametrize("hint,key,ra,dec", [
    ("Ring Nebula", "M57", 283.39587 + 0.03, 33.02858 + 0.02),
    ("Ghost of Jupiter Nebula", "NGC3242", 156.192, -18.642 + 0.02),
    ("van den Bergh 152", "VDB152", 333.3522, 70.2514),
    ("Cave", "SH2-155", 344.475, 62.518),
    ("NYCephei_bare", "NYCEP", 344.66583, 63.07715),
])
def test_common_names_and_aliases_resolve_tiny_and_size_less_objects(hint, key, ra, dec):
    t = group_targets([fr(ra=ra, dec=dec, fov=(1.32, 0.75), hint=hint)])[0]
    assert t.key == key


def test_ring_nebula_without_hint_still_falls_back_to_coordinates():  # R17 guard unchanged
    t = group_targets([fr(ra=283.39587 + 0.03, dec=33.02858 + 0.02, fov=(1.32, 0.75))])[0]
    assert t.key != "M57"


def test_cave_in_a_wide_field_beats_the_giant_cloud():
    t = group_targets([fr(ra=343.19, dec=62.55, fov=(1.05, 0.70), hint="Cave")])[0]
    assert t.key == "SH2-155"


def test_spelled_out_prefixes():
    assert normalise_id("Barnard 142_Tile03") == "B142"
    assert normalise_id("van den Bergh 152") == "VDB152"
    assert normalise_id("Sharpless 2-155") == "SH2-155"
    assert normalise_id("Sharpless 155") is None


def test_barnard_tiles_merge_into_one_target():
    fs = [fr(ra=294.9223, dec=10.5184 + d, fov=(1.32, 0.75), hint=f"Barnard 142_Tile0{i}")
          for i, d in enumerate((-0.5, 0.0, 0.5), 1)]
    ts = group_targets(fs)
    assert [t.key for t in ts] == ["B142"] and len(ts[0].frame_idx) == 3


def test_designation_hint_beats_common_name_and_stale_hint_does_not_shadow():
    rosette = [fr(ra=97.98, dec=4.94, fov=(3, 2), hint="Rosette Nebula") for _ in range(3)] + \
              [fr(ra=97.98, dec=4.94, fov=(3, 2), hint="NGC 2244") for _ in range(2)]
    assert group_targets(rosette)[0].key == "NGC2239"
    m8 = [fr(ra=270.92, dec=-24.38, fov=(1.32, 0.75), hint="Zeta Ophiuchi") for _ in range(3)] + \
         [fr(ra=270.92, dec=-24.38, fov=(1.32, 0.75), hint="M8_x")]
    assert group_targets(m8)[0].key == "M8"


def test_resolved_hints_never_reach_the_label():
    t = group_targets([fr(ra=344.66583, dec=63.07715, fov=(1.32, 0.75), hint="NYCephei_bare")])[0]
    assert "bare" not in t.label.lower() and "bare" not in (t.common_name or "").lower()
