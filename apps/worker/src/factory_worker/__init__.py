"""Workflow executor process for the AI Software Factory.

Phase 1 provides the process shell only: it starts, verifies the database, and shuts down
gracefully. The durable job queue arrives in Phase 2 and graph execution in Phase 3.
"""

__version__ = "0.1.0"
