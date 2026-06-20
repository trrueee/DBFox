from __future__ import annotations

from engine.agent_core.result_profiler import profile_result


def test_profile_result_uses_chinese_visible_text():
    profile = profile_result(
        question="分析小红书工具使用情况",
        columns=["tool_name", "usage_count"],
        rows=[
            {"tool_name": "图片工作室", "usage_count": 150},
            {"tool_name": "视频号小红书", "usage_count": 60},
            {"tool_name": "活动发布", "usage_count": 2},
        ],
    )

    visible_text = "\n".join(profile.notable_facts + profile.anomalies + profile.limitations)
    assert "The result contains" not in visible_text
    assert "The most frequent" not in visible_text
    assert "ranges from" not in visible_text
    assert "profile is based" not in visible_text
    assert "结果包含 3 行" in profile.notable_facts[0]
    assert any("tool_name 中最常见的值是 图片工作室" in fact for fact in profile.notable_facts)
    assert any("usage_count 的范围是 2 到 150" in fact for fact in profile.notable_facts)
