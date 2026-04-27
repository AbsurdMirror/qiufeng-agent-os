from dataclasses import dataclass
from traceback import extract_tb, format_exception


class ModelResponseRepairableError(Exception):
    def __init__(
        self,
        *,
        reason_code: str,
        target_label: str,
        invalid_output: str,
        error_text: str,
    ) -> None:
        super().__init__(error_text)
        self.reason_code = reason_code
        self.target_label = target_label
        self.invalid_output = invalid_output
        self.error_text = error_text

    def to_dict(self) -> dict[str, str]:
        return {
            "reason_code": self.reason_code,
            "target_label": self.target_label,
            "invalid_output": self.invalid_output,
            "error_text": self.error_text,
        }

    def to_repair_message(self) -> "ModelMessage":
        from src.domain.models import ModelMessage

        return ModelMessage(
            role="user",
            content=(
                f"你的上一次{self.target_label}在解析阶段出错，请严格按照本轮规范重新输出。\n"
                "要求：只输出符合规范的结果，不要附加解释文本。\n"
                f"上一次{self.target_label}为: {self.invalid_output}\n"
                f"解析错误: {self.error_text}"
            ),
        )


@dataclass(frozen=True)
class ErrorReport:
    summary: str
    exception_type: str
    location: str
    stack_trace: str

    def to_user_message(self) -> str:
        return (
            f"{self.summary}\n"
            f"异常类型: {self.exception_type}\n"
            f"错误位置: {self.location}\n"
            f"调用栈:\n{self.stack_trace}"
        )


def build_error_report(
    error: BaseException,
    *,
    summary: str,
    max_frames: int = 6,
) -> ErrorReport:
    traceback_items = extract_tb(error.__traceback__)
    visible_frames = traceback_items[-max_frames:]
    if visible_frames:
        last_frame = visible_frames[-1]
        location = f"{last_frame.filename}:{last_frame.lineno} in {last_frame.name}"
    else:
        location = "unknown"

    stack_lines = format_exception(type(error), error, error.__traceback__)
    stack_trace = "".join(stack_lines).strip()
    return ErrorReport(
        summary=summary,
        exception_type=type(error).__name__,
        location=location,
        stack_trace=stack_trace,
    )


def format_user_facing_error(
    error: BaseException,
    *,
    summary: str,
    max_frames: int = 6,
) -> str:
    report = build_error_report(error, summary=summary, max_frames=max_frames)
    return report.to_user_message()
