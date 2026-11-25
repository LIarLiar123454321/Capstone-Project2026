#讓AI能根據tool名稱，執行對應的工具

# 工具註冊表
TOOL_REGISTRY = {
}

def excexute_tool(tool_name: str):
    tool = TOOL_REGISTRY.get(tool_name)

    if tool is None:
        return {
            "error": f"找不到工具：{tool_name}"
        }