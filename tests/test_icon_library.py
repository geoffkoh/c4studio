"""The icon library the picker browses (PP-233)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from c4studio.icon_library import friendly_name, scan
from c4studio.icons import MAX_ICON_BYTES

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>'


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("aws/Arch_AWS-Lambda_48.svg", "Lambda"),
        ("aws/Arch_Amazon-Simple-Queue-Service_64.png", "Simple Queue Service"),
        (
            "aws/Res_Amazon-Simple-Storage-Service_S3-Bucket_48_Dark.svg",
            "Simple Storage Service S3 Bucket (dark)",
        ),
        ("fa/svgs/solid/database.svg", "database (solid)"),
        ("fa/svgs/brands/aws.svg", "aws (brands)"),
        ("simple/postgresql.svg", "postgresql"),
        ("logo.png", "logo"),
    ],
)
def test_names_read_the_way_a_person_would_say_them(path: str, name: str) -> None:
    assert friendly_name(PurePosixPath(path)) == name


@pytest.fixture
def library(tmp_path: Path) -> Path:
    folder = tmp_path / "icons"
    files = [
        "aws/Arch_AWS-Lambda/16/Arch_AWS-Lambda_16.svg",
        "aws/Arch_AWS-Lambda/48/Arch_AWS-Lambda_48.png",
        "aws/Arch_AWS-Lambda/48/Arch_AWS-Lambda_48.svg",
        "aws/Arch_AWS-Lambda/64/Arch_AWS-Lambda_64.svg",
        "aws/Res_Amazon-EC2_Instance_48_Light.svg",
        "aws/Res_Amazon-EC2_Instance_48_Dark.svg",
        "fa/svgs/solid/database.svg",
        "fa/svgs/regular/database.svg",
        "loose.svg",
        "aws/README.md",
        ".git/icon.svg",
    ]
    for rel in files:
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(SVG)
    (folder / "aws" / "huge.svg").write_bytes(b" " * (MAX_ICON_BYTES + 1))
    return tmp_path


def test_variants_collapse_to_one_icon_each(library: Path) -> None:
    icons, truncated = scan(library / "icons", library)
    assert not truncated
    assert [(i.pack, i.name, i.path) for i in icons] == [
        ("", "loose", "icons/loose.svg"),
        ("aws", "EC2 Instance (dark)", "icons/aws/Res_Amazon-EC2_Instance_48_Dark.svg"),
        (
            "aws",
            "EC2 Instance (light)",
            "icons/aws/Res_Amazon-EC2_Instance_48_Light.svg",
        ),
        # The 48 px SVG, over the PNG and the other sizes.
        ("aws", "Lambda", "icons/aws/Arch_AWS-Lambda/48/Arch_AWS-Lambda_48.svg"),
        ("fa", "database (regular)", "icons/fa/svgs/regular/database.svg"),
        ("fa", "database (solid)", "icons/fa/svgs/solid/database.svg"),
    ]


def test_a_missing_folder_lists_nothing(tmp_path: Path) -> None:
    assert scan(tmp_path / "icons", tmp_path) == ([], False)
