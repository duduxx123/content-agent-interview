import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content_agent.schemas import Suggestion


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAFE_HOLD_TEXT = "该话术命中需核验的表达，已暂缓播报；请按商品资料修改后再使用。"

# Normalize common live-commerce obfuscation before dictionary matching.
_WHITESPACE_RE = re.compile(r"[\s ​‌‍﻿]+")
_SEPARATOR_RE = re.compile(r"[*·•\-_~|/\\]+")
_NEGATION_RE = re.compile(
    r"(?:不是|并非|没有|没|从未|未曾|绝不|并不|不能(?:说|称|保证|确保|承诺)?|"
    r"不会|不可|不得|不算|谈不上|不存在|无法(?:保证|确保|说|称)?|"
    r"不承诺|不保证|不宣称|不表示|不代表|不构成|未能|未|无|别|勿|不)"
    r"(?:毫无|毫|完全|任何|一点|丝毫|绝对|那么|这么|所谓)?\s*$"
)
_QUOTE_RE = re.compile(
    r"(?:(?:有人|有观众|有粉丝|观众|粉丝)(?:问|说)|是不是|是否|据说|据称|听说|"
    r"网传|传言|疑问|询问|咨询)\s*$"
)
_QUESTION_AFTER_RE = re.compile(r"^\s*(?:吗|么|呢|嘛|？|\?)")

# Fixed expressions that contain a risk term but do not make the corresponding claim.
_AFTER_EXCEPTIONS = {
    "第一": re.compile(
        r"^(?:步|次|段|项|条|部分|章|节|阶段|时间|季度|周|天|批|轮|现场|视角|"
        r"人称|作者|页|集|期|届|书记|号|版)"
    ),
    "最好": re.compile(r"^(?:先|还是|在|去|问|看|等|咨询|确认|对照|以|不要|别|选择|提前|避免)"),
    "唯一": re.compile(r"^(?:编号|编码|标识|码|键|id)"),
    "最高": re.compile(r"^(?:温度|气温|限速|限值)"),
    "最低": re.compile(r"^(?:温度|气温|限值)"),
}


@dataclass(frozen=True)
class _Finding:
    term: str
    category: str
    risk_level: str
    replacement: str
    matched: str
    start: int
    end: int
    decision: str
    reason: str
    context: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "category": self.category,
            "risk_level": self.risk_level,
            "replacement": self.replacement,
            "matched": self.matched,
            "decision": self.decision,
            "reason": self.reason,
            "context": self.context,
        }


