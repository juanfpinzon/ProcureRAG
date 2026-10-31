import importlib.util
from pathlib import Path


def _load_deployed_proof_module():
    """Load `scripts/deployed_proof.py` by path (a standard-library script, like container_smoke.py)."""
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "deployed_proof.py"
    spec = importlib.util.spec_from_file_location("deployed_proof", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The script's interpretations are pure functions, so they are tested here
# without a network. The HTTP calls themselves are the deployed proof.
# ---------------------------------------------------------------------------


def test_function_region_is_the_second_to_last_part_and_the_edge_region_is_never_returned():
    proof = _load_deployed_proof_module()

    assert proof.function_region("fra1::dub1::abcd1-1730000000000-0123456789ab") == "dub1"
    assert proof.function_region("fra1::abcd1-1730000000000-0123456789ab") is None  # static: no function ran
    assert proof.function_region(None) is None
    assert proof.function_region("") is None


def test_the_free_kill_switch_probe_reads_422_as_on_and_503_as_off():
    proof = _load_deployed_proof_module()

    assert proof.kill_switch_state(422) == "on"
    assert proof.kill_switch_state(503).startswith("off")
    assert proof.kill_switch_state(429).startswith("unexpected")


def test_browser_leaks_reports_names_only():
    proof = _load_deployed_proof_module()
    host = "procurerag-api.example-region.azurecontainerapps.io"

    assert proof.browser_leaks(["<html>ProcureRAG case study</html>", "PROCURERAG_LIVE_LLM=0"], host) == []
    found = proof.browser_leaks(['x="PROCURERAG_SERVICE_TOKEN"', f"fetch('https://{host}/query')"], host)
    assert found == ["PROCURERAG_SERVICE_TOKEN", "the Azure API host"]
    assert proof.browser_leaks(["anything"], None) == []


def test_spoof_verdict_passes_only_when_forged_addresses_still_count_as_one_client():
    proof = _load_deployed_proof_module()

    assert proof.spoof_verdict(["ready", "ready", "ready", "busy"])[0] is True
    assert proof.spoof_verdict(["waking", "busy"])[0] is True  # earlier checks today count too
    # All four admitted: each forged address was a new client.
    assert proof.spoof_verdict(["ready", "ready", "ready", "ready"])[0] is False
    # Not evidence either way.
    assert proof.spoof_verdict(["busy"])[0] is False
    assert "inconclusive" in proof.spoof_verdict(["busy"])[1]
    assert "inconclusive" in proof.spoof_verdict(["unavailable", "unavailable"])[1]
    assert proof.spoof_verdict([])[0] is False


def test_watch_stops_at_the_first_change_and_prints_both_timestamps(capsys):
    proof = _load_deployed_proof_module()
    statuses = iter([422, 422, 422, 503])
    times = iter(["T0", "T1", "T2", "T3"])
    ticks = iter(range(100))

    exit_code = proof.run_watch(
        "https://site.example.invalid",
        interval=1,
        max_seconds=60,
        probe=lambda site: (next(statuses), {}, 0.1),
        clock=lambda: next(times),
        sleep=lambda seconds: None,
        monotonic=lambda: next(ticks),
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "last request with the old state: T2" in output
    assert "first request with the new state: T3" in output


def test_watch_gives_up_without_a_change():
    proof = _load_deployed_proof_module()
    ticks = iter([0, 0, 5, 11])

    exit_code = proof.run_watch(
        "https://site.example.invalid",
        interval=1,
        max_seconds=10,
        probe=lambda site: (422, {}, 0.1),
        clock=lambda: "T",
        sleep=lambda seconds: None,
        monotonic=lambda: next(ticks),
    )
    assert exit_code == 1


def test_site_must_be_https():
    proof = _load_deployed_proof_module()

    try:
        proof.main(["free", "--site", "http://site.example.invalid"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("an http:// site was accepted")
