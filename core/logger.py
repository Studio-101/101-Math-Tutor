import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TrajectoryLogger:
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.events: list[dict[str, Any]] = []
        self.step_index = 0

    def log(
        self,
        source: str,
        event_type: str,
        content: Any,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        Records a raw unedited step in the trajectory.
        """
        now = datetime.now()
        entry = {
            "step_index": self.step_index,
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "source": source,
            "type": event_type,
            "content": content,
            **extra,
        }
        self.events.append(entry)
        self.step_index += 1
        return entry

    def to_jsonl(self) -> str:
        """Converts entire trajectory to raw JSONL string."""
        lines = [json.dumps(ev, ensure_ascii=False) for ev in self.events]
        return "\n".join(lines)

    def to_markdown_transcript(self, problem_title: str = "數學解題紀錄") -> str:
        """Generates a human-readable markdown transcript."""
        md = [
            f"# {problem_title} 完整逐字稿日誌 (Conversation Transcript)",
            f"- **記錄時間**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)",
            f"- **會話識別碼**：`{self.session_id}`",
            "",
            "---",
            "",
        ]

        for ev in self.events:
            src = ev["source"]
            ev_type = ev["type"]
            ts = ev["timestamp"]
            content = ev["content"]

            if ev_type == "USER_INPUT":
                md.append(f"### [User (學生)] ── {ts}\n{content}\n\n---")
            elif ev_type == "COORDINATOR_RESPONSE":
                md.append(f"### [tutor_coordinator (前台轉錄確認)] ── {ts}\n{content}\n\n---")
            elif ev_type == "SOLVER_TOOL_CALL":
                code = ev.get("code", content)
                md.append(
                    f"### [math_solver ➔ 呼叫 Python 雙軌驗證沙盒] ── {ts}\n"
                    f"```python\n{code}\n```\n\n---"
                )
            elif ev_type == "TOOL_EXECUTION_RESULT":
                out = ev.get("output", content)
                success = ev.get("success", True)
                status = "✅ 執行成功" if success else "❌ 執行失敗"
                md.append(
                    f"### [Python 沙盒真實輸出 ({status})] ── {ts}\n"
                    f"```text\n{out}\n```\n\n---"
                )
            elif ev_type == "SOLVER_REPORT":
                md.append(f"### [math_solver (內部驗證報告)] ── {ts}\n{content}\n\n---")
            elif ev_type == "TUTOR_RESPONSE":
                md.append(f"### [shape_tutor (家教引導)] ── {ts}\n{content}\n\n---")

        return "\n".join(md)

    def save_to_disk(
        self,
        folder_prefix: str = "run",
        problem_title: str = "數學解題紀錄",
        solver_report: str = "",
        python_scripts: Optional[list[str]] = None,
    ) -> Optional[Path]:
        """
        No-op: logs are no longer saved to disk.
        """
        return None
