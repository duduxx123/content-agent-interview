import re
from collections import Counter

from content_agent.schemas import AgentInput, CommentAnalysis, InteractionResult


TOPIC_KEYWORDS = {
    "价格": ("价格", "多少钱", "贵", "便宜", "优惠", "券", "到手价"),
    "肤质": ("油皮", "干皮", "敏感肌", "肤质", "皮肤", "适合我", "能用吗"),
    "成分": ("成分", "水杨酸", "烟酰胺", "透明质酸", "酒精", "香精"),
    "功效": ("功效", "控油", "修护", "保湿", "效果", "有用吗"),
    "用法": ("怎么用", "用法", "使用方法", "早上", "晚上", "步骤"),
    "试用/购买": ("小样", "试用", "怎么买", "链接", "下单", "购买", "库存", "发货"),
}
NEGATIVE_TERMS = (
    "太贵", "贵了", "价格高", "不值", "没效果", "没用", "不好用", "过敏", "刺激",
    "失望", "不喜欢", "假货", "不靠谱", "骗人", "差评",
)
PURCHASE_TERMS = (
    "怎么买", "在哪买", "链接", "下单", "想买", "已拍", "购买", "有小样", "小样",
    "优惠券", "有券吗", "包邮吗", "库存", "什么时候发货",
)
QUESTION_TERMS = (
    "吗", "呢", "怎么", "什么", "多少", "能不能", "可以", "适合", "如何", "有没有", "为什么",
)


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?；;：:]+", "", text).casefold()


def classify_topics(text: str) -> list[str]:
    """Return the live topics mentioned in a comment or repeated-question key."""
    return [
        topic
        for topic, keywords in TOPIC_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]


class InteractionModule:
    def analyze(self, payload: AgentInput) -> InteractionResult:
        """Classify a window of comments with a small, explainable keyword baseline."""
        comments = [comment.strip() for comment in payload.recent_comments if comment.strip()]
        if not comments:
            analysis = payload.comment_analysis.model_copy(deep=True)
        else:
            topic_counts: Counter[str] = Counter()
            comment_counts: Counter[str] = Counter()
            questions: list[str] = []
            question_counts: Counter[str] = Counter()
            negative: list[str] = []
            purchase: list[str] = []

            for comment in comments:
                normalized = _normalize(comment)
                comment_counts[normalized] += 1
                for topic in classify_topics(comment):
                    topic_counts[topic] += 1
                is_question = (
                    "?" in comment or "？" in comment
                    or any(keyword in comment for keyword in QUESTION_TERMS)
                )
                if is_question:
                    question_counts[normalized] += 1
                    if normalized not in {_normalize(item) for item in questions}:
                        questions.append(comment)
                if any(term in comment for term in NEGATIVE_TERMS):
                    negative.append(comment)
                if any(term in comment for term in PURCHASE_TERMS):
                    purchase.append(comment)

            analysis = CommentAnalysis(
                hot_words=dict(topic_counts),
                negative_feedback=list(dict.fromkeys(negative)),
                purchase_intent=list(dict.fromkeys(purchase)),
                questions=questions,
                repeated_questions={
                    question: count
                    for question, count in question_counts.items()
                    if count > 1
                },
                # Non-question duplicates are treated as spam/flood signals.
                repeated_comments={
                    text: count
                    for text, count in comment_counts.items()
                    if count > 1 and text not in question_counts
                },
            )

        summary = [f"当前阶段：{payload.live_state.current_stage}"]
        summary.append(f"本窗口收到 {len(comments)} 条文本消息")
        summary.extend(
            f"高频关注：{topic}（{count}条）"
            for topic, count in sorted(analysis.hot_words.items(), key=lambda item: item[1], reverse=True)
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
        for event_type, count in payload.event_counts.items():
            if event_type != "danmaku" and count:
                summary.append(f"直播互动：{event_type} {count}次")
        return InteractionResult(comment_analysis=analysis, summary=summary, mode="rules")
