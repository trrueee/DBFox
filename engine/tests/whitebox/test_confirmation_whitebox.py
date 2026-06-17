import pytest
import threading
from engine.policy.confirmation import ConfirmationManager

# covers: CONF-1 token not exists
def test_conf1_not_exists():
    mgr = ConfirmationManager()
    ok, msg = mgr.validate_and_consume(
        "invalid-token", "confirm",
        expected_action="query", expected_datasource_id="ds-1", expected_details={}
    )
    assert not ok
    assert "无效或已过期" in msg

# covers: CONF-2 token expired
def test_conf2_expired():
    mgr = ConfirmationManager(ttl_seconds=-1)
    token = mgr.create_confirmation("ds-1", "query", {"sql": "SELECT 1"}, "confirm")
    ok, msg = mgr.validate_and_consume(
        token, "confirm",
        expected_action="query", expected_datasource_id="ds-1", expected_details={"sql": "SELECT 1"}
    )
    assert not ok
    assert "已过期" in msg

# covers: CONF-3 action mismatch
def test_conf3_action_mismatch():
    mgr = ConfirmationManager()
    token = mgr.create_confirmation("ds-1", "query", {"sql": "SELECT 1"}, "confirm")
    ok, msg = mgr.validate_and_consume(
        token, "confirm",
        expected_action="other_action", expected_datasource_id="ds-1", expected_details={"sql": "SELECT 1"}
    )
    assert not ok
    assert "操作类型不匹配" in msg

# covers: CONF-4 datasource mismatch
def test_conf4_datasource_mismatch():
    mgr = ConfirmationManager()
    token = mgr.create_confirmation("ds-1", "query", {"sql": "SELECT 1"}, "confirm")
    ok, msg = mgr.validate_and_consume(
        token, "confirm",
        expected_action="query", expected_datasource_id="ds-other", expected_details={"sql": "SELECT 1"}
    )
    assert not ok
    assert "数据源不匹配" in msg

# covers: CONF-5 details mismatch
def test_conf5_details_mismatch():
    mgr = ConfirmationManager()
    token = mgr.create_confirmation("ds-1", "query", {"sql": "SELECT 1"}, "confirm")
    ok, msg = mgr.validate_and_consume(
        token, "confirm",
        expected_action="query", expected_datasource_id="ds-1", expected_details={"sql": "SELECT 2"}
    )
    assert not ok
    assert "参数" in msg and "不匹配" in msg

# covers: CONF-6 confirm_text mismatch
def test_conf6_text_mismatch():
    mgr = ConfirmationManager()
    token = mgr.create_confirmation("ds-1", "query", {"sql": "SELECT 1"}, "confirm")
    ok, msg = mgr.validate_and_consume(
        token, "wrong_confirm",
        expected_action="query", expected_datasource_id="ds-1", expected_details={"sql": "SELECT 1"}
    )
    assert not ok
    assert "文本不匹配" in msg

# covers: CONF-7 all match
def test_conf7_success():
    mgr = ConfirmationManager()
    token = mgr.create_confirmation("ds-1", "query", {"sql": "SELECT 1"}, "confirm")
    ok, msg = mgr.validate_and_consume(
        token, "confirm",
        expected_action="query", expected_datasource_id="ds-1", expected_details={"sql": "SELECT 1"}
    )
    assert ok
    assert msg == ""

# covers: CONF-8 double consume
def test_conf8_double_consume():
    mgr = ConfirmationManager()
    token = mgr.create_confirmation("ds-1", "query", {"sql": "SELECT 1"}, "confirm")
    ok1, _ = mgr.validate_and_consume(
        token, "confirm",
        expected_action="query", expected_datasource_id="ds-1", expected_details={"sql": "SELECT 1"}
    )
    assert ok1
    ok2, msg2 = mgr.validate_and_consume(
        token, "confirm",
        expected_action="query", expected_datasource_id="ds-1", expected_details={"sql": "SELECT 1"}
    )
    assert not ok2
    assert "无效或已过期" in msg2

# covers: CONF-9 concurrent validate
def test_conf9_concurrent():
    mgr = ConfirmationManager()
    token = mgr.create_confirmation("ds-1", "query", {"sql": "SELECT 1"}, "confirm")
    
    results = []
    def attempt():
        ok, msg = mgr.validate_and_consume(
            token, "confirm",
            expected_action="query", expected_datasource_id="ds-1", expected_details={"sql": "SELECT 1"}
        )
        results.append(ok)
        
    t1 = threading.Thread(target=attempt)
    t2 = threading.Thread(target=attempt)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    assert results.count(True) == 1
    assert results.count(False) == 1
