from enum import Enum
from typing import Optional
from pydantic import BaseModel


class TaskMode(str, Enum):
    EXPLAIN = "EXPLAIN"
    PLAN = "PLAN"
    EXECUTE = "EXECUTE"
    SEARCH = "SEARCH"
    FIX = "FIX"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class Task(BaseModel):
    id: str
    userId: str
    repositoryId: Optional[str] = None
    mode: TaskMode
    status: TaskStatus
    prompt: str
    result: Optional[str] = None
    branchName: Optional[str] = None
    prUrl: Optional[str] = None
    createdAt: str
    updatedAt: str


class Repository(BaseModel):
    id: str
    userId: str
    fullName: str
    defaultBranch: str = "main"
    isActive: bool = False


class ProcessTaskRequest(BaseModel):
    """Payload the NestJS server sends when dispatching a task to the worker."""
    task_id: str
    user_id: str
    mode: TaskMode
    prompt: str
    repo_full_name: Optional[str] = None
    repo_default_branch: Optional[str] = None
    github_token: Optional[str] = None
    session_context: Optional[str] = None  # Phase B: injected session memory

