from open_researcher.resource_scheduler import (
    candidate_single_gpu_saturation_profiles,
    classify_single_gpu_saturation_status,
    select_single_gpu_saturation_profile,
    single_gpu_saturation_budget_mb,
)


def test_single_gpu_saturation_budget_reserves_headroom():
    budget_mb, headroom_mb = single_gpu_saturation_budget_mb(
        total_memory_mb=49152,
        free_memory_mb=46080,
        headroom_ratio=0.10,
        minimum_headroom_mb=2048,
    )

    assert headroom_mb == 4915
    assert budget_mb == 41165


def test_candidate_single_gpu_saturation_profiles_include_implicit_and_matching_config_profiles():
    idea = {
        "resource_request": {"gpu_count": 1, "gpu_mem_mb": 12000},
        "execution_shape": {"batch_size": 8},
        "workload_label": "train",
    }
    profiles = candidate_single_gpu_saturation_profiles(
        idea,
        resource_profiles={
            "single_gpu_small": {"gpu_count": 1, "gpu_mem_mb": 10000, "workload_label": "train"},
            "single_gpu_large": {"gpu_count": 1, "gpu_mem_mb": 16000, "workload_label": "train"},
            "eval_shape": {"gpu_count": 1, "gpu_mem_mb": 4096, "workload_label": "eval"},
        },
        default_gpu_mem_mb=4096,
    )

    assert [profile["name"] for profile in profiles] == [
        "single_gpu_small",
        "__idea_default__",
        "single_gpu_large",
    ]


def test_select_single_gpu_saturation_profile_prefers_highest_safe_profile():
    idea = {
        "resource_request": {"gpu_count": 1, "gpu_mem_mb": 12000},
        "workload_label": "train",
    }
    selection = select_single_gpu_saturation_profile(
        idea,
        resource_profiles={
            "single_gpu_small": {"gpu_count": 1, "gpu_mem_mb": 10000, "expected_memory_mb": 11000},
            "single_gpu_large": {"gpu_count": 1, "gpu_mem_mb": 14000, "expected_memory_mb": 15000},
            "single_gpu_too_big": {"gpu_count": 1, "gpu_mem_mb": 20000, "expected_memory_mb": 21000},
        },
        gpu={"host": "local", "device": 0, "memory_total": 49152, "memory_free": 24576, "reservations": []},
        default_gpu_mem_mb=4096,
        headroom_ratio=0.10,
        minimum_headroom_mb=2048,
    )

    assert selection["supported"] is True
    assert selection["selected_profile"]["name"] == "single_gpu_large"
    assert selection["gpu_budget_mb"] > 0
    assert [profile["name"] for profile in selection["qualification_profiles"]] == [
        "single_gpu_small",
        "__idea_default__",
        "single_gpu_large",
        "single_gpu_too_big",
    ]


def test_classify_single_gpu_saturation_status_uses_peak_or_expected_memory():
    assert (
        classify_single_gpu_saturation_status(
            gpu_budget_mb=16000,
            observed_peak_gpu_mem_mb=15000,
        )
        == "saturated"
    )
    assert (
        classify_single_gpu_saturation_status(
            gpu_budget_mb=16000,
            expected_peak_gpu_mem_mb=9000,
        )
        == "underfilled"
    )
    assert classify_single_gpu_saturation_status(gpu_budget_mb=0) == "unsupported"
