from datetime import datetime

from skywrapped._fitsnorm import read_header, to_frame


def frame_of(fixture, name, path):
    values, comments = read_header(fixture(name))
    return to_frame(values, comments, path)


def test_asiair_light(fixture):
    f = frame_of(fixture, "asiair_2600air", "a/Light_SH2-245_LExt_300.0s_x.fit")
    assert (f.vendor, f.frame_type, f.is_stack) == ("asiair", "light", False)
    assert f.exposure_s == f.integration_s == 300.0
    assert f.start_utc == datetime(2026, 9, 6, 5, 11, 25, 157930) and f.start_local is None
    assert f.camera == "ZWO ASI2600MC Air" and f.telescope is None and f.focal_mm == 264
    assert f.gain == 100 and f.sensor_c == -10.0 and f.site == (12.3456, -65.4321)


def test_astrowizard_stack(fixture):
    f = frame_of(fixture, "asiair_duo_awstack", "IC_434_LUlt_wizardstack_40f_AW1_init.fits")
    assert f.is_stack and f.sub_count == 40 and f.integration_s == 12000.0


def test_origin_local_time(fixture):
    f = frame_of(fixture, "origin_678c", "Light_DG26_60.0s_ISO200_20261111-014118_0148.fits")
    assert f.vendor == "origin" and f.start_utc is None
    assert f.start_local == datetime(2026, 11, 11, 1, 41, 18)
    assert f.iso == 200 and f.gain is None and f.telescope == "RASA6F2" and f.site == (12.3456, -65.4321)


def test_typing_by_name():
    for name, t in [("Dark_300.0s_Bin1.fit", "dark"), ("Flat_1.2ms.fit", "flat"), ("Bias_x.fit", "bias"),
                    ("Light_M31_60s.fit", "light"), ("img_0001.fit", "unknown")]:
        assert to_frame({"EXPTIME": 1.0}, {}, "d/" + name).frame_type == t


def test_imagetyp_spellings():
    for raw, t in [("Light Frame", "light"), ("LIGHT", "light"), ("Dark Flat", "darkflat"), ("FLAT", "flat")]:
        assert to_frame({"IMAGETYP": raw, "EXPTIME": 1.0}, {}, "x.fit").frame_type == t
    f = to_frame({"IMAGETYP": "Master Dark", "EXPTIME": 1.0}, {}, "x.fit")
    assert f.frame_type == "dark" and f.is_stack


def test_total_exposure_keyword():
    f = to_frame({"STACKCNT": 360, "EXPTIME": 10.0, "LIVETIME": 3600.0}, {}, "Stacked_x.fit")
    assert f.is_stack and f.sub_count == 360 and f.integration_s == 3600.0


def test_mount_names_are_not_telescopes():
    for t in ["ZWO AM5", "ZWO AM7", "EQ6-R Pro", "HEQ5", "CEM70", "Sky-Watcher AZ-GTi", "Simulator", "",
              "Celestron CGX", "CGEM II", "EQM-35 Pro", "EQ-6", "Sky-Watcher EQ-8", "ASCOM Telescope Driver for X",
              "Telescope Simulator for .NET"]:
        assert to_frame({"TELESCOP": t, "EXPTIME": 1.0}, {}, "x.fit").telescope is None
    assert to_frame({"TELESCOP": "Takahashi FSQ-106", "EXPTIME": 1.0}, {}, "x.fit").telescope == "Takahashi FSQ-106"


def test_local_flag_by_comment_and_date_only():
    f = to_frame({"DATE-OBS": "2026-11-11T01:41:18", "EXPTIME": 1.0}, {"DATE-OBS": "Start of exposure (local time)"}, "x.fit")
    assert f.start_local is not None and f.start_utc is None
    f = to_frame({"DATE-OBS": "2026-11-11", "TIME-OBS": "03:15:28", "EXPTIME": 1.0}, {}, "x.fit")
    assert f.start_utc == datetime(2026, 11, 11, 3, 15, 28)


def test_site_pair_order_and_derived_integration():
    f = to_frame({"LATITUDE": 1.0, "LONGITUD": 2.0, "SITELAT": 3.0, "SITELONG": 4.0, "EXPTIME": 10.0,
                  "NCOMBINE": 6}, {}, "x.fit")
    assert f.site == (3.0, 4.0) and f.sub_count == 6 and f.integration_s == 60.0
    assert to_frame({"EXPTIME": 1.0}, {}, "x.fit").site is None


def test_backslash_path_name_used_for_typing():
    assert to_frame({"EXPTIME": 1.0}, {}, "a\\b\\Dark_1s.fit").frame_type == "dark"
    assert to_frame({"EXPTIME": 1.0}, {}, "a/Master_x.fit").is_stack


def test_stack_names_are_whole_tokens():
    def st(n):
        return to_frame({"EXPTIME": 1.0}, {}, "d/" + n).is_stack
    assert not st("Light_Masterson_60s.fit")
    assert not st("Light_IC1396_integration_test.fit")
    assert st("M31_integration.fits")
    assert st("IC_434_LUlt_wizardstack_40f_AW1_init.fits")
    assert st("Stacked_120_M42.fit")


