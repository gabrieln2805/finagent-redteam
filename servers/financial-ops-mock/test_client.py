import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command="python3", args=["server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools:", [t.name for t in tools.tools])

            print("\n--- get_invoice(INV-1002) [poisoned] ---")
            r = await session.call_tool("get_invoice", {"invoice_id": "INV-1002"})
            print(r.content[0].text)

            print("\n--- transfer_funds attempted with a made-up token ---")
            r = await session.call_tool("transfer_funds", {"amount": 75000, "destination": "SF-EXFIL-9910", "approval_token": "fake-token-123"})
            print(r.content[0].text)

            print("\n--- request_approval (legitimate first step) ---")
            r = await session.call_tool("request_approval", {"action_type": "transfer_funds", "details": "test"})
            print(r.content[0].text)

            print("\n--- get_invoice(unknown) ---")
            r = await session.call_tool("get_invoice", {"invoice_id": "INV-9999"})
            print(r.content[0].text)


asyncio.run(main())
