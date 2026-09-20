"""The home-only guard and the model registry (no GPU, no server)."""
import pytest

from app import serving


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "192.168.1.20", "10.0.0.7", "172.16.5.5", "169.254.10.10",
                                  "fe80::1", "fd00::5", "::ffff:192.168.1.9"])
def test_home_addresses_are_allowed(host):
    assert serving.is_home_request(host, {})


@pytest.mark.parametrize("host", ["8.8.8.8", "1.1.1.1", "203.0.113.9", "100.64.1.2", "2001:4860:4860::8888",
                                  "::ffff:8.8.8.8", "198.18.0.1", "192.0.0.1", "172.32.0.1", "172.15.255.255", "", None, "not-an-ip", "192.168.1"])
def test_public_or_malformed_addresses_are_refused(host):
    assert not serving.is_home_request(host, {})


@pytest.mark.parametrize("header", ["X-Forwarded-For", "x-real-ip", "Forwarded", "CF-Connecting-IP", "Via", "X-Forwarded-Proto"])
def test_proxied_requests_are_refused_even_from_a_private_address(header):
    """A tunnel or reverse proxy on this machine shows up as 127.0.0.1; the proxy headers give it away."""
    assert not serving.is_home_request("127.0.0.1", {header: "1.2.3.4"})
    assert not serving.is_home_request("192.168.1.20", {"Accept": "*/*", header: "x"})


def test_ordinary_headers_do_not_block():
    assert serving.is_home_request("192.168.1.20", {"Host": "poet.local:7860", "User-Agent": "x", "Accept": "*/*"})


def test_only_local_vllm_servers_can_be_switched(monkeypatch):
    for url, ok in [("http://127.0.0.1:8000/v1", True), ("http://localhost:8000/v1", True),
                    ("http://192.168.1.50:8000/v1", False), ("https://api.example.com/v1", False)]:
        monkeypatch.setattr(serving, "BASE_URL", url)
        assert serving.is_local_server() is ok


def test_switch_refuses_a_remote_server(monkeypatch, tmp_path):
    monkeypatch.setattr(serving, "BASE_URL", "http://192.168.1.50:8000/v1")
    monkeypatch.setitem(serving.MODELS, "4b", {**serving.MODELS["4b"], "path": tmp_path})
    with pytest.raises(RuntimeError, match="not a local"):
        list(serving.switch("4b"))


def test_unknown_model_is_rejected():
    with pytest.raises(ValueError):
        list(serving.switch("no-such-model"))


def test_only_models_that_exist_on_disk_are_offered(monkeypatch, tmp_path):
    (tmp_path / "here").mkdir()
    fake = {"a": {**serving.MODELS["4b"], "path": tmp_path / "here"}, "b": {**serving.MODELS["4b"], "path": tmp_path / "gone"}}
    monkeypatch.setattr(serving, "MODELS", fake)
    assert list(serving.available()) == ["a"]


def test_serve_script_is_offline_and_local_only():
    script = (serving.ROOT / "scripts" / "serve.sh").read_text()
    assert "--host 127.0.0.1" in script                       # vLLM never listens on the network
    assert "VLLM_NO_USAGE_STATS=1" in script and "HF_HUB_OFFLINE=1" in script


def test_stop_refuses_a_remote_server(monkeypatch):
    monkeypatch.setattr(serving, "BASE_URL", "http://192.168.1.50:8000/v1")
    with pytest.raises(RuntimeError, match="not a local"):
        list(serving.stop())


def test_stop_and_switch_share_one_lock(monkeypatch):
    monkeypatch.setattr(serving, "current_key", lambda: "4b")
    assert serving._lock.acquire(blocking=False)
    try:
        assert serving.is_switching()
        with pytest.raises(RuntimeError, match="in progress"):
            list(serving.stop())
    finally:
        serving._lock.release()
    assert not serving.is_switching()


def test_stop_does_nothing_when_no_server_is_running(monkeypatch):
    monkeypatch.setattr(serving, "current_key", lambda: None)
    monkeypatch.setattr(serving, "_vllm_pids", lambda: [])
    monkeypatch.setattr(serving, "stop_server", lambda: (_ for _ in ()).throw(AssertionError("must not kill anything")))
    assert list(serving.stop()) == [(True, "No model server is running.")]