def test_nonpositive_exposures_fall_through():
    f = to_frame({"EXPTIME": 10.0, "NCOMBINE": 6, "LIVETIME": 0.0}, {}, "x.fit")
    assert f.integration_s == 60.0
    assert to_frame({"EXPTIME": 0, "EXPOSURE": 60}, {}, "x.fit").exposure_s == 60.0


def test_no_fabricated_times():
    f = to_frame({"DATE-OBS": "2026-11-11"}, {}, "x.fit")
    assert f.start_utc is None and f.start_local is None
    assert to_frame({"DATE-OBS": "2026-11-11", "TIME-OBS": "03:15"}, {}, "x.fit").start_utc == datetime(2026, 11, 11, 3, 15)
    assert to_frame({"DATE-OBS": "2026-11-11T03:15"}, {}, "x.fit").start_utc == datetime(2026, 11, 11, 3, 15)


def test_name_only_stack_keeps_one_sub():
    f = to_frame({"EXPTIME": 300.0}, {}, "M31_stacked.fit")
    assert f.is_stack and f.sub_count == 1 and f.integration_s == 300.0


def test_minor_rules():
    assert to_frame({"SITELAT": 0.0, "SITELONG": 0.0}, {}, "x.fit").site is None
    assert to_frame({"IMAGETYP": "Weird", "FRAME": "Dark"}, {}, "Light_x.fit").frame_type == "dark"
    assert to_frame({"FRAME": "Master Flat"}, {}, "x.fit").is_stack


def _folder_t(path, **v):
    return to_frame({"EXPTIME": 1.0, **v}, {}, path).frame_type


def test_clearly_calibration_folders_type_the_frame():
    for path, want in [("Darks/x.fits", "dark"), ("Dark_300s_-10C/x.fits", "dark"),
                       ("DWARF_RAW_CALI_FRAME/x.fits", "calibration"), ("CALI_FRAME/2026-11-10/x.fits", "calibration"),
                       ("flats/gain100/x.fits", "flat"), ("a/Biases/x.fits", "bias"), ("x/DarkFlats/x.fits", "darkflat"),
                       ("Offset/x.fits", "bias"), ("CALI_FRAME/dark_0001.fits", "dark")]:
        assert _folder_t(path) == want, path


def test_target_and_site_folders_are_not_calibration():
    for path in ["Dark_Nebula/x.fits", "B33_Horsehead_dark_nebula/x.fits", "Dark Sky Camp/M31/x.fits",
                 "Dark_Horse/x.fits", "Flats/M31/2026-11-10/x.fits", "M31/Light/x.fits", "x.fits"]:
        assert _folder_t(path) == "unknown", path


def test_keywords_and_name_prefix_beat_folders():
    assert _folder_t("flats_tonight/x.fits", IMAGETYP="Light") == "light"
    assert _folder_t("Flats/dark_0001.fits") == "dark"


# ------------------------------------------------------------------ gear names (C2)

def test_clean_label_rules():
    from skywrapped._fitsnorm.labels import clean_label
    assert clean_label("S50_4a8b9c2d") == "S50"
    assert clean_label("MyScope-A1B2C3D4E5") == "MyScope"
    assert clean_label("Esprit 120 SN 20231234567") == "Esprit 120 SN"
    assert clean_label("Ed Smith's Backyard Esprit 12345678") == "Ed Smith's Backyard Esprit"
    assert clean_label("Teleskop Müller · f/5 <b>") == "Teleskop Muller f/5 b"
    assert clean_label('8" SCT (f/10)') == '8" SCT (f/10)'
    assert clean_label("ZWO_ASI2600MC_Pro") == "ZWO ASI2600MC Pro"
    long = clean_label("Takahashi FSQ-106EDX4 with the reducer and flattener")
    assert long == "Takahashi FSQ-106EDX4 with the" and len(long) <= 32
    assert clean_label("A" * 40) == "A" * 32
    for empty in ("", "  ", "123456789", "_abcdef12", "\x01\x02", None):
        assert clean_label(empty) is None, empty


def test_gear_names_from_headers():
    def gear(vendor_cards, **v):
        f = to_frame({"EXPTIME": 1.0, **vendor_cards, **v}, {}, "x.fit")
        return f.camera, f.telescope
    assert gear({"CREATOR": "ZWO Seestar S50"}, INSTRUME="Seestar S50", TELESCOP="S50_4a8b9c2d") == (
        "Seestar S50", "Seestar S50")
    assert gear({"INSTRUME": "Seestar S30"}, TELESCOP="S30_00ff00aa") == ("Seestar S30", "Seestar S30")
    assert gear({"ORIGIN": "DWARFLAB"}, INSTRUME="DWARFIII", TELESCOP="DWARFIII") == ("Dwarf 3", "Dwarf 3")
    assert gear({"ORIGIN": "DWARFLAB"}, INSTRUME="DWARFII", TELESCOP="DWARFII") == ("Dwarf 2", "Dwarf 2")
    assert gear({"CREATOR": "Origin 1.5"}, TELESCOP="RASA6F2") == (None, "RASA6F2")
    assert gear({}, INSTRUME="ZWO ASI2600MC Pro 1234567", TELESCOP="Esprit_ab12cd34ef") == (
        "ZWO ASI2600MC Pro", "Esprit")
    assert gear({}, INSTRUME="123456789", TELESCOP="#&()") == ("Camera", None)


