"""Tests for idea pool file manager."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from open_researcher.idea_pool import IdeaPool


@pytest.fixture
def pool_file(tmp_path):
    p = tmp_path / "idea_pool.json"
    p.write_text(json.dumps({"ideas": []}))
    return p


@pytest.fixture
def pool(pool_file):
    return IdeaPool(pool_file)


def test_add_idea(pool, pool_file):
    pool.add("cosine LR with warmup", source="literature", category="lr_schedule", priority=1)
    data = json.loads(pool_file.read_text())
    assert len(data["ideas"]) == 1
    idea = data["ideas"][0]
    assert idea["description"] == "cosine LR with warmup"
    assert idea["status"] == "pending"
    assert idea["priority"] == 1
    assert idea["id"].startswith("idea-")


def test_list_by_status(pool):
    pool.add("idea A", priority=2)
    pool.add("idea B", priority=1)
    pending = pool.list_by_status("pending")
    assert len(pending) == 2
    assert pending[0]["description"] == "idea B"


def test_update_status(pool):
    pool.add("idea A", priority=1)
    ideas = pool.list_by_status("pending")
    pool.update_status(ideas[0]["id"], "running", experiment=1)
    running = pool.list_by_status("running")
    assert len(running) == 1
    assert running[0]["assigned_experiment"] == 1


def test_mark_done(pool):
    pool.add("idea A", priority=1)
    ideas = pool.list_by_status("pending")
    pool.mark_done(ideas[0]["id"], metric_value=1.49, verdict="kept")
    done = pool.list_by_status("done")
    assert len(done) == 1
    assert done[0]["result"]["metric_value"] == 1.49


def test_summary(pool):
    pool.add("A", priority=1)
    pool.add("B", priority=2)
    pool.add("C", priority=3)
    ideas = pool.list_by_status("pending")
    pool.update_status(ideas[0]["id"], "running")
    s = pool.summary()
    assert s == {"pending": 2, "running": 1, "done": 0, "skipped": 0, "total": 3}


def test_delete_idea(pool):
    pool.add("A", priority=1)
    ideas = pool.list_by_status("pending")
    pool.delete(ideas[0]["id"])
    assert pool.summary()["total"] == 0


def test_update_priority(pool):
    pool.add("A", priority=3)
    ideas = pool.list_by_status("pending")
    pool.update_priority(ideas[0]["id"], 1)
    reloaded = pool.list_by_status("pending")
    assert reloaded[0]["priority"] == 1


def test_add_idea_with_gpu_hint(pool, pool_file):
    pool.add("DDP training experiment", priority=1, gpu_hint=4)
    data = json.loads(pool_file.read_text())
    assert data["ideas"][0]["gpu_hint"] == 4


def test_add_idea_default_gpu_hint(pool, pool_file):
    pool.add("simple experiment", priority=1)
    data = json.loads(pool_file.read_text())
    assert data["ideas"][0]["gpu_hint"] == "auto"


def test_claim_idea_atomic(pool):
    pool.add("idea A", priority=1)
    pool.add("idea B", priority=2)
    claimed = pool.claim_idea(worker_id="w-001")
    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["claimed_by"] == "w-001"
    assert claimed["claim_token"].startswith("claim-")
    first_seq = int(claimed["claim_token_seq"])
    claimed2 = pool.claim_idea(worker_id="w-002")
    assert claimed2 is not None
    assert claimed2["id"] != claimed["id"]
    assert int(claimed2["claim_token_seq"]) > first_seq


def test_mark_done_rejects_stale_claim_token(pool):
    pool.add("idea A", priority=1)
    claim = pool.claim_idea(worker_id="w-001")
    assert claim is not None

    stale_ok = pool.mark_done(
        claim["id"], metric_value=1.23, verdict="kept", claim_token="stale-token"
    )
    assert stale_ok is False
    assert len(pool.list_by_status("done")) == 0

    accepted = pool.mark_done(
        claim["id"],
        metric_value=1.23,
        verdict="kept",
        claim_token=claim["claim_token"],
    )
    assert accepted is True
    done = pool.list_by_status("done")
    assert len(done) == 1
    assert done[0]["result"]["metric_value"] == 1.23


def test_claim_idea_none_available(pool):
    result = pool.claim_idea(worker_id="w-001")
    assert result is None


def test_concurrent_adds(pool_file):
    """20 threads adding ideas concurrently — verify all 20 exist."""
    pool = IdeaPool(pool_file)

    def add_idea(i):
        return pool.add(f"concurrent idea {i}", priority=i)

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(add_idea, i) for i in range(20)]
        results = [f.result() for f in as_completed(futures)]

    assert len(results) == 20
    all_ideas = pool.all_ideas()
    assert len(all_ideas) == 20
    # All IDs should be unique
    ids = [idea["id"] for idea in all_ideas]
    assert len(set(ids)) == 20


def test_concurrent_claim(pool_file):
    """5 threads claiming from 5 ideas — verify no duplicates."""
    pool = IdeaPool(pool_file)
    for i in range(5):
        pool.add(f"claimable idea {i}", priority=i + 1)

    def claim(worker_idx):
        return pool.claim_idea(worker_id=f"w-{worker_idx:03d}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(claim, i) for i in range(5)]
        results = [f.result() for f in as_completed(futures)]

    # All 5 should be claimed (no None results)
    claimed = [r for r in results if r is not None]
    assert len(claimed) == 5
    # No duplicate IDs
    claimed_ids = [r["id"] for r in claimed]
    assert len(set(claimed_ids)) == 5
