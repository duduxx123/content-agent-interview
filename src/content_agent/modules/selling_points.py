from content_agent.providers.product_catalog import ProductCatalog
from content_agent.schemas import AgentInput, Suggestion


INTENT_BY_TOPIC = {
    "价格": "转化",
    "试用/购买": "转化",
    "肤质": "答疑",
    "成分": "答疑",
    "功效": "答疑",
    "用法": "答疑",
    "商品介绍": "讲解",
}


def intent_for(topic: str) -> str:
    return INTENT_BY_TOPIC.get(topic, "讲解")


class SellingPointModule:
    def suggest(self, payload: AgentInput, interactions: list[str]) -> list[Suggestion]:
        """Match common live questions to supplied product facts without inventing claims."""
        product = payload.product
        benefits = "、".join(product.benefits) if product.benefits else "商品信息"
        ingredients = "、".join(product.ingredients)
        analysis = payload.comment_analysis
        topics = analysis.hot_words
        candidates: list[Suggestion] = []
        audience_text = " ".join(
            [
                *payload.recent_comments,
                *analysis.questions,
                *analysis.negative_feedback,
                *analysis.purchase_intent,
                *topics.keys(),
            ]
        )
        matched_points = ProductCatalog.match_selling_points(product, audience_text)
        matched_topics: set[str] = set()

        def add(topic: str, score: float, script: str, action: str, reason: str) -> None:
            candidates.append(Suggestion(
                priority="中",
                score=score,
                suggested_script=script,
                recommended_action=action,
                trigger_reason=reason,
                compliance_status="待检查",
                topic=topic,
                intent=intent_for(topic),
            ))

        for point, keywords in matched_points[:3]:
            matched_topics.add(point.topic)
            if point.topic == "成分":
                script = f"商品资料列出的{point.description}，可以在详情页核对完整成分信息。"
            else:
                script = (
                    f"当前商品资料列出的{point.label}是{point.description}。"
                    "具体适用范围和使用注意事项请以商品详情为准。"
                )
            if point.verified:
                action = f"展示核验过的商品资料，说明{point.label}"
            else:
                action = f"先核对商品标签或备案资料，再说明{point.label}"
            add(
                point.topic,
                min(0.74 + 0.04 * len(keywords), 0.9),
                script,
                action,
                f"观众提到：{'、'.join(keywords[:3])}",
            )

        price_questions = [item for item in analysis.negative_feedback if any(term in item for term in ("贵", "价格", "不值"))]
        if topics.get("价格", 0) or price_questions:
            price_text = f"，当前标注价格为 {product.price:g} 元" if product.price is not None else "，价格请以商品页面实时展示为准"
            size_text = f"，规格为 {product.specification}" if product.specification else ""
            add(
                "价格", 0.82 if price_questions else 0.68,
                f"关于大家关心的价格，这款{product.name}{size_text}{price_text}。可以对照规格和商品页活动信息再做判断。",
                "展示商品规格、到手价和当前活动规则",
                price_questions[0] if price_questions else f"价格相关关注 {topics['价格']} 条",
            )

        if topics.get("肤质", 0) and "肤质" not in matched_topics:
            benefit_text = "、".join(product.benefits) if product.benefits else ""
            claims = f"，商品资料标注{benefit_text}" if benefit_text else ""
            add(
                "肤质", 0.76,
                f"关于肤质适用问题，这款{product.name}{claims}。具体适用人群和使用注意事项请以商品说明为准。",
                "展示商品详情中的适用肤质与注意事项",
                f"识别到肤质相关关注 {topics['肤质']} 条",
            )

        if topics.get("成分", 0) and ingredients and "成分" not in matched_topics:
            add(
                "成分", 0.72,
                f"这款{product.name}的商品资料列出了{ingredients}，大家可以按详情页核对成分信息。",
                "展示商品成分表，并按详情页说明介绍",
                f"识别到成分相关关注 {topics['成分']} 条",
            )

        if topics.get("功效", 0) and benefits and "功效" not in matched_topics:
            add(
                "功效", 0.70,
                f"商品资料标注的特点包括{benefits}；具体效果因人而异，请以商品说明和实际体验为准。",
                "结合商品详情介绍已标注的特点，避免承诺效果",
                f"识别到功效相关关注 {topics['功效']} 条",
            )

        if topics.get("用法", 0):
            usage = "；".join(product.usage_instructions)
            usage_text = f"商品资料列出的使用方法为：{usage}。" if usage else "请以商品说明书中的步骤和用量为准。"
            add(
                "用法", 0.66,
                f"关于{product.name}的使用方法，{usage_text}",
                "展示商品说明中的使用步骤",
                f"识别到用法相关关注 {topics['用法']} 条",
            )

        if topics.get("试用/购买", 0) or analysis.purchase_intent:
            add(
                "试用/购买", 0.78,
                f"有观众在问试用或购买方式，请以直播间商品链接当前展示的规格、库存和活动信息为准。",
                "指向商品卡，确认小样、库存和活动信息后回答",
                analysis.purchase_intent[0] if analysis.purchase_intent else f"识别到试用/购买关注 {topics.get('试用/购买', 0)} 条",
            )

        if not candidates:
            ingredient_text = f"，商品资料列出的成分有{ingredients}" if ingredients else ""
            add(
                "商品介绍", 0.5,
                f"这款{product.name}主打{benefits}{ingredient_text}，规格为{product.specification or '以商品页为准'}。",
                "继续按商品详情介绍规格、成分和标注特点",
                "本窗口没有识别到明确问题，提供商品基础介绍",
            )

        return sorted(candidates, key=lambda item: item.score, reverse=True)[:3]
