from pathlib import Path

from onemic.infrastructure.lv2 import LSP_GATE_URI, find_lsp_gate, lv2_dirs


def install_gate(directory: Path) -> None:
    bundle = directory / "lsp-plugins.lv2"
    bundle.mkdir(parents=True)
    (bundle / "gate_mono.ttl").write_text("")


def test_the_gate_is_found_on_lv2_path(tmp_path: Path) -> None:
    install_gate(tmp_path / "plugins")

    assert find_lsp_gate({"LV2_PATH": f"/nowhere:{tmp_path / 'plugins'}"}) == LSP_GATE_URI


def test_the_gate_is_found_in_the_home_directory(tmp_path: Path) -> None:
    install_gate(tmp_path / ".lv2")

    assert find_lsp_gate({"HOME": str(tmp_path), "LV2_PATH": ""}) == LSP_GATE_URI


def test_a_missing_gate_is_reported(tmp_path: Path) -> None:
    assert find_lsp_gate({"LV2_PATH": str(tmp_path)}) is None


def test_default_search_order() -> None:
    assert lv2_dirs({"HOME": "/home/u"})[:2] == [Path("/home/u/.lv2"), Path("/usr/lib/lv2")]
