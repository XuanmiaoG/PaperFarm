"""Tests for GPU manager."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest

from open_researcher.gpu_manager import GPUManager


@pytest.fixture
def gpu_file(tmp_path):
    return tmp_path / "gpu_status.json"


@pytest.fixture
def mgr(gpu_file):
    return GPUManager(gpu_file)


NVIDIA_SMI_OUTPUT = """\
index, memory.total [MiB], memory.used [MiB], memory.free [MiB], utilization.gpu [%]
0, 24576 MiB, 2048 MiB, 22528 MiB, 10 %
1, 24576 MiB, 20000 MiB, 4576 MiB, 95 %
"""


def test_detect_local_gpus(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_OUTPUT)
        gpus = mgr.detect_local()
    assert len(gpus) == 2
    assert gpus[0]["device"] == 0
    assert gpus[0]["memory_free"] == 22528
    assert gpus[1]["memory_free"] == 4576


def test_detect_local_no_nvidia_smi(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        gpus = mgr.detect_local()
    assert gpus == []


def test_allocate_picks_most_free(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_OUTPUT)
        result = mgr.allocate()
    assert result is not None
    host, device = result
    assert host == "local"
    assert device == 0


def test_allocate_writes_status(mgr, gpu_file):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_OUTPUT)
        mgr.allocate(tag="exp-001")
    data = json.loads(gpu_file.read_text())
    allocated = [g for g in data["gpus"] if g["allocated_to"] == "exp-001"]
    assert len(allocated) == 1


def test_release(mgr, gpu_file):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_OUTPUT)
        mgr.allocate(tag="exp-001")
        mgr.release("local", 0)
    data = json.loads(gpu_file.read_text())
    g = [g for g in data["gpus"] if g["device"] == 0][0]
    assert g["allocated_to"] is None


def test_status(mgr, gpu_file):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_OUTPUT)
        mgr.refresh()
    status = mgr.status()
    assert len(status) == 2


NVIDIA_SMI_4GPU = """\
index, memory.total [MiB], memory.used [MiB], memory.free [MiB], utilization.gpu [%]
0, 24576 MiB, 2048 MiB, 22528 MiB, 10 %
1, 24576 MiB, 3000 MiB, 21576 MiB, 15 %
2, 24576 MiB, 20000 MiB, 4576 MiB, 95 %
3, 24576 MiB, 1000 MiB, 23576 MiB, 5 %
"""


NVIDIA_SMI_6GPU = """\
index, memory.total [MiB], memory.used [MiB], memory.free [MiB], utilization.gpu [%]
0, 49140 MiB, 0 MiB, 49140 MiB, 0 %
1, 49140 MiB, 0 MiB, 49140 MiB, 0 %
2, 49140 MiB, 0 MiB, 49140 MiB, 0 %
3, 49140 MiB, 0 MiB, 49140 MiB, 0 %
4, 49140 MiB, 0 MiB, 49140 MiB, 0 %
5, 49140 MiB, 0 MiB, 49140 MiB, 0 %
"""


def test_allocate_group(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_4GPU)
        result = mgr.allocate_group(count=2, tag="exp-multi")
    assert result is not None
    assert len(result) == 2
    devices = [r[1] for r in result]
    assert 3 in devices
    assert 0 in devices


def test_allocate_group_not_enough(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_OUTPUT)
        result = mgr.allocate_group(count=5, tag="exp-big")
    assert result is None


def test_allocate_group_single(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_OUTPUT)
        result = mgr.allocate_group(count=1, tag="exp-single")
    assert result is not None
    assert len(result) == 1


def test_detect_local_honors_allowed_devices(gpu_file):
    mgr = GPUManager(gpu_file, allowed_local_devices={4, 5})
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_6GPU)
        gpus = mgr.detect_local()
    assert [gpu["device"] for gpu in gpus] == [4, 5]


def test_reserve_group_respects_required_devices(gpu_file):
    mgr = GPUManager(gpu_file)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_6GPU)
        reservations = mgr.reserve_group(
            count=2,
            tag="exp-pinned",
            memory_mb=4096,
            shareable=False,
            exclusive=True,
            required_devices=[
                {"host": "local", "device": 4},
                {"host": "local", "device": 5},
            ],
        )
    assert reservations is not None
    assert {(item["host"], item["device"]) for item in reservations} == {("local", 4), ("local", 5)}


def test_user_pin_reservations_block_allocation(gpu_file):
    rows = []
    for device in range(6):
        row = {
            "host": "local",
            "device": device,
            "memory_total": 49140,
            "memory_used": 0,
            "memory_free": 49140,
            "utilization": 0,
            "reservations": [],
        }
        if device < 4:
            row["reservations"].append(
                {
                    "id": f"pin-{device}",
                    "tag": "user_pinned_excluded",
                    "kind": "user_pin",
                }
            )
        rows.append(row)
    gpu_file.write_text(json.dumps({"gpus": rows}, indent=2), encoding="utf-8")
    mgr = GPUManager(gpu_file)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_6GPU)
        reservations = mgr.reserve_group(
            count=2,
            tag="exp-free",
            memory_mb=4096,
            shareable=False,
            exclusive=True,
        )
    assert reservations is not None
    assert {(item["host"], item["device"]) for item in reservations} == {("local", 4), ("local", 5)}


def test_release_group(mgr, gpu_file):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_4GPU)
        gpus = mgr.allocate_group(count=2, tag="exp-multi")
        mgr.release_group(gpus)
    data = json.loads(gpu_file.read_text())
    for g in data["gpus"]:
        assert g["allocated_to"] is None


def test_concurrent_allocate_release(gpu_file):
    """Multiple threads allocating and releasing GPUs concurrently."""
    mgr = GPUManager(gpu_file)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_4GPU)

        # Allocate all 4 GPUs with different tags
        def allocate_one(i):
            return mgr.allocate(tag=f"exp-{i}")

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(allocate_one, i) for i in range(4)]
            results = [f.result() for f in as_completed(futures)]

        # All 4 should be allocated (no None)
        allocated = [r for r in results if r is not None]
        assert len(allocated) == 4

        # All device indices should be unique
        devices = [(h, d) for h, d in allocated]
        assert len(set(devices)) == 4

        # Now release all concurrently
        def release_one(gpu_tuple):
            mgr.release(gpu_tuple[0], gpu_tuple[1])

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(release_one, g) for g in allocated]
            for f in as_completed(futures):
                f.result()

        # All should be released
        data = json.loads(gpu_file.read_text())
        for g in data["gpus"]:
            assert g["allocated_to"] is None
