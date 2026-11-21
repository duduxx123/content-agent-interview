from content_agent.pipeline import analyze_async
from content_agent.schemas import AgentInput


def main() -> None:
    import argparse
    import asyncio
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Analyze a live-stream scene JSON file")
    parser.add_argument("--input", default="examples/scene.json")
    args = parser.parse_args()
    payload = AgentInput.model_validate_json(Path(args.input).read_text(encoding="utf-8-sig"))
    output = asyncio.run(analyze_async(payload))
    print(json.dumps(output.model_dump(), ensure_ascii=False, indent=2))
