import datetime
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ExecutionState:
    """
    Tracks and maintains execution state, step progress, and audit details
    for multi-step autonomous plans.
    """

    VALID_STATUSES = {"IDLE", "PLANNING", "EXECUTING", "COMPLETED", "FAILED"}

    def __init__(self):
        self.current_goal: str = ""
        self.plan: List[Dict[str, Any]] = []
        self.completed_steps: List[Dict[str, Any]] = []
        self.status: str = "IDLE"
        self.error_reason: Optional[str] = None
        self.start_time: Optional[datetime.datetime] = None
        self.end_time: Optional[datetime.datetime] = None

    def start_plan(self, goal: str, plan: List[Dict[str, Any]]) -> None:
        """
        Initializes execution state for a new multi-step plan.

        Args:
            goal (str): The parent goal or objective description.
            plan (List[Dict[str, Any]]): The list of planned step objects.
        """
        self.current_goal = goal.strip() if goal else ""
        self.plan = plan if plan else []
        self.completed_steps = []
        self.status = "EXECUTING" if self.plan else "IDLE"
        self.error_reason = None
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.end_time = None
        logger.info(f"[ExecutionState] Started plan for goal: '{self.current_goal}' with {len(self.plan)} steps.")

    def mark_step_complete(self, step_number: int, result: Any) -> None:
        """
        Records completion details for a specific plan step.

        Args:
            step_number (int): The 1-based step number completed.
            result (Any): Output, status message, or return value of the step.
        """
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        completion_record = {
            "step": step_number,
            "result": result,
            "completed_at": timestamp,
        }
        self.completed_steps.append(completion_record)
        logger.info(f"[ExecutionState] Step {step_number} completed.")

        # Check if all steps in plan are done
        if len(self.completed_steps) >= len(self.plan) and self.status == "EXECUTING":
            self.status = "COMPLETED"
            self.end_time = datetime.datetime.now(datetime.timezone.utc)
            logger.info(f"[ExecutionState] Plan completed successfully for goal: '{self.current_goal}'")

    def fail_plan(self, reason: str) -> None:
        """
        Marks overall plan execution as failed with error details.

        Args:
            reason (str): Description of the failure or exception encountered.
        """
        self.status = "FAILED"
        self.error_reason = str(reason).strip()
        self.end_time = datetime.datetime.now(datetime.timezone.utc)
        logger.error(f"[ExecutionState] Plan failed for goal: '{self.current_goal}'. Reason: {self.error_reason}")

    def get_summary(self) -> str:
        """
        Generates a human-readable progress status summary.

        Returns:
            str: Natural language summary of current execution state.
        """
        if self.status == "IDLE":
            return "Execution state is currently idle."

        total_steps = len(self.plan)
        done_steps = len(self.completed_steps)

        summary_lines = [
            f"Goal: '{self.current_goal}'",
            f"Status: {self.status}",
            f"Progress: {done_steps}/{total_steps} steps completed."
        ]

        if self.completed_steps:
            summary_lines.append("Completed Steps:")
            for item in self.completed_steps:
                summary_lines.append(f"  - Step {item['step']}: {item['result']}")

        if self.status == "FAILED" and self.error_reason:
            summary_lines.append(f"Failure Reason: {self.error_reason}")

        return "\n".join(summary_lines)
