import pytest
from unittest.mock import MagicMock
from engine.errors import DataSourceConnectionError
from engine.tunnel import TunnelManager, TunnelState

# covers: TUNNEL-1 First get
def test_tunnel1_first_get():
    mgr = TunnelManager()
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel.local_bind_port = 12345
    mgr._start_physical_tunnel = MagicMock(return_value=mock_tunnel)
    mgr.health_check = MagicMock(return_value=True)
    
    ds_dict = {"id": "ds-1", "host": "127.0.0.1", "port": 3306}
    t = mgr.get_or_reconnect(ds_dict)
    assert t == mock_tunnel
    mgr._start_physical_tunnel.assert_called_once_with(ds_dict)
    assert mgr.get_tunnel_state("ds-1") == TunnelState.CONNECTED

# covers: TUNNEL-2 Health check reuse
def test_tunnel2_reuse():
    mgr = TunnelManager()
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel.local_bind_port = 12345
    mgr._start_physical_tunnel = MagicMock(return_value=mock_tunnel)
    mgr.health_check = MagicMock(return_value=True)
    
    ds_dict = {"id": "ds-1"}
    t1 = mgr.get_or_reconnect(ds_dict)
    t2 = mgr.get_or_reconnect(ds_dict)
    assert t1 == t2
    assert mgr._start_physical_tunnel.call_count == 1

# covers: TUNNEL-3 Self healing reconnect success
def test_tunnel3_reconnect_success():
    mgr = TunnelManager()
    mock_tunnel1 = MagicMock()
    mock_tunnel1.is_active = True
    mock_tunnel1.local_bind_port = 12345
    
    mock_tunnel2 = MagicMock()
    mock_tunnel2.is_active = True
    mock_tunnel2.local_bind_port = 54321
    
    mgr._start_physical_tunnel = MagicMock(side_effect=[mock_tunnel1, mock_tunnel2])
    mgr.health_check = MagicMock(return_value=True)
    ds_dict = {"id": "ds-1"}
    t1 = mgr.get_or_reconnect(ds_dict)
    assert t1 == mock_tunnel1
    
    mgr.health_check = MagicMock(return_value=False)
    t2 = mgr.get_or_reconnect(ds_dict)
    assert t2 == mock_tunnel2
    mock_tunnel1.stop.assert_called_once()
    assert mgr.get_tunnel_state("ds-1") == TunnelState.CONNECTED

# covers: TUNNEL-4 Reconnect failure
def test_tunnel4_reconnect_failure():
    mgr = TunnelManager()
    mock_tunnel1 = MagicMock()
    mock_tunnel1.is_active = True
    mock_tunnel1.local_bind_port = 12345
    
    mgr._start_physical_tunnel = MagicMock(side_effect=[mock_tunnel1, Exception("SSH error")])
    mgr.health_check = MagicMock(return_value=True)
    ds_dict = {"id": "ds-1"}
    t1 = mgr.get_or_reconnect(ds_dict)
    assert t1 == mock_tunnel1
    
    mgr.health_check = MagicMock(return_value=False)
    with pytest.raises(DataSourceConnectionError) as exc:
        mgr.get_or_reconnect(ds_dict)
    assert "自愈重连失败" in str(exc.value)
    assert mgr.get_tunnel_state("ds-1") == TunnelState.FAILED

# covers: TUNNEL-5 Concurrent request lock protection
def test_tunnel5_concurrent_creation():
    mgr = TunnelManager()
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel.local_bind_port = 12345
    mgr._start_physical_tunnel = MagicMock(return_value=mock_tunnel)
    mgr.health_check = MagicMock(return_value=True)
    assert not mgr._lock.locked()

# covers: TUNNEL-6 Stop exception swallowed
def test_tunnel6_stop_exception_swallowed():
    mgr = TunnelManager()
    mock_tunnel1 = MagicMock()
    mock_tunnel1.is_active = True
    mock_tunnel1.local_bind_port = 12345
    mock_tunnel1.stop.side_effect = Exception("Stop failed")
    
    mock_tunnel2 = MagicMock()
    mock_tunnel2.is_active = True
    mock_tunnel2.local_bind_port = 54321
    
    mgr._start_physical_tunnel = MagicMock(side_effect=[mock_tunnel1, mock_tunnel2])
    mgr.health_check = MagicMock(return_value=True)
    ds_dict = {"id": "ds-1"}
    mgr.get_or_reconnect(ds_dict)
    
    mgr.health_check = MagicMock(return_value=False)
    t = mgr.get_or_reconnect(ds_dict)
    assert t == mock_tunnel2
    mock_tunnel1.stop.assert_called_once()
