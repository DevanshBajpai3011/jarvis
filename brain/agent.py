import logging
from typing import Optional, Tuple, Any
from brain.planner import TaskPlanner
from brain.state import ExecutionState
from brain.tools import execute_tool_call

logger = logging.getLogger(__name__)


class AutonomousAgent:
    """
    Autonomous execution agent that plans, tracks, and executes multi-step goals.
    """

    def __init__(self, planner: Optional[TaskPlanner] = None, state: Optional[ExecutionState] = None):
        self.planner = planner or TaskPlanner()
        self.state = state or ExecutionState()

    def _execute_step(self, step_obj: dict, brain: Any = None) -> Tuple[bool, str]:
        """
        Executes an individual step based on its action and arguments.
        """
        action = str(step_obj.get("action", "")).strip().lower()
        args = step_obj.get("args", {})
        if not isinstance(args, dict):
            args = {}

        try:
            if action == "open_app":
                app_name = args.get("app_name", "")
                res = execute_tool_call("open_application", {"app_name": app_name})
                success = "successfully" in res.lower() or "opened" in res.lower()
                return success, res

            elif action == "set_reminder":
                text = args.get("text", args.get("reminder_text", ""))
                time_str = args.get("time", args.get("time_str", ""))
                res = execute_tool_call("manage_reminder", {"action": "add", "reminder_text": text, "time_str": time_str})
                success = "failed" not in res.lower() and "cannot" not in res.lower()
                return success, res

            elif action == "run_script":
                script_name = args.get("script_name", "")
                res = execute_tool_call("execute_whitelisted_script", {"script_name": script_name})
                success = "successfully" in res.lower()
                return success, res

            elif action == "capture_screen":
                from vision import VisionCapturer
                vc = VisionCapturer()
                out = vc.capture_screen(args.get("output_filename", "temp_vision/screen.jpg"))
                if out:
                    return True, f"Screen captured successfully to {out}."
                return False, "Failed to capture screen."

            elif action == "speak":
                msg = args.get("message", "Step completed.")
                return True, msg

            else:
                res = execute_tool_call(action, args)
                if "Unknown tool" in res and brain:
                    res = brain.think(f"Execute task step: {action} with args {args}")
                success = "error" not in res.lower() and "failed" not in res.lower()
                return success, res

        except Exception as e:
            logger.error(f"[Agent] Exception during step execution ({action}): {e}")
            return False, f"Exception during step execution ({action}): {str(e)}"

    def execute_goal(self, user_goal: str, brain: Any = None, tts: Any = None) -> str:
        """
        Decomposes and executes a multi-step user goal autonomously.

        Args:
            user_goal (str): The overall user goal to execute.
            brain (Brain, optional): Gemini Brain instance for synthesis.
            tts (PiperTTS, optional): PiperTTS instance for spoken updates.

        Returns:
            str: Final spoken completion report or failure explanation.
        """
        if not user_goal or not user_goal.strip():
            return "No goal specified, sir."

        initial_msg = "Analyzing your request and forming an execution plan, sir."
        print(f"[Agent] {initial_msg}", flush=True)
        if tts:
            try:
                tts.speak(initial_msg)
            except Exception as e:
                logger.warning(f"TTS speak failed during initial update: {e}")

        plan = self.planner.decompose_goal(user_goal)
        if not plan:
            self.state.fail_plan("Could not decompose goal into executable sub-tasks.")
            fail_msg = "I was unable to form an execution plan for your request, sir."
            if tts:
                tts.speak(fail_msg)
            return fail_msg

        self.state.start_plan(user_goal, plan)

        for step_obj in plan:
            step_num = step_obj.get("step", 1)
            action = step_obj.get("action", "unknown")
            args = step_obj.get("args", {})

            print(f"[Agent] Executing Step {step_num}: {action} | Args: {args}", flush=True)
            logger.info(f"[Agent] Executing Step {step_num}: {action} | Args: {args}")

            success, result_msg = self._execute_step(step_obj, brain)
            self.state.mark_step_complete(step_num, result_msg)

            if not success:
                error_reason = f"Step {step_num} ({action}) encountered an issue: {result_msg}"
                self.state.fail_plan(error_reason)
                abort_msg = f"I could not complete the plan, sir. {result_msg}"
                print(f"[Agent Error] {abort_msg}", flush=True)
                if tts:
                    tts.speak(abort_msg)
                return abort_msg

        # Synthesize final spoken completion report
        summary = self.state.get_summary()
        if brain:
            prompt = (
                f"The user goal was: '{user_goal}'.\n"
                f"All execution steps completed successfully:\n{summary}\n\n"
                f"Synthesize a concise, polite, natural spoken J.A.R.V.I.S. completion report."
            )
            final_report = brain.think(prompt)
        else:
            final_report = f"All tasks for '{user_goal}' have been completed successfully, sir."

        print(f"[Agent] Final Completion Report: {final_report}", flush=True)
        if tts:
            tts.speak(final_report)

        return final_report