class ComplianceModule:
    def __init__(
        self,
        rules_path: str | Path = PROJECT_ROOT / "config" / "compliance_rules.json",
    ) -> None:
        data = json.loads(Path(rules_path).read_text(encoding="utf-8-sig"))
        self.notice = data.get("notice", "")
        self.rules: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for group in data.get("groups", []):
            category = str(group.get("category", "未分类"))
            risk_level = str(group.get("risk_level", "review"))
            replacement = str(group.get("replacement", "请根据可核验的商品资料重新表述。"))
            for raw_term in group.get("terms", []):
                term = str(raw_term).strip()
                if not term or (term, category) in seen:
                    continue
                seen.add((term, category))
                self.rules.append(
                    {
                        "term": term,
                        "category": category,
                        "risk_level": risk_level,
                        "replacement": replacement,
                        "patterns": tuple(
                            self._compile_variant(variant)
                            for variant in self._variant_forms(term)
                        ),
                    }
                )

    @staticmethod
    def _normalize(text: str) -> str:
        """Fold width, spacing, separators and common equivalent expressions."""
        normalized = unicodedata.normalize("NFKC", text).casefold()
        normalized = _WHITESPACE_RE.sub("", normalized)
        normalized = _SEPARATOR_RE.sub("", normalized)
        normalized = normalized.replace("蕞", "最")
        normalized = normalized.replace("百分之百", "100%")
        # "没有副作用" / "无任何副作用" are the same claim as "无副作用".
        normalized = normalized.replace("没有", "无")
        normalized = normalized.replace("无任何", "无")
        return normalized

    @staticmethod
    def _variant_forms(term: str) -> set[str]:
        variants = {term}
        if "100%" in term:
            variants.add(term.replace("100%", "百分之百"))
            variants.add(term.replace("100%", "百分百"))
        if term.startswith("零"):
            variants.add("0" + term[1:])
        if term == "第一":
            variants.update({"第1", "no.1", "no1"})
        return variants

    @staticmethod
    def _compile_variant(variant: str) -> re.Pattern[str]:
        # Normalized text has no whitespace or common separators between characters.
        return re.compile("".join(re.escape(char) for char in variant.casefold()))

    @staticmethod
    def _dedupe_overlaps(findings: list[_Finding]) -> list[_Finding]:
        """Keep the longest match when several dictionary entries overlap."""
        findings.sort(key=lambda item: (item.start, -(item.end - item.start), item.term))
        selected: list[_Finding] = []
        for finding in findings:
            if any(
                kept.start <= finding.start and finding.end <= kept.end
                for kept in selected
            ):
                continue
            selected.append(finding)
        return selected

    @staticmethod
    def _classify(term: str, text: str, start: int, end: int) -> tuple[str, str]:
        before = text[max(0, start - 16) : start]
        after = text[end : end + 12]
        exception = _AFTER_EXCEPTIONS.get(term)
        if exception is not None and exception.match(after):
            return "exempt", "固定搭配例外"
        if _QUESTION_AFTER_RE.match(after):
            return "exempt", "询问语境"
        if _QUOTE_RE.search(before):
            return "exempt", "转述或询问语境"
        if _NEGATION_RE.search(before):
            return "exempt", "否定或免责语境"
        return "hit", "命中风险词"

    def _find(self, text: str) -> list[_Finding]:
        normalized = self._normalize(text)
        findings: list[_Finding] = []
        for rule in self.rules:
            for pattern in rule["patterns"]:
                for match in pattern.finditer(normalized):
                    start, end = match.span()
                    decision, reason = self._classify(rule["term"], normalized, start, end)
                    findings.append(
                        _Finding(
                            term=rule["term"],
                            category=rule["category"],
                            risk_level=rule["risk_level"],
                            replacement=rule["replacement"],
                            matched=match.group(0),
                            start=start,
                            end=end,
                            decision=decision,
                            reason=reason,
                            context=normalized[max(0, start - 6) : min(len(normalized), end + 6)],
                        )
                    )
        return self._dedupe_overlaps(findings)

    def screen(self, text: str) -> dict[str, Any]:
        """Return explainable hit/exemption records for one piece of text."""
        findings = self._find(text)
        return {
            "normalized": self._normalize(text),
            "hits": [item.as_dict() for item in findings if item.decision == "hit"],
            "exempt": [item.as_dict() for item in findings if item.decision == "exempt"],
        }

    def filter(self, candidates: list[Suggestion]) -> list[Suggestion]:
        """Screen generated speech/action text and attach contextual rewrite guidance."""
        for item in candidates:
            output_text = f"{item.suggested_script}\n{item.recommended_action}"
            findings = self._find(output_text)
            hits = [finding for finding in findings if finding.decision == "hit"]
            exempt = [finding for finding in findings if finding.decision == "exempt"]

            if not hits:
                item.compliance_status = "通过词库预筛查（仍需按语境复核）"
                if exempt:
                    item.compliance_status = (
                        f"通过词库预筛查（已排除 {len(exempt)} 处语境例外，仍需按语境复核）"
                    )
                item.compliance_replacements = []
                continue

            hit_terms = list(dict.fromkeys(finding.term for finding in hits))
            guidance = list(dict.fromkeys(finding.replacement for finding in hits))
            joined_terms = "、".join(hit_terms[:8])
            status = (
                f"需人工复核：命中风险词 {joined_terms}"
                + ("等" if len(hit_terms) > 8 else "")
            )
            if exempt:
                status += f"（已排除 {len(exempt)} 处语境例外）"
            item.compliance_status = status
            item.compliance_replacements = guidance
            item.suggested_script = SAFE_HOLD_TEXT
            item.recommended_action = "按下方替代建议修改，并核对商品资料和宣传依据后再播报。"
            item.score = min(item.score, 0.1)
            item.priority = "低"
        return candidates
