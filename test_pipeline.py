import asyncio
from agents.pipeline import run_analysis
from dotenv import load_dotenv

load_dotenv()

async def main():
    repo_info = {"full_name": "affaan-m/everything-claude-code"}
    async for event in run_analysis(repo_info, query="__analysis__"):
        print(event)

if __name__ == "__main__":
    asyncio.run(main())