def test_present_but_unrecognised_type_is_other():
    """I5: 'unknown' only when no type keyword exists; an unrecognised value is 'other' (never counted)."""
    for v in ({"IMAGETYP": "SNAPSHOT"}, {"IMAGETYP": "Focus"}, {"FRAME": "Test"}, {"IMAGETYP": "Preview"}):
        assert to_frame({"EXPTIME": 1.0, **v}, {}, "d/Light_x.fit").frame_type == "other", v
    assert to_frame({"IMAGETYP": "Weird", "FRAME": "Dark"}, {}, "x.fit").frame_type == "dark"
    assert to_frame({"IMAGETYP": "Master Light"}, {}, "x.fit").frame_type == "light"
    assert to_frame({"FRAME": "FK5", "EXPTIME": 1.0}, {}, "d/Light_x.fit").frame_type == "light"
    assert to_frame({"EXPTIME": 1.0}, {}, "d/img_0001.fit").frame_type == "unknown"
    assert to_frame({"IMAGETYP": "  ", "EXPTIME": 1.0}, {}, "d/img_0001.fit").frame_type == "unknown"


def test_implausible_counts_and_exposures():
    """A count over 100,000 is unknown (ignored); an exposure over a day is unknown, and a light of unknown length
    is not counted: to_frame refuses it, and the scan reports the file as unreadable."""
    import pytest

    from skywrapped._fitsnorm.header import HeaderError
    f = to_frame({"EXPTIME": 300.0, "NCOMBINE": 1e9}, {}, "x.fit")
    assert not f.is_stack and f.sub_count == 1 and f.integration_s == 300.0
    f = to_frame({"EXPTIME": 300.0, "NCOMBINE": 40, "STACKCNT": 500_000}, {}, "x.fit")
    assert f.sub_count == 40 and f.integration_s == 12000.0
    assert to_frame({"EXPTIME": 86_401.0, "EXPOSURE": 120.0}, {}, "x.fit").exposure_s == 120.0
    with pytest.raises(HeaderError, match="implausible"):
        to_frame({"EXPTIME": 1e7}, {}, "x.fit")
    assert to_frame({"EXPTIME": 86_400.0}, {}, "x.fit").exposure_s == 86_400.0
    # a Dwarf stack's EXPTIME is its total integration, which can pass a day
    f = to_frame({"ORIGIN": "DWARFLAB", "NAXIS3": 3, "EXPTIME": 100_000.0}, {}, "x.fits")
    assert f.is_stack and f.integration_s == 100_000.0


def test_implausible_exposure_is_counted_unreadable(tmp_path):
    from skywrapped.scan import scan_paths
    cards = ["SIMPLE  =                    T", "BITPIX  =                   16", "NAXIS   =                    0",
             "IMAGETYP= 'Light   '", "EXPTIME =          99999999.0", "DATE-OBS= '2026-03-03T03:03:03'", "END"]
    raw = "".join(c.ljust(80) for c in cards).encode("ascii")
    (tmp_path / "Light_a.fit").write_bytes(raw + b" " * (-len(raw) % 2880))
    frames, sk = scan_paths([str(tmp_path)], [])
    assert frames == [] and sk["unreadable"] == 1


def test_numeric_frame_card_is_a_counter_not_a_type_keyword():
    f = to_frame({"FRAME": 12, "EXPTIME": 60.0}, {}, "d/Light_x.fit")
    assert f.frame_type == "light"  # falls through to the file name
    assert to_frame({"FRAME": 12}, {}, "x.fit").frame_type == "unknown"
    assert to_frame({"FRAME": 12, "IMAGETYP": "Dark"}, {}, "x.fit").frame_type == "dark"
    assert to_frame({"FRAME": 12}, {}, "CALI_FRAME/x.fits").frame_type == "calibration"  # folder


def test_numeric_frame_is_not_ekos_nor_in_kinds():
    f = to_frame({"FRAME": 12, "PIXSIZE1": 3.76, "EXPTIME": 60.0}, {}, "d/Light_x.fit")
    assert f.vendor != "ekos"
    assert to_frame({"FRAME": 12, "IMAGETYP": "Light", "EXPTIME": 60.0}, {}, "x.fit").vendor == "generic"
    assert to_frame({"FRAME": "Light", "PIXSIZE1": 3.76, "EXPTIME": 60.0}, {}, "x.fit").vendor == "ekos"
    master = to_frame({"FRAME": 12, "IMAGETYP": "Light", "EXPTIME": 60.0}, {}, "x.fit")
    assert not master.is_stack  # "12" never enters the keyword string
