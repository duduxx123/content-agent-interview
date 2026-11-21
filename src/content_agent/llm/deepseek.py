import json
import os
import re
from collections import Counter
from pathlib import Path

import aiohttp
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from content_agent.modules.interaction import classify_topics

from content_agent.schemas import (
    AgentInput,
    AgentOutput,
    CommentAnalysis,
    InteractionResult,
)


MAX_SEMANTIC_COMMENTS = 60
MAX_COMMENT_CHARS = 80


class DeepSeekAPIError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"DeepSeek API returned HTTP {status_code}")


class _RefinedSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    suggested_script: str = Field(min_length=1, max_length=500)
    recommended_action: str = Field(min_length=1, max_length=200)


class _RefinementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[_RefinedSuggestion]
    decision_summary: str | None = Field(default=None, max_length=800)


class _SemanticInteractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hot_words: dict[str, int] = Field(default_factory=dict)
    questions: list[str] = Field(default_factory=list)
    negative_feedback: list[str] = Field(default_factory=list)
    purchase_intent: list[str] = Field(default_factory=list)
    repeated_questions: dict[str, int] | list[object] = Field(default_factory=list)
    repeated_comments: dict[str, int] | list[object] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)


class DeepSeekClient:
    """Small async DeepSeek chat-completions client using environment config."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-flash",
        timeout_seconds: float = 20,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "DeepSeekClient | None":
        config_path = Path(__file__).resolve().parents[3] / "config" / "agent.json"
        try:
            agent_config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            agent_config = {}
        if not agent_config.get("deepseek_enabled", False):
            return None

        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(
            api_key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip(),
            timeout_seconds=float(os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "20")),
        )

    async def _post_json(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> str:
        request_data = {
            "model": self._model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=request_data,
            ) as response:
                if response.status >= 400:
                    # Avoid including provider response bodies or authorization data in logs.
                    raise DeepSeekAPIError(response.status)
                response_data = await response.json()

        content = response_data["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek returned empty JSON content")
        return content

    async def refine(self, payload: AgentInput, output: AgentOutput) -> AgentOutput:
        """Polish rule-generated drafts with stage-aware phrasing."""
        stage = output.stage_state
        stage_context = {
            "current_stage": (
                stage.current_stage if stage else payload.live_state.current_stage
            ),
            "stage_goal": stage.stage_goal if stage else "",
            "stage_focus": stage.stage_focus if stage else "",
            "stage_progress": round(stage.stage_progress, 3) if stage else None,
            "next_stage": stage.next_stage if stage else None,
            "next_stage_preparation": (
                stage.next_stage_preparation if stage else []
            ),
            "source": stage.source if stage else "clock",
            "notes": stage.notes if stage else [],
        }
        system_prompt = (
            "你是直播提词润色助手。根据 stage_context 的当前阶段调整语气、句式和推荐动作："
            "预热期暖场、引导关注和停留；产品讲解期讲清卖点和用法；"
            "答疑期先回应问题并解释边界；促单期围绕价格、规格、活动和库存推动下单，"
            "但不制造虚假稀缺；收尾期总结、感谢和预告。"
            "只改写给定草稿，不得增加商品资料中没有的事实、成分、适用人群、功效、价格或优惠承诺；"
            "保留草稿的意图和商品边界；不要回应弹幕，不要输出解释。"
            "另外用 2-3 句中文写一段 decision_summary，解释本轮为什么这样排序："
            "结合阶段、识别到的主题、decision_notes 和候选建议；只做解释，不新增商品事实或承诺。"
            "请输出 json，格式必须为："
            '{"suggestions":[{"index":0,"suggested_script":"...","recommended_action":"..."}],'
            '"decision_summary":"..."}'
        )
        user_data = {
            "stage_context": stage_context,
            "product_facts": payload.product.model_dump(),
            "recognized_topics": payload.comment_analysis.hot_words,
            "decision_notes": output.decision_notes,
            "drafts": [
                {
                    "index": index,
                    "topic": item.topic,
                    "intent": item.intent,
                    "priority": item.priority,
                    "score": item.score,
                    "trigger_reason": item.trigger_reason,
                    "suggested_script": item.suggested_script,
                    "recommended_action": item.recommended_action,
                }
                for index, item in enumerate(output.suggestions)
            ],
        }
        content = await self._post_json(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "请按要求润色以下草稿，并只返回指定结构的 JSON：\n"
                    + json.dumps(user_data, ensure_ascii=False),
                },
            ],
            max_tokens=1200,
            temperature=0.2,
        )
        parsed = _RefinementResponse.model_validate_json(content)

        expected = set(range(len(output.suggestions)))
        actual = [item.index for item in parsed.suggestions]
        if len(actual) != len(expected) or set(actual) != expected:
            raise ValueError("DeepSeek returned an incomplete suggestion set")

        for refined in parsed.suggestions:
            original = output.suggestions[refined.index]
            original.suggested_script = refined.suggested_script.strip()
            original.recommended_action = refined.recommended_action.strip()
        output.ai_decision_summary = (parsed.decision_summary or "").strip()[:600]
        output.generation_mode = "deepseek"
        return output

    @staticmethod
    def _clean_text(value: object, limit: int) -> str:
        return " ".join(str(value).split())[:limit]

    @classmethod
    def _clean_list(
        cls,
        values: list[object],
        *,
        limit: int = 8,
        text_limit: int = 80,
    ) -> list[str]:
        result: list[str] = []
        for value in values:
            text = cls._clean_text(value, text_limit)
            if text and text not in result:
                result.append(text)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _normalize_topics(values: dict[str, int]) -> dict[str, int]:
        """Map model topic labels onto the product/decision topic vocabulary."""
        normalized: Counter[str] = Counter()
        for label, count in values.items():
            topics = classify_topics(label)
            if topics:
                for topic in topics:
                    normalized[topic] += count
            else:
                normalized[label] += count
        return dict(normalized.most_common(12))

    @classmethod
    def _clean_pairs(
        cls,
        values: dict[str, int] | list[object],
        *,
        limit: int = 8,
        min_count: int = 2,
    ) -> dict[str, int]:
        if isinstance(values, dict):
            return cls._clean_counts(values, limit=limit, min_count=min_count)

        cleaned: list[tuple[str, int]] = []
        for value in values:
            if isinstance(value, dict):
                text = cls._clean_text(
                    value.get("question")
                    or value.get("text")
                    or value.get("content")
                    or "",
                    80,
                )
                raw_count = (
                    value.get("count")
                    or value.get("times")
                    or value.get("num")
                    or 0
                )
                number = re.search(r"\d+", str(raw_count))
                if text and number:
                    count = int(number.group(0))
                    if count >= min_count:
                        cleaned.append((text, min(count, 999)))
                continue

            text = cls._clean_text(value, 80)
            match = (
                re.search(r"[（(]\s*(\d+)\s*次\s*[）)]", text)
                or re.search(r"[x×]\s*(\d+)\s*$", text)
                or re.search(r"[：:]\s*(\d+)\s*次?\s*$", text)
            )
            if not match:
                continue
            count = int(match.group(1))
            key = text[: match.start()].strip(" ：:（(")
            if key and count >= min_count:
                cleaned.append((key, min(count, 999)))
        cleaned.sort(key=lambda item: item[1], reverse=True)
        return dict(cleaned[:limit])

    @classmethod
    def _clean_counts(
        cls,
        values: dict[str, int],
        *,
        limit: int = 12,
        min_count: int = 1,
    ) -> dict[str, int]:
        cleaned: list[tuple[str, int]] = []
        for key, value in values.items():
            text = cls._clean_text(key, 40)
            if not text:
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count < min_count:
                continue
            cleaned.append((text, min(count, 999)))
        cleaned.sort(key=lambda item: item[1], reverse=True)
        return dict(cleaned[:limit])

    @staticmethod
    def _select_comments(comments: list[str]) -> tuple[list[str], int]:
        selected: list[str] = []
        for comment in comments:
            text = " ".join(str(comment).split())
            if text:
                selected.append(text[:MAX_COMMENT_CHARS])
        return selected[-MAX_SEMANTIC_COMMENTS:], len(selected)

    @staticmethod
    def _repair_semantic_json(text: str) -> str:
        """Repair a common model mistake: {"a（2次）","b（2次）"} for a list field."""
        for field in ("repeated_questions", "repeated_comments"):
            pattern = re.compile(rf'("{field}"\s*:\s*)\{{([^{{}}]*)\}}')

            def repl(match: re.Match[str]) -> str:
                body = match.group(2)
                if ":" in body:
                    return match.group(0)
                return f"{match.group(1)}[{body}]"

            text = pattern.sub(repl, text)
        return text

    @classmethod
    def _parse_semantic(cls, content: str) -> _SemanticInteractionResponse:
        text = content.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            # strict=False tolerates literal control characters inside strings.
            data = json.loads(text, strict=False)
        except json.JSONDecodeError:
            data = json.loads(cls._repair_semantic_json(text), strict=False)
        return _SemanticInteractionResponse.model_validate(data)

    async def analyze_interactions(
        self,
        comments: list[str],
        *,
        stage: str | None = None,
    ) -> InteractionResult:
        """Use the model to understand a window of danmaku instead of keyword counting."""
        selected, total = self._select_comments(comments)
        if not selected:
            return InteractionResult(
                comment_analysis=CommentAnalysis(),
                summary=["AI 语义分析：本窗口没有可分析文本。"],
                mode="deepseek",
            )

        system_prompt = (
            "你是直播弹幕语义分析助手。只依据用户提供的弹幕文本，不补充未出现的信息，"
            "不输出用户名或其他隐私信息。请完成："
            "1) 归纳高频关注主题及出现次数；主题键优先使用：价格、肤质、成分、功效、用法、"
            "试用/购买，其他主题可保留；2) 提取问题、负面反馈、购买意向；"
            "3) 合并语义相近的重复问题，给出代表问法和次数；"
            "4) 识别重复刷屏文本及次数；5) 输出不超过 3 条中文摘要。"
            "没有内容的字段用空数组或空对象。所有字符串使用中文标点，"
            "不要使用英文双引号、反斜杠或换行符。只输出 JSON，格式必须为："
            '{"hot_words":{},"questions":[],"negative_feedback":[],"purchase_intent":[],'
            '"repeated_questions":["代表问法（2次）"],'
            '"repeated_comments":["刷屏文本（3次）"],"summary":[]}'
        )
        if stage:
            system_prompt += (
                f"当前直播阶段是：{stage}。理解弹幕时结合阶段重点，"
                "但不要改变弹幕原意，也不要补充未出现的信息。"
            )
        user_data = {
            "stage": stage,
            "comments": selected,
            "comment_count": total,
            "analyzed_count": len(selected),
        }
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "请语义分析以下弹幕，并只返回指定结构的 JSON：\n"
                + json.dumps(user_data, ensure_ascii=False),
            },
        ]
        content = await self._post_json(
            messages,
            max_tokens=1200,
            temperature=0.1,
        )
        try:
            parsed = self._parse_semantic(content)
        except (json.JSONDecodeError, ValidationError):
            # A model occasionally emits unescaped quotes or a stray newline.
            # Retry once with a strict JSON reminder before falling back.
            retry_messages = [
                *messages,
                {"role": "assistant", "content": content[:4000]},
                {
                    "role": "user",
                    "content": (
                        "上面的输出不是合法 JSON。请重新输出严格合法的 JSON 对象；"
                        "字符串内不要使用英文双引号、反斜杠或换行符，只输出 JSON。"
                    ),
                },
            ]
            content = await self._post_json(
                retry_messages,
                max_tokens=1200,
                temperature=0.0,
            )
            parsed = self._parse_semantic(content)

        analysis = CommentAnalysis(
            hot_words=self._normalize_topics(self._clean_counts(parsed.hot_words)),
            questions=self._clean_list(parsed.questions),
            negative_feedback=self._clean_list(parsed.negative_feedback, limit=6),
            purchase_intent=self._clean_list(parsed.purchase_intent, limit=6),
            repeated_questions=self._clean_pairs(
                parsed.repeated_questions,
                limit=8,
            ),
            repeated_comments=self._clean_pairs(
                parsed.repeated_comments,
                limit=6,
            ),
        )

        summary = [f"AI 语义分析：本窗口 {total} 条文本"]
        if total > len(selected):
            summary[0] += f"，分析最近 {len(selected)} 条"
        summary.extend(
            f"高频关注：{topic}（{count}条）"
            for topic, count in analysis.hot_words.items()
        )
        summary.extend(
            f"重复问题：{question}（{count}次）"
            for question, count in analysis.repeated_questions.items()
        )
        summary.extend(
            f"刷屏文本：{text}（{count}次）"
            for text, count in analysis.repeated_comments.items()
        )
        summary.extend(f"负面反馈：{item}" for item in analysis.negative_feedback)
        summary.extend(f"购买意向：{item}" for item in analysis.purchase_intent)
        summary.extend(
            f"语义摘要：{item}"
            for item in self._clean_list(parsed.summary, limit=3)
        )
        return InteractionResult(
            comment_analysis=analysis,
            summary=summary,
            mode="deepseek",
        )
