# dbfox.workspace

Official System DLC for Project-scoped local workspaces. The DLC owns the
workspace binding, resource discovery/resolution, bounded file read/search
operations, Agent tools, context contribution, artifact contracts, Connector,
and file Dock. Core owns only the native folder-picker boundary and generic DLC
host.

Extension API v2 does not yet provide an isolated-process execution path for
installable DLC tools. File mutation therefore remains deliberately
unregistered: DBFox does not weaken the Tool Runtime's filesystem-write
boundary to simulate support. It can be enabled when the DLC worker protocol
can materialize signed package tools in the isolated worker.
