# Simple in-memory store for pending task results
# For a real application, this would need to be more robust (e.g., Redis, DB)
# and handle session-specificity if tasks are user-dependent.

# Structure: {task_id: result_data}
PENDING_TASK_RESULTS: dict[str, any] = {}

def set_task_result(task_id: str, result: any):
    """Stores the result of a completed task."""
    PENDING_TASK_RESULTS[task_id] = result
    print(f"PendingTasksStore: Result set for task_id {task_id}")

def get_task_result(task_id: str) -> any:
    """Retrieves and removes the result of a task."""
    result = PENDING_TASK_RESULTS.pop(task_id, None)
    if result:
        print(f"PendingTasksStore: Result retrieved and removed for task_id {task_id}")
    else:
        print(f"PendingTasksStore: No result found for task_id {task_id} on get_task_result")
    return result

def peek_task_result(task_id: str) -> any:
    """Retrieves the result of a task without removing it."""
    result = PENDING_TASK_RESULTS.get(task_id, None)
    if result:
        print(f"PendingTasksStore: Result peeked for task_id {task_id}")
    else:
        print(f"PendingTasksStore: No result found for task_id {task_id} on peek_task_result")
    return result

def clear_all_pending_tasks():
    """Clears all pending tasks from the store. Useful for testing or resets."""
    count = len(PENDING_TASK_RESULTS)
    PENDING_TASK_RESULTS.clear()
    print(f"PendingTasksStore: Cleared all {count} pending tasks.")

def list_pending_tasks() -> list[str]:
    """Lists all task_ids currently in the store."""
    return list(PENDING_TASK_RESULTS.keys())
```
