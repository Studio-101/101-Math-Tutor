import os
from typing import Callable, Optional
from PIL import Image
import io

from google import genai
from google.genai import types

from core.skills_loader import load_skill_prompt
from core.code_runner import execute_python_code
from core.logger import TrajectoryLogger


class GeminiTutorEngine:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set. Please provide a valid Gemini API key.")
        
        self.model = model
        self.client = genai.Client(api_key=self.api_key)
        
        # Load skill prompts directly from SKILL.md
        self.coordinator_prompt = load_skill_prompt("tutor_coordinator")
        self.solver_prompt = load_skill_prompt("math_solver")
        self.tutor_prompt = load_skill_prompt("shape_tutor")

    def coordinate_problem(
        self,
        text_input: str = "",
        image_bytes: Optional[bytes] = None,
        logger: Optional[TrajectoryLogger] = None,
    ) -> str:
        """
        Stage 0: tutor_coordinator
        Transcribes/analyzes the problem and breaks it down for user confirmation.
        """
        if logger:
            logger.log("USER", "USER_INPUT", text_input if text_input else "[上傳題目圖片]")
            logger.log("SYSTEM", "SYSTEM_PROMPT_COORDINATOR", self.coordinator_prompt)
        contents = []
        if image_bytes:
            image = Image.open(io.BytesIO(image_bytes))
            contents.append(image)
            prompt_text = "這是學生上傳的數學題目圖片。"
            if text_input and text_input.strip():
                prompt_text += f"\n學生特別附帶之說明或備註：\n{text_input.strip()}\n（若學生有指定解特定小題或特定要求，請務必嚴格遵循學生指定範圍處理）"
            prompt_text += (
                "\n請嚴格依據 tutor_coordinator 的規範，使用純文字與常見 Unicode 數學符號（嚴禁 LaTeX），"
                "辨識圖中題目，並拆解已知條件與求解目標，詢問學生是否正確。"
            )
            contents.append(prompt_text)
        else:
            contents.append(
                f"學生輸入的數學題目如下：\n{text_input}\n\n"
                "請嚴格依據 tutor_coordinator 的規範，將題目拆解為原子已知條件與求解目標，詢問學生是否正確。"
            )

        config = types.GenerateContentConfig(
            system_instruction=self.coordinator_prompt,
            temperature=0.2,
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )
        res_text = response.text.strip()
        if logger:
            logger.log("COORDINATOR", "COORDINATOR_RESPONSE", res_text)
        return res_text

    def solve_with_verification(
        self,
        confirmed_problem: str,
        log_callback: Optional[Callable[[dict], None]] = None,
        logger: Optional[TrajectoryLogger] = None,
    ) -> tuple[str, list[dict]]:
        """
        Stage 1: math_solver
        Solves the confirmed problem using dual verification with local Python (SymPy) execution.
        Captures all code executions and returns (final_report, tool_logs).
        """
        if logger:
            logger.log("SYSTEM", "SYSTEM_PROMPT_SOLVER", self.solver_prompt)

        tool_logs = []

        def execute_math_verification_script(python_code: str) -> str:
            """
            撰寫並執行 Python 數學驗證腳本（可使用 sympy, math, fractions）。
            執行後回傳 stdout 與 stderr。
            """
            if logger:
                logger.log("SOLVER", "SOLVER_TOOL_CALL", python_code, code=python_code)

            success, output = execute_python_code(python_code)
            log_entry = {
                "code": python_code,
                "output": output,
                "success": success,
            }
            tool_logs.append(log_entry)

            if logger:
                logger.log(
                    "TOOL_RUNNER",
                    "TOOL_EXECUTION_RESULT",
                    output,
                    success=success,
                    output=output,
                )

            if log_callback:
                log_callback(log_entry)
            return f"[Execution Success: {success}]\nOutput:\n{output}"

        # Initialize chat with math_solver instructions and the verification tool
        config = types.GenerateContentConfig(
            system_instruction=self.solver_prompt,
            tools=[execute_math_verification_script],
            temperature=0.1,
        )

        chat = self.client.chats.create(model=self.model, config=config)

        prompt = (
            f"已確認的題目如下：\n{confirmed_problem}\n\n"
            "【執行任務指令】\n"
            "請嚴格依照 math_solver 規範執行：\n"
            "1. 題意重述與已知條件條列（原子化）。\n"
            "2. MathQ-Verify 檢驗。\n"
            "3. 【強制要求】你必須調用 `execute_math_verification_script` 工具來執行實際的 Python/SymPy 程式碼！\n"
            "   程式碼中必須包含兩種完全不同類別的解題驗證方法（【路徑 A】與【路徑 B】），並在程式中比對兩者結果。\n"
            "   嚴禁在回答中心算或直接給出答案，所有數值結論必須來自該工具的真實執行輸出。\n"
            "4. 根據工具執行回傳之輸出，判定雙軌一致性。\n"
            "5. 產出詳細的內部報告（包含正確答案、分步解法、學生易錯點），供後續教學使用。"
        )

        if logger:
            logger.log("COORDINATOR", "SOLVER_TASK_DELEGATION", prompt)

        response = chat.send_message(prompt)
        final_report = response.text or "驗證完成，內部報告已產生。"
        final_report = final_report.strip()

        if logger:
            logger.log("SOLVER", "SOLVER_REPORT", final_report)

        return final_report, tool_logs

    def start_tutoring_first_message(
        self,
        confirmed_problem: str,
        solver_report: str,
        logger: Optional[TrajectoryLogger] = None,
    ) -> str:
        """Generates the opening Socratic question from shape_tutor."""
        tutor_system_instruction = (
            f"{self.tutor_prompt}\n\n"
            "=== [內部驗證報告 (供你掌握正解與解題步驟，切勿直接提供給學生)] ===\n"
            f"{solver_report}\n\n"
            "=== [學生面對的題目] ===\n"
            f"{confirmed_problem}\n"
        )
        if logger:
            logger.log("SYSTEM", "SYSTEM_PROMPT_TUTOR", tutor_system_instruction)

        prompt = (
            "學生已經確認題目並準備好開始學習了。"
            "請依據 shape_tutor 的 SHAPE 微鷹架原則，向學生親切問好，"
            "並提出引導解題的第一個小問題或觀察點（切勿一次講完或透露答案）。"
        )
        config = types.GenerateContentConfig(
            system_instruction=tutor_system_instruction,
            temperature=0.4,
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=[prompt],
            config=config,
        )
        res_text = response.text.strip()
        if logger:
            logger.log("SHAPE_TUTOR", "TUTOR_RESPONSE", res_text)
        return res_text

    def continue_tutoring_with_history(
        self,
        confirmed_problem: str,
        solver_report: str,
        chat_history: list[dict],
        logger: Optional[TrajectoryLogger] = None,
    ) -> str:
        """
        Sends the complete dialogue history to shape_tutor.
        100% stateless, crash-proof, and resilient across Streamlit reruns.
        """
        tutor_system_instruction = (
            f"{self.tutor_prompt}\n\n"
            "=== [內部驗證報告 (供你掌握正解與解題步驟，切勿直接提供給學生)] ===\n"
            f"{solver_report}\n\n"
            "=== [學生面對的題目] ===\n"
            f"{confirmed_problem}\n"
        )

        contents = []
        for msg in chat_history:
            role = "user" if msg["role"] == "user" else "model"
            parts = []
            img_data = msg.get("image_bytes")
            if img_data:
                try:
                    parts.append(types.Part.from_bytes(data=img_data, mime_type="image/jpeg"))
                except Exception as e:
                    pass
            text_str = msg.get("content", "")
            if img_data:
                augmented_text = (
                    f"【學生手寫草稿照片上傳】\n"
                    f"學生備註：{text_str}\n\n"
                    "請仔細審視圖中學生的手寫步驟與符號，對照內部驗證報告中的步驟，"
                    "精準指認學生算到哪裡、哪一步正確、是否有正負號或運算錯誤，並進行親切溫和的微鷹架引導。"
                )
                parts.append(types.Part.from_text(text=augmented_text))
            else:
                parts.append(types.Part.from_text(text=text_str))

            contents.append(types.Content(role=role, parts=parts))

        if logger and chat_history:
            last_msg = chat_history[-1]
            log_desc = last_msg.get("content", "")
            if last_msg.get("image_bytes"):
                log_desc = f"[上傳手寫草稿圖片] {log_desc}"
            logger.log("USER", "USER_INPUT", log_desc)

        config = types.GenerateContentConfig(
            system_instruction=tutor_system_instruction,
            temperature=0.4,
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )
        res_text = response.text.strip()
        if logger:
            logger.log("SHAPE_TUTOR", "TUTOR_RESPONSE", res_text)
        return res_text
